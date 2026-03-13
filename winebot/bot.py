import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

from openai import AsyncOpenAI

from winebot.config import load_config
from winebot.db import DB
from winebot.pipeline import find_and_prepare_draft
from winebot.scheduler import setup_scheduler

cfg = load_config()
db = DB()
client = AsyncOpenAI(api_key=cfg.openai_api_key)

dp = Dispatcher()

def kb_preview() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Утвердить", callback_data="approve"),
        InlineKeyboardButton(text="🔁 Новая генерация", callback_data="regen"),
        InlineKeyboardButton(text="✍️ Изменить", callback_data="edit"),
    ]])

class EditStates(StatesGroup):
    waiting_text = State()

async def generate_preview(bot: Bot, chat_id: int):
    prepared = await find_and_prepare_draft(
        db,
        client,
        cfg.openai_model,
        days_cooldown=cfg.days_cooldown,
        max_candidates=cfg.max_candidates,
        debug=cfg.debug,
    )
    if not prepared:
        await bot.send_message(chat_id, "Не нашла кандидата (картинки/данных нет или всё слишком свежее). Попробуй ещё раз: /post")
        return

    msg = await bot.send_photo(
        chat_id=chat_id,
        photo=prepared["image_url"],
        caption=prepared["caption_html"],
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=kb_preview()
    )

    draft_id = await db.create_draft(
        fingerprint=prepared["fingerprint"],
        canonical_name=prepared["canonical_name"],
        image_url=prepared["image_url"],
        caption_html=prepared["caption_html"],
        preview_chat_id=chat_id,
        preview_message_id=msg.message_id,
    )
    for o in prepared["offers"]:
        await db.add_offer(draft_id, o["store"], o.get("price_rub"), o["url"])

@dp.message(Command("post"))
async def cmd_post(m: Message):
    if m.from_user.id != cfg.admin_user_id:
        return
    await generate_preview(m.bot, m.chat.id)

@dp.callback_query(F.data.in_({"approve","regen","edit"}))
async def on_action(cq: CallbackQuery, state: FSMContext):
    if cq.from_user.id != cfg.admin_user_id:
        await cq.answer("Не для тебя кнопки 🙂", show_alert=True)
        return

    draft = await db.get_draft_by_preview(cq.message.chat.id, cq.message.message_id)
    if not draft:
        await cq.answer("Черновик не найден (уже удалён?).", show_alert=True)
        return

    if cq.data == "approve":
        sent = await cq.bot.send_photo(
            chat_id=cfg.channel_id,
            photo=draft["image_url"],
            caption=draft["caption_html"],
            parse_mode="HTML",
            disable_web_page_preview=True
        )
        await db.upsert_publication(draft["fingerprint"], draft["canonical_name"], sent.message_id)
        await db.delete_draft(draft["id"])
        await cq.message.edit_reply_markup(reply_markup=None)
        await cq.answer("Утверждено и отправлено в канал ✅")
        return

    if cq.data == "regen":
        await db.delete_draft(draft["id"])
        try:
            await cq.message.delete()
        except Exception:
            pass
        await cq.answer("Генерирую новое…")
        await generate_preview(cq.bot, cq.message.chat.id)
        return

    if cq.data == "edit":
        await state.set_state(EditStates.waiting_text)
        await state.update_data(
            draft_id=draft["id"],
            preview_chat_id=cq.message.chat.id,
            preview_msg_id=cq.message.message_id,
        )
        await cq.answer()
        await cq.message.reply("Ок. Пришли новый текст подписи (HTML можно, ссылки лучше оставь как есть).")

@dp.message(EditStates.waiting_text)
async def on_new_text(m: Message, state: FSMContext):
    if m.from_user.id != cfg.admin_user_id:
        return
    data = await state.get_data()
    draft_id = data["draft_id"]
    preview_chat_id = data["preview_chat_id"]
    preview_msg_id = data["preview_msg_id"]

    new_caption = (m.text or "").strip()
    if not new_caption:
        await m.answer("Пустой текст — не принимаю. Пришли нормальный текст или /post для нового.")
        return

    await db.update_draft_caption(draft_id, new_caption)

    try:
        await m.bot.edit_message_caption(
            chat_id=preview_chat_id,
            message_id=preview_msg_id,
            caption=new_caption,
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=kb_preview()
        )
        await m.answer("Готово. Вернула на согласование ✅")
    except Exception:
        await m.answer("Не смогла обновить превью (Telegram иногда ругается). Сделай /post заново.")
    await state.clear()

async def main():
    await db.init()
    bot = Bot(cfg.bot_token)

    # daily preview to admin at configured time
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
