"""Новые правила: дедуп перепечаток, конфликт доказательств, автосвязывание цитат, нормализация кавычек."""
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
from doreposta.pipeline import dedupe_sources, validate_result

BODY = ("Минэкономразвития сообщило о росте ВВП России на 3.6 процента по итогам года. "
        "Показатель превысил прогнозы аналитиков и ожидания Центробанка. "
        "Эксперты связывают рост с восстановлением промышленности и экспорта.")


def mk_src(id, content=BODY):
    return Source(id=id, title="Материал", url=f"https://example.com/{id}", content=content,
                  content_kind=ContentKind.page, origin=Origin.retrieved)


def mk_claim(evidence, status=Status.supported):
    return EvaluationResult(claims=[ClaimResult(
        id="c1", text="ВВП России вырос на 3.6%", status=status,
        explanation="Вывод модели", evidence=evidence, limitations=[], next_action="",
    )])


def test_dedupe_removes_reposts():
    original = mk_src("s1")
    repost = mk_src("s2", content="  " + BODY + "  ")  # та же статья с другими пробелами
    other = mk_src("s3", content="Совсем другая новость про криптовалюту и биткоин, ничего общего.")
    kept = dedupe_sources([original, repost, other])
    assert [s.id for s in kept] == ["s1", "s3"]


def test_dedupe_keeps_different_texts():
    a = mk_src("s1")
    b = mk_src("s2", content="Центробанк повысил ключевую ставку до 21 процента на фоне инфляции.")
    assert len(dedupe_sources([a, b])) == 2


def test_conflict_supports_and_contradicts_downgraded():
    quote = "Минэкономразвития сообщило о росте ВВП России на 3.6 процента"
    ev = [
        Evidence(source_id="s1", quote=quote, relation=Relation.supports, explanation="подтверждает"),
        Evidence(source_id="s2", quote=quote, relation=Relation.contradicts, explanation="опровергает"),
    ]
    cr = validate_result(mk_claim(ev), [mk_src("s1"), mk_src("s2")]).claims[0]
    assert cr.status == Status.insufficient
    assert any("Конфликт доказательств" in item for item in cr.limitations)


def test_wrong_source_id_relinked_by_quote():
    quote = "Минэкономразвития сообщило о росте ВВП России на 3.6 процента"
    ev = [Evidence(source_id="s_nope", quote=quote, relation=Relation.supports, explanation="да")]
    cr = validate_result(mk_claim(ev), [mk_src("s1"), mk_src("s2", content="Другой текст про ставку.")]).claims[0]
    assert cr.status == Status.supported
    assert cr.evidence[0].source_id == "s1"
    assert any("привязана заново" in item for item in cr.limitations)


def test_quote_with_typographic_quotes_matches():
    quote = "«Минэкономразвития сообщило о росте ВВП России»"
    src = mk_src("s1", content='Сайт пишет: "Минэкономразвития сообщило о росте ВВП России" — вот так.')
    ev = [Evidence(source_id="s1", quote=quote, relation=Relation.supports, explanation="да")]
    cr = validate_result(mk_claim(ev), [src]).claims[0]
    assert cr.status == Status.supported
    assert cr.evidence
