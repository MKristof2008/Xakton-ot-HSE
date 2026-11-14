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
from .kb_facts import KbFactsSignal
from .quotes import QuotesSignal
from .rhetoric import RhetoricSignal
from .screenshot import ScreenshotSignal
from .source_search import SourceSearchSignal
from .text_claims import ClaimsSignal
from .text_sources import SourcesSignal
from .machine_text import MachineTextSignal
from .video import VideoSignal

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
        KbFactsSignal,
        SourcesSignal,
        QuotesSignal,
        RhetoricSignal,
        MachineTextSignal,
    ],
    "url": [
        ClaimsSignal,
        KbFactsSignal,
        SourcesSignal,
        QuotesSignal,
        RhetoricSignal,
        MachineTextSignal,
    ],
    "video": [
        VideoSignal,
    ],
}


def default_signals(input_type: InputType | str) -> list[Signal]:
    """Возвращает список экземпляров сигналов для данного типа входа.

    У `InputType` (str, Enum) обычный ``str()`` даёт «InputType.image»,
    а не «image»: брать нужно ``.value``, иначе картинка получает
    текстовые сигналы и все они честно отвечают «unavailable».

    Принимает и MIME-тип («image/png»): категория там — первая часть.
    """
    raw = getattr(input_type, "value", input_type)
    key = str(raw).strip().lower()
    if "/" in key:
        key = key.split("/", 1)[0]
    classes = SIGNALS.get(key, SIGNALS["text"])
    return [cls() for cls in classes]


__all__ = [
    "SIGNALS",
    "default_signals",
]
