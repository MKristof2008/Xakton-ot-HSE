"""Три уровня проверки под три тарифа.

Эксперт на встрече сказал прямо: разница тарифов — не в «честности»
модели, а в **объёме разбора**. Вердикт одинаковый, различается глубина:

  База (free)  — сырой короткий ответ: вердикт и одна фраза почему.
  Плюс (pro)   — анализ: объяснение, цитата из источника, что проверить.
  Макс (team)  — полный разбор: таблица утверждений, вывод по каждому,
                 что делать и готовая формулировка для пересылки.

Каждый уровень может работать на своей модели — переменные
``LLM_MODEL_BASE``, ``LLM_MODEL_PLUS``, ``LLM_MODEL_MAX``. Если переменная
не задана, берётся общий ``LLM_MODEL``: без настройки всё продолжает
работать одной моделью, различаясь глубиной промпта.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Tier:
    """Профиль одного уровня: модель, размер ответа и глубина промпта."""

    key: str
    #: Переменная окружения с id модели именно для этого уровня.
    model_env: str
    #: Предел токенов ответа: база короче, макс подробнее.
    max_tokens: int
    #: Сколько символов источника отдаём модели.
    source_chars: int
    #: Глубина: verdict | analysis | full
    depth: str
    #: Температура. На всех уровнях 0 — вердикт не должен «гулять».
    temperature: float = 0.0

    def model(self, default: str = "") -> str:
        return (os.environ.get(self.model_env) or default or "").strip()


BASE = Tier(
    key="base",
    model_env="LLM_MODEL_BASE",
    max_tokens=220,
    source_chars=600,
    depth="verdict",
)

PLUS = Tier(
    key="plus",
    model_env="LLM_MODEL_PLUS",
    max_tokens=600,
    source_chars=1200,
    depth="analysis",
)

MAX = Tier(
    key="max",
    model_env="LLM_MODEL_MAX",
    max_tokens=1400,
    source_chars=2000,
    depth="full",
)

#: Тариф в базе → уровень проверки.
_BY_PLAN = {
    "free": BASE,
    "base": BASE,
    "pro": PLUS,
    "plus": PLUS,
    "team": MAX,
    "max": MAX,
}


def for_plan(plan: str | None) -> Tier:
    """Уровень по названию тарифа. Неизвестный тариф = база."""
    return _BY_PLAN.get((plan or "free").strip().lower(), BASE)


#: Подпись уровня для интерфейса и ответа API.
LABELS = {"base": "База", "plus": "Плюс", "max": "Макс"}
