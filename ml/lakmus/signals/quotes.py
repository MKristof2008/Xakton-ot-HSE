"""T3. Точные цитаты и их дословность (раздел 6.6 ТЗ).

Сигнал ищет в тексте оформленные кавычками цитаты и проверяет, встречается ли
они дословно в найденных материалах. Доказательная сила здесь ограничена:
найденная дословная цитата подтверждает, что цитата существует, но не то, что
её правильно поняли. Ненайденная цитата — повод искать дальше, а не приговор:
поиск не видит закрытых источников, а короткие фразы гуглятся плохо.

Поэтому «цитата нигде не найдена» даёт neutral с нулевой силой, а не
supports_fake. Совпадение только со сниппетом считается слабым: сниппет —
это текст поисковика, а не страница.

Промпт ml/prompts/t3_quote.md фиксирует правила для человека, код его не
вызывает: здесь всё решается строковым сравнением.
"""

from __future__ import annotations

import re
from typing import Any, Sequence

from .. import textutil
from ..context import CheckContext
from ..schemas import SignalResult, Stage, Verdict
from .base import BaseSignal, make_result

MIN_QUOTE_CHARS = 12
MAX_QUOTE_CHARS = 400
MAX_QUOTES = 5
QUERY_WORDS = 10

#: Разные типографики кавычек: «ёлочки», „немецкие“, “английские”, "прямые".
_QUOTE_PATTERNS = (
    re.compile(r"«([^«»]{12,400})»"),
    re.compile(r"„([^„“\"]{12,400})[\"“]"),
    re.compile(r"“([^“”]{12,400})”"),
    re.compile(r"\"([^\"\n]{12,400})\""),
)


def _attr(item: Any, name: str, default: Any = "") -> Any:
    if isinstance(item, dict):
        return item.get(name, default)
    return getattr(item, name, default)


def extract_quotes(text: str) -> list[dict[str, Any]]:
    """Цитаты из текста: длиной от MIN_QUOTE_CHARS, без повторов, по порядку."""
    source = text or ""
    found: list[dict[str, Any]] = []
    for pattern in _QUOTE_PATTERNS:
        for match in pattern.finditer(source):
            quote = textutil.norm_ws(match.group(1))
            if len(quote) < MIN_QUOTE_CHARS:
                continue
            found.append({"quote": quote[:MAX_QUOTE_CHARS], "start": match.start(1)})

    found.sort(key=lambda item: item["start"])
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in found:
        key = textutil.fold(item["quote"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
        if len(unique) >= MAX_QUOTES:
            break
    return unique


def _query_for(quote: str) -> str:
    return " ".join(quote.split()[:QUERY_WORDS])


def _hit_body(hit: Any) -> str:
    title = textutil.norm_ws(str(_attr(hit, "title") or ""))
    body = textutil.norm_ws(str(_attr(hit, "content") or ""))
    return f"{title}. {body}".strip(". ") if title else body


async def _check_quote(ctx: CheckContext, quote: str) -> dict[str, Any]:
    """Ищет цитату дословно; snippet — слабое совпадение."""
    provider = ctx.search
    result: dict[str, Any] = {
        "quote": quote,
        "query": _query_for(quote),
        "found": False,
        "verbatim": False,
        "source_ids": [],
        "domain": "",
        "strong": False,
        "error": None,
    }
    if provider is None:
        return result

    try:
        hits = list(await provider.search(result["query"]) or [])
    except Exception as exc:  # поисковик упал — цитата остаётся непроверенной
        result["error"] = f"{type(exc).__name__}"
        return result

    for hit in hits:
        if not textutil.contains_verbatim(_hit_body(hit), quote):
            continue
        result["found"] = True
        result["verbatim"] = True
        if not bool(_attr(hit, "snippet", False)):
            result["strong"] = True
        source_id = str(_attr(hit, "id") or "")
        if source_id and source_id not in result["source_ids"]:
            result["source_ids"].append(source_id)
        if not result["domain"]:
            domain = str(_attr(hit, "domain") or "")
            result["domain"] = domain or str(_attr(hit, "url") or "")
    return result


class QuotesSignal(BaseSignal):
    """T3: дословность цитат, оформленных кавычками."""

    id = "quotes"
    name = "Точные цитаты"
    stage = Stage.sources
    timeout_s = 10.0

    async def run(self, ctx: CheckContext) -> SignalResult:
        text = (ctx.text or "").strip()
        if not text:
            return self.unavailable("нет текста: искать цитаты не в чем")
        if ctx.search is None:
            return self.unavailable("нет поиска: не с чем сверять цитаты")

        quotes = extract_quotes(text)
        if not quotes:
            return make_result(
                self, Verdict.neutral, 0.0, 0.0,
                "Точных цитат в тексте нет — проверять дословность нечего.",
                {"quotes": [], "found": 0, "missing_quotes": [], "searched": 0,
                 "search_errors": []},
            )

        checked = [await _check_quote(ctx, item["quote"]) for item in quotes]
        found = [item for item in checked if item["found"]]
        missing = [item for item in checked if not item["found"]]
        details = {
            "quotes": checked,
            "found": len(found),
            "missing_quotes": [item["quote"] for item in missing],
            "searched": len(checked),
            "search_errors": [item["error"] for item in checked if item["error"]],
        }

        if not found:
            return make_result(
                self, Verdict.neutral, 0.0, 0.3,
                f"Цитата нигде не найдена ({len(missing)} из {len(checked)}): "
                "это не доказывает подделку — поиск мог просто не увидеть источник.",
                details,
            )

        strong = [item for item in found if item["strong"]]
        domains = sorted({item["domain"] for item in found if item["domain"]})
        source_note = f" Источники: {', '.join(domains[:3])}." if domains else ""
        if strong:
            return make_result(
                self, Verdict.supports_real, 0.5, 0.65,
                f"Цитаты найдены дословно: {len(strong)} из {len(checked)}. "
                f"Дословность подтверждена, смысл ещё нужно читать в контексте.{source_note}",
                details,
            )
        return make_result(
            self, Verdict.supports_real, 0.35, 0.4,
            f"Цитаты нашлись только в сниппетах поиска: {len(found)} из {len(checked)}. "
            f"Сниппет — слабое совпадение, страницу нужно открыть.{source_note}",
            details,
        )


__all__ = ["QuotesSignal", "extract_quotes"]
