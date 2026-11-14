"""Общие фикстуры тестов API.

Проверка требует аккаунта — это продуктовое решение, а не временное
ограничение. Поэтому тесты не должны ходить «гостем»: фикстура создаёт
пользователя и подставляет токен, а сами тесты проверяют логику, а не
аутентификацию (для неё есть отдельные тесты).
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("VERDICT_DB", ":memory:")

from backend.main import app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def _make_client() -> tuple[TestClient, dict[str, str]]:
    """Клиент и заголовки с токеном нового аккаунта."""
    client = TestClient(app)
    token = client.post("/api/users").json()["token"]
    return client, {"X-Token": token}


@pytest.fixture
def client_auth() -> tuple[TestClient, dict[str, str]]:
    return _make_client()


@pytest.fixture
def auth_headers() -> dict[str, str]:
    """Только заголовки — когда клиент создаётся в самом тесте."""
    client = TestClient(app)
    token = client.post("/api/users").json()["token"]
    return {"X-Token": token}


@pytest.fixture
def pro_headers() -> dict[str, str]:
    """Заголовки пользователя с подпиской."""
    client = TestClient(app)
    token = client.post("/api/users").json()["token"]
    client.post("/api/upgrade", json={"plan": "pro"}, headers={"X-Token": token})
    return {"X-Token": token}
