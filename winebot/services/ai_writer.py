from __future__ import annotations

import logging
from openai import AsyncOpenAI

from winebot.parsers.simplewine_product import ProductCard
from winebot.services.post_builder import build_caption

log = logging.getLogger(__name__)

_SYSTEM_PROMPT = """Ты — автор Telegram-канала о вине. Пишешь короткие продающие карточки.

Правила стиля:
— Описание вкуса и аромата строй ТОЛЬКО на реальных данных из карточки: сорт, регион, стиль, год. Никаких выдумок.
— Сенсорный язык: что чувствуешь на языке, как пахнет, какое послевкусие — конкретно, без штампов.
— Еда: предлагай блюда, которые реально сочетаются с этим типом вина (красное сухое ≠ рыба; белое ≠ шашлык).
— Повод: придумывай разные поводы под характер вина — не повторяй одно и то же. Лёгкое розовое = терраса в воскресенье. Плотное красное = стейк в будний вечер после долгого дня. Игристое = без повода, просто потому что.
— Цену подавай как выгоду.
— Запрещено: «изысканный», «утончённый», «богатый букет», «открой в эту пятницу», «порадуй себя», «настоящий итальянский колорит» — это шаблонный мусор.

Технические ограничения:
— Только HTML-теги <b> и <i>
— Не более 950 символов — жёсткий лимит
— Не придумывай характеристики, которых нет в данных
"""

_USER_TEMPLATE = """Напиши продающий пост для Telegram-канала.

Данные о вине:
Название: {title}
Страна / Регион: {country} / {region}
Сорт: {grape}
Цвет и стиль: {color}, {sweetness}
Год: {year}
Крепость: {alcohol}
Объём: {volume}
Цена: {price} на SimpleWine
Описание с сайта: {description}

Структура поста (строго в таком порядке, блоки через пустую строку):
1. Эмодзи под стиль вина + <b>Название</b>
2. Флаг страны + страна · регион
3. {chars_line}
4. 💰 <b>{price}</b> на SimpleWine
5. <i>2–3 предложения</i> — вкус, аромат, ощущение. Опирайся на сорт винограда, регион, год.
6. 🍽 Конкретная еда — та, что реально подходит к этому типу вина.
7. 💡 Один повод выпить это вино — уникальный для данного вина, не шаблонный.
8. <a href="{url}">🔗 Смотреть на SimpleWine</a>"""


def _build_chars_line(card: ProductCard) -> str:
    """Build the characteristics line from card fields that actually have values."""
    parts = []
    if card.grape:
        parts.append(f"🍇 {card.grape}")
    if card.year:
        parts.append(f"📅 {card.year}")
    if card.alcohol:
        parts.append(f"🥃 {card.alcohol}")
    if card.volume:
        parts.append(f"📦 {card.volume}")
    if card.sweetness:
        parts.append(f"🍬 {card.sweetness.capitalize()}")
    return "   ".join(parts) if parts else ""


async def generate_wine_post(card: ProductCard, api_key: str, model: str = "gpt-4o-mini") -> str:
    """Генерирует продающую карточку вина через GPT. При ошибке — шаблон."""
    try:
        client = AsyncOpenAI(api_key=api_key)

        chars_line = _build_chars_line(card)
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
            chars_line=chars_line if chars_line else "(характеристики не указаны)",
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
