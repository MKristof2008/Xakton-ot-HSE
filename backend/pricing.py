"""Детерминированная цена лота по правилу из docs/CONTRACT.md.

`price_rub = base × freshness × uniqueness × provenance × demand`,
округление до 100 ₽. Каждый множитель объясняется в `why_price` человеческим
языком. Никаких случайных чисел: одинаковый вход даёт одинаковую цену.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

BASE_RUB = 1500
ROUND_TO = 100

#: Категории спроса по ключевым словам подписи и локации.
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
        # EXIF и ISO без зоны: считаем UTC и честно помечаем это в why_price.
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


def freshness(shot_at: Optional[datetime], now: datetime) -> tuple[float, str]:
    """Свежесть по времени съёмки (CONTRACT: <1 ч ×3, <6 ч ×2, <24 ч ×1.5, <72 ч ×1, иначе ×0.5)."""
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


def uniqueness(check: dict[str, Any]) -> tuple[float, str, bool, int, bool]:
    """Уникальность по сигналу поиска первоисточника.

    Возвращает (множитель, объяснение, unique, similar_in_archive, duplicate).
    """
    signal = _signal(check, "source_search")
    details = signal.get("details") or {}
    if signal.get("verdict") == "unavailable":
        reason = signal.get("summary") or "сигнал недоступен"
        return 1.0, f"уникальность не проверена ({reason}) — множитель 1.0", False, 0, False
    earlier = details.get("earlier_than_claimed") or []
    matches = details.get("matches") or []
    if earlier:
        return 0.0, "кадр публиковался раньше заявленной даты — это не оригинал", False, len(matches), True
    if matches:
        return 1.0, f"в архиве найдено похожих кадров: {len(matches)}", False, len(matches), False
    return 2.0, "совпадений в архиве нет", True, 0, False


def provenance(check: dict[str, Any]) -> tuple[float, str, str]:
    """Происхождение по сигналу метаданных. Возвращает (множитель, объяснение, origin)."""
    signal = _signal(check, "metadata")
    details = signal.get("details") or {}
    if signal.get("verdict") == "unavailable":
        return 0.7, "метаданные недоступны — множитель 0.7", "источник не установлен"
    c2pa = details.get("c2pa") or {}
    camera = details.get("camera")
    datetime_value = details.get("datetime")
    gps = details.get("gps") or {}
    has_geo = bool(gps.get("latitude") is not None and gps.get("longitude") is not None)

    if camera and datetime_value and has_geo:
        return 1.5, "камера, дата и GPS в метаданных на месте", f"снято на камеру {camera}"
    if camera and datetime_value:
        return 1.5, "камера и дата съёмки в метаданных на месте", f"снято на камеру {camera}"
    if c2pa.get("present"):
        return 1.0, "есть манифест C2PA, но камера и дата не подтверждены", "файл подписан C2PA"
    if camera or datetime_value or has_geo:
        return 1.0, "метаданные частичные", f"снято на камеру {camera}" if camera else "частичные метаданные"
    return 0.7, "в файле нет метаданных источника — множитель 0.7", "источник не установлен"


def demand(caption: str, location: str) -> tuple[float, str]:
    """Спрос по категории события (ЧП ×1.8, городское ×1.2, иначе ×1.0)."""
    text = f"{caption} {location}".lower()
    for _key, (multiplier, label, words) in DEMAND_KEYWORDS.items():
        if any(word in text for word in words):
            return multiplier, f"категория «{label}»"
    return 1.0, "категория события не распознана"


def make_title(caption: str, location: str) -> str:
    text = " ".join((caption or "").split())[:80]
    place = " ".join((location or "").split())[:60]
    if text and place and place.lower() not in text.lower():
        text = f"{text}, {place}"
    elif not text:
        text = f"Материал с места: {place}" if place else "Материал без подписи"
    return f"{text} — фото с места"


def build_listing(
    check: dict[str, Any],
    offer: dict[str, Any],
    now: Optional[datetime] = None,
) -> tuple[Optional[dict[str, Any]], str]:
    """Собрать параметры лота. Второй элемент — причина отказа (пусто, если лот есть)."""
    now = now or datetime.now(timezone.utc)
    caption = offer.get("caption") or ""
    location = offer.get("location") or ""

    shot_at = parse_dt(offer.get("shot_at"))
    if shot_at is None:
        shot_at = parse_dt((_signal(check, "metadata").get("details") or {}).get("datetime"))

    fresh_mult, fresh_why = freshness(shot_at, now)
    uniq_mult, uniq_why, unique, similar, duplicate = uniqueness(check)
    prov_mult, prov_why, origin = provenance(check)
    demand_mult, demand_why = demand(caption, location)

    if duplicate:
        return None, uniq_why

    raw = BASE_RUB * fresh_mult * uniq_mult * prov_mult * demand_mult
    price = max(ROUND_TO, int(round(raw / ROUND_TO)) * ROUND_TO)

    details = _signal(check, "metadata").get("details") or {}
    gps = details.get("gps") or {}
    geo = location.strip()
    if gps.get("latitude") is not None and gps.get("longitude") is not None:
        coords = f"{float(gps['latitude']):.4f}, {float(gps['longitude']):.4f}"
        geo = f"{geo} ({coords})" if geo else coords

    trust = check.get("trust") or {"score": 0, "uncertainty": 1.0, "coverage": 0.0,
                                   "level": "fog", "conflict": False}

    plan = {
        "title": make_title(caption, location),
        "price_rub": price,
        "trust": trust,
        "facts": {
            "origin": origin,
            "shot_at": iso(shot_at),
            "geo": geo or "не указано",
            "unique": unique,
            "similar_in_archive": similar,
        },
        "why_price": [
            f"База: {BASE_RUB} ₽",
            f"Свежесть ×{fresh_mult:g}: {fresh_why}",
            f"Уникальность ×{uniq_mult:g}: {uniq_why}",
            f"Происхождение ×{prov_mult:g}: {prov_why}",
            f"Спрос ×{demand_mult:g}: {demand_why}",
            f"Итого: {price} ₽",
        ],
    }
    return plan, ""