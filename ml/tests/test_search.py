import pytest
from unittest import mock

from lakmus.context import SearchHit
from lakmus.search import BackendSearchProvider, FakeSearchProvider


@pytest.mark.asyncio
async def test_fake_search_provider_returns_hits():
    hits = [
        SearchHit(id="s1", title="t1", url="https://a/1", content="c1"),
        SearchHit(id="s2", title="t2", url="https://a/2", content="c2"),
    ]
    provider = FakeSearchProvider(hits)
    result = await provider.search("запрос")
    assert len(result) == 2
    assert provider.queries == ["запрос"]


@pytest.mark.asyncio
async def test_backend_search_provider_parses_json():
    response_data = b'[{"id":"s1","title":"t","url":"https://a","published_at":"2024-01-01","content":"c","snippet":true,"domain":"a"}]'

    class _FakeResp:
        def read(self):
            return response_data

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    with mock.patch("urllib.request.urlopen", return_value=_FakeResp()):
        provider = BackendSearchProvider(url="https://backend.test/search", api_key="key")
        result = await provider.search("запрос")

    assert len(result) == 1
    hit = result[0]
    assert hit.id == "s1"
    assert hit.title == "t"
    assert hit.url == "https://a"
    assert hit.content == "c"
    assert hit.snippet is True
    assert hit.domain == "a"


def test_backend_search_provider_requires_url():
    with pytest.raises(ValueError):
        BackendSearchProvider(url="")
