"""CLI оценки качества на размеченном наборе (раздел 6.7 ТЗ).

Печатает счётчики манифеста, метрики прогона и текстовую кривую
«риск–покрытие». Графических библиотек нет и не будет: ASCII-достаточно,
зато скрипт работает в любом терминале и в CI.

Запуск::

    python ml/tools/eval.py --dataset ml/data/labels_example.jsonl
    python ml/tools/eval.py --dataset ml/data/labels_example.jsonl \\
        --results ml/data/results_example.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ML_ROOT = Path(__file__).resolve().parents[1]
if str(ML_ROOT) not in sys.path:
    sys.path.insert(0, str(ML_ROOT))

from lakmus.dataset import (  # noqa: E402  (путь к ml/ нужен до импорта)
    dataset_stats,
    load_dataset,
    validate_dataset,
)
from lakmus.metrics import (  # noqa: E402
    FOG_THRESHOLD,
    risk_coverage_curve,
    summarize_benchmark,
    to_binary,
)

DEFAULT_DATASET_PATH = ML_ROOT / "data" / "labels_example.jsonl"
DEFAULT_RESULTS_PATH = ML_ROOT / "data" / "results_example.jsonl"


def _pct(value: float) -> str:
    return f"{100.0 * value:.1f}%"


def _read_results(path: Path) -> list[dict]:
    """Читает JSONL результатов: id, label, score, uncertainty, level."""
    rows: list[dict] = []
    with path.open(encoding="utf-8") as handle:
        for lineno, line in enumerate(handle, 1):
            text = line.strip()
            if not text or text.startswith("#"):
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{lineno}: невалидный JSON: {exc.msg}") from exc
            if not isinstance(payload, dict):
                raise ValueError(f"{path}:{lineno}: ожидался JSON-объект")
            if "id" not in payload or "score" not in payload:
                raise ValueError(
                    f"{path}:{lineno}: нужны поля id и score "
                    "(плюс label, uncertainty, level)"
                )
            rows.append(payload)
    return rows


def _print_dataset(path: Path, cases) -> None:
    report = validate_dataset(cases)
    stats = dataset_stats(cases)
    print(f"Набор: {path}")
    print(f"  объектов {report['total']} (минимум ТЗ {report['min_total']})")
    parts = [f"{name} {count}" for name, count in report["by_category"].items()]
    print("  " + "  ".join(parts))
    print(
        f"  изображений {stats['images']}, текстов {stats['texts']}, "
        f"неоднозначных {stats['ambiguous']}"
    )
    if stats["by_generator"]:
        generators = ", ".join(
            f"{name} {count}" for name, count in stats["by_generator"].items()
        )
        print(f"  генераторы: {generators}")
    if report["warnings"]:
        print("  предупреждения:")
        for warning in report["warnings"]:
            print(f"    - {warning}")
    else:
        print("  набор соответствует минимумам ТЗ")
    print()


def _print_metrics(summary: dict) -> None:
    print(
        f"Метрики (n={summary['n']}, настоящее {summary['positives']}, "
        f"подделка {summary['negatives']})"
    )
    print(f"  AUC (ROC)              {summary['auc']:.4f}")
    print(f"  Brier                  {summary['brier']:.4f}")
    print(f"  ECE (10 бинов)         {summary['ece']:.4f}")
    print(f"  Selective accuracy     {summary['selective_accuracy']:.4f}")
    print(f"  Покрытие (не Туман)    {_pct(summary['coverage'])}")
    print(f"  Доля Тумана            {_pct(summary['fog_share'])}")
    print(
        "  Туман на неоднозначных "
        f"{_pct(summary['fog_share_ambiguous'])} (порог u > {FOG_THRESHOLD})"
    )
    print(
        "  ориентиры: AUC 1.0 — идеал; ECE <= 0.10 — вероятностям можно верить;"
        " selective accuracy считает только ответы вне Тумана"
    )
    print()


def _print_curve(curve: list[dict]) -> None:
    print("Кривая риск–покрытие (сначала самые уверенные, бар — точность)")
    print("  покрытие   точность    риск   порог u")
    for row in curve:
        bar = "#" * int(round(row["accuracy"] * 10))
        print(
            f"  {_pct(row['coverage']):>8}   {_pct(row['accuracy']):>8}   "
            f"{_pct(row['risk']):>6}   {row['uncertainty_threshold']:.2f}  {bar}"
        )
    print()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Метрики «Лакмуса» на размеченном наборе (ТЗ 6.7)"
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=DEFAULT_DATASET_PATH,
        help="манифест набора, JSONL (по умолчанию ml/data/labels_example.jsonl)",
    )
    parser.add_argument(
        "--results",
        type=Path,
        default=None,
        help="результаты прогона, JSONL (по умолчанию ml/data/results_example.jsonl)",
    )
    parser.add_argument(
        "--steps", type=int, default=10, help="точек на кривой риск–покрытие"
    )
    args = parser.parse_args(argv)

    try:
        cases = load_dataset(args.dataset)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Ошибка набора: {exc}", file=sys.stderr)
        return 2

    results_path = args.results or DEFAULT_RESULTS_PATH
    try:
        results = _read_results(results_path)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Ошибка результатов: {exc}", file=sys.stderr)
        print(
            f"Подсказка: укажите --results или создайте {DEFAULT_RESULTS_PATH}",
            file=sys.stderr,
        )
        return 2

    _print_dataset(args.dataset, cases)

    by_id = {case.id: case for case in cases}
    records: list[dict] = []
    unknown: list[str] = []
    for row in results:
        case = by_id.get(str(row["id"]))
        label = case.label if case is not None else row.get("label")
        if case is None:
            unknown.append(str(row["id"]))
        if label is None:
            print(
                f"Ошибка результатов: у {row['id']} нет метки, "
                "а в наборе такого id нет",
                file=sys.stderr,
            )
            return 2
        records.append(
            {
                "id": row["id"],
                "label": label,
                "category": case.category if case is not None else row.get("category"),
                "score": row["score"],
                "uncertainty": row.get("uncertainty", 1.0),
                "level": row.get("level"),
            }
        )

    covered = {str(row["id"]) for row in results}
    missing = [case.id for case in cases if case.id not in covered]
    print(
        f"Результаты: {results_path} — {len(results)} строк, "
        f"размечено в наборе {len(results) - len(unknown)}"
    )
    if unknown:
        print(f"  нет в разметке: {', '.join(unknown)}")
    if missing:
        print(f"  без результата: {len(missing)} ({', '.join(missing)})")
    print()

    summary = summarize_benchmark(records)
    _print_metrics(summary)
    _print_curve(
        risk_coverage_curve(
            [record["score"] for record in records],
            [to_binary(record["label"]) for record in records],
            [float(record["uncertainty"]) for record in records],
            steps=args.steps,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
