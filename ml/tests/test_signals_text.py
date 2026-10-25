"""Тесты текстовых сигналов T1–T5 (разделы 6.4–6.7 ТЗ).

Всё на FakeLLMClient и поддельном поиске: ни ключа, ни сети, ни новых
зависимостей. Проверяем не «качество модели», а контракт сигналов: вердикт,
силу, надёжность, обязательные details и поведение без модели/поиска.
"""

import json

from doreposta import FakeLLMClient, ModelCallError
from lakmus.context import CheckContext, SearchHit
from lakmus.schemas import CheckInput, InputType, Stage, Verdict
from lakmus.signals.machine_text import MachineTextSignal
from lakmus.signals.quotes import QuotesSignal, extract_quotes
from lakmus.signals.rhetoric import RhetoricSignal
from lakmus.signals.text_claims import ClaimsSignal
from lakmus.signals.text_sources import (
    DOMAIN_TIERS,
    SourcesSignal,
    domain_tier,
    independent_docs,
    normalize_domain,
)

# --------------------------------------------------------------------------
# вспомогательное
# --------------------------------------------------------------------------


def ctx(text, llm=None, search=None, options=None, cache=None):
    context = CheckContext(
        check_id="check-text-1",
        input=CheckInput(type=InputType.text),
        text=text,
        llm=llm,
        search=search,
        options=options or {},
    )
    if cache:
        context.cache.update(cache)
    return context


class FakeSearch:
    """Поисковик-заглушка: ответы по запросу, "*" — ответ по умолчанию."""

    def __init__(self, responses=None):
        self.responses = responses or {}
        self.queries = []

    async def search(self, query):
        self.queries.append(query)
        return list(self.responses.get(query, self.responses.get("*", [])))


def hit(hit_id, domain, content, title="", snippet=False):
    return SearchHit(
        id=hit_id,
        title=title or hit_id,
        url=f"https://{domain}/{hit_id}",
        content=content,
        snippet=snippet,
        domain=domain,
    )


def claims_json(items, reason=None):
    return json.dumps({"claims": items, "uncheckable_reason": reason}, ensure_ascii=False)


def claims_cache(*texts):
    return {
        "claims": [
            {"id": f"c{index + 1}", "text": text, "queries": [text[:60]]}
            for index, text in enumerate(texts)
        ]
    }


METRO_DOC = "Метро откроют 15 мая 2029 года, сообщил мэр города на встрече с журналистами."


# --------------------------------------------------------------------------
# T1. проверяемые утверждения
# --------------------------------------------------------------------------


async def test_claims_drops_year_that_model_invented():
    text = "Метро откроют 15 мая 2029 года. Мэр пообещал бесплатный проезд для школьников."
    llm = FakeLLMClient([claims_json([
        {"id": "a", "text": "Метро откроют 15 мая 2029 года",
         "queries": ["метро откроют 15 мая"], "kind": "дата"},
        {"id": "b", "text": "Мэр пообещал бесплатный проезд для школьников",
         "queries": ["мэр бесплатный проезд"], "kind": "событие"},
        {"id": "c", "text": "В 2031 году тариф вырастет вдвое",
         "queries": ["тариф вырастет"], "kind": "число"},
    ])])

    result = await ClaimsSignal().run(ctx(text, llm=llm))

    assert result.id == "claims"
    assert result.stage is Stage.sources
    assert result.verdict is Verdict.neutral
    assert result.strength == 0.0
    assert result.details["count"] == 2
    assert [claim["id"] for claim in result.details["claims"]] == ["c1", "c2"]
    assert any("год" in item for item in result.details["dropped"])
    # текст уходит модели как данные, а не как инструкции
    assert "<<<" in llm.calls[0][1] and ">>>" in llm.calls[0][1]


async def test_claims_limits_to_five_and_keeps_order():
    texts = [
        "Тариф вырастет с первого июня",
        "Проезд станет бесплатным для школьников",
        "Мэр подписал распоряжение о ремонте депо",
        "Школы закроют на карантин",
        "Автобусы пустят по новому маршруту",
        "Стоимость проезда изменится",
        "Депо отремонтируют за счёт города",
    ]
    llm = FakeLLMClient([claims_json(
        [{"text": text, "queries": [text], "kind": "событие"} for text in texts]
    )])

    result = await ClaimsSignal().run(ctx(" ".join(texts) + ".", llm=llm))

    assert result.details["count"] == 5
    assert [claim["id"] for claim in result.details["claims"]] == ["c1", "c2", "c3", "c4", "c5"]


async def test_claims_empty_list_is_opinion_not_error():
    llm = FakeLLMClient([claims_json([], reason="в тексте только мнение")])

    result = await ClaimsSignal().run(ctx("Всё будет хорошо, я верю в лучшее.", llm=llm))

    assert result.verdict is Verdict.neutral
    assert result.details["count"] == 0
    assert result.details["uncheckable_reason"] == "в тексте только мнение"
    assert "мнение" in result.summary
    assert result.reliability <= 0.3


async def test_claims_without_llm_is_unavailable():
    result = await ClaimsSignal().run(ctx("Метро откроют 15 мая 2029 года."))

    assert result.verdict is Verdict.unavailable
    assert "нет клиента модели" in result.summary


async def test_claims_survives_model_failure():
    llm = FakeLLMClient([ModelCallError("сервис недоступен")])

    result = await ClaimsSignal().run(ctx("Метро откроют 15 мая 2029 года.", llm=llm))

    assert result.verdict is Verdict.unavailable
    assert "модель не ответила" in result.summary


# --------------------------------------------------------------------------
# T2. сверка с источниками
# --------------------------------------------------------------------------


def test_domain_tiers_and_normalization():
    assert normalize_domain("https://www.tass.ru:443/a/b?x=1#z") == "tass.ru"
    assert normalize_domain("ria.ru") == "ria.ru"
    assert domain_tier("tass.ru") == 1
    assert domain_tier("news.bbc.com") == 2
    assert domain_tier("example.com") is None
    assert DOMAIN_TIERS["kremlin.ru"] == 1


def test_retranslations_count_as_one_document():
    hits = [
        hit("h1", "tass.ru", METRO_DOC),
        hit("h2", "ria.ru", METRO_DOC),
        hit("h3", "lenta.ru", METRO_DOC),
    ]

    docs = independent_docs(hits)

    assert len(docs) == 1
    assert len(docs[0]["hits"]) == 3
    assert docs[0]["tier"] == 1


async def test_sources_confirms_claim_but_retranslations_are_one_source():
    search = FakeSearch({"*": [
        hit("h1", "tass.ru", METRO_DOC),
        hit("h2", "ria.ru", METRO_DOC),
        hit("h3", "lenta.ru", METRO_DOC),
    ]})
    context = ctx("Метро откроют 15 мая 2029 года.", search=search,
                  cache=claims_cache("Метро откроют 15 мая 2029 года"))

    result = await SourcesSignal().run(context)

    assert result.id == "sources"
    assert result.stage is Stage.sources
    assert result.verdict is Verdict.supports_real
    assert result.details["independent_count"] == 1
    assert result.details["positions"]["подтверждает"] == 1
    assert 0.0 < result.strength <= 0.85
    assert result.reliability >= 0.6
    assert "подтверждают" in result.summary


async def test_sources_two_independent_sources_are_stronger():
    second = "По данным мэрии, метро откроют 15 мая 2029 года после ремонта путей."
    single = FakeSearch({"*": [hit("h1", "tass.ru", METRO_DOC)]})
    double = FakeSearch({"*": [hit("h1", "tass.ru", METRO_DOC),
                               hit("h2", "interfax.ru", second)]})
    cache = claims_cache("Метро откроют 15 мая 2029 года")

    one = await SourcesSignal().run(ctx("Метро откроют 15 мая 2029 года.",
                                        search=single, cache=cache))
    two = await SourcesSignal().run(ctx("Метро откроют 15 мая 2029 года.",
                                        search=double, cache=claims_cache(
                                            "Метро откроют 15 мая 2029 года")))

    assert two.details["independent_count"] == 2
    assert two.verdict is Verdict.supports_real
    assert two.strength > one.strength


async def test_sources_contradicting_material_supports_fake():
    search = FakeSearch({"*": [
        hit("h1", "tass.ru", "Метро не откроют 15 мая 2029 года: ремонт перенесли на осень."),
    ]})
    context = ctx("Метро откроют 15 мая 2029 года.", search=search,
                  cache=claims_cache("Метро откроют 15 мая 2029 года"))

    result = await SourcesSignal().run(context)

    assert result.verdict is Verdict.supports_fake
    assert result.details["positions"]["опровергает"] == 1
    assert "опровергают" in result.summary


async def test_sources_without_search_is_unavailable():
    result = await SourcesSignal().run(
        ctx("Метро откроют 15 мая 2029 года.", cache=claims_cache("Метро откроют 15 мая 2029 года"))
    )

    assert result.verdict is Verdict.unavailable
    assert "нет поиска" in result.summary


async def test_sources_without_claims_is_neutral():
    result = await SourcesSignal().run(
        ctx("Всё будет хорошо.", search=FakeSearch({}), cache={"claims": []})
    )

    assert result.verdict is Verdict.neutral
    assert result.strength == 0.0
    assert result.details["claims"] == []


async def test_sources_without_claims_and_without_llm_is_unavailable():
    result = await SourcesSignal().run(ctx("Метро откроют.", search=FakeSearch({})))

    assert result.verdict is Verdict.unavailable
    assert "нет клиента модели" in result.summary


async def test_sources_empty_search_result_is_not_a_verdict():
    result = await SourcesSignal().run(
        ctx("Метро откроют 15 мая 2029 года.", search=FakeSearch({}),
            cache=claims_cache("Метро откроют 15 мая 2029 года"))
    )

    assert result.verdict is Verdict.neutral
    assert result.strength == 0.0
    assert result.details["positions"]["не найдено"] == 1


# --------------------------------------------------------------------------
# T3. точные цитаты
# --------------------------------------------------------------------------

QUOTE_TEXT = (
    "Мэр заявил: «Метро откроют уже в мае этого года, обещаю вам лично» "
    "и ушёл, не отвечая на вопросы."
)


def test_extract_quotes_ignores_short_and_deduplicates():
    text = "Он сказал: «Коротко» и «Это достаточно длинная цитата для проверки»."

    quotes = extract_quotes(text)

    assert [item["quote"] for item in quotes] == ["Это достаточно длинная цитата для проверки"]


async def test_quotes_found_verbatim_supports_real():
    search = FakeSearch({"*": [
        hit("h1", "tass.ru", "Метро откроют уже в мае этого года, обещаю вам лично — заявил мэр."),
    ]})

    result = await QuotesSignal().run(ctx(QUOTE_TEXT, search=search))

    assert result.id == "quotes"
    assert result.verdict is Verdict.supports_real
    assert result.details["found"] == 1
    assert result.details["quotes"][0]["verbatim"] is True
    assert result.reliability >= 0.4


async def test_quotes_snippet_only_is_weak_evidence():
    search = FakeSearch({"*": [
        hit("h1", "lenta.ru", "Метро откроют уже в мае этого года, обещаю вам лично", snippet=True),
    ]})

    result = await QuotesSignal().run(ctx(QUOTE_TEXT, search=search))

    assert result.verdict is Verdict.supports_real
    assert result.details["quotes"][0]["strong"] is False
    assert result.strength <= 0.4


async def test_quotes_missing_is_not_a_fake_verdict():
    search = FakeSearch({"*": [hit("h1", "example.com", "Совсем другой текст про погоду в мае.")]})

    result = await QuotesSignal().run(ctx(QUOTE_TEXT, search=search))

    assert result.verdict is Verdict.neutral
    assert result.strength == 0.0
    assert result.details["missing_quotes"]
    assert "нигде не найдена" in result.summary
    assert "не доказывает подделку" in result.summary


async def test_quotes_without_search_is_unavailable():
    result = await QuotesSignal().run(ctx(QUOTE_TEXT))

    assert result.verdict is Verdict.unavailable
    assert "нет поиска" in result.summary


async def test_quotes_and_text_without_quotes_is_neutral():
    result = await QuotesSignal().run(ctx("Просто текст без кавычек.", search=FakeSearch({})))

    assert result.verdict is Verdict.neutral
    assert result.details["searched"] == 0


# --------------------------------------------------------------------------
# T4. риторика давления
# --------------------------------------------------------------------------

PRESSING = (
    "СРОЧНО!!! Перешлите всем! Источники сообщают: врачи скрывают правду. "
    "Это катастрофа, шок, кошмар, позор!"
)

CALM = (
    "По сообщению пресс-службы метрополитена, с 15 мая 2029 года интервал движения "
    "поездов сократится до двух минут в часы пик. Расписание опубликовано на сайте "
    "https://mosmetro.ru/news."
)


async def test_rhetoric_flags_pressing_style_but_stays_neutral():
    result = await RhetoricSignal().run(ctx(PRESSING))

    assert result.id == "rhetoric"
    assert result.stage is Stage.artifacts
    assert result.verdict is Verdict.neutral
    assert result.strength == 0.0
    assert result.details["flag"] is True
    assert result.reliability <= 0.3
    assert "характерный для манипуляций" in result.summary.lower()
    assert "не признак лжи" in result.summary


async def test_rhetoric_calm_text_has_no_flags():
    result = await RhetoricSignal().run(ctx(CALM))

    assert result.details["flag"] is False
    assert result.details["markers"] == []
    assert result.reliability <= 0.1
    assert result.verdict is Verdict.neutral


async def test_rhetoric_merges_llm_markers_and_keeps_reliability_low():
    llm = FakeLLMClient([json.dumps({"flag": True, "markers": ["обращение к детям"],
                                     "note": "давление на эмоции"}, ensure_ascii=False)])

    result = await RhetoricSignal().run(ctx(CALM, llm=llm))

    assert "обращение к детям" in result.details["markers"]
    assert result.details["llm"] == "использована"
    assert result.reliability <= 0.3
    assert result.strength == 0.0


async def test_rhetoric_survives_broken_llm_answer():
    llm = FakeLLMClient(["не JSON вовсе"])

    result = await RhetoricSignal().run(ctx(PRESSING, llm=llm))

    assert result.details["flag"] is True
    assert "не разобран" in result.details["llm"]
    assert result.reliability <= 0.3


async def test_rhetoric_without_text_is_unavailable():
    result = await RhetoricSignal().run(ctx("   "))

    assert result.verdict is Verdict.unavailable


# --------------------------------------------------------------------------
# T5. машинный текст
# --------------------------------------------------------------------------

ROBOTIC = " ".join(
    ["Служба города сообщает о ходе работ по ремонту моста."] * 10
)


async def test_machine_text_is_only_a_weak_hint():
    result = await MachineTextSignal().run(ctx(ROBOTIC))

    assert result.id == "machine_text"
    assert result.verdict is Verdict.neutral
    assert result.reliability <= 0.05
    assert result.strength <= 0.05
    assert result.details["perplexity"].startswith("недоступна")
    assert result.details["words"] >= 40
    assert result.details["hints"]


async def test_machine_text_short_text_gives_no_claim():
    result = await MachineTextSignal().run(ctx("Короткий текст. Ещё одно предложение."))

    assert result.verdict is Verdict.neutral
    assert result.details["hints"] == []
    assert result.strength == 0.0
    assert "ненадёжна" in result.summary


async def test_machine_text_without_text_is_unavailable():
    result = await MachineTextSignal().run(ctx(""))

    assert result.verdict is Verdict.unavailable
