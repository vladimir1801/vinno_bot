# Wine Day Bot

Telegram-бот, который:
- ищет карточки вина в каталогах магазинов,
- нормализует данные через OpenAI,
- присылает админу превью,
- публикует пост после ручного подтверждения,
- хранит антидубли и черновики в SQLite.

## Быстрый запуск

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
python -m winebot.bot
```

## Что заполнить в `.env`

- `BOT_TOKEN`
- `ADMIN_USER_ID`
- `CHANNEL_ID`
- `OPENAI_API_KEY`

Дополнительно:
- `OPENAI_MODEL` — по умолчанию `gpt-5.2`
- `TZ` — по умолчанию `Europe/Moscow`
- `POST_TIME_HOUR` / `POST_TIME_MINUTE`
- `DAYS_COOLDOWN`
- `MAX_CANDIDATES`
- `DEBUG`
- `SQLITE_PATH`

## Примечания

- Бот использует SQLite для черновиков и антидублей.
- Парсеры магазинов работают по принципу best effort: сайты могут менять верстку или включать защиту.
- Если магазины отдают 401/403, бот не сможет подобрать кандидата, пока не будут обновлены парсеры или источник данных.
