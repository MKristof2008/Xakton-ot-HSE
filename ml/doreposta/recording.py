"""Запись и проигрывание пар «промпт/ответ» — воспроизводимость прогонов.

Ничего не решает про качество ответа: позволяет повторно прогнать один и
тот же диалог с моделью без живого API и сравнить результат.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Sequence, Union

from .llm_client import LLMClient, LLMResponse
from .schemas import ModelCallError

Record = dict


def load_records(path: Union[str, Path]) -> list[Record]:
    """Читает JSONL с записями обменов."""
    records: list[Record] = []
    with Path(path).open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


class RecordingLLMClient(LLMClient):
    """Оборачивает клиента и дописывает каждый обмен в JSONL."""

    def __init__(self, inner: LLMClient, path: Union[str, Path]):
        self.inner = inner
        self.path = Path(path)

    async def complete(self, system: str, user: str) -> LLMResponse:
        resp = await self.inner.complete(system, user)
        record = {"system": system, "user": user, "response": resp.text}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        return resp


class ReplayLLMClient(LLMClient):
    """Отвечает из записи по паре (system, user); иначе — ModelCallError."""

    def __init__(self, source: Union[str, Path, Iterable[Record]]):
        records = (load_records(source) if isinstance(source, (str, Path))
                   else list(source))
        self._by_key: dict[tuple[str, str], str] = {}
        for record in records:
            self._by_key[(record["system"], record["user"])] = record["response"]
        self.requests = 0

    async def complete(self, system: str, user: str) -> LLMResponse:
        self.requests += 1
        try:
            text = self._by_key[(system, user)]
        except KeyError as e:
            raise ModelCallError(
                "Нет записи для этого запроса — перезапишите эталон") from e
        return LLMResponse(text)


class SequenceLLMClient(LLMClient):
    """Отдаёт заранее заготовленные ответы по очереди — для тестов."""

    def __init__(self, responses: Sequence[str]):
        self._responses = list(responses)
        self.requests = 0

    async def complete(self, system: str, user: str) -> LLMResponse:
        self.requests += 1
        if not self._responses:
            raise ModelCallError("Заготовленные ответы закончились")
        return LLMResponse(self._responses.pop(0))
