"""Почему вердикт может разойтись между уровнями — проверка в лоб.

Запуск: py -3 -I ml/tools/tier_stability.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ml"))


def load_env() -> None:
    env_file = ROOT / "ml" / ".env"
    if not env_file.is_file():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


TEXT = (
    "СРОЧНО! ЦБ запретил снятие наличных с 1 марта 2026 года. "
    "Перешлите всем, кого это касается!"
)


async def main() -> int:
    load_env()
    from lakmus import full_pipeline
    from lakmus.tariffs import BASE, MAX, PLUS

    for tier in (BASE, PLUS, MAX):
        print(f"=== {tier.key} ===")
        for attempt in range(2):
            full_pipeline._CACHE.clear()
            outcome = await full_pipeline.run_check(TEXT, tier=tier)
            statuses = [(c.status, len(c.explanation), bool(c.action), bool(c.resend))
                        for c in outcome.claims]
            print(f"  попытка {attempt + 1}: {outcome.verdict} {statuses}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
