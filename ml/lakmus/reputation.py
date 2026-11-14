"""Репутация источника: можно ли считать его доказательством.

Зачем отдельный модуль: без него модель видит текст со страницы, которая
специально публикует выдумки, и отвечает «источник подтверждает». Это
худший из возможных провалов — система не просто ошибается, она
подтверждает фейк ссылкой на фейк.

Правила:

  * **trusted**   — государственные, агентства, качественные СМИ;
  * **satire**    — сатирические издания: всё выдумано намеренно;
  * **untrusted** — известные фабрики выдумок;
  * **unknown**   — всё остальное: не доказательство, но и не приговор.

Ключевое: **сам сайт не доказывает ложность своего текста.** Сатирический
домен означает «нельзя использовать как доказательство», а не «каждый факт
в нём ложный». Утверждение всё равно проверяется по независимым источникам.

Поддомены наследуют репутацию родителя, но только в правильную сторону:
`news.cbr.ru` доверенный, `cbr.ru.evil.com` — нет.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

Reputation = Literal["trusted", "satire", "untrusted", "unknown"]

#: Государственные и официальные источники.
OFFICIAL: frozenset[str] = frozenset({
    "government.ru", "kremlin.ru", "mid.ru", "mil.ru", "cbr.ru", "mos.ru",
    "nalog.gov.ru", "rostrud.gov.ru", "mchs.gov.ru", "gosuslugi.ru",
    "publication.pravo.gov.ru", "pravo.gov.ru", "consultant.ru",
    "rosstat.gov.ru", "obrnadzor.gov.ru", "minzdrav.gov.ru",
    "mintrud.gov.ru", "meteorf.gov.ru", "rkn.gov.ru", "fssp.gov.ru",
})

#: Агентства и фактчекинг-проекты.
AGENCIES: frozenset[str] = frozenset({
    "tass.ru", "ria.ru", "interfax.ru", "reuters.com", "apnews.com", "afp.com",
    "factcheck.org", "snopes.com", "politifact.com", "fullfact.org",
    "provereno.media", "stopfake.org", "lapsha.media",
})

#: Качественные СМИ.
QUALITY_MEDIA: frozenset[str] = frozenset({
    "rbc.ru", "kommersant.ru", "vedomosti.ru", "forbes.ru", "rg.ru", "iz.ru",
    "lenta.ru", "gazeta.ru", "meduza.io", "novayagazeta.eu", "theins.ru",
    "bbc.com", "bbc.co.uk", "dw.com", "euronews.com", "theguardian.com",
    "nytimes.com", "washingtonpost.com", "ft.com", "bloomberg.com",
})

#: Сатирические издания: пишут выдумки намеренно, это жанр.
#: Использовать как доказательство нельзя ни при каких формулировках.
SATIRE: frozenset[str] = frozenset({
    "panorama.pub", "panorama.ru", "fognews.ru", "the-onion.com",
    "theonion.com", "clickhole.com", "babylonbee.com", "newsbiscuit.com",
    "dailycurrant.com", "waterfordwhispersnews.com", "thepoke.co.uk",
    "der-postillon.com", "lerelaisdelabonne.fr", "elmundotoday.com",
    "worldnewsdailyreport.com", "huzlers.com", "empirenews.net",
})

#: Известные фабрики выдумок и сайты-подделки под СМИ.
UNTRUSTED: frozenset[str] = frozenset({
    "infowars.com", "beforeitsnews.com", "yournewswire.com",
    "neonnettle.com", "newspunch.com", "thelastlineofdefense.org",
    "react365.com", "doly.co.uk", "realtime24news.com", "awdnews.com",
    "veteranstoday.com", "worldtruth.tv",
})

#: Признаки домена-подделки: «cbr.ru.news-today.xyz» и подобное.
_LOOKALIKE_HINTS: tuple[str, ...] = (
    "cbr-ru", "cbrru", "gosuslugi-", "-gosuslugi", "kremlin-", "-kremlin",
    "tass-", "-tass", "ria-", "-ria", "sberbank-", "-sberbank",
)

_TRUSTED_SET: frozenset[str] = OFFICIAL | AGENCIES | QUALITY_MEDIA

_SCHEME = re.compile(r"^[a-z][a-z0-9+.\-]*://", re.IGNORECASE)
#: Кириллица и прочие не-ASCII в домене — почти всегда подделка под
#: латинское написание (гомоглифы).
_NON_ASCII = re.compile(r"[^\x00-\x7F]")
_IP_LIKE = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")


@dataclass(frozen=True)
class DomainInfo:
    """Результат классификации домена."""

    host: str
    reputation: Reputation
    reason: str

    @property
    def can_confirm(self) -> bool:
        """Может ли этот домен быть подтверждающим доказательством."""
        return self.reputation == "trusted"

    @property
    def must_not_be_evidence(self) -> bool:
        """Домен, который нельзя использовать как доказательство вообще."""
        return self.reputation in ("satire", "untrusted")


def normalize_host(value: str) -> str:
    """Домен из URL или строки: без схемы, пути, порта, логина и www."""
    text = (value or "").strip().lower()
    if not text:
        return ""
    text = _SCHEME.sub("", text)
    text = text.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    text = text.rsplit("@", 1)[-1]
    # порт убираем, но не ломаем IPv6 в скобках
    if text.startswith("["):
        text = text.split("]", 1)[0].strip("[")
    else:
        text = text.split(":", 1)[0]
    text = text.strip(".")
    while text.startswith("www."):
        text = text[4:]
    return text


def _parent_matches(host: str, table: frozenset[str]) -> bool:
    """Совпадает ли домен или его родитель с таблицей.

    `news.cbr.ru` наследует доверие `cbr.ru`. Но `cbr.ru.evil.com` —
    это домен `evil.com` с поддоменами, и он родителю не наследует:
    проверяем только суффиксы, начиная со второго уровня.
    """
    if host in table:
        return True
    parts = host.split(".")
    for index in range(1, len(parts) - 1):
        if ".".join(parts[index:]) in table:
            return True
    return False


def classify(value: str) -> DomainInfo:
    """Определить репутацию домена или URL.

    Никогда не бросает: неизвестный или пустой домен — `unknown`.
    """
    host = normalize_host(value)
    if not host:
        return DomainInfo("", "unknown", "домен не указан")

    if _IP_LIKE.match(host):
        return DomainInfo(host, "unknown", "источник по IP-адресу, а не по домену")

    if _NON_ASCII.search(host):
        return DomainInfo(
            host, "untrusted",
            "в домене нелатинские символы — похоже на подделку под известный сайт",
        )

    if _parent_matches(host, SATIRE):
        return DomainInfo(
            host, "satire",
            "сатирическое издание: материалы выдуманы намеренно и не являются фактами",
        )

    if _parent_matches(host, UNTRUSTED):
        return DomainInfo(
            host, "untrusted",
            "сайт известен публикацией выдумок и не может быть доказательством",
        )

    # Доверенный домен стоит слева от чужого: cbr.ru.evil.com — это
    # домен evil.com, а не cbr.ru. Такая запись всегда подделка.
    for trusted_host in _TRUSTED_SET:
        if host.startswith(trusted_host + ".") and not _parent_matches(host, _TRUSTED_SET):
            return DomainInfo(
                host, "untrusted",
                "домен выдаёт себя за известный источник",
            )

    if any(hint in host for hint in _LOOKALIKE_HINTS):
        return DomainInfo(
            host, "untrusted",
            "домен имитирует адрес известного источника",
        )

    if _parent_matches(host, _TRUSTED_SET):
        if _parent_matches(host, OFFICIAL):
            return DomainInfo(host, "trusted", "официальный источник")
        if _parent_matches(host, AGENCIES):
            return DomainInfo(host, "trusted", "информационное агентство или фактчекер")
        return DomainInfo(host, "trusted", "качественное издание")

    return DomainInfo(host, "unknown", "домен не входит в список проверенных")


def is_satire(value: str) -> bool:
    return classify(value).reputation == "satire"


def can_confirm(value: str) -> bool:
    """Может ли домен подтверждать утверждение."""
    return classify(value).can_confirm


def describe(value: str) -> str:
    """Человеческое объяснение для интерфейса."""
    info = classify(value)
    if info.reputation == "trusted":
        return f"{info.host}: {info.reason}"
    if info.reputation == "satire":
        return f"{info.host}: сатирическое издание, факты в нём выдуманы"
    if info.reputation == "untrusted":
        return f"{info.host}: {info.reason}"
    return f"{info.host}: источник не проверен"
