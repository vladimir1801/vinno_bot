# Wine Day Bot (AI + moderation)

Telegram bot that:
- at 16:00 (or by /post) finds a candidate wine from Russian-market store catalogs,
- checks the publications DB (anti-duplicate with a 60-day cooldown),
- uses OpenAI Responses API to normalize/extract characteristics and generate a nice "wine of the day" card,
- sends you a preview with buttons: Approve / Regenerate / Edit,
- after approval posts to your channel and stores publication info in SQLite.

## What you need to fill
Create a `.env` from `.env.example` and fill:
- BOT_TOKEN
- ADMIN_USER_ID
- CHANNEL_ID
- OPENAI_API_KEY
- (optional) OPENAI_MODEL

## Local run
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
python -m winebot.bot
```

## Railway deploy (simple)
1) Push this repo to GitHub.
2) Create a Railway project from the repo.
3) Add the same env vars as in `.env.example` to Railway Variables.
4) Start command: `python -m winebot.bot`

## Notes
- The bot does NOT try to read channel history (Telegram API limitation). It tracks what it posted in SQLite.
- Scrapers are best-effort; the AI step is designed to clean up inconsistencies in naming/fields.
