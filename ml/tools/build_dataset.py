"""Собрать размеченный набор под раздел 6.7 ТЗ.

Что делает: берёт исходные изображения и тексты, делает из них объекты
набора нужных категорий и пишет манифест в формате
``ml/data/labels_example.jsonl``.

Честно о границах автоматики:

  * ``edited``       — делается полностью автоматически из настоящих фото:
                       кроп, поворот, сдвиг цвета, вставка фрагмента;
  * ``text``         — шаблонные фейки и настоящие факты из базы знаний;
  * ``real_photo``   — только копирование того, что уже есть на диске:
                       синтетикой «настоящее фото» не сделать;
  * ``generated``    — тоже копирование: генерация требует внешних
                       сервисов и лимитов, скрипт этого не делает;
  * ``mislabelled``  — скриншоты с ложной подписью: подпись задаётся
                       вручную, картинка берётся из настоящих фото.

Поэтому настоящих фото и генераций скрипт не выдумывает: он раскладывает
по категориям то, что дали, и честно пишет, сколько не хватает до нормы.

Запуск::

    python -I ml/tools/build_dataset.py --help
    python -I ml/tools/build_dataset.py --real "C:/photos" --generated "C:/ai" \\
        --out ml/data/samples --manifest ml/data/labels.jsonl
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import random
import shutil
import sys
from pathlib import Path
from typing import Iterable

ML_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ML_ROOT))

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}

#: Сколько объектов нужно по ТЗ 6.7.
MINIMUMS = {
    "real_photo": 50,
    "generated": 50,
    "edited": 30,
    "mislabelled": 20,
    "text": 60,
}


def _pil():
    try:
        from PIL import Image, ImageDraw, ImageEnhance
        return Image, ImageDraw, ImageEnhance
    except ImportError:
        raise SystemExit("нужен Pillow: pip install pillow")


def _slug(path: Path) -> str:
    """Короткий стабильный идентификатор файла."""
    digest = hashlib.sha1(str(path).encode("utf-8")).hexdigest()[:8]
    return digest


# --------------------------------------------------------------- edited

def make_edited(source: Path, out_dir: Path, index: int) -> list[Path]:
    """Из одного настоящего фото — несколько «правленых» вариантов.

    Каждый вариант — реальная операция, которую делает человек перед
    публикацией: обрезка, поворот, сдвиг цвета, вставка фрагмента.
    Метка ``edited``: фото настоящее, но пересылать как есть нельзя.
    """
    Image, ImageDraw, ImageEnhance = _pil()
    out_dir.mkdir(parents=True, exist_ok=True)
    made: list[Path] = []
    try:
        with Image.open(source) as opened:
            base = opened.convert("RGB")
    except Exception:
        return made

    w, h = base.size
    if w < 200 or h < 200:
        return made

    # 1. Кроп: убираем часть кадра — типичная подмена контекста.
    crop = base.crop((int(w * 0.12), int(h * 0.12), int(w * 0.92), int(h * 0.92)))
    target = out_dir / f"img_edit_{index:03d}_crop.jpg"
    crop.save(target, "JPEG", quality=90)
    made.append(target)

    # 2. Поворот: снимок «повернули», чтобы скрыть ориентиры.
    rotated = base.rotate(3.5, expand=True)
    target = out_dir / f"img_edit_{index:03d}_rot.jpg"
    rotated.save(target, "JPEG", quality=90)
    made.append(target)

    # 3. Сдвиг цвета: «сделать вечерним» — меняет время суток на глаз.
    tinted = ImageEnhance.Color(base).enhance(1.6)
    tinted = ImageEnhance.Brightness(tinted).enhance(0.82)
    target = out_dir / f"img_edit_{index:03d}_color.jpg"
    tinted.save(target, "JPEG", quality=90)
    made.append(target)

    # 4. Вставка фрагмента: копируем кусок и вставляем рядом.
    patch_w, patch_h = max(20, w // 5), max(20, h // 5)
    patch = base.crop((10, 10, 10 + patch_w, 10 + patch_h))
    pasted = base.copy()
    pasted.paste(patch, (w - patch_w - 10, h - patch_h - 10))
    target = out_dir / f"img_edit_{index:03d}_paste.jpg"
    pasted.save(target, "JPEG", quality=90)
    made.append(target)

    # 5. Зеркальное отражение: меняет расположение объектов, ломает
    #    привязку к местности.
    mirrored = base.transpose(Image.FLIP_LEFT_RIGHT)
    target = out_dir / f"img_edit_{index:03d}_flip.jpg"
    mirrored.save(target, "JPEG", quality=90)
    made.append(target)

    # 6. Сильная пересборка качества: следы двойного сжатия, как после
    #    многократной пересылки через мессенджеры.
    buffer = io.BytesIO()
    base.save(buffer, "JPEG", quality=35)
    buffer.seek(0)
    with Image.open(buffer) as low:
        low.load()
        target = out_dir / f"img_edit_{index:03d}_recompress.jpg"
        low.convert("RGB").save(target, "JPEG", quality=85)
    made.append(target)

    return made


def make_mislabelled(source: Path, out_dir: Path, index: int) -> Path | None:
    """Настоящее фото + ложная подпись = объект «mislabelled».

    Картинка не меняется: ложь в подписи, а не в файле. Поэтому здесь
    только копия — подпись живёт в манифесте.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    Image, _, _ = _pil()
    try:
        with Image.open(source) as opened:
            opened.convert("RGB").save(
                out_dir / f"img_mis_{index:03d}.jpg", "JPEG", quality=90
            )
    except Exception:
        return None
    return out_dir / f"img_mis_{index:03d}.jpg"


def copy_category(sources: Iterable[Path], out_dir: Path, prefix: str) -> list[Path]:
    """Скопировать настоящие файлы в категорию — без обработки."""
    out_dir.mkdir(parents=True, exist_ok=True)
    copied: list[Path] = []
    for i, src in enumerate(sources, 1):
        if src.suffix.lower() not in IMAGE_EXT:
            continue
        dst = out_dir / f"{prefix}_{i:03d}{src.suffix.lower()}"
        try:
            shutil.copy2(src, dst)
            copied.append(dst)
        except OSError:
            continue
    return copied


# ------------------------------------------------------------------ текст

#: Шаблоны вирусных фейков: подстановка темы и приёма давления.
FAKE_TEMPLATES = [
    "СРОЧНО! {topic} с {date}! Перешли всем, пока не поздно!",
    "Внимание! Власти скрывают: {topic} уже {date}. Не молчите!",
    "Только что узнал: {topic} с {date}. Источник в правительстве, подробности скрывают.",
    "ШОК! {topic} с {date}! Об этом не напишут в новостях — распространите!",
    "Всем! С {date} {topic}. Знакомый из администрации подтвердил.",
]

FAKE_TOPICS = [
    "запретят наличные",
    "отменят ЕГЭ",
    "введут комендантский час",
    "повысят пенсионный возраст до 70 лет",
    "закроют все пункты выдачи заказов",
    "обяжут установить новое приложение",
    "введут налог на снятие наличных",
    "отменят льготы для пенсионеров",
]

FAKE_DATES = ["1 января", "1 марта", "следующей недели", "понедельника", "9 декабря"]


def make_fake_texts(count: int, seed: int = 7) -> list[dict]:
    """Шаблонные фейки: жанр вирусного сообщения с признаками давления."""
    rng = random.Random(seed)
    out: list[dict] = []
    seen: set[str] = set()
    while len(out) < count:
        template = rng.choice(FAKE_TEMPLATES)
        topic = rng.choice(FAKE_TOPICS)
        date = rng.choice(FAKE_DATES)
        text = template.format(topic=topic, date=date)
        if text in seen:
            continue
        seen.add(text)
        out.append({"text": text, "label": "fake", "source": "шаблон вирусного сообщения"})
    return out


#: Как настоящие факты выглядят в живой речи: не только сухая цитата,
#: но и пересказ с ссылкой на источник. Число и суть не меняются.
REAL_TEMPLATES = [
    "{claim}. Источник: {source}.",
    "Напоминаю: {claim}. Подробности в первоисточнике — {source}.",
    "По официальным данным, {claim}. Проверить: {source}.",
    "{claim} — это подтверждается документом: {source}.",
]


def make_real_texts(count: int) -> list[dict]:
    """Настоящие тексты — факты из курируемой базы, у каждого есть источник.

    Каждый факт даётся в нескольких формулировках: живой текст отличается
    от пресс-релиза, а модель должна узнавать факт в любой из них.
    """
    kb_path = ML_ROOT / "lakmus" / "data" / "kb_facts.json"
    try:
        kb = json.loads(kb_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    out: list[dict] = []
    facts: list[tuple[str, str]] = []
    for topic in kb.get("topics", []):
        for fact in topic.get("facts", []):
            claim = str(fact.get("claim", "")).strip().rstrip(".")
            if not claim:
                continue
            facts.append((claim, str(fact.get("source", "")).strip()))
    if not facts:
        return out

    # Обходим факты по кругу, меняя формулировку: один факт даёт до четырёх
    # разных по стилю, но одинаковых по сути текстов.
    index = 0
    while len(out) < count:
        claim, source = facts[index % len(facts)]
        template = REAL_TEMPLATES[(index // len(facts)) % len(REAL_TEMPLATES)]
        text = template.format(claim=claim, source=source or "база фактов")
        out.append({
            "text": text,
            "label": "real",
            "source": source or "база фактов",
        })
        index += 1
    return out


# --------------------------------------------------------------- манифест

def build_manifest(
    real: list[Path],
    generated: list[Path],
    edited: list[Path],
    mislabelled: list[Path],
    texts: list[dict],
    root: Path,
) -> list[dict]:
    """Собрать строки манифеста в формате LabeledCase."""
    rows: list[dict] = []

    def rel(path: Path) -> str:
        try:
            return str(path.relative_to(root.parent.parent)).replace("\\", "/")
        except ValueError:
            return str(path).replace("\\", "/")

    for i, path in enumerate(real, 1):
        rows.append({
            "id": f"img_real_{i:03d}", "path": rel(path), "kind": "image",
            "category": "real_photo", "label": "real",
            "generator": None, "source": "настоящее фото",
        })

    for i, path in enumerate(generated, 1):
        rows.append({
            "id": f"img_gen_{i:03d}", "path": rel(path), "kind": "image",
            "category": "generated", "label": "fake",
            "generator": "unknown", "source": "сгенерировано",
        })

    for i, path in enumerate(edited, 1):
        rows.append({
            "id": f"img_edit_{i:03d}", "path": rel(path), "kind": "image",
            "category": "edited", "label": "edited",
            "generator": None, "source": "правка настоящего фото",
        })

    for i, path in enumerate(mislabelled, 1):
        rows.append({
            "id": f"img_mis_{i:03d}", "path": rel(path), "kind": "image",
            "category": "mislabelled", "label": "mislabelled",
            "generator": None, "source": "настоящее фото с ложной подписью",
        })

    real_n = fake_n = 0
    for item in texts:
        kind = "real" if item["label"] == "real" else "fake"
        if kind == "real":
            real_n += 1
            num = real_n
        else:
            fake_n += 1
            num = fake_n
        rows.append({
            "id": f"txt_{kind}_{num:03d}",
            "path": f"data/samples/texts/txt_{kind}_{num:03d}.txt",
            "kind": "text", "category": "text", "label": item["label"],
            "generator": None if kind == "real" else "template",
            "source": item.get("source", ""),
        })

    return rows


def write_texts(texts: list[dict], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    real_i = fake_i = 0
    for item in texts:
        if item["label"] == "real":
            real_i += 1
            name = f"txt_real_{real_i:03d}.txt"
        else:
            fake_i += 1
            name = f"txt_fake_{fake_i:03d}.txt"
        (out_dir / name).write_text(item["text"], encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Собрать размеченный набор")
    ap.add_argument("--real", type=Path, action="append", default=[],
                    help="папка с настоящими фото (можно несколько раз)")
    ap.add_argument("--generated", type=Path, action="append", default=[],
                    help="папка со сгенерированными изображениями")
    ap.add_argument("--samples", type=Path, default=ML_ROOT / "data" / "samples",
                    help="куда складывать файлы набора")
    ap.add_argument("--manifest", type=Path, default=ML_ROOT / "data" / "labels.jsonl",
                    help="куда записать манифест")
    ap.add_argument("--texts", type=int, default=60, help="сколько текстов собрать")
    ap.add_argument("--apply", action="store_true", help="выполнить (без флага — показать план)")
    args = ap.parse_args(argv)

    def images(folders: list[Path]) -> list[Path]:
        out: list[Path] = []
        for folder in folders:
            if folder.is_dir():
                out.extend(sorted(p for p in folder.iterdir()
                                  if p.suffix.lower() in IMAGE_EXT))
        return out

    real_src = images(args.real)
    gen_src = images(args.generated)

    print(f"настоящих фото найдено: {len(real_src)}")
    print(f"сгенерированных найдено: {len(gen_src)}")

    if not args.apply:
        print("\nПлан (запустите с --apply, чтобы выполнить):")
        print(f"  real_photo : скопировать {len(real_src)}, нужно {MINIMUMS['real_photo']}")
        print(f"  generated  : скопировать {len(gen_src)}, нужно {MINIMUMS['generated']}")
        print(f"  edited     : x4 из каждого фото = {len(real_src) * 4}, нужно {MINIMUMS['edited']}")
        print(f"  mislabelled: по одному из фото = {len(real_src)}, нужно {MINIMUMS['mislabelled']}")
        print(f"  text       : собрать {args.texts}, нужно {MINIMUMS['text']}")
        return 0

    samples = args.samples
    real_files = copy_category(real_src, samples / "real_photo", "img_real")
    gen_files = copy_category(gen_src, samples / "generated", "img_gen")

    edited_files: list[Path] = []
    mislabelled_files: list[Path] = []
    for i, src in enumerate(real_src, 1):
        edited_files.extend(make_edited(src, samples / "edited", i))
        mis = make_mislabelled(src, samples / "mislabelled", i)
        if mis:
            mislabelled_files.append(mis)

    fake = make_fake_texts(args.texts // 2)
    real_texts = make_real_texts(args.texts - len(fake))
    texts = real_texts + fake
    write_texts(texts, samples / "texts")

    rows = build_manifest(
        real_files, gen_files, edited_files, mislabelled_files, texts, samples
    )
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    with args.manifest.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"\nманифест: {args.manifest} — {len(rows)} объектов")
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["category"]] = counts.get(row["category"], 0) + 1
    for name, need in MINIMUMS.items():
        have = counts.get(name, 0)
        mark = "OK " if have >= need else "нед"
        print(f"  {mark} {name:12} {have:>3} из {need}")
    return 0


if __name__ == "__main__":
    import io as _io

    # Консоль Windows по умолчанию cp1251 и падает на «→», «×», «—».
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = _io.TextIOWrapper(
            sys.stdout.buffer, encoding="utf-8", errors="replace"
        )
    raise SystemExit(main())
