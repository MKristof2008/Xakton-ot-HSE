"""Провайдеры поиска для «Лакмус».

ML-часть не делает собственный поисковик, но умеет ходить
в backend endpoint другого разработчика, который по запросу
возвращает источники.
"""

from __future__ import annotations

import json as _json
import os
import urllib.error
import urllib.request
from typing import Any, Sequence

from .context import SearchHit, SearchProvider


class BackendSearchProvider(SearchProvider):
    """Поиск через backend endpoint.

    Ожидает, что backend принимает POST с JSON { "query": "..." }
    и возвращает список объектов:
        [
          {
            "id": "s1",
            "title": "...",
            "url": "...",
            "published_at": "...",
            "content": "...",
            "snippet": true/false,
            "domain": "..."
          }
        ]

    Конфигурация через переменные окружения:
        BACKEND_SEARCH_URL  (обязательна)
        BACKEND_API_KEY     (опционально)
    """

    def __init__(
        self,
        url: str | None = None,
        api_key: str | None = None,
        timeout: float = 10.0,
    ):
        self.url = url or os.environ.get("BACKEND_SEARCH_URL", "")
        self.api_key = api_key or os.environ.get("BACKEND_API_KEY", "")
        self.timeout = float(timeout)
        if not self.url:
            raise ValueError("BackendSearchProvider: BACKEND_SEARCH_URL не задан")

    async def search(self, query: str) -> Sequence[SearchHit]:
        body = _json.dumps({"query": query}).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(self.url, data=body, headers=headers, method="POST")

        def _call() -> bytes:
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    return resp.read()
            except urllib.error.HTTPError as exc:
                raise RuntimeError(f"BackendSearchProvider: HTTP {exc.code}") from exc
            except urllib.error.URLError as exc:
                raise RuntimeError(f"BackendSearchProvider: {exc.reason}") from exc

        import asyncio
        raw = await asyncio.to_thread(_call)
        items = _json.loads(raw.decode("utf-8"))
        return [_to_hit(item) for item in items if isinstance(items, list)]


def _to_hit(item: dict[str, Any]) -> SearchHit:
    return SearchHit(
        id=str(item.get("id", "")),
        title=str(item.get("title", "")),
        url=str(item.get("url", "")),
        published_at=item.get("published_at"),
        content=str(item.get("content", "")),
        snippet=bool(item.get("snippet", False)),
        domain=str(item.get("domain", "")),
    )


class FakeSearchProvider(SearchProvider):
    """Фейковый поиск для тестов."""

    def __init__(self, hits: Sequence[SearchHit] | None = None):
        self.hits = list(hits or [])
        self.queries: list[str] = []

    async def search(self, query: str) -> Sequence[SearchHit]:
        self.queries.append(query)
        return self.hits
