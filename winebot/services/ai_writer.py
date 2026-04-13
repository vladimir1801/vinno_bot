from __future__ import annotations

import logging
from openai import AsyncOpenAI

from winebot.parsers.simplewine_product import ProductCard
from winebot.services.post_builder import build_caption

log = logging.getLogger(__name__)

_SYSTEM_PROMPT = """Ты — автор Telegram-канала о вине с 50 000 подписчиков. Твои посты не просто информируют — они заставляют людей тянуться за телефоном и заказывать вино прямо сейчас.

Твой стиль:
— Пишешь как человек, который только что открыл бутылку и не может не поделиться
— Создаёшь сцену: вечер пятницы, стейк на сковороде, первый глоток
— Используешь сенсорный язык: как пахнет, как ощущается на языке, какое послевкусие
— Называешь конкретную еду, с которой это вино будет лучшим вечером в жизни
— Даёшь читателю повод: «возьми на день рождения», «открой в эту пятницу», «подари себе»
— Цену подаёшь как выгоду, а не просто факт
— Никогда не пишешь «изысканный», «утончённый», «богатый букет» — это мусор
— Заканчиваешь так, чтобы человек нажал на ссылку

Технические ограничения:
— Только HTML-теги <b> и <i>
— Не более 950 символов — это жёсткий лимит
— Не придумывай данные, которых нет в описании
"""

_USER_TEMPLATE = """Напиши продающий пост для Telegram-канала про это вино.

Данные:
Название: {title}
Страна / Регион: {country}, {region}
Сорт: {grape}
Цвет / стиль: {color}, {sweetness}
Год: {year}
Крепость: {alcohol}
Объём: {volume}
Цена: {price} на SimpleWine
Описание с сайта: {description}
Ссылка: {url}

Структура поста:
1. Эмодзи + <b>Название</b> — без лишних слов
2. Флаг + страна · регион (одна строка)
3. 🍇 Сорт   📅 Год   🥃 Алкоголь   📦 Объём   🍬 Стиль — только те поля, что есть
4. 💰 <b>Цена</b> на SimpleWine
5. <i>2–3 предложения живого описания</i> — запах, вкус, ощущение. Никаких штампов. Пиши как будто держишь бокал в руке
6. Конкретная еда, с которой это вино — идеал. Начни с 🍽
7. Повод или момент — когда и зачем его брать. 1 предложение, начни с 💡
8. <a href="{url}">🔗 Смотреть на SimpleWine</a>

Разделяй блоки пустой строкой."""


async def generate_wine_post(card: ProductCard, api_key: str, model: str = "gpt-4o-mini") -> str:
    """Генерирует продающую карточку вина через GPT. При ошибке — шаблон."""
    try:
        client = AsyncOpenAI(api_key=api_key)

        user_msg = _USER_TEMPLATE.format(
            title=card.title or "—",
            country=card.country or "—",
            region=card.region or "—",
            grape=card.grape or "—",
            color=card.color or "—",
            sweetness=card.sweetness or "—",
            year=card.year or "—",
            alcohol=card.alcohol or "—",
            volume=card.volume or "—",
            price=card.price or "—",
            description=card.description or "описания нет",
            url=card.url,
        )

        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.92,
            max_tokens=620,
        )

        text = (response.choices[0].message.content or "").strip()

        if len(text) < 80:
            raise ValueError(f"Слишком короткий ответ от GPT: {repr(text)}")

        # Жёсткий обрез если GPT всё же вышел за лимит
        if len(text) > 1020:
            text = text[:1017].rsplit("\n", 1)[0] + "…"

        log.info("AI-карточка сгенерирована (%d символов)", len(text))
        return text

    except Exception as exc:
        log.warning("Ошибка AI-редактора (%s), использую шаблон: %s", type(exc).__name__, exc)
        return build_caption(card)
