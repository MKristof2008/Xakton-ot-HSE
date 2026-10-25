"""Извлечение JSON-объекта из ответа модели.

Своя реализация для «Лакмуса»: ответ может прийти в markdown-заборе, с
пояснением до и после объекта или вовсе без объекта. Никаких догадок —
если объекта нет, это ошибка разбора, а не пустой результат.
"""

from __future__ import annotations

import json
import re

_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.S)


class JSONParseError(ValueError):
    """В ответе модели нет разбираемого JSON-объекта."""


def parse_json_object(raw: str) -> dict:
    """Возвращает первый JSON-объект из текста ответа."""
    text = (raw or "").strip()
    if not text:
        raise JSONParseError("пустой ответ модели")
    fenced = _FENCE.search(text)
    if fenced:
        text = fenced.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise JSONParseError("в ответе модели нет JSON-объекта")
    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError as exc:
        raise JSONParseError(f"невалидный JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise JSONParseError("ожидался JSON-объект")
    return data
