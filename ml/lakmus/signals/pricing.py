"""Сигнал «Цена материала»: детерминированное правило из docs/CONTRACT.md.

`price_rub = base × freshness × uniqueness × provenance × demand`,
округление до 100. База 1500 ₽.

Это не оценка правдивости, поэтому вердикт всегда neutral, strength и
reliability — 0: в score доверия сигнал не участвует. Цена отдаётся только
в details (price_rub, multipliers, why_price), а объяснение каждой цифры —
по-русски, без «AI решил».

Входы:
  * shot_at — ctx.options["shot_at"] (ISO) либо EXIF-дата из метаданных;
  * uniqueness — из ctx.options["prior_signals"] / ctx.cache, иначе
    пересчитывается функциями uniqueness.py;
  * provenance — метаданные через parse_metadata (камера, дата, GPS) и
    необязательный явный признак ctx.options["geo_matches"];
  * demand — ctx.options["category"] либо ключевые слова события в тексте.

«Сейчас» берётся из ctx.options["now"] (ISO), иначе — текущее время UTC;
тот же вход и тот же `now` дают ту же цену.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from ..context import CheckContext
from ..schemas import Stage, Verdict
from .base import BaseSignal, make_result
from .provenance import parse_metadata
from .uniqueness import (
    ImageUndecodable,
    PillowMissing,
    image_hashes,
    load_archive,
    match_archive,
)

BASE_PRICE = 1500
ROUND_STEP = 100

# freshness: границы в часах (строго меньше) и множители; иначе — OLD.
FRESHNESS_TIERS: tuple[tuple[float, float], ...] = (
    (1.0, 3.0),
    (6.0, 2.0),
    (24.0, 1.5),
    (72.0, 1.0),
)
FRESHNESS_OLD = 0.5
FRESHNESS_UNKNOWN = 1.0

UNIQUENESS_NONE = 2.0
UNIQUENESS_SIMILAR = 1.0
UNIQUENESS_DUPLICATE = 0.0

PROVENANCE_FULL = 1.5
PROVENANCE_PARTIAL = 1.0
PROVENANCE_NONE = 0.7

DEMAND_INCIDENT = 1.8
DEMAND_URBAN = 1.2
DEMAND_OTHER = 1.0

# Ключевые слова категории события. Регистр не важен.
INCIDENT_WORDS: tuple[str, ...] = (
    "чп", "происшеств", "пожар", "взрыв", "авар", "катастроф", "дтп",
    "наводнени", "землетряс", "обрушен", "стрельб", "ранен", "погиб",
    "эвакуац", "теракт", "крушени", "утечк", "задымлен",
)
URBAN_WORDS: tuple[str, ...] = (
    "город", "улиц", "метро", "район", "двор", "парк", "площад", "школ",
    "магазин", "жк", "мэр", "коммунал", "тротуар", "остановк", "маршрут",
)


def _as_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_bool(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in ("true", "1", "да", "yes"):
        return True
    if isinstance(value, str) and value.strip().lower() in ("false", "0", "нет", "no"):
        return False
    return None


# --------------------------------------------------------------------------
# разбор дат
# --------------------------------------------------------------------------


def parse_moment(value: Any) -> Optional[datetime]:
    """ISO, EXIF ("2026:11:13 15:12:00") или date → datetime UTC."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        moment = value
    else:
        text = str(value).strip()
        moment = None
        try:
            moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            for fmt in ("%Y:%m:%d %H:%M:%S", "%Y:%m:%d", "%Y-%m-%d"):
                try:
                    moment = datetime.strptime(text[:19] if "%H" in fmt else text[:10], fmt)
                    break
                except ValueError:
                    continue
        if moment is None:
            return None
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def _now(ctx: CheckContext) -> datetime:
    explicit = parse_moment(ctx.options.get("now"))
    if explicit is not None:
        return explicit
    return datetime.now(timezone.utc)


def _iso(moment: Optional[datetime]) -> Optional[str]:
    return moment.isoformat() if moment else None


# --------------------------------------------------------------------------
# множители
# --------------------------------------------------------------------------


def freshness_multiplier(hours: Optional[float]) -> tuple[float, str]:
    """(множитель, объяснение)."""
    if hours is None:
        return FRESHNESS_UNKNOWN, "дата съёмки неизвестна — свежесть не оценивается, множитель 1.0"
    if hours < 0:
        hours = 0.0
    for limit, factor in FRESHNESS_TIERS:
        if hours < limit:
            return factor, f"снято {_hours_text(hours)} назад, множитель {factor:.1f}"
    return FRESHNESS_OLD, f"снято {_hours_text(hours)} назад, множитель {FRESHNESS_OLD:.1f}"


def _hours_text(hours: float) -> str:
    if hours < 1.0:
        return f"{max(1, round(hours * 60))} мин."
    if hours < 48.0:
        return f"{hours:.1f} ч."
    return f"{hours / 24.0:.0f} сут."


def demand_category(text: str, explicit: Any = None) -> tuple[str, float, str]:
    """(категория, множитель, объяснение) по подсказке или ключевым словам."""
    key = str(explicit or "").strip().lower()
    alias = {
        "incident": "incident", "чп": "incident", "происшествие": "incident",
        "urban": "urban", "городское": "urban", "city": "urban",
        "other": "other", "остальное": "other",
    }.get(key)
    if alias == "incident":
        return "incident", DEMAND_INCIDENT, f"категория ЧП/происшествие, множитель {DEMAND_INCIDENT:.1f}"
    if alias == "urban":
        return "urban", DEMAND_URBAN, f"городская категория, множитель {DEMAND_URBAN:.1f}"
    if alias == "other":
        return "other", DEMAND_OTHER, f"обычная категория, множитель {DEMAND_OTHER:.1f}"

    low = (text or "").lower()
    if any(word in low for word in INCIDENT_WORDS):
        return "incident", DEMAND_INCIDENT, f"по тексту это ЧП/происшествие, множитель {DEMAND_INCIDENT:.1f}"
    if any(word in low for word in URBAN_WORDS):
        return "urban", DEMAND_URBAN, f"по тексту это городское событие, множитель {DEMAND_URBAN:.1f}"
    return "other", DEMAND_OTHER, f"категория неопределённая, множитель {DEMAND_OTHER:.1f}"


# --------------------------------------------------------------------------
# происхождение и уникальность из уже посчитанного или из данных
# --------------------------------------------------------------------------


def _prior_map(ctx: CheckContext) -> dict[str, Any]:
    raw = (
        ctx.options.get("prior_signals")
        or ctx.cache.get("signal_results")
        or ctx.cache.get("signals")
        or {}
    )
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, (list, tuple)):
        out: dict[str, Any] = {}
        for item in raw:
            key = getattr(item, "id", None)
            if key is None and isinstance(item, dict):
                key = item.get("id")
            if key:
                out[str(key)] = item
        return out
    return {}


def _details_of(item: Any) -> dict[str, Any]:
    if item is None:
        return {}
    raw = getattr(item, "details", None)
    if raw is None and isinstance(item, dict):
        raw = item.get("details", item)
    return raw if isinstance(raw, dict) else {}


def _metadata_details(ctx: CheckContext, meta: dict[str, Any]) -> dict[str, Any]:
    """Только нужные для цены поля метаданных — без разбора текстовых чанков."""
    exif = meta.get("exif") or {}
    gps = meta.get("gps") or {}
    camera = None
    make, model = exif.get("Make"), exif.get("Model")
    if isinstance(make, str) and make:
        camera = f"{make} {model}".strip() if isinstance(model, str) and model else make
    datetime_value = (
        exif.get("DateTimeOriginal") or exif.get("DateTime") or exif.get("DateTimeDigitized")
    )
    return {
        "has_metadata": bool(meta.get("has_metadata")),
        "camera": camera,
        "datetime": datetime_value if isinstance(datetime_value, str) else None,
        "gps": {"latitude": gps.get("Latitude"), "longitude": gps.get("Longitude")},
        "gps_present": bool(gps.get("Latitude") and gps.get("Longitude")),
    }


def _provenance_multiplier(
    ctx: CheckContext, meta_details: dict[str, Any]
) -> tuple[float, str, dict[str, Any]]:
    camera = meta_details.get("camera")
    datetime_value = meta_details.get("datetime")
    gps_present = meta_details.get("gps_present")
    intact = bool(camera or datetime_value)

    explicit = _as_bool(ctx.options.get("geo_matches"))
    claimed = ctx.options.get("location") or ctx.options.get("claimed_location") or ""

    if explicit is not None:
        geo_matches, geo_note = explicit, ("гео совпадает с подписью" if explicit else "гео не совпадает с подписью")
    elif gps_present and claimed:
        # Сверить координаты с названием места без геокодера нельзя — честно
        # фиксируем неопределённость, а не выдаём её за совпадение.
        geo_matches, geo_note = False, "координаты есть, но сверить их с подписью о месте нечем"
    elif not claimed:
        geo_matches, geo_note = False, "заявленного места нет"
    else:
        geo_matches, geo_note = False, "геолокации в метаданных нет"

    flags = {
        "camera": bool(camera),
        "datetime": bool(datetime_value),
        "gps": bool(gps_present),
        "geo_matches": bool(geo_matches),
        "geo_note": geo_note,
    }

    if intact and geo_matches:
        return (
            PROVENANCE_FULL,
            f"метаданные целы и {geo_note}, множитель {PROVENANCE_FULL:.1f}",
            flags,
        )
    if intact or gps_present or meta_details.get("has_metadata"):
        return (
            PROVENANCE_PARTIAL,
            f"метаданные частичные ({geo_note}), множитель {PROVENANCE_PARTIAL:.1f}",
            flags,
        )
    return (
        PROVENANCE_NONE,
        f"метаданных нет ({geo_note}), множитель {PROVENANCE_NONE:.1f}",
        flags,
    )


def _uniqueness_from_details(details: dict[str, Any]) -> Optional[dict[str, Any]]:
    if "unique" not in details and "duplicate" not in details:
        return None
    duplicate = bool(details.get("duplicate"))
    similar = details.get("similar_in_archive")
    if not isinstance(similar, int):
        similar = 0
    unique = bool(details.get("unique", not duplicate and similar == 0))
    return {"unique": unique and not duplicate, "duplicate": duplicate, "similar": similar}


def _uniqueness_verdict(
    ctx: CheckContext,
) -> tuple[dict[str, Any], str]:
    """Уникальность: из prior_signals, кэша или собственный пересчёт."""
    prior = _prior_map(ctx)
    for key in ("uniqueness", "I7"):
        found = _uniqueness_from_details(_details_of(prior.get(key))) if prior.get(key) else None
        if found is not None:
            return found, "prior_signals"

    cached = ctx.cache.get("uniqueness")
    if isinstance(cached, dict) and ("unique" in cached or "duplicate" in cached):
        found = _uniqueness_from_details(cached)
        if found is not None:
            return found, "cache"

    data = ctx.data
    if not data:
        return {"unique": None, "duplicate": False, "similar": None}, "unavailable"
    try:
        hashes = ctx.cache.get("image_hashes")
        if not isinstance(hashes, dict) or "dhash" not in hashes:
            hashes = ctx.remember("image_hashes", image_hashes(data))
        entries, reason = load_archive(ctx.options.get("archive_dir"))
        if reason:
            return {"unique": None, "duplicate": False, "similar": None}, "unavailable"
        match = match_archive(hashes, entries)
        return (
            {
                "unique": match["similar"] == 0,
                "duplicate": match["duplicate"],
                "similar": match["similar"],
            },
            "recomputed",
        )
    except (PillowMissing, ImageUndecodable, OSError):
        return {"unique": None, "duplicate": False, "similar": None}, "unavailable"


def _uniqueness_multiplier(unique_info: dict[str, Any]) -> tuple[float, str]:
    if unique_info.get("duplicate"):
        return UNIQUENESS_DUPLICATE, "дубликат уже есть в архиве, множитель 0.0 — материал не выставляется"
    if unique_info.get("unique") is None:
        return (
            UNIQUENESS_SIMILAR,
            "уникальность проверить не удалось (архив недоступен), множитель 1.0 как при похожих кадрах",
        )
    if unique_info.get("unique"):
        return UNIQUENESS_NONE, f"совпадений в архиве нет, множитель {UNIQUENESS_NONE:.1f}"
    similar = unique_info.get("similar") or 1
    return (
        UNIQUENESS_SIMILAR,
        f"похожих кадров в архиве: {similar}, множитель {UNIQUENESS_SIMILAR:.1f}",
    )


def _round_price(value: float) -> int:
    """Округление до 100 вверх от половины шага (детерминированное)."""
    return int(math.floor(value / ROUND_STEP + 0.5)) * ROUND_STEP


# --------------------------------------------------------------------------
# сигнал
# --------------------------------------------------------------------------


class PricingSignal(BaseSignal):
    """Цена материала по правилу контракта. Не участник оценки доверия."""

    id = "pricing"
    name = "Цена материала"
    stage = Stage.context
    timeout_s = 8.0

    async def run(self, ctx: CheckContext):
        now = _now(ctx)

        # --- метаданные: из priors, иначе из байтов
        prior = _prior_map(ctx)
        meta_details = _details_of(prior.get("metadata")) if prior.get("metadata") else {}
        meta: dict[str, Any] = {}
        if not meta_details:
            cached_meta = ctx.cache.get("metadata")
            if isinstance(cached_meta, dict) and "c2pa" in cached_meta:
                meta = cached_meta
            elif ctx.data:
                meta = ctx.remember("metadata", parse_metadata(ctx.data))
            meta_details = _metadata_details(ctx, meta)
        else:
            # В details сигнала метаданных поля уже разобраны.
            meta_details = {
                "has_metadata": bool(meta_details.get("has_metadata")),
                "camera": meta_details.get("camera"),
                "datetime": meta_details.get("datetime"),
                "gps_present": bool(meta_details.get("gps") or {}),
                "gps": meta_details.get("gps") or {},
            }

        # --- дата съёмки
        shot_at = parse_moment(ctx.options.get("shot_at"))
        if shot_at is None:
            shot_at = parse_moment(meta_details.get("datetime"))
            shot_source = "metadata"
        else:
            shot_source = "options"
        hours = (now - shot_at).total_seconds() / 3600.0 if shot_at else None
        fresh, fresh_why = freshness_multiplier(hours)

        unique_info, unique_source = _uniqueness_verdict(ctx)
        unique_mult, unique_why = _uniqueness_multiplier(unique_info)

        prov_mult, prov_why, prov_flags = _provenance_multiplier(ctx, meta_details)

        text_for_demand = " ".join(
            part for part in (str(ctx.options.get("caption") or ""), ctx.text or "") if part
        )
        category, demand_mult, demand_why = demand_category(
            text_for_demand, ctx.options.get("category")
        )

        price_rub = _round_price(BASE_PRICE * fresh * unique_mult * prov_mult * demand_mult)
        available = unique_mult != UNIQUENESS_DUPLICATE

        why_price = [
            f"Базовая цена: {BASE_PRICE} ₽",
            f"Свежесть: {fresh_why}",
            f"Уникальность: {unique_why}",
            f"Происхождение: {prov_why}",
            f"Спрос: {demand_why}",
        ]
        if not available:
            why_price.append("Итог: дубликат не выставляется на продажу, цена 0 ₽")
        else:
            why_price.append(
                f"Итог: {BASE_PRICE} × {fresh:.1f} × {unique_mult:.1f} × "
                f"{prov_mult:.1f} × {demand_mult:.1f} = {price_rub} ₽ (округлено до 100)"
            )

        details: dict[str, Any] = {
            "price_rub": price_rub,
            "currency": "RUB",
            "listed": available,
            "base": BASE_PRICE,
            "multipliers": {
                "freshness": fresh,
                "uniqueness": unique_mult,
                "provenance": prov_mult,
                "demand": demand_mult,
            },
            "why_price": why_price,
            "shot_at": _iso(shot_at),
            "shot_at_source": shot_source if shot_at else None,
            "age_hours": round(hours, 3) if hours is not None else None,
            "demand_category": category,
            "provenance_flags": prov_flags,
            "uniqueness": unique_info,
            "uniqueness_source": unique_source,
            "now": now.isoformat(),
        }

        if not available:
            summary = (
                "Материал уже есть в архиве: дубликат не выставляется на продажу. "
                "Это не оценка правдивости."
            )
        else:
            summary = (
                f"Расчётная цена — {price_rub} ₽ по правилу "
                f"{BASE_PRICE} × свежесть × уникальность × происхождение × спрос. "
                "Цена не говорит, настоящий ли материал."
            )
        # strength/reliability = 0: цена — не голос в оценке доверия.
        return make_result(self, Verdict.neutral, 0.0, 0.0, summary, details)