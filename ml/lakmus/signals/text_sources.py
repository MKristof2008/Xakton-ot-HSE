"""T2. Сверка утверждений с источниками (раздел 6.5 ТЗ).

Правила детерминированные и прозрачные: решение «подтверждает / опровергает /
не найдено» принимает код, а не модель. Модель нужна только на шаге T1 —
она выделяет утверждения и запросы (TextClaimsSignal).

Что считается доказательством:
  * покрытие утверждения материалом не ниже COVER_CONFIRM;
  * противоречие — расхождение по отрицанию или по годам;
  * перепечатки одного текста (jaccard >= REPRINT_JACCARD) — один документ,
    иначе сеть перепостов выглядела бы как независимое подтверждение;
  * домены делятся на ярусы DOMAIN_TIERS: первоисточники и агентства
    весят больше, перепечатки и соцсети — меньше.

Материалов нет — сигнал честно возвращает neutral с нулевой силой:
«не искали» и «не нашли» не должны выглядеть как «опровергнуто».

Промпт ml/prompts/t2_sources.md фиксирует те же правила для человека,
код его не вызывает.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Sequence

from pydantic import ValidationError

from .. import textutil
from ..context import CheckContext
from ..schemas import SignalResult, Stage, Verdict
from .base import BaseSignal, make_result
from .text_claims import ClaimItem, ClaimsError, extract_claims

MAX_QUERIES_PER_CLAIM = 2
COVER_CONFIRM = 0.6
REPRINT_JACCARD = 0.85
MAX_SOURCES_IN_SUMMARY = 3

_TIER1 = frozenset({
    # государственные и международные первоисточники
    "government.ru", "kremlin.ru", "mid.ru", "mil.ru", "cbr.ru", "mos.ru",
    "nalog.gov.ru", "rostrud.gov.ru", "mchs.gov.ru", "gosuslugi.ru",
    # агентства
    "tass.ru", "ria.ru", "interfax.ru", "reuters.com", "apnews.com", "afp.com",
    # фактчекинг
    "factcheck.org", "snopes.com", "politifact.com", "fullfact.org",
    "provereno.media", "stopfake.org",
})

_TIER2 = frozenset({
    "rbc.ru", "kommersant.ru", "vedomosti.ru", "forbes.ru", "rg.ru", "iz.ru",
    "lenta.ru", "gazeta.ru", "meduza.io", "novayagazeta.eu", "theins.ru",
    "bbc.com", "dw.com", "euronews.com", "theguardian.com", "nytimes.com",
    "washingtonpost.com", "ft.com", "bloomberg.com", "arstechnica.com",
})

#: Ярус домена: 1 — первоисточник или агентство, 2 — качественное СМИ.
DOMAIN_TIERS: dict[str, int] = {
    **{domain: 1 for domain in _TIER1},
    **{domain: 2 for domain in _TIER2},
}

_TIER_RELIABILITY = {1: 0.75, 2: 0.6}
_SCHEME = re.compile(r"^[a-z][a-z0-9+.\-]*://", re.IGNORECASE)


def normalize_domain(value: str) -> str:
    """Домен из строки или URL: без схемы, пути, порта и ведущего www."""
    text = (value or "").strip().lower()
    if not text:
        return ""
    text = _SCHEME.sub("", text)
    text = text.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    text = text.rsplit("@", 1)[-1].split(":", 1)[0]
    text = text.strip(".")
    if text.startswith("www."):
        text = text[4:]
    return text


def domain_tier(domain: str) -> int | None:
    """Ярус домена; поддомены наследуют ярус родителя."""
    host = normalize_domain(domain)
    if not host:
        return None
    known = DOMAIN_TIERS.get(host)
    if known is not None:
        return known
    parts = host.split(".")
    for index in range(1, len(parts) - 1):
        known = DOMAIN_TIERS.get(".".join(parts[index:]))
        if known is not None:
            return known
    return None


def _attr(item: Any, name: str, default: Any = "") -> Any:
    if isinstance(item, dict):
        return item.get(name, default)
    return getattr(item, name, default)


def _hit_domain(hit: Any) -> str:
    return normalize_domain(str(_attr(hit, "domain") or "")) or normalize_domain(str(_attr(hit, "url") or ""))


def _hit_text(hit: Any) -> str:
    title = textutil.norm_ws(str(_attr(hit, "title") or ""))
    body = _hit_body(hit)
    return textutil.norm_ws(f"{title}. {body}".strip(". ")) if title else body


def _hit_body(hit: Any) -> str:
    return textutil.norm_ws(str(_attr(hit, "content") or ""))


def _reprint_tokens(hit: Any) -> set[str]:
    """Токены для сравнения перепечаток: тело, а не заголовок.

    Перепечатка сохраняет текст, но не обязательно заголовок: у разных
    изданий он свой. Сравнение по тексту с заголовком давало бы лишние
    «независимые» источники на коротких заметках.
    """
    tokens = textutil.token_set(_hit_body(hit))
    return tokens if tokens else textutil.token_set(_hit_text(hit))


def _hit_key(hit: Any) -> str:
    return str(_attr(hit, "id") or "") or str(_attr(hit, "url") or "") or repr(hit)


def independent_docs(hits: Sequence[Any]) -> list[dict[str, Any]]:
    """Схлопывает перепечатки: один текст — один независимый документ."""
    docs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for hit in hits or []:
        key = _hit_key(hit)
        if key in seen:
            continue
        seen.add(key)
        body = _hit_text(hit)
        tokens = _reprint_tokens(hit)
        for doc in docs:
            if textutil.jaccard(tokens, doc["tokens"]) >= REPRINT_JACCARD:
                doc["texts"].append(body)
                doc["hits"].append(hit)
                break
        else:
            domain = _hit_domain(hit)
            docs.append({
                "tokens": tokens,
                "texts": [body],
                "hits": [hit],
                "domain": domain,
                "tier": domain_tier(domain),
            })
    return docs


def _contradicts(claim_text: str, doc_text: str) -> bool:
    """Материал спорит с утверждением: обратное отрицание при общем содержании
    или другой год события."""
    if textutil.has_negation(claim_text) != textutil.has_negation(doc_text):
        if textutil.coverage(claim_text, textutil.token_set(doc_text)) >= 0.5:
            return True
    claim_years = textutil.years(claim_text)
    doc_years = textutil.years(doc_text)
    if claim_years and doc_years and not (claim_years & doc_years):
        return True
    return False


def _claim_text(claim: Any) -> str:
    return textutil.norm_ws(str(_attr(claim, "text") or (claim if isinstance(claim, str) else "")))


def _claim_id(claim: Any) -> str:
    return str(_attr(claim, "id") or "")


def _claim_queries(claim: Any) -> list[str]:
    raw = _attr(claim, "queries", None)
    if raw is None and isinstance(claim, dict):
        raw = claim.get("queries")
    out: list[str] = []
    for item in raw or []:
        query = textutil.norm_ws(str(item or ""))
        if query and query not in out:
            out.append(query)
    if not out:
        text = _claim_text(claim)
        if text:
            out.append(text[:120])
    return out[:MAX_QUERIES_PER_CLAIM]


def judge_claim(claim: Any, docs: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Решение по одному утверждению: подтверждает / опровергает / не найдено."""
    text = _claim_text(claim)
    confirm: list[dict[str, Any]] = []
    deny: list[dict[str, Any]] = []
    for doc in docs or []:
        best = 0.0
        for body in doc["texts"]:
            best = max(best, textutil.coverage(text, textutil.token_set(body)))
        if best < COVER_CONFIRM:
            continue
        entry = {
            "domain": doc["domain"] or "?",
            "tier": doc["tier"],
            "coverage": round(best, 3),
        }
        if any(_contradicts(text, body) for body in doc["texts"]):
            deny.append(entry)
        else:
            confirm.append(entry)

    if len(confirm) > len(deny):
        position, picked = "подтверждает", confirm
    elif len(deny) > len(confirm):
        position, picked = "опровергает", deny
    else:
        position, picked = "не найдено", []

    tiers = [entry["tier"] for entry in picked if entry["tier"]]
    return {
        "claim_id": _claim_id(claim),
        "claim": text,
        "position": position,
        "independent": len(confirm) + len(deny),
        "tier": min(tiers) if tiers else None,
        "coverage": round(max((entry["coverage"] for entry in picked), default=0.0), 3),
        "sources": [dict(entry, domain=entry["domain"]) for entry in picked[:5]],
    }


def _coerce_claims(value: Any) -> list[Any]:
    """Приводит кэш и вход сигнала к списку утверждений."""
    if value is None:
        return []
    if isinstance(value, ClaimItem):
        return [value]
    if isinstance(value, dict):
        if "claims" in value:
            return _coerce_claims(value.get("claims"))
        return _coerce_claims([value])
    if isinstance(value, str):
        return _coerce_claims([value])
    if not isinstance(value, (list, tuple)):
        return []

    out: list[Any] = []
    for item in value:
        if isinstance(item, ClaimItem):
            out.append(item)
            continue
        if isinstance(item, str):
            payload: Any = {"text": item}
        elif isinstance(item, dict):
            payload = item
        else:
            continue
        try:
            out.append(ClaimItem(**payload))
        except ValidationError:
            continue
    return out


async def load_claims(ctx: CheckContext) -> list[Any]:
    """Утверждения из кэша T1 или, если T1 не запускался, новый разбор текста."""
    if "claims" in ctx.cache:
        return _coerce_claims(ctx.cache.get("claims"))
    if ctx.llm is None:
        raise ClaimsError("нет клиента модели: утверждения не выделены")
    return await extract_claims(ctx)


async def _search_all(
    ctx: CheckContext, claims: Sequence[Any]
) -> tuple[list[Any], list[str]]:
    """Ищет материалы по запросам утверждений; одинаковые запросы — один раз."""
    provider = ctx.search
    hits: list[Any] = []
    errors: list[str] = []
    if provider is None:
        return hits, errors

    executed: set[str] = set()
    for claim in claims:
        for query in _claim_queries(claim):
            if not query or query in executed:
                continue
            executed.add(query)
            try:
                found = await provider.search(query)
            except Exception as exc:  # поисковик может упасть — это не приговор
                errors.append(f"{query}: {type(exc).__name__}")
                continue
            try:
                hits.extend(list(found or []))
            except TypeError:
                errors.append(f"{query}: провайдер вернул не список")
    return hits, errors


def _domains_list(entries: Iterable[dict[str, Any]]) -> list[str]:
    """Домены без повторов: сначала ярус 1, потом 2, потом неизвестные."""
    domains = sorted(
        {(entry["domain"], entry["tier"]) for entry in entries if entry.get("domain")},
        key=lambda item: (item[1] is None, item[1] or 9, item[0]),
    )
    return [domain for domain, _ in domains]


def _domains_summary(entries: Iterable[dict[str, Any]]) -> str:
    return ", ".join(_domains_list(entries)[:MAX_SOURCES_IN_SUMMARY])


class SourcesSignal(BaseSignal):
    """T2: утверждения сверяются с найденными материалами."""

    id = "sources"
    name = "Сверка с источниками"
    stage = Stage.sources
    timeout_s = 10.0

    async def run(self, ctx: CheckContext) -> SignalResult:
        if ctx.search is None:
            return self.unavailable("нет поиска: сверять утверждения не с чем")

        try:
            claims = await load_claims(ctx)
        except ClaimsError as exc:
            return self.unavailable(str(exc))

        if not claims:
            return make_result(
                self, Verdict.neutral, 0.0, 0.0,
                "Проверяемых утверждений нет — сверять с источниками нечего.",
                {"claims": [], "positions": {}, "domains": [],
                 "independent_count": 0, "search_errors": []},
            )

        hits, errors = await _search_all(ctx, claims)
        docs = independent_docs(hits)
        judged = [judge_claim(claim, docs) for claim in claims]
        total = len(judged)
        confirmed = [item for item in judged if item["position"] == "подтверждает"]
        denied = [item for item in judged if item["position"] == "опровергает"]

        positions = {
            "подтверждает": len(confirmed),
            "опровергает": len(denied),
            "не найдено": total - len(confirmed) - len(denied),
        }
        details = {
            "claims": [
                {
                    "id": item["claim_id"],
                    "text": item["claim"],
                    "position": item["position"],
                    "independent": item["independent"],
                    "tier": item["tier"],
                    "coverage": item["coverage"],
                }
                for item in judged
            ],
            "positions": positions,
            "domains": _domains_list(
                {"domain": doc["domain"], "tier": doc["tier"]} for doc in docs
            ),
            "independent_count": max((item["independent"] for item in judged), default=0),
            "search_errors": errors,
        }

        if not docs:
            return make_result(
                self, Verdict.neutral, 0.0, 0.25,
                "Материалов по утверждениям не нашлось — подтверждать или опровергать нечем.",
                details,
            )
        if len(confirmed) == len(denied):
            return make_result(
                self, Verdict.neutral, 0.0, 0.3,
                "Найденные материалы не дают перевеса ни в одну сторону.",
                details,
            )

        winning = confirmed if len(confirmed) > len(denied) else denied
        verdict = Verdict.supports_real if len(confirmed) > len(denied) else Verdict.supports_fake
        best_tier = min((item["tier"] for item in winning if item["tier"]), default=None)
        max_independent = max(item["independent"] for item in winning)
        bonus = min(0.10, 0.05 * (max_independent - 1)) if max_independent > 1 else 0.0
        strength = min(
            0.85,
            0.25 + 0.35 * (len(winning) / total)
            + {1: 0.10, 2: 0.05}.get(best_tier, 0.0)
            + bonus,
        )
        reliability = _TIER_RELIABILITY.get(best_tier, 0.45)

        verb = "подтверждают" if verdict is Verdict.supports_real else "опровергают"
        summary = f"Найденные материалы {verb} {len(winning)} из {total} утверждений."
        domains = _domains_summary(
            source for item in winning for source in item["sources"]
        )
        if domains:
            summary += f" Источники: {domains}."
        return make_result(self, verdict, strength, reliability, summary, details)


__all__ = [
    "DOMAIN_TIERS",
    "SourcesSignal",
    "domain_tier",
    "independent_docs",
    "judge_claim",
    "load_claims",
    "normalize_domain",
]
