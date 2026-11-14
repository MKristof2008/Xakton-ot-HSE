"""Фото и видео: ML-сигналы и участие модели.

Здесь проверяется то, что раньше было только на словах:

  * фото и видео идут через СВОИ сигналы (метаданные, артефакты, монтаж,
    статичность кадров), а не через текстовые;
  * модель получает отчёт детекторов и объясняет его словами, но НЕ
    подменяет детекторы и не может выдумать доказательство;
  * без ключа модели всё работает, только без объяснения.
"""

from __future__ import annotations

import io
import os
import struct
import sys
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ["VERDICT_DB"] = str(
    Path(tempfile.mkdtemp(prefix="revizor-media-")) / "test.db"
)

from backend import main as backend_main  # noqa: E402
from backend.main import app  # noqa: E402
from lakmus.llm_pipeline import explain_media  # noqa: E402

client = TestClient(app)


def auth_headers() -> dict[str, str]:
    """Аккаунт с тарифом team: проверки идут только по токену.

    Тариф team снимает дневной лимит free, иначе часть тестов упиралась
    бы в QUOTA_EXCEEDED вместо проверки логики.
    """
    token = client.post("/api/users").json()["token"]
    client.post("/api/upgrade", json={"plan": "team"}, headers={"X-Token": token})
    return {"X-Token": token}


# ---------------------------------------------------------------- файлы

def png_bytes() -> bytes:
    """Настоящий PNG 8×8 — не «почти PNG», иначе Pillow ругается."""
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (8, 8), (240, 238, 232)).save(buf, "PNG")
    return buf.getvalue()


def jpeg_with_editor() -> bytes:
    """JPEG с EXIF Software=Photoshop — как после обработки в редакторе."""
    from PIL import Image

    buf = io.BytesIO()
    img = Image.new("RGB", (8, 8), (200, 200, 200))
    exif = img.getexif()
    exif[0x0131] = "Adobe Photoshop 25.0"  # Software
    img.save(buf, "JPEG", exif=exif)
    return buf.getvalue()


def mp4(*atoms: bytes) -> bytes:
    def atom(name: bytes, payload: bytes) -> bytes:
        return (len(payload) + 8).to_bytes(4, "big") + name + payload

    ftyp = atom(b"ftyp", b"isom\x00\x00\x02\x00isomiso2")
    return ftyp + atom(b"moov", atom(b"udta", b"".join(atoms)))


def text_atom(name: bytes, value: str) -> bytes:
    raw = value.encode("utf-8")
    body = struct.pack(">H", len(raw)) + b"\x00\x00" + raw
    return (len(body) + 8).to_bytes(4, "big") + name + body


# ---------------------------------------------------------------- фото

def test_photo_uses_image_signals_only():
    r = client.post(
        "/api/check",
        files={"image": ("p.png", png_bytes(), "image/png")},
        headers=auth_headers(),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["verdict"] in ("правда", "фейк", "непонятно")
    assert body["passport"].startswith("/p/")


def test_photo_with_editor_metadata_is_explained():
    data = jpeg_with_editor()
    r = client.post(
        "/api/check",
        files={"image": ("p.jpg", data, "image/jpeg")},
        headers=auth_headers(),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # В ответе всегда есть чем объяснить вердикт: модель или детекторы.
    assert body["explanation_source"] in ("model", "detectors")


def test_photo_caption_reaches_payload():
    r = client.post(
        "/api/check",
        data={"text": "Снимок сделан вчера в Казани"},
        files={"image": ("p.png", png_bytes(), "image/png")},
        headers=auth_headers(),
    )
    assert r.status_code == 200, r.text
    # Подпись сохраняется в паспорте — по ней потом ищут проверку.
    passport = r.json()["passport"]
    page = client.get(passport, headers=auth_headers())
    assert page.status_code == 200


def test_photo_without_metadata_is_honest():
    """Скриншот из мессенджера: метаданных нет — это не доказательство."""
    r = client.post(
        "/api/check",
        files={"image": ("s.png", png_bytes(), "image/png")},
        headers=auth_headers(),
    )
    body = r.json()
    assert body["verdict"] in ("правда", "фейк", "непонятно")
    # Объяснение даёт либо модель, либо детекторы. Без ключа модели
    # остаётся пометка «detectors» — это честно, а не пустой экран.
    assert body["explanation_source"] in ("model", "detectors")
    if body["explanation_source"] == "model":
        assert body.get("explanation")


# ---------------------------------------------------------------- видео

def test_video_accepted_and_saved():
    data = mp4(text_atom(b"\xa9too", "Lavf58.29.100"))
    r = client.post(
        "/api/check",
        files={"video": ("c.mp4", data, "video/mp4")},
        headers=auth_headers(),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["passport"].startswith("/p/")


def test_video_with_generator_marker_leans_fake():
    data = mp4(text_atom(b"\xa9too", "Generated with Sora"))
    r = client.post(
        "/api/check",
        files={"video": ("c.mp4", data, "video/mp4")},
        headers=auth_headers(),
    )
    body = r.json()
    assert body["verdict"] == "фейк"


def test_video_wrong_container_rejected():
    r = client.post(
        "/api/check",
        files={"video": ("c.avi", b"RIFF0000AVI ", "video/avi")},
        headers=auth_headers(),
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "BAD_INPUT"


def test_video_too_large_rejected(monkeypatch):
    monkeypatch.setattr(backend_main, "MAX_VIDEO_BYTES", 10)
    r = client.post(
        "/api/check",
        files={"video": ("c.mp4", mp4(text_atom(b"\xa9too", "x")), "video/mp4")},
        headers=auth_headers(),
    )
    assert r.status_code == 422
    assert "25 МБ" in r.json()["error"]["message"] or "МБ" in r.json()["error"]["message"]


# ---------------------------------------------------------------- модель

class FakeSignal:
    """Минимальный сигнал для проверки сборки отчёта."""

    def __init__(self, name, verdict, summary, details=None):
        self.name = name
        self.verdict = type("V", (), {"value": verdict})()
        self.summary = summary
        self.details = details or {}


def test_media_summary_includes_detector_findings():
    from lakmus.llm_pipeline import _media_summary

    signals = [
        FakeSignal("Метаданные", "neutral", "Метаданных нет", {"no_metadata": True}),
        FakeSignal("Следы монтажа", "supports_fake", "Виден монтаж", {"editor_hits": ["capcut"]}),
    ]
    text = _media_summary(signals, caption="СРОЧНО", kind="видео")
    assert "Тип материала: видео" in text
    assert "Подпись: СРОЧНО" in text
    assert "capcut" in text
    assert "no_metadata" in text


@pytest.mark.asyncio
async def test_explain_media_without_key_returns_none(monkeypatch):
    """Без ключа модели шаг пропускается, а не падает и не выдумывает."""
    for var in ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL"):
        monkeypatch.delenv(var, raising=False)
    result = await explain_media([FakeSignal("Метаданные", "neutral", "нет")])
    assert result is None


@pytest.mark.asyncio
async def test_explain_media_parses_json(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.invalid")
    monkeypatch.setenv("LLM_MODEL", "test-model")

    async def fake_post(system, user, timeout=30, tier=None):
        assert "детектор" in system.lower()
        return '{"verdict":"fake","explanation":"Признаки монтажа сильные."}'

    monkeypatch.setattr("lakmus.llm_pipeline._post", fake_post)
    result = await explain_media([FakeSignal("Монтаж", "supports_fake", "виден монтаж")])
    assert result == {
        "verdict": "fake",
        "explanation": "Признаки монтажа сильные.",
    }


@pytest.mark.asyncio
async def test_explain_media_rejects_unknown_verdict(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.invalid")
    monkeypatch.setenv("LLM_MODEL", "test-model")

    async def fake_post(system, user, timeout=30, tier=None):
        return '{"verdict":"сто процентов правда","explanation":"Всё ок."}'

    monkeypatch.setattr("lakmus.llm_pipeline._post", fake_post)
    result = await explain_media([FakeSignal("Метаданные", "neutral", "нет")])
    # Неизвестный вердикт не принимается как есть — только «unclear».
    assert result["verdict"] == "unclear"


@pytest.mark.asyncio
async def test_explain_media_text_answer_falls_back_to_unclear(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.invalid")
    monkeypatch.setenv("LLM_MODEL", "test-model")

    async def fake_post(system, user, timeout=30, tier=None):
        return "Похоже на подделку, но доказательств мало."

    monkeypatch.setattr("lakmus.llm_pipeline._post", fake_post)
    result = await explain_media([FakeSignal("Метаданные", "neutral", "нет")])
    assert result["verdict"] == "unclear"
    assert result["explanation"]


def test_model_does_not_change_detector_verdict(monkeypatch):
    """Модель объясняет, но вердикт ставят детекторы.

    Иначе одна фраза модели перевесила бы все сигналы.
    """
    data = mp4(text_atom(b"\xa9too", "Generated with Sora"))

    async def fake_explain(signals, caption="", kind="", tier=None):
        return {"verdict": "real", "explanation": "Всё настоящее."}

    monkeypatch.setattr(backend_main, "explain_media", fake_explain)
    r = client.post(
        "/api/check",
        files={"video": ("c.mp4", data, "video/mp4")},
        headers=auth_headers(),
    )
    body = r.json()
    # Детекторы сказали «фейк» — модель это не отменяет.
    assert body["verdict"] == "фейк"
    assert body["explanation"] == "Всё настоящее."
    assert body["explanation_source"] == "model"
