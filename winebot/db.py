from __future__ import annotations

import json
from typing import Any

import aiosqlite


async def init_db(db_path: str) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS recent_posts (
                url TEXT PRIMARY KEY,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS drafts (
                chat_id INTEGER PRIMARY KEY,
                payload TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        await db.commit()


async def was_posted_recently(db_path: str, url: str, days: int = 90) -> bool:
    """Возвращает True, если вино публиковалось в последние `days` дней."""
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            "SELECT 1 FROM recent_posts WHERE url = ? "
            "AND created_at > datetime('now', ?) "
            "LIMIT 1",
            (url, f"-{days} days"),
        )
        row = await cursor.fetchone()
        return row is not None


async def mark_posted(db_path: str, url: str) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT OR REPLACE INTO recent_posts(url, created_at) VALUES(?, CURRENT_TIMESTAMP)",
            (url,),
        )
        await db.commit()


async def cleanup_old_posts(db_path: str, keep_days: int = 365) -> int:
    """Удаляет записи старше keep_days. Возвращает число удалённых строк."""
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            "DELETE FROM recent_posts WHERE created_at < datetime('now', ?)",
            (f"-{keep_days} days",),
        )
        await db.commit()
        return cursor.rowcount


async def get_post_count(db_path: str) -> int:
    """Сколько всего вин опубликовано в БД."""
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM recent_posts")
        row = await cursor.fetchone()
        return row[0] if row else 0


# ─── Черновики ────────────────────────────────────────────────────────────────

async def save_draft(db_path: str, chat_id: int, payload: dict[str, Any]) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            INSERT INTO drafts(chat_id, payload, updated_at)
            VALUES(?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(chat_id) DO UPDATE SET
                payload = excluded.payload,
                updated_at = CURRENT_TIMESTAMP
            """,
            (chat_id, json.dumps(payload, ensure_ascii=False)),
        )
        await db.commit()


async def load_draft(db_path: str, chat_id: int) -> dict[str, Any] | None:
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            "SELECT payload FROM drafts WHERE chat_id = ? LIMIT 1",
            (chat_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return json.loads(row[0])


async def delete_draft(db_path: str, chat_id: int) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute("DELETE FROM drafts WHERE chat_id = ?", (chat_id,))
        await db.commit()


# ─── Настройки (KV) ───────────────────────────────────────────────────────────

async def get_setting(db_path: str, key: str) -> str | None:
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            "SELECT value FROM settings WHERE key = ? LIMIT 1", (key,)
        )
        row = await cursor.fetchone()
        return row[0] if row else None


async def set_setting(db_path: str, key: str, value: str) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        await db.commit()
