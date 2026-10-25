"""Валидация результата проверки по JSON Schema.

Схема экспортирована генератором ``ml/tools/export_schema.py`` и хранится в
``contracts/check_result.schema.json``. Этот модуль гарантирует, что
``CheckResult`` на выходе ML соответствует общему контракту.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from jsonschema import ValidationError, validate

if TYPE_CHECKING:
    from .schemas import CheckResult


# Путь к JSON Schema относительно корня репозитория.
DEFAULT_SCHEMA_PATH = Path(__file__).resolve().parents[2] / "contracts" / "check_result.schema.json"


def _load_schema(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"JSON Schema не найдена: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def validate_check_result(result: "CheckResult | dict[str, Any]", *, schema_path: str | Path | None = None) -> "CheckResult":
    """Проверить ``result`` по JSON Schema контракта.

    Parameters
    ----------
    result:
        Готовый результат проверки либо уже сериализованный dict.
    schema_path:
        Путь к ``check_result.schema.json``. По умолчанию ищется
        ``contracts/check_result.schema.json`` в корне репозитория.

    Returns
    -------
    CheckResult
        Тот же объект, который был передан.

    Raises
    ------
    ValueError
        Если результат не соответствует схеме.
    FileNotFoundError
        Если схема не найдена.
    """
    from .schemas import CheckResult  # noqa: F401

    if isinstance(result, dict):
        data = result
    else:
        data = result.model_dump(mode="json")

    path = Path(schema_path) if schema_path else DEFAULT_SCHEMA_PATH
    schema = _load_schema(path)

    try:
        validate(instance=data, schema=schema)
    except ValidationError as exc:
        raise ValueError(f"CheckResult не прошёл валидацию по JSON Schema: {exc.message}") from exc

    return result
