"""Обход SSRF: адрес 127.0.0.1 записывают не только точками."""

from __future__ import annotations

import pytest

from lakmus.sources import _is_private_host, _parse_ipv4, domain_of


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",
        "http://0x7f000001/",          # hex-запись 127.0.0.1
        "http://2130706433/",          # десятичная запись 127.0.0.1
        "http://0177.0.0.1/",          # восьмеричная запись
        "http://[::1]/",
        "http://localhost/",
        "http://LOCALHOST:8080/",
        "http://10.0.0.5/",
        "http://192.168.1.1/",
        "http://172.16.0.1/",
        "http://172.31.255.1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://100.64.0.1/",
        "http://0.0.0.0/",
    ],
)
def test_private_addresses_blocked(url):
    assert _is_private_host(url), f"{url} должен считаться локальным"


@pytest.mark.parametrize(
    "url",
    [
        "https://cbr.ru/press/",
        "https://www.rbc.ru/story",
        "http://172.32.0.1/",   # вне диапазона 172.16-31
        "https://8.8.8.8/",
    ],
)
def test_public_addresses_allowed(url):
    assert not _is_private_host(url), f"{url} должен считаться публичным"


def test_ipv4_parser_handles_forms():
    assert _parse_ipv4("127.0.0.1") == (127, 0, 0, 1)
    assert _parse_ipv4("0x7f000001") == (127, 0, 0, 1)
    assert _parse_ipv4("2130706433") == (127, 0, 0, 1)
    assert _parse_ipv4("0177.0.0.1") == (127, 0, 0, 1)
    assert _parse_ipv4("example.com") is None
    assert _parse_ipv4("999.1.1.1") is None


def test_domain_of_strips_only_www_prefix():
    """lstrip("www.") срезал любые из символов: w3.org превращался в 3.org."""
    assert domain_of("https://www.rbc.ru/a") == "rbc.ru"
    assert domain_of("https://w3.org/x") == "w3.org"
    assert domain_of("https://wow.ru/x") == "wow.ru"
    assert domain_of("https://cbr.ru:8443/x") == "cbr.ru"
    assert domain_of("https://cbr.ru/x?y=1") == "cbr.ru"
