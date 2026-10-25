"""Слияние сигналов — субъективная логика Йосанга (раздел 6.6 ТЗ).

Все формулы и пороги живут здесь и читаются из FUSION_CONFIG, чтобы
frontend мог показывать те же числа на странице «Метод».
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from .schemas import Level, SignalResult, Stage, Trust, Verdict

# Пороги из раздела 3 и 6.6 ТЗ. Единственный источник истины.
FUSION_CONFIG: dict[str, float | dict[str, float]] = {
    "strong_belief": 0.6,       # b_i > 0.6 или d_j > 0.6 → конфликт
    "conflict_uncertainty_bonus": 0.2,
    "coverage_floor": 0.5,      # при coverage < 0.5 ...
    "uncertainty_floor": 0.45,  # ... uncertainty не ниже 0.45
    "fog_threshold": 0.40,
    "confirmed_score": 80.0,
    "level_bands": {"likely_real": 60.0, "doubtful": 35.0},
    "provenance_reliability": 0.8,  # «сильный сигнал происхождения»
}


@dataclass(frozen=True)
class Opinion:
    """Мнение (b, d, u): вера в «настоящее», вера в «подделку», неопределённость."""

    b: float = 0.0
    d: float = 0.0
    u: float = 1.0

    def __post_init__(self) -> None:
        total = self.b + self.d + self.u
        if abs(total - 1.0) > 1e-9:
            raise ValueError(f"b + d + u != 1: {total}")

    @classmethod
    def from_signal(cls, signal: SignalResult) -> "Opinion":
        if signal.verdict == Verdict.supports_real:
            b = signal.strength * signal.reliability
            return cls(b=b, d=0.0, u=1.0 - b)
        if signal.verdict == Verdict.supports_fake:
            d = signal.strength * signal.reliability
            return cls(b=0.0, d=d, u=1.0 - d)
        # neutral и unavailable ничего не добавляют, но не ломают расчёт.
        return cls(b=0.0, d=0.0, u=1.0)

    @property
    def probability(self) -> float:
        return self.b + 0.5 * self.u


def cumulative_fusion(left: Opinion, right: Opinion) -> Opinion:
    """Попарное cumulative fusion из 6.6."""
    kappa = left.u + right.u - left.u * right.u
    if kappa <= 1e-12:
        # Оба мнения абсолютно уверены и противоположны: усредняем веру.
        b = (left.b + right.b) / 2
        d = (left.d + right.d) / 2
        return Opinion(b=b, d=d, u=0.0)
    b = (left.b * right.u + right.b * left.u) / kappa
    d = (left.d * right.u + right.d * left.u) / kappa
    u = (left.u * right.u) / kappa
    return _normalize(b, d, u)


def _normalize(b: float, d: float, u: float) -> Opinion:
    b = max(0.0, min(1.0, b))
    d = max(0.0, min(1.0, d))
    u = max(0.0, min(1.0, u))
    total = b + d + u
    if total <= 0:
        return Opinion()
    if abs(total - 1.0) > 1e-9:
        b, d, u = b / total, d / total, u / total
    return Opinion(b=b, d=d, u=u)


def fuse_opinions(opinions: Sequence[Opinion]) -> Opinion:
    if not opinions:
        return Opinion()
    result = opinions[0]
    for opinion in opinions[1:]:
        result = cumulative_fusion(result, opinion)
    return result


def has_conflict(signals: Iterable[SignalResult]) -> bool:
    strong = FUSION_CONFIG["strong_belief"]
    opinions = [Opinion.from_signal(s) for s in signals]
    return any(o.b > strong for o in opinions) and any(o.d > strong for o in opinions)


def has_provenance_anchor(signals: Iterable[SignalResult]) -> bool:
    """C2PA или найденный первоисточник — условие уровня «Подтверждено»."""
    floor = FUSION_CONFIG["provenance_reliability"]
    for signal in signals:
        if signal.stage != Stage.provenance:
            continue
        if signal.verdict == Verdict.supports_real and signal.reliability >= floor:
            return True
    return False


def level_for(score: int, uncertainty: float, conflict: bool, anchored: bool) -> Level:
    """Порядок проверки условий важен (раздел 3 ТЗ)."""
    if uncertainty > FUSION_CONFIG["fog_threshold"] or conflict:
        return Level.fog
    if score >= FUSION_CONFIG["confirmed_score"] and anchored:
        return Level.confirmed
    bands = FUSION_CONFIG["level_bands"]
    if score >= bands["likely_real"]:
        return Level.likely_real
    if score >= bands["doubtful"]:
        return Level.doubtful
    return Level.likely_fake


def coverage_of(signals: Sequence[SignalResult]) -> float:
    if not signals:
        return 0.0
    worked = sum(1 for s in signals if s.verdict != Verdict.unavailable)
    return worked / len(signals)


def fuse(signals: Sequence[SignalResult]) -> Trust:
    """Сигналы → trust (score, uncertainty, coverage, level, conflict)."""
    opinions = [Opinion.from_signal(s) for s in signals]
    merged = fuse_opinions(opinions)
    score = round(100 * merged.probability)
    uncertainty = merged.u
    coverage = coverage_of(signals)
    conflict = has_conflict(signals)

    if conflict:
        uncertainty = min(1.0, uncertainty + FUSION_CONFIG["conflict_uncertainty_bonus"])
    if coverage < FUSION_CONFIG["coverage_floor"]:
        uncertainty = max(uncertainty, FUSION_CONFIG["uncertainty_floor"])

    score = max(0, min(100, score))
    level = level_for(score, uncertainty, conflict, has_provenance_anchor(signals))
    return Trust(
        score=score,
        uncertainty=round(uncertainty, 4),
        coverage=round(coverage, 4),
        level=level,
        conflict=conflict,
    )
