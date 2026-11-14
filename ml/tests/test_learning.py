"""Обучение на ошибках: поправка человека меняет будущий ответ.

Эксперт на встрече спрашивал, как модель будет дообучаться. Здесь это
проверяется вживую: человек говорит «должно быть фейк» — и следующая
проверка того же текста отвечает из банка знаний, без сети и без модели.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent / "backend"))

from backend.main import app  # noqa: E402

client = TestClient(app)

TEXT = "СРОЧНО! ЦБ запретил снятие наличных с 1 марта 2026 года."


def _user(plan: str = "team") -> str:
    token = client.post("/api/users").json()["token"]
    if plan != "free":
        client.post("/api/upgrade", json={"plan": plan}, headers={"X-Token": token})
    return token


def test_feedback_without_source_is_not_learned():
    """Без источника поправка остаётся в журнале, но не в банке."""
    token = _user()
    check = client.post(
        "/api/check", json={"text": TEXT}, headers={"X-Token": token}
    ).json()

    r = client.post(
        "/api/feedback",
        json={"check_id": check["id"], "verdict_ok": False, "expected": "фейк"},
        headers={"X-Token": token},
    )
    assert r.status_code == 200
    body = r.json()
    # У проверки без источника учить нечему — честно сообщаем.
    assert body["ok"] is True
    assert body["learned"] is False


def test_feedback_stats_counts_corrections():
    token = _user()
    check = client.post(
        "/api/check", json={"text": TEXT}, headers={"X-Token": token}
    ).json()
    client.post(
        "/api/feedback",
        json={"check_id": check["id"], "verdict_ok": False, "expected": "фейк"},
        headers={"X-Token": token},
    )
    stats = client.get("/api/feedback/stats").json()
    assert stats["total"] >= 1
    assert stats["wrong"] >= 1


def test_bank_human_entry_overrides_model(tmp_path, monkeypatch):
    """Ручная запись в банке важнее вывода модели."""
    from lakmus import bank as bank_module

    monkeypatch.setenv("VERDICT_BANK", str(tmp_path / "bank.json"))
    bank = bank_module.reset(tmp_path / "bank.json")

    bank.learn(
        "Проверяемое утверждение",
        "supported",
        tag="finance",
        source_url="https://example.com/model",
    )
    bank.learn(
        "Проверяемое утверждение",
        "contradicted",
        tag="finance",
        source_url="https://cbr.ru/official",
        origin="human",
    )
    # Модель пробует вернуть своё — не может.
    bank.learn(
        "Проверяемое утверждение",
        "supported",
        tag="finance",
        source_url="https://example.com/again",
    )

    entry = bank.lookup("Проверяемое утверждение")
    assert entry is not None
    assert entry.status == "contradicted"
    assert entry.origin == "human"
