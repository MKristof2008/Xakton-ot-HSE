"""Сигнал I7 «Оригинальность»: перцептивный хеш и локальный архив (6.3 ТЗ).

Хеши считаются на Pillow (dHash 8x8 — сравнение соседних пикселей, aHash 8x8
— сравнение со средним). Без Pillow сигнал возвращает unavailable.

Архив — каталог с JSON-манифестом (manifest.json; допускаются известные
имена вроде known_cases.json). Путь задаётся через
``ctx.options["archive_dir"]``, по умолчанию ``ml/data/archive``. Если
каталога или манифеста нет — unavailable с честной причиной, а не падение.

Совпадение по расстоянию Хэмминга:
  * ≤ DUPLICATE_DISTANCE — дубликат: supports_fake;
  * ≤ SIMILAR_DISTANCE — похожий кадр: neutral;
  * иначе — уникально: supports_real (средняя сила, отсутствие в локальном
    архиве — слабый довод, это честно написано в summary).
"""

from __future__ import annotations

import io
import json
import pathlib
from typing import Any, Optional

from ..context import CheckContext
from ..schemas import InputType, Stage, Verdict
from .base import BaseSignal, make_result
from .source_search import hamming_hex

DUPLICATE_DISTANCE = 4   # полное совпадение (из 64 бит)
SIMILAR_DISTANCE = 12    # похожий кадр, но не дубликат
MAX_PIXELS = 40_000_000  # защита от гигантских картинок

DEFAULT_ARCHIVE_DIR = pathlib.Path(__file__).resolve().parents[2] / "data" / "archive"
MANIFEST_NAMES = ("manifest.json", "archive.json", "known_cases.json")

RELIABILITY_DUPLICATE = 0.75
RELIABILITY_PARTIAL = 0.5
RELIABILITY_UNIQUE = 0.5


class PillowMissing(RuntimeError):
    """Pillow не установлен — хеши не посчитать."""


class ImageUndecodable(ValueError):
    """Файл не читается как изображение."""


def _pil():
    try:
        from PIL import Image
    except ImportError:
        return None
    return Image


def _resample(image_module):
    """LANCZOS в новых Pillow, константа 1 — в старых."""
    resampling = getattr(image_module, "Resampling", None)
    if resampling is not None:
        return resampling.LANCZOS
    return 1


def image_hashes(data: bytes) -> dict[str, str]:
    """dHash 8x8 и aHash 8x8 по серой картинке.

    Бросает PillowMissing, если Pillow нет, и ImageUndecodable, если файл
    битый или слишком большой.
    """
    image_module = _pil()
    if image_module is None:
        raise PillowMissing("нужен Pillow: без него не посчитать перцептивный хеш")
    try:
        with image_module.open(io.BytesIO(data)) as image:
            width, height = image.size
            if width <= 0 or height <= 0 or width * height > MAX_PIXELS:
                raise ImageUndecodable("недопустимый размер изображения")
            gray = image.convert("L")
            # tobytes() для L-режима — ровно по байту на пиксель.
            d_pixels = gray.resize((9, 8), _resample(image_module)).tobytes()
            a_pixels = gray.resize((8, 8), _resample(image_module)).tobytes()
    except ImageUndecodable:
        raise
    except Exception as exc:  # битый файл, неподдерживаемый формат
        raise ImageUndecodable(f"{type(exc).__name__}: {exc}"[:200]) from exc

    if len(d_pixels) != 9 * 8 or len(a_pixels) != 8 * 8:
        raise ImageUndecodable("Pillow вернул неполный растр")

    d_bits = 0
    for y in range(8):
        for x in range(8):
            left = d_pixels[y * 9 + x]
            right = d_pixels[y * 9 + x + 1]
            d_bits = (d_bits << 1) | (1 if left > right else 0)

    mean = sum(a_pixels) / len(a_pixels)
    a_bits = 0
    for value in a_pixels:
        a_bits = (a_bits << 1) | (1 if value > mean else 0)
    return {"dhash": f"{d_bits:016x}", "ahash": f"{a_bits:016x}"}


def _valid_hash(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    text = value.strip().lower()
    if not text or len(text) % 2 or len(text) > 64:
        return None
    try:
        int(text, 16)
    except ValueError:
        return None
    return text


def _archive_path(archive_dir: Any) -> pathlib.Path:
    if archive_dir:
        return pathlib.Path(str(archive_dir))
    return DEFAULT_ARCHIVE_DIR


def load_archive(archive_dir: Any = None) -> tuple[list[dict[str, Any]], Optional[str]]:
    """Читает манифест архива → (записи, причина недоступности).

    Запись: id, dhash, ahash, url, date. Если хешей в манифесте нет, но есть
    файл, хеши считаются по файлу. Записи без хешей пропускаются.
    """
    base = _archive_path(archive_dir)
    if not base.is_dir():
        return [], f"архив не найден: {base}"
    manifest = next((base / name for name in MANIFEST_NAMES if (base / name).is_file()), None)
    if manifest is None:
        return [], f"в архиве нет манифеста ({', '.join(MANIFEST_NAMES)}): {base}"
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [], f"манифест архива не читается: {manifest} ({type(exc).__name__})"

    if isinstance(payload, dict):
        # Пустой список — валидный архив («пока ничего нет»), поэтому ищем
        # ключ по наличию, а не по истинности значения.
        raw_items = next(
            (payload[key] for key in ("items", "cases", "archive") if key in payload),
            None,
        )
    else:
        raw_items = payload
    if not isinstance(raw_items, list):
        return [], f"в манифесте нет списка записей: {manifest}"

    entries: list[dict[str, Any]] = []
    for index, item in enumerate(raw_items):
        if not isinstance(item, dict):
            continue
        dhash = _valid_hash(item.get("dhash")) or _valid_hash(item.get("phash"))
        ahash = _valid_hash(item.get("ahash"))
        file_name = item.get("file") or item.get("path")
        if (not dhash and not ahash) and file_name:
            try:
                hashes = image_hashes((base / str(file_name)).read_bytes())
            except (OSError, PillowMissing, ImageUndecodable):
                continue
            dhash, ahash = hashes["dhash"], hashes["ahash"]
        if not dhash and not ahash:
            continue
        entries.append({
            "id": str(item.get("id") or f"item-{index + 1}"),
            "dhash": dhash,
            "ahash": ahash,
            "url": str(item.get("url") or ""),
            "date": str(item.get("date") or ""),
        })
    return entries, None


def _entry_distance(query: dict[str, str], entry: dict[str, Any]) -> Optional[int]:
    """Минимум по доступным хешам; None — сравнивать нечего."""
    distances = [
        hamming_hex(query[kind], entry[kind])
        for kind in ("dhash", "ahash")
        if query.get(kind) and entry.get(kind)
    ]
    return min(distances) if distances else None


def match_archive(
    hashes: dict[str, str], entries: list[dict[str, Any]]
) -> dict[str, Any]:
    """Лучшее совпадение и число похожих кадров в архиве."""
    best: Optional[dict[str, Any]] = None
    similar = 0
    for entry in entries:
        distance = _entry_distance(hashes, entry)
        if distance is None:
            continue
        if distance <= SIMILAR_DISTANCE:
            similar += 1
        if best is None or distance < best["hamming"]:
            best = {
                "id": entry["id"],
                "hamming": distance,
                "url": entry["url"],
                "date": entry["date"],
            }
    if best is not None and best["hamming"] > SIMILAR_DISTANCE:
        best = None
    return {"best": best, "similar": similar, "duplicate": bool(best and best["hamming"] <= DUPLICATE_DISTANCE)}


class UniquenessSignal(BaseSignal):
    """I7: есть ли этот кадр в локальном архиве."""

    id = "uniqueness"
    name = "Оригинальность"
    stage = Stage.sources
    timeout_s = 15.0

    async def run(self, ctx: CheckContext):
        if ctx.input.type != InputType.image:
            return self.unavailable("сигнал работает только с изображениями")
        data = ctx.data
        if not data:
            return self.unavailable("нет байтов изображения на входе")
        try:
            hashes = image_hashes(data)
        except PillowMissing as exc:
            return self.unavailable(str(exc))
        except ImageUndecodable as exc:
            return self.unavailable(f"не удалось прочитать изображение: {exc}")
        ctx.remember("image_hashes", hashes)

        entries, reason = load_archive(ctx.options.get("archive_dir"))
        if reason:
            return self.unavailable(reason)

        match = match_archive(hashes, entries)
        best = match["best"]
        similar = match["similar"]
        duplicate = match["duplicate"]
        details: dict[str, Any] = {
            "unique": similar == 0,
            "duplicate": duplicate,
            "similar_in_archive": similar,
            "best_match": best,
            "phash": hashes["dhash"],
            "dhash": hashes["dhash"],
            "ahash": hashes["ahash"],
            "hash_algorithm": "dhash8x8+ahash8x8 (Pillow)",
            "archive_size": len(entries),
            "duplicate_distance": DUPLICATE_DISTANCE,
            "similar_distance": SIMILAR_DISTANCE,
        }

        if duplicate and best is not None:
            date_note = f", дата {best['date']}" if best["date"] else ""
            summary = (
                f"Дубликат уже есть в архиве (id {best['id']}{date_note}). "
                "Этот кадр не уникален: похоже, его выдают за новый."
            )
            return make_result(
                self, Verdict.supports_fake, 0.85, RELIABILITY_DUPLICATE, summary, details
            )

        if best is not None:
            date_note = f", дата {best['date']}" if best["date"] else ""
            summary = (
                f"В архиве есть похожие кадры ({similar}, лучший id {best['id']}{date_note}), "
                "но точного дубликата нет. Уникальность под вопросом."
            )
            return make_result(
                self, Verdict.neutral, 0.3, RELIABILITY_PARTIAL, summary, details
            )

        # Пустой архив — не доказательство уникальности: сравнивать не с чем.
        # Иначе «не нашли в пустой базе» становится ложным доводом «оригинал»
        # и глушит настоящий сигнал (например, детектор ИИ).
        if not entries:
            return make_result(
                self, Verdict.neutral, 0.0, RELIABILITY_UNIQUE,
                "Архив пуст: сравнивать не с чем, довода об оригинальности нет.",
                details,
            )

        summary = (
            f"Совпадений в локальном архиве нет (проверено записей: {len(entries)}). "
            "Это довод в пользу оригинальности, но архив неполный: отсутствие дубликата не доказывает новизну."
        )
        return make_result(
            self, Verdict.supports_real, 0.45, RELIABILITY_UNIQUE, summary, details
        )