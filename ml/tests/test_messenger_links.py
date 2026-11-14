"""Ссылки из мессенджеров: главред спрашивал про этот сценарий дважды."""

from __future__ import annotations

import pytest

from lakmus.sources import _og_preview, fetch_page


PAGE_WITH_OG = """
<html><head>
<meta property="og:title" content="ЦБ опроверг слухи о запрете наличных">
<meta property="og:description" content="Банк России заявил, что ограничений не планируется">
</head><body><div id="root"></div></body></html>
"""

PAGE_EMPTY = "<html><head></head><body><div id='root'></div></body></html>"


def test_og_preview_extracts_title_and_description():
    text = _og_preview(PAGE_WITH_OG)
    assert text is not None
    assert "запрете наличных" in text
    assert "не планируется" in text


def test_og_preview_returns_none_on_empty_page():
    assert _og_preview(PAGE_EMPTY) is None


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8000/api/health",
        "http://169.254.169.254/latest/meta-data/",
        "http://192.168.1.1/admin",
        "http://localhost:3000/",
    ],
)
def test_private_hosts_are_not_fetched(url):
    """SSRF: пользовательская ссылка не должна ходить внутрь сети."""
    assert fetch_page(url) is None


def test_non_http_schemes_rejected():
    assert fetch_page("ftp://example.com/x") is None
    assert fetch_page("javascript:alert(1)") is None
