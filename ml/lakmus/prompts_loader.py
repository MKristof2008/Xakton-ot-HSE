"""Загрузка промптов сигналов и адвокатов из /prompts (раздел 6.8 ТЗ).

Промпты лежат обычными .md файлами под версионированием, а не строками в коде:
так правка промпта видна в истории отдельным диффом. Загрузка кешируется —
файл читается один раз на процесс.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

SUFFIX: Final = ".md"
_PROMPTS_DIR: Final = Path(__file__).resolve().parent.parent / "prompts"
_cache: dict[str, str] = {}


class PromptNotFound(FileNotFoundError):
    """Промпта нет в ml/prompts — сигнал обязан вернуть unavailable, а не падать."""


def prompts_dir() -> Path:
    """Каталог с промптами (для диагностики и тестов)."""
    return _PROMPTS_DIR


def available_prompts() -> list[str]:
    """Имена промптов без расширения — то, что лежит в каталоге сейчас."""
    if not _PROMPTS_DIR.is_dir():
        return []
    return sorted(path.stem for path in _PROMPTS_DIR.glob(f"*{SUFFIX}"))


def load_prompt(name: str) -> str:
    """Текст промпта по имени файла без расширения.

    Бросает PromptNotFound с понятным сообщением, если файла нет или он пуст.
    """
    key = str(name or "").strip()
    if not key:
        raise PromptNotFound("пустое имя промпта")
    cached = _cache.get(key)
    if cached is not None:
        return cached
    path = _PROMPTS_DIR / f"{key}{SUFFIX}"
    try:
        text = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError as exc:
        raise PromptNotFound(f"нет файла промпта: {path}") from exc
    if not text:
        raise PromptNotFound(f"файл промпта пуст: {path}")
    _cache[key] = text
    return text


def clear_cache() -> None:
    """Сбрасывает кеш — нужен, если промпты правят во время работы."""
    _cache.clear()
