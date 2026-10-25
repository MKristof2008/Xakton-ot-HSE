"""Сигнал I3 «Следы монтажа»: ELA / copy-move / двойное сжатие (раздел 6.3 ТЗ).

Все детекторы опциональны: без Pillow и OpenCV сигнал возвращает
unavailable с понятной причиной, а не ломает проверку.

По ТЗ это «подсказка, а не доказательство»: reliability ограничена
0.3–0.5, вердикт supports_fake возможен, supports_real — нет.
"""

from __future__ import annotations

import importlib.util
import io
import os
from typing import Any, Callable, Optional

from ..context import CheckContext
from ..schemas import InputType, Overlay, Stage, Verdict
from .base import BaseSignal, make_result

# Следы монтажа — слабое указание. Границы из ТЗ.
RELIABILITY_MIN = 0.3
RELIABILITY_MAX = 0.5
POSITIVE_THRESHOLD = 0.5

Detector = Callable[[bytes, CheckContext], Optional[dict[str, Any]]]


def _present(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def missing_dependencies() -> list[str]:
    """Чего не хватает для ELA/copy-move/двойного сжатия."""
    missing = []
    if not _present("PIL"):
        missing.append("PIL")
    if not (_present("cv2") and _present("numpy")):
        missing.append("cv2+numpy")
    return missing


def ela_detector(data: bytes, ctx: CheckContext) -> Optional[dict[str, Any]]:
    """Error Level Analysis: пересохранение JPEG и карта разницы."""
    try:
        from PIL import Image, ImageChops, ImageEnhance
    except ImportError:
        return None
    try:
        with Image.open(io.BytesIO(data)) as source:
            original = source.convert("RGB")
    except Exception:
        return None
    try:
        buffer = io.BytesIO()
        original.save(buffer, "JPEG", quality=90)
        buffer.seek(0)
        with Image.open(buffer) as recompressed:
            diff = ImageChops.difference(original, recompressed.convert("RGB"))
    except Exception:
        return None
    gray = diff.convert("L")
    histogram = gray.histogram()
    total = sum(histogram) or 1
    hot = sum(histogram[64:]) / total       # доля «горячих» пикселей
    mean = sum(i * count for i, count in enumerate(histogram)) / total
    score = min(1.0, 0.6 * hot * 4 + 0.4 * (mean / 32.0))
    heatmap = ImageEnhance.Brightness(gray).enhance(8.0)
    return {
        "score": max(0.0, min(1.0, score)),
        "mean_diff": round(mean, 3),
        "hot_ratio": round(hot, 4),
        "heatmap": heatmap,
    }


def copy_move_detector(data: bytes, ctx: CheckContext) -> Optional[dict[str, Any]]:
    """Copy-move: похожие дескрипторы у далеко разнесённых фрагментов."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        return None
    try:
        buffer = np.frombuffer(data, np.uint8)
        image = cv2.imdecode(buffer, cv2.IMREAD_GRAYSCALE)
        if image is None:
            return None
        orb = cv2.ORB_create(nfeatures=2000)
        keypoints, descriptors = orb.detectAndCompute(image, None)
        if descriptors is None or len(keypoints) < 20:
            return {"score": 0.0, "matches": 0}
        matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
        pairs = matcher.knnMatch(descriptors, descriptors, k=3)
    except Exception:
        return None
    suspicious = 0
    for candidates in pairs:
        if len(candidates) < 2:
            continue
        first, second = candidates[1], candidates[2] if len(candidates) > 2 else candidates[1]
        if first.distance > 32:
            continue
        p1 = keypoints[first.queryIdx].pt
        p2 = keypoints[second.trainIdx].pt
        if abs(p1[0] - p2[0]) + abs(p1[1] - p2[1]) > 24:  # далеко друг от друга
            suspicious += 1
    ratio = suspicious / max(1, len(pairs))
    return {"score": max(0.0, min(1.0, ratio * 3.0)), "matches": suspicious}


def double_jpeg_detector(data: bytes, ctx: CheckContext) -> Optional[dict[str, Any]]:
    """Двойное JPEG-сжатие: периодичность сетки блоков 8x8.

    Грубая оценка без DCT-гистограмм: сравниваем средний перепад на
    границах блоков и внутри блоков. Двойное сжатие делает сетку рваной.
    """
    if not data.startswith(b"\xff\xd8"):
        return None  # приём имеет смысл только для JPEG
    try:
        import cv2
        import numpy as np
    except ImportError:
        return None
    try:
        image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_GRAYSCALE)
    except Exception:
        return None
    if image is None:
        return None
    try:
        column_diff = np.abs(np.diff(image.astype(np.int16), axis=1)).mean(axis=0)
        row_diff = np.abs(np.diff(image.astype(np.int16), axis=1)).mean(axis=1)
    except Exception:
        return None
    grid = [column_diff[i] for i in range(7, len(column_diff), 8)]
    off_grid = [column_diff[i] for i in range(len(column_diff)) if i % 8 != 7]
    if not grid or not off_grid:
        return None
    grid_mean = float(np.mean(grid))
    off_mean = float(np.mean(off_grid)) or 1e-6
    ratio = grid_mean / off_mean
    row_spread = float(np.std(row_diff)) if len(row_diff) else 0.0
    score = 0.0
    if ratio > 1.6:  # сетка слишком выражена для одинарного сжатия
        score = min(1.0, (ratio - 1.6) / 1.4)
    if row_spread > 18:
        score = max(score, min(1.0, row_spread / 40.0))
    return {"score": max(0.0, min(1.0, score)), "grid_ratio": round(ratio, 3)}


DETECTORS: list[Detector] = [ela_detector, copy_move_detector, double_jpeg_detector]


def _save_heatmap(heatmap: Any, ctx: CheckContext) -> Optional[str]:
    """Сохранить heatmap в overlay_dir и вернуть URL для фронтенда.

    Без overlay_dir overlay не создаётся: сигнал не хранит файлы сам.
    """
    directory = ctx.options.get("overlay_dir")
    if not directory or heatmap is None:
        return None
    try:
        os.makedirs(directory, exist_ok=True)
        name = f"{ctx.check_id}-manipulation.png"
        heatmap.convert("L").save(os.path.join(directory, name), "PNG")
    except Exception:
        return None
    prefix = str(ctx.options.get("overlay_url_prefix", "/overlays")).rstrip("/")
    return f"{prefix}/{name}"


class ManipulationSignal(BaseSignal):
    """I3: следы монтажа — подсказка, не доказательство."""

    id = "manipulation"
    name = "Следы монтажа"
    stage = Stage.artifacts
    timeout_s = 20.0

    async def run(self, ctx: CheckContext):
        if ctx.input.type != InputType.image:
            return self.unavailable("сигнал работает только с изображениями")
        data = ctx.data
        if not data:
            return self.unavailable("нет байтов изображения на входе")
        detectors = ctx.options.get("manipulation_detectors") or DETECTORS
        scores: dict[str, float] = {}
        raw: dict[str, Any] = {}
        overlays: list[Overlay] = []
        errors: list[dict[str, str]] = []
        skipped: list[str] = []
        for detector in detectors:
            name = getattr(detector, "__name__", repr(detector))
            try:
                outcome = detector(data, ctx)
            except Exception as exc:
                errors.append({"detector": name, "error": f"{type(exc).__name__}: {exc}"[:200]})
                continue
            if not isinstance(outcome, dict) or outcome.get("score") is None:
                skipped.append(name)
                continue
            scores[name] = max(0.0, min(1.0, float(outcome["score"])))
            metrics = {key: value for key, value in outcome.items()
                       if key not in ("score", "heatmap")}
            if metrics:
                raw[name] = {**raw.get(name, {}), **metrics}
            if name == "ela_detector":
                url = _save_heatmap(outcome.get("heatmap"), ctx)
                if url:
                    overlays.append(Overlay(type="heatmap", url=url))

        if not scores:
            missing = missing_dependencies()
            reason = "детекторы монтажа недоступны"
            if missing:
                reason += f": нужны {', '.join(missing)}"
            if errors:
                reason += f"; ошибка: {errors[0]['detector']}: {errors[0]['error']}"
            return self.unavailable(reason)

        best = max(scores.values())
        details: dict[str, Any] = {
            "scores": {name: round(value, 3) for name, value in scores.items()},
            "metrics": raw,
            "skipped": skipped,
            "errors": errors,
            "threshold": POSITIVE_THRESHOLD,
            "note": "слабый сигнал: следы монтажа бывают и в обычных фото после обработки",
        }
        if best >= POSITIVE_THRESHOLD:
            # Согласие детекторов даёт большую надёжность, но не выше границы ТЗ.
            agreeing = sum(1 for value in scores.values() if value >= POSITIVE_THRESHOLD)
            reliability = min(RELIABILITY_MAX, RELIABILITY_MIN + 0.1 * (agreeing - 1))
            details["agreeing_detectors"] = agreeing
            summary = (
                "Детекторы видят следы монтажа или повторяющиеся фрагменты. "
                "Это подсказка, а не доказательство: похожий результат даёт обычная обработка фото."
            )
            return make_result(
                self, Verdict.supports_fake, min(0.6, best), reliability,
                summary, details, overlays,
            )

        details["best"] = round(best, 3)
        summary = (
            "Следов монтажа детекторы не нашли. Скорее всего файл не правили, "
            "но подсказка слабая и доказательством не является."
        )
        return make_result(
            self, Verdict.neutral, 0.1, RELIABILITY_MIN, summary, details, overlays
        )
