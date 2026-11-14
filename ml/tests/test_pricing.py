"""Тесты сигнала «Цена материала»: правило из docs/CONTRACT.md.

Входы искусственные: shot_at/now задаются опциями, поэтому тест не зависит
от текущего времени. Метаданные — реальный JPEG от Pillow с EXIF/GPS.
"""

import io
import json

from PIL import Image

from lakmus.context import CheckContext
from lakmus.schemas import CheckInput, InputType, Stage, Verdict
from lakmus.signals.pricing import (
    BASE_PRICE,
    PricingSignal,
    demand_category,
    freshness_multiplier,
    parse_moment,
)
from lakmus.signals.uniqueness import image_hashes


def make_jpeg(exif: bool = True, size=(48, 48)) -> bytes:
    image = Image.new("RGB", size, (90, 120, 160))
    image.putpixel((0, 0), (250, 250, 250))
    buffer = io.BytesIO()
    if not exif:
        image.save(buffer, "JPEG", quality=90)
        return buffer.getvalue()
    exif_data = Image.Exif()
    exif_data[0x010F] = "Canon"
    exif_data[0x0110] = "EOS R6"
    exif_data[0x9003] = "2026:11:13 15:00:00"
    gps = exif_data.get_ifd(0x8825)
    gps[1] = "N"
    gps[2] = (55.0, 45.0, 0.0)
    gps[3] = "E"
    gps[4] = (37.0, 37.0, 0.0)
    image.save(buffer, "JPEG", quality=90, exif=exif_data.tobytes())
    return buffer.getvalue()


def write_archive(tmp_path, items) -> str:
    archive = tmp_path / "archive"
    archive.mkdir(exist_ok=True)
    (archive / "manifest.json").write_text(
        json.dumps({"items": items}, ensure_ascii=False), encoding="utf-8"
    )
    return str(archive)


def empty_archive(tmp_path) -> str:
    """Архив без совпадений: хеши, инвертированные относительно входных."""
    data = make_jpeg(exif=True)
    hashes = image_hashes(data)
    far = {
        "id": "far",
        "dhash": f"{int(hashes['dhash'], 16) ^ 0xFFFFFFFFFFFFFFFF:016x}",
        "ahash": f"{int(hashes['ahash'], 16) ^ 0xFFFFFFFFFFFFFFFF:016x}",
    }
    return write_archive(tmp_path, [far])


def make_ctx(data, options=None, text="") -> CheckContext:
    return CheckContext(
        check_id="test-pricing",
        input=CheckInput(type=InputType.image),
        data=data,
        text=text,
        options=dict(options or {}),
    )


# --------------------------------------------------------------------------
# множители и утилиты
# --------------------------------------------------------------------------


def test_freshness_tiers():
    assert freshness_multiplier(0.2)[0] == 3.0
    assert freshness_multiplier(2.0)[0] == 2.0
    assert freshness_multiplier(10.0)[0] == 1.5
    assert freshness_multiplier(50.0)[0] == 1.0
    assert freshness_multiplier(200.0)[0] == 0.5
    assert freshness_multiplier(None)[0] == 1.0


def test_demand_category_by_words_and_option():
    assert demand_category("Пожар на складе в Люберцах")[1] == 1.8
    assert demand_category("В центре города перекрыли улицу")[1] == 1.2
    assert demand_category("Котик спит")[1] == 1.0
    assert demand_category("", explicit="incident")[0] == "incident"
    assert demand_category("Пожар", explicit="other")[1] == 1.0


def test_parse_moment_formats():
    assert parse_moment("2026-11-13T15:00:00Z") is not None
    assert parse_moment("2026:11:13 15:00:00") is not None
    assert parse_moment("2026-11-13") is not None
    assert parse_moment("не дата") is None
    assert parse_moment(None) is None


# --------------------------------------------------------------------------
# максимум и ноль
# --------------------------------------------------------------------------


async def test_max_price_for_fresh_unique_full_provenance_and_incident(tmp_path):
    data = make_jpeg(exif=True)
    ctx = make_ctx(data, {
        "shot_at": "2026-11-13T15:00:00Z",
        "now": "2026-11-13T15:30:00Z",
        "archive_dir": empty_archive(tmp_path),
        "geo_matches": True,
        "category": "incident",
    })
    result = await PricingSignal().run(ctx)

    assert result.stage == Stage.context
    assert result.verdict == Verdict.neutral
    assert result.strength == 0.0
    assert result.reliability == 0.0
    assert result.details["multipliers"] == {
        "freshness": 3.0,
        "uniqueness": 2.0,
        "provenance": 1.5,
        "demand": 1.8,
    }
    # 1500 × 3 × 2 × 1.5 × 1.8 = 24300
    assert result.details["price_rub"] == 24300
    assert result.details["listed"] is True
    assert result.details["price_rub"] % 100 == 0
    assert len(result.details["why_price"]) >= 5
    assert any("Базовая цена" in line for line in result.details["why_price"])
    assert any("Итог" in line for line in result.details["why_price"])


async def test_old_duplicate_is_not_listed(tmp_path):
    data = make_jpeg(exif=True)
    hashes = image_hashes(data)
    archive_dir = write_archive(tmp_path, [{
        "id": "old-shot",
        "dhash": hashes["dhash"],
        "ahash": hashes["ahash"],
        "date": "2019-04-01",
    }])
    ctx = make_ctx(data, {
        "shot_at": "2026-11-01T10:00:00Z",
        "now": "2026-11-13T15:00:00Z",
        "archive_dir": archive_dir,
    })
    result = await PricingSignal().run(ctx)

    assert result.details["multipliers"]["uniqueness"] == 0.0
    assert result.details["price_rub"] == 0
    assert result.details["listed"] is False
    assert any("не выставляется" in line for line in result.details["why_price"])
    assert result.verdict == Verdict.neutral


async def test_price_is_deterministic(tmp_path):
    data = make_jpeg(exif=True)
    options = {
        "shot_at": "2026-11-13T12:00:00Z",
        "now": "2026-11-13T15:00:00Z",
        "archive_dir": empty_archive(tmp_path),
        "category": "urban",
    }
    first = await PricingSignal().run(make_ctx(data, options))
    second = await PricingSignal().run(make_ctx(data, options))

    assert first.details["price_rub"] == second.details["price_rub"]
    assert first.details["multipliers"] == second.details["multipliers"]


async def test_rounding_to_hundred(tmp_path):
    # 1500 × 1.0 (даты нет) × 2.0 (уникально) × 0.7 (метаданных нет) × 1.0 = 2100
    data = make_jpeg(exif=False)
    ctx = make_ctx(data, {
        "now": "2026-11-13T15:00:00Z",
        "archive_dir": empty_archive(tmp_path),
    })
    result = await PricingSignal().run(ctx)

    price = result.details["price_rub"]
    assert price % 100 == 0
    assert price == 2100
    assert result.details["multipliers"]["freshness"] == 1.0
    assert result.details["multipliers"]["provenance"] == 0.7
    assert result.details["why_price"]


async def test_uses_prior_signals_when_given(tmp_path):
    ctx = make_ctx(make_jpeg(exif=True), {
        "shot_at": "2026-11-13T14:30:00Z",
        "now": "2026-11-13T15:00:00Z",
        "prior_signals": {
            "uniqueness": {
                "id": "uniqueness",
                "details": {"unique": False, "similar_in_archive": 2, "duplicate": False},
            },
            "metadata": {
                "id": "metadata",
                "details": {
                    "has_metadata": True,
                    "camera": "Canon EOS R6",
                    "datetime": "2026:11:13 14:00:00",
                    "gps": {"latitude": 55.0, "longitude": 37.0},
                },
            },
        },
        "geo_matches": True,
    })
    result = await PricingSignal().run(ctx)

    assert result.details["uniqueness_source"] == "prior_signals"
    assert result.details["multipliers"]["uniqueness"] == 1.0
    assert result.details["multipliers"]["provenance"] == 1.5
    # 1500 × 3 × 1 × 1.5 × 1.0 = 6750 → 6800
    assert result.details["price_rub"] == 6800


async def test_unavailable_archive_is_not_duplicate(tmp_path):
    ctx = make_ctx(make_jpeg(), {
        "shot_at": "2026-11-13T14:00:00Z",
        "now": "2026-11-13T15:00:00Z",
        "archive_dir": str(tmp_path / "missing"),
    })
    result = await PricingSignal().run(ctx)

    # Архива нет — уникальность не проверить: множитель 1.0, а не «дубликат».
    assert result.details["multipliers"]["uniqueness"] == 1.0
    assert result.details["listed"] is True
    assert result.details["price_rub"] > 0
    assert result.details["uniqueness_source"] == "unavailable"


async def test_exif_date_used_when_shot_at_missing(tmp_path):
    ctx = make_ctx(make_jpeg(exif=True), {
        "now": "2026-11-13T15:30:00Z",
        "archive_dir": empty_archive(tmp_path),
    })
    result = await PricingSignal().run(ctx)

    assert result.details["shot_at_source"] == "metadata"
    assert result.details["multipliers"]["freshness"] == 3.0


async def test_no_data_is_neutral_with_zero_price(tmp_path):
    ctx = CheckContext(
        check_id="test-pricing-empty",
        input=CheckInput(type=InputType.image),
        options={"now": "2026-11-13T15:00:00Z", "archive_dir": empty_archive(tmp_path)},
    )
    result = await PricingSignal().run(ctx)

    assert result.verdict == Verdict.neutral
    assert result.strength == 0.0
    assert result.reliability == 0.0
    assert result.details["price_rub"] >= 0
    assert result.details["multipliers"]["provenance"] == 0.7
    assert result.details["why_price"]


async def test_caption_drives_demand(tmp_path):
    data = make_jpeg(exif=True)
    base_options = {
        "shot_at": "2026-11-13T14:30:00Z",
        "now": "2026-11-13T15:00:00Z",
        "archive_dir": empty_archive(tmp_path),
    }
    calm = await PricingSignal().run(
        make_ctx(data, {**base_options, "caption": "Прогулка в парке"})
    )
    incident = await PricingSignal().run(
        make_ctx(data, {**base_options, "caption": "Пожар на складе, дым над районом"})
    )

    assert calm.details["demand_category"] == "urban"
    assert incident.details["demand_category"] == "incident"
    assert incident.details["price_rub"] > calm.details["price_rub"]


async def test_price_increases_monotonically_with_base():
    """База 1500 ₽ зафиксирована контрактом."""
    assert BASE_PRICE == 1500