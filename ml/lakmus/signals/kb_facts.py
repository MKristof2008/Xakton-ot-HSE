"""Проверка утверждений по курируемой базе фактов — без модели.

Сигнал T2 в офлайн-режиме: модель недоступна, поэтому утверждения ищутся
по ключевым темам в ``data/kb_facts.json``, а числа и даты сверяются
детерминированно. Это честная проверка на ограниченной базе, а не
имитация полноценного поиска: чего нет в базе — помечается как
непроверенное, а не додумывается.

Вердикты:
  supports_real   — утверждение совпало с записью базы;
  supports_fake   — база прямо опровергает (запись с verdict=false_claim);
  neutral         — тема найдена, но подтвердить или опровергнуть нельзя;
  unavailable     — база не загружена или тема не найдена.
"""

from __future__ import annotations

import json
import pathlib
import re
from typing import Any, Optional

from ..context import CheckContext
from ..schemas import InputType, Stage, Verdict
from .base import BaseSignal, make_result

KB_PATH = pathlib.Path(__file__).resolve().parents[1] / "data" / "kb_facts.json"

RELIABILITY_MATCH = 0.9      # совпадение с курируемой записью и её первоисточником
RELIABILITY_REFUTE = 0.9     # прямое опровержение курируемой записью
RELIABILITY_TOPIC = 0.35     # тема найдена, но без сверки

#: Допуск при сравнении чисел: «21%» и «21,00%» — одно и то же.
NUMBER_TOLERANCE = 0.005


class KbError(RuntimeError):
    """База не читается — сигнал вернёт unavailable."""


def load_kb(path: Any = None) -> dict[str, Any]:
    """Читает базу фактов. Бросает KbError с понятной причиной."""
    target = pathlib.Path(path) if path else KB_PATH
    if not target.is_file():
        raise KbError(f"база фактов не найдена: {target}")
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise KbError(f"база фактов не читается: {type(exc).__name__}") from exc


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().lower().replace("ё", "е")


def _numbers(text: str) -> set[float]:
    """Все числа из текста: «21%», «21,00», «5 000» → 21.0, 21.0, 5000.0."""
    out: set[float] = set()
    for raw in re.findall(r"\d[\d\s]*(?:[.,]\d+)?", text or ""):
        cleaned = raw.replace(" ", "").replace(",", ".")
        try:
            out.add(round(float(cleaned), 3))
        except ValueError:
            continue
    return out


def _numbers_agree(a: set[float], b: set[float]) -> Optional[bool]:
    """True — все числа утверждения есть в записи, False — хоть одно расходится.

    Сравниваем как подмножество, а не «любая пара совпала»: иначе «ставка
    15%» проходит проверку из-за совпавшего числа «25» (день месяца).
    """
    if not a or not b:
        return None
    for x in a:
        if not any(y and abs(x - y) / max(abs(y), 1e-9) <= NUMBER_TOLERANCE for y in b):
            return False
    return True


def _content_numbers(text: str) -> set[float]:
    """Числа, которые несут смысл: годы и дни месяца не в счёт.

    Год проверяется отдельно (_years), а день месяца совпадает почти
    всегда и только маскирует расхождение в главной цифре.
    """
    out: set[float] = set()
    for value in _numbers(text):
        if 1900 <= value <= 2100:
            continue  # год — отдельная проверка
        if value == int(value) and 1 <= value <= 31 and "." not in str(value):
            continue  # похоже на день месяца
        out.add(value)
    return out


def _years(text: str) -> set[int]:
    return {int(y) for y in re.findall(r"\b(19\d{2}|20\d{2})\b", text or "")}


def find_topic(kb: dict[str, Any], text: str) -> Optional[dict[str, Any]]:
    """Тема по ключевым словам. Берём тему с самым длинным совпавшим словом."""
    low = _norm(text)
    best: Optional[dict[str, Any]] = None
    best_len = 0
    for topic in kb.get("topics", []):
        for keyword in topic.get("keywords", []):
            k = _norm(keyword)
            if k and k in low and len(k) > best_len:
                best, best_len = topic, len(k)
    return best


def check_against_topic(topic: dict[str, Any], text: str) -> tuple[Verdict, float, str, dict[str, Any]]:
    """Сверка текста с записями темы.

    Возвращает (вердикт, сила, объяснение, детали).
    """
    facts = topic.get("facts", [])
    refuted = [f for f in facts if f.get("verdict") == "false_claim"]
    confirmed = [f for f in facts if f.get("verdict") == "true"]

    # 1. Прямое опровержение: база говорит, что такого нет.
    if refuted:
        fact = refuted[0]
        return (
            Verdict.supports_fake,
            RELIABILITY_REFUTE,
            f"База фактов опровергает: {fact['claim']}.",
            {
                "topic": topic["topic"],
                "matched_fact": fact,
                "reason": "refuted",
                "source": fact.get("source"),
                "url": fact.get("url"),
            },
        )

    # 2. Подтверждение с сверкой чисел и годов.
    if confirmed:
        fact = confirmed[0]
        claim_numbers = _content_numbers(text)
        fact_numbers = _content_numbers(str(fact.get("value", "")) + " " + fact["claim"])
        agree = _numbers_agree(claim_numbers, fact_numbers)

        claim_years = _years(text)
        fact_years = _years(fact.get("date", "") + " " + fact["claim"])
        year_ok = not claim_years or not fact_years or bool(claim_years & fact_years)

        if agree is False:
            return (
                Verdict.supports_fake,
                RELIABILITY_REFUTE,
                f"Число в сообщении не совпадает с базой: {fact['claim']}.",
                {
                    "topic": topic["topic"],
                    "matched_fact": fact,
                    "reason": "number_mismatch",
                    "claim_numbers": sorted(claim_numbers),
                    "fact_numbers": sorted(fact_numbers),
                    "source": fact.get("source"),
                    "url": fact.get("url"),
                },
            )

        if agree and year_ok:
            return (
                Verdict.supports_real,
                RELIABILITY_MATCH,
                f"Совпадает с базой: {fact['claim']}.",
                {
                    "topic": topic["topic"],
                    "matched_fact": fact,
                    "reason": "matched",
                    "source": fact.get("source"),
                    "url": fact.get("url"),
                },
            )

        return (
            Verdict.neutral,
            RELIABILITY_TOPIC,
            f"Тема найдена ({topic['topic']}), но числа или даты не сверены: {fact['claim']}.",
            {
                "topic": topic["topic"],
                "matched_fact": fact,
                "reason": "partial",
                "source": fact.get("source"),
                "url": fact.get("url"),
            },
        )

    return (
        Verdict.neutral,
        RELIABILITY_TOPIC,
        f"Тема найдена ({topic['topic']}), записей для сверки нет.",
        {"topic": topic["topic"], "reason": "topic_only"},
    )


class KbFactsSignal(BaseSignal):
    """Сверка утверждений с курируемой базой фактов (офлайн, без модели)."""

    id = "kb_facts"
    name = "Сверка с базой фактов"
    stage = Stage.sources
    timeout_s = 5.0

    async def run(self, ctx: CheckContext) -> Any:
        if ctx.input.type == InputType.image:
            return self.unavailable("сигнал работает с текстом, а не с изображением")

        text = (ctx.text or ctx.input.extracted_text or "").strip()
        if len(text) < 12:
            return self.unavailable("текст слишком короткий для сверки")

        try:
            kb = load_kb(ctx.options.get("kb_path"))
        except KbError as exc:
            return self.unavailable(str(exc))

        topic = find_topic(kb, text)
        if topic is None:
            return make_result(
                self, Verdict.unavailable, 0.0, 0.0,
                "Темы нет в базе фактов — утверждение не проверено. "
                "Это не значит, что оно ложное.",
                {"reason": "topic_not_found", "topics_in_kb": len(kb.get("topics", []))},
            )

        verdict, reliability, summary, details = check_against_topic(topic, text)
        strength = reliability  # сила равна надёжности: совпадение — единственный довод
        return make_result(self, verdict, strength, reliability, summary, details)
