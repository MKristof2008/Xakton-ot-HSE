"""HTTP API «Проверено» — фактчекинг по замыслу эксперта NMH.

Две ступени по подписке:
  free — вердикт и уровень доверия;
  pro  — плюс разбор: сигналы, доказательства, источники, что проверить дальше.

Плюс вкладка топов: что проверяют сейчас, по счётчику одинаковых запросов.

Запуск: py -3 -m uvicorn backend.main:app --port 8000
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ML_DIR = Path(__file__).resolve().parent.parent / "ml"
BACKEND_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ML_DIR))
sys.path.insert(0, str(BACKEND_DIR))

env_path = ML_DIR / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())

from lakmus.context import CheckContext  # noqa: E402
from lakmus.pipeline import check as run_check  # noqa: E402
from lakmus.schemas import CheckInput, InputType  # noqa: E402

import store  # noqa: E402

MAX_TEXT = 4000

app = FastAPI(title="Проверено — фактчекинг API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-Token"],
)


# ---------- ошибки в одном формате ----------

def fail(code: str, message: str, status: int) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


@app.exception_handler(404)
async def not_found(request: Request, exc: Any) -> JSONResponse:
    return fail("NOT_FOUND", "такого адреса нет", 404)


# ---------- модели ----------

class CheckRequest(BaseModel):
    text: str = Field(..., max_length=MAX_TEXT)


class UpgradeRequest(BaseModel):
    plan: str = "pro"


class PinRequest(BaseModel):
    text_hash: str
    title: str = ""


# ---------- сборка ответа ----------

def level_label(level: str) -> str:
    return {
        "confirmed": "Подтверждено",
        "likely_real": "Скорее правда",
        "fog": "Туман",
        "doubtful": "Сомнительно",
        "likely_fake": "Скорее фейк",
    }.get(level, level)


def verdict_of(result: Any) -> str:
    """Короткий вердикт для бесплатного тарифа — одно слово."""
    level = result.trust.level.value
    if level in ("confirmed", "likely_real"):
        return "правда"
    if level in ("likely_fake", "doubtful"):
        return "фейк"
    return "непонятно"


def public_payload(result: Any, check_id: str, plan: str) -> dict[str, Any]:
    """Собирает ответ по тарифу. Free не видит разбор — только вердикт."""
    base: dict[str, Any] = {
        "id": check_id,
        "verdict": verdict_of(result),
        "level": result.trust.level.value,
        "level_label": level_label(result.trust.level.value),
        "score": result.trust.score,
        "uncertainty": round(result.trust.uncertainty, 4),
        "plan": plan,
    }
    if plan != "pro":
        base["upgrade_hint"] = (
            "Разбор — почему такой вердикт, источники и что проверить дальше — "
            "доступен по подписке."
        )
        return base

    base["signals"] = [
        {
            "id": s.id,
            "name": s.name,
            "stage": s.stage.value,
            "verdict": s.verdict.value,
            "strength": round(s.strength, 3),
            "reliability": round(s.reliability, 3),
            "summary": s.summary,
            "details": s.details,
        }
        for s in result.signals
    ]
    base["debate"] = {
        "for_real": [{"text": t.text, "signal_ids": t.signal_ids} for t in result.debate.for_real],
        "for_fake": [{"text": t.text, "signal_ids": t.signal_ids} for t in result.debate.for_fake],
    }
    base["provenance"] = [
        {"date": p.date, "where": p.where, "note": p.note} for p in result.provenance
    ]
    base["next_steps"] = [
        {"kind": n.kind.value, "title": n.title, "why": n.why} for n in result.next_steps
    ]
    base["limits"] = result.limits
    base["duration_ms"] = result.duration_ms
    return base


def resolve_user(token: Optional[str]) -> Optional[dict[str, Any]]:
    return store.user_by_token(token or "")


# ---------- эндпоинты ----------

@app.get("/api/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "llm": bool(os.environ.get("LLM_API_KEY")),
        "time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


@app.post("/api/check")
async def check_text(
    req: CheckRequest,
    x_token: Optional[str] = Header(default=None, alias="X-Token"),
) -> Any:
    """Проверить утверждение. Free — вердикт, pro — полный разбор."""
    text = (req.text or "").strip()
    if len(text) < 8:
        return fail("BAD_INPUT", "слишком короткий текст: нужно хотя бы 8 символов", 422)
    if len(text) > MAX_TEXT:
        return fail("BAD_INPUT", f"текст длиннее {MAX_TEXT} символов", 422)

    user = resolve_user(x_token)
    plan = user["plan"] if user else "free"

    if user and plan == "free" and store.free_quota_left(user["id"]) <= 0:
        return fail(
            "QUOTA_EXCEEDED",
            "бесплатные проверки на сегодня закончились. Подписка снимает лимит.",
            429,
        )

    check_id = f"chk_{int(time.time() * 1000) % 10**10:010d}"
    ctx = CheckContext(
        check_id=check_id,
        input=CheckInput(type=InputType.text, extracted_text=text),
        text=text,
    )
    try:
        result = await run_check(ctx, llm=None)
    except Exception as exc:  # пайплайн упал — это не 500 без объяснения
        return fail("CHECK_FAILED", f"проверка не удалась: {type(exc).__name__}", 502)

    payload = public_payload(result, check_id, plan)
    store.save_check(
        text=text,
        verdict=payload["verdict"],
        score=result.trust.score,
        uncertainty=result.trust.uncertainty,
        level=result.trust.level.value,
        full=payload,
        user_id=user["id"] if user else None,
    )
    if user:
        payload["quota_left"] = store.free_quota_left(user["id"]) if plan == "free" else None
    return payload


@app.get("/api/check/{check_id}")
async def get_check(
    check_id: str,
    x_token: Optional[str] = Header(default=None, alias="X-Token"),
) -> Any:
    """Повторно открыть проверку. Разбор отдаётся только по подписке."""
    row = store.get_check(check_id)
    if not row:
        return fail("NOT_FOUND", "проверка не найдена", 404)
    user = resolve_user(x_token)
    plan = user["plan"] if user else "free"
    full = row["full"]
    if plan != "pro":
        return {k: v for k, v in full.items() if k not in (
            "signals", "debate", "provenance", "next_steps", "limits", "duration_ms"
        )} | {"plan": plan, "upgrade_hint": "Разбор доступен по подписке."}
    return full


@app.get("/api/top")
async def top(limit: int = 20, hours: int = 48) -> dict[str, Any]:
    """Топы проверяемых утверждений — та самая вкладка из совета эксперта."""
    limit = max(1, min(50, limit))
    hours = max(1, min(24 * 30, hours))
    items = store.top_items(limit=limit, window_hours=hours)
    for item in items:
        item["level_label"] = level_label(item.get("level") or "fog")
    return {"window_hours": hours, "items": items}


@app.post("/api/top/pin")
async def pin(req: PinRequest) -> Any:
    if not req.text_hash:
        return fail("BAD_INPUT", "нужен text_hash", 422)
    store.pin_top(req.text_hash, req.title)
    return {"ok": True}


@app.get("/api/stats")
async def stats() -> dict[str, Any]:
    return store.stats()


@app.post("/api/users")
async def create_user() -> dict[str, Any]:
    """Гостевой пользователь с бесплатным тарифом и своим токеном."""
    return store.create_user("free")


@app.get("/api/me")
async def me(x_token: Optional[str] = Header(default=None, alias="X-Token")) -> Any:
    user = resolve_user(x_token)
    if not user:
        return fail("UNAUTHORIZED", "нужен токен пользователя", 401)
    out = {"id": user["id"], "plan": user["plan"]}
    if user["plan"] == "free":
        out["quota_left"] = store.free_quota_left(user["id"])
        out["quota_per_day"] = store.FREE_CHECKS_PER_DAY
    return out


@app.post("/api/upgrade")
async def upgrade(
    req: UpgradeRequest,
    x_token: Optional[str] = Header(default=None, alias="X-Token"),
) -> Any:
    """Демо-апгрейд тарифа. В продукте здесь платёжный провайдер."""
    user = resolve_user(x_token)
    if not user:
        return fail("UNAUTHORIZED", "нужен токен пользователя", 401)
    if not store.upgrade_user(x_token or "", req.plan):
        return fail("BAD_INPUT", "неизвестный тариф", 422)
    return {"ok": True, "plan": req.plan}


@app.get("/api/pricing")
async def pricing() -> dict[str, Any]:
    """Тарифы — то, что эксперт просила продумать подробно."""
    return {
        "plans": [
            {
                "id": "free",
                "name": "Бесплатно",
                "price_rub": 0,
                "limits": f"{store.FREE_CHECKS_PER_DAY} проверок в день",
                "features": ["Вердикт: правда, фейк или непонятно", "Уровень доверия"],
            },
            {
                "id": "pro",
                "name": "Разбор",
                "price_rub": 300,
                "limits": "Без ограничений",
                "features": [
                    "Всё из бесплатного",
                    "Почему такой вердикт — по каждому сигналу",
                    "Ссылки на первоисточники",
                    "Что проверить дальше",
                    "Без рекламы",
                ],
                "recommended": True,
            },
            {
                "id": "team",
                "name": "Редакция",
                "price_rub": 5000,
                "limits": "До 10 сотрудников",
                "features": [
                    "Всё из «Разбора»",
                    "Проверка ссылок и скриншотов пачкой",
                    "Доступ к топикам проверок",
                    "Приоритетная поддержка",
                ],
            },
        ],
        "note": "Первый месяц бесплатно: сначала репутация, потом подписка.",
    }

# ---------- раздача собранного интерфейса ----------
# В проде nginx обычно отдаёт статику сам, но если фронт собран в
# frontend/dist, FastAPI может отдать его напрямую — удобно для одного
# контейнера без отдельного веб-сервера.

_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if _DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(_DIST), html=True), name="web")
