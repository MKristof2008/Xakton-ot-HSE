"""Семантические сценарии для live-прогона модели (не unit-тесты!).

Прогон через живую модель показывает качество промптов A/B.
Fake-клиент это НЕ проверяет — только логику пайплайна.

Формат: (сообщение, источники, ожидаемый статус первого утверждения).
Ожидания — ориентир для ревью человеком, не жёсткий assert.
"""
from doreposta import ContentKind, Source

CASES = [
    # 1. прямое подтверждение
    {
        "name": "supported: дата совпадает",
        "message": "Метро на Сокольнической линии продлили до Рощино, открытие 3 марта 2025!",
        "sources": [Source(id="s1", title="Мэрия", url="https://example.com/1",
                           content="Открытие станции Рощино Сокольнической линии состоялось 3 марта 2025 года.",
                           content_kind=ContentKind.page)],
        "expect": "supported",
    },
    # 2. прямое противоречие
    {
        "name": "contradicted: дата не та",
        "message": "Фестиваль света пройдёт 5 июня, все приходите!",
        "sources": [Source(id="s1", title="Афиша", url="https://example.com/2",
                           content="Фестиваль света перенесён с 5 июня на 19 июня из-за погодных условий.",
                           content_kind=ContentKind.page)],
        "expect": "contradicted",
    },
    # 3. пропущенное ограничение
    {
        "name": "context: все vs только второй курс",
        "message": "Всем студентам вуза повысят стипендию на 20%!",
        "sources": [Source(id="s1", title="Приказ", url="https://example.com/3",
                           content="Стипендия повышается на 20% студентам второго курса очной формы обучения.",
                           content_kind=ContentKind.page)],
        "expect": "context",
    },
    # 4. только snippet
    {
        "name": "insufficient: один snippet",
        "message": "Препарат продлили до 2030 года.",
        "sources": [Source(id="s1", title="Поисковая выдача", url="https://example.com/4",
                           content="…препарат продлён до…",
                           content_kind=ContentKind.snippet)],
        "expect": "insufficient",
    },
    # 5. мнение — утверждений нет
    {
        "name": "нет утверждений: мнение",
        "message": "Лучший сериал года, всем смотреть!",
        "sources": [],
        "expect": None,  # 0 claims
    },
    # 6. «завтра» без даты
    {
        "name": "извлечение: завтра без даты не конкретизируется",
        "message": "Завтра перекроют центр города из-за марафона",
        "sources": [],
        "expect": None,
    },
    # 7. нерелевантный источник
    {
        "name": "insufficient: источник не про то",
        "message": "Цены на билеты в кино вырастут вдвое с мая.",
        "sources": [Source(id="s1", title="Другое", url="https://example.com/7",
                           content="В городе открыли новый каток в парке.",
                           content_kind=ContentKind.page)],
        "expect": "insufficient",
    },
]
