"""Хранилище «Свидетель» на stdlib sqlite3.

Чистые функции поверх простого SQL, без ORM. Путь к базе задаётся
переменной окружения ``WITNESS_DB`` (по умолчанию ``backend/data/witness.db``).

Таблицы: ``offers``, ``checks``, ``listings``, ``deals``.
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

BACKEND_DIR = Path(__file__).resolve().parent
DEFAULT_DB_PATH = BACKEND_DIR / "data" / "witness.db"

#: Комиссия платформы — 20 % от суммы сделки.
COMMISSION_RATE = 0.20
#: Срок жизни лота.
LISTING_TTL_DAYS = 7

SCHEMA = """
CREATE TABLE IF NOT EXISTS offers (
    id          TEXT PRIMARY KEY,
    created_at  TEXT NOT NULL,
    status      TEXT NOT NULL,
    author_id   TEXT NOT NULL,
    author_name TEXT NOT NULL,
    payout      INTEGER NOT NULL DEFAULT 0,
    file_name   TEXT NOT NULL,
    file_size   INTEGER NOT NULL,
    file_mime   TEXT NOT NULL,
    sha256      TEXT NOT NULL,
    preview_url TEXT NOT NULL,
    caption     TEXT NOT NULL DEFAULT '',
    location    TEXT NOT NULL DEFAULT '',
    shot_at     TEXT
);

CREATE TABLE IF NOT EXISTS checks (
    offer_id   TEXT PRIMARY KEY REFERENCES offers(id),
    check_id   TEXT NOT NULL,
    status     TEXT NOT NULL,
    result_json TEXT,
    error      TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS listings (
    id          TEXT PRIMARY KEY,
    offer_id    TEXT NOT NULL REFERENCES offers(id),
    check_id    TEXT NOT NULL,
    title       TEXT NOT NULL,
    price_rub   INTEGER NOT NULL,
    currency    TEXT NOT NULL DEFAULT 'RUB',
    state       TEXT NOT NULL DEFAULT 'available',
    created_at  TEXT NOT NULL,
    expires_at  TEXT NOT NULL,
    trust_json  TEXT NOT NULL,
    facts_json  TEXT NOT NULL,
    why_json    TEXT NOT NULL,
    preview_url TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS deals (
    id                TEXT PRIMARY KEY,
    listing_id        TEXT NOT NULL REFERENCES listings(id),
    buyer_id          TEXT NOT NULL,
    buyer_name        TEXT NOT NULL,
    amount_rub        INTEGER NOT NULL,
    commission_rub    INTEGER NOT NULL,
    author_payout_rub INTEGER NOT NULL,
    status            TEXT NOT NULL DEFAULT 'paid',
    created_at        TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_listings_state ON listings(state);
CREATE INDEX IF NOT EXISTS idx_deals_listing ON deals(listing_id);
"""


class NotFound(Exception):
    """Запись не найдена."""


class AlreadySold(Exception):
    """Лот уже продан или недоступен."""


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def utcnow_iso() -> str:
    return utcnow().isoformat(timespec="seconds").replace("+00:00", "Z")


def new_id(prefix: str) -> str:
    """Короткий публичный id вида ``off_7f3a91``."""
    return f"{prefix}_{uuid.uuid4().hex[:6]}"


def db_path() -> Path:
    """Путь к базе: WITNESS_DB или backend/data/witness.db."""
    return Path(os.environ.get("WITNESS_DB") or DEFAULT_DB_PATH)


def connect() -> sqlite3.Connection:
    """Открыть соединение и гарантировать схему."""
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


# --------------------------------------------------------------------------
# Offer
# --------------------------------------------------------------------------

def create_offer(
    *,
    offer_id: str,
    file_name: str,
    file_size: int,
    file_mime: str,
    sha256: str,
    preview_url: str,
    caption: str = "",
    location: str = "",
    shot_at: Optional[str] = None,
    author_id: str = "usr_anon",
    author_name: str = "Аноним",
) -> dict[str, Any]:
    """Создать заявку в статусе ``checking``."""
    with connect() as conn:
        conn.execute(
            """INSERT INTO offers (id, created_at, status, author_id, author_name, payout,
                                   file_name, file_size, file_mime, sha256, preview_url,
                                   caption, location, shot_at)
               VALUES (?, ?, 'checking', ?, ?, 0, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (offer_id, utcnow_iso(), author_id, author_name, file_name, file_size,
             file_mime, sha256, preview_url, caption, location, shot_at),
        )
    offer = get_offer(offer_id)
    assert offer is not None
    return offer


def get_offer(offer_id: str) -> Optional[dict[str, Any]]:
    """Заявка в форме контракта или ``None``."""
    with connect() as conn:
        row = conn.execute("SELECT * FROM offers WHERE id = ?", (offer_id,)).fetchone()
    return _offer_dict(row) if row else None


def set_offer_status(offer_id: str, status: str) -> None:
    with connect() as conn:
        conn.execute("UPDATE offers SET status = ? WHERE id = ?", (status, offer_id))


def listing_id_for_offer(offer_id: str) -> Optional[str]:
    with connect() as conn:
        row = conn.execute(
            "SELECT id FROM listings WHERE offer_id = ? ORDER BY created_at DESC LIMIT 1",
            (offer_id,),
        ).fetchone()
    return row["id"] if row else None


def _offer_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "status": row["status"],
        "created_at": row["created_at"],
        "author": {
            "id": row["author_id"],
            "display_name": row["author_name"],
            "payout": row["payout"],
        },
        "file": {
            "name": row["file_name"],
            "size": row["file_size"],
            "mime": row["file_mime"],
            "sha256": row["sha256"],
            "preview_url": row["preview_url"],
        },
        "caption": row["caption"],
        "location": row["location"],
        "shot_at": row["shot_at"],
    }


# --------------------------------------------------------------------------
# Check
# --------------------------------------------------------------------------

def save_check(
    offer_id: str,
    check_id: str,
    result: Optional[dict[str, Any]] = None,
    *,
    status: str = "done",
    error: Optional[str] = None,
) -> None:
    """Сохранить результат проверки (или факт сбоя) для заявки."""
    payload = json.dumps(result, ensure_ascii=False) if result is not None else None
    with connect() as conn:
        conn.execute(
            """INSERT INTO checks (offer_id, check_id, status, result_json, error, created_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(offer_id) DO UPDATE SET
                   check_id = excluded.check_id,
                   status = excluded.status,
                   result_json = excluded.result_json,
                   error = excluded.error,
                   created_at = excluded.created_at""",
            (offer_id, check_id, status, payload, error, utcnow_iso()),
        )


def get_check_row(offer_id: str) -> Optional[dict[str, Any]]:
    """Сырая запись проверки: ``{check_id, status, result, error}`` или ``None``."""
    with connect() as conn:
        row = conn.execute("SELECT * FROM checks WHERE offer_id = ?", (offer_id,)).fetchone()
    if row is None:
        return None
    result = json.loads(row["result_json"]) if row["result_json"] else None
    return {
        "offer_id": row["offer_id"],
        "check_id": row["check_id"],
        "status": row["status"],
        "result": result,
        "error": row["error"],
    }


# --------------------------------------------------------------------------
# Listing
# --------------------------------------------------------------------------

def create_listing(
    *,
    offer_id: str,
    check_id: str,
    title: str,
    price_rub: int,
    trust: dict[str, Any],
    facts: dict[str, Any],
    why_price: list[str],
    preview_url: str,
    currency: str = "RUB",
) -> dict[str, Any]:
    """Выставить лот в состояние ``available``."""
    listing_id = new_id("lst")
    created = utcnow()
    expires = created + timedelta(days=LISTING_TTL_DAYS)
    with connect() as conn:
        conn.execute(
            """INSERT INTO listings (id, offer_id, check_id, title, price_rub, currency, state,
                                     created_at, expires_at, trust_json, facts_json, why_json,
                                     preview_url)
               VALUES (?, ?, ?, ?, ?, ?, 'available', ?, ?, ?, ?, ?, ?)""",
            (listing_id, offer_id, check_id, title, int(price_rub), currency,
             _iso(created), _iso(expires),
             json.dumps(trust, ensure_ascii=False),
             json.dumps(facts, ensure_ascii=False),
             json.dumps(why_price, ensure_ascii=False),
             preview_url),
        )
    listing = get_listing(listing_id)
    assert listing is not None
    return listing


def get_listing(listing_id: str) -> Optional[dict[str, Any]]:
    with connect() as conn:
        row = conn.execute("SELECT * FROM listings WHERE id = ?", (listing_id,)).fetchone()
    return _listing_dict(row) if row else None


def list_listings(
    *,
    state: Optional[str] = None,
    min_price: Optional[int] = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Лента лотов: фильтры по состоянию и минимальной цене, новые сверху."""
    query = "SELECT * FROM listings"
    clauses: list[str] = []
    params: list[Any] = []
    if state:
        clauses.append("state = ?")
        params.append(state)
    if min_price is not None:
        clauses.append("price_rub >= ?")
        params.append(int(min_price))
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(max(1, min(int(limit), 200)))
    with connect() as conn:
        rows = conn.execute(query, params).fetchall()
    return [_listing_dict(row) for row in rows]


def _listing_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "offer_id": row["offer_id"],
        "check_id": row["check_id"],
        "title": row["title"],
        "price_rub": row["price_rub"],
        "currency": row["currency"],
        "state": row["state"],
        "created_at": row["created_at"],
        "expires_at": row["expires_at"],
        "trust": json.loads(row["trust_json"]),
        "facts": json.loads(row["facts_json"]),
        "why_price": json.loads(row["why_json"]),
        "preview_url": row["preview_url"],
    }


# --------------------------------------------------------------------------
# Deal
# --------------------------------------------------------------------------

def buy_listing(listing_id: str, buyer_id: str = "org_mash", buyer_name: str = "Mash") -> dict[str, Any]:
    """Купить лот: комиссия 20 %, лот и заявка переходят в ``sold``.

    Переход атомарный: ``UPDATE ... WHERE state = 'available'`` отсекает
    повторную покупку даже при параллельных запросах.
    """
    with connect() as conn:
        row = conn.execute("SELECT * FROM listings WHERE id = ?", (listing_id,)).fetchone()
        if row is None:
            raise NotFound(f"лот {listing_id} не найден")
        cur = conn.execute(
            "UPDATE listings SET state = 'sold' WHERE id = ? AND state = 'available'",
            (listing_id,),
        )
        if cur.rowcount != 1:
            raise AlreadySold(f"лот {listing_id} уже недоступен (состояние {row['state']})")

        amount = int(row["price_rub"])
        commission = int(round(amount * COMMISSION_RATE))
        payout = amount - commission
        deal = {
            "id": new_id("deal"),
            "listing_id": listing_id,
            "buyer": {"id": buyer_id, "name": buyer_name},
            "amount_rub": amount,
            "commission_rub": commission,
            "author_payout_rub": payout,
            "status": "paid",
            "created_at": utcnow_iso(),
        }
        conn.execute(
            """INSERT INTO deals (id, listing_id, buyer_id, buyer_name, amount_rub,
                                  commission_rub, author_payout_rub, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'paid', ?)""",
            (deal["id"], listing_id, buyer_id, buyer_name, amount,
             commission, payout, deal["created_at"]),
        )
        conn.execute("UPDATE offers SET status = 'sold' WHERE id = ?", (row["offer_id"],))
    return deal


def list_deals() -> list[dict[str, Any]]:
    """Сделки, новые сверху."""
    with connect() as conn:
        rows = conn.execute("SELECT * FROM deals ORDER BY created_at DESC").fetchall()
    return [
        {
            "id": row["id"],
            "listing_id": row["listing_id"],
            "buyer": {"id": row["buyer_id"], "name": row["buyer_name"]},
            "amount_rub": row["amount_rub"],
            "commission_rub": row["commission_rub"],
            "author_payout_rub": row["author_payout_rub"],
            "status": row["status"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]


# --------------------------------------------------------------------------
# Сводка
# --------------------------------------------------------------------------

def stats() -> dict[str, int]:
    """Заявки, лоты, продажи, оборот и комиссия."""
    with connect() as conn:
        offers = conn.execute("SELECT COUNT(*) FROM offers").fetchone()[0]
        listings = conn.execute("SELECT COUNT(*) FROM listings").fetchone()[0]
        sold = conn.execute("SELECT COUNT(*) FROM deals").fetchone()[0]
        turnover = conn.execute("SELECT COALESCE(SUM(amount_rub), 0) FROM deals").fetchone()[0]
        commission = conn.execute(
            "SELECT COALESCE(SUM(commission_rub), 0) FROM deals"
        ).fetchone()[0]
    return {
        "offers": int(offers),
        "listings": int(listings),
        "sold": int(sold),
        "turnover_rub": int(turnover),
        "commission_rub": int(commission),
    }


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")