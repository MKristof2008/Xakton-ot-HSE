"""Сравнение моделей на одном и том же эталонном наборе.

Запуск::

    py -3 -I ml/tools/compare_models.py gpt-4o-mini gpt-4.1-mini gpt-4.1

Печатает таблицу: сколько кейсов модель угадала, среднее время ответа
и сколько раз она вернула невалидный ответ. Выбор модели — по цифрам,
а не по названию.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "ml"))

# Ключи лежат в ml/.env или в корневом .env (в git не попадают).
for candidate in (REPO / "ml" / ".env", REPO / ".env"):
    if candidate.exists():
        for line in candidate.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())

from lakmus.full_pipeline import run_check  # noqa: E402

EVAL_SET = REPO / "ml" / "data" / "eval_set.json"


def load_cases() -> list[dict]:
    return json.loads(EVAL_SET.read_text(encoding="utf-8"))["cases"]


def run_model(model: str, cases: list[dict], limit: int | None) -> dict:
    os.environ["LLM_MODEL"] = model
    # Кэш ответов живёт в процессе — между моделями его надо сбрасывать,
    # иначе вторая модель получит ответы первой и сравнение будет ложным.
    import lakmus.full_pipeline as fp

    fp._CACHE.clear()

    ok = 0
    total = 0
    times: list[int] = []
    errors = 0
    fails: list[dict] = []

    for case in cases[: limit or len(cases)]:
        total += 1
        started = time.monotonic()
        try:
            outcome = asyncio.run(run_check(case["text"]))
            got = outcome.verdict
        except Exception as exc:  # сеть, ключ, что угодно
            errors += 1
            got = f"ошибка: {type(exc).__name__}"
        ms = int((time.monotonic() - started) * 1000)
        times.append(ms)

        if got == case["expect"]:
            ok += 1
        else:
            fails.append({"text": case["text"][:60], "expect": case["expect"],
                          "got": got, "class": case["class"]})

    return {
        "model": model,
        "ok": ok,
        "total": total,
        "accuracy": round(ok / total, 4) if total else 0,
        "avg_ms": int(sum(times) / len(times)) if times else 0,
        "errors": errors,
        "fails": fails,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("models", nargs="+", help="id моделей на шлюзе")
    ap.add_argument("--limit", type=int, default=0, help="сколько кейсов (0 — все)")
    ap.add_argument("--json", action="store_true", help="вывести JSON вместо таблицы")
    args = ap.parse_args()

    if not os.environ.get("LLM_API_KEY"):
        print("Нет LLM_API_KEY: сравнивать нечего.")
        return 2

    cases = load_cases()
    results = [run_model(m, cases, args.limit or None) for m in args.models]

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=1))
        return 0

    print(f"{'модель':28} {'верно':>7} {'точность':>9} {'мс':>6} {'ошибки':>7}")
    print("-" * 62)
    for r in results:
        print(
            f"{r['model']:28} {r['ok']:>3}/{r['total']:<3} "
            f"{r['accuracy'] * 100:>8.1f}% {r['avg_ms']:>6} {r['errors']:>7}"
        )

    for r in results:
        if r["fails"]:
            print(f"\n{r['model']} — провалы:")
            for f in r["fails"]:
                print(f"  [{f['class']}] ждали {f['expect']}, дали {f['got']}: {f['text']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
