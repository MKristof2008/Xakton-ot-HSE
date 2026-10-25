"""Текстовые помощники сигналов «Лакмуса».

Нормализация, значимые слова и годы берутся из готового ml/doreposta/checks,
чтобы правила совпадали с пайплайном «До репоста», а не расходились с ним.
Импорт с запасным путём: пакет ml виден и как `doreposta`, и как `ml.doreposta`.
"""

from __future__ import annotations

import re

try:  # обычный запуск: ml/ лежит в sys.path
    from doreposta import checks as _checks
except ModuleNotFoundError:  # импорт как ml.lakmus.signals...
    from ml.doreposta import checks as _checks

norm_ws = _checks.norm_ws
content_tokens = _checks.content_tokens
jaccard = _checks.jaccard
has_negation = _checks.has_negation
years = _checks.years
numbers = _checks.numbers

_DIGITS = re.compile(r"\d+(?:[.,]\d+)?")
_URL = re.compile(r"https?://|www\.", re.IGNORECASE)
_WORDS = re.compile(r"[0-9a-zа-яё]+", re.IGNORECASE)


def digits(text: str) -> set[str]:
    """Все числа текста, включая даты и проценты (у content_tokens их нет)."""
    return {m.group(0).rstrip(".,") for m in _DIGITS.finditer(text or "") if m.group(0)}


def token_set(text: str) -> set[str]:
    """Значимые слова плюс числа и годы — мера покрытия утверждения материалом."""
    return content_tokens(text) | digits(text) | {str(year) for year in years(text)}


def words(text: str) -> list[str]:
    """Слова в нижнем регистре — для счётчиков и лексического разнообразия."""
    return [w.lower() for w in _WORDS.findall(text or "")]


def fold(text: str) -> str:
    """Строка без лишних пробелов и в нижнем регистре — для дословных сравнений."""
    return norm_ws(text or "").casefold()


def contains_verbatim(haystack: str, needle: str) -> bool:
    """Дословное вхождение с точностью до регистра и пробелов."""
    target = fold(needle)
    return bool(target) and target in fold(haystack)


def has_link(text: str) -> bool:
    """Есть ли в тексте ссылка."""
    return bool(_URL.search(text or ""))


def coverage(claim_text: str, doc_tokens: set[str]) -> float:
    """Доля значимых слов и чисел утверждения, найденных в материале."""
    tokens = token_set(claim_text)
    if not tokens or not doc_tokens:
        return 0.0
    return len(tokens & doc_tokens) / len(tokens)
