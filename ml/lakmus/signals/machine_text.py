"""T5. Признаки машинного текста (раздел 6.7 ТЗ).

Честная рамка: по стилю отличить машинный текст от человеческого нельзя
надёжно. Поэтому сигнал даёт только слабые статистические подсказки и
минимальную надёжность (0.05), а вердикт всегда neutral.

Считаем то, что видно без модели и без словарей:
  * burstiness — разброс длины предложений (у людей он выше);
  * type-token ratio — лексическое разнообразие;
  * длину текста: на коротком тексте статистика ничего не значит.

Perplexity не считается: для неё нужна языковая модель, которой у сигнала нет.
Значение поля остаётся текстом, чтобы не выглядело как настоящая метрика.
"""

from __future__ import annotations

import math
import re
from typing import Any

from .. import textutil
from ..context import CheckContext
from ..schemas import SignalResult, Stage, Verdict
from .base import BaseSignal, make_result

MIN_WORDS = 40
MIN_SENTENCES = 5
BURSTINESS_HINT = 0.35
TTR_HINT = 0.45
WEAK_STRENGTH = 0.05
WEAK_RELIABILITY = 0.05

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?…])\s+")


def _sentences(text: str) -> list[str]:
    return [part for part in _SENTENCE_SPLIT.split(text or "") if part.strip()]


def analyse(text: str) -> dict[str, Any]:
    """Статистика текста: длина предложений, разброс, разнообразие слов."""
    sentences = _sentences(text)
    counts = [len(textutil.words(sentence)) for sentence in sentences]
    counts = [count for count in counts if count > 0]
    tokens = textutil.words(text)

    mean = sum(counts) / len(counts) if counts else 0.0
    spread = (
        math.sqrt(sum((count - mean) ** 2 for count in counts) / len(counts))
        if counts else 0.0
    )
    burstiness = (spread / mean) if mean else 0.0
    ttr = (len(set(tokens)) / len(tokens)) if tokens else 0.0

    return {
        "burstiness": round(burstiness, 3),
        "mean_sentence_words": round(mean, 2),
        "type_token_ratio": round(ttr, 3),
        "sentences": len(sentences),
        "words": len(tokens),
    }


def hints_for(stats: dict[str, Any]) -> list[str]:
    """Слабые подсказки; на коротком тексте не выдаются вовсе."""
    if stats["words"] < MIN_WORDS:
        return []
    hints: list[str] = []
    if stats["burstiness"] < BURSTINESS_HINT and stats["sentences"] >= MIN_SENTENCES:
        hints.append("предложения почти одинаковой длины — у людей разброс выше")
    if stats["type_token_ratio"] < TTR_HINT:
        hints.append("низкое лексическое разнообразие")
    return hints


class MachineTextSignal(BaseSignal):
    """T5: слабые признаки машинного текста, без приговора."""

    id = "machine_text"
    name = "Машинный текст"
    stage = Stage.artifacts
    timeout_s = 3.0

    async def run(self, ctx: CheckContext) -> SignalResult:
        text = (ctx.text or "").strip()
        if not text:
            return self.unavailable("нет текста: признаки машинной генерации искать не в чем")

        stats = analyse(text)
        hints = hints_for(stats)
        details = {
            **stats,
            "perplexity": "недоступна: нужна языковая модель",
            "hints": hints,
            "note": (
                "Статистика стиля — слабая подсказка: детекторы ИИ часто ошибаются "
                "и на человеческих текстах, и на отредактированных машинных."
            ),
        }
        if stats["words"] < MIN_WORDS:
            summary = (
                f"Текст короче {MIN_WORDS} слов — статистика стиля ненадёжна, "
                "вывод о машинной генерации не делается."
            )
        elif hints:
            summary = (
                f"Слабые признаки машинного текста: {len(hints)}. "
                "Это не доказательство — детекторы ИИ часто ошибаются."
            )
        else:
            summary = "Явных признаков машинного текста нет; по стилю такой вывод не делается."

        return make_result(
            self, Verdict.neutral,
            WEAK_STRENGTH if hints else 0.0,
            WEAK_RELIABILITY,
            summary,
            details,
        )


__all__ = ["MachineTextSignal", "analyse", "hints_for"]
