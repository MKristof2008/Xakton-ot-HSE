"""Проверка шлюза: какие модели реально отвечают на этом ключе.

Запуск:
    py -3 -I ml/tools/probe_models.py            # список моделей
    py -3 -I ml/tools/probe_models.py gpt-4o-mini gpt-4.1

Печатает: ответила ли модель, сколько токенов, сколько секунд, фрагмент.
Только чтение — в проекте ничего не меняет.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load_env() -> None:
    """Подхватить ml/.env, не перетирая уже заданные переменные."""
    env_file = ROOT / "ml" / ".env"
    if not env_file.is_file():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def _auth() -> tuple[str, str]:
    api_key = os.environ.get("LLM_API_KEY", "")
    base_url = os.environ.get("LLM_BASE_URL", "").rstrip("/")
    return api_key, base_url


def list_models() -> list[str]:
    api_key, base_url = _auth()
    if not (api_key and base_url):
        print("нет LLM_API_KEY или LLM_BASE_URL")
        return []
    request = urllib.request.Request(
        f"{base_url}/v1/models",
        headers={"Authorization": f"Bearer {api_key}"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        print(f"список моделей недоступен: {type(exc).__name__}: {exc}")
        return []
    items = body.get("data") if isinstance(body, dict) else body
    out: list[str] = []
    for item in items or []:
        if isinstance(item, dict) and item.get("id"):
            out.append(str(item["id"]))
    for name in sorted(out):
        print(name)
    print(f"\nвсего: {len(out)}")
    return out


def ask(model: str, question: str) -> dict:
    api_key, base_url = _auth()
    if not (api_key and base_url):
        return {"ok": False, "error": "нет ключа или адреса"}

    payload = json.dumps(
        {
            "model": model,
            "temperature": 0,
            "max_tokens": 120,
            "messages": [{"role": "user", "content": question}],
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url}/v1/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            body = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    seconds = round(time.monotonic() - started, 2)
    try:
        content = str(body["choices"][0]["message"]["content"]).strip()
        tokens = (body.get("usage") or {}).get("completion_tokens", "?")
    except (KeyError, IndexError, TypeError):
        return {"ok": False, "error": f"неожиданный ответ: {str(body)[:200]}"}
    return {"ok": True, "seconds": seconds, "tokens": tokens, "text": content[:160]}


def main() -> int:
    load_env()
    models = sys.argv[1:]
    if not models:
        models = list_models()
        if not models:
            return 1
        # Без аргументов проверяем только текущую модель и первые три.
        current = os.environ.get("LLM_MODEL", "").strip()
        chosen = ([current] if current else []) + models[:3]
        models = list(dict.fromkeys(chosen))

    question = (
        "Ответь по-русски одним предложением: что значит вердикт «непонятно» "
        "в фактчекинге?"
    )
    ok_count = 0
    for model in models:
        result = ask(model, question)
        if result["ok"]:
            ok_count += 1
            print(
                f"OK   {model:30} {result['seconds']:>5}s  "
                f"{result['tokens']:>4} tok  {result['text'][:90]}"
            )
        else:
            print(f"FAIL {model:30} {result['error'][:110]}")
    print(f"\nработают: {ok_count} из {len(models)}")
    return 0 if ok_count else 1


if __name__ == "__main__":
    raise SystemExit(main())
