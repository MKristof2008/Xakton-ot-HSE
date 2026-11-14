import asyncio
import inspect
import sys

import pathlib as _pathlib

_HERE = _pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE.parent))


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
