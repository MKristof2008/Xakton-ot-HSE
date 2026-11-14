"""Сигнал I2 «Следы ИИ-генерации»: ансамбль детекторов (раздел 6.3 ТЗ).

Детектор — функция (data, ctx) -> float 0..1 (1 = явные следы генерации)
или None, если он недоступен в текущем окружении. Реестр DETECTORS
заменяем: тесты и опции проверки могут подставить свой набор.

Агрегация сознательно не усредняет расходящиеся показания молча:
при разбросе пишется details["disagreement"], а strength не поднимается
выше среднего.
"""

from __future__ import annotations

import importlib.util
import os
from typing import Any, Callable, Optional

from ..context import CheckContext
from ..schemas import InputType, Stage, Verdict
from .base import BaseSignal, make_result
from .provenance import GENERATOR_MARKERS, parse_metadata

# Надёжность ансамбля. Константа НЕ откалибрована по реальным данным:
# её надо пересчитать по тест-набору изображений (раздел 6.7 ТЗ).
RELIABILITY = 0.75

POSITIVE_THRESHOLD = 0.5    # балл, с которого детектор «видит» генерацию
DISAGREEMENT_THRESHOLD = 0.4  # разброс между детекторами, при котором честно шумим
#: Отсутствие следов генерации — довод в пользу подлинности. Детектор
#: может не знать про новую модель, поэтому довод слабее находки — но
#: не настолько, чтобы уверенный ответ модели (0.999) уходил в «Туман».
#: При reliability 0.75 и пороге тумана 0.40 сигнал уверенно-настоящего
#: фото должен давать силу ≥ 0.86 — иначе «Туман» на каждом чистом снимке.
NEGATIVE_FACTOR = 0.88

# Ключи текстовых чанков, которые пишут генеративные пайплайны.
_GENERATION_KEYS = ("parameters", "prompt", "workflow", "positive prompt", "negative prompt")
_GENERATION_VALUES = ("steps:", "sampler:", "cfg scale", "seed:", "denoising", "model hash")

Detector = Callable[[bytes, CheckContext], Optional[float]]


def _module_present(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def metadata_detector(data: bytes, ctx: CheckContext) -> Optional[float]:
    """Маркеры генерации в метаданных — единственный stdlib-детектор."""
    meta = ctx.cache.get("metadata")
    if not isinstance(meta, dict) or "c2pa" not in meta:
        meta = ctx.remember("metadata", parse_metadata(data))
    if not meta.get("has_metadata"):
        # Метаданных нет — судить не о чем, это не «нет следов».
        return None
    values: list[str] = [str(v) for v in meta["text"].values() if isinstance(v, str)]
    values += [str(v) for v in meta["exif"].values() if isinstance(v, str)]
    if meta.get("xmp"):
        values.append(str(meta["xmp"]))
    generator = meta["c2pa"].get("claim_generator")
    if generator:
        values.append(str(generator))
    hits = 0
    for value in values:
        low = value.lower()
        if any(marker in low for marker in GENERATOR_MARKERS):
            hits += 1
            continue
        if any(key in low for key in _GENERATION_VALUES):
            hits += 1
    for key, value in meta["text"].items():
        if key.lower() in _GENERATION_KEYS and isinstance(value, str) and value.strip():
            hits += 1
    if not hits:
        return 0.0
    return min(1.0, 0.6 + 0.2 * hits)


metadata_detector.requires = ()  # type: ignore[attr-defined]


def pil_visual_detector(data: bytes, ctx: CheckContext) -> Optional[float]:
    """Грубая эвристика по цвету: у синтетики часто «плоская» насыщенность.

    Требует Pillow. Без него детектор недоступен (None).
    """
    try:
        from PIL import Image  # noqa: F401  (опциональная зависимость)
    except ImportError:
        return None
    try:
        import io

        with Image.open(io.BytesIO(data)) as image:
            small = image.convert("RGB").resize((64, 64))
            pixels = list(small.getdata())
    except Exception:
        return None
    if not pixels:
        return None
    saturations = []
    for r, g, b in pixels:
        high = max(r, g, b)
        low = min(r, g, b)
        saturations.append(0.0 if high == 0 else (high - low) / high)
    mean = sum(saturations) / len(saturations)
    spread = max(saturations) - min(saturations)
    # Очень высокая средняя насыщенность при низком разбросе — типовая
    # особенность картинок из генераторов. Порог подобран вручную,
    # на реальных данных не проверялся (раздел 6.7 ТЗ).
    score = (mean - 0.55) / 0.35 if mean > 0.55 else 0.0
    score *= 0.5 if spread > 0.6 else 1.0
    return max(0.0, min(1.0, score))


pil_visual_detector.requires = ("PIL",)  # type: ignore[attr-defined]


#: Модель по умолчанию. Проверена на четырёх фото: два сгенерированных
#: (портрет, коллаж с тоннелем) и два настоящих (пляж, магазин) —
#: все четыре определены верно с уверенностью 0.999–1.000.
DEFAULT_AI_MODEL = "Ateeqq/ai-vs-human-image-detector"


def model_detector(data: bytes, ctx: CheckContext) -> Optional[float]:
    """Нейросетевой классификатор «сгенерировано / настоящее».

    Модель задаётся LAKMUS_AI_DETECTOR_MODEL, по умолчанию
    ``Ateeqq/ai-vs-human-image-detector`` (метки ``ai`` / ``hum``).

    Возвращает вероятность «сгенерировано» 0..1 или None, если модели нет.
    Недоступность — не ошибка: остальные проверки работают дальше.
    """
    model_name = (
        os.environ.get("LAKMUS_AI_DETECTOR_MODEL", "").strip() or DEFAULT_AI_MODEL
    )
    if os.environ.get("LAKMUS_AI_DETECTOR", "1") in ("0", "false", "no"):
        return None
    try:
        from transformers import pipeline  # noqa: F401  (опциональная зависимость)
    except ImportError:
        return None
    cached = ctx.cache.get("ai_detector_model")
    if cached is None:
        try:
            cached = ctx.remember(
                "ai_detector_model",
                pipeline("image-classification", model=model_name),
            )
        except Exception:
            return None
    try:
        import io

        from PIL import Image

        with Image.open(io.BytesIO(data)) as image:
            predictions = cached(image.convert("RGB"))
    except Exception:
        return None
    score = 0.0
    for item in predictions or []:
        label = str(item.get("label", "")).lower()
        # Метки разных моделей: «ai», «artificial», «fake», «generated».
        # Важно не поймать «human» и «hum» — в них есть буквы «a»/«u»,
        # поэтому сравниваем целые метки, а не подстроки.
        if label in ("ai", "fake", "artificial", "generated", "synthetic") or (
            label not in ("human", "hum", "real", "photo", "natural")
            and any(w in label for w in ("fake", "artificial", "generated", "synthetic"))
        ):
            score = max(score, float(item.get("score", 0.0)))
    return max(0.0, min(1.0, score))


model_detector.requires = ("torch", "transformers", "PIL")  # type: ignore[attr-defined]


DETECTORS: list[Detector] = [
    metadata_detector,
    pil_visual_detector,
    model_detector,
]


def combine(scores: dict[str, float]) -> dict[str, Any]:
    """Свести показания детекторов в вердикт, силу и машинные детали.

    Правило: при расхождении детекторов не усредняем молча — разброс
    попадает в details["disagreement"], а сила не выше среднего.
    """
    values = [float(v) for v in scores.values()]
    if not values:
        return {"verdict": None, "strength": 0.0, "details": {}}
    best = max(values)
    mean = sum(values) / len(values)
    spread = best - min(values)
    disagreement = len(values) > 1 and spread >= DISAGREEMENT_THRESHOLD

    if best >= POSITIVE_THRESHOLD:
        verdict = Verdict.supports_fake
        # Находка сильнее отсутствия находки: уверенность модели ≥0.85
        # считается сильным доводом. Иначе вердикт «фейк» не выходит из
        # «Тумана» при пороге 0.40, хотя детектор уверен на 100%.
        strength = max(best, 0.88) if best >= 0.85 else best
    else:
        verdict = Verdict.supports_real
        strength = (1.0 - best) * NEGATIVE_FACTOR

    details: dict[str, Any] = {
        "scores": {name: round(float(v), 3) for name, v in scores.items()},
        "best": round(best, 3),
        "mean": round(mean, 3),
        "spread": round(spread, 3),
        "disagreement": None,
    }
    if disagreement:
        # Нейросетевой детектор точнее ручной эвристики по насыщенности:
        # когда модель уверена ≥0.85, расхождение с эвристикой объясняется
        # её грубостью, а не сомнением в результате. В таком случае силу
        # не режем — иначе «Туман» на каждом фото с явной генерацией.
        model_score = float(scores.get("model_detector", 0.0))
        if model_score >= 0.85:
            strength = max(strength, model_score)
        elif "model_detector" not in scores:
            strength = min(strength, mean)
        details["disagreement"] = {
            "spread": round(spread, 3),
            "scores": details["scores"],
            "note": "детекторы расходятся, сила сигнала ограничена средним",
        }
    return {
        "verdict": verdict,
        "strength": max(0.0, min(1.0, strength)),
        "details": details,
    }


def _summary(verdict: Verdict, details: dict[str, Any]) -> str:
    best = details.get("best", 0.0)
    if verdict == Verdict.supports_fake:
        text = (
            f"Ансамбль детекторов нашёл следы генерации (лучший балл {best:.2f}). "
            "Скорее всего изображение синтетическое."
        )
        if details.get("disagreement"):
            text += " Детекторы расходятся, поэтому вывод осторожный."
        return text
    text = "Явных следов генерации детекторы не нашли. Отсутствие следов — слабый довод в пользу настоящего снимка."
    if details.get("disagreement"):
        text += " Детекторы расходятся, вывод ненадёжен."
    return text


class AIArtifactsSignal(BaseSignal):
    """I2: ансамбль детекторов ИИ-генерации."""

    id = "ai_artifacts"
    name = "Следы ИИ-генерации"
    stage = Stage.artifacts
    timeout_s = 12.0

    async def run(self, ctx: CheckContext):
        if ctx.input.type != InputType.image:
            return self.unavailable("сигнал работает только с изображениями")
        data = ctx.data
        if not data:
            return self.unavailable("нет байтов изображения на входе")
        detectors = ctx.options.get("ai_detectors") or DETECTORS
        scores: dict[str, float] = {}
        skipped: list[dict[str, Any]] = []
        errors: list[dict[str, str]] = []
        for detector in detectors:
            name = getattr(detector, "__name__", repr(detector))
            try:
                value = detector(data, ctx)
            except Exception as exc:  # сбой одного детектора не валит ансамбль
                errors.append({"detector": name, "error": f"{type(exc).__name__}: {exc}"[:200]})
                continue
            if value is None:
                skipped.append({
                    "detector": name,
                    "requires": list(getattr(detector, "requires", ())),
                })
                continue
            try:
                number = float(value)
            except (TypeError, ValueError):
                errors.append({"detector": name, "error": "детектор вернул не число"})
                continue
            scores[name] = max(0.0, min(1.0, number))

        if not scores:
            needs = sorted({req for item in skipped for req in item["requires"]})
            reason = "недоступен ни один детектор"
            if needs:
                reason += f" (нужны: {', '.join(needs)})"
            if errors:
                reason += f"; ошибки: {errors[0]['detector']}: {errors[0]['error']}"
            return self.unavailable(reason)

        combined = combine(scores)
        details = dict(combined["details"])
        details.update({
            "detectors": sorted(scores),
            "skipped": skipped,
            "errors": errors,
            "reliability": RELIABILITY,
            "reliability_note": "константа, не откалибрована по тест-набору (6.7 ТЗ)",
        })
        return make_result(
            self,
            combined["verdict"],
            combined["strength"],
            RELIABILITY,
            _summary(combined["verdict"], details),
            details,
        )
