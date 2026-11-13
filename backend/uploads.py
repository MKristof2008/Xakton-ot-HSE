"""Валидация загружаемых файлов: MIME, размер, реальный формат, превью.

Пользовательскому имени файла не доверяем: оно только записывается в
метаданные Offer, а на диск всё кладётся под сгенерированный id. Содержимое
файлов нигде не логируется.
"""

from __future__ import annotations

import hashlib
import io
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

_BACKEND_DIR = Path(__file__).resolve().parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from PIL import Image, UnidentifiedImageError  # noqa: E402

from paths import ALLOWED_MIME, MAX_UPLOAD_BYTES, PREVIEW_MAX_SIDE  # noqa: E402


class UploadError(Exception):
    """Ошибка загрузки с кодом контракта и HTTP-статусом."""

    def __init__(self, code: str, message: str, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


@dataclass(frozen=True)
class PreparedImage:
    """Проверенное изображение: оригинал, превью и метаданные файла."""

    data: bytes
    original_ext: str
    preview_jpeg: bytes
    mime: str
    sha256: str
    width: int
    height: int
    safe_name: str


def sanitize_filename(name: Optional[str], fallback: str = "upload") -> str:
    """Безопасное имя для метаданных: только basename и разрешённые символы."""
    base = (name or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
    cleaned = "".join(ch for ch in base if ch.isalnum() or ch in "._- ()")
    cleaned = cleaned.lstrip(".")[:120]
    return cleaned or fallback


def _detect_format(image: Image.Image) -> Optional[str]:
    fmt = (image.format or "").upper()
    return fmt or None


def prepare_upload(raw: bytes, declared_mime: Optional[str], filename: Optional[str]) -> PreparedImage:
    """Проверить файл и собрать превью.

    Проверки по порядку: размер → заявленный MIME → реальный формат Pillow →
    декодирование пикселей (анти-бомба). Любая ошибка → UploadError.
    """
    if not raw:
        raise UploadError("BAD_INPUT", "файл пуст", 400)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise UploadError(
            "TOO_LARGE",
            f"файл больше {MAX_UPLOAD_BYTES // (1024 * 1024)} МБ",
            413,
        )

    mime = (declared_mime or "").split(";")[0].strip().lower()
    if mime not in ALLOWED_MIME:
        raise UploadError(
            "UNSUPPORTED_TYPE",
            "поддерживаются только JPEG, PNG и WebP",
            415,
        )

    try:
        with Image.open(io.BytesIO(raw)) as image:
            actual = _detect_format(image)
            if actual not in set(ALLOWED_MIME.values()):
                raise UploadError(
                    "UNSUPPORTED_TYPE",
                    "содержимое файла не является JPEG, PNG или WebP",
                    415,
                )
            if ALLOWED_MIME[mime] != actual:
                raise UploadError(
                    "UNSUPPORTED_TYPE",
                    f"заявлен {mime}, а внутри {actual}",
                    415,
                )

            width, height = image.size
            if width <= 0 or height <= 0 or width * height > 80_000_000:
                raise UploadError("BAD_INPUT", "недопустимый размер изображения", 400)

            # Декодируем пиксели: битые данные и «декомпрессионные бомбы» отсекаются тут.
            image.load()
            preview = image.copy()
            preview.thumbnail((PREVIEW_MAX_SIDE, PREVIEW_MAX_SIDE))
            if preview.mode not in ("RGB", "L"):
                preview = preview.convert("RGB")
            buffer = io.BytesIO()
            preview.save(buffer, format="JPEG", quality=85, optimize=True)
            preview_bytes = buffer.getvalue()
            original_ext = actual.lower().replace("jpeg", "jpg")
    except UploadError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise UploadError(
            "UNSUPPORTED_TYPE",
            f"не удалось прочитать изображение: {type(exc).__name__}",
            415,
        ) from exc

    return PreparedImage(
        data=raw,
        original_ext=original_ext,
        preview_jpeg=preview_bytes,
        mime=mime,
        sha256=hashlib.sha256(raw).hexdigest(),
        width=width,
        height=height,
        safe_name=sanitize_filename(filename),
    )