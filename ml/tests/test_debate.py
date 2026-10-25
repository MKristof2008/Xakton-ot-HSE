"""Тесты модуля «Два адвоката» (раздел 6.8 ТЗ).

Проверяем не красноречие модели, а контракт: каждый тезис ссылается на
существующий сигнал, приговоров в тезисах нет, стороны ограничены по длине,
а без модели спор всё равно собирается и остаётся связным.
"""

import json

from doreposta import FakeLLMClient, ModelCallError
from lakmus.debate import MAX_THESES, MIN_THESES, run_debate, sanitize_theses
from lakmus.schemas import (
    CheckInput,
    CheckResult,
    Debate,
    InputType,
    Level,
    NextStepKind,
    SignalResult,
    Stage,
    Verdict,
)

# --------------------------------------------------------------------------
# вспомогательное
# --------------------------------------------------------------------------


def sig(signal_id, verdict, strength=0.5, reliability=0.6, stage=Stage.artifacts,
        name=None, summary="Короткое пояснение сигнала."):
    return SignalResult(
        id=signal_id,
        name=name or signal_id,
        stage=stage,
        verdict=verdict,
        strength=strength,
        reliability=reliability,
        summary=summary,
    )


def payload(theses):
    return json.dumps({"theses": theses}, ensure_ascii=False)


def debate_client(real_theses, fake_theses, judged=None):
    """Клиент, который различает стороны по системному промпту.

    Очередь ответов тут не годится: стороны идут через asyncio.gather, и
    порядок вызовов не определён. Судья отвечает только если задан judged.
    """

    def handler(system, user):
        if "Адвокат реальности" in system:
            return payload(real_theses)
        if "Адвокат подделки" in system:
            return payload(fake_theses)
        if judged is None:
            raise ModelCallError("судья в этом тесте не нужен")
        return json.dumps(judged, ensure_ascii=False)

    return FakeLLMClient(handler)


REAL_SIGNAL = sig("provenance", Verdict.supports_real, 0.7, 0.8, Stage.provenance,
                  name="Первоисточник")
FAKE_SIGNAL = sig("manipulation", Verdict.supports_fake, 0.6, 0.7,
                  name="Манипуляция")
QUIET_SIGNAL = sig("machine_text", Verdict.neutral, 0.1, 0.05,
                   name="Машинный текст")


# --------------------------------------------------------------------------
# sanitize_theses: правила отбора
# --------------------------------------------------------------------------


def test_theses_with_unknown_signals_are_dropped():
    items = [
        {"text": "Первоисточник найден и датирован", "signal_ids": ["provenance"]},
        {"text": "Совпадение с базой фейков", "signal_ids": ["ghost"]},
        {"text": "Ссылка на выдуманный сигнал", "signal_ids": ["ghost", "provenance"]},
        {"text": "Без ссылок вовсе"},
    ]

    out = sanitize_theses(items, {"provenance", "manipulation"})

    assert [thesis.text for thesis in out] == [
        "Первоисточник найден и датирован",
        "Ссылка на выдуманный сигнал",
    ]
    assert out[1].signal_ids == ["provenance"]


def test_categorical_theses_are_dropped():
    items = [
        {"text": "Это точно правда", "signal_ids": ["provenance"]},
        {"text": "Однозначно подделка", "signal_ids": ["manipulation"]},
        {"text": "Совпадение 100%", "signal_ids": ["manipulation"]},
        {"text": "Метрики указывают на подделку", "signal_ids": ["manipulation"]},
    ]

    out = sanitize_theses(items, {"provenance", "manipulation"})

    assert [thesis.text for thesis in out] == ["Метрики указывают на подделку"]


def test_sanitize_limits_count_and_skips_duplicates():
    items = [
        {"text": "Аргумент номер один", "signal_ids": ["provenance"]},
        {"text": "Аргумент  номер  один", "signal_ids": ["provenance"]},
        {"text": "Аргумент номер два", "signal_ids": ["provenance"]},
        {"text": "Аргумент номер три", "signal_ids": ["provenance"]},
        {"text": "Аргумент номер четыре", "signal_ids": ["provenance"]},
        {"text": "Аргумент номер пять", "signal_ids": ["provenance"]},
    ]

    out = sanitize_theses(items, {"provenance"}, limit=MAX_THESES)

    assert len(out) == MAX_THESES
    assert out[0].text == "Аргумент номер один"


# --------------------------------------------------------------------------
# спор с моделью
# --------------------------------------------------------------------------


async def test_model_debate_keeps_linkage_to_signals():
    real = [
        {"text": "Первоисточник найден и датирован", "signal_ids": ["provenance"]},
        {"text": "Придуманный аргумент", "signal_ids": ["ghost"]},
    ]
    fake = [
        {"text": "Разметка указывает на манипуляцию", "signal_ids": ["manipulation"]},
    ]
    llm = debate_client(real, fake, judged={
        "for_real": real, "for_fake": fake,
    })

    debate, _ = await run_debate([REAL_SIGNAL, FAKE_SIGNAL], llm, Level.fog)

    known = {"provenance", "manipulation"}
    assert [thesis.text for thesis in debate.for_real] == ["Первоисточник найден и датирован"]
    assert [thesis.text for thesis in debate.for_fake] == ["Разметка указывает на манипуляцию"]
    for thesis in debate.for_real + debate.for_fake:
        assert thesis.signal_ids
        assert set(thesis.signal_ids) <= known


async def test_model_theses_are_capped_per_side():
    many = [
        {"text": f"Аргумент стороны номер {index}", "signal_ids": ["provenance"]}
        for index in range(1, 7)
    ]
    llm = debate_client(many, many, judged={"for_real": many, "for_fake": many})

    debate, _ = await run_debate([REAL_SIGNAL, FAKE_SIGNAL], llm, Level.fog)

    assert len(debate.for_real) <= MAX_THESES
    assert len(debate.for_fake) <= MAX_THESES


async def test_unavailable_signals_are_hidden_from_the_model():
    off = sig("search", Verdict.unavailable, 0.0, 0.0, summary="нет поиска")
    llm = debate_client(
        [{"text": "Первоисточник найден", "signal_ids": ["provenance"]}],
        [{"text": "Разметка указывает на манипуляцию", "signal_ids": ["manipulation"]}],
        judged={"for_real": [], "for_fake": []},
    )

    await run_debate([REAL_SIGNAL, FAKE_SIGNAL, off], llm, Level.fog)

    sent = "\n".join(user for _, user in llm.calls)
    assert "<<<" in sent and ">>>" in sent
    assert "нет поиска" not in sent


async def test_broken_model_answer_falls_back_without_exception():
    llm = FakeLLMClient([ModelCallError("сервис недоступен")])

    debate, _ = await run_debate([REAL_SIGNAL, FAKE_SIGNAL], llm, Level.fog)

    assert [thesis.signal_ids for thesis in debate.for_real] == [["provenance"]]
    assert [thesis.signal_ids for thesis in debate.for_fake] == [["manipulation"]]


async def test_garbage_answer_falls_back_to_signals():
    llm = FakeLLMClient(["это не JSON, а поток сознания"])

    debate, _ = await run_debate([REAL_SIGNAL, FAKE_SIGNAL], llm, Level.fog)

    assert debate.for_real and debate.for_fake
    assert debate.for_real[0].signal_ids == ["provenance"]
    assert debate.for_fake[0].signal_ids == ["manipulation"]


# --------------------------------------------------------------------------
# спор без модели
# --------------------------------------------------------------------------


async def test_debate_without_llm_is_built_from_signals():
    debate, steps = await run_debate(
        [REAL_SIGNAL, FAKE_SIGNAL, QUIET_SIGNAL], None, Level.fog
    )

    assert len(debate.for_real) == 1
    assert len(debate.for_fake) == 1
    assert debate.for_real[0].signal_ids == ["provenance"]
    assert debate.for_fake[0].signal_ids == ["manipulation"]
    assert "Первоисточник" in debate.for_real[0].text

    kinds = [step.kind for step in steps]
    assert NextStepKind.ask_source in kinds
    assert NextStepKind.verify in kinds
    assert NextStepKind.hold in kinds
    assert MIN_THESES <= len(debate.for_real) + len(debate.for_fake) <= MAX_THESES


async def test_neutral_only_signals_do_not_invent_an_accusation():
    debate, _ = await run_debate([QUIET_SIGNAL], None, Level.fog)

    # Спор не придумывает обвинение: обе стороны опираются на один сигнал.
    for thesis in debate.for_real + debate.for_fake:
        assert thesis.signal_ids == ["machine_text"]


async def test_next_steps_follow_level():
    _, fake_steps = await run_debate([FAKE_SIGNAL], None, Level.likely_fake)
    _, real_steps = await run_debate([REAL_SIGNAL], None, Level.likely_real)

    assert [step.kind for step in fake_steps][0] is NextStepKind.hold
    assert [step.kind for step in real_steps][0] is NextStepKind.share


def test_run_debate_signature_is_stable():
    import inspect

    params = list(inspect.signature(run_debate).parameters)
    assert params == ["signals", "llm", "level", "options"]


# --------------------------------------------------------------------------
# контракт результата
# --------------------------------------------------------------------------


async def test_result_with_debate_passes_contract_validation():
    debate, steps = await run_debate(
        [REAL_SIGNAL, FAKE_SIGNAL], None, Level.fog
    )

    result = CheckResult(
        id="check-debate-1",
        input=CheckInput(type=InputType.text),
        signals=[REAL_SIGNAL, FAKE_SIGNAL],
        debate=debate,
        next_steps=steps,
    ).validate_contract()

    assert result.debate.for_real
    assert result.debate.for_fake


def test_contract_rejects_thesis_without_signal_ids():
    broken = Debate(for_real=[{"text": "Просто мнение", "signal_ids": []}])

    try:
        CheckResult(
            id="check-debate-2",
            input=CheckInput(type=InputType.text),
            signals=[REAL_SIGNAL],
            debate=broken,
        ).validate_contract()
    except ValueError as exc:
        assert "signal_ids" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("контракт пропустил тезис без ссылок")
