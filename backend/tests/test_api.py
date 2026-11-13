"""Тесты API «Свидетель».

Пути к медиа читаются при импорте приложения, поэтому временный каталог
задаётся до импорта. База — своя на каждый тест через WITNESS_DB (tmp_path).
"""

from __future__ import annotations

import io
import os
import shutil
import tempfile
import time

import pytest

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_DIR = os.path.dirname(BACKEND_DIR)

if REPO_DIR not in os.sys.path:
    os.sys.path.insert(0, REPO_DIR)
if BACKEND_DIR not in os.sys.path:
    os.sys.path.insert(0, BACKEND_DIR)

MEDIA_TMP = tempfile.mkdtemp(prefix="witness_media_")
os.environ["WITNESS_MEDIA"] = MEDIA_TMP

from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

import events  # noqa: E402
import main as backend_main  # noqa: E402
import store  # noqa: E402


def pytest_sessionfinish(session, exitstatus):  # pragma: no cover - уборка
    shutil.rmtree(MEDIA_TMP, ignore_errors=True)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """Клиент с временной БД на каждый тест (store читает WITNESS_DB при вызове)."""
    monkeypatch.setenv("WITNESS_DB", str(tmp_path / "witness.db"))
    events.reset_broker()
    with TestClient(backend_main.app) as test_client:
        yield test_client
    events.reset_broker()


def _image_bytes(fmt: str = "PNG", size=(640, 480), color=(120, 40, 40)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format=fmt)
    return buffer.getvalue()


def _upload(client, data: bytes, name="photo.png", mime="image/png", **form):
    fields = {
        "caption": "Дым над заводом, Люберцы",
        "location": "Люберцы",
        "shot_at": "2026-11-13T15:12:00Z",
    }
    fields.update(form)
    files = {"file": (name, data, mime)}
    return client.post("/api/offers", files=files, data=fields)


def _wait_offer(client, offer_id: str, timeout: float = 20.0) -> str:
    """Дождаться, пока фоновая проверка перестанет быть checking."""
    deadline = time.time() + timeout
    status = "checking"
    while time.time() < deadline:
        status = client.get(f"/api/offers/{offer_id}").json()["status"]
        if status != "checking":
            return status
        time.sleep(0.05)
    raise AssertionError(f"заявка {offer_id} осталась в {status}")


def _make_listing(price: int = 4200) -> str:
    """Лот напрямую через хранилище — для тестов покупки без пайплайна."""
    offer = store.create_offer(
        offer_id=store.new_id("off"),
        file_name="photo.jpg",
        file_size=1000,
        file_mime="image/jpeg",
        sha256="0" * 64,
        preview_url="/media/off_test/preview.jpg",
        caption="Дым над заводом",
        location="Люберцы",
        shot_at="2026-11-13T15:12:00Z",
    )
    listing = store.create_listing(
        offer_id=offer["id"],
        check_id="chk_test",
        title="Дым над заводом — фото с места",
        price_rub=price,
        trust={"score": 84, "uncertainty": 0.12, "coverage": 0.9,
               "level": "confirmed", "conflict": False},
        facts={"origin": "снято на камеру", "shot_at": "2026-11-13T15:12:00Z",
               "geo": "Люберцы", "unique": True, "similar_in_archive": 0},
        why_price=["База: 1500 ₽", f"Итого: {price} ₽"],
        preview_url="/media/off_test/preview.jpg",
    )
    store.set_offer_status(offer["id"], "listed")
    return listing["id"]


# --------------------------------------------------------------------------
# Загрузка заявки
# --------------------------------------------------------------------------

def test_create_offer(client):
    response = _upload(client, _image_bytes("JPEG"), "моё фото.jpg", "image/jpeg")
    assert response.status_code == 201, response.text
    offer = response.json()

    assert offer["id"].startswith("off_")
    assert offer["status"] == "checking"
    assert offer["file"]["mime"] == "image/jpeg"
    assert offer["file"]["name"] == "моё фото.jpg"
    assert offer["file"]["size"] > 0
    assert len(offer["file"]["sha256"]) == 64
    assert offer["file"]["preview_url"] == f"/media/{offer['id']}/preview.jpg"

    # Имя на диске своё: путь строится из id, а не из пользовательского имени.
    preview = client.get(offer["file"]["preview_url"])
    assert preview.status_code == 200
    with Image.open(io.BytesIO(preview.content)) as image:
        assert max(image.size) <= 800

    # Файл сохраняется под своим id.
    assert os.path.isfile(os.path.join(MEDIA_TMP, offer["id"], "preview.jpg"))


def test_offer_check_after_pipeline(client):
    offer_id = _upload(client, _image_bytes("PNG")).json()["id"]
    status = _wait_offer(client, offer_id)
    assert status in {"listed", "rejected", "sold"}

    check = client.get(f"/api/offers/{offer_id}/check")
    assert check.status_code == 200, check.text
    payload = check.json()
    assert payload["offer_id"] == offer_id
    assert payload["input"]["type"] == "image"
    assert payload["status"] == "done"
    assert payload["signals"], "сигналы должны быть"
    ids = {signal["id"] for signal in payload["signals"]}
    # Ошибка выбора сигналов по InputType.image увела бы набор в текстовый.
    assert "metadata" in ids
    assert "claims" not in ids


def test_offer_rejected_or_listed(client):
    offer_id = _upload(client, _image_bytes("PNG")).json()["id"]
    status = _wait_offer(client, offer_id)
    listings = client.get("/api/listings").json()
    ours = [item for item in listings if item["offer_id"] == offer_id]

    if status == "listed":
        assert len(ours) == 1
        listing = ours[0]
        assert listing["price_rub"] > 0
        assert listing["state"] == "available"
        assert listing["check_id"]
        assert listing["why_price"], "цена обязана объясняться"
        assert listing["preview_url"] == f"/media/{offer_id}/preview.jpg"
    else:
        assert status == "rejected"
        assert ours == []


def test_check_before_done_returns_409_or_result(client):
    """Пока проверки нет в БД — контрактная ошибка, а не голый detail."""
    offer = store.create_offer(
        offer_id="off_pending", file_name="a.png", file_size=1,
        file_mime="image/png", sha256="0" * 64, preview_url="/media/off_pending/preview.jpg",
    )
    response = client.get(f"/api/offers/{offer['id']}/check")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CHECK_FAILED"


def test_unsupported_declared_type(client):
    response = _upload(client, b"hello", "note.txt", "text/plain")
    assert response.status_code == 415
    assert response.json()["error"] == {
        "code": "UNSUPPORTED_TYPE",
        "message": "поддерживаются только JPEG, PNG и WebP",
    }


def test_mime_spoofing_rejected(client):
    """Пользователь назвал text-файл картинкой: проверяем реальный формат."""
    response = _upload(client, b"definitely not an image", "photo.png", "image/png")
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "UNSUPPORTED_TYPE"


def test_mime_mismatch_rejected(client):
    response = _upload(client, _image_bytes("PNG"), "photo.jpg", "image/jpeg")
    assert response.status_code == 415


def test_too_large_file(client):
    big = _image_bytes("PNG", size=(10, 10)) + b"\x00" * (15 * 1024 * 1024)
    response = _upload(client, big, "big.png", "image/png")
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "TOO_LARGE"


def test_filename_is_sanitized(client):
    response = _upload(client, _image_bytes("PNG"), "../../evil\u0000name.png", "image/png")
    assert response.status_code == 201
    offer = response.json()
    assert ".." not in offer["file"]["name"]
    assert "/" not in offer["file"]["name"]
    dirs = os.listdir(MEDIA_TMP)
    assert offer["id"] in dirs


def test_unknown_offer_is_404(client):
    response = client.get("/api/offers/off_nope")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_events_stream(client):
    offer_id = _upload(client, _image_bytes("PNG")).json()["id"]
    _wait_offer(client, offer_id)

    with client.stream("GET", f"/api/offers/{offer_id}/events") as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        body = "".join(response.iter_text())

    assert "event: signal_done" in body
    assert "event: done" in body
    assert "signal_done" in body


# --------------------------------------------------------------------------
# Лоты и сделки
# --------------------------------------------------------------------------

def test_buy_commission(client):
    listing_id = _make_listing(4200)
    response = client.post(f"/api/listings/{listing_id}/buy")
    assert response.status_code == 200, response.text
    deal = response.json()

    assert deal["deal_id"] == deal["id"]
    assert deal["amount_rub"] == 4200
    assert deal["commission_rub"] == 840          # ровно 20 %
    assert deal["author_payout_rub"] == 3360
    assert deal["commission_rub"] + deal["author_payout_rub"] == deal["amount_rub"]
    assert deal["status"] == "paid"

    listing = client.get(f"/api/listings/{listing_id}").json()
    assert listing["state"] == "sold"
    assert client.get("/api/offers/" + listing["offer_id"]).json()["status"] == "sold"


def test_second_buy_conflicts(client):
    listing_id = _make_listing(1000)
    assert client.post(f"/api/listings/{listing_id}/buy").status_code == 200
    response = client.post(f"/api/listings/{listing_id}/buy")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ALREADY_SOLD"


def test_listings_filters(client):
    cheap = _make_listing(1000)
    pricey = _make_listing(9000)

    assert {item["id"] for item in client.get("/api/listings").json()} == {cheap, pricey}

    filtered = client.get("/api/listings", params={"min_price": 5000}).json()
    assert [item["id"] for item in filtered] == [pricey]

    assert client.get("/api/listings", params={"state": "available"}).json()
    client.post(f"/api/listings/{cheap}/buy")
    sold = client.get("/api/listings", params={"state": "sold"}).json()
    assert [item["id"] for item in sold] == [cheap]

    bad = client.get("/api/listings", params={"state": "weird"})
    assert bad.status_code == 400
    assert bad.json()["error"]["code"] == "BAD_INPUT"

    missing = client.get("/api/listings/lst_nope")
    assert missing.status_code == 404


def test_stats(client):
    _make_listing(4200)
    sold_id = _make_listing(1000)
    client.post(f"/api/listings/{sold_id}/buy")

    stats = client.get("/api/stats").json()
    assert stats["offers"] == 2
    assert stats["listings"] == 2
    assert stats["sold"] == 1
    assert stats["turnover_rub"] == 1000
    assert stats["commission_rub"] == 200


def test_deals_list(client):
    listing_id = _make_listing(5000)
    client.post(f"/api/listings/{listing_id}/buy")
    deals = client.get("/api/deals").json()
    assert len(deals) == 1
    assert deals[0]["listing_id"] == listing_id
    assert deals[0]["commission_rub"] == 1000


def test_market_demo_without_file(client, monkeypatch, tmp_path):
    monkeypatch.setenv("WITNESS_DEMO_LISTINGS", str(tmp_path / "missing.json"))
    response = client.get("/api/market/demo")
    assert response.status_code == 200
    assert response.json()["items"] == []


def test_market_demo_with_file(client, monkeypatch, tmp_path):
    path = tmp_path / "demo_listings.json"
    path.write_text('[{"id": "lst_1", "price_rub": 100}]', encoding="utf-8")
    monkeypatch.setenv("WITNESS_DEMO_LISTINGS", str(path))
    body = client.get("/api/market/demo").json()
    assert [item["id"] for item in body["items"]] == ["lst_1"]


def test_no_legacy_verify(client):
    assert client.post("/api/verify").status_code in (404, 405)


def test_cors_preflight(client):
    ok = client.options(
        "/api/stats",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"},
    )
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:5173"

    bad = client.options(
        "/api/stats",
        headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "GET"},
    )
    assert bad.headers.get("access-control-allow-origin") is None