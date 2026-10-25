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
.venv/Scripts/python.exe -m pip install -r ml/requirements.txt

# тесты (модель не вызывается), из корня репозитория
.venv/Scripts/python.exe -m pytest -q

# демонстрация пайплайна
cd ml && ../.venv/Scripts/python.exe example.py
```

Переменные окружения (см. `.env.example`): `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`, `LLM_TIMEOUT`.

## Структура

- `ml/` — зона ML: LLM-пайплайн, схемы, проверка результата, тесты (см. `ml/README.md`)
  - `ml/doreposta/schemas.py` — схемы `Source`, `Claim`, `ClaimResult`, `EvaluationResult`, ошибки
  - `ml/doreposta/prompts.py` — промпты извлечения и оценки утверждений
  - `ml/doreposta/llm_client.py` — `LLMClient` (реальная модель) и `FakeLLMClient` (тесты)
  - `ml/doreposta/pipeline.py` — `extract_claims`, `evaluate_claims`, `compose_reply`, `validate_result`
  - `ml/tests/` — сценарии пайплайна, правила статусов, live-кейсы
  - `ml/example.py`, `ml/live_run.py` — пример на fake-клиенте и прогон на живой модели
- `backend/` — HTTP API, поиск и получение страниц (зона backend)

## Команда

<!-- Участники и зоны ответственности -->
