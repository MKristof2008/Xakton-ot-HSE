"""Тесты сигнала «Оригинальность» и перцептивных хешей (Pillow).

Картинки генерируются Pillow прямо в tmp_path: бинарных фикстур нет.
"""

import io
import json

from PIL import Image

from lakmus.context import CheckContext
from lakmus.schemas import CheckInput, InputType, Stage, Verdict
from lakmus.signals.uniqueness import (
    DUPLICATE_DISTANCE,
    UniquenessSignal,
    image_hashes,
    load_archive,
    match_archive,
)


def structured_image(shift: int = 0, size=(64, 64), fmt="PNG") -> bytes:
    """Картинка с крупными блоками — у неё осмысленный перцептивный хеш.

    Однотонная заливка даёт хеш из нулей, поэтому для сравнений берём блоки.
    """
    image = Image.new("RGB", size)
    pixels = []
    for y in range(size[1]):
        for x in range(size[0]):
            value = ((x // 8) * 37 + (y // 8) * 61 + ((x // 8) * (y // 8)) * 23 + shift) % 256
            pixels.append((value, value // 2, 255 - value))
    image.putdata(pixels)
    buffer = io.BytesIO()
    if fmt == "JPEG":
        image.save(buffer, "JPEG", quality=90)
    else:
        image.save(buffer, "PNG")
    return buffer.getvalue()


def gradient_image(size=(64, 64)) -> bytes:
    return structured_image(size=size)


def make_ctx(data, options=None) -> CheckContext:
    return CheckContext(
        check_id="test-uniqueness",
        input=CheckInput(type=InputType.image),
        data=data,
        options=dict(options or {}),
    )


def write_archive(tmp_path, items) -> str:
    archive = tmp_path / "archive"
    archive.mkdir()
    (archive / "manifest.json").write_text(
        json.dumps({"version": 1, "items": items}, ensure_ascii=False), encoding="utf-8"
    )
    return str(archive)


# --------------------------------------------------------------------------
# хеши
# --------------------------------------------------------------------------


def test_hashes_are_deterministic():
    data = gradient_image()
    first = image_hashes(data)
    second = image_hashes(data)
    assert first == second
    assert set(first) == {"dhash", "ahash"}
    for value in first.values():
        assert len(value) == 16
        int(value, 16)


def test_hashes_differ_for_different_images():
    left = image_hashes(structured_image(shift=0))
    right = image_hashes(structured_image(shift=118))
    assert left["dhash"] != right["dhash"] or left["ahash"] != right["ahash"]


def test_hashes_survive_jpeg_recompression():
    original = image_hashes(structured_image(shift=0, fmt="PNG"))
    compressed = image_hashes(structured_image(shift=0, fmt="JPEG"))

    def distance(a: str, b: str) -> int:
        return bin(int(a, 16) ^ int(b, 16)).count("1")

    # Небольшая перекодировка не должна превращать кадр в «другой».
    assert distance(original["dhash"], compressed["dhash"]) <= DUPLICATE_DISTANCE * 3


# --------------------------------------------------------------------------
# архив
# --------------------------------------------------------------------------


async def test_no_archive_is_unavailable(tmp_path):
    ctx = make_ctx(gradient_image(), {"archive_dir": str(tmp_path / "нет-такого")})
    result = await UniquenessSignal().run(ctx)

    assert result.stage == Stage.sources
    assert result.verdict == Verdict.unavailable
    assert "архив не найден" in result.details["reason"]


def test_archive_without_manifest_is_unavailable(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    entries, reason = load_archive(empty)
    assert entries == []
    assert "нет манифеста" in reason


def test_broken_manifest_is_unavailable(tmp_path):
    archive = tmp_path / "archive"
    archive.mkdir()
    (archive / "manifest.json").write_text("{не json}", encoding="utf-8")
    entries, reason = load_archive(archive)
    assert entries == []
    assert "не читается" in reason


async def test_exact_duplicate_supports_fake(tmp_path):
    data = gradient_image()
    hashes = image_hashes(data)
    archive_dir = write_archive(tmp_path, [{
        "id": "old-flood-2021",
        "dhash": hashes["dhash"],
        "ahash": hashes["ahash"],
        "url": "https://example.org/old",
        "date": "2021-07-18",
    }])

    result = await UniquenessSignal().run(make_ctx(data, {"archive_dir": archive_dir}))

    assert result.verdict == Verdict.supports_fake
    assert result.strength >= 0.8
    assert result.details["unique"] is False
    assert result.details["similar_in_archive"] == 1
    assert result.details["best_match"]["id"] == "old-flood-2021"
    assert result.details["best_match"]["hamming"] == 0
    assert result.details["best_match"]["url"] == "https://example.org/old"
    assert result.details["phash"] == hashes["dhash"]
    assert "2021-07-18" in result.summary


async def test_unique_image_supports_real(tmp_path):
    archive_dir = write_archive(tmp_path, [{
        "id": "some-other-shot",
        "dhash": f"{int(image_hashes(gradient_image())['dhash'], 16) ^ 0xFFFFFFFFFFFFFFFF:016x}",
        "ahash": f"{int(image_hashes(gradient_image())['ahash'], 16) ^ 0xFFFFFFFFFFFFFFFF:016x}",
        "date": "2020-01-01",
    }])
    data = gradient_image()

    result = await UniquenessSignal().run(make_ctx(data, {"archive_dir": archive_dir}))

    # Локальный архив неполный: «уникально» — средний, а не сильный довод.
    assert result.verdict == Verdict.supports_real
    assert 0.0 < result.strength <= 0.6
    assert result.details["unique"] is True
    assert result.details["similar_in_archive"] == 0
    assert result.details["best_match"] is None


async def test_partial_match_is_neutral(tmp_path):
    data = gradient_image()
    hashes = image_hashes(data)
    near = f"{int(hashes['dhash'], 16) ^ 0x1FF:016x}"  # 9 бит разницы
    archive_dir = write_archive(tmp_path, [{
        "id": "similar-shot",
        "dhash": near,
        "ahash": None,
        "date": "2022-01-01",
    }])

    result = await UniquenessSignal().run(make_ctx(data, {"archive_dir": archive_dir}))

    assert result.verdict == Verdict.neutral
    assert result.details["unique"] is False
    assert result.details["similar_in_archive"] == 1
    assert result.details["best_match"]["id"] == "similar-shot"


async def test_pillow_unavailable_is_reported(tmp_path, monkeypatch):
    from lakmus.signals import uniqueness as module

    monkeypatch.setattr(module, "_pil", lambda: None)
    data = gradient_image()
    archive_dir = write_archive(tmp_path, [])
    result = await UniquenessSignal().run(make_ctx(data, {"archive_dir": archive_dir}))

    assert result.verdict == Verdict.unavailable
    assert "Pillow" in result.details["reason"]


async def test_broken_file_is_unavailable_without_exception(tmp_path):
    archive_dir = write_archive(tmp_path, [])
    result = await UniquenessSignal().run(
        make_ctx(b"\x89PNG\r\n\x1a\n" + b"\x00" * 40, {"archive_dir": archive_dir})
    )

    assert result.verdict == Verdict.unavailable
    assert "не удалось прочитать изображение" in result.details["reason"]


async def test_empty_bytes_is_unavailable():
    result = await UniquenessSignal().run(make_ctx(b""))
    assert result.verdict == Verdict.unavailable


async def test_archive_entry_by_file_path(tmp_path):
    """Запись манифеста может ссылаться на файл — хеш тогда считается по нему."""
    data = gradient_image()
    archive_dir = pathlib_archive(tmp_path, data)

    entries, reason = load_archive(archive_dir)
    assert reason is None
    assert entries[0]["id"] == "file-entry"

    result = await UniquenessSignal().run(make_ctx(data, {"archive_dir": archive_dir}))
    assert result.verdict == Verdict.supports_fake


def pathlib_archive(tmp_path, data: bytes) -> str:
    archive = tmp_path / "file-archive"
    archive.mkdir()
    (archive / "old.png").write_bytes(data)
    (archive / "manifest.json").write_text(
        json.dumps({"items": [{"id": "file-entry", "file": "old.png"}]}, ensure_ascii=False),
        encoding="utf-8",
    )
    return str(archive)


def test_match_archive_picks_minimum_distance():
    hashes = {"dhash": "f" * 16, "ahash": "0" * 16}
    far = f"{int(hashes['dhash'], 16) ^ 0xFFFFFFFFFFFFFFFF:016x}"
    near = f"{int(hashes['dhash'], 16) ^ 0xF:016x}"  # 4 бита разницы
    entries = [
        {"id": "far", "dhash": far, "ahash": None, "url": "", "date": ""},
        {"id": "near", "dhash": near, "ahash": None, "url": "", "date": ""},
        {"id": "elsewhere", "dhash": "0" * 16, "ahash": None, "url": "", "date": ""},
    ]
    match = match_archive(hashes, entries)
    assert match["best"]["id"] == "near"
    assert match["best"]["hamming"] == 4
    assert match["duplicate"] is True
    assert match["similar"] == 1