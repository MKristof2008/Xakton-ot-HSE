"""Контекст одной проверки: всё, что сигналы получают на входе."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Protocol, Sequence

from .schemas import CheckInput


@dataclass
class SearchHit:
    """Результат поиска от backend (ML не делает собственный поисковик)."""

    id: str
    title: str
    url: str
    published_at: Optional[str] = None
    content: str = ""
    snippet: bool = False
    domain: str = ""


class SearchProvider(Protocol):
    async def search(self, query: str) -> Sequence[SearchHit]:
        ...


@dataclass
class CheckContext:
    """Один материал на входе проверки.

    data — исходные байты (изображение), text — текст или OCR-расшифровка.
    llm и search необязательны: если backend их не дал, сигнал обязан
    вернуть unavailable, а не падать.
    """

    check_id: str
    input: CheckInput
    data: Optional[bytes] = None
    text: str = ""
    llm: Any = None
    search: Optional[SearchProvider] = None
    options: dict[str, Any] = field(default_factory=dict)
    cache: dict[str, Any] = field(default_factory=dict)

    def remember(self, key: str, value: Any) -> Any:
        self.cache[key] = value
        return value
