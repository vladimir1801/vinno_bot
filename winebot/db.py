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
        await db.commit()


async def was_posted_recently(db_path: str, url: str) -> bool:
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            "SELECT 1 FROM recent_posts WHERE url = ? LIMIT 1",
            (url,),
        )
        row = await cursor.fetchone()
        return row is not None


async def mark_posted(db_path: str, url: str) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT OR REPLACE INTO recent_posts(url) VALUES(?)",
            (url,),
        )
        await db.commit()


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
