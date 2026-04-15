from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime

import httpx
import pytz
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from winebot.config import Settings, load_settings
from winebot.db import (
    cleanup_old_posts,
    delete_draft,
    get_post_count,
    get_setting,
    init_db,
    load_draft,
    mark_posted,
    save_draft,
    set_setting,
)
from winebot.pipeline import find_and_prepare_draft
from winebot.services.fact_service import get_random_fact

_DL_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://simplewine.ru/",
}


async def _download_image(url: str) -> bytes | None:
    """Download image bytes server-side so Telegram doesn't need to reach the source."""
    try:
        async with httpx.AsyncClient(
            headers=_DL_HEADERS, timeout=15, follow_redirects=True
        ) as client:
            r = await client.get(url)
            ct = r.headers.get("content-type", "")
            if r.status_code == 200 and ct.startswith("image/"):
                return r.content
    except Exception as exc:
        log.debug("Image download failed for %s: %s", url, exc)
    return None


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger(__name__)

settings: Settings = load_settings()
bot = Bot(
    token=settings.bot_token,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
dp = Dispatcher()
scheduler = AsyncIOScheduler(timezone=settings.tz)


# --- Глобальный обработчик ошибок -------------------------------------------

@dp.errors()
async def global_error_handler(event, exception: Exception) -> bool:
    log.exception("Необработанная ошибка: %s", exception)
    try:
        await bot.send_message(
            settings.admin_id,
            "\u274c <b>Ошибка бота:</b>\n"
            f"<code>{type(exception).__name__}: {str(exception)[:300]}</code>",
        )
    except Exception:
        pass
    return True   # помечаем как обработанную, бот не падает


# --- Клавиатуры ---------------------------------------------------------------

def _preview_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Опубликовать", callback_data="publish"),
                InlineKeyboardButton(text="Другое вино", callback_data="next"),
            ]
        ]
    )


# --- Отправка превью ----------------------------------------------------------

async def _send_preview(chat_id: int, payload: dict) -> None:
    await save_draft(settings.database_path, chat_id, payload)
    caption = payload["caption"]

    if payload.get("image_url"):
        photo = await _prepare_photo(payload["image_url"])
        if photo is not None:
            try:
                await bot.send_photo(
                    chat_id=chat_id,
                    photo=photo,
                    caption=caption,
                    reply_markup=_preview_keyboard(),
                )
                return
            except Exception as exc:
                log.warning("Не удалось отправить фото превью: %s", exc)

    await bot.send_message(
        chat_id=chat_id,
        text=caption,
        reply_markup=_preview_keyboard(),
        disable_web_page_preview=False,
    )


async def _publish_to_channel(payload: dict) -> None:
    caption = payload["caption"]
    if payload.get("image_url"):
        photo = await _prepare_photo(payload["image_url"])
        if photo is not None:
            try:
                await bot.send_photo(
                    chat_id=settings.channel_id,
                    photo=photo,
                    caption=caption,
                )
                return
            except Exception as exc:
                log.warning("Не удалось отправить фото в канал: %s", exc)
    await bot.send_message(
        chat_id=settings.channel_id,
        text=caption,
        disable_web_page_preview=False,
    )


async def _prepare_photo(url: str):
    """Download image bytes and wrap as BufferedInputFile; fall back to URL string."""
    data = await _download_image(url)
    if data:
        return BufferedInputFile(data, filename="wine.jpg")
    return url  # Telegram will try to fetch directly as fallback


async def generate_preview(chat_id: int) -> None:
    payload = await find_and_prepare_draft(settings)
    if not payload:
        await bot.send_message(
            chat_id,
            "Не нашёл подходящего кандидата. Попробуй через пару минут (/post).",
        )
        return
    await _send_preview(chat_id, payload)


# --- Планировщик --------------------------------------------------------------

async def scheduled_daily_post() -> None:
    log.info("Запуск ежедневного поста")
    try:
        payload = await find_and_prepare_draft(settings)
        if not payload:
            await bot.send_message(
                settings.admin_id,
                "Ежедневный пост: не нашёл кандидата. Используй /post вручную.",
            )
            return

        if settings.auto_publish:
            await _publish_to_channel(payload)
            await mark_posted(settings.database_path, payload["url"])
            await bot.send_message(
                settings.admin_id,
                "Автопост опубликован: <b>{}</b>".format(payload["title"]),
            )
            log.info("Автопост опубликован: %s", payload["title"])
        else:
            await bot.send_message(
                settings.admin_id,
                "Время публикации! Вот сегодняшний кандидат:",
            )
            await _send_preview(settings.admin_id, payload)
            log.info("Превью отправлено администратору: %s", payload["title"])

        deleted = await cleanup_old_posts(settings.database_path, keep_days=365)
        if deleted:
            log.info("Очищено старых записей: %d", deleted)

    except Exception as exc:
        log.exception("Ошибка в ежедневном посте: %s", exc)
        await bot.send_message(settings.admin_id, "Ошибка ежедневного поста: {}".format(exc))


def _reschedule(post_time: str) -> None:
    hour, minute = map(int, post_time.split(":"))
    if scheduler.get_job("daily_post"):
        scheduler.remove_job("daily_post")
    scheduler.add_job(
        scheduled_daily_post,
        trigger=CronTrigger(hour=hour, minute=minute, timezone=settings.tz),
        id="daily_post",
        name="Ежедневный пост",
        replace_existing=True,
    )
    log.info("Планировщик: новое время %s (%s)", post_time, settings.tz)


async def scheduled_fact_post() -> None:
    """Post a daily wine/vineyard fact with a Wikimedia photo."""
    log.info("Публикация факта о вине")
    try:
        fact = await get_random_fact()
        text = f"🍇 <b>Факт о вине</b>\n\n{fact['text']}"

        if fact.get("image_url"):
            photo = await _prepare_photo(fact["image_url"])
            try:
                await bot.send_photo(
                    chat_id=settings.channel_id,
                    photo=photo,
                    caption=text,
                )
                return
            except Exception as exc:
                log.warning("Не удалось отправить фото факта: %s", exc)

        await bot.send_message(
            settings.channel_id,
            text,
            disable_web_page_preview=True,
        )
    except Exception as exc:
        log.exception("Ошибка публикации факта: %s", exc)
        await bot.send_message(settings.admin_id, f"Ошибка публикации факта: {exc}")


def _reschedule_fact(fact_time: str) -> None:
    hour, minute = map(int, fact_time.split(":"))
    if scheduler.get_job("daily_fact"):
        scheduler.remove_job("daily_fact")
    scheduler.add_job(
        scheduled_fact_post,
        trigger=CronTrigger(hour=hour, minute=minute, timezone=settings.tz),
        id="daily_fact",
        name="Факт о вине",
        replace_existing=True,
    )
    log.info("Факт о вине: новое время %s (%s)", fact_time, settings.tz)


# --- Команды бота -------------------------------------------------------------

@dp.message(Command("start"))
async def cmd_start(message: Message) -> None:
    if message.from_user and message.from_user.id != settings.admin_id:
        await message.answer("Этот бот работает только для администратора.")
        return
    await message.answer(
        "🍷 <b>Vinno Bot запущен!</b>\n\n"
        "Каждый день в назначенное время я найду интересное вино "
        "и пришлю тебе карточку для одобрения.\n\n"
        "Используй /help для списка команд."
    )


@dp.message(Command("help"))
async def cmd_help(message: Message) -> None:
    if message.from_user and message.from_user.id != settings.admin_id:
        return
    job = scheduler.get_job("daily_post")
    next_run = job.next_run_time.strftime("%d.%m %H:%M") if job and job.next_run_time else "—"
    fact_job = scheduler.get_job("daily_fact")
    next_fact = fact_job.next_run_time.strftime("%d.%m %H:%M") if fact_job and fact_job.next_run_time else "—"
    await message.answer(
        "📋 <b>Команды:</b>\n\n"
        "/post — найти вино и показать превью\n"
        "/fact — опубликовать факт о вине прямо сейчас\n"
        "/schedule HH:MM — изменить время ежедневного поста\n"
        "/schedule_fact HH:MM — изменить время факта о вине\n"
        "/status — статистика и расписание\n"
        "/help — это сообщение\n\n"
        "Следующий автопост: <b>{}</b>\n"
        "Следующий факт: <b>{}</b>".format(next_run, next_fact)
    )


@dp.message(Command("post"))
async def cmd_post(message: Message) -> None:
    if message.from_user and message.from_user.id != settings.admin_id:
        await message.answer("Эта команда доступна только администратору.")
        return
    await message.answer("Ищу вино...")
    await generate_preview(message.chat.id)


@dp.message(Command("schedule"))
async def cmd_schedule(message: Message) -> None:
    if message.from_user and message.from_user.id != settings.admin_id:
        return

    text = (message.text or "").strip()
    m = re.search(r"\b(\d{1,2}):(\d{2})\b", text)
    if not m:
        await message.answer(
            "Укажи время в формате HH:MM\n"
            "Пример: /schedule 09:30"
        )
        return

    hour, minute = int(m.group(1)), int(m.group(2))
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        await message.answer("Некорректное время. Используй формат HH:MM (00:00–23:59).")
        return

    post_time = "{:02d}:{:02d}".format(hour, minute)
    await set_setting(settings.database_path, "post_time", post_time)
    _reschedule(post_time)

    tz = pytz.timezone(settings.tz)
    today = datetime.now(tz).strftime("%d.%m.%Y")
    await message.answer(
        "Время ежедневного поста установлено: <b>{}</b> ({})\n"
        "Сегодня: {}".format(post_time, settings.tz, today)
    )


@dp.message(Command("status"))
async def cmd_status(message: Message) -> None:
    if message.from_user and message.from_user.id != settings.admin_id:
        return

    job = scheduler.get_job("daily_post")
    next_run = "—"
    if job and job.next_run_time:
        next_run = job.next_run_time.strftime("%d.%m.%Y %H:%M")

    fact_job = scheduler.get_job("daily_fact")
    next_fact = "—"
    if fact_job and fact_job.next_run_time:
        next_fact = fact_job.next_run_time.strftime("%d.%m.%Y %H:%M")

    post_time = await get_setting(settings.database_path, "post_time") or settings.post_time
    fact_time = await get_setting(settings.database_path, "fact_post_time") or settings.fact_post_time
    count = await get_post_count(settings.database_path)
    mode = "автопубликация" if settings.auto_publish else "одобрение администратора"

    await message.answer(
        "📊 <b>Статус Vinno Bot</b>\n\n"
        "Время поста: <b>{}</b> ({})\n"
        "Следующий запуск: <b>{}</b>\n"
        "Факт о вине: <b>{}</b> · следующий: <b>{}</b>\n"
        "Режим: {}\n"
        "Опубликовано вин: <b>{}</b>\n"
        "Не повторять: <b>{} дней</b>".format(
            post_time, settings.tz, next_run,
            fact_time, next_fact,
            mode, count, settings.history_days
        )
    )


@dp.message(Command("fact"))
async def cmd_fact(message: Message) -> None:
    if message.from_user and message.from_user.id != settings.admin_id:
        return
    await message.answer("Публикую факт о вине в канал...")
    await scheduled_fact_post()


@dp.message(Command("schedule_fact"))
async def cmd_schedule_fact(message: Message) -> None:
    if message.from_user and message.from_user.id != settings.admin_id:
        return

    text = (message.text or "").strip()
    m = re.search(r"\b(\d{1,2}):(\d{2})\b", text)
    if not m:
        await message.answer("Укажи время в формате HH:MM\nПример: /schedule_fact 14:00")
        return

    hour, minute = int(m.group(1)), int(m.group(2))
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        await message.answer("Некорректное время. Используй формат HH:MM (00:00–23:59).")
        return

    fact_time = "{:02d}:{:02d}".format(hour, minute)
    await set_setting(settings.database_path, "fact_post_time", fact_time)
    _reschedule_fact(fact_time)
    await message.answer(
        "Время факта о вине установлено: <b>{}</b> ({})".format(fact_time, settings.tz)
    )


# --- Callback-кнопки ----------------------------------------------------------

@dp.callback_query(F.data == "next")
async def cb_next(callback: CallbackQuery) -> None:
    if callback.from_user.id != settings.admin_id:
        await callback.answer("Недоступно", show_alert=True)
        return
    await callback.answer("Ищу другой вариант...")
    await generate_preview(callback.message.chat.id)


@dp.callback_query(F.data == "publish")
async def cb_publish(callback: CallbackQuery) -> None:
    if callback.from_user.id != settings.admin_id:
        await callback.answer("Недоступно", show_alert=True)
        return

    payload = await load_draft(settings.database_path, callback.message.chat.id)
    if not payload:
        await callback.answer("Черновик не найден", show_alert=True)
        return

    await _publish_to_channel(payload)
    await mark_posted(settings.database_path, payload["url"])
    await delete_draft(settings.database_path, callback.message.chat.id)
    await callback.answer("Опубликовано")
    await bot.send_message(
        callback.message.chat.id,
        "Готово! Пост ушёл в канал: <b>{}</b>".format(payload["title"])
    )


# --- Запуск -------------------------------------------------------------------

async def main() -> None:
    await init_db(settings.database_path)

    saved_time = await get_setting(settings.database_path, "post_time")
    post_time = saved_time or settings.post_time
    _reschedule(post_time)

    saved_fact_time = await get_setting(settings.database_path, "fact_post_time")
    fact_time = saved_fact_time or settings.fact_post_time
    _reschedule_fact(fact_time)

    scheduler.start()
    log.info("Планировщик запущен: пост %s, факт %s (%s)", post_time, fact_time, settings.tz)

    await bot.delete_webhook(drop_pending_updates=True)
    await bot.send_message(
        settings.admin_id,
        f"✅ Бот запущен.\n"
        f"Автопост в <b>{post_time}</b> · Факт о вине в <b>{fact_time}</b> ({settings.tz})\n"
        f"AI-редактор: {'включён' if settings.openai_api_key else 'выключен (нет OPENAI_API_KEY)'}",
    )
    try:
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown(wait=False)


if __name__ == "__main__":
    asyncio.run(main())
