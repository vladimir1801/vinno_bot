from __future__ import annotations

import hashlib
import html
import json
import re
from typing import Any

from openai import AsyncOpenAI
from pydantic import BaseModel, Field


class WineCard(BaseModel):
    canonical_name: str = Field(..., description="Canonical wine name")
    type: str | None = Field(None, description="still, sparkling, etc.")
    color: str | None = Field(None, description="red, white, rose, orange")
    sugar: str | None = Field(None, description="dry, semi-dry, semi-sweet, sweet")
    country: str | None = None
    region: str | None = None
    grape: str | None = None
    volume_ml: int | None = None
    abv: float | None = Field(None, description="Alcohol percentage, e.g. 12.5")
    description: str = Field(..., description="4-6 sentences in Russian")


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        raise ValueError("No JSON object found in model output")
    return json.loads(match.group(0))


def fingerprint_from(canonical_name: str, volume_ml: int | None) -> str:
    base = canonical_name.strip().lower().replace("ё", "е")
    base = re.sub(r"\s+", " ", base)
    base += f"|{volume_ml or ''}"
    return hashlib.sha1(base.encode("utf-8")).hexdigest()


def _normalize_badge(value: str | None) -> str | None:
    if not value:
        return None
    return value.strip()


def build_caption_html(card: WineCard, offers: list[dict[str, Any]]) -> str:
    prices = [int(o["price_rub"]) for o in offers if o.get("price_rub") is not None]
    avg_price = int(sum(prices) / len(prices)) if prices else None

    badges: list[str] = []
    for value in (
        _normalize_badge(card.color),
        _normalize_badge(card.sugar),
        _normalize_badge(card.type) if card.type and card.type.lower() != "still" else None,
    ):
        if value:
            badges.append(html.escape(value))

    if card.volume_ml:
        badges.append(f"{card.volume_ml} мл" if card.volume_ml < 1000 else f"{card.volume_ml / 1000:g} л")
    if card.abv is not None:
        badges.append(f"{card.abv:g}%")

    meta = [part for part in (card.country, card.region, card.grape) if part]
    meta_line = " / ".join(html.escape(part) for part in meta)

    lines: list[str] = [f"🍷 <b>Вино дня:</b> {html.escape(card.canonical_name)}"]

    if badges:
        lines.append(" • ".join(badges))
    if meta_line:
        lines.append(meta_line)

    lines.append("")
    lines.append(html.escape(card.description.strip()))
    lines.append("")
    lines.append("<b>Где купить:</b>")

    for offer in offers:
        store = html.escape(str(offer["store"]))
        url = html.escape(str(offer["url"]), quote=True)
        price = f"{int(offer['price_rub'])} ₽" if offer.get("price_rub") is not None else "цена не указана"
        lines.append(f"• {store}: <a href=\"{url}\">{html.escape(price)}</a>")

    if avg_price is not None:
        lines.extend(["", f"<b>Средняя цена:</b> ~{avg_price} ₽"])

    lines.extend(["", "⚠️ Цены и наличие зависят от региона и текущих акций."])
    return "\n".join(lines)


async def make_card(client: AsyncOpenAI, model: str, raw_candidates: list[dict[str, Any]]) -> WineCard:
    prompt_text = (
        "Ты делаешь карточку вина для Telegram-канала на русском языке.\n"
        "На входе сырые карточки из магазинов.\n\n"
        "Задачи:\n"
        "1) Определи, относятся ли записи к одному и тому же вину.\n"
        "2) Сформируй одно canonical_name.\n"
        "3) Извлеки только те характеристики, которые реально видны в данных. Ничего не выдумывай.\n"
        "4) Напиши описание на русском: 4-6 предложений, дружелюбно, полезно, чуть живо, без кринжа.\n\n"
        "Верни ТОЛЬКО JSON-объект такого вида:\n"
        "{\n"
        '  "canonical_name": string,\n'
        '  "type": string|null,\n'
        '  "color": string|null,\n'
        '  "sugar": string|null,\n'
        '  "country": string|null,\n'
        '  "region": string|null,\n'
        '  "grape": string|null,\n'
        '  "volume_ml": integer|null,\n'
        '  "abv": number|null,\n'
        '  "description": string\n'
        "}\n"
    )
    payload = json.dumps(raw_candidates, ensure_ascii=False)

    response = await client.responses.create(
        model=model,
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt_text},
                    {"type": "input_text", "text": payload[:12000]},
                ],
            }
        ],
        store=False,
    )

    data = _extract_json(response.output_text)
    return WineCard.model_validate(data)
