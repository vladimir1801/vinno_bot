import aiosqlite
from datetime import datetime, timezone

DDL = '''
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS publications (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  fingerprint TEXT NOT NULL UNIQUE,
  canonical_name TEXT NOT NULL,
  posted_at TEXT NOT NULL,
  channel_message_id INTEGER
);

CREATE TABLE IF NOT EXISTS drafts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  fingerprint TEXT NOT NULL,
  canonical_name TEXT NOT NULL,
  image_url TEXT NOT NULL,
  caption_html TEXT NOT NULL,
  created_at TEXT NOT NULL,
  preview_chat_id INTEGER NOT NULL,
  preview_message_id INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS draft_offers (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  draft_id INTEGER NOT NULL,
  store TEXT NOT NULL,
  price_rub INTEGER,
  url TEXT NOT NULL,
  FOREIGN KEY(draft_id) REFERENCES drafts(id) ON DELETE CASCADE
);
'''

class DB:
    def __init__(self, path: str = "winebot.sqlite3"):
        self.path = path

    async def init(self):
        async with aiosqlite.connect(self.path) as db:
            await db.executescript(DDL)
            await db.commit()

    async def get_last_posted_at(self, fingerprint: str) -> str | None:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            row = await db.execute_fetchone(
                "SELECT posted_at FROM publications WHERE fingerprint=?",
                (fingerprint,),
            )
            return row["posted_at"] if row else None

    async def upsert_publication(self, fingerprint: str, canonical_name: str, channel_message_id: int | None):
        now = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                '''
                INSERT INTO publications (fingerprint, canonical_name, posted_at, channel_message_id)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(fingerprint) DO UPDATE SET
                  canonical_name=excluded.canonical_name,
                  posted_at=excluded.posted_at,
                  channel_message_id=excluded.channel_message_id
                ''',
                (fingerprint, canonical_name, now, channel_message_id),
            )
            await db.commit()

    async def create_draft(self, fingerprint: str, canonical_name: str, image_url: str, caption_html: str,
                           preview_chat_id: int, preview_message_id: int) -> int:
        now = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                '''
                INSERT INTO drafts (fingerprint, canonical_name, image_url, caption_html, created_at,
                                    preview_chat_id, preview_message_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ''',
                (fingerprint, canonical_name, image_url, caption_html, now, preview_chat_id, preview_message_id),
            )
            await db.commit()
            return cur.lastrowid

    async def add_offer(self, draft_id: int, store: str, price_rub: int | None, url: str):
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT INTO draft_offers (draft_id, store, price_rub, url) VALUES (?, ?, ?, ?)",
                (draft_id, store, price_rub, url),
            )
            await db.commit()

    async def get_draft_by_preview(self, chat_id: int, message_id: int) -> dict | None:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            row = await db.execute_fetchone(
                "SELECT * FROM drafts WHERE preview_chat_id=? AND preview_message_id=?",
                (chat_id, message_id),
            )
            return dict(row) if row else None

    async def get_offers(self, draft_id: int) -> list[dict]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            rows = await db.execute_fetchall(
                "SELECT store, price_rub, url FROM draft_offers WHERE draft_id=? ORDER BY id",
                (draft_id,),
            )
            return [dict(r) for r in rows]

    async def update_draft_caption(self, draft_id: int, caption_html: str):
        async with aiosqlite.connect(self.path) as db:
            await db.execute("UPDATE drafts SET caption_html=? WHERE id=?", (caption_html, draft_id))
            await db.commit()

    async def delete_draft(self, draft_id: int):
        async with aiosqlite.connect(self.path) as db:
            await db.execute("DELETE FROM drafts WHERE id=?", (draft_id,))
            await db.commit()
