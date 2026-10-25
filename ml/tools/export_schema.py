"""Генератор JSON Schema контракта (раздел 3 ТЗ).

Схема собирается из pydantic-модели, а не пишется руками: единственный
источник истины — ``ml/lakmus/schemas.py``. Результат кладётся в
``contracts/`` в корне репозитория, откуда его читают backend и frontend.

Запуск::

    python ml/tools/export_schema.py
    python ml/tools/export_schema.py --out contracts
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ML_ROOT = REPO_ROOT / "ml"
if str(ML_ROOT) not in sys.path:
    sys.path.insert(0, str(ML_ROOT))

from lakmus.schemas import CheckResult  # noqa: E402  (путь к ml/ нужен до импорта)

#: Имя файла схемы в каталоге контрактов.
SCHEMA_NAME = "check_result.schema.json"


def build_schema() -> dict:
    """JSON Schema результата проверки ``CheckResult``."""
    return CheckResult.model_json_schema()


def export(destination: str | Path | None = None) -> Path:
    """Пишет схему в каталог (по умолчанию ``<корень репозитория>/contracts``)."""
    target_dir = Path(destination) if destination is not None else REPO_ROOT / "contracts"
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / SCHEMA_NAME
    path.write_text(
        json.dumps(build_schema(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Экспорт JSON Schema контракта CheckResult (ТЗ раздел 3)"
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="каталог для схемы (по умолчанию contracts/ в корне репозитория)",
    )
    args = parser.parse_args(argv)
    path = export(args.out)
    print(f"Схема контракта записана: {path}")
    print(f"Модель: CheckResult, свойств верхнего уровня: {len(build_schema().get('properties', {}))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
