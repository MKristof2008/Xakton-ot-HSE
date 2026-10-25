"""Ужесточения пайплайна: обрезка контекста, дедупликация, отбор, ретраи, записи."""
import json
import urllib.error
import urllib.request

import pytest

from doreposta import (
    Claim,
    ClaimResult,
    ContentKind,
    EvaluationResult,
    Evidence,
    FakeLLMClient,
    ModelCallError,
    Origin,
    Relation,
    Source,
    Status,
    extract_claims,
    summarize,
    validate_result,
)
from doreposta import checks
from doreposta.context_build import sources_block
from doreposta.llm_client import LLMClient
from doreposta.recording import RecordingLLMClient, ReplayLLMClient


def src(id="s1", content="", published_at=None, title="Материал"):
    return Source(id=id, title=title, url=f"https://example.com/{id}", content=content,
                  content_kind=ContentKind.page, origin=Origin.retrieved,
                  published_at=published_at)


def claim(text="Утверждение", **kwargs):
    return Claim(id=kwargs.get("id", "c1"), original_span=text, text=text,
                 queries=kwargs.get("queries", ["запрос"]))


def check(text, quote, published_at=None, content=None, relation="supports"):
    res = EvaluationResult(claims=[ClaimResult(
        id="c1", text=text, status=Status.supported, explanation="вывод",
        evidence=[Evidence(source_id="s1", quote=quote, relation=Relation(relation),
                           explanation="связь")],
        limitations=[], next_action="проверить")])
    content = quote if content is None else content
    return validate_result(res, [src(content=content, published_at=published_at)]).claims[0]


# --- годы -------------------------------------------------------------------

def test_other_year_downgraded():
    cr = check("Университет открыл факультет в 2024 году",
               "Университет открыл факультет в 2021 году")
    assert cr.status is Status.insufficient
    assert any("другой год" in lim for lim in cr.limitations)


def test_year_without_quote_or_date_downgraded():
    cr = check("Университет открыл факультет в 2024 году",
               "Университет открыл новый факультет")
    assert cr.status is Status.insufficient
    assert any("Год не подтверждён" in lim for lim in cr.limitations)


def test_published_at_confirms_year():
    cr = check("Университет открыл факультет в 2024 году",
               "Университет открыл новый факультет", published_at="2024-09-01")
    assert cr.status is Status.supported


# --- числа и отрицания ------------------------------------------------------

def test_number_mismatch_downgraded():
    cr = check("Открыли 7 новых корпусов", "Открыли 5 новых корпусов")
    assert cr.status is Status.insufficient
    assert any("Числа" in lim for lim in cr.limitations)


def test_negation_mismatch_downgraded():
    cr = check("Строительство не остановят", "строительство объекта продолжается")
    assert cr.status is Status.insufficient
    assert any("Отрицание" in lim for lim in cr.limitations)


def test_short_quote_dropped():
    cr = check("Университет открыл новый факультет", "подтверждаю")
    assert cr.status is Status.insufficient
    assert not cr.evidence
    assert any("слишком коротких цитат" in lim for lim in cr.limitations)


# --- обрезка контекста ------------------------------------------------------

def test_truncate_content_marks_cut():
    long = ("начало " * 900) + "университет факультет " + ("хвост " * 900)
    text, was_cut = checks.truncate_content(long, ["университет"], limit=4000)
    assert was_cut is True
    assert "университет" in text
    assert len(text) <= 4100


def test_sources_block_reports_truncated():
    block, truncated = sources_block([src(content="слово " * 2000)], ["слово"])
    assert truncated == {"s1"}
    assert "s1" in block


# --- дедупликация при извлечении -------------------------------------------

async def test_duplicate_claims_removed():
    payload = json.dumps({"claims": [
        {"id": "c1", "original_span": "Университет открыл новый факультет",
         "text": "Университет открыл новый факультет", "queries": ["факультет"]},
        {"id": "c2", "original_span": "открыл новый факультет",
         "text": "Университет открыл новый факультет", "queries": ["факультет"]},
    ], "uncheckable_reason": None})
    client = FakeLLMClient(lambda system, user: payload)
    res = await extract_claims("Университет открыл новый факультет", None, client)
    assert len(res.claims) == 1


# --- отбор источников -------------------------------------------------------

def test_select_sources_limits_and_ranks():
    sources = [src(id=f"s{i}", content="посторонний текст про погоду",
                   title=f"Заметка {i}") for i in range(8)]
    sources.append(src(id="rel", content="университет открыл факультет",
                       title="Факультет"))
    picked = checks.select_sources([claim("Университет открыл факультет")], sources, 6)
    assert len(picked) == 6
    assert "rel" in {s.id for s in picked}


# --- ретраи -----------------------------------------------------------------

class _Resp:
    def __init__(self, payload):
        self._body = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _client():
    return LLMClient(api_key="k", base_url="http://x", model="m", retries=2, backoff=0)


def test_sync_call_retries_on_503(monkeypatch):
    calls = []

    def fake(req, timeout=None):
        calls.append(1)
        if len(calls) < 3:
            raise urllib.error.HTTPError("http://x", 503, "busy", None, None)
        return _Resp({"choices": [{"message": {"content": "ok"}}]})

    monkeypatch.setattr(urllib.request, "urlopen", fake)
    assert _client()._sync_call("s", "u").text == "ok"
    assert len(calls) == 3


def test_sync_call_does_not_retry_on_400(monkeypatch):
    calls = []

    def fake(req, timeout=None):
        calls.append(1)
        raise urllib.error.HTTPError("http://x", 400, "bad", None, None)

    monkeypatch.setattr(urllib.request, "urlopen", fake)
    with pytest.raises(ModelCallError):
        _client()._sync_call("s", "u")
    assert len(calls) == 1


# --- запись, проигрывание, сводка ------------------------------------------

async def test_record_and_replay(tmp_path):
    path = tmp_path / "run.jsonl"
    rec = RecordingLLMClient(FakeLLMClient(lambda system, user: "ответ"), path)
    await rec.complete("sys", "user")

    replay = ReplayLLMClient(path)
    assert (await replay.complete("sys", "user")).text == "ответ"
    with pytest.raises(ModelCallError):
        await replay.complete("sys", "other")


def test_summarize_counts():
    cr = ClaimResult(id="c1", text="t", status=Status.insufficient, explanation="e",
                     evidence=[], limitations=["Год не подтверждён"], next_action="a")
    stats = summarize([EvaluationResult(claims=[cr], share_text="")])
    assert stats["claims"] == 1
    assert stats["by_status"]["insufficient"] == 1
    assert stats["limitations"]["Год не подтверждён"] == 1


async def test_truncation_limitation_added_on_evaluate():
    from doreposta import evaluate_claims

    long_content = ("посторонний текст " * 500) + "метро откроют 12 мая 2025 года"
    payload = json.dumps({"claims": [{
        "id": "c1", "text": "Метро откроют 12 мая 2025 года", "status": "supported",
        "explanation": "материал прямо говорит о дате",
        "evidence": [{"source_id": "s1", "quote": "метро откроют 12 мая 2025 года",
                      "relation": "supports", "explanation": "дата совпадает"}],
        "limitations": [], "next_action": "проверить"}]})
    client = FakeLLMClient(lambda system, user: payload)
    res = await evaluate_claims([claim("Метро откроют 12 мая 2025 года")],
                                [src(content=long_content)], {}, client)
    assert any("усечён" in lim for lim in res.claims[0].limitations)
