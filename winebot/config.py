from __future__ import annotations

import os
from dataclasses import dataclass


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(slots=True)
class Settings:
    bot_token: str
    admin_id: int
    channel_id: str
    debug: bool = False
    max_candidates: int = 8
    database_path: str = "winebot.db"
    tz: str = "Asia/Yekaterinburg"


def load_settings() -> Settings:
    bot_token = os.getenv("BOT_TOKEN", "").strip()
    admin_raw = os.getenv("ADMIN_ID", "").strip()
    channel_id = os.getenv("CHANNEL_ID", "").strip()

    if not bot_token:
        raise RuntimeError("BOT_TOKEN is not set")
    if not admin_raw:
        raise RuntimeError("ADMIN_ID is not set")
    if not channel_id:
        raise RuntimeError("CHANNEL_ID is not set")

    try:
        admin_id = int(admin_raw)
    except ValueError as exc:
        raise RuntimeError("ADMIN_ID must be integer") from exc

    max_candidates_raw = os.getenv("MAX_CANDIDATES", "8").strip()
    try:
        max_candidates = max(1, min(20, int(max_candidates_raw)))
    except ValueError:
        max_candidates = 8

    return Settings(
        bot_token=bot_token,
        admin_id=admin_id,
        channel_id=channel_id,
        debug=_as_bool(os.getenv("DEBUG"), False),
        max_candidates=max_candidates,
        database_path=os.getenv("DATABASE_PATH", "winebot.db").strip() or "winebot.db",
        tz=os.getenv("TZ", "Asia/Yekaterinburg").strip() or "Asia/Yekaterinburg",
    )
