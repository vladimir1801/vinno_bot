from __future__ import annotations

import json
from pathlib import Path

from winebot.parsers.simplewine_product import ProductCard


_FACTS_PATH = Path(__file__).resolve().parent.parent / "data" / "grape_facts.json"


def _load_facts() -> dict[str, str]:
    try:
        return json.loads(_FACTS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def build_caption(card: ProductCard) -> str:
    facts = _load_facts()

    grape = (card.grape or "").strip()
    fact = facts.get(grape.lower())

    parts: list[str] = []
    parts.append(f"<b>{card.title}</b>")

    details: list[str] = []
    if card.price:
        details.append(f"Цена: {card.price}")
    if card.country:
        details.append(f"Страна: {card.country}")
    if card.region:
        details.append(f"Регион: {card.region}")
    if grape:
        details.append(f"Сорт: {grape}")
    if card.volume:
        details.append(f"Объём: {card.volume}")

    if details:
        parts.append("\n".join(details))

    if grape or card.country or card.region:
        descr_bits = []
        if grape:
            descr_bits.append(f"В основе этого вина — {grape}")
        if card.country:
            descr_bits.append(f"Происхождение — {card.country}")
        if card.region:
            descr_bits.append(f"регион {card.region}")
        sentence = ". ".join([bit.rstrip(".") for bit in descr_bits if bit]).strip()
        if sentence:
            parts.append(sentence + ".")

    if fact:
        parts.append(f"Интересный факт: {fact}")

    parts.append(f"<a href=\"{card.url}\">Смотреть на SimpleWine</a>")

    return "\n\n".join(parts)
