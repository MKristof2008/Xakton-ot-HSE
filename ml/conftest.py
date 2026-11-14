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
