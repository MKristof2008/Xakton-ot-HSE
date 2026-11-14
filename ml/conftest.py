import asyncio
import inspect
import sys
import tempfile

import pathlib as _pathlib

import pytest

_HERE = _pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE.parent))


@pytest.fixture(autouse=True)
def _offline_by_default(monkeypatch):
    """Тесты не ходят в сеть и не пишут в рабочие данные.

    backend/main.py подхватывает ml/.env при импорте, поэтому на машине с
    настоящим ключом тесты начинали звонить живому шлюзу: медленно,
    недетерминированно и за деньги. Здесь ключи убираем — тест, которому
    модель нужна, выставляет их сам через monkeypatch.

    Банк знаний тоже уводим во временную папку: иначе прогон тестов
    пополнял бы рабочий банк, и следующие тесты получали бы ответы из
    него вместо проверки логики.
    """
    for var in ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL",
                "LLM_MODEL_BASE", "LLM_MODEL_PLUS", "LLM_MODEL_MAX",
                "SERPER_API_KEY"):
        monkeypatch.delenv(var, raising=False)

    bank_file = _pathlib.Path(
        tempfile.mkdtemp(prefix="revizor-bank-")
    ) / "bank.json"
    monkeypatch.setenv("VERDICT_BANK", str(bank_file))
    try:
        from lakmus import bank as bank_module

        bank_module.reset(bank_file)
    except Exception:
        pass


#: Готовые заголовки для тестов, которые не хотят зависеть от фикстуры.
#: Раньше часть тестов писала headers=AUTH — такого имени в проекте не было
#: и они падали на ImportError. Теперь оно есть и работает так же, как
#: фикстура auth_headers: аккаунт с тарифом team, без дневного лимита.
def _make_auth() -> dict:
    from fastapi.testclient import TestClient

    from backend.main import app

    client = TestClient(app)
    token = client.post("/api/users").json()["token"]
    client.post("/api/upgrade", json={"plan": "team"}, headers={"X-Token": token})
    return {"X-Token": token}


class _AuthProxy:
    """Ленивые заголовки: к базе обращаемся при первом использовании.

    Важно не создавать аккаунт при импорте conftest: тогда он появится
    до того, как тест выставит свою временную базу (VERDICT_DB).
    """

    _cache: dict | None = None

    def _get(self) -> dict:
        if _AuthProxy._cache is None:
            _AuthProxy._cache = _make_auth()
        return _AuthProxy._cache

    def keys(self):
        return self._get().keys()

    def __getitem__(self, key):
        return self._get()[key]

    def __iter__(self):
        return iter(self._get())

    def __len__(self):
        return len(self._get())

    def get(self, key, default=None):
        return self._get().get(key, default)


AUTH = _AuthProxy()


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
