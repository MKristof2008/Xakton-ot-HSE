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
from .provenance import MetadataSignal
from .quotes import QuotesSignal
from .rhetoric import RhetoricSignal
from .screenshot import ScreenshotSignal
from .source_search import SourceSearchSignal
from .text_claims import ClaimsSignal
from .text_sources import SourcesSignal
from .machine_text import MachineTextSignal

SIGNALS: dict[str, list[type]] = {
    "image": [
        MetadataSignal,
        AIArtifactsSignal,
        ManipulationSignal,
        SourceSearchSignal,
        ScreenshotSignal,
    ],
    "text": [
        ClaimsSignal,
        SourcesSignal,
        QuotesSignal,
        RhetoricSignal,
        MachineTextSignal,
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
    classes = SIGNALS.get(str(input_type).lower().split("/")[-1], SIGNALS["text"])
    return [cls() for cls in classes]


__all__ = [
    "SIGNALS",
    "default_signals",
]
