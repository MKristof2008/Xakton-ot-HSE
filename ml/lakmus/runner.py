"""Раннер сигналов: asyncio.gather, таймауты, события (раздел 6.2 ТЗ)."""

from __future__ import annotations

import asyncio
import time
from typing import Awaitable, Callable, Sequence

from .context import CheckContext
from .schemas import SignalEvent, SignalResult
from .signals.base import Signal


def _failed(signal: Signal, reason: str) -> SignalResult:
    return SignalResult.unavailable(signal.id, signal.name, signal.stage, reason)


async def _run_one(signal: Signal, ctx: CheckContext) -> tuple[SignalResult, float]:
    started = time.monotonic()
    try:
        result = await asyncio.wait_for(signal.run(ctx), timeout=signal.timeout_s)
        if not isinstance(result, SignalResult):
            result = _failed(signal, "сигнал вернул не SignalResult")
    except asyncio.TimeoutError:
        result = _failed(signal, f"таймаут {signal.timeout_s:.0f} с")
    except Exception as exc:  # любой сбой внешнего сервиса не ломает проверку
        result = _failed(signal, f"ошибка сигнала: {type(exc).__name__}: {exc}"[:200])
    if result.id != signal.id:
        # Контракт: id результата — id сигнала, иначе слияние и адвокаты поедут.
        result = result.model_copy(update={"id": signal.id, "stage": signal.stage})
    return result, (time.monotonic() - started) * 1000


async def run_signals(
    signals: Sequence[Signal],
    ctx: CheckContext,
    on_done: Callable[[SignalEvent], Awaitable[None]] | None = None,
) -> tuple[list[SignalResult], list[str]]:
    """Запускает сигналы параллельно и возвращает результаты и limits."""
    tasks = [asyncio.create_task(_run_one(s, ctx)) for s in signals]
    results: list[SignalResult] = []
    limits: list[str] = []

    for signal, task in zip(signals, tasks):
        result, _ms = await task
        results.append(result)
        if result.verdict.value == "unavailable":
            reason = result.details.get("reason") or result.summary
            limits.append(f"{signal.name}: {reason}")
        if on_done is not None:
            await on_done(SignalEvent(check_id=ctx.check_id, signal=result))

    return results, limits
