"""Схемы контракта «Лакмус» (раздел 3 и 6.2 ТЗ).

Контракт един для backend, ML и frontend: JSON Schema экспортируется в
/contracts генератором ml/tools/export_schema.py.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator


class InputType(str, Enum):
    image = "image"
    text = "text"
    url = "url"
    video = "video"


class Stage(str, Enum):
    provenance = "provenance"
    artifacts = "artifacts"
    sources = "sources"
    context = "context"


class Verdict(str, Enum):
    supports_real = "supports_real"
    supports_fake = "supports_fake"
    neutral = "neutral"
    unavailable = "unavailable"


class Level(str, Enum):
    confirmed = "confirmed"
    likely_real = "likely_real"
    fog = "fog"
    doubtful = "doubtful"
    likely_fake = "likely_fake"


class CheckStatus(str, Enum):
    queued = "queued"
    running = "running"
    done = "done"
    failed = "failed"


class Overlay(BaseModel):
    type: Literal["heatmap", "boxes", "regions"] = "heatmap"
    url: str = ""


class SignalResult(BaseModel):
    """Результат одного сигнала. Поля повторяют общий контракт."""

    id: str
    name: str
    stage: Stage
    verdict: Verdict = Verdict.unavailable
    strength: float = Field(0.0, ge=0.0, le=1.0)
    reliability: float = Field(0.0, ge=0.0, le=1.0)
    summary: str = ""
    details: dict[str, Any] = Field(default_factory=dict)
    overlays: list[Overlay] = Field(default_factory=list)

    @field_validator("summary")
    @classmethod
    def _summary_short(cls, v: str) -> str:
        # ТЗ: 1–2 предложения по-русски, без полотна текста.
        return v.strip()[:400]

    @classmethod
    def unavailable(cls, signal_id: str, name: str, stage: Stage, reason: str) -> "SignalResult":
        return cls(
            id=signal_id,
            name=name,
            stage=stage,
            verdict=Verdict.unavailable,
            summary=reason[:200],
            details={"reason": reason},
        )


class Trust(BaseModel):
    score: int = Field(0, ge=0, le=100)
    uncertainty: float = Field(1.0, ge=0.0, le=1.0)
    coverage: float = Field(0.0, ge=0.0, le=1.0)
    level: Level = Level.fog
    conflict: bool = False


class CheckInput(BaseModel):
    type: InputType
    sha256: str = ""
    preview_url: Optional[str] = None
    extracted_text: Optional[str] = None
    # Имя файла: нужно для паспорта и чтобы в отчёте было видно, что проверяли.
    filename: str = ""


class DebateThesis(BaseModel):
    text: str
    signal_ids: list[str] = Field(default_factory=list)


class Debate(BaseModel):
    for_real: list[DebateThesis] = Field(default_factory=list)
    for_fake: list[DebateThesis] = Field(default_factory=list)


class ProvenanceEntry(BaseModel):
    date: Optional[str] = None
    where: str = ""
    note: str = ""


class NextStepKind(str, Enum):
    verify = "verify"
    ask_source = "ask_source"
    hold = "hold"
    share = "share"


class NextStep(BaseModel):
    kind: NextStepKind
    title: str
    why: str = ""


class CheckResult(BaseModel):
    id: str
    status: CheckStatus = CheckStatus.done
    input: CheckInput
    trust: Trust = Field(default_factory=Trust)
    signals: list[SignalResult] = Field(default_factory=list)
    debate: Debate = Field(default_factory=Debate)
    provenance: list[ProvenanceEntry] = Field(default_factory=list)
    next_steps: list[NextStep] = Field(default_factory=list)
    limits: list[str] = Field(default_factory=list)
    duration_ms: int = 0

    def validate_contract(self) -> "CheckResult":
        """Проверки, которые обязаны выполняться на выходе ML."""
        ids = {s.id for s in self.signals}
        if len(ids) != len(self.signals):
            raise ValueError("Дубли id сигналов в результате")
        for side in (self.debate.for_real, self.debate.for_fake):
            for thesis in side:
                if not thesis.signal_ids:
                    raise ValueError(f"Тезис без signal_ids: {thesis.text[:60]!r}")
                unknown = [s for s in thesis.signal_ids if s not in ids]
                if unknown:
                    raise ValueError(f"Тезис ссылается на несуществующие сигналы: {unknown}")
        return self


class SignalEvent(BaseModel):
    """Событие signal_done для SSE (контракт с backend)."""

    type: Literal["signal_done"] = "signal_done"
    check_id: str
    signal: SignalResult
