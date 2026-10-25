"""CLI генерации документа «Методология» (раздел 6.9 п.5 ТЗ).

Реестр сигналов живёт здесь, потому что это данные проекта, а не логика
рендера: ``lakmus.methodology.build_methodology`` умеет собрать документ
из любого совместимого реестра, а этот файл даёт ему наш.

Запуск::

    python ml/tools/methodology.py
    python ml/tools/methodology.py --out ml/docs/METHODOLOGY.md
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ML_ROOT = REPO_ROOT / "ml"
if str(ML_ROOT) not in sys.path:
    sys.path.insert(0, str(ML_ROOT))

from lakmus.fusion import FUSION_CONFIG  # noqa: E402  (путь к ml/ нужен до импорта)
from lakmus.methodology import build_methodology  # noqa: E402

DEFAULT_OUTPUT = ML_ROOT / "docs" / "METHODOLOGY.md"

#: Реестр сигналов с надёжностями из ТЗ (I1 0.95, I2 0.75, I3 0.40, I4 0.80,
#: I5 0.50, I6 0.30, T1 —, T2 0.70, T3 0.60, T4 0.30, T5 0.05).
#: ``reliability = None`` — надёжность не измерена, сигнал не участвует
#: в score как доказательство.
SIGNALS_META: list[dict] = [
    {
        "id": "I1",
        "name": "Манифест происхождения (C2PA)",
        "stage": "provenance",
        "reliability": 0.95,
        "what": "есть ли подписанный манифест о том, кем и когда создан файл",
        "limits": [
            "манифест есть у меньшинства файлов",
            "пере-сохранение через мессенджер срезает манифест",
        ],
    },
    {
        "id": "I2",
        "name": "Следы генеративных моделей",
        "stage": "artifacts",
        "reliability": 0.75,
        "what": "характерные текстуры и шум диффузионных моделей",
        "limits": [
            "новые модели оставляют меньше следов",
            "сильное сжатие и фильтры скрывают шум",
        ],
    },
    {
        "id": "I3",
        "name": "Метаданные EXIF",
        "stage": "artifacts",
        "reliability": 0.40,
        "what": "камера, дата съёмки и программа обработки из заголовков файла",
        "limits": [
            "EXIF легко подделать",
            "соцсети и мессенджеры вырезают метаданные",
        ],
    },
    {
        "id": "I4",
        "name": "Обратный поиск и первоисточник",
        "stage": "sources",
        "reliability": 0.80,
        "what": "находится ли этот же кадр в более ранних публикациях",
        "limits": [
            "не видит закрытые и только что опубликованные материалы",
            "похожие кадры дают ложные совпадения",
        ],
    },
    {
        "id": "I5",
        "name": "Физика кадра",
        "stage": "artifacts",
        "reliability": 0.50,
        "what": "согласованы ли свет, тени, отражения и геометрия сцен",
        "limits": [
            "сильные модели соблюдают физику",
            "локальная правка заметна только рядом с местом правки",
        ],
    },
    {
        "id": "I6",
        "name": "Частотный анализ",
        "stage": "artifacts",
        "reliability": 0.30,
        "what": "аномалии спектра, характерные для склейки и вставок",
        "limits": [
            "надёжен только при грубой склейке",
            "чувствителен к повторному сжатию",
        ],
    },
    {
        "id": "T1",
        "name": "Поиск первоисточника текста",
        "stage": "provenance",
        "reliability": None,
        "what": "находится ли текст или его фрагменты в более ранних публикациях",
        "limits": [
            "надёжность не измерена: сигнал не участвует в score как доказательство",
            "перепечатки и цитаты дают ложные совпадения",
        ],
    },
    {
        "id": "T2",
        "name": "Стилометрия и детектор машинного текста",
        "stage": "artifacts",
        "reliability": 0.70,
        "what": "похож ли текст на сгенерированный моделью по ритму и выбору слов",
        "limits": [
            "короткие тексты неразличимы",
            "редактура человека маскирует машинное происхождение",
        ],
    },
    {
        "id": "T3",
        "name": "Проверка утверждений по источникам",
        "stage": "sources",
        "reliability": 0.60,
        "what": "подтверждают или опровергают ли найденные источники утверждения текста",
        "limits": [
            "зависит от качества поиска",
            "отсутствие опровержения не равно подтверждению",
        ],
    },
    {
        "id": "T4",
        "name": "Согласованность дат, чисел и названий",
        "stage": "context",
        "reliability": 0.30,
        "what": "сходятся ли даты, числа и имена внутри текста и с контекстом",
        "limits": [
            "ловит только грубые расхождения",
            "не проверяет смысл утверждения",
        ],
    },
    {
        "id": "T5",
        "name": "Пунктуация, эмодзи и типографика",
        "stage": "artifacts",
        "reliability": 0.05,
        "what": "типографские привычки, характерные для генераторов",
        "limits": [
            "почти шум: стиль легко подделать",
            "у живых авторов тоже бывает машинная типографика",
        ],
    },
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Генерация документа «Методология» (ТЗ 6.9 п.5)"
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="куда писать Markdown (по умолчанию ml/docs/METHODOLOGY.md)",
    )
    args = parser.parse_args(argv)

    document = build_methodology(SIGNALS_META, FUSION_CONFIG)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(document, encoding="utf-8")
    print(f"Методология записана: {args.out}")
    print(f"Сигналов в реестре: {len(SIGNALS_META)}, строк: {document.count(chr(10)) + 1}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
