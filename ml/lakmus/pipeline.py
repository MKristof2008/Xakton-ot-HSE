"""Оркестратор проверки «Лакмус» (раздел 6.2, 6.7, 6.8 ТЗ).

Последовательность одной проверки:
  1. Выбрать сигналы по типу входа.
  2. Запустить их параллельно (`runner.run_signals`).
  3. Слить результаты в оценку доверия (`fusion.fuse`).
  4. Собрать аргументы «за» и «против» (`debate.run_debate`).
  5. Сформировать `CheckResult` и проверить контракт.
"""

from __future__ import annotations

import time
from typing import Any, Callable

from . import signals as _signal_registry
from .context import CheckContext
from .debate import run_debate
from .fusion import fuse
from .runner import run_signals
from .schemas import CheckInput, CheckResult, CheckStatus, NextStep, ProvenanceEntry, SignalResult
from .validate import validate_check_result


async def check(
    ctx: CheckContext,
    options: dict[str, Any] | None = None,
    llm: Any | None = None,
    on_signal_done: Callable | None = None,
) -> CheckResult:
    """Проверить один материал.

    Parameters
    ----------
    ctx:
        Контекст проверки. В `ctx.llm` можно передать клиента модели;
        параметр `llm` переопределяет его.
    options:
        Опции проверки (например, `max_debate_theses`).
    on_signal_done:
        Корутина/функция, вызываемая после каждого сигнала для SSE.

    Returns
    -------
    CheckResult
        Результат проверки, удовлетворяющий `validate_contract()`.
    """
    if ctx is None:
        raise ValueError("ctx is required")
    options = {**(ctx.options or {}), **(options or {})}
    effective_llm = llm if llm is not None else ctx.llm

    started_at = time.monotonic()
    selected = _signal_registry.default_signals(ctx.input.type)
    signal_results, limits = await run_signals(
        signals=selected,
        ctx=ctx,
        on_done=on_signal_done,
    )

    trust = fuse(signal_results)
    debate, next_steps = await run_debate(
        signal_results,
        llm=effective_llm,
        level=trust.level,
        options=options,
    )

    provenance = _collect_provenance(signal_results)
    duration_ms = int((time.monotonic() - started_at) * 1000)

    result = CheckResult(
        id=ctx.check_id,
        status=CheckStatus.done,
        input=ctx.input,
        trust=trust,
        signals=signal_results,
        debate=debate,
        provenance=provenance,
        next_steps=next_steps,
        limits=limits,
        duration_ms=duration_ms,
    )
    return validate_check_result(result.validate_contract())


def _collect_provenance(signal_results: list[SignalResult]) -> list[ProvenanceEntry]:
    entries: list[ProvenanceEntry] = []
    for signal in signal_results:
        raw = signal.details.get("provenance") if signal.details else None
        if not raw:
            continue
        if isinstance(raw, dict):
            entries.append(ProvenanceEntry(**raw))
        elif isinstance(raw, list):
            for item in raw:
                if isinstance(item, dict):
                    entries.append(ProvenanceEntry(**item))
    return entries


__all__ = ["check"]
