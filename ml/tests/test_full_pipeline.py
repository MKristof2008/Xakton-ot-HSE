"""Тесты полного пайплайна: извлечение, источники, оценка, валидация.

Проверяем то, что защищает от вранья: цитата, которой нет в источнике,
обязана понижать вердикт; отсутствие источников — давать «не проверено»,
а не «фейк»; SSRF-фильтр не пускает на локальные адреса.
"""

from __future__ import annotations

import asyncio

import pytest

from lakmus.full_pipeline import (
    _content_numbers,
    _is_negated,
    _level_for,
    _quote_in_source,
    ClaimFinding,
    extract_offline,
    judge_offline,
    llm_enabled,
    run_check,
)
from lakmus.sources import (
    CatalogProvider,
    FetchedSource,
    LocalKbProvider,
    NullProvider,
    _is_private_host,
    domain_of,
    is_trusted,
)


def run(text: str, **kwargs):
    return asyncio.run(run_check(text, **kwargs))


# ------------------------------------------------------------ извлечение

def test_extract_finds_sentences_with_numbers():
    claims = extract_offline("ЦБ поднял ставку до 21% годовых. Погода хорошая.")
    assert any("21%" in c for c in claims)


def test_extract_skips_empty_text():
    assert extract_offline("") == []


def test_extract_limits_to_three():
    text = " ".join(f"Штраф вырастет до {i}00 рублей." for i in range(1, 8))
    assert len(extract_offline(text)) <= 3


# ------------------------------------------------------------ источники

def test_private_hosts_blocked():
    assert _is_private_host("http://localhost:8000/api")
    assert _is_private_host("http://127.0.0.1/admin")
    assert _is_private_host("http://192.168.1.1/")
    assert _is_private_host("http://169.254.169.254/latest/meta-data")
    assert _is_private_host("http://10.0.0.5/")


def test_public_hosts_allowed():
    assert not _is_private_host("https://www.cbr.ru/press/")
    assert not _is_private_host("https://tass.ru/article")


def test_trusted_domains():
    assert is_trusted("https://www.cbr.ru/press/")
    assert is_trusted("https://cbr.ru/")
    assert not is_trusted("https://example.com/post")


def test_domain_of():
    assert domain_of("https://www.cbr.ru/press/") == "cbr.ru"
    assert domain_of("not a url") == ""


def test_local_kb_provider_finds_topic():
    provider = LocalKbProvider()
    found = asyncio.run(provider.find("ЦБ поднял ключевую ставку"))
    assert found
    assert "Банк России" in found[0].content or "ставку" in found[0].content.lower()


def test_local_kb_provider_returns_empty_for_unknown():
    provider = LocalKbProvider()
    # «погода в Сочи» — есть тема про погоду, поэтому берём то, чего в базе
    # точно нет: рецепт или имя.
    assert asyncio.run(provider.find("рецепт борща с пампушками")) == []


def test_null_provider_returns_nothing():
    assert asyncio.run(NullProvider().find("что угодно")) == []


# ------------------------------------------------------------ валидация

def test_quote_must_be_verbatim():
    assert _quote_in_source("Банк России не принимал решений", "банк россии не принимал решений о запрете")
    assert not _quote_in_source("Банк России запретил наличные", "банк россии не принимал решений")


def test_quote_normalizes_quotes_and_dashes():
    assert _quote_in_source("«запрет» — не принимался", "запрет - не принимался")


def test_short_quote_rejected():
    assert not _quote_in_source("да", "да, это правда")


# ------------------------------------------------------------ числа

def test_content_numbers_skip_years_and_days():
    nums = _content_numbers("25 октября 2024 года ставка 21%")
    assert 21.0 in nums
    assert 2024 not in nums


def test_negation_detected():
    assert _is_negated("ЦБ не запрещал наличные")
    assert not _is_negated("ЦБ запретил наличные")


# ------------------------------------------------------------ уровень

def test_level_all_supported():
    """Подтверждение с цитатой и доверенным источником — высокий балл.

    Балл теперь считается по рубрике, поэтому проверяем именно полный
    набор доказательств: без них вердикт тот же, но цифра честно низкая
    (см. test_level_supported_without_evidence_is_low).
    """
    finding = ClaimFinding(
        text="a", status="supported", quote="дословная цитата", trusted=True
    )
    level, verdict, score, _ = _level_for(
        [finding], sources=2, trusted=1, searched=True
    )
    assert (level, verdict) == ("likely_real", "правда")
    assert score >= 70


def test_level_supported_without_evidence_is_low():
    """«Правда» без цитаты и источников не может давать высокую уверенность."""
    level, verdict, score, _ = _level_for(
        [ClaimFinding(text="a", status="supported")]
    )
    assert (level, verdict) == ("likely_real", "правда")
    assert score < 50


def test_level_all_contradicted():
    finding = ClaimFinding(
        text="a", status="contradicted", quote="источник отрицает", trusted=True
    )
    level, verdict, score, _ = _level_for(
        [finding], sources=2, trusted=1, searched=True
    )
    assert (level, verdict) == ("likely_fake", "фейк")
    assert score <= 40


def test_level_conflict_is_fog():
    findings = [
        ClaimFinding(text="a", status="supported"),
        ClaimFinding(text="b", status="contradicted"),
    ]
    level, verdict, _, uncertainty = _level_for(findings)
    assert level == "fog"
    assert verdict == "непонятно"
    assert uncertainty >= 0.5


def test_level_empty_is_fog():
    assert _level_for([])[0] == "fog"


# ------------------------------------------------------------ сквозные

def test_known_fake_is_detected():
    result = run("СРОЧНО! ЦБ запретил наличные с 1 марта 2026 года! Перешли всем!")
    assert result.verdict == "фейк"
    assert result.claims


def test_known_true_is_confirmed():
    result = run("ЦБ поднял ключевую ставку до 21% годовых 25 октября 2024 года.")
    assert result.verdict == "правда"


def test_unknown_topic_is_not_fake():
    """Главное: чего нет в источниках — «непонятно», а не «фейк»."""
    # Текст намеренно не из базы фактов и без признаков жанра фейка:
    # проверяем именно честное «не знаю».
    result = run("Вчера в Крыму видели стаю диких уток.")
    assert result.verdict == "непонятно"
    assert result.claims[0].status == "insufficient"


def test_empty_message_reports_no_claims():
    result = run("   ")
    assert result.verdict == "непонятно"
    assert any("нет проверяемых" in l.lower() for l in result.limitations)


def test_llm_disabled_without_env(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    assert llm_enabled() is False


def test_llm_enabled_with_env(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "x")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.org")
    assert llm_enabled() is True


def test_offline_mode_reported(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    result = run("ЦБ поднял ключевую ставку до 21% годовых")
    assert result.mode == "offline"


def test_judge_offline_without_sources_is_insufficient():
    finding = judge_offline("Ставка выросла до 50%", [])
    assert finding.status == "insufficient"
    assert finding.limitations


def test_pipeline_returns_duration():
    result = run("ЦБ поднял ключевую ставку до 21% годовых")
    assert result.duration_ms >= 0


def test_result_serializes():
    result = run("ЦБ поднял ключевую ставку до 21% годовых")
    data = result.as_dict()
    assert set(data) >= {"claims", "verdict", "level", "score", "mode"}
    assert isinstance(data["claims"], list)
