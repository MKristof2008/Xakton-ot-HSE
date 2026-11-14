"""Признаки вирусной выдумки: ловят жанр, но не обвиняют зря.

Проверяем две вещи, которые легко сломать при правках словаря:

  * настоящие выдумки ловятся;
  * нейтральные новости не ловятся, иначе система начнёт клеить ярлыки.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lakmus import fake_markers, verdict_rules  # noqa: E402
from lakmus.full_pipeline import ClaimFinding  # noqa: E402


FAKES = [
    "СРОЧНО! ЦБ запретил снятие наличных с 1 марта. Перешлите всем!",
    "С 1 января всех россиян обязали установить приложение 2.0.",
    "ЦБ вводит новый налог на снятие наличных — 10%.",
    "Путин подписал указ о роспуске Госдумы.",
    "В Москве вводят комендантский час с 1 декабря для всех",
]

NEUTRAL = [
    "В Казани открыли новый мост через реку.",
    "Минздрав сообщил о новом лекарстве от рака",
    "ЦБ поднял ключевую ставку до 21% годовых",
    "С 1 января 2025 года МРОТ составляет 22 440 рубля.",
]


def test_fakes_are_detected():
    for text in FAKES:
        markers = fake_markers.find_markers(text)
        assert markers, f"не поймали выдумку: {text}"
        assert fake_markers.score(markers) > 0


def test_neutral_text_has_few_or_no_markers():
    """Нейтральная новость не должна выглядеть как вирусная выдумка."""
    for text in NEUTRAL:
        markers = fake_markers.find_markers(text)
        # Один слабый маркер допустим (например, «учёные нашли»),
        # но не набор признаков жанра.
        assert len(markers) <= 1, f"ложное срабатывание: {text} -> {[m.key for m in markers]}"


def test_absurd_measure_weighs_more_than_style():
    """«Запрет наличных» весомее, чем просто восклицание."""
    absurd = fake_markers.find_markers("ЦБ запретил снятие наличных")
    style = fake_markers.find_markers("СРОЧНО! Перешлите всем!")
    assert any(m.key == "absurd_measure" for m in absurd)
    assert not any(m.key == "absurd_measure" for m in style)


def test_single_style_marker_does_not_decide():
    """Один стилистический признак — пометка, но не вердикт «фейк»."""
    text = "Учёные нашли воду на Марсе."
    result = verdict_rules.rules_for_text(
        claims=[ClaimFinding(text=text, status="insufficient")],
        sources=0,
        trusted=0,
        text=text,
    )
    assert result.verdict == "непонятно"


def test_absurd_measure_decides_without_sources():
    text = "ЦБ вводит новый налог на снятие наличных — 10%."
    result = verdict_rules.rules_for_text(
        claims=[ClaimFinding(text=text, status="insufficient")],
        sources=0,
        trusted=0,
        text=text,
    )
    assert result.verdict == "фейк"
    assert result.confidence >= 55


def test_sources_outweigh_text_style():
    """Если источник есть, его слово важнее стиля текста."""
    text = "СРОЧНО! Перешлите всем! ЦБ поднял ставку до 21%."
    claim = ClaimFinding(
        text=text, status="supported", quote="Банк России повысил ставку до 21,00%"
    )
    result = verdict_rules.rules_for_text(
        claims=[claim], sources=1, trusted=1, text=text
    )
    assert result.verdict == "правда"


def test_marker_has_reason_and_evidence():
    markers = fake_markers.find_markers("СРОЧНО! Перешлите всем!")
    assert markers
    for marker in markers:
        assert marker.title
        assert marker.reason
        assert marker.evidence
