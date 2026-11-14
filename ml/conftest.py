import asyncio
import inspect
import sys

import pathlib as _pathlib

import pytest

_HERE = _pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE.parent))


@pytest.fixture(autouse=True)
def _offline_by_default(monkeypatch):
    """Тесты не ходят в сеть и не тратят токены.

    backend/main.py подхватывает ml/.env при импорте, поэтому на машине с
    настоящим ключом тесты начинали звонить живому шлюзу: медленно,
    недетерминированно и за деньги. Здесь ключи убираем — тест, которому
    модель нужна, выставляет их сам через monkeypatch.
    """
    for var in ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL",
                "LLM_MODEL_BASE", "LLM_MODEL_PLUS", "LLM_MODEL_MAX",
                "SERPER_API_KEY"):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def auth_headers():
    """Аккаунт с тарифом team: проверки идут только по токену.

    Тариф team снимает дневной лимит free, иначе часть тестов упиралась
    бы в QUOTA_EXCEEDED, а не проверяла то, ради чего написана.
    """
    from fastapi.testclient import TestClient

    from backend.main import app

    client = TestClient(app)
    token = client.post("/api/users").json()["token"]
    client.post("/api/upgrade", json={"plan": "team"}, headers={"X-Token": token})
    return {"X-Token": token}


def pytest_pyfunc_call(pyfuncitem):
    # async-тесты без плагина pytest-asyncio
    fn = pyfuncitem.obj
    if inspect.iscoroutinefunction(fn):
        kwargs = {name: pyfuncitem.funcargs[name]
                  for name in pyfuncitem._fixtureinfo.argnames}
        asyncio.run(fn(**kwargs))
        return True


def pytest_runtest_setup(item):
    """Кэш пайплайна общий на процесс: без сброса тест получал результат
    предыдущего теста на тот же текст и проверял не то, что хотел."""
    try:
        from lakmus.full_pipeline import _CACHE

        _CACHE.clear()
    except Exception:
        pass
