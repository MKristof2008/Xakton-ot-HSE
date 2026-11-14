"""Тесты репутации доменов.

Главное, что проверяем: сайт, который публикует выдумки, не может быть
доказательством. И подделка под известный домен не наследует его доверие.
"""

from __future__ import annotations

import pytest

from lakmus.reputation import (
    can_confirm,
    classify,
    describe,
    is_satire,
    normalize_host,
)


# ------------------------------------------------------------ нормализация

@pytest.mark.parametrize(
    "value, expected",
    [
        ("https://cbr.ru/press/pr/?file=x", "cbr.ru"),
        ("http://www.tass.ru/a", "tass.ru"),
        ("www.lenta.ru", "lenta.ru"),
        ("https://user:pass@ria.ru:443/x", "ria.ru"),
        ("CBR.RU", "cbr.ru"),
        ("  https://example.com  ", "example.com"),
        ("", ""),
    ],
)
def test_normalize_host(value, expected):
    assert normalize_host(value) == expected


# --------------------------------------------------------------- классы

def test_official_is_trusted():
    info = classify("https://cbr.ru/press/")
    assert info.reputation == "trusted"
    assert info.can_confirm is True


def test_subdomain_inherits_trust():
    assert classify("https://news.cbr.ru/a").reputation == "trusted"


def test_quality_media_is_trusted():
    assert classify("https://www.kommersant.ru/doc/1").reputation == "trusted"


def test_satire_detected():
    info = classify("https://panorama.pub/2026/11/novost")
    assert info.reputation == "satire"
    assert info.can_confirm is False
    assert info.must_not_be_evidence is True


def test_untrusted_factory_detected():
    info = classify("https://infowars.com/post")
    assert info.reputation == "untrusted"
    assert info.must_not_be_evidence is True


def test_unknown_domain_is_not_trusted():
    info = classify("https://some-random-blog.xyz/post")
    assert info.reputation == "unknown"
    assert info.can_confirm is False
    assert info.must_not_be_evidence is False


def test_empty_is_unknown():
    assert classify("").reputation == "unknown"


# ---------------------------------------------------------------- подделки

def test_lookalike_domain_is_untrusted():
    """cbr.ru.evil.com — это домен evil.com, а не cbr.ru."""
    info = classify("https://cbr.ru.evil.com/press")
    assert info.reputation == "untrusted"
    assert info.can_confirm is False


def test_lookalike_with_hyphen():
    assert classify("https://cbr-ru-news.xyz/").reputation == "untrusted"


def test_cyrillic_homoglyph_is_untrusted():
    info = classify("https://сбербанк.рф/news")
    assert info.reputation == "untrusted"


def test_ip_address_is_unknown():
    assert classify("http://192.168.1.1/news").reputation == "unknown"


# ---------------------------------------------------------------- хелперы

def test_is_satire_helper():
    assert is_satire("https://panorama.pub/x") is True
    assert is_satire("https://cbr.ru/x") is False


def test_can_confirm_helper():
    assert can_confirm("https://tass.ru/x") is True
    assert can_confirm("https://panorama.pub/x") is False
    assert can_confirm("https://unknown.example/x") is False


def test_describe_mentions_satire():
    text = describe("https://panorama.pub/x")
    assert "сатир" in text.lower()


def test_describe_unknown():
    text = describe("https://unknown.example/x")
    assert "не проверен" in text.lower()
