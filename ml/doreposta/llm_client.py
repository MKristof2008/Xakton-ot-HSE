"""Клиент модели.

Реальный клиент — OpenAI-совместимый chat completions, конфигурируется
через переменные окружения. FakeLLMClient — для тестов без API-ключа.
"""
from __future__ import annotations

import asyncio
import json
import os
import time
import urllib.error
import urllib.request
from typing import Callable, Optional, Union

from .schemas import InvalidResponse, ModelCallError, ModelTimeout

_RETRY_STATUS = frozenset({429, 500, 502, 503, 504})


class LLMResponse:
    __slots__ = ("text",)

    def __init__(self, text: str):
        self.text = text


class LLMClient:
    """Минимальный конфигурируемый клиент chat-completions.

    Секреты — только из окружения:
      LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, LLM_TIMEOUT (секунды),
      LLM_RETRIES (повторы на 429/5xx), LLM_BACKOFF (пауза в секундах).
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[float] = None,
        retries: Optional[int] = None,
        backoff: Optional[float] = None,
    ):
        self.api_key = api_key or os.environ.get("LLM_API_KEY", "")
        self.base_url = (base_url or os.environ.get("LLM_BASE_URL", "")).rstrip("/")
        self.model = model or os.environ.get("LLM_MODEL", "")
        self.timeout = float(timeout or os.environ.get("LLM_TIMEOUT", "60"))
        env_retries = os.environ.get("LLM_RETRIES", "2")
        self.retries = int(retries if retries is not None else env_retries)
        env_backoff = os.environ.get("LLM_BACKOFF", "0.5")
        self.backoff = float(backoff if backoff is not None else env_backoff)
        if not self.api_key or not self.base_url or not self.model:
            raise ModelCallError(
                "LLM-клиент не сконфигурирован: задайте LLM_API_KEY, LLM_BASE_URL, LLM_MODEL"
            )

    async def complete(self, system: str, user: str) -> LLMResponse:
        return await asyncio.wait_for(
            asyncio.to_thread(self._sync_call, system, user),
            timeout=self.timeout,
        )

    def _sync_call(self, system: str, user: str) -> LLMResponse:
        body = json.dumps({
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0,
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/v1/chat/completions",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
        )
        data = None
        last_error: Optional[Exception] = None
        for attempt in range(self.retries + 1):
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                break
            except TimeoutError as e:
                raise ModelTimeout(str(e)) from e
            except urllib.error.HTTPError as e:
                if e.code not in _RETRY_STATUS:
                    raise ModelCallError(str(e)) from e
                last_error = e
            except urllib.error.URLError as e:
                last_error = e
            except Exception as e:
                raise ModelCallError(str(e)) from e
            if attempt < self.retries:
                time.sleep(self.backoff * (attempt + 1))
        else:
            raise ModelCallError(
                f"LLM-сервис недоступен после {self.retries + 1} попыток: {last_error}")
        try:
            return LLMResponse(data["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as e:
            raise InvalidResponse(f"Неожиданная структура ответа API: {e}") from e


# Обработчик: (system_prompt, user_prompt) -> str (сырой ответ модели)
FakeHandler = Callable[[str, str], str]
FakeHandlerAsync = Callable[[str, str], "asyncio.Future[str]"]


class FakeLLMClient:
    """Fake-клиент для тестов без API-ключа.

    Принимает функцию-обработчик или очередь ответов.
    Не является доказательством качества живой модели — только проверяет
    логику пайплайна и обработку ошибок.
    """

    def __init__(self, handler: Union[FakeHandler, list]):
        if isinstance(handler, list):
            queue = list(handler)
            def h(system: str, user: str) -> str:
                if not queue:
                    raise ModelCallError("FakeLLMClient: очередь ответов исчерпана")
                item = queue.pop(0)
                if isinstance(item, Exception):
                    raise item
                return item
            self._handler = h
        else:
            self._handler = handler
        self.calls: list[tuple[str, str]] = []

    async def complete(self, system: str, user: str) -> LLMResponse:
        self.calls.append((system, user))
        result = self._handler(system, user)
        if asyncio.iscoroutine(result):
            result = await result
        return LLMResponse(result)
