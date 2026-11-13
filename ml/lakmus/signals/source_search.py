"""Сигнал I4 «Поиск первоисточника»: перцептивный хеш и ранние упоминания (6.3 ТЗ).

Только stdlib: собственный PNG-декодер (zlib + фильтры строк) → градации
серого → dHash 8x8 и pHash (DCT 32x32). JPEG без Pillow распознать нельзя,
поэтому хеш для него не считается и это честно попадает в unavailable.

Локальная база известных кейсов — ml/lakmus/data/known_cases.json
(phash/dhash, дата, место, пояснение). Внешний обратный поиск выполняется
только через ctx.search, если backend его дал: запрос — URL превью в
кавычках, а при его отсутствии строка "phash:<хеш>" (такой запрос имеет
смысл лишь для внешних баз, которые индексируют перцептивные хеши).
"""

from __future__ import annotations

import io
import json
import math
import pathlib
import struct
import zlib
from datetime import date
from typing import Any, Optional, Sequence

from ..context import CheckContext
from ..schemas import InputType, Stage, Verdict
from .base import BaseSignal, make_result

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
MAX_DISTANCE = 10           # порог Хэмминга для совпадения (из 64 бит)
MAX_PIXELS = 40_000_000     # защита от гигантских картинок
MAX_HASH_PIXELS = 40_000_000  # то же для Pillow-пути (JPEG/WebP)
DATA_DIR = pathlib.Path(__file__).resolve().parent.parent / "data"
KNOWN_CASES_PATH = DATA_DIR / "known_cases.json"

_CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}


class PngError(ValueError):
    """PNG не поддерживается или повреждён."""


# --------------------------------------------------------------------------
# декодер PNG
# --------------------------------------------------------------------------


def _iter_chunks(data: bytes):
    pos = len(PNG_SIGNATURE)
    total = len(data)
    while pos + 8 <= total:
        length = int.from_bytes(data[pos:pos + 4], "big")
        ctype = data[pos + 4:pos + 8]
        start = pos + 8
        end = start + length
        if length < 0 or end > total:
            break
        yield ctype, data[start:end]
        pos = end + 4
        if ctype == b"IEND":
            break


def _unfilter(raw: bytes, width: int, height: int, bpp: int) -> bytes:
    stride = width * bpp
    expected = (stride + 1) * height
    if len(raw) < expected:
        raise PngError("данные изображения обрезаны")
    prev = bytearray(stride)
    out = bytearray(stride * height)
    pos = 0
    for y in range(height):
        ftype = raw[pos]
        pos += 1
        line = bytearray(raw[pos:pos + stride])
        pos += stride
        if ftype == 0:
            pass
        elif ftype == 1:
            for i in range(bpp, stride):
                line[i] = (line[i] + line[i - bpp]) & 0xFF
        elif ftype == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif ftype == 3:
            for i in range(stride):
                left = line[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + ((left + prev[i]) >> 1)) & 0xFF
        elif ftype == 4:
            for i in range(stride):
                a = line[i - bpp] if i >= bpp else 0
                b = prev[i]
                c = prev[i - bpp] if i >= bpp else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                if pa <= pb and pa <= pc:
                    pred = a
                elif pb <= pc:
                    pred = b
                else:
                    pred = c
                line[i] = (line[i] + pred) & 0xFF
        else:
            raise PngError(f"неизвестный фильтр строки {ftype}")
        out[y * stride:(y + 1) * stride] = line
        prev = line
    return bytes(out)


def decode_png_gray(data: bytes) -> tuple[int, int, bytes]:
    """PNG (8/16 бит, без интерлейса) → (ширина, высота, серые байты)."""
    if not data.startswith(PNG_SIGNATURE):
        raise PngError("это не PNG")
    header = None
    palette = None
    idat = bytearray()
    for ctype, payload in _iter_chunks(data):
        if ctype == b"IHDR":
            header = payload
        elif ctype == b"PLTE":
            palette = payload
        elif ctype == b"IDAT":
            idat += payload
        elif ctype == b"IEND":
            break
    if header is None or len(header) < 13:
        raise PngError("нет заголовка IHDR")
    width, height, depth, color, _comp, _filt, interlace = struct.unpack(">IIBBBBB", header[:13])
    if interlace != 0:
        raise PngError("чересстрочный PNG не поддерживается")
    if depth not in (8, 16):
        raise PngError(f"глубина {depth} бит не поддерживается")
    channels = _CHANNELS.get(color)
    if channels is None:
        raise PngError(f"тип цвета {color} не поддерживается")
    if width <= 0 or height <= 0 or width * height > MAX_PIXELS:
        raise PngError("недопустимый размер изображения")
    if not idat:
        raise PngError("нет данных изображения")
    try:
        raw = zlib.decompress(bytes(idat))
    except zlib.error as exc:
        raise PngError(f"данные изображения не распаковались: {exc}") from exc
    sample = depth // 8
    bpp = channels * sample
    pixels = _unfilter(raw, width, height, bpp)
    stride = width * bpp
    gray = bytearray(width * height)
    index = 0
    for y in range(height):
        base = y * stride
        for x in range(width):
            offset = base + x * bpp
            if color == 3:
                entry = pixels[offset]
                if palette is not None and entry * 3 + 2 < len(palette):
                    r, g, b = palette[entry * 3], palette[entry * 3 + 1], palette[entry * 3 + 2]
                else:
                    r = g = b = entry
            elif color in (0, 4):
                r = g = b = pixels[offset]  # 16 бит: берём старший байт
            else:
                step = 2 if sample == 2 else 1
                r = pixels[offset]
                g = pixels[offset + step]
                b = pixels[offset + 2 * step]
            gray[index] = (299 * r + 587 * g + 114 * b) // 1000
            index += 1
    return width, height, bytes(gray)


def resize_gray(gray: bytes, width: int, height: int, tw: int, th: int) -> bytes:
    """Усреднение по площади: устойчивый к масштабу даунсемплинг."""
    if width <= 0 or height <= 0 or tw <= 0 or th <= 0:
        raise PngError("пустое изображение")
    out = bytearray(tw * th)
    for ty in range(th):
        y0 = ty * height // th
        y1 = max(y0 + 1, (ty + 1) * height // th)
        for tx in range(tw):
            x0 = tx * width // tw
            x1 = max(x0 + 1, (tx + 1) * width // tw)
            total = 0
            count = 0
            for y in range(y0, min(y1, height)):
                row = y * width
                for x in range(x0, min(x1, width)):
                    total += gray[row + x]
                    count += 1
            out[ty * tw + tx] = total // count if count else 0
    return bytes(out)


# --------------------------------------------------------------------------
# хеши
# --------------------------------------------------------------------------


def _decode_with_pillow_gray(data: bytes) -> Optional[tuple[int, int, bytes]]:
    """JPEG/WebP и прочее через Pillow → (ширина, высота, серые байты).

    Возвращает None, если Pillow нет или файл не декодируется: сигнал тогда
    честно сообщает, что хеш не посчитан, а не падает.
    """
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        with Image.open(io.BytesIO(data)) as image:
            width, height = image.size
            if width <= 0 or height <= 0 or width * height > MAX_HASH_PIXELS:
                return None
            return width, height, image.convert("L").tobytes()
    except Exception:
        return None


def dhash_hex(gray: bytes, width: int, height: int) -> str:
    """dHash 8x8 (сравнение соседних пикселей) → 16 hex-символов."""
    small = resize_gray(gray, width, height, 9, 8)
    bits = 0
    for y in range(8):
        for x in range(8):
            left = small[y * 9 + x]
            right = small[y * 9 + x + 1]
            bits = (bits << 1) | (1 if left > right else 0)
    return f"{bits:016x}"


_COS = [[math.cos((2 * x + 1) * u * math.pi / 64.0) for x in range(32)] for u in range(32)]


def _dct2(grid: bytes) -> list[float]:
    """2D DCT-II 32x32 (сепарабельно): строки, затем столбцы."""
    rows: list[list[float]] = []
    for y in range(32):
        row = [float(grid[y * 32 + x]) for x in range(32)]
        rows.append([
            sum(row[x] * _COS[u][x] for x in range(32)) for u in range(32)
        ])
    out = [0.0] * (32 * 32)
    for u in range(32):
        column = [rows[y][u] for y in range(32)]
        for v in range(32):
            out[v * 32 + u] = sum(column[y] * _COS[v][y] for y in range(32))
    return out


def phash_hex(gray: bytes, width: int, height: int) -> str:
    """pHash 8x8 по низким частотам DCT → 16 hex-символов."""
    small = resize_gray(gray, width, height, 32, 32)
    coeffs = _dct2(small)
    top = [coeffs[v * 32 + u] for v in range(8) for u in range(8)]
    rest = top[1:]  # DC-коэффициент не участвует в медиане
    median = sorted(rest)[len(rest) // 2]
    bits = 0
    for value in top:
        bits = (bits << 1) | (1 if value > median else 0)
    return f"{bits:016x}"


def hamming_hex(left: str, right: str) -> int:
    """Расстояние Хэмминга для hex-хешей одинаковой длины (иначе — большое)."""
    if not left or not right or len(left) != len(right):
        return 64
    try:
        return bin(int(left, 16) ^ int(right, 16)).count("1")
    except ValueError:
        return 64


# --------------------------------------------------------------------------
# локальная база известных кейсов
# --------------------------------------------------------------------------


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


def load_known_cases(path: str | pathlib.Path | None = None) -> list[dict[str, Any]]:
    """Читает ml/lakmus/data/known_cases.json. Битый файл — пустая база."""
    target = pathlib.Path(path) if path else KNOWN_CASES_PATH
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    raw_cases = payload.get("cases") if isinstance(payload, dict) else payload
    if not isinstance(raw_cases, list):
        return []
    cases: list[dict[str, Any]] = []
    for item in raw_cases:
        if not isinstance(item, dict):
            continue
        phash = _valid_hash(item.get("phash"))
        dhash = _valid_hash(item.get("dhash"))
        if not phash and not dhash:
            continue
        cases.append({
            "id": str(item.get("id") or f"case-{len(cases) + 1}"),
            "phash": phash,
            "dhash": dhash,
            "date": str(item.get("date") or ""),
            "where": str(item.get("where") or ""),
            "note": str(item.get("note") or ""),
        })
    return cases


def _parse_date(value: Any) -> Optional[date]:
    if not value:
        return None
    text = str(value).strip()
    for candidate in (text[:10], text):
        try:
            return date.fromisoformat(candidate)
        except ValueError:
            continue
    return None


def match_known_cases(
    phash: str, dhash: str, cases: Sequence[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Совпадения по локальной базе: расстояние Хэмминга ≤ MAX_DISTANCE."""
    matches: list[dict[str, Any]] = []
    for case in cases:
        best: Optional[dict[str, Any]] = None
        for kind, mine in (("phash", phash), ("dhash", dhash)):
            reference = case.get(kind)
            if not reference or not mine:
                continue
            distance = hamming_hex(mine, reference)
            if distance <= MAX_DISTANCE and (best is None or distance < best["distance"]):
                best = {"case": case, "distance": distance, "hash": kind}
        if best is not None:
            matches.append(best)
    matches.sort(key=lambda item: item["distance"])
    return matches


# --------------------------------------------------------------------------
# сигнал
# --------------------------------------------------------------------------


def _search_query(ctx: CheckContext, phash: str) -> str:
    """Запрос для обратного поиска.

    Backend отдаёт только текстовый поиск, поэтому:
      1) если есть URL превью — ищем точную ссылку (находит страницы,
         где картинка уже опубликована);
      2) иначе — "phash:<хеш>" для внешних баз, индексирующих хеши.
    """
    url = (ctx.input.preview_url or "").strip()
    if url:
        return f'"{url}"'
    return f"phash:{phash}" if phash else ""


async def _search_hits(ctx: CheckContext, query: str) -> list[Any]:
    provider = ctx.search
    if provider is None or not query:
        return []
    try:
        hits = await provider.search(query)
    except Exception:
        return []
    try:
        return list(hits)[:20]
    except TypeError:
        return []


class SourceSearchSignal(BaseSignal):
    """I4: перцептивный хеш, локальная база и внешние упоминания."""

    id = "source_search"
    name = "Поиск первоисточника"
    stage = Stage.sources
    timeout_s = 15.0

    async def run(self, ctx: CheckContext):
        if ctx.input.type != InputType.image:
            return self.unavailable("сигнал работает только с изображениями")
        data = ctx.data
        if not data:
            return self.unavailable("нет байтов изображения на входе")

        phash = ""
        dhash = ""
        hash_error = None
        try:
            width, height, gray = decode_png_gray(data)
            phash = phash_hex(gray, width, height)
            dhash = dhash_hex(gray, width, height)
        except PngError as exc:
            # PNG-декодер на stdlib не берёт JPEG/WebP. Pillow в проекте есть,
            # поэтому пробуем его, а не сдаёмся сразу.
            fallback = _decode_with_pillow_gray(data)
            if fallback is None:
                hash_error = f"не удалось посчитать хеш: {exc}"
            else:
                width, height, gray = fallback
                phash = phash_hex(gray, width, height)
                dhash = dhash_hex(gray, width, height)
        except (MemoryError, ValueError) as exc:
            hash_error = f"не удалось посчитать хеш: {type(exc).__name__}"

        details: dict[str, Any] = {
            "phash": phash or None,
            "dhash": dhash or None,
            "hash_algorithm": "dhash8x8+phash32x32 (stdlib)",
            "max_distance": MAX_DISTANCE,
            "hash_error": hash_error,
        }
        claimed = _parse_date(ctx.options.get("claimed_date"))
        details["claimed_date"] = claimed.isoformat() if claimed else None

        cases = load_known_cases(ctx.options.get("known_cases_path"))
        matches = match_known_cases(phash, dhash, cases) if (phash or dhash) else []
        details["known_cases_checked"] = len(cases)
        details["matches"] = [
            {
                "id": item["case"]["id"],
                "distance": item["distance"],
                "hash": item["hash"],
                "date": item["case"]["date"],
                "where": item["case"]["where"],
                "note": item["case"]["note"],
            }
            for item in matches[:5]
        ]

        query = _search_query(ctx, phash)
        hits = await _search_hits(ctx, query)
        details["search_query"] = query or None
        details["external_hits"] = [
            {
                "title": str(getattr(hit, "title", ""))[:200],
                "url": str(getattr(hit, "url", "")),
                "published_at": getattr(hit, "published_at", None),
                "domain": str(getattr(hit, "domain", "")),
            }
            for hit in hits[:10]
        ]

        provenance: list[dict[str, Any]] = []
        earlier: list[dict[str, Any]] = []

        if matches:
            best = matches[0]["case"]
            found = _parse_date(best["date"])
            provenance.append({
                "date": found.isoformat() if found else None,
                "where": best["where"] or "локальная база известных кейсов",
                "note": best["note"] or f"похожий кадр уже встречался (id {best['id']})",
            })
            if claimed and found and (claimed - found).days >= 1:
                earlier.append({
                    "where": best["where"] or "локальная база известных кейсов",
                    "date": found.isoformat(),
                    "days_before": (claimed - found).days,
                    "source": "local_db",
                })

        for hit in hits:
            published = _parse_date(getattr(hit, "published_at", None))
            provenance.append({
                "date": published.isoformat() if published else None,
                "where": str(getattr(hit, "url", ""))[:300],
                "note": str(getattr(hit, "title", ""))[:200],
            })
            if claimed and published and (claimed - published).days >= 1:
                earlier.append({
                    "where": str(getattr(hit, "url", ""))[:300],
                    "date": published.isoformat(),
                    "days_before": (claimed - published).days,
                    "source": "search",
                })

        details["provenance"] = provenance[:5]
        details["earlier_than_claimed"] = earlier

        if earlier:
            days = max(item["days_before"] for item in earlier)
            reliability = 0.85 if earlier[0]["source"] == "local_db" else 0.8
            details["days_before_claimed"] = days
            summary = (
                f"Похожий кадр уже публиковался примерно на {days} дн. раньше заявленной даты. "
                "Скорее всего материал выдают за новый или вырван из старого контекста."
            )
            return make_result(self, Verdict.supports_fake, 0.85, reliability, summary, details)

        if matches or provenance:
            summary = (
                "Найдены более ранние упоминания того же кадра, но заявленная дата не известна "
                "или не расходится с ними. Пока это только контекст."
            )
            return make_result(self, Verdict.neutral, 0.3, 0.4, summary, details)

        if not phash and not dhash and not hits:
            return self.unavailable(hash_error or "не удалось извлечь признаки изображения")

        summary = (
            "Совпадений в локальной базе и внешних упоминаний не найдено. "
            "Отсутствие первоисточника само по себе ничего не доказывает."
        )
        return make_result(self, Verdict.neutral, 0.0, 0.3, summary, details)
