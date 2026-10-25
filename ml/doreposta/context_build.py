"""Сборка блока источников для промпта: лимит размера и обрезка текста."""
from __future__ import annotations

from typing import Sequence

from . import checks
from .schemas import Source

SOURCE_CHAR_LIMIT = 4000
MAX_SOURCES = 6

_TEMPLATE = '<source id="{id}" kind="{kind}" origin="{origin}" title="{title}"{published}>\n{content}\n</source>'


def sources_block(sources: Sequence[Source], queries: Sequence[str] = ()) -> tuple[str, set[str]]:
    """Готовит материалы для промпта, обрезая слишком длинные тексты.

    Возвращает (блок, id источников, которые были усечены).
    """
    parts = []
    truncated: set[str] = set()
    for source in sources:
        content, was_cut = checks.truncate_content(source.content, queries, SOURCE_CHAR_LIMIT)
        if was_cut:
            truncated.add(source.id)
        published = f' published_at="{source.published_at}"' if source.published_at else ""
        parts.append(_TEMPLATE.format(
            id=source.id,
            kind=source.content_kind.value,
            origin=source.origin.value,
            title=source.title,
            published=published,
            content=content,
        ))
    return "\n\n".join(parts), truncated
