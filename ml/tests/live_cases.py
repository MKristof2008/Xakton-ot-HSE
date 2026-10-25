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
                           content="Открытие станции Рощино Сокольнической линии запланировано на 3 марта 2025 года.",
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
        "expect": "insufficient",  # дата сообщения неизвестна — не проверяется
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
    # 8. экономика: ставка ЦБ подтверждена
    {
        "name": "supported: ставка ЦБ (cbr.ru + РБК)",
        "message": "Центробанк поднял ключевую ставку до 21% — деньги кончаются!",
        "sources": [
            Source(id="s1", title="Банк России", url="https://cbr.ru/press/keypr/",
                   content="Совет директоров Банка России принял решение повысить ключевую ставку до 21,00% годовых.",
                   content_kind=ContentKind.page),
            Source(id="s2", title="РБК", url="https://rbc.ru/economics/stavka",
                   content="ЦБ повысил ключевую ставку до 21% годовых, это максимум с 2003 года.",
                   content_kind=ContentKind.page),
        ],
        "expect": "supported",
    },
    # 9. экономика: фейк про отмену наличных
    {
        "name": "contradicted: наличные не отменяют (РИА + ЦБ)",
        "message": "С 1 января в России запрещают наличные деньги, срочно снимайте!",
        "sources": [
            Source(id="s1", title="РИА Новости", url="https://ria.ru/economy/nal",
                   content="Банк России опроверг сообщения о запрете наличных: такие планы не обсуждаются.",
                   content_kind=ContentKind.page),
            Source(id="s2", title="Банк России", url="https://cbr.ru/press/nal",
                   content="ЦБ сообщил, что информация о запрете наличных расчётов с 1 января не соответствует действительности.",
                   content_kind=ContentKind.page),
        ],
        "expect": "contradicted",
    },
    # 10. крипта: источник опровергает обобщение (Forbes)
    {
        "name": "contradicted: биткоин «обвалился» — только на одной бирже",
        "message": "Биткоин рухнул на 40% за час, крипте конец!",
        "sources": [
            Source(id="s1", title="Forbes", url="https://forbes.ru/crypto/btc",
                   content="На единственной бирже BTC-E из-за технического сбоя котировки биткоина briefly отображались на 40% ниже рынка; на остальных крупнейших биржах цена изменилась менее чем на 2%.",
                   content_kind=ContentKind.page),
        ],
        "expect": "contradicted",
    },
    # 11. крипта: конфликт источников (Яндекс.Новости-агрегатор vs Google News-агрегатор)
    {
        "name": "insufficient: конфликт про регулирование крипты",
        "message": "Майнинг в России полностью запретили с этого месяца.",
        "sources": [
            Source(id="s1", title="Агрегатор новостей", url="https://news.example.com/1",
                   content="Подписан закон, ограничивающий майнинг в отдельных регионах в пиковые часы; полный запрет не вводится.",
                   content_kind=ContentKind.page),
            Source(id="s2", title="РБК Крипто", url="https://rbc.ru/crypto/mining",
                   content="Закон легализует майнинг для юрлиц из реестра, но региональные ограничения в пиковые часы сохраняются.",
                   content_kind=ContentKind.page),
        ],
        "expect": "contradicted",  # источники явно опровергают полный запрет
    },
]
