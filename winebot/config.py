from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class Config:
    bot_token: str
    admin_user_id: int
    channel_id: int
    tz: str
    post_hour: int
    post_minute: int
    openai_api_key: str
    openai_model: str
    days_cooldown: int
    max_candidates: int
    debug: bool
    sqlite_path: str


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


def load_config() -> Config:
    return Config(
        bot_token=_require_env("BOT_TOKEN"),
        admin_user_id=int(_require_env("ADMIN_USER_ID")),
        channel_id=int(_require_env("CHANNEL_ID")),
        tz=os.getenv("TZ", "Europe/Moscow"),
        post_hour=int(os.getenv("POST_TIME_HOUR", "16")),
        post_minute=int(os.getenv("POST_TIME_MINUTE", "0")),
        openai_api_key=_require_env("OPENAI_API_KEY"),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-5.2"),
        days_cooldown=int(os.getenv("DAYS_COOLDOWN", "60")),
        max_candidates=int(os.getenv("MAX_CANDIDATES", "40")),
        debug=os.getenv("DEBUG", "0").strip() == "1",
        sqlite_path=os.getenv("SQLITE_PATH", "winebot.sqlite3"),
    )
