from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(slots=True)
class Settings:
    bot_token: str
    admin_id: int
    channel_id: str
    debug: bool = False
    max_candidates: int = 10
    database_path: str = "winebot.db"
    tz: str = "Asia/Yekaterinburg"
    post_time: str = "10:00"
    auto_publish: bool = False
    history_days: int = 90
    openai_api_key: str = ""          # если задан — используем GPT для карточки
    openai_model: str = "gpt-4o-mini" # модель по умолчанию
    fact_post_time: str = "14:00"     # время ежедневного факта о вине
    max_price_rub: int = 5000         # 0 = без ограничения


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

    def _int(key: str, default: int, lo: int = 1, hi: int = 9999) -> int:
        try:
            return max(lo, min(hi, int(os.getenv(key, str(default)).strip())))
        except ValueError:
            return default

    return Settings(
        bot_token=bot_token,
        admin_id=admin_id,
        channel_id=channel_id,
        debug=os.getenv("DEBUG", "").strip().lower() in {"1", "true", "yes", "on"},
        max_candidates=_int("MAX_CANDIDATES", 10, 1, 20),
        database_path=os.getenv("DATABASE_PATH", "winebot.db").strip() or "winebot.db",
        tz=os.getenv("TZ", "Asia/Yekaterinburg").strip() or "Asia/Yekaterinburg",
        post_time=os.getenv("POST_TIME", "10:00").strip() or "10:00",
        auto_publish=os.getenv("AUTO_PUBLISH", "").strip().lower() in {"1", "true", "yes", "on"},
        history_days=_int("HISTORY_DAYS", 90, 7, 3650),
        openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini",
        fact_post_time=os.getenv("FACT_POST_TIME", "14:00").strip() or "14:00",
        max_price_rub=_int("MAX_PRICE_RUB", 5000, 0, 999_999),
    )
