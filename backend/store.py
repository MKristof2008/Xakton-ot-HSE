"""Хранилище проверок, топов и подписок. SQLite на stdlib.

Три сущности по замыслу эксперта NMH:
  checks   — каждая проверка, включая анонимные;
  top      — агрегат по тексту: сколько раз проверяли, какой вердикт;
  users    — тариф (free / pro) и ключ доступа.

Топы считаются из checks, а не ведутся отдельно: это защита от
рассинхрона между счётчиком и историей.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Optional

DEFAULT_DB = Path(__file__).resolve().parent / "data" / "verdict.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS checks (
    id          TEXT PRIMARY KEY,
    text        TEXT NOT NULL,
    text_hash   TEXT NOT NULL,
    verdict     TEXT NOT NULL,
    score       INTEGER NOT NULL,
    uncertainty REAL NOT NULL,
    level       TEXT NOT NULL,
    full_json   TEXT NOT NULL,
    user_id     TEXT,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_checks_hash ON checks(text_hash);
CREATE INDEX IF NOT EXISTS idx_checks_created ON checks(created_at);

CREATE TABLE IF NOT EXISTS users (
    id          TEXT PRIMARY KEY,
    plan        TEXT NOT NULL DEFAULT 'free',
    token       TEXT NOT NULL UNIQUE,
    created_at  TEXT NOT NULL,
    expires_at  TEXT
);

CREATE TABLE IF NOT EXISTS top_pins (
    text_hash   TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    pinned_at   TEXT NOT NULL
);
"""

FREE_CHECKS_PER_DAY = 10


def db_path() -> Path:
    return Path(os.environ.get("VERDICT_DB") or DEFAULT_DB)


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def text_hash(text: str) -> str:
    """Одинаковый текст → одинаковый хеш. Основа топов."""
    normalized = " ".join((text or "").lower().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ---------- пользователи и тарифы ----------

def create_user(plan: str = "free") -> dict[str, Any]:
    uid = f"usr_{secrets.token_hex(4)}"
    token = secrets.token_urlsafe(24)
    with connect() as conn:
        conn.execute(
            "INSERT INTO users(id, plan, token, created_at) VALUES(?,?,?,?)",
            (uid, plan, token, now_iso()),
        )
    return {"id": uid, "plan": plan, "token": token}


def user_by_token(token: str) -> Optional[dict[str, Any]]:
    if not token:
        return None
    with connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE token = ?", (token,)).fetchone()
    return dict(row) if row else None


def upgrade_user(token: str, plan: str = "pro") -> bool:
    """Демо-апгрейд тарифа. В реальном продукте здесь платёжный провайдер."""
    if plan not in ("free", "pro"):
        return False
    with connect() as conn:
        cur = conn.execute("UPDATE users SET plan = ? WHERE token = ?", (plan, token))
    return cur.rowcount > 0


def checks_today(user_id: str) -> int:
    day = time.strftime("%Y-%m-%d", time.gmtime())
    with connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM checks WHERE user_id = ? AND created_at LIKE ?",
            (user_id, f"{day}%"),
        ).fetchone()
    return int(row["n"]) if row else 0


def free_quota_left(user_id: str) -> int:
    return max(0, FREE_CHECKS_PER_DAY - checks_today(user_id))


# ---------- проверки ----------

def save_check(
    *,
    text: str,
    verdict: str,
    score: int,
    uncertainty: float,
    level: str,
    full: dict[str, Any],
    user_id: Optional[str] = None,
) -> str:
    check_id = f"chk_{secrets.token_hex(5)}"
    with connect() as conn:
        conn.execute(
            "INSERT INTO checks(id, text, text_hash, verdict, score, uncertainty, level,"
            " full_json, user_id, created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                check_id,
                text,
                text_hash(text),
                verdict,
                int(score),
                float(uncertainty),
                level,
                json.dumps(full, ensure_ascii=False),
                user_id,
                now_iso(),
            ),
        )
    return check_id


def get_check(check_id: str) -> Optional[dict[str, Any]]:
    with connect() as conn:
        row = conn.execute("SELECT * FROM checks WHERE id = ?", (check_id,)).fetchone()
    if not row:
        return None
    data = dict(row)
    data["full"] = json.loads(data.pop("full_json"))
    return data


def get_by_hash(text_hash_value: str) -> Optional[dict[str, Any]]:
    """Последняя проверка этого утверждения — основа «паспорта».

    Паспорт один на утверждение, а не на каждую проверку: сколько бы раз
    текст ни проверяли, ссылка ведёт на актуальный результат.
    """
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM checks WHERE text_hash = ? ORDER BY created_at DESC LIMIT 1",
            (text_hash_value,),
        ).fetchone()
        count = conn.execute(
            "SELECT COUNT(*) AS n FROM checks WHERE text_hash = ?",
            (text_hash_value,),
        ).fetchone()["n"]
    if not row:
        return None
    data = dict(row)
    data["full"] = json.loads(data.pop("full_json"))
    data["checks_count"] = int(count)
    return data


def check_count_by_hash(text_hash_value: str) -> int:
    with connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM checks WHERE text_hash = ?",
            (text_hash_value,),
        ).fetchone()
    return int(row["n"]) if row else 0


# ---------- топы ----------

def top_items(limit: int = 20, window_hours: int = 48) -> list[dict[str, Any]]:
    """Топ проверяемых утверждений за окно.

    Считается по text_hash: одна и та же новость от ста человек — одна
    строка с счётчиком 100. Показываем и вердикт, и разброс мнений.

    Плюс «живость»: сколько проверок за последний час и минуту. Это не
    декорация — по этим числам видно, что утверждение сейчас на волне,
    а не просто накопило счётчик за неделю.
    """
    now = time.time()
    since = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - window_hours * 3600))
    hour_ago = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - 3600))
    minute_ago = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - 60))

    with connect() as conn:
        rows = conn.execute(
            """
            SELECT text_hash,
                   MIN(text)                         AS sample_text,
                   COUNT(*)                          AS checks_count,
                   MAX(created_at)                   AS last_at,
                   SUM(CASE WHEN created_at >= ? THEN 1 ELSE 0 END) AS last_hour,
                   SUM(CASE WHEN created_at >= ? THEN 1 ELSE 0 END) AS last_minute,
                   (SELECT verdict FROM checks c2
                     WHERE c2.text_hash = c.text_hash
                     ORDER BY created_at DESC LIMIT 1) AS verdict,
                   (SELECT score FROM checks c3
                     WHERE c3.text_hash = c.text_hash
                     ORDER BY created_at DESC LIMIT 1) AS score,
                   (SELECT level FROM checks c4
                     WHERE c4.text_hash = c.text_hash
                     ORDER BY created_at DESC LIMIT 1) AS level,
                   COUNT(DISTINCT verdict)           AS verdict_variants
              FROM checks c
             WHERE created_at >= ?
             GROUP BY text_hash
             ORDER BY last_hour DESC, checks_count DESC, last_at DESC
             LIMIT ?
            """,
            (hour_ago, minute_ago, since, int(limit)),
        ).fetchall()
        pinned = {r["text_hash"] for r in conn.execute("SELECT text_hash FROM top_pins")}
    out = []
    for row in rows:
        item = dict(row)
        item["pinned"] = item["text_hash"] in pinned
        item["last_hour"] = int(item.get("last_hour") or 0)
        item["last_minute"] = int(item.get("last_minute") or 0)
        out.append(item)
    return out


def pin_top(text_hash_value: str, title: str) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO top_pins(text_hash, title, pinned_at) VALUES(?,?,?)",
            (text_hash_value, title[:200], now_iso()),
        )


def stats() -> dict[str, Any]:
    with connect() as conn:
        total = conn.execute("SELECT COUNT(*) AS n FROM checks").fetchone()["n"]
        unique = conn.execute("SELECT COUNT(DISTINCT text_hash) AS n FROM checks").fetchone()["n"]
        fake = conn.execute(
            "SELECT COUNT(*) AS n FROM checks WHERE level = 'likely_fake'"
        ).fetchone()["n"]
        real = conn.execute(
            "SELECT COUNT(*) AS n FROM checks WHERE level IN ('confirmed','likely_real')"
        ).fetchone()["n"]
        fog = conn.execute("SELECT COUNT(*) AS n FROM checks WHERE level = 'fog'").fetchone()["n"]
        pro = conn.execute("SELECT COUNT(*) AS n FROM users WHERE plan = 'pro'").fetchone()["n"]
    return {
        "checks": int(total),
        "unique_claims": int(unique),
        "fake": int(fake),
        "real": int(real),
        "fog": int(fog),
        "pro_users": int(pro),
    }
