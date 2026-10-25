# Xakton-ot-HSE

Репозиторий проекта для хакатона (HSE).

## Описание

Пайплайн проверки утверждений «До репоста»: из сообщения пользователя извлекаются
проверяемые утверждения, backend подбирает источники, модель выносит статус по каждому
утверждению (`supported` / `contradicted` / `context` / `insufficient`), результат
валидируется и превращается в короткое уточнение для пересылки.
Модель возвращает только `source_id` — ссылки подставляет backend из своего списка источников.

## Стек

- Python 3.10+
- Pydantic 2 — схемы данных и валидация
- OpenAI-совместимый chat completions через `urllib` (без SDK)
- pytest — тесты на fake-клиенте, без API-ключа

## Запуск

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt

# тесты (модель не вызывается)
.venv/Scripts/python.exe -m pytest -q

# демонстрация пайплайна
.venv/Scripts/python.exe example.py
```

Переменные окружения (см. `.env.example`): `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`, `LLM_TIMEOUT`.

## Структура

- `doreposta/schemas.py` — схемы `Source`, `Claim`, `ClaimResult`, `EvaluationResult`, ошибки
- `doreposta/prompts.py` — промпты извлечения и оценки утверждений
- `doreposta/llm_client.py` — `LLMClient` (реальная модель) и `FakeLLMClient` (тесты)
- `doreposta/pipeline.py` — `extract_claims`, `evaluate_claims`, `compose_reply`, `validate_result`
- `tests/` — сценарии пайплайна и правила статусов
- `example.py` — сквозной пример на fake-клиенте

## Команда

<!-- Участники и зоны ответственности -->
