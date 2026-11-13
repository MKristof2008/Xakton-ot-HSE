"""Тесты сигнала сверки с базой фактов.

Проверяем то, что важно для честности продукта: база опровергает,
подтверждает, расходится в числах, или темы нет вовсе. В последнем
случае сигнал обязан сказать «не проверено», а не «фейк».
"""

from __future__ import annotations

import json

import pytest

from lakmus.context import CheckContext
from lakmus.schemas import CheckInput, InputType, Verdict
from lakmus.signals.kb_facts import (
    KbFactsSignal,
    KbError,
    check_against_topic,
    find_topic,
    load_kb,
    _numbers,
    _numbers_agree,
    _years,
)


def make_ctx(text: str, **options) -> CheckContext:
    return CheckContext(
        check_id="t",
        input=CheckInput(type=InputType.text, extracted_text=text),
        text=text,
        options=options,
    )


def run(text: str, **options):
    import asyncio
    return asyncio.run(KbFactsSignal().run(make_ctx(text, **options)))


# ---------- разбор чисел ----------

def test_numbers_parsed_with_spaces_and_commas():
    assert 5000.0 in _numbers("штраф 5 000 рублей")
    assert 21.0 in _numbers("ставка 21,00% годовых")


def test_numbers_agree_tolerates_rounding():
    assert _numbers_agree({21.0}, {21.0}) is True
    assert _numbers_agree({21.0}, {20.0}) is False
    assert _numbers_agree(set(), {21.0}) is None


def test_years_extracted():
    assert _years("25 октября 2024 года") == {2024}
    assert _years("без даты") == set()


# ---------- база ----------

def test_load_kb_missing_file_raises(tmp_path):
    with pytest.raises(KbError):
        load_kb(tmp_path / "nope.json")


def test_load_kb_broken_json_raises(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{не json", encoding="utf-8")
    with pytest.raises(KbError):
        load_kb(path)


def test_find_topic_matches_longest_keyword():
    kb = load_kb()
    topic = find_topic(kb, "ЦБ поднял ключевую ставку до 21%")
    assert topic is not None
    assert topic["id"] == "kb_cb_key_rate"


def test_find_topic_returns_none_for_unknown():
    kb = load_kb()
    assert find_topic(kb, "Сегодня хорошая погода в Москве") is None


# ---------- вердикты ----------

def test_refuted_claim_returns_supports_fake():
    result = run("СРОЧНО! ЦБ запретил наличные с 1 марта 2026 года! Перешли всем!")
    assert result.verdict == Verdict.supports_fake
    assert result.details["reason"] == "refuted"
    assert result.details["source"]


def test_matching_fact_returns_supports_real():
    result = run("ЦБ поднял ключевую ставку до 21% годовых 25 октября 2024 года")
    assert result.verdict == Verdict.supports_real
    assert result.details["reason"] == "matched"


def test_number_mismatch_is_fake():
    result = run("ЦБ поднял ключевую ставку до 15% годовых 25 октября 2024 года")
    assert result.verdict == Verdict.supports_fake
    assert result.details["reason"] == "number_mismatch"


def test_unknown_topic_is_unavailable_not_fake():
    """Главное правило: чего нет в базе — не значит «фейк»."""
    result = run("Вчера в Казани открыли новый мост через реку")
    assert result.verdict == Verdict.unavailable
    assert result.details["reason"] == "topic_not_found"


def test_short_text_is_unavailable():
    result = run("привет")
    assert result.verdict == Verdict.unavailable


def test_image_input_is_unavailable():
    import asyncio
    ctx = CheckContext(
        check_id="i",
        input=CheckInput(type=InputType.image),
        data=b"\x89PNG\r\n\x1a\n",
    )
    result = asyncio.run(KbFactsSignal().run(ctx))
    assert result.verdict == Verdict.unavailable


def test_broken_kb_path_is_unavailable(tmp_path):
    result = run("ЦБ поднял ключевую ставку до 21%", kb_path=tmp_path / "missing.json")
    assert result.verdict == Verdict.unavailable
    assert "не найдена" in result.summary


# ---------- структура ответа ----------

def test_details_include_source_and_url():
    result = run("С 1 января 2026 года штраф за покупку алкоголя составит 5000 рублей")
    assert result.verdict == Verdict.supports_fake
    assert result.details.get("url", "").startswith("http")
    assert result.details.get("matched_fact")


def test_summary_is_short():
    result = run("СРОЧНО! ЦБ запретил наличные с 1 марта 2026 года!")
    assert len(result.summary) <= 400


def test_kb_has_required_topics():
    kb = load_kb()
    ids = {t["id"] for t in kb["topics"]}
    assert {"kb_cb_key_rate", "kb_cash_ban", "kb_alcohol_fine"} <= ids
