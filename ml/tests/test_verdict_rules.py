"""Алгоритм анализа: плейбук по темам и правила вывода вердикта.

Здесь проверяется главное обещание продукта: вердикт получается по
явным правилам, а не «по настроению модели».

  * плейбук даёт разный чек-лист для экономики, медицины и медиа;
  * правило с сильным признаком решает само;
  * слабые признаки не перебивают сильные;
  * противоречие ведёт к «непонятно», а не к случайной стороне;
  * отсутствие метаданных у файла никогда не даёт «фейк».
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lakmus import playbook, verdict_rules  # noqa: E402
from lakmus.full_pipeline import ClaimFinding  # noqa: E402


# ---------------------------------------------------------------- плейбук

def test_playbook_differs_by_topic():
    finance = playbook.for_material("text", "finance")
    health = playbook.for_material("text", "health")

    assert finance.kind == health.kind == "text"
    assert finance.steps != health.steps
    assert "Банка России" in " ".join(finance.steps)
    assert "Минздрав" in " ".join(health.steps)


def test_playbook_has_fake_and_real_signals():
    plan = playbook.for_material("text", "law")
    assert plan.fake_signals
    assert plan.real_signals
    assert plan.not_proof
    assert plan.rules


def test_playbook_for_image_and_video_differ():
    image = playbook.for_material("image")
    video = playbook.for_material("video")

    assert image.kind == "image"
    assert video.kind == "video"
    assert "статичность" in " ".join(video.steps).lower() or "статичн" in " ".join(video.steps).lower()
    assert image.steps != video.steps


def test_playbook_link_is_text():
    assert playbook.for_material("link", "finance").kind == "text"


def test_playbook_unknown_topic_still_usable():
    plan = playbook.for_material("text", "неизвестная-тема")
    assert plan.steps
    assert plan.fake_signals


def test_playbook_prompt_contains_checklist():
    text = playbook.for_material("video").as_prompt()
    assert "АЛГОРИТМ ПРОВЕРКИ" in text
    assert "Признаки подделки" in text
    assert "НЕ считается доказательством" in text


def test_playbook_serializes_for_api():
    data = playbook.for_material("image").as_dict()
    assert data["kind"] == "image"
    assert isinstance(data["steps"], list)


# ---------------------------------------------------------------- правила

def test_strong_generator_marker_wins():
    class Signal:
        name = "Видео"
        verdict = "supports_fake"
        summary = "подпись генератора"
        details = {"generator_hits": ["Sora"]}

    result = verdict_rules.rules_for_media([Signal()])
    assert result.verdict == "фейк"
    assert result.confidence >= 80
    assert any(h.key == "generator" for h in result.hits)


def test_static_video_is_fake():
    class Signal:
        name = "Видео"
        verdict = "supports_fake"
        summary = "кадры не меняются"
        details = {"static_video": True}

    result = verdict_rules.rules_for_media([Signal()])
    assert result.verdict == "фейк"


def test_missing_metadata_is_never_fake():
    """Стёртые метаданные — не улика: мессенджеры их удаляют."""
    class Signal:
        name = "Метаданные"
        verdict = "neutral"
        summary = "метаданных нет"
        details = {"no_metadata": True}

    result = verdict_rules.rules_for_media([Signal()])
    assert result.verdict == "непонятно"
    assert result.confidence <= 20


def test_editor_traces_are_neutral():
    class Signal:
        name = "Следы монтажа"
        verdict = "neutral"
        summary = "монтаж"
        details = {"editor_hits": ["Photoshop"]}

    result = verdict_rules.rules_for_media([Signal()])
    assert result.verdict == "непонятно"
    assert any(h.key == "editor" for h in result.hits)


def test_text_supported_with_quote_is_true():
    claim = ClaimFinding(
        text="МРОТ 22 440", status="supported", quote="22 440 рубля в месяц"
    )
    result = verdict_rules.rules_for_text(
        claims=[claim], sources=1, trusted=1
    )
    assert result.verdict == "правда"
    assert result.confidence >= 70


def test_text_contradicted_with_quote_is_fake():
    claim = ClaimFinding(
        text="ЦБ запретил наличные",
        status="contradicted",
        quote="Банк России не принимал решений о запрете наличных",
    )
    result = verdict_rules.rules_for_text(
        claims=[claim], sources=1, trusted=1
    )
    assert result.verdict == "фейк"
    assert result.confidence >= 70


def test_text_without_sources_is_unclear():
    claim = ClaimFinding(text="что-то произошло", status="insufficient")
    result = verdict_rules.rules_for_text(
        claims=[claim], sources=0, trusted=0
    )
    assert result.verdict == "непонятно"
    assert result.confidence <= 20


def test_text_future_is_never_fake():
    claim = ClaimFinding(
        text="мобилизацию объявят со следующей недели",
        status="contradicted",
        quote="источник не подтверждает",
    )
    result = verdict_rules.rules_for_text(
        claims=[claim], sources=1, trusted=1, is_future=True
    )
    assert result.verdict != "фейк" or result.confidence < 70


def test_conflict_between_directions_is_unclear():
    """Сильный довод за фейк и сильный за правду — спор, не выбор наугад."""
    fake = ClaimFinding(
        text="а", status="contradicted", quote="источник отрицает"
    )
    real = ClaimFinding(
        text="б", status="supported", quote="источник подтверждает"
    )
    result = verdict_rules.rules_for_text(
        claims=[fake, real], sources=2, trusted=2
    )
    assert result.verdict == "непонятно"


def test_every_hit_has_reason():
    claim = ClaimFinding(text="а", status="supported", quote="цитата")
    result = verdict_rules.rules_for_text(claims=[claim], sources=1, trusted=1)
    assert result.hits
    for hit in result.hits:
        assert hit.title
        assert hit.reason
        assert hit.direction in ("fake", "real", "neutral")
        assert 0.0 <= hit.weight <= 1.0


def test_rules_catalog_for_ui():
    for kind in ("media", "text"):
        catalog = verdict_rules.describe_rules(kind)
        assert catalog
        for item in catalog:
            assert item["key"] and item["title"] and item["detail"]
