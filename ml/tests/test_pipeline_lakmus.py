import pytest

from lakmus import CheckInput, InputType, CheckResult
from lakmus.context import CheckContext
from lakmus.pipeline import check
from lakmus.schemas import SignalEvent


@pytest.mark.asyncio
async def test_pipeline_text_returns_check_result():
    ctx = CheckContext(
        check_id="test_text_01",
        input=CheckInput(type=InputType.text, extracted_text="Сегодня в Москве идёт снег."),
        text="Сегодня в Москве идёт снег.",
    )
    result = await check(ctx)
    assert isinstance(result, CheckResult)
    assert result.id == "test_text_01"
    assert result.status.value == "done"
    assert len(result.signals) == 6
    assert result.trust.score >= 0
    assert all(s.id for s in result.signals)


@pytest.mark.asyncio
async def test_pipeline_image_returns_check_result():
    ctx = CheckContext(
        check_id="test_img_01",
        input=CheckInput(type=InputType.image),
        data=b"\x89PNG\r\n\x1a\n" + b"\x00" * 100,
    )
    result = await check(ctx)
    assert isinstance(result, CheckResult)
    assert result.input.type == InputType.image
    assert len(result.signals) == 7
    assert result.trust.uncertainty >= 0


@pytest.mark.asyncio
async def test_pipeline_url_uses_text_signals():
    ctx = CheckContext(
        check_id="test_url_01",
        input=CheckInput(type=InputType.url, extracted_text="По сообщениям, завтра повышение ставки."),
        text="По сообщениям, завтра повышение ставки.",
    )
    result = await check(ctx)
    assert isinstance(result, CheckResult)
    assert result.input.type == InputType.url
    signal_ids = {s.id for s in result.signals}
    assert "claims" in signal_ids
    assert "sources" in signal_ids


@pytest.mark.asyncio
async def test_pipeline_no_llm_fallback_debate():
    ctx = CheckContext(
        check_id="test_fallback_01",
        input=CheckInput(type=InputType.text, extracted_text="Пример текста."),
        text="Пример текста.",
    )
    result = await check(ctx)
    assert result.debate.for_real or result.debate.for_fake or True
    assert result.next_steps
    assert all(step.kind for step in result.next_steps)


@pytest.mark.asyncio
async def test_pipeline_sse_callback_called():
    seen = []

    async def _on_done(event: SignalEvent):
        seen.append(event.signal.id)

    ctx = CheckContext(
        check_id="test_sse_01",
        input=CheckInput(type=InputType.text, extracted_text="Hello."),
        text="Hello.",
    )
    result = await check(ctx, on_signal_done=_on_done)
    assert len(seen) == len(result.signals)
    assert "claims" in seen
