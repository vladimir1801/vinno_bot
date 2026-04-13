from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, CallbackQuery
from aiogram.client.default import DefaultBotProperties

from winebot.config import load_settings
from winebot.db import delete_draft, init_db, load_draft, mark_posted, save_draft
from winebot.pipeline import find_and_prepare_draft


logging.basicConfig(level=logging.INFO)

settings = load_settings()
bot = Bot(
    token=settings.bot_token,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
dp = Dispatcher()


def _preview_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Опубликовать", callback_data="publish"),
                InlineKeyboardButton(text="Другое вино", callback_data="next"),
            ]
        ]
    )


async def _send_preview(chat_id: int, payload: dict) -> None:
    await save_draft(settings.database_path, chat_id, payload)
    caption = payload["caption"]

    if payload.get("image_url"):
        try:
            await bot.send_photo(
                chat_id=chat_id,
                photo=payload["image_url"],
                caption=caption,
                reply_markup=_preview_keyboard(),
            )
            return
        except Exception as exc:
            logging.warning("Preview photo send failed: %s", exc)

    await bot.send_message(
        chat_id=chat_id,
        text=caption,
        reply_markup=_preview_keyboard(),
        disable_web_page_preview=False,
    )


async def generate_preview(chat_id: int) -> None:
    payload = await find_and_prepare_draft(settings)
    if not payload:
        await bot.send_message(
            chat_id,
            "Не нашла подходящего кандидата. Попробуй ещё раз через пару минут.",
        )
        return

    await _send_preview(chat_id, payload)


@dp.message(Command("start"))
async def cmd_start(message: Message) -> None:
    if message.from_user and message.from_user.id != settings.admin_id:
        await message.answer("Этот бот работает только для администратора.")
        return
    await message.answer("Бот запущен. Для превью используй /post")


@dp.message(Command("post"))
async def cmd_post(message: Message) -> None:
    if message.from_user and message.from_user.id != settings.admin_id:
        await message.answer("Эта команда доступна только администратору.")
        return
    await generate_preview(message.chat.id)


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

    caption = payload["caption"]

    if payload.get("image_url"):
        try:
            await bot.send_photo(
                chat_id=settings.channel_id,
                photo=payload["image_url"],
                caption=caption,
            )
        except Exception as exc:
            logging.warning("Channel photo send failed: %s", exc)
            await bot.send_message(
                chat_id=settings.channel_id,
                text=caption,
                disable_web_page_preview=False,
            )
    else:
        await bot.send_message(
            chat_id=settings.channel_id,
            text=caption,
            disable_web_page_preview=False,
        )

    await mark_posted(settings.database_path, payload["url"])
    await delete_draft(settings.database_path, callback.message.chat.id)
    await callback.answer("Опубликовано")
    await bot.send_message(callback.message.chat.id, "Готово. Пост ушёл в канал.")


async def main() -> None:
    await init_db(settings.database_path)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
