"""Три уровня проверки: база, плюс, макс.

Эксперт на встрече: «не экономьте на модели ради репутации — разница
тарифов в объёме объяснения, а не в качестве вердикта». Эти тесты
держат именно это правило:

  * уровень выбирается по тарифу пользователя;
  * модель на уровень можно задать отдельной переменной;
  * база просит короткий ответ, плюс — разбор, макс — полный;
  * вердикт не зависит от уровня, а разбор — зависит;
  * кэш не отдаёт короткий ответ базы пользователю с плюсом.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent / "backend"))

from lakmus import tariffs  # noqa: E402
from lakmus.tariffs import BASE, MAX, PLUS, for_plan  # noqa: E402


def test_plan_maps_to_level():
    assert for_plan("free") is BASE
    assert for_plan("pro") is PLUS
    assert for_plan("team") is MAX
    assert for_plan("max") is MAX


def test_unknown_plan_falls_back_to_base():
    assert for_plan("что-то") is BASE
    assert for_plan(None) is BASE
    assert for_plan("") is BASE


def test_levels_grow_in_depth():
    """Каждый следующий уровень отдаёт модели больше контекста и токенов."""
    assert BASE.max_tokens < PLUS.max_tokens < MAX.max_tokens
    assert BASE.source_chars < PLUS.source_chars < MAX.source_chars
    assert BASE.depth != PLUS.depth != MAX.depth


def test_model_per_level_from_env(monkeypatch):
    monkeypatch.setenv("LLM_MODEL_BASE", "model-cheap")
    monkeypatch.setenv("LLM_MODEL_PLUS", "model-mid")
    monkeypatch.setenv("LLM_MODEL_MAX", "model-best")
    assert BASE.model("fallback") == "model-cheap"
    assert PLUS.model("fallback") == "model-mid"
    assert MAX.model("fallback") == "model-best"


def test_missing_level_model_uses_shared_default(monkeypatch):
    """Без отдельных переменных всё работает одной моделью — без падения."""
    for var in ("LLM_MODEL_BASE", "LLM_MODEL_PLUS", "LLM_MODEL_MAX"):
        monkeypatch.delenv(var, raising=False)
    assert BASE.model("shared") == "shared"
    assert MAX.model("shared") == "shared"


def test_depth_prompt_differs_by_level():
    from lakmus.llm_pipeline import _depth_suffix

    base_prompt = _depth_suffix(BASE)
    plus_prompt = _depth_suffix(PLUS)
    max_prompt = _depth_suffix(MAX)

    assert base_prompt != plus_prompt != max_prompt
    # База не просит разбора, макс просит готовую пересылку.
    assert "resend" not in base_prompt
    assert "resend" in max_prompt
    assert "action" in plus_prompt


@pytest.mark.asyncio
async def test_evaluate_returns_action_only_above_base(monkeypatch):
    """Вердикт одинаков, но «что делать» появляется с плюса."""
    from lakmus import llm_pipeline

    answer = (
        '{"status":"contradicted","quote":"нет такого решения",'
        '"explanation":"Источник опровергает.","action":"Не пересылайте.",'
        '"resend":"Это фейк: ЦБ не запрещал наличные."}'
    )

    async def fake_post(system, user, timeout=30, tier=None):
        return answer

    monkeypatch.setenv("LLM_API_KEY", "test")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.invalid")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    monkeypatch.setattr(llm_pipeline, "_post", fake_post)

    base = await llm_pipeline.evaluate_one_with_llm("ЦБ запретил наличные", [], BASE)
    plus = await llm_pipeline.evaluate_one_with_llm("ЦБ запретил наличные", [], PLUS)
    top = await llm_pipeline.evaluate_one_with_llm("ЦБ запретил наличные", [], MAX)

    # Вердикт на всех уровнях один и тот же.
    assert base["status"] == plus["status"] == top["status"] == "contradicted"
    # Разбор — разный.
    assert "action" not in base
    assert plus["action"]
    assert top["resend"]


def test_cache_key_separates_levels():
    """Плюс не должен получить короткий ответ, сохранённый базой."""
    from lakmus.full_pipeline import _cache_key

    text = "ЦБ запретил наличные с 1 марта"
    assert _cache_key(text, BASE.key) != _cache_key(text, PLUS.key)
    assert _cache_key(text, PLUS.key) != _cache_key(text, MAX.key)
