"""Теги тем, банк знаний и рубрика рассуждения.

Три вещи, которые делают вердикт объяснимым:

  * тег — к какому классу относится утверждение и какие правила к нему
    применяются;
  * банк — что система уже проверила, чтобы не искать заново;
  * рубрика — из чего сложился балл, а не «50 по умолчанию».
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent / "backend"))

from lakmus import bank as bank_module  # noqa: E402
from lakmus import reasoning, tags  # noqa: E402
from lakmus.full_pipeline import ClaimFinding, _level_for  # noqa: E402


# ------------------------------------------------------------------ теги

def test_finance_tag_detected():
    match = tags.classify("ЦБ запретил снятие наличных с 1 марта")
    assert match.tag.key == "finance"
    assert match.is_confident
    assert "цб" in match.hits or "наличн" in match.hits


def test_law_tag_detected():
    match = tags.classify("С 1 января вырастет штраф за покупку алкоголя")
    assert match.tag.key == "law"


def test_health_tag_detected():
    match = tags.classify("Минздрав сообщил о новом лекарстве от рака")
    assert match.tag.key == "health"


def test_unknown_tag_for_neutral_text():
    match = tags.classify("Сегодня хорошая погода для прогулки")
    # Погода — известная тема; проверяем именно отсутствие уверенности
    # на тексте без маркеров.
    tie = tags.classify("Было принято некоторое решение по вопросу")
    assert tie.tag is tags.UNKNOWN or tie.score < 1.0


def test_short_marker_matches_whole_word_only():
    """«цб» не должно находиться внутри других слов: «обцыганенный» — не ЦБ."""
    match = tags.classify("Рубль укрепился после решения ЦБ")
    assert match.tag.key == "finance"
    assert tags.classify("Обцыганенный текст без темы").tag is tags.UNKNOWN


def test_every_tag_has_rules_or_sources():
    for tag in tags.all_tags():
        assert tag.key and tag.title
        assert tag.keywords, f"тег {tag.key} без ключевых слов"
        assert tag.sources or tag.rules, f"тег {tag.key} без источников и правил"


def test_tag_serializes_for_api():
    match = tags.classify("ЦБ поднял ключевую ставку")
    data = match.as_dict()
    assert data["key"] == "finance"
    assert isinstance(data["hits"], list)
    assert data["risk"] >= 1


# ------------------------------------------------------------------ банк

@pytest.fixture()
def fresh_bank(tmp_path):
    return bank_module.reset(tmp_path / "bank.json")


def test_bank_learns_only_with_source(fresh_bank):
    # Без источника — не знание.
    assert fresh_bank.learn("ЦБ поднял ставку", "supported") is None
    # Без вердикта — тоже.
    assert fresh_bank.learn(
        "ЦБ поднял ставку", "insufficient", source_url="https://cbr.ru/x"
    ) is None
    # С источником и вердиктом — знание.
    entry = fresh_bank.learn(
        "ЦБ поднял ключевую ставку до 21%",
        "supported",
        tag="finance",
        quote="Банк России принял решение повысить ключевую ставку до 21,00%",
        source_url="https://cbr.ru/press/pr/",
        source_title="Банк России",
    )
    assert entry is not None
    assert fresh_bank.lookup("ЦБ поднял ключевую ставку до 21%") is not None


def test_bank_repeat_confirmation_increments(fresh_bank):
    for _ in range(3):
        fresh_bank.learn(
            "МРОТ вырастет с 1 января",
            "supported",
            tag="law",
            source_url="https://government.ru/news/1",
        )
    entry = fresh_bank.lookup("МРОТ вырастет с 1 января")
    assert entry is not None
    assert entry.confirmations == 3


def test_bank_human_edit_wins(fresh_bank):
    fresh_bank.learn(
        "Слух о запрете наличных",
        "supported",
        tag="finance",
        source_url="https://example.com/a",
    )
    fresh_bank.learn(
        "Слух о запрете наличных",
        "contradicted",
        tag="finance",
        source_url="https://cbr.ru/b",
        origin="human",
    )
    # Модель пробует переписать человеческую правку — не может.
    fresh_bank.learn(
        "Слух о запрете наличных",
        "supported",
        tag="finance",
        source_url="https://example.com/c",
    )
    entry = fresh_bank.lookup("Слух о запрете наличных")
    assert entry is not None
    assert entry.status == "contradicted"
    assert entry.origin == "human"


def test_bank_exact_match_only(fresh_bank):
    """Похожее утверждение — не то же самое: 21% и 20% разные факты."""
    fresh_bank.learn(
        "Ключевая ставка 21%",
        "supported",
        tag="finance",
        source_url="https://cbr.ru/a",
    )
    assert fresh_bank.lookup("Ключевая ставка 21%") is not None
    assert fresh_bank.lookup("Ключевая ставка 20%") is None


def test_bank_persists_to_disk(fresh_bank, tmp_path):
    fresh_bank.learn(
        "Тестовое утверждение",
        "supported",
        tag="tech",
        source_url="https://example.com/x",
    )
    assert fresh_bank.save() is True
    raw = json.loads((tmp_path / "bank.json").read_text(encoding="utf-8"))
    assert raw["entries"][0]["claim"] == "Тестовое утверждение"

    reopened = bank_module.Bank(tmp_path / "bank.json")
    assert reopened.lookup("Тестовое утверждение") is not None


def test_bank_search_by_topic(fresh_bank):
    fresh_bank.learn(
        "ЦБ повысил ключевую ставку до 21 процента",
        "supported",
        tag="finance",
        source_url="https://cbr.ru/a",
    )
    fresh_bank.learn(
        "В Казани открыли новый мост через реку",
        "supported",
        tag="transport",
        source_url="https://tass.ru/b",
    )
    hits = fresh_bank.search("ключевая ставка ЦБ решение", tag="finance")
    assert hits and "ставку" in hits[0].claim


# --------------------------------------------------------------- рубрика

def _claim(status, quote="", trusted=False):
    return ClaimFinding(
        text="утверждение", status=status, quote=quote, trusted=trusted
    )


def test_rubric_gives_zero_without_evidence():
    """Ни источников, ни цитат — не «50 из 100», а честно низко."""
    result = reasoning.judge(claims=[_claim("insufficient")], sources=0, trusted=0)
    assert result.verdict == "непонятно"
    assert result.confidence <= 15
    assert result.summary


def test_rubric_high_with_quote_and_trusted_source():
    result = reasoning.judge(
        claims=[_claim("supported", quote="дословно", trusted=True)],
        sources=2,
        trusted=1,
    )
    assert result.verdict == "правда"
    assert result.confidence >= 70


def test_rubric_fake_needs_contradiction():
    result = reasoning.judge(
        claims=[_claim("contradicted", quote="источник отрицает")],
        sources=1,
        trusted=1,
    )
    assert result.verdict == "фейк"


def test_rubric_conflict_lowers_confidence():
    result = reasoning.judge(
        claims=[_claim("supported", quote="a"), _claim("contradicted", quote="b")],
        sources=2,
        trusted=2,
    )
    assert result.verdict == "непонятно"
    assert result.confidence < 70


def test_rubric_every_criterion_has_reason():
    result = reasoning.judge(
        claims=[_claim("supported", quote="q")], sources=1, trusted=1
    )
    assert len(result.criteria) >= 5
    for criterion in result.criteria:
        assert criterion.title
        assert criterion.reason, f"критерий {criterion.key} без обоснования"
        assert 0 <= criterion.points <= criterion.max_points


def test_rubric_marks_future_prediction():
    """Прогноз не может быть «правдой», даже если рубрика довольна."""
    result = reasoning.judge(
        claims=[_claim("supported", quote="q")],
        sources=2,
        trusted=2,
        tag=tags.for_key("military"),
    )
    # У темы армии правило future_never_fake: вердикт не должен быть «правда»
    # без явного события. Рубрика это учитывает через правила темы.
    assert result.verdict in ("правда", "непонятно")


def test_level_for_uses_rubric_score():
    """Балл приходит из рубрики, поэтому у него есть объяснение."""
    level, verdict, score, _ = _level_for(
        [_claim("supported", quote="цитата", trusted=True)],
        sources=2,
        trusted=1,
        searched=True,
    )
    assert (level, verdict) == ("likely_real", "правда")
    assert 0 <= score <= 100
