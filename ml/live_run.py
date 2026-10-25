"""Live-прогон пайплайна через реальную модель.

Настройка:
  1. aistudio.google.com → Get API key (бесплатно)
  2. Впиши ключ в файл .env рядом с этим скриптом (LLM_API_KEY=...)
     .env в git НЕ коммитится.
  3. Запуск: py -3 live_run.py

Не является unit-тестом: результаты прогона ревьюит человек.
"""
import asyncio
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, ".")

# загрузка .env без python-dotenv
env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(env_path):
    for line in open(env_path, encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

from doreposta import LLMClient, compose_reply, evaluate_claims, extract_claims
from tests.live_cases import CASES


async def run_case(client, case):
    print(f"\n=== {case['name']} ===")
    print(f"Сообщение: {case['message']}")
    extraction = await extract_claims(case["message"], {}, client)
    if not extraction.claims:
        print(f"Утверждений не извлечено. Причина: {extraction.uncheckable_reason}")
        return
    for c in extraction.claims:
        print(f"  claim: {c.text} | missing: {c.missing_context}")
    evaluation = await evaluate_claims(extraction.claims, case["sources"], {}, client)
    for cr in evaluation.claims:
        mark = "OK " if case["expect"] and cr.status.value == case["expect"] else "?? "
        print(f"  {mark}статус: {cr.status.value} (ожидали: {case['expect']})")
        print(f"    объяснение: {cr.explanation}")
        for ev in cr.evidence:
            print(f"    [{ev.relation.value}] «{ev.quote}» ({ev.source_id})")
        for lim in cr.limitations:
            print(f"    ограничение: {lim}")
    print("  --- для чата ---")
    print("  " + compose_reply(evaluation, case["sources"]).replace("\n", "\n  "))


async def main():
    if not os.environ.get("LLM_API_KEY"):
        print("Впиши ключ в .env (LLM_API_KEY=...) и перезапусти.")
        print("Бесплатный ключ: aistudio.google.com → Get API key")
        return
    client = LLMClient()
    print(f"Модель: {client.model} @ {client.base_url}")
    for case in CASES:
        try:
            await run_case(client, case)
        except Exception as e:
            print(f"  ОШИБКА ({type(e).__name__}): {e}")


if __name__ == "__main__":
    asyncio.run(main())
