# Зона ML — пайплайн «До репоста»

Всё, что относится к LLM-пайплайну, схемам, проверке результата и тестам.
HTTP API, поиск и получение страниц — в `backend/`; frontend — отдельно.

## Состав

- `doreposta/schemas.py` — схемы `Source`, `Claim`, `ClaimResult`, `EvaluationResult`, ошибки
- `doreposta/prompts.py` — промпты извлечения и оценки утверждений
- `doreposta/llm_client.py` — `LLMClient` (реальная модель) и `FakeLLMClient` (тесты)
- `doreposta/pipeline.py` — `extract_claims`, `evaluate_claims`, `compose_reply`, `validate_result`
- `tests/` — сценарии пайплайна, правила статусов, набор live-кейсов
- `example.py` — сквозной пример на fake-клиенте (без ключа)
- `live_run.py` — прогон на живой модели

## Запуск

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r ml/requirements.txt

cd ml
../.venv/Scripts/python.exe -m pytest -q      # тесты без API-ключа
../.venv/Scripts/python.exe example.py        # демонстрация пайплайна
../.venv/Scripts/python.exe live_run.py       # только с LLM_API_KEY
```

Из корня репозитория те же тесты запускаются как `pytest -q` (корневой `conftest.py`
добавляет `ml/` в `sys.path`).

Переменные окружения: `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`, `LLM_TIMEOUT`
(шаблон — `.env.example` в корне).
