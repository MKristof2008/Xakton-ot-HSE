"""Детерминированные помощники: цифры, отрицания, отбор и обрезка текста.

Ничего не выдумывают и не вызывают модель — только нормализуют текст,
считают пересечения слов и готовят безопасный по размеру контекст.
"""
from __future__ import annotations

import re
from typing import Iterable, Sequence

_WORD_RE = re.compile(r"[0-9a-zа-яё]+", re.IGNORECASE)
_YEAR_RE = re.compile(r"\b(1[89]\d{2}|20\d{2})\b")
_NEG_RE = re.compile(r"\bне\b|\bнет\b|\bникогда\b|\bнельзя\b|отмен|прекрат|опроверг",
                     re.IGNORECASE)

_STOP = frozenset("""
и в во на с со по не что как для от до из за при это этот эта эти был была были было
будет будут все всех всё его её их они она оно или но а же ли то так уже ещё более
менее который которая которые котором чей чья чьи свой своя свои только тоже также
если чтобы чем без под над около после перед через год году года лет месяц месяца
может можно есть да но мы вы ты я он
""".split())


def norm_ws(text: str) -> str:
    """Схлопывает пробелы и обрезает края."""
    return re.sub(r"\s+", " ", text or "").strip()


def years(text: str) -> set[int]:
    """Все четырёхзначные годы в тексте."""
    return {int(m) for m in _YEAR_RE.findall(text or "")}


def numbers(text: str) -> set[str]:
    """Числовые токены, кроме годов."""
    out = set()
    for tok in _WORD_RE.findall(text or ""):
        if tok.isdigit() and len(tok) <= 3:
            out.add(tok)
    return out


def has_negation(text: str) -> bool:
    """Есть ли в тексте отрицание или отмена."""
    return bool(_NEG_RE.search(text or ""))


def content_tokens(text: str) -> set[str]:
    """Значимые слова в грубой нормализации (6-символьный префикс)."""
    out = set()
    for tok in _WORD_RE.findall(text or ""):
        tok = tok.lower()
        if len(tok) < 4 or tok in _STOP or tok.isdigit():
            continue
        out.add(tok[:6])
    return out


def jaccard(left: Iterable[str], right: Iterable[str]) -> float:
    """Пересечение множеств к их объединению."""
    a, b = set(left), set(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def quote_too_short(quote: str) -> bool:
    """Цитата из одного-двух слов ничего не доказывает.

    Год внутри цитаты считаем достаточной конкретикой: в коротких фразах
    вроде «откроют 12 мая 2025 года» значимых слов немного.
    """
    return len(content_tokens(quote)) < 2


def truncate_content(content: str, queries: Sequence[str] = (), limit: int = 4000) -> tuple[str, bool]:
    """Обрезает текст источника, оставляя окно вокруг слов запроса.

    Возвращает (текст, признак обрезки). Признак нужен, чтобы честно
    отметить в ограничениях, что модель видела не весь документ.
    """
    content = content or ""
    if len(content) <= limit:
        return content, False

    low = content.lower()
    cut = None
    for query in queries:
        for token in content_tokens(query):
            idx = low.find(token, 0, limit * 2)
            if idx != -1 and (cut is None or idx < cut):
                cut = idx

    if cut is None:
        return content[:limit].rstrip() + " …", True
    start = max(0, cut - 300)
    return "… " + content[start:start + limit].strip() + " …", True


def select_sources(claims: Sequence, sources: Sequence, limit: int = 6) -> list:
    """Отбирает до `limit` уже полученных источников по лексическому пересечению.

    Это не поиск: список приходит от backend, функция только упорядочивает
    и сокращает его, чтобы не переполнить контекст модели.
    """
    sources = list(sources)
    if len(sources) <= limit:
        return sources

    terms: set[str] = set()
    for claim in claims:
        terms |= content_tokens(getattr(claim, "text", ""))
        for query in getattr(claim, "queries", []) or []:
            terms |= content_tokens(query)

    scored = []
    for index, source in enumerate(sources):
        hay = content_tokens(f"{source.title} {source.content}")
        scored.append((-len(terms & hay), index, source))
    scored.sort(key=lambda item: (item[0], item[1]))
    return [source for _, _, source in sorted(scored[:limit], key=lambda item: item[1])]
