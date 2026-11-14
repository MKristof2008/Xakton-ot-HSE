"""Система тегов: к какому классу относится утверждение.

Зачем это нужно. Модель не должна решать «фейк или нет» из воздуха: сначала
утверждение относится к теме, и дальше проверка идёт по правилам этой темы.
Экономика — по официальным данным, медицина — по Минздраву, происшествие —
по сообщениям ведомств. Тогда «ЦБ запретил наличные» проверяется по базе
ЦБ, а не по случайной выдаче.

Тег ставится детерминированно — по словам и сущностям, без модели. Это
важно: тег должен быть одинаковым на всех тарифах и между прогонами,
иначе вердикт поедет. Модель может уточнить тег, но не заменить его.

Каждый тег знает:
  * где искать (``sources``) — приоритетные домены;
  * какие правила применять (``rules``) — например, для прогнозов запрещено
    выносить «фейк»;
  * насколько тема опасна для репутации (``risk``) — влияет на осторожность.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable


@dataclass(frozen=True)
class Tag:
    """Тема утверждения и правила её проверки."""

    key: str
    title: str
    #: Слова-маркеры. Сравнение идёт по нормализованному тексту.
    keywords: tuple[str, ...]
    #: Приоритетные источники для этой темы (домены).
    sources: tuple[str, ...] = ()
    #: Правила проверки для этой темы.
    rules: tuple[str, ...] = ()
    #: 1 — обычная тема, 3 — высокая цена ошибки (деньги, здоровье, люди).
    risk: int = 1


TAGS: tuple[Tag, ...] = (
    Tag(
        key="finance",
        title="Деньги и ЦБ",
        keywords=(
            "цб", "центробанк", "банк россии", "ключев", "ставк", "наличн",
            "рубл", "валют", "ипотек", "кредит", "вклад", "банк", "доллар",
            "евро", "биржа", "акци",
        ),
        sources=("cbr.ru", "government.ru", "rbc.ru", "tass.ru"),
        rules=("official_only", "numbers_must_match"),
        risk=3,
    ),
    Tag(
        key="law",
        title="Законы и налоги",
        keywords=(
            "налог", "штраф", "закон", "указ", "постановлен", "госдум",
            "запрет", "запретил", "разреш", "обязательн", "госуслуг",
            "мрот", "пенси", "льгот", "выплат", "пособи", "суд",
        ),
        sources=("publication.pravo.gov.ru", "government.ru", "nalog.gov.ru"),
        rules=("official_only", "future_never_fake"),
        risk=3,
    ),
    Tag(
        key="health",
        title="Здоровье и медицина",
        keywords=(
            "врач", "медицин", "лекарств", "препарат", "вакцин", "болезн",
            "вирус", "минздрав", "больниц", "аптек", "здоров", "рака",
            "лечит", "симптом",
        ),
        sources=("minzdrav.gov.ru", "who.int", "rospotrebnadzor.ru"),
        rules=("official_only", "no_miracle_cure"),
        risk=3,
    ),
    Tag(
        key="education",
        title="Образование и экзамены",
        keywords=(
            "егэ", "огэ", "экзамен", "школ", "вуз", "университет",
            "обрнадзор", "просвещен", "студент", "прием", "аттестат",
            "каникул", "урок",
        ),
        sources=("obrnadzor.gov.ru", "edu.gov.ru", "ria.ru"),
        rules=("official_only",),
        risk=2,
    ),
    Tag(
        key="emergency",
        title="Происшествия и ЧС",
        keywords=(
            "пожар", "взрыв", "теракт", "авар", "наводнен", "землетрясен",
            "погибл", "пострадал", "эваку", "чс", "мчс", "дтп", "катастроф",
        ),
        sources=("mchs.gov.ru", "mvd.ru", "tass.ru", "ria.ru"),
        rules=("count_from_official", "future_never_fake"),
        risk=3,
    ),
    Tag(
        key="military",
        title="Армия и мобилизация",
        keywords=(
            "мобилизац", "военн", "арми", "призыв", "миноборон", "сво",
            "военнослуж", "повестк", "фронт",
        ),
        sources=("mil.ru", "government.ru", "tass.ru"),
        rules=("future_never_fake", "official_only"),
        risk=3,
    ),
    Tag(
        key="politics",
        title="Политика и выборы",
        keywords=(
            "выбор", "президент", "депутат", "парламент", "правительств",
            "министр", "партия", "голосован", "референдум", "губернатор",
        ),
        sources=("government.ru", "cikrf.ru", "tass.ru"),
        rules=("official_only",),
        risk=2,
    ),
    Tag(
        key="tech",
        title="Технологии и ИИ",
        keywords=(
            "нейросет", "искусственн", "гаджет", "смартфон", "apple",
            "google", "приложени", "чип", "спутник", "телефон", "интернет",
        ),
        sources=("tass.ru", "rbc.ru", "interfax.ru"),
        risk=1,
    ),
    Tag(
        key="transport",
        title="Транспорт",
        keywords=(
            "метро", "поезд", "самолет", "аэропорт", "мост", "дорог",
            "автобус", "тариф", "билет", "жд", "ржд", "трамва",
        ),
        sources=("tass.ru", "mintrans.gov.ru", "rbc.ru"),
        rules=("official_only",),
        risk=2,
    ),
    Tag(
        key="showbiz",
        title="Звёзды и развлечения",
        keywords=(
            "звезд", "актер", "певиц", "певец", "сериал", "шоу",
            "скандал", "развод", "свадьб", "беременн", "блогер",
        ),
        sources=("tass.ru", "ria.ru"),
        rules=("weak_evidence",),
        risk=1,
    ),
    Tag(
        key="weather",
        title="Погода",
        keywords=(
            "погод", "мороз", "жара", "снег", "ураган", "циклон", "градус",
            "осадк", "гидромет", "заморозк",
        ),
        sources=("meteoinfo.ru", "mchs.gov.ru"),
        rules=("future_never_fake",),
        risk=2,
    ),
)

#: Тег по умолчанию: тема не распознана.
UNKNOWN = Tag(
    key="unknown",
    title="Тема не определена",
    keywords=(),
    rules=("no_sources_no_fake",),
    risk=1,
)

_BY_KEY = {tag.key: tag for tag in TAGS}


@dataclass
class TagMatch:
    """Результат разметки: тег, уверенность и все зацепки."""

    tag: Tag
    score: float = 0.0
    hits: list[str] = field(default_factory=list)

    @property
    def is_confident(self) -> bool:
        return self.tag is not UNKNOWN and self.score >= 1.0

    def as_dict(self) -> dict[str, object]:
        return {
            "key": self.tag.key,
            "title": self.tag.title,
            "score": round(self.score, 2),
            "hits": self.hits,
            "risk": self.tag.risk,
            "rules": list(self.tag.rules),
        }


def _normalize(text: str) -> str:
    return " ".join((text or "").lower().replace("ё", "е").split())


def _hit(keyword: str, text: str) -> bool:
    """Слово найдено как основа слова, а не как случайная подстрока.

    Короткие метки («цб», «чс», «суд») ищем целым словом: иначе «цб»
    находится внутри «руб», а «суд» — внутри «судьба».
    """
    if len(keyword) <= 3:
        return re.search(rf"(?<!\w){re.escape(keyword)}(?!\w)", text) is not None
    return keyword in text


def classify(text: str, extra: Iterable[str] = ()) -> TagMatch:
    """Определить тему утверждения. Без модели и без сети."""
    haystack = _normalize(" ".join([text or "", *extra]))
    if not haystack:
        return TagMatch(UNKNOWN, 0.0)

    best = TagMatch(UNKNOWN, 0.0)
    for tag in TAGS:
        hits = [kw for kw in tag.keywords if _hit(kw, haystack)]
        if not hits:
            continue
        score = float(len(hits))
        if score > best.score:
            best = TagMatch(tag, score, hits)
    return best


def for_key(key: str) -> Tag:
    """Тег по ключу. Неизвестный ключ — тема не определена."""
    return _BY_KEY.get((key or "").strip().lower(), UNKNOWN)


def all_tags() -> list[Tag]:
    return list(TAGS)


def all_keys() -> list[str]:
    return [tag.key for tag in TAGS]
