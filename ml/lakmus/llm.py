"""Кэширование и воспроизведение LLM-вызовов для «Лакмус».

Позволяет сохранять ответы модели во время разработки и тестов,
а затем перезапускать пайплайн без повторных запросов к API.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class _LLMClient(Protocol):
    async def complete(self, system: str, user: str) -> Any:
        ...


def _text(response: Any) -> str:
    return str(getattr(response, "text", response))


def _key(system: str, user: str) -> str:
    return hashlib.sha256((system + "\n" + user).encode("utf-8")).hexdigest()


@dataclass
class _Record:
    key: str
    system: str
    user: str
    response: str


def _to_records(raw: Any) -> list[_Record]:
    if not isinstance(raw, list):
        return []
    records: list[_Record] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        key = item.get("key") or _key(item.get("system", ""), item.get("user", ""))
        records.append(_Record(key=key, system=item.get("system", ""), user=item.get("user", ""), response=item.get("response", "")))
    return records


class RecordingLLMClient:
    """Обёртка вокруг LLM-клиента: записывает каждый вызов.

    Пример:
        real = LLMClient()
        rec = RecordingLLMClient(real)
        await rec.complete("system", "user")
        rec.save("calls.json")
    """

    def __init__(self, client: _LLMClient, records: list[dict[str, str]] | None = None):
        self._client = client
        self._calls: list[_Record] = []
        if records:
            for rec in _to_records(records):
                self._calls.append(rec)

    async def complete(self, system: str, user: str) -> Any:
        response = await self._client.complete(system, user)
        self._calls.append(_Record(key=_key(system, user), system=system, user=user, response=_text(response)))
        return response

    def save(self, path: str | Path) -> None:
        """Сохранить записи в JSON-файл (перезаписывает)."""
        data = [{"key": r.key, "system": r.system, "user": r.user, "response": r.response} for r in self._calls]
        Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    @property
    def calls(self) -> list[_Record]:
        return list(self._calls)


class ReplayLLMClient:
    """Воспроизводит ранее записанные ответы модели.

    Если запрос не найден, можно:
      - передать `fallback` клиент и включить запись;
      - или получить исключение.
    """

    def __init__(
        self,
        path: str | Path,
        *,
        fallback: _LLMClient | None = None,
        record: bool = False,
    ):
        self._records: dict[str, str] = {}
        self._fallback = fallback
        self._record = record and fallback is not None
        self._recorder: RecordingLLMClient | None = None
        if record and fallback is not None:
            self._recorder = RecordingLLMClient(fallback)
        self._load(path)

    def _load(self, path: str | Path) -> None:
        p = Path(path)
        if not p.exists():
            return
        for rec in _to_records(json.loads(p.read_text(encoding="utf-8"))):
            self._records[rec.key] = rec.response

    async def complete(self, system: str, user: str) -> Any:
        key = _key(system, user)
        if key in self._records:
            return _LLMResponse(self._records[key])
        if self._recorder is not None:
            response = await self._recorder.complete(system, user)
            self._records[key] = _text(response)
            return response
        if self._fallback is not None:
            return await self._fallback.complete(system, user)
        raise RuntimeError("ReplayLLMClient: запрос не найден и fallback отключён")

    def save(self, path: str | Path) -> None:
        """Сохранить текущий кэш, включая новые записи от fallback."""
        if self._recorder is not None and self._recorder.calls:
            self._recorder.save(path)


@dataclass
class _LLMResponse:
    text: str


def replay_response(text: str) -> _LLMResponse:
    return _LLMResponse(text)
