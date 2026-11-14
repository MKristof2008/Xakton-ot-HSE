"""Диагностика: что именно отвечает модель на каждом уровне.

Запуск: py -3 -I ml/tools/tier_debug.py "утверждение"
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


async def main() -> int:
    load_env()
    claim = sys.argv[1] if len(sys.argv) > 1 else (
        "ЦБ запретил снятие наличных с 1 марта 2026 года"
    )

    from lakmus import llm_pipeline
    from lakmus.tariffs import BASE, MAX, PLUS

    for tier in (BASE, PLUS, MAX):
        system, user = llm_pipeline.EVALUATE_NO_SOURCES_SYSTEM, f"УТВЕРЖДЕНИЕ: {claim}"
        system = system + llm_pipeline._depth_suffix(tier)
        raw = await llm_pipeline._post(system, user, tier=tier)
        print(f"=== {tier.key} (max_tokens={tier.max_tokens}) ===")
        print(f"raw: {raw!r}")
        print(f"json: {llm_pipeline._json_from(raw or '')}")
        print(f"текстовый разбор: {llm_pipeline._status_from_text(raw or '')}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
