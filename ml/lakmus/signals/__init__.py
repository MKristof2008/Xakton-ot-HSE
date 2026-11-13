"""Реестр сигналов «Лакмус».

Сигналы разделены по типу входного материала. Для `url` используется
текстовый набор, потому что backend должен предоставить извлечённый текст;
ML-часть не выполняет сетевые запросы самостоятельно.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .base import Signal

from ..schemas import InputType
from .ai_artifacts import AIArtifactsSignal
from .manipulation import ManipulationSignal
from .pricing import PricingSignal
from .provenance import MetadataSignal
from .quotes import QuotesSignal
from .rhetoric import RhetoricSignal
from .screenshot import ScreenshotSignal
from .source_search import SourceSearchSignal
from .text_claims import ClaimsSignal
from .text_sources import SourcesSignal
from .machine_text import MachineTextSignal
from .uniqueness import UniquenessSignal

SIGNALS: dict[str, list[type]] = {
    "image": [
        MetadataSignal,
        AIArtifactsSignal,
        ManipulationSignal,
        SourceSearchSignal,
        ScreenshotSignal,
        UniquenessSignal,
        PricingSignal,
    ],
    "text": [
        ClaimsSignal,
        SourcesSignal,
        QuotesSignal,
        RhetoricSignal,
        MachineTextSignal,
        PricingSignal,
    ],
    "url": [
        ClaimsSignal,
        SourcesSignal,
        QuotesSignal,
        RhetoricSignal,
        MachineTextSignal,
    ],
}


def default_signals(input_type: InputType | str) -> list[Signal]:
    """Возвращает список экземпляров сигналов для данного типа входа."""
    # str(InputType.image) в Python 3.11+ даёт "InputType.image" — берём value.
    raw = getattr(input_type, "value", input_type)
    key = str(raw).lower().split("/")[-1]
    classes = SIGNALS.get(key, SIGNALS["text"])
    return [cls() for cls in classes]


__all__ = [
    "SIGNALS",
    "default_signals",
]
