"""Сборка лота из результата проверки.

Цену считает ML-сигнал `pricing` по правилу контракта — у него есть все входы
(свежесть, уникальность, происхождение, спрос), и он же объясняет каждую цифру
в `why_price`. Backend не переписывает его вывод: берёт `price_rub`,
`why_price` и `listed` из `details`.

Если сигнал `pricing` недоступен или его результат не по контракту, backend
считает цену сам по тем же детерминированным правилам — иначе маркетплейс
развалится из-за сбоя одного сигнала. Никаких случайных чисел.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

BASE_RUB = 1500
ROUND_TO = 100

DEMAND_KEYWORDS: dict[str, tuple[float, str, tuple[str, ...]]] = {
    "incident": (1.8, "происшествие", (
        "пожар", "дым", "авари", "взрыв", "дтп", "катастроф", "обстрел",
        "наводнен", "чп", "происшеств", "рушен", "пострадав", "скорую",
    )),
    "urban": (1.2, "городское событие", (
        "город", "улиц", "парк", "метро", "площад", "район", "митинг",
        "стройк", "фестивал", "сквер", "набережн", "двор",
    )),
}

EXIF_DT_FORMATS = ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y:%m:%d %H:%M")


def parse_dt(value: Any) -> Optional[datetime]:
    """Разобрать ISO-дату (или EXIF-формат) в aware UTC. Мусор → None."""
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    candidate = text.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(candidate)
    except ValueError:
        dt = None
        for fmt in EXIF_DT_FORMATS:
            try:
                dt = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
        if dt is None:
            return None
    if dt.tzinfo is None:
        # EXIF без зоны: считаем UTC и не делаем вид, что знаем больше.
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _signal(check: dict[str, Any], signal_id: str) -> dict[str, Any]:
    for item in check.get("signals") or []:
        if item.get("id") == signal_id:
            return item
    return {}


def _details(check: dict[str, Any], signal_id: str) -> dict[str, Any]:
    details = _signal(check, signal_id).get("details")
    return details if isinstance(details, dict) else {}


# --------------------------------------------------------------------------
# Локальный расчёт — резерв, когда сигнал `pricing` недоступен
# --------------------------------------------------------------------------

def _freshness(shot_at: Optional[datetime], now: datetime) -> tuple[float, str]:
    if shot_at is None:
        return 1.0, "дата съёмки неизвестна — множитель 1.0"
    hours = max(0.0, (now - shot_at).total_seconds() / 3600.0)
    if hours < 1:
        return 3.0, "снято меньше часа назад"
    if hours < 6:
        return 2.0, f"снято {hours:.1f} ч назад"
    if hours < 24:
        return 1.5, f"снято {hours:.0f} ч назад"
    if hours < 72:
        return 1.0, f"снято {hours / 24:.1f} сут назад"
    return 0.5, f"снято {hours / 24:.0f} сут назад — материал несвежий"


def _local_multipliers(
    check: dict[str, Any], offer: dict[str, Any], now: datetime
) -> tuple[list[float], list[str], bool, dict[str, Any]]:
    """Множители, объяснения и признак дубликата для локального расчёта."""
    shot_at = parse_dt(offer.get("shot_at")) or parse_dt(_details(check, "metadata").get("datetime"))
    fresh, fresh_why = _freshness(shot_at, now)

    uniq_details = _details(check, "uniqueness")
    if "unique" in uniq_details or "duplicate" in uniq_details:
        duplicate = bool(uniq_details.get("duplicate"))
        unique = bool(uniq_details.get("unique")) and not duplicate
        similar = uniq_details.get("similar_in_archive") or 0
        if duplicate:
            uniq, uniq_why = 0.0, "дубликат уже есть в архиве — не выставляется"
        elif unique:
            uniq, uniq_why = 2.0, "совпадений в архиве нет"
        else:
            uniq, uniq_why = 1.0, f"похожих кадров в архиве: {similar}"
    else:
        duplicate, unique, similar = False, False, 0
        reason = _signal(check, "uniqueness").get("summary") or "сигнал недоступен"
        uniq, uniq_why = 1.0, f"уникальность не проверена ({reason[:120]}) — множитель 1.0"

    meta = _details(check, "metadata")
    gps = meta.get("gps") or {}
    has_geo = gps.get("latitude") is not None and gps.get("longitude") is not None
    if meta.get("camera") and meta.get("datetime"):
        prov, prov_why = 1.5, "камера и дата съёмки в метаданных на месте"
    elif meta.get("camera") or meta.get("datetime") or has_geo:
        prov, prov_why = 1.0, "метаданные частичные"
    elif _signal(check, "metadata").get("verdict") == "unavailable":
        prov, prov_why = 0.7, "метаданные недоступны — множитель 0.7"
    else:
        prov, prov_why = 0.7, "в файле нет метаданных источника — множитель 0.7"

    text = f"{offer.get('caption') or ''} {offer.get('location') or ''}".lower()
    demand, demand_why = 1.0, "категория события не распознана"
    for _key, (multiplier, label, words) in DEMAND_KEYWORDS.items():
        if any(word in text for word in words):
            demand, demand_why = multiplier, f"категория «{label}»"
            break

    multipliers = [fresh, uniq, prov, demand]
    explanations = [
        f"Свежесть ×{fresh:g}: {fresh_why}",
        f"Уникальность ×{uniq:g}: {uniq_why}",
        f"Происхождение ×{prov:g}: {prov_why}",
        f"Спрос ×{demand:g}: {demand_why}",
    ]
    facts = {"unique": unique, "similar_in_archive": similar}
    return multipliers, explanations, duplicate, facts


def _factual_origin(check: dict[str, Any]) -> str:
    """Человеческое описание происхождения по сигналу метаданных."""
    meta = _details(check, "metadata")
    camera = meta.get("camera")
    if camera:
        return f"снято на камеру {camera}"
    if (meta.get("c2pa") or {}).get("present"):
        return "файл подписан манифестом C2PA"
    if (meta.get("gps") or {}).get("latitude") is not None:
        return "в файле есть GPS-координаты"
    return "источник не установлен"


def _geo(check: dict[str, Any], location: str) -> str:
    place = (location or "").strip()
    gps = _details(check, "metadata").get("gps") or {}
    lat, lon = gps.get("latitude"), gps.get("longitude")
    if lat is None or lon is None:
        return place or "не указано"
    coords = f"{float(lat):.4f}, {float(lon):.4f}"
    return f"{place} ({coords})" if place else coords


def make_title(caption: str, location: str) -> str:
    text = " ".join((caption or "").split())[:80]
    place = " ".join((location or "").split())[:60]
    if text and place and place.lower() not in text.lower():
        text = f"{text}, {place}"
    elif not text:
        text = f"Материал с места: {place}" if place else "Материал без подписи"
    return f"{text} — фото с места"


# --------------------------------------------------------------------------
# Публичная сборка лота
# --------------------------------------------------------------------------

def build_listing(
    check: dict[str, Any],
    offer: dict[str, Any],
    now: Optional[datetime] = None,
) -> tuple[Optional[dict[str, Any]], str]:
    """Собрать параметры лота. Второй элемент — причина отказа (пусто, если лот есть)."""
    now = now or datetime.now(timezone.utc)
    caption = offer.get("caption") or ""
    location = offer.get("location") or ""

    pricing = _details(check, "pricing")
    shot_at = parse_dt(pricing.get("shot_at")) or parse_dt(offer.get("shot_at")) \
        or parse_dt(_details(check, "metadata").get("datetime"))

    local_facts: dict[str, Any] = {"unique": False, "similar_in_archive": 0}
    if isinstance(pricing.get("price_rub"), int) and isinstance(pricing.get("why_price"), list):
        price = int(pricing["price_rub"])
        why_price = [str(line) for line in pricing["why_price"]]
        listed = bool(pricing.get("listed", price > 0))
        uniq = pricing.get("uniqueness") or {}
        local_facts = {
            "unique": bool(uniq.get("unique")),
            "similar_in_archive": int(uniq.get("similar") or 0),
        }
        if not shot_at:
            shot_at = parse_dt(pricing.get("shot_at"))
    else:
        multipliers, explanations, duplicate, local_facts = _local_multipliers(check, offer, now)
        listed = not duplicate
        raw = BASE_RUB
        for multiplier in multipliers:
            raw *= multiplier
        price = 0 if duplicate else max(ROUND_TO, int(round(raw / ROUND_TO)) * ROUND_TO)
        why_price = [f"База: {BASE_RUB} ₽"] + explanations
        if listed:
            why_price.append(f"Итого: {price} ₽")

    if not listed:
        reason = why_price[-1] if why_price else "материал не выставляется"
        return None, reason

    trust = check.get("trust") or {
        "score": 0, "uncertainty": 1.0, "coverage": 0.0, "level": "fog", "conflict": False,
    }

    return {
        "title": make_title(caption, location),
        "price_rub": price,
        "trust": trust,
        "facts": {
            "origin": _factual_origin(check),
            "shot_at": iso(shot_at),
            "geo": _geo(check, location),
            "unique": bool(local_facts.get("unique")),
            "similar_in_archive": int(local_facts.get("similar_in_archive") or 0),
        },
        "why_price": why_price,
    }, ""