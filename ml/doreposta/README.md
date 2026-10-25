# До репоста — LLM-пайплайн

Фактчекинг сообщений из чатов: извлечение утверждений, оценка по источникам,
строгая валидация, уточнение для пересылки.

## Структура

- `doreposta/schemas.py` — контракты данных (Pydantic), согласованы с backend/frontend
- `doreposta/llm_client.py` — `LLMClient` (OpenAI-совместимый, env-конфиг) и `FakeLLMClient` для тестов
- `doreposta/prompts.py` — системные промпты A (извлечение) и B (оценка)
- `doreposta/pipeline.py` — `extract_claims`, `evaluate_claims`, `compose_reply`, `validate_result`
- `tests/test_pipeline.py` — 12 обязательных сценариев + обработка ошибок (15 тестов)
- `example.py` — полный прогон без API-ключа

## Запуск

```bash
py -3 -m pytest tests/ -q   # тесты, ключ не нужен
py -3 example.py            # пример end-to-end на fake-модели
```

## Живая модель

Задать переменные окружения (см. `.env.example`, значения пустые):

```
LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, LLM_TIMEOUT
```

и заменить `FakeLLMClient` на `LLMClient()` — интерфейс `complete(system, user)` одинаковый.

## Интеграция с backend

```python
extraction = await extract_claims(message_text, {"message_date": date}, client)
evaluation = await evaluate_claims(extraction.claims, sources_from_backend, {}, client)
reply = compose_reply(evaluation, sources_from_backend)
```

Backend передаёт источники (`Source`), получает `EvaluationResult`.
Модель возвращает `source_id`, URL подставляет backend из своего списка.

## Источники для экономики и крипты (фокус проекта)

Приоритет для backend при поиске материалов:

- **cbr.ru** — Банк России: ставка, регулирование, официальные опровержения
- **РБК** (rbc.ru, в т.ч. РБК Крипто) — экономика и крипторынок
- **РИА Новости / ТАСС** — агентства, официальные заявления
- **Forbes.ru** — крипта, рынки, расследования
- **Яндекс Новости / Google News** — только как агрегаторы для поиска первоисточника,
  сами по себе не доказательство

Перепечатки одной новости дедуплицируются пайплайном (`dedupe_sources`),
поэтому агрегаторы не дают лишних «подтверждений». Live-кейсы по экономике
и крипте: `tests/live_cases.py`, сценарии 8–11.

## Ограничения MVP

- Оценка строится только по переданным материалам, без знаний «из памяти» модели.
- Snippet сам по себе не даёт финальных статусов — понижается до `insufficient`.
- Модель может ошибаться в логической релевантности цитат: дословность проверяется
  детерминированно, смысловая связь — только моделью (см. тест 12).
- Семантическое качество промптов требует live-прогона; fake-тесты проверяют
  только логику пайплайна и обработку ошибок.
