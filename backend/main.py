"""FastAPI-обёртка над пайплайном «До репоста».

Принимает текст сообщения + источники (как в ml/doreposta/schemas.py),
возвращает статусы утверждений и готовый ответ для пересылки.

Запуск: py -3 uvicorn main:app --reload --port 8000
Ключ модели backend берёт из .env рядом с ../ml (см. ml/.env.example).
"""
import os
import sys

from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware

# пайплайн живёт в ../ml
ML_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ml")
sys.path.insert(0, os.path.abspath(ML_DIR))

env_path = os.path.join(os.path.abspath(ML_DIR), ".env")
if os.path.exists(env_path):
    for line in open(env_path, encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

from doreposta import (  # noqa: E402
    FakeLLMClient, LLMClient, Source, EvaluationResult,
    compose_reply, evaluate_claims, extract_claims, validate_result,
)
from doreposta.schemas import Claim  # noqa: E402
from pydantic import BaseModel  # noqa: E402

app = FastAPI(title="До репоста — фактчекинг API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def make_client():
    """Живой клиент, если заданы LLM_* в .env; иначе fake для локальных прогонов."""
    if os.environ.get("LLM_API_KEY") and os.environ.get("LLM_BASE_URL"):
        return LLMClient()
    return FakeLLMClient(lambda s, u: '{"claims": [], "uncheckable_reason": "нет ключа — backend в demo-режиме"}')


class VerifyTextRequest(BaseModel):
    text: str
    sources: list[Source] = []
    message_date: str | None = None


class ClaimReply(BaseModel):
    claim_id: str
    text: str
    status: str
    explanation: str
    limitations: list[str]
    next_action: str


class VerifyTextResponse(BaseModel):
    reply: str
    claims: list[ClaimReply]


@app.post("/api/verify-text", response_model=VerifyTextResponse)
async def verify_text(req: VerifyTextRequest):
    """Основной эндпоинт по ТЗ: текст -> статусы утверждений + ответ для чата."""
    client = make_client()
    ctx = {"message_date": req.message_date} if req.message_date else {}

    extraction = await extract_claims(req.text, ctx, client)
    if not extraction.claims:
        return VerifyTextResponse(
            reply=extraction.uncheckable_reason or "Проверяемых фактов не найдено.",
            claims=[])

    claims = [Claim(id=c.id, text=c.text, original_span=c.original_span) for c in extraction.claims]
    evaluation = await evaluate_claims(claims, req.sources, ctx, client)
    evaluation = validate_result(evaluation, req.sources, claims)
    reply = compose_reply(evaluation, req.sources)

    return VerifyTextResponse(
        reply=reply,
        claims=[ClaimReply(
            claim_id=cr.id, text=cr.text, status=cr.status.value,
            explanation=cr.explanation, limitations=cr.limitations,
            next_action=cr.next_action,
        ) for cr in evaluation.claims],
    )


# --- legacy-мок старого демо (TrustLens), оставлен для совместимости с фронтом ---
import random  # noqa: E402

MOCK_RESPONSES = {
    "fake": {
        "trust_score": 14,
        "metadata_analysis": "Critical anomalies found in EXIF data. Timestamps modified.",
        "artifact_analysis": "Visual analysis revealed clear AI artifacts of diffusion models.",
        "logic_analysis": "Text content contains high-level emotional manipulation.",
        "action_plan": [
            "Do not forward this media asset to any work or family chats.",
            "Run a reverse image search to locate the original unaltered source.",
        ],
    },
    "true": {
        "trust_score": 92,
        "metadata_analysis": "Metadata is intact. No trace of tampering.",
        "artifact_analysis": "Digital cloning or audio/video manipulation artifacts not detected.",
        "logic_analysis": "Fact-checking confirms information aligns with official press releases.",
        "action_plan": [
            "This asset passed verification and has a high trust score.",
            "You can safely use and cite this content in your workflow.",
        ],
    },
}


@app.post("/api/verify")
async def verify_media(file: UploadFile = File(...)):
    """Старый мок по файлу. Для фактчекинга текста используйте /api/verify-text."""
    filename = (file.filename or "").lower()
    if "fake" in filename or "test" in filename:
        return MOCK_RESPONSES["fake"]
    response = MOCK_RESPONSES["true"].copy()
    response["trust_score"] = random.randint(75, 95)
    return response


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
