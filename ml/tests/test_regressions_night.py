"""Регрессы, найденные при разборе ночной работы (14 ноября).

Каждый тест соответствует конкретному дефекту, который был в main.
"""

from __future__ import annotations

import asyncio

import pytest

from lakmus.full_pipeline import _CACHE, _is_future, _is_vague, run_check
from lakmus.signals.kb_facts import check_against_topic, find_topics, load_kb


@pytest.fixture(autouse=True)
def _clear_cache():
    _CACHE.clear()
    yield
    _CACHE.clear()


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    """Без ключа модели: тесты не должны ходить в живую LLM.

    backend.main подхватывает ml/.env, и если там лежит LLM_API_KEY,
    пайплайн отвечает через модель — недетерминированно и по сети.
    """
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)


# --- 1. Защиты от vague/future не работали -------------------------------

def test_future_claim_is_not_refuted():
    """«Мобилизацию объявят» — прогноз, базу нельзя ставить в опровержение."""
    outcome = asyncio.run(run_check("Мобилизацию объявят со следующей недели."))
    assert outcome.verdict != "фейк", "прогноз о будущем не может быть фейком"


def test_vague_claim_is_not_confirmed():
    """«Компания X купила Y» — проверить нельзя, но и не фейк."""
    outcome = asyncio.run(run_check("Компания X купила компанию Y за 5 млрд рублей."))
    assert outcome.verdict == "непонятно"


def test_regex_patterns_contain_no_control_chars():
    """В регулярки однажды попал литеральный backspace — они не совпадали ни с чем."""
    import pathlib

    src = pathlib.Path(__file__).resolve().parents[1] / "lakmus" / "full_pipeline.py"
    assert b"\x08" not in src.read_bytes()


def test_guards_detect_their_cases():
    assert _is_vague("Компания X купила Y")
    assert not _is_vague("Компания «Ромашка» купила «Лютик»")
    assert _is_future("Завтра ожидается снег")
    assert not _is_future("Вчера открыли мост")


# --- 2. Любое упоминание темы давало «правда» ----------------------------

@pytest.mark.parametrize(
    "text",
    [
        "Что там по МРОТ?",
        "Слышал про ключевую ставку, что скажешь?",
        "Проверь вот эту новость про ставку ЦБ пожалуйста",
    ],
)
def test_topic_mention_is_not_a_confirmation(text):
    """Раньше любое упоминание темы возвращало supports_real."""
    outcome = asyncio.run(run_check(text))
    assert outcome.verdict != "правда", f"«{text}» не утверждает факт, подтверждать нечего"


def test_real_fact_still_confirmed():
    outcome = asyncio.run(run_check("МРОТ с 1 января 2025 года — 22 440 рублей."))
    assert outcome.verdict == "правда"


# --- 3. Падежные формы не находили тему ----------------------------------

@pytest.mark.parametrize(
    "text",
    [
        "Мобилизацию объявят с 1 сентября.",
        "Мобилизация начнётся с 1 сентября.",
        "Объявлена всеобщая мобилизация.",
    ],
)
def test_case_forms_find_topic(text):
    kb = load_kb()
    assert find_topics(kb, text), f"тема не найдена для «{text}»"


def test_topic_requires_all_keyword_words():
    """Ключ «ставка цб» не должен срабатывать на «ставка выросла»."""
    kb = load_kb()
    topics = find_topics(kb, "Ставка выросла до 50%")
    assert not any("ЦБ" in t["topic"] for t in topics)


def test_every_kb_fact_confirms_its_own_wording():
    """Все true-факты базы должны подтверждаться своей же формулировкой."""
    kb = load_kb()
    for topic in kb["topics"]:
        for fact in topic["facts"]:
            if fact.get("verdict") != "true":
                continue
            verdict, _, _, details = check_against_topic(topic, fact["claim"])
            assert verdict.value == "supports_real", (
                f"факт «{fact['claim'][:50]}» не подтверждается: "
                f"{verdict.value} / {details.get('reason')}"
            )


# --- 4. Кэш игнорировал url ----------------------------------------------

def test_cache_separates_different_urls():
    """Проверка присланной ссылки не должна отдавать результат без источников."""
    text = "Учёные доказали что вода кипит при 100 градусах"
    a = asyncio.run(run_check(text))
    b = asyncio.run(run_check(text, url="https://ru.wikipedia.org/wiki/Вода"))
    assert a is not b, "разные url — разные прогоны, кэш не должен склеивать"
