"""Предрасчитанные результаты для demo-режима (раздел 3, 6.9 п.4 ТЗ).

Demo-режим не вызывает модель: он проигрывает заранее посчитанные
``CheckResult`` из каталога ``ml/data/demo``. Файл — ``<check_id>.json``
ровно в формате контракта (``CheckResult.model_dump_json``), поэтому его
можно отдавать frontend тем же путём, что и живой результат.

Задержки. Живая проверка идёт 2–4 секунды, и сигналы приходят по мере
готовности. В demo они уже готовы все сразу, но показывать их разом
нельзя — интерфейс теряет смысл «проверка идёт». :func:`replay_delays`
раздаёт сигналам задержки 200–400 мс, пропорциональные их доле в
``duration_ms``, детерминированно: один и тот же результат всегда
проигрывается одинаково.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from .schemas import CheckResult

#: Границы паузы между появлением сигналов, мс.
MIN_DELAY_MS: int = 200
MAX_DELAY_MS: int = 400

#: Пауза, когда результат не несёт длительности.
DEFAULT_DELAY_MS: int = 300


def demo_path(check_id: str, directory: str | Path) -> Path:
    """Путь файла демо-результата ``<check_id>.json``."""
    return Path(directory) / f"{check_id}.json"


def save_demo(result: CheckResult, directory: str | Path) -> Path:
    """Сохраняет результат как демо-файл и возвращает путь.

    Перед записью вызывается ``validate_contract``: демо обязано быть
    валидным контрактом, иначе frontend покажет то, чего не бывает в
    живом прогоне (например, тезис адвоката без сигналов).
    """
    result.validate_contract()
    target = demo_path(result.id, directory)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(result.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return target


def load_demo(check_id: str, directory: str | Path) -> CheckResult | None:
    """Читает демо-результат или ``None``, если файла нет.

    Битый файл — не «нет файла»: он означает испорченное демо, поэтому
    бросаем ``ValueError`` с путём, а не молча отдаём пустоту.
    """
    target = demo_path(check_id, directory)
    if not target.is_file():
        return None
    try:
        return CheckResult.model_validate_json(target.read_text(encoding="utf-8"))
    except ValidationError as exc:
        raise ValueError(f"демо-файл {target} не соответствует контракту: {exc}") from exc


def list_demo(directory: str | Path) -> list[str]:
    """Список id доступных демо-результатов (по имени файла), по алфавиту."""
    root = Path(directory)
    if not root.is_dir():
        return []
    return sorted(path.stem for path in root.glob("*.json") if path.is_file())


def _weight(signal_id: str, index: int) -> int:
    """Детерминированный вес сигнала: стабилен между запусками и платформами."""
    code_sum = sum(ord(char) for char in signal_id)
    return 1 + (code_sum * 31 + index * 17) % 97


def replay_delays(result: CheckResult) -> list[dict]:
    """Расписание появления сигналов в demo-режиме.

    Каждому сигналу достаётся доля ``duration_ms`` пропорционально его
    весу, но не меньше :data:`MIN_DELAY_MS` и не больше
    :data:`MAX_DELAY_MS` — так demo не выглядит ни мгновенным, ни
    затянутым. Результат — список словарей в порядке сигналов:

    * ``signal_id`` — id сигнала;
    * ``delay_ms`` — пауза перед показом этого сигнала;
    * ``at_ms`` — накопленное время от старта проигрывания.

    Пустой результат без сигналов даёт пустое расписание.
    """
    signals = list(result.signals)
    if not signals:
        return []

    weights = [_weight(signal.id, index) for index, signal in enumerate(signals)]
    total_weight = sum(weights)
    duration = max(0, int(result.duration_ms))

    delays: list[dict] = []
    elapsed = 0
    for signal, weight in zip(signals, weights):
        if duration <= 0:
            delay = DEFAULT_DELAY_MS
        else:
            delay = int(round(duration * weight / total_weight))
        delay = max(MIN_DELAY_MS, min(MAX_DELAY_MS, delay))
        elapsed += delay
        delays.append(
            {"signal_id": signal.id, "delay_ms": delay, "at_ms": elapsed}
        )
    return delays
