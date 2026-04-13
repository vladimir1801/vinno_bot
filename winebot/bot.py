from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from openai import AsyncOpenAI

from winebot.config import load_config
from winebot.db import DB
from winebot.pipeline import find_and_prepare_draft
from winebot.scheduler import setup_scheduler


logging.basicConfig(level=logging.INFO)

cfg = load_config()
db = DB(cfg.sqlite_path)
client = AsyncOpenAI(api_key=cfg.openai_api_key)
dp = Dispatcher()


def kb_preview() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Утвердить", callback_data="approve"),
                InlineKeyboardButton(text="🔁 Новая генерация", callback_data="regen"),
                InlineKeyboardButton(text="✍️ Изменить", callback_data="edit"),
            ]
        ]
    )


class EditStates(StatesGroup):
    waiting_text = State()


async def generate_preview(bot: Bot, chat_id: int) -> None:
    prepared = await find_and_prepare_draft(
        db,
        client,
        cfg.openai_model,
        days_cooldown=cfg.days_cooldown,
        max_candidates=cfg.max_candidates,
        debug=cfg.debug,
    )

    if not prepared:
        await bot.send_message(
            chat_id,
            "Не нашла подходящего кандидата. Возможно, магазины не отдали данные или всё недавно уже публиковалось. Попробуй ещё раз: /post",
        )
        return

    msg = await bot.send_photo(
        chat_id=chat_id,
        photo=prepared["image_url"],
        caption=prepared["caption_html"],
        parse_mode=ParseMode.HTML,
        reply_markup=kb_preview(),
    )

    draft_id = await db.create_draft(
        fingerprint=prepared["fingerprint"],
        canonical_name=prepared["canonical_name"],
        image_url=prepared["image_url"],
        caption_html=prepared["caption_html"],
        preview_chat_id=chat_id,
        preview_message_id=msg.message_id,
    )

    for offer in prepared["offers"]:
        await db.add_offer(
            draft_id=draft_id,
            store=offer["store"],
            price_rub=offer.get("price_rub"),
            url=offer["url"],
        )


@dp.message(Command("start"))
async def cmd_start(message: Message) -> None:
    if message.from_user and message.from_user.id == cfg.admin_user_id:
        await message.answer("Бот запущен. Для превью используй /post")


@dp.message(Command("post"))
async def cmd_post(message: Message) -> None:
    if not message.from_user or message.from_user.id != cfg.admin_user_id:
        return
    await generate_preview(message.bot, message.chat.id)


@dp.callback_query(F.data.in_({"approve", "regen", "edit"}))
async def on_action(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.from_user or callback.from_user.id != cfg.admin_user_id:
        await callback.answer("Эти кнопки не для тебя.", show_alert=True)
        return

    if not callback.message:
        await callback.answer("Сообщение не найдено.", show_alert=True)
        return

    draft = await db.get_draft_by_preview(callback.message.chat.id, callback.message.message_id)
    if not draft:
        await callback.answer("Черновик не найден.", show_alert=True)
        return

    if callback.data == "approve":
        sent = await callback.bot.send_photo(
            chat_id=cfg.channel_id,
            photo=draft["image_url"],
            caption=draft["caption_html"],
            parse_mode=ParseMode.HTML,
        )
        await db.upsert_publication(
            draft["fingerprint"],
            draft["canonical_name"],
            sent.message_id,
        )
        await db.delete_draft(draft["id"])
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.answer("Отправлено в канал ✅")
        return

    if callback.data == "regen":
        await db.delete_draft(draft["id"])
        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.answer("Генерирую новое превью…")
        await generate_preview(callback.bot, callback.message.chat.id)
        return

    if callback.data == "edit":
        await state.set_state(EditStates.waiting_text)
        await state.update_data(
            draft_id=draft["id"],
            preview_chat_id=callback.message.chat.id,
            preview_msg_id=callback.message.message_id,
        )
        await callback.answer()
        await callback.message.reply(
            "Пришли новый текст подписи. HTML можно оставить, ссылки тоже."
        )


@dp.message(EditStates.waiting_text)
async def on_new_text(message: Message, state: FSMContext) -> None:
    if not message.from_user or message.from_user.id != cfg.admin_user_id:
        return

    data = await state.get_data()
    draft_id = int(data["draft_id"])
    preview_chat_id = int(data["preview_chat_id"])
    preview_msg_id = int(data["preview_msg_id"])

    new_caption = (message.text or "").strip()
    if not new_caption:
        await message.answer("Пустой текст не подойдёт. Пришли нормальную подпись.")
        return

    await db.update_draft_caption(draft_id, new_caption)
    try:
        await message.bot.edit_message_caption(
            chat_id=preview_chat_id,
            message_id=preview_msg_id,
            caption=new_caption,
            parse_mode=ParseMode.HTML,
            reply_markup=kb_preview(),
        )
        await message.answer("Готово. Превью обновила ✅")
    except Exception:
        await message.answer("Не смогла обновить превью. Проще сделать /post заново.")
    finally:
        await state.clear()


async def main() -> None:
    await db.init()
    bot = Bot(token=cfg.bot_token)
    setup_scheduler(
        bot=bot,
        tz=cfg.tz,
        hour=cfg.post_hour,
        minute=cfg.post_minute,
        job_coro=generate_preview,
        job_args=[bot, cfg.admin_user_id],
    )
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
