"""Брокер SSE-событий проверки.

Пайплайн публикует события через `on_signal_done`, подписчик SSE читает их из
своей `asyncio.Queue`. События копятся и в буфере заявки: тот, кто подключился
позже (или переподключился), получает всю историю, а не пустоту.

Формат SSE: имя события — `stage_started` / `signal_done` / `done` / `error`,
данные — JSON с полем `kind` (`status`, `signal`, `done`, `error`), чтобы
frontend мог разбирать поток единообразно.
"""

from __future__ import annotations

import asyncio
from typing import Any

#: Сколько событий держим в буфере на одну заявку.
MAX_BUFFER = 200


class EventBroker:
    """Подписки на события заявок в памяти процесса."""

    def __init__(self) -> None:
        self._queues: dict[str, list[asyncio.Queue]] = {}
        self._buffers: dict[str, list[dict[str, Any]]] = {}
        self._finished: set[str] = set()

    def publish(self, offer_id: str, event: dict[str, Any]) -> None:
        buffer = self._buffers.setdefault(offer_id, [])
        buffer.append(event)
        if len(buffer) > MAX_BUFFER:
            del buffer[: len(buffer) - MAX_BUFFER]
        if event.get("kind") in ("done", "error"):
            self._finished.add(offer_id)
        for queue in list(self._queues.get(offer_id, [])):
            queue.put_nowait(event)

    def subscribe(self, offer_id: str) -> asyncio.Queue:
        """Новая подписка с проигрыванием уже случившихся событий."""
        queue: asyncio.Queue = asyncio.Queue()
        for event in self._buffers.get(offer_id, []):
            queue.put_nowait(event)
        self._queues.setdefault(offer_id, []).append(queue)
        return queue

    def unsubscribe(self, offer_id: str, queue: asyncio.Queue) -> None:
        queues = self._queues.get(offer_id)
        if not queues:
            return
        if queue in queues:
            queues.remove(queue)
        if not queues:
            self._queues.pop(offer_id, None)

    def is_finished(self, offer_id: str) -> bool:
        return offer_id in self._finished

    def forget(self, offer_id: str) -> None:
        """Забыть историю (используется в тестах)."""
        self._buffers.pop(offer_id, None)
        self._finished.discard(offer_id)


#: Общий брокер процесса. Тесты подменяют его через reset().
broker = EventBroker()


def reset_broker() -> None:
    global broker
    broker = EventBroker()


def sse_frame(event: str, payload: dict[str, Any]) -> str:
    """Кадр SSE: имя события + data в одну строку JSON."""
    import json

    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event}\ndata: {data}\n\n"


def status_event(kind: str, **fields: Any) -> dict[str, Any]:
    """Событие status/stage_started (frontend ждёт `kind: status`)."""
    event: dict[str, Any] = {"kind": kind}
    event.update({key: value for key, value in fields.items() if value is not None})
    return event