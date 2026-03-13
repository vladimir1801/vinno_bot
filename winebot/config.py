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

def load_config() -> Config:
    def _req(name: str) -> str:
        v = os.environ.get(name)
        if not v:
            raise RuntimeError(f"Missing required env var: {name}")
        return v

    return Config(
        bot_token=_req("BOT_TOKEN"),
        admin_user_id=int(_req("ADMIN_USER_ID")),
        channel_id=int(_req("CHANNEL_ID")),
        tz=os.getenv("TZ", "Europe/Moscow"),
        post_hour=int(os.getenv("POST_TIME_HOUR", "16")),
        post_minute=int(os.getenv("POST_TIME_MINUTE", "0")),
        openai_api_key=_req("OPENAI_API_KEY"),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-5.2"),
        days_cooldown=int(os.getenv("DAYS_COOLDOWN", "60")),
        max_candidates=int(os.getenv("MAX_CANDIDATES", "80")),
        debug=os.getenv("DEBUG", "0") == "1",
    )
