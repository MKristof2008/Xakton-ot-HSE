"""Разметка тестового набора (раздел 6.7 ТЗ).

Один объект набора — одна строка JSONL в манифесте (см. ``ml/data/README.md``).
Файлы изображений и текстов в репозиторий не кладём: ``path`` — путь к
образцу внутри ``data/samples/…``, которого в git может не быть.

Категории ТЗ 6.7 и их минимальные объёмы:

===============  ========  ============================================
категория        минимум   что это
===============  ========  ============================================
``real_photo``   50        настоящие фотографии без правок
``generated``    50        полностью сгенерированные изображения
``edited``       30        реальные фото с правками (кроп, вставки, цвет)
``mislabelled``  20        настоящие фото с ложной подписью/контекстом
``text``         60        тексты: настоящие и машинные
===============  ========  ============================================

Сумма минимумов по категориям — 210 объектов, при этом ТЗ задаёт нижнюю
границу набора в 150 объектов. Проверяем оба условия: и общий объём,
и каждый минимум по категории.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Iterable, Literal, Optional

from pydantic import BaseModel, ValidationError, field_validator

#: Минимальный объём набора по ТЗ 6.7.
MIN_TOTAL: int = 150

#: Минимумы по категориям из ТЗ 6.7.
DATASET_MINIMUMS: dict[str, int] = {
    "real_photo": 50,
    "generated": 50,
    "edited": 30,
    "mislabelled": 20,
    "text": 60,
}

#: Категории, неоднозначные по своей природе: «Туман» там — верный ответ.
AMBIGUOUS_CATEGORIES: frozenset[str] = frozenset({"edited", "mislabelled"})

#: Ожидаемая метка для однозначных категорий.
DEFAULT_LABEL: dict[str, str] = {
    "real_photo": "real",
    "generated": "fake",
    "edited": "edited",
    "mislabelled": "mislabelled",
}

#: Метки, которые в бинарной задаче «настоящее/подделка» дают 1.
POSITIVE_LABELS: frozenset[str] = frozenset({"real"})


def to_binary_label(label: str) -> int:
    """Метка ТЗ → 1 («настоящее») или 0 («не настоящее»).

    ``real`` → 1. ``fake``, ``edited`` и ``mislabelled`` → 0: в задаче
    «можно ли пересылать как есть» материал с правками или с ложной
    подписью — не настоящее, даже если исходное фото реально.
    """
    text = str(label).strip().lower()
    if text in POSITIVE_LABELS:
        return 1
    if text in {"fake", "edited", "mislabelled"}:
        return 0
    raise ValueError(f"Неизвестная метка: {label!r}")


class LabeledCase(BaseModel):
    """Один размеченный объект набора.

    ``path`` — путь к образцу относительно корня репозитория
    (``data/samples/…``); файла может не быть в git, манифест важнее.
    ``generator`` — для ``generated``: ``midjourney``, ``sdxl``, ``dalle3``…
    ``source`` — откуда взят объект: домен, архив, номер поста.
    """

    id: str
    path: str
    kind: Literal["image", "text"]
    category: Literal["real_photo", "generated", "edited", "mislabelled", "text"]
    label: Literal["real", "fake", "edited", "mislabelled"]
    generator: Optional[str] = None
    source: Optional[str] = None

    @field_validator("id", "path")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("пустое значение")
        return value

    @property
    def binary_label(self) -> int:
        return to_binary_label(self.label)

    @property
    def ambiguous(self) -> bool:
        return self.category in AMBIGUOUS_CATEGORIES


def load_dataset(path: str | Path) -> list[LabeledCase]:
    """Читает манифест JSONL и валидирует каждую строку.

    Пустые строки и строки, начинающиеся с ``#``, пропускаются. Ошибка
    сообщает файл и номер строки — манифест правят руками, искать
    проблемную запись должно быть просто.
    """
    manifest = Path(path)
    if not manifest.is_file():
        raise FileNotFoundError(f"Манифест не найден: {manifest}")

    cases: list[LabeledCase] = []
    with manifest.open(encoding="utf-8") as handle:
        for lineno, line in enumerate(handle, 1):
            text = line.strip()
            if not text or text.startswith("#"):
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"{manifest}:{lineno}: невалидный JSON: {exc.msg}"
                ) from exc
            if not isinstance(payload, dict):
                raise ValueError(f"{manifest}:{lineno}: ожидался JSON-объект")
            try:
                cases.append(LabeledCase(**payload))
            except ValidationError as exc:
                first = exc.errors()[0]
                where = ".".join(str(part) for part in first["loc"]) or "строка"
                raise ValueError(
                    f"{manifest}:{lineno}: поле {where}: {first['msg']}"
                ) from exc
    return cases


def validate_dataset(cases: Iterable[LabeledCase]) -> dict:
    """Сверяет набор с минимумами ТЗ 6.7.

    Возвращает словарь:

    * ``total`` / ``min_total`` / ``ok`` — объём и общий вердикт;
    * ``by_category`` — счётчики по всем пяти категориям (нули тоже);
    * ``by_label``, ``by_kind`` — распределение меток и типов входа;
    * ``below_minimum`` — категории, где минимум ТЗ не набран;
    * ``missing_categories`` — категории без единого объекта;
    * ``duplicate_ids`` — повторы id (ломают join с результатами);
    * ``warnings`` — готовые к печати предупреждения по-русски.
    """
    items = list(cases)
    by_category: Counter[str] = Counter(case.category for case in items)
    by_label: Counter[str] = Counter(case.label for case in items)
    by_kind: Counter[str] = Counter(case.kind for case in items)
    id_counts: Counter[str] = Counter(case.id for case in items)

    categories = {name: by_category.get(name, 0) for name in DATASET_MINIMUMS}
    below = {
        name: count
        for name, count in categories.items()
        if count < DATASET_MINIMUMS[name]
    }
    missing = [name for name, count in categories.items() if count == 0]
    duplicates = sorted(cid for cid, count in id_counts.items() if count > 1)

    warnings: list[str] = []
    if len(items) < MIN_TOTAL:
        warnings.append(
            f"всего {len(items)} объектов при минимуме ТЗ {MIN_TOTAL}"
        )
    for name, count in categories.items():
        minimum = DATASET_MINIMUMS[name]
        if count < minimum:
            warnings.append(
                f"{name}: {count} из {minimum} — не хватает {minimum - count}"
            )
    if duplicates:
        warnings.append(f"повторяющиеся id: {', '.join(duplicates)}")
    for case in items:
        expected = DEFAULT_LABEL.get(case.category)
        if expected is not None and case.label != expected:
            warnings.append(
                f"{case.id}: у категории {case.category} ожидалась метка "
                f"{expected}, указана {case.label}"
            )

    ok = len(items) >= MIN_TOTAL and not below and not duplicates
    return {
        "total": len(items),
        "min_total": MIN_TOTAL,
        "ok": ok,
        "by_category": categories,
        "by_label": dict(sorted(by_label.items())),
        "by_kind": dict(sorted(by_kind.items())),
        "below_minimum": below,
        "missing_categories": missing,
        "duplicate_ids": duplicates,
        "warnings": warnings,
    }


def dataset_stats(cases: Iterable[LabeledCase]) -> dict:
    """Описательные статистики набора (без сверки с ТЗ).

    Отвечает на вопросы «чем именно набран набор»: сколько изображений
    и текстов, какими генераторами, с каких источников, сколько
    неоднозначных объектов и сколько уникальных путей.
    """
    items = list(cases)
    generators: Counter[str] = Counter(
        case.generator for case in items if case.generator
    )
    sources: Counter[str] = Counter(
        case.source for case in items if case.source
    )
    images = sum(1 for case in items if case.kind == "image")
    ambiguous = sum(1 for case in items if case.ambiguous)
    total = len(items)
    return {
        "total": total,
        "images": images,
        "texts": total - images,
        "ambiguous": ambiguous,
        "ambiguous_share": round(ambiguous / total, 4) if total else 0.0,
        "unique_paths": len({case.path for case in items}),
        "with_generator": sum(1 for case in items if case.generator),
        "with_source": sum(1 for case in items if case.source),
        "by_generator": dict(sorted(generators.items())),
        "by_source": dict(sorted(sources.items())),
    }
