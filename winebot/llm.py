import json, re, hashlib
from typing import Any
from pydantic import BaseModel, Field
from openai import AsyncOpenAI

class WineCard(BaseModel):
    canonical_name: str = Field(..., description="Canonical wine name, e.g. 'Fanagoria F-Style Cabernet Sauvignon'")
    type: str | None = Field(None, description="Still wine / sparkling / etc.")
    color: str | None = Field(None, description="red/white/rose/orange")
    sugar: str | None = Field(None, description="dry/semi-dry/semi-sweet/sweet")
    country: str | None = None
    region: str | None = None
    grape: str | None = None
    volume_ml: int | None = None
    abv: float | None = Field(None, description="Alcohol percent, e.g. 12.5")
    description: str = Field(..., description="4-6 sentences, friendly, no cringe, optionally a bit of humor")

def _extract_json(text: str) -> dict[str, Any]:
    # Try to find the first JSON object in the text (robust against extra words)
    m = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not m:
        raise ValueError("No JSON found in model output")
    raw = m.group(0)
    return json.loads(raw)

def fingerprint_from(canonical_name: str, volume_ml: int | None) -> str:
    base = canonical_name.strip().lower().replace("ё","е")
    base = re.sub(r"\s+", " ", base)
    base += f"|{volume_ml or ''}"
    return hashlib.sha1(base.encode("utf-8")).hexdigest()

def build_caption_html(card: WineCard, offers: list[dict]) -> str:
    # average price
    prices = [o["price_rub"] for o in offers if o.get("price_rub")]
    avg = int(sum(prices)/len(prices)) if prices else None

    badges = []
    if card.color: badges.append(card.color)
    if card.sugar: badges.append(card.sugar)
    if card.type and card.type.lower() != "still": badges.append(card.type)
    if card.volume_ml: badges.append(f"{card.volume_ml/1000:.2g} л" if card.volume_ml >= 1000 else f"{card.volume_ml} мл")
    if card.abv: badges.append(f"{card.abv:g}%")

    line1 = f"🍷 <b>Вино дня:</b> {card.canonical_name}"
    line2 = f"<i>{' • '.join(badges)}</i>" if badges else ""

    meta = []
    if card.country: meta.append(card.country)
    if card.region: meta.append(card.region)
    if card.grape: meta.append(card.grape)
    meta_line = f"<i>{' / '.join(meta)}</i>" if meta else ""

    lines = [line1]
    if line2: lines.append(line2)
    if meta_line: lines.append(meta_line)
    lines.append("")
    lines.append(card.description.strip())
    lines.append("")
    lines.append("<b>Где купить:</b>")
    for o in offers:
        p = f"{o['price_rub']} ₽" if o.get("price_rub") else "цена не найдена"
        lines.append(f"• <b>{o['store']}</b>: <a href=\"{o['url']}\">{p}</a>")
    if avg:
        lines.append("")
        lines.append(f"<b>Средняя цена:</b> ~{avg} ₽")
    lines.append("")
    lines.append("⚠️ Цены/наличие зависят от региона и акций.")
    return "\n".join(lines)

async def make_card(client: AsyncOpenAI, model: str, raw_candidates: list[dict]) -> WineCard:
    """Use the model to normalize wine identity + characteristics and generate description.

    raw_candidates: list of dicts with keys like:
      store, url, title, price_rub, image_url, raw_text
    """
    prompt_text = (
        "You are a wine-card generator for a Telegram channel in Russia.\n"
        "You receive raw product data from Russian wine stores (names/fields may differ).\n"
        "Task:\n"
        "1) Decide whether the candidates refer to the same wine. If they do, unify into ONE canonical wine.\n"
        "2) Produce a canonical_name (use the most recognizable name; keep brand/producer if present).\n"
        "3) Extract characteristics if present in the data (best-effort; do NOT invent).\n"
        "4) Write a 4–6 sentence description in Russian: friendly, useful, slightly witty, not cheesy.\n\n"
        "Return ONLY a single JSON object with this schema (no extra text):\n"
        "{\n"
        "  \"canonical_name\": string,\n"
        "  \"type\": string|null,\n"
        "  \"color\": string|null,\n"
        "  \"sugar\": string|null,\n"
        "  \"country\": string|null,\n"
        "  \"region\": string|null,\n"
        "  \"grape\": string|null,\n"
        "  \"volume_ml\": integer|null,\n"
        "  \"abv\": number|null,\n"
        "  \"description\": string\n"
        "}\n\n"
        "Raw candidates JSON:\n"
    )

    payload = json.dumps(raw_candidates, ensure_ascii=False)
    resp = await client.responses.create(
        model=model,
        input=[{
            "role": "user",
            "content": [
                {"type": "input_text", "text": prompt_text},
                {"type": "input_text", "text": payload[:12000]},
            ],
        }],
        store=False,
    )
    data = _extract_json(resp.output_text)
    return WineCard.model_validate(data)
