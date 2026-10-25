"""Единый интерфейс сигнала (раздел 6.2 ТЗ)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..context import CheckContext
from ..schemas import SignalResult, Stage


@runtime_checkable
class Signal(Protocol):
    id: str
    name: str
    stage: Stage
    timeout_s: float

    async def run(self, ctx: CheckContext) -> SignalResult:
        ...


class BaseSignal:
    """Удобная база: сигнал объявляет id/name/stage/timeout и run()."""

    id: str = "base"
    name: str = "Сигнал"
    stage: Stage = Stage.artifacts
    timeout_s: float = 9.0

    def unavailable(self, reason: str) -> SignalResult:
        return SignalResult.unavailable(self.id, self.name, self.stage, reason)


def make_result(
    signal: BaseSignal,
    verdict,
    strength: float,
    reliability: float,
    summary: str,
    details: dict | None = None,
    overlays=None,
) -> SignalResult:
    return SignalResult(
        id=signal.id,
        name=signal.name,
        stage=signal.stage,
        verdict=verdict,
        strength=max(0.0, min(1.0, strength)),
        reliability=max(0.0, min(1.0, reliability)),
        summary=summary,
        details=details or {},
        overlays=overlays or [],
    )
