"""Сигнал «Видео»: контейнер MP4/MOV, следы монтажа и генерации, статика."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ml"))

from lakmus.context import CheckContext  # noqa: E402
from lakmus.schemas import CheckInput, InputType  # noqa: E402
from lakmus.signals.video import (  # noqa: E402
    VideoSignal,
    parse_video_metadata,
    sample_frames,
)


def atom(name: bytes, payload: bytes) -> bytes:
    return (len(payload) + 8).to_bytes(4, "big") + name + payload


def text_atom(name: bytes, value: str) -> bytes:
    body = b"\x00\x00\x00\x00" + b"\x00\x00" + value.encode("utf-8")
    return atom(name, body)


def mp4(*atoms: bytes, brand: bytes = b"isom") -> bytes:
    ftyp = atom(b"ftyp", brand + b"\x00\x00\x02\x00" + brand + b"iso2")
    return ftyp + atom(b"moov", atom(b"udta", b"".join(atoms)))


def ctx_for(data: bytes) -> CheckContext:
    return CheckContext(
        check_id="test-video",
        input=CheckInput(type=InputType.video, filename="clip.mp4"),
        data=data,
    )


def test_detects_container_and_text_atoms():
    meta = parse_video_metadata(mp4(text_atom(b"\xa9too", "CapCut 4.2")))
    assert meta["container"] == "mp4"
    assert meta["has_metadata"] is True
    assert "CapCut 4.2" in meta["texts"].values()


def test_editor_marker_recognised():
    meta = parse_video_metadata(mp4(text_atom(b"\xa9too", "KineMaster")))
    assert meta["editor_hits"], "редактор должен попасть в editor_hits"
    assert not meta["generator_hits"]


def test_generator_marker_recognised():
    meta = parse_video_metadata(mp4(text_atom(b"\xa9too", "Made with Runway Gen-2")))
    assert meta["generator_hits"]


def test_no_metadata_is_not_evidence():
    meta = parse_video_metadata(mp4())
    assert meta["has_metadata"] is False
    assert not meta["generator_hits"]


def test_not_mp4_is_unknown():
    meta = parse_video_metadata(b"\x00" * 64)
    assert meta["container"] == "unknown"


def test_broken_file_does_not_raise():
    """Битый контейнер — штатная ситуация, сигнал не должен падать."""
    meta = parse_video_metadata(b"\x00\x00\x00\xff" + b"ftyp" + b"isom" + b"\x00" * 20)
    assert isinstance(meta, dict)


def test_sample_frames_without_cv2_reports_unavailable(monkeypatch):
    monkeypatch.setattr("lakmus.signals.video.cv_available", lambda: False)
    result = sample_frames(b"\x00" * 100)
    assert result["available"] is False
    assert result["static"] is None


@pytest.mark.asyncio
async def test_generated_video_supports_fake():
    data = mp4(text_atom(b"\xa9too", "Sora"))
    result = await VideoSignal().run(ctx_for(data))
    assert result.verdict.value == "supports_fake"
    assert "генератор" in result.summary.lower()


@pytest.mark.asyncio
async def test_plain_video_is_neutral_with_limits():
    data = mp4(text_atom(b"\xa9too", "Lavf58.29.100"))
    result = await VideoSignal().run(ctx_for(data))
    assert result.verdict.value == "neutral"
    # О смысле ролика сигнал не говорит — это должно быть видно.
    assert "содержани" in result.summary.lower()


@pytest.mark.asyncio
async def test_wrong_input_type_unavailable():
    ctx = CheckContext(
        check_id="test-video-text",
        input=CheckInput(type=InputType.text, extracted_text="текст"),
        text="текст",
    )
    result = await VideoSignal().run(ctx)
    assert result.verdict.value == "unavailable"


@pytest.mark.asyncio
async def test_pipeline_runs_only_video_signal():
    from lakmus.pipeline import check

    result = await check(ctx_for(mp4(text_atom(b"\xa9too", "CapCut"))))
    assert [s.id for s in result.signals] == ["video"]
    assert result.trust.uncertainty >= 0
