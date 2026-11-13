"""Пути и константы backend «Свидетель»."""

from __future__ import annotations

import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
REPO_DIR = BACKEND_DIR.parent
ML_DIR = REPO_DIR / "ml"

#: Каталог для загруженных файлов и превью (отдаётся StaticFiles по /media).
MEDIA_DIR = Path(os.environ.get("WITNESS_MEDIA") or BACKEND_DIR / "media")
#: JSON с предзаполненными лотами для демо (создаёт агент 4 в ml/data).
DEMO_LISTINGS_PATH = Path(
    os.environ.get("WITNESS_DEMO_LISTINGS") or ML_DIR / "data" / "demo_listings.json"
)


def demo_listings_path() -> Path:
    """Актуальный путь демо-лотов: WITNESS_DEMO_LISTINGS или ml/data/demo_listings.json."""
    override = os.environ.get("WITNESS_DEMO_LISTINGS")
    return Path(override) if override else ML_DIR / "data" / "demo_listings.json"

#: Лимит загрузки — 15 МБ.
MAX_UPLOAD_BYTES = 15 * 1024 * 1024
#: Лимит тела запроса: запас над лимитом файла на multipart-заголовки.
MAX_REQUEST_BYTES = MAX_UPLOAD_BYTES + 1 * 1024 * 1024
#: Разрешённые типы: MIME из заголовка и реальные форматы Pillow.
ALLOWED_MIME = {"image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP"}
#: Предел стороны превью.
PREVIEW_MAX_SIDE = 800

#: Оригиналы CORS — только dev-фронтенд Vite.
CORS_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]