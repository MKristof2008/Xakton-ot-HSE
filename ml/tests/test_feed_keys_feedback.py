"""Лента, API-ключи и обратная связь.

Три вещи из разговора с экспертом, которые раньше были только словами:
«дайте проверенные новости», «корпорации покупают токены» и «модель
будет дообучаться на фидбеке».
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Отдельная база на файле: с «:memory:» каждая связь sqlite получает
# пустую базу, и данные между запросами не видны.
_DB = Path(tempfile.mkdtemp(prefix="revizor-test-")) / "test.db"
os.environ["VERDICT_DB"] = str(_DB)

from backend.main import app  # noqa: E402

client = TestClient(app)
TEXT = "СРОЧНО! ЦБ запретил наличные с 1 марта 2026 года!"


def new_user(plan: str = "free") -> str:
    token = client.post("/api/users").json()["token"]
    if plan != "free":
        client.post("/api/upgrade", json={"plan": plan}, headers={"X-Token": token})
    return token


# ---------- лента ----------

def test_feed_returns_items_with_passport():
    client.post("/api/check", json={"text": TEXT}, headers={"X-Token": new_user()})
    body = client.get("/api/feed").json()
    assert body["items"], "после проверки лента не должна быть пустой"
    item = body["items"][0]
    assert item["passport"].startswith("/p/")
    assert item["level_label"]
    assert body["verified"] + body["refuted"] + body["unclear"] == len(body["items"])


def test_feed_counts_match_items():
    body = client.get("/api/feed?limit=5").json()
    levels = [i["level"] for i in body["items"]]
    assert body["verified"] == sum(1 for l in levels if l in ("confirmed", "likely_real"))
    assert body["refuted"] == sum(1 for l in levels if l == "likely_fake")


# ---------- API-ключи ----------

def test_keys_require_team_plan():
    token = new_user("pro")
    r = client.post("/api/keys", json={"label": "x"}, headers={"X-Token": token})
    assert r.status_code == 402
    assert r.json()["error"]["code"] == "PLAN_REQUIRED"


def test_keys_require_auth():
    r = client.post("/api/keys", json={"label": "x"})
    assert r.status_code == 401


def test_team_can_issue_and_use_key():
    token = new_user("team")
    created = client.post(
        "/api/keys", json={"label": "редакция"}, headers={"X-Token": token}
    ).json()
    raw = created["key"]
    assert raw.startswith("rvz_")
    assert created["prefix"] == raw[:12]

    # Ключ работает вместо токена и даёт тариф команды (полный разбор).
    body = client.post(
        "/api/check", json={"text": TEXT}, headers={"X-Api-Key": raw}
    ).json()
    assert body["plan"] == "team"
    assert "claims" in body


def test_key_not_stored_in_plain_text():
    """В базе только хеш: список ключей не отдаёт сам ключ."""
    token = new_user("team")
    created = client.post("/api/keys", json={"label": "a"}, headers={"X-Token": token}).json()
    listed = client.get("/api/keys", headers={"X-Token": token}).json()
    assert listed["items"]
    for item in listed["items"]:
        assert "key" not in item
        assert created["key"] not in str(item)
    assert listed["usage"]["checks"] >= 0


def test_revoked_key_stops_working():
    token = new_user("team")
    created = client.post("/api/keys", json={"label": "b"}, headers={"X-Token": token}).json()
    ok = client.delete(f"/api/keys/{created['id']}", headers={"X-Token": token})
    assert ok.status_code == 200

    r = client.post(
        "/api/check", json={"text": TEXT}, headers={"X-Api-Key": created["key"]}
    )
    # Отозванный ключ не даёт доступа: запрос отклоняется, как без входа.
    assert r.status_code == 401


def test_cannot_revoke_someone_elses_key():
    owner = new_user("team")
    other = new_user("team")
    created = client.post("/api/keys", json={"label": "c"}, headers={"X-Token": owner}).json()
    r = client.delete(f"/api/keys/{created['id']}", headers={"X-Token": other})
    assert r.status_code == 404


# ---------- обратная связь ----------

def test_feedback_accepted_and_counted():
    token = new_user()
    check = client.post("/api/check", json={"text": TEXT}, headers={"X-Token": token}).json()
    r = client.post(
        "/api/feedback",
        json={"check_id": check["id"], "verdict_ok": False, "expected": "фейк"},
        headers={"X-Token": token},
    )
    assert r.status_code == 200
    assert r.json()["ok"] is True

    stats = client.get("/api/feedback/stats").json()
    assert stats["total"] >= 1
    assert stats["wrong"] >= 1
    assert 0.0 <= stats["accuracy"] <= 1.0


def test_feedback_unknown_check_rejected():
    r = client.post("/api/feedback", json={"check_id": "chk_nope", "verdict_ok": True})
    assert r.status_code == 404


def test_feedback_bad_expected_rejected():
    token = new_user()
    check = client.post("/api/check", json={"text": TEXT}, headers={"X-Token": token}).json()
    r = client.post(
        "/api/feedback",
        json={"check_id": check["id"], "verdict_ok": False, "expected": "может быть"},
        headers={"X-Token": token},
    )
    assert r.status_code == 422
