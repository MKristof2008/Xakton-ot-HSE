import pytest

from doreposta.llm_client import FakeLLMClient
from lakmus import CheckInput, InputType
from lakmus.context import CheckContext
from lakmus.pipeline import check


@pytest.mark.asyncio
async def test_pipeline_with_fake_llm_debate():
    def _handler(system: str, user: str) -> str:
        # Промпты дебатов просят JSON с тезисами.
        if "реальность" in system.lower() or "real" in system.lower():
            return '{"theses": [{"text": "В сообщении присутствует простое фактическое утверждение.", "signal_ids": ["claims"]}]}'
        if "подделка" in system.lower() or "fake" in system.lower():
            return '{"theses": [{"text": "Нет явных признаков подделки.", "signal_ids": ["claims"]}]}'
        return '{"theses": []}'

    fake = FakeLLMClient(_handler)
    ctx = CheckContext(
        check_id="llm_debate_01",
        input=CheckInput(type=InputType.text, extracted_text="Сегодня снег."),
        text="Сегодня снег.",
    )
    result = await check(ctx, llm=fake)
    assert result.debate.for_real or result.debate.for_fake
    assert result.next_steps
    # LLM должен был быть вызван хотя бы для одной стороны дебатов.
    assert fake.calls
