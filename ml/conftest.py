import asyncio
import inspect
import sys

sys.path.insert(0, ".")
sys.path.insert(0, "ml")


def pytest_pyfunc_call(pyfuncitem):
    # async-тесты без плагина pytest-asyncio
    fn = pyfuncitem.obj
    if inspect.iscoroutinefunction(fn):
        kwargs = {name: pyfuncitem.funcargs[name]
                  for name in pyfuncitem._fixtureinfo.argnames}
        asyncio.run(fn(**kwargs))
        return True
