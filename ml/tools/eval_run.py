"""Прогон эталонного набора: качество проверки по классам ошибок.

Запуск:
    python -m ml.tools.eval_run              # только база, без сети
    python -m ml.tools.eval_run --with-llm   # с LLM и поиском (медленно)

Зачем: видеть, какие классы кейсов проваливаются, а не только общий счёт.
«9 из 13» ничего не говорит о причине; «проваливается класс news_fake»
говорит сразу, что править.

Отчёт: сводка по классам, каждый провал с вердиктом и пояснением.
Сохраняется в ml/data/eval_report.json для истории.
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import os
import pathlib
import sys
import time
from typing import Any

ML_DIR = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ML_DIR))

from lakmus.full_pipeline import CheckOutcome, run_check  # noqa: E402

SET_PATH = ML_DIR / "data" / "eval_set.json"
REPORT_PATH = ML_DIR / "data" / "eval_report.json"


def load_env() -> None:
    for candidate in (ML_DIR.parent / ".env", ML_DIR / ".env"):
        if not candidate.exists():
            continue
        for line in candidate.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())


def load_cases() -> list[dict[str, str]]:
    data = json.loads(SET_PATH.read_text(encoding="utf-8"))
    return data.get("cases", [])


async def run_case(case: dict[str, str]) -> dict[str, Any]:
    text = case["text"]
    expect = case["expect"]
    started = time.monotonic()
    try:
        outcome: CheckOutcome = await run_check(text)
        got = outcome.verdict
        explanation = outcome.claims[0].explanation if outcome.claims else ""
        status = outcome.claims[0].status if outcome.claims else ""
        sources = outcome.sources_used
        mode = outcome.mode
    except Exception as exc:  # провал пайплайна — тоже провал кейса
        got, explanation, status, sources, mode = (
            "ОШИБКА", f"{type(exc).__name__}: {exc}"[:200], "", 0, "",
        )
    return {
        "text": text,
        "class": case.get("class", ""),
        "expect": expect,
        "got": got,
        # «?» — кейс без строгого ожидания: проверяем только, что
        # пайплайн не падает и даёт валидный вердикт.
        "ok": (got in ("правда", "фейк", "непонятно")) if expect == "?" else got == expect,
        "status": status,
        "explanation": explanation[:200],
        "sources": sources,
        "mode": mode,
        "ms": int((time.monotonic() - started) * 1000),
    }


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    by_class: dict[str, dict[str, int]] = {}
    for item in results:
        cls = item["class"] or "?"
        bucket = by_class.setdefault(cls, {"total": 0, "ok": 0})
        bucket["total"] += 1
        bucket["ok"] += 1 if item["ok"] else 0

    total = len(results)
    ok = sum(1 for r in results if r["ok"])
    times = sorted(r["ms"] for r in results)
    return {
        "total": total,
        "ok": ok,
        "accuracy": round(ok / total, 3) if total else 0.0,
        "by_class": {
            name: {**v, "accuracy": round(v["ok"] / v["total"], 3)}
            for name, v in sorted(by_class.items())
        },
        "median_ms": times[len(times) // 2] if times else 0,
        "max_ms": times[-1] if times else 0,
    }


def print_report(results: list[dict[str, Any]], summary: dict[str, Any]) -> None:
    print(f"\n{'кейс':<52} {'класс':<12} {'ждали':<10} {'получили':<11} мс")
    print("-" * 96)
    for item in results:
        mark = "OK " if item["ok"] else "!! "
        print(
            f"{mark}{item['text'][:48]:<50} {item['class']:<12} "
            f"{item['expect']:<10} {item['got']:<11} {item['ms']}"
        )

    print("\n=== ПО КЛАССАМ ===")
    for name, stats in summary["by_class"].items():
        bar = "█" * int(stats["accuracy"] * 10)
        print(f"  {name:<14} {stats['ok']}/{stats['total']}  {stats['accuracy']:.0%} {bar}")

    print(
        f"\nИТОГО: {summary['ok']}/{summary['total']} "
        f"({summary['accuracy']:.0%}) · медиана {summary['median_ms']} мс · "
        f"макс {summary['max_ms']} мс"
    )

    fails = [r for r in results if not r["ok"]]
    if fails:
        print("\n=== ПРОВАЛЫ ===")
        for item in fails:
            print(f"  [{item['class']}] {item['text'][:54]}")
            print(f"     ждали «{item['expect']}», дали «{item['got']}» [{item['status']}]")
            print(f"     {item['explanation'][:150]}")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Прогон эталонного набора")
    parser.add_argument("--with-llm", action="store_true", help="включить LLM и поиск")
    parser.add_argument("--json", action="store_true", help="сохранить отчёт в файл")
    args = parser.parse_args()

    # Строгий режим включается переменной STRICT_NOT_FOUND, по умолчанию он
    # уже включён в самом пайплайне.
    if not args.with_llm:
        # Офлайн-режим: только база. Ключи не загружаем, чтобы прогон был
        # быстрым и детерминированным.
        os.environ.pop("LLM_API_KEY", None)
        os.environ.pop("SERPER_API_KEY", None)
    else:
        load_env()

    cases = load_cases()
    results = [await run_case(case) for case in cases]
    summary = summarize(results)
    print_report(results, summary)

    if args.json:
        REPORT_PATH.write_text(
            json.dumps(
                {"summary": summary, "results": results,
                 "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"\nОтчёт сохранён: {REPORT_PATH}")


if __name__ == "__main__":
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    asyncio.run(main())