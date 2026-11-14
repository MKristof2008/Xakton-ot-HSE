"""Сигнал «Видео»: что можно сказать о ролике без его просмотра.

Честная граница: мы не «понимаем» видео. Сигнал делает то, что можно
проверить детерминированно:

  * читает метаданные контейнера (MP4/MOV: дата, камера, кодировщик);
  * ищет следы монтажа и генерации в этих метаданных;
  * при наличии OpenCV вытаскивает несколько кадров и проверяет, не
    является ли ролик перекодированной картинкой (один статичный кадр).

Распознавания речи и анализа смысла здесь нет — для этого нужна модель,
и это честно написано в ограничениях. Сигнал полезен тем, что ловит
самый частый случай в мессенджерах: фото или скриншот, оформленный
как «видео», и ролик, перезалитый с чужой датой.
"""

from __future__ import annotations

import importlib.util
from typing import Any, Optional

from ..context import CheckContext
from ..schemas import InputType, Stage, Verdict
from .base import BaseSignal, make_result

# Маркеры кодировщиков и генераторов в MP4-метаданных (moov/udta/©too).
GENERATOR_MARKERS: tuple[str, ...] = (
    "stable diffusion", "sora", "runway", "pika", "kling", "veo", "luma",
    "gen-2", "gen-3", "synthesia", "heygen", "d-id", "wombo", "kaiber",
    "сгенерировано", "нейросеть", "ai generated",
)

EDITOR_MARKERS: tuple[str, ...] = (
    "capcut", "premiere", "after effects", "davinci", "final cut",
    "inshot", "kine master", "kinemaster", "filmora", "movavi", "veed",
)

# Атомы MP4, в которых лежат человекочитаемые строки.
_TEXT_ATOMS = (b"\xa9too", b"\xa9nam", b"\xa9cmt", b"\xa9day", b"\xa9mak",
               b"\xa9mod", b"desc", b"ldes")

_MAX_ATOMS = 4000
_MAX_TEXT = 4096


def _present(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def cv_available() -> bool:
    return _present("cv2")


def _iter_atoms(data: bytes, start: int = 0, end: Optional[int] = None,
                depth: int = 0):
    """Обойти атомы MP4. Не бросает: битый файл просто даёт меньше атомов."""
    end = len(data) if end is None else min(end, len(data))
    pos = start
    seen = 0
    while pos + 8 <= end and seen < _MAX_ATOMS:
        size = int.from_bytes(data[pos:pos + 4], "big")
        name = data[pos + 4:pos + 8]
        header = 8
        if size == 1:  # 64-битный размер
            if pos + 16 > end:
                return
            size = int.from_bytes(data[pos + 8:pos + 16], "big")
            header = 16
        elif size == 0:  # до конца файла
            size = end - pos
        if size < header or pos + size > end:
            return
        body_start = pos + header
        body_end = pos + size
        yield name, body_start, body_end, depth
        seen += 1
        # Контейнеры, внутри которых есть другие атомы.
        if name in (b"moov", b"trak", b"mdia", b"udta", b"meta", b"ilst",
                    b"moof", b"traf", b"stbl"):
            # у meta первые 4 байта — версия/флаги
            inner = body_start + 4 if name == b"meta" else body_start
            yield from _iter_atoms(data, inner, body_end, depth + 1)
        pos = body_end


def parse_video_metadata(data: bytes) -> dict[str, Any]:
    """Метаданные контейнера: тип, текстовые атомы, следы генерации.

    Публичная функция без контекста проверки — тестируется отдельно.
    """
    meta: dict[str, Any] = {
        "container": "",
        "brand": "",
        "texts": {},
        "generator_hits": [],
        "editor_hits": [],
        "has_metadata": False,
    }
    if len(data) < 12:
        return meta

    if data[4:8] == b"ftyp":
        meta["container"] = "mp4"
        meta["brand"] = data[8:12].decode("ascii", "replace").strip()
    elif data[4:8] == b"moov":
        meta["container"] = "mov"
    else:
        meta["container"] = "unknown"

    if meta["container"] == "unknown":
        return meta

    found: dict[str, str] = {}
    for name, start, end, _depth in _iter_atoms(data):
        if name not in _TEXT_ATOMS:
            continue
        raw = data[start:min(end, start + _MAX_TEXT)]
        # В атоме данных сначала идёт описание: 2 байта размера, 2 байта
        # языка, затем сама строка. Пропускаем ровно столько, сколько
        # указано в размере, иначе теряем первые символы.
        text = ""
        if len(raw) >= 4:
            declared = int.from_bytes(raw[0:2], "big")
            body = raw[4:4 + declared] if declared else raw[4:]
            text = body.decode("utf-8", "replace")
        if not text:
            text = raw.decode("utf-8", "replace")
        text = text.replace("\x00", "").strip()
        if text:
            found[name.decode("latin-1")] = text[:300]

    meta["texts"] = found
    meta["has_metadata"] = bool(found)

    blob = " ".join(found.values()).lower()
    for marker in GENERATOR_MARKERS:
        if marker in blob:
            meta["generator_hits"].append(marker)
    for marker in EDITOR_MARKERS:
        if marker in blob:
            meta["editor_hits"].append(marker)
    return meta


def sample_frames(data: bytes, count: int = 3) -> dict[str, Any]:
    """Несколько кадров через OpenCV. None-поля, если OpenCV нет.

    Кадры нужны для одной проверки: одинаковые ли они. Ролик, который на
    самом деле статичная картинка, — частый приём в фейковых «видео».
    """
    if not cv_available():
        return {"available": False, "frames": 0, "static": None}
    try:
        import cv2
        import numpy as np
    except Exception:
        return {"available": False, "frames": 0, "static": None}

    try:
        # Пишем во временный файл: VideoCapture не читает bytes напрямую.
        import os
        import tempfile

        fd, path = tempfile.mkstemp(suffix=".mp4")
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
            cap = cv2.VideoCapture(path)
            if not cap.isOpened():
                return {"available": True, "frames": 0, "static": None}
            total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            fps = float(cap.get(cv2.CAP_PROP_FPS) or 0)
            grabbed = []
            for i in range(count):
                if total > 0:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, int(total * (i + 0.5) / count))
                ok, frame = cap.read()
                if not ok or frame is None:
                    continue
                small = cv2.resize(frame, (64, 64))
                grabbed.append(small.astype("float32"))
            cap.release()
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass
    except Exception:
        return {"available": True, "frames": 0, "static": None}

    if len(grabbed) < 2:
        return {
            "available": True,
            "frames": len(grabbed),
            "static": None,
            "total_frames": total,
            "fps": round(fps, 2),
        }

    diffs = [
        float(np.abs(grabbed[i] - grabbed[i - 1]).mean())
        for i in range(1, len(grabbed))
    ]
    mean_diff = sum(diffs) / len(diffs)
    return {
        "available": True,
        "frames": len(grabbed),
        "static": mean_diff < 1.0,
        "mean_diff": round(mean_diff, 3),
        "total_frames": total,
        "fps": round(fps, 2),
        "duration_s": round(total / fps, 2) if fps else None,
    }


class VideoSignal(BaseSignal):
    """Метаданные ролика и проверка «движется ли картинка»."""

    id = "video"
    name = "Видео"
    stage = Stage.provenance
    timeout_s = 12.0

    async def run(self, ctx: CheckContext):
        if ctx.input.type != InputType.video:
            return self.unavailable("сигнал работает только с видео")

        data = ctx.data
        if not data:
            return self.unavailable("нет байтов видео на входе")
        if len(data) < 12:
            return self.unavailable("файл слишком мал, чтобы быть видео")

        meta = ctx.cache.get("video_meta")
        if not isinstance(meta, dict):
            try:
                meta = parse_video_metadata(data)
            except Exception as exc:
                return self.unavailable(
                    f"разбор контейнера не удался: {type(exc).__name__}"
                )
            ctx.remember("video_meta", meta)

        if meta["container"] == "unknown":
            return self.unavailable("это не MP4/MOV: формат не разобран")

        frames = ctx.cache.get("video_frames")
        if not isinstance(frames, dict):
            frames = sample_frames(data)
            ctx.remember("video_frames", frames)

        details: dict[str, Any] = {"metadata": meta, "frames": frames}
        limitations: list[str] = [
            "Звук и речь не анализируются: распознавание речи не подключено."
        ]

        if meta["generator_hits"]:
            details["generator_hits"] = meta["generator_hits"]
            # Явная подпись генератора в контейнере — сильное доказательство:
            # такое пишут сами инструменты генерации. Уверенность высокая,
            # но не абсолютная: строку в метаданных можно вписать руками.
            return make_result(
                self,
                Verdict.supports_fake,
                0.85,
                0.75,
                "В метаданных ролика есть следы генератора "
                f"({', '.join(meta['generator_hits'][:3])}).",
                details,
            )

        if frames.get("static") is True:
            details["static_video"] = True
            return make_result(
                self,
                Verdict.supports_fake,
                0.5,
                0.4,
                "Кадры почти не отличаются: это статичная картинка, "
                "оформленная как видео.",
                details,
            )

        if meta["editor_hits"]:
            details["editor_hits"] = meta["editor_hits"]
            return make_result(
                self,
                Verdict.neutral,
                0.2,
                0.4,
                "Ролик смонтирован в редакторе "
                f"({', '.join(meta['editor_hits'][:3])}). "
                "Монтаж сам по себе не делает видео фейком.",
                details,
            )

        if meta["has_metadata"]:
            summary = (
                "Метаданные контейнера на месте, следов генератора в них нет. "
                "Это не подтверждение содержания: о смысле ролика сигнал не говорит."
            )
            return make_result(self, Verdict.neutral, 0.2, 0.4, summary, details)

        limitations.append(
            "Метаданные стёрты: мессенджеры удаляют их при пересылке."
        )
        details["no_metadata"] = True
        details["limitations"] = limitations
        return make_result(
            self,
            Verdict.neutral,
            0.0,
            0.2,
            "Метаданных нет: соцсети и мессенджеры стирают их при загрузке. "
            "Отсутствие метаданных ничего не доказывает.",
            details,
        )
