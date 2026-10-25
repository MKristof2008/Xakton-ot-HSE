"""Сигнал I6 «Скриншот соцсети»: контекст публикации (раздел 6.3 ТЗ).

OCR только через опциональные pytesseract/PaddleOCR: без них сигнал
возвращает unavailable (или честно использует уже распознанный ctx.text,
если проверка пришла с текстом). Визуальные нестыковки — только при
наличии Pillow, надёжность ≤ 0.3: скриншот легко подделать.
"""

from __future__ import annotations

import importlib.util
import io
from typing import Any, Optional

from ..context import CheckContext
from ..schemas import InputType, Stage, Verdict
from .base import BaseSignal, make_result

RELIABILITY_MAX = 0.3
MAX_TEXT = 2000

# Подписи интерфейсов, по которым узнаётся скриншот соцсети.
_PLATFORM_HINTS: tuple[str, ...] = (
    "нравится", "поделиться", "подписаться", "подписчики", "репост", "ретвит",
    "лайк", "коммент", "сообщение", "истории", "сториз", "shorts",
    "follow", "share", "subscribe", "like", "repost", "reels", "tiktok",
    "telegram", "вконтакте", "instagram", "whatsapp", "youtube", "x.com",
)


def _present(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def ocr_available() -> bool:
    return _present("pytesseract") or _present("paddleocr")


def run_ocr(data: bytes) -> Optional[str]:
    """OCR через первую доступную библиотеку. None — если OCR недоступен."""
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        pytesseract = None  # type: ignore[assignment]
    if pytesseract is not None:
        try:
            with Image.open(io.BytesIO(data)) as image:
                text = pytesseract.image_to_string(image, lang="rus+eng")
            if text and text.strip():
                return text.strip()
        except Exception:
            pass
    try:
        from paddleocr import PaddleOCR
    except ImportError:
        return None
    try:
        engine = PaddleOCR(use_angle_cls=True, lang="ru", show_log=False)
        result = engine.ocr(data)
    except Exception:
        return None
    lines: list[str] = []
    for block in result or []:
        for row in block or []:
            try:
                lines.append(str(row[1][0]))
            except (IndexError, TypeError):
                continue
    text = "\n".join(lines).strip()
    return text or None


def visual_anomalies(data: bytes) -> Optional[dict[str, Any]]:
    """Простые нестыковки вёрстки: однотонные строки, как в интерфейсе.

    Требует Pillow; без него проверка не выполняется (None).
    """
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        with Image.open(io.BytesIO(data)) as image:
            gray = image.convert("L").resize((64, 128))
            pixels = list(gray.getdata())
    except Exception:
        return None
    if len(pixels) != 64 * 128:
        return None
    flat_rows = 0
    for y in range(128):
        row = pixels[y * 64:(y + 1) * 64]
        if max(row) - min(row) <= 2:
            flat_rows += 1
    ratio = flat_rows / 128
    return {"flat_row_ratio": round(ratio, 3), "looks_like_ui": ratio > 0.15}


def _platform_hints(text: str) -> list[str]:
    low = text.lower()
    hits = [hint for hint in _PLATFORM_HINTS if hint in low]
    return sorted(set(hits))[:10]


class ScreenshotSignal(BaseSignal):
    """I6: скриншот соцсети — контекстный, слабый по определению."""

    id = "screenshot"
    name = "Скриншот соцсети"
    stage = Stage.context
    timeout_s = 20.0

    async def run(self, ctx: CheckContext):
        if ctx.input.type != InputType.image:
            return self.unavailable("сигнал работает только с изображениями")

        text = (ctx.text or "").strip()
        source = "ctx.text"
        if not text and ctx.data:
            ocred = run_ocr(ctx.data)
            if ocred:
                text = ocred
                source = "ocr"
        if not text:
            if not ctx.data:
                return self.unavailable("нет ни изображения, ни текста для разбора")
            reason = "текст не распознан: OCR недоступен"
            if not ocr_available():
                reason += " (нужны pytesseract или PaddleOCR)"
            else:
                reason += " (OCR не нашёл текста на картинке)"
            return self.unavailable(reason)

        details: dict[str, Any] = {
            "extracted_text": text[:MAX_TEXT],
            "text_source": source,
            "text_length": len(text),
        }
        hints = _platform_hints(text)
        if hints:
            details["platform_hints"] = hints

        strength = 0.1
        reliability = 0.2
        notes: list[str] = []

        anomalies = visual_anomalies(ctx.data) if ctx.data else None
        if anomalies:
            details["visual"] = anomalies
            if anomalies.get("looks_like_ui"):
                strength = 0.2
                reliability = RELIABILITY_MAX
                notes.append("разметка похожа на интерфейс соцсети")

        if hints:
            strength = max(strength, 0.2)
            reliability = max(reliability, 0.25)
            notes.append("в тексте есть подписи интерфейса")

        if notes:
            summary = (
                "Материал выглядит как скриншот соцсети: " + ", ".join(notes) + ". "
                "Скриншот не подтверждает содержание поста — его легко собрать в редакторе."
            )
        else:
            summary = (
                "Текст с картинки разобран, признаков интерфейса соцсети не нашлось. "
                "Контекст публикации сам по себе ничего не доказывает."
            )
        return make_result(self, Verdict.neutral, strength, reliability, summary, details)
