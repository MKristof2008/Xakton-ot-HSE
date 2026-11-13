"""Мост к ML-пайплайну «Лакмус»: контекст, запуск проверки, адаптер сигналов.

Backend не переписывает `CheckResult` — он передаёт контекст и возвращает
то, что отдал ML. Исключение — `default_signals(InputType.image)` в ML
сейчас падает на `str(InputType.image) == "InputType.image"` и подставляешь
текстовые сигналы; здесь это аккуратно чинится обёрткой, без правки ml/.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Callable, Optional

_BACKEND_DIR = Path(__file__).resolve().parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from paths import ML_DIR, REPO_DIR

# Пакет ML импортируется как `ml.lakmus`, значит корень репозитория тоже на пути.
if str(REPO_DIR) not in sys.path:
    sys.path.insert(0, str(REPO_DIR))

if str(ML_DIR) not in sys.path:
    sys.path.insert(0, str(ML_DIR))

from ml.lakmus import signals as _signal_registry  # noqa: E402
from ml.lakmus.context import CheckContext  # noqa: E402
from ml.lakmus.pipeline import check as run_pipeline  # noqa: E402
from ml.lakmus.schemas import CheckInput, CheckResult, InputType, SignalEvent  # noqa: E402

_ORIGINAL_DEFAULT_SIGNALS = _signal_registry.default_signals


def _fixed_default_signals(input_type: Any) -> list[Any]:
    """Снять обёртку `InputType.image` → `"image"` перед выбором сигналов."""
    if hasattr(input_type, "value"):
        input_type = input_type.value
    return _ORIGINAL_DEFAULT_SIGNALS(input_type)


# Патч идемпотентный: повторный импорт не навешивает обёртку на обёртку.
if _signal_registry.default_signals is not _fixed_default_signals:
    _signal_registry.default_signals = _fixed_default_signals


def has_llm() -> bool:
    """LLM подключается только при наличии окружения; ключа нет — работаем без него."""
    return bool(os.environ.get("LLM_API_KEY") and os.environ.get("LLM_BASE_URL"))


def build_context(
    *,
    check_id: str,
    sha256: str,
    preview_url: Optional[str],
    data: bytes,
    text: str,
    caption: str,
    location: str,
    shot_at: Optional[str],
) -> CheckContext:
    """Контекст проверки изображения. OCR не делаем: сигнал сам скажет unavailable."""
    check_input = CheckInput(
        type=InputType.image,
        sha256=sha256,
        preview_url=preview_url,
    )
    options: dict[str, Any] = {
        "caption": caption,
        "location": location,
        "shot_at": shot_at,
    }
    return CheckContext(
        check_id=check_id,
        input=check_input,
        data=data,
        text=text,
        options=options,
    )


async def run_check(
    ctx: CheckContext,
    on_signal_done: Optional[Callable[[SignalEvent], Any]] = None,
) -> CheckResult:
    """Запустить пайплайн. Без LLM спор собирается детерминированным fallback."""
    return await run_pipeline(ctx, llm=None, on_signal_done=on_signal_done)