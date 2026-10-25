import random
import time
from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware

# Создаем локальное приложение
app = FastAPI(title="TrueSight AI - Localhost Backend")

# Разрешаем фронтенду подключаться к нашему локальному хосту
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MOCK_RESPONSES = {
    "fake": {
        "trust_score": 14,
        "metadata_analysis": "Critical anomalies found in EXIF data. Timestamps modified.",
        "artifact_analysis": "Visual analysis revealed clear AI artifacts of diffusion models.",
        "logic_analysis": "Text content contains high-level emotional manipulation.",
        "action_plan": [
            "Do not forward this media asset to any work or family chats.",
            "Run a reverse image search to locate the original unaltered source."
        ]
    },
    "true": {
        "trust_score": 92,
        "metadata_analysis": "Metadata is intact. No trace of tampering.",
        "artifact_analysis": "Digital cloning or audio/video manipulation artifacts not detected.",
        "logic_analysis": "Fact-checking confirms information aligns with official press releases.",
        "action_plan": [
            "This asset passed verification and has a high trust score.",
            "You can safely use and cite this content in your workflow."
        ]
    }
}

@app.post("/api/verify")
async def verify_media(file: UploadFile = File(...)):
    time.sleep(1.5)  # Имитация задержки обработки локально
    filename = file.filename.lower()
    if "fake" in filename or "test" in filename:
        return MOCK_RESPONSES["fake"]
    else:
        response = MOCK_RESPONSES["true"].copy()
        response["trust_score"] = random.randint(75, 95)
        return response

if __name__ == "__main__":
    import uvicorn
    # Запуск локального сервера на порту 8000
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
