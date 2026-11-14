"""Живая проверка трёх тарифов на настоящем ключе модели.

Запуск:
    py -3 -I ml/tools/live_tiers.py "текст сообщения"

Что делает: прогоняет один и тот же текст через три уровня тарифа и
печатает, что вернулось — вердикт, длину объяснения, цитату, «что делать».
Так видно, что база отвечает коротко, плюс даёт разбор, макс — полный.
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


DEFAULT_TEXT = (
    "СРОЧНО! ЦБ запретил снятие наличных с 1 марта 2026 года. "
    "Перешлите всем, кого это касается!"
)


async def main() -> int:
    load_env()
    text = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_TEXT

    from lakmus.full_pipeline import run_check
    from lakmus.tariffs import BASE, MAX, PLUS

    print(f"Текст: {text[:100]}...\n")
    for tier in (BASE, PLUS, MAX):
        print(f"=== {tier.key.upper()} (модель {tier.model('LLM_MODEL')}) ===")
        outcome = await run_check(text, tier=tier)
        print(f"вердикт:      {outcome.verdict} / {outcome.level} ({outcome.score})")
        print(f"режим:        {outcome.mode}, источников: {outcome.sources_used}")
        for claim in outcome.claims:
            print(f"— утверждение: {claim.text[:90]}")
            print(f"  статус:      {claim.status}")
            print(f"  объяснение:  {len(claim.explanation)} симв. {claim.explanation[:160]}")
            if claim.quote:
                print(f"  цитата:      {claim.quote[:120]}")
            if claim.action:
                print(f"  что делать:  {claim.action[:160]}")
            if claim.resend:
                print(f"  пересылка:   {claim.resend[:160]}")
        print(f"время:        {outcome.duration_ms} мс\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
