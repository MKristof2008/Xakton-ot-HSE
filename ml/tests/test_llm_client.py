import json
import pytest
from pathlib import Path

from lakmus.llm import RecordingLLMClient, ReplayLLMClient, replay_response


class _FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def complete(self, system: str, user: str):
        self.calls.append((system, user))
        return replay_response(self.responses.pop(0))


@pytest.mark.asyncio
async def test_recording_client_saves_calls(tmp_path):
    path = tmp_path / "calls.json"
    fake = _FakeClient(["ответ 1", "ответ 2"])
    rec = RecordingLLMClient(fake)
    await rec.complete("sys1", "usr1")
    await rec.complete("sys2", "usr2")
    rec.save(path)

    data = json.loads(path.read_text(encoding="utf-8"))
    assert len(data) == 2
    assert data[0]["response"] == "ответ 1"
    assert data[1]["user"] == "usr2"


@pytest.mark.asyncio
async def test_replay_client_returns_recorded(tmp_path):
    path = tmp_path / "calls.json"
    rec = RecordingLLMClient(_FakeClient(["ответ"]))
    await rec.complete("sys", "usr")
    rec.save(path)

    replay = ReplayLLMClient(path)
    resp = await replay.complete("sys", "usr")
    assert resp.text == "ответ"


@pytest.mark.asyncio
async def test_replay_client_missing_raises(tmp_path):
    replay = ReplayLLMClient(tmp_path / "empty.json")
    with pytest.raises(RuntimeError):
        await replay.complete("sys", "usr")


@pytest.mark.asyncio
async def test_replay_client_with_fallback_records(tmp_path):
    path = tmp_path / "calls.json"
    fallback = _FakeClient(["новый ответ"])
    replay = ReplayLLMClient(path, fallback=fallback, record=True)
    resp = await replay.complete("sys", "usr")
    assert resp.text == "новый ответ"
    replay.save(path)
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data[0]["response"] == "новый ответ"
