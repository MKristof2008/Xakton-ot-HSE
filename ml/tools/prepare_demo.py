"""Подготовка стенда к защите: чистка демо-следов и аккаунты для жюри.

Запуск:
    py -3 -I ml/tools/prepare_demo.py            # показать, что будет сделано
    py -3 -I ml/tools/prepare_demo.py --apply    # выполнить

Что делает:

  1. Делает резервную копию базы рядом с оригиналом.
  2. Удаляет проверки, созданные раньше указанного времени (по умолчанию
     20:00 сегодня) — это следы наших прогонов и записи демо.
  3. Удаляет демо-аккаунты (demo*, free*, plus*, max*, probe*, rubric*,
     shot*, check*@example.com), чтобы топы и лента не показывали мусор.
  4. Создаёт аккаунты для жюри с понятными логинами и паролем.

Аккаунты жюри печатаются в конце: их можно отдать на защите.

Важно: удаляются только записи, созданные до границы. Всё, что появится
после, останется — чтобы живые проверки на защите не пропали.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ml"))
# backend лежит в корне проекта: импорт `from backend import store`
# требует корень в sys.path, а не папку backend.
sys.path.insert(0, str(ROOT))

DB = ROOT / "backend" / "data" / "verdict.db"

#: Маски демо-аккаунтов: всё, что мы создавали тестами и демо.
DEMO_PATTERNS = (
    "demo%@example.com",
    "free%@example.com",
    "plus%@example.com",
    "max%@example.com",
    "probe%@example.com",
    "rubric%@example.com",
    "shot%@example.com",
    "check%@example.com",
    "test%@example.com",
)

#: Аккаунты для жюри. Пароль один, чтобы не путались на стенде.
JUDGE_ACCOUNTS = (
    ("jury-base@revizor.demo", "База — короткий вердикт", "free"),
    ("jury-plus@revizor.demo", "Плюс — разбор и что делать", "pro"),
    ("jury-max@revizor.demo", "Макс — полный анализ и пересылка", "team"),
    ("jury-max-2@revizor.demo", "Макс — второй ноутбук", "team"),
)
JUDGE_PASSWORD = "revizor-2026"


def iso_before(hour: int, minute: int = 0) -> str:
    """Граница в формате базы: сегодняшняя дата, указанное время UTC."""
    now = datetime.now(timezone.utc)
    boundary = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return boundary.strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> int:
    parser = argparse.ArgumentParser(description="Подготовка стенда к защите")
    parser.add_argument("--apply", action="store_true", help="выполнить изменения")
    parser.add_argument(
        "--before", default="20:00",
        help="удалять записи раньше этого времени (ЧЧ:ММ, UTC), по умолчанию 20:00",
    )
    parser.add_argument(
        "--all", action="store_true",
        help="удалить все проверки и отзывы (чистый стенд для жюри)",
    )
    args = parser.parse_args()

    if args.all:
        # Всё, что есть в базе, — наши прогоны и демо. Для жюри нужен
        # пустой стенд: топы и лента не должны показывать тестовый мусор.
        boundary = "9999-12-31T23:59:59Z"
    else:
        hour, minute = (int(part) for part in args.before.split(":"))
        boundary = iso_before(hour, minute)

    if not DB.is_file():
        print(f"база не найдена: {DB}")
        return 1

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    checks_before = conn.execute(
        "SELECT COUNT(*) FROM checks WHERE created_at < ?", (boundary,)
    ).fetchone()[0]
    users_total = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]

    demo_where = " OR ".join("email LIKE ?" for _ in DEMO_PATTERNS)
    demo_users = conn.execute(
        f"SELECT COUNT(*) FROM users WHERE {demo_where}", DEMO_PATTERNS
    ).fetchone()[0]
    feedback_before = conn.execute(
        "SELECT COUNT(*) FROM feedback WHERE created_at < ?", (boundary,)
    ).fetchone()[0]

    print(f"База: {DB}")
    print(f"Граница: {boundary}")
    print(f"Проверок до границы: {checks_before}")
    print(f"Отзывов до границы: {feedback_before}")
    print(f"Всего аккаунтов: {users_total}, из них демо: {demo_users}")
    print()

    if not args.apply:
        print("Это предпросмотр. Чтобы выполнить: --apply")
        conn.close()
        return 0

    backup = DB.with_name(f"verdict-backup-{int(time.time())}.db")
    shutil.copy2(DB, backup)
    print(f"Резервная копия: {backup}")

    conn.execute("DELETE FROM checks WHERE created_at < ?", (boundary,))
    conn.execute("DELETE FROM feedback WHERE created_at < ?", (boundary,))
    # Топы считаются из checks, но старые закрепления чистим отдельно.
    conn.execute("DELETE FROM top_pins WHERE pinned_at < ?", (boundary,))
    conn.execute(f"DELETE FROM users WHERE {demo_where}", DEMO_PATTERNS)
    conn.commit()
    print("Демо-следы удалены.")

    # Аккаунты жюри создаём через тот же код, что и регистрация:
    # пароль хешируется так же, токен выпускается так же.
    #
    # Важно: своё соединение закрываем заранее. SQLite не даёт писать из
    # второго соединения, пока первое держит незавершённую транзакцию, —
    # иначе «database is locked».
    from backend import store

    conn.close()
    conn = None

    created: list[tuple[str, str, str]] = []
    for email, label, plan in JUDGE_ACCOUNTS:
        with sqlite3.connect(DB) as own:
            own.row_factory = sqlite3.Row
            existing = own.execute(
                "SELECT id FROM users WHERE email = ?", (email,)
            ).fetchone()
            if existing is not None:
                own.execute(
                    "UPDATE users SET plan = ? WHERE email = ?", (plan, email)
                )
                created.append((email, label, plan))
                continue

        user = store.register_user(email, JUDGE_PASSWORD, label)
        if user is None:
            print(f"  не удалось создать {email}")
            continue
        with sqlite3.connect(DB) as own:
            own.execute(
                "UPDATE users SET plan = ? WHERE id = ?", (plan, user["id"])
            )
        created.append((email, label, plan))

    print()
    print("=" * 62)
    print("АККАУНТЫ ДЛЯ ЖЮРИ")
    print("=" * 62)
    print(f"Пароль для всех: {JUDGE_PASSWORD}")
    print()
    for email, label, plan in created:
        plan_name = {"free": "База", "pro": "Плюс", "team": "Макс"}.get(plan, plan)
        print(f"  {email:28} {plan_name:6} — {label}")
    print()
    print("Лимит проверок у «Базы» — 10 в день. «Плюс» и «Макс» без лимита.")

    with sqlite3.connect(DB) as final:
        users = final.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        checks = final.execute("SELECT COUNT(*) FROM checks").fetchone()[0]
    print(f"\nПосле очистки: аккаунтов {users}, проверок {checks}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
