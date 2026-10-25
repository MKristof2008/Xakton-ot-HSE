"""Правила статусов в validate_result: без оснований статус понижается."""
from doreposta import (
    ClaimResult,
    ContentKind,
    EvaluationResult,
    Evidence,
    Origin,
    Relation,
    Source,
    Status,
)
from doreposta.pipeline import validate_result

CONTENT = "Университет подтвердил открытие нового факультета в 2024 году."
QUOTE = "Университет подтвердил открытие нового факультета"


def src(id="s1"):
    return Source(id=id, title="Материал", url="https://example.com/1", content=CONTENT,
                  content_kind=ContentKind.page, origin=Origin.retrieved)


def result(status, relation="supports", limitations=None, explanation="Почему цитата относится"):
    return EvaluationResult(claims=[ClaimResult(
        id="c1",
        text="Университет открыл новый факультет в 2024 году",
        status=status,
        explanation="Вывод модели",
        evidence=[Evidence(source_id="s1", quote=QUOTE, relation=relation,
                           explanation=explanation)],
        limitations=list(limitations or []),
        next_action="Проверить приказ",
    )])


def check(status, **kwargs):
    return validate_result(result(status, **kwargs), [src()]).claims[0]


def test_supported_survives_with_supporting_quote():
    cr = check("supported")
    assert cr.status == Status.supported
    assert cr.evidence


def test_supported_without_supports_downgraded():
    cr = check("supported", relation="adds_context")
    assert cr.status == Status.insufficient
    assert any("relation=supports" in item for item in cr.limitations)


def test_contradicted_without_contradicts_downgraded():
    cr = check("contradicted", relation="supports")
    assert cr.status == Status.insufficient
    assert any("relation=contradicts" in item for item in cr.limitations)


def test_context_without_named_condition_downgraded():
    cr = check("context", relation="adds_context", explanation="")
    assert cr.status == Status.insufficient
    assert any("условие" in item for item in cr.limitations)


def test_context_with_condition_survives():
    cr = check("context", relation="adds_context", limitations=["речь только о бакалавриате"])
    assert cr.status == Status.context
    assert "речь только о бакалавриате" in cr.limitations
