from __future__ import annotations

import json
import re
from pathlib import Path

from winebot.parsers.simplewine_product import ProductCard


_FACTS_PATH = Path(__file__).resolve().parent.parent / "data" / "grape_facts.json"

# Эмодзи-флаги для основных винных стран
_COUNTRY_FLAGS: dict[str, str] = {
    "франция": "🇫🇷", "france": "🇫🇷",
    "италия": "🇮🇹", "italy": "🇮🇹",
    "испания": "🇪🇸", "spain": "🇪🇸",
    "португалия": "🇵🇹", "portugal": "🇵🇹",
    "германия": "🇩🇪", "germany": "🇩🇪",
    "австрия": "🇦🇹", "austria": "🇦🇹",
    "аргентина": "🇦🇷", "argentina": "🇦🇷",
    "чили": "🇨🇱", "chile": "🇨🇱",
    "австралия": "🇦🇺", "australia": "🇦🇺",
    "сша": "🇺🇸", "usa": "🇺🇸", "соединённые штаты": "🇺🇸", "united states": "🇺🇸",
    "новая зеландия": "🇳🇿", "new zealand": "🇳🇿",
    "юар": "🇿🇦", "южная африка": "🇿🇦", "south africa": "🇿🇦",
    "грузия": "🇬🇪", "georgia": "🇬🇪",
    "россия": "🇷🇺", "russia": "🇷🇺",
    "венгрия": "🇭🇺", "hungary": "🇭🇺",
    "греция": "🇬🇷", "greece": "🇬🇷",
    "румыния": "🇷🇴", "romania": "🇷🇴",
    "молдавия": "🇲🇩", "moldova": "🇲🇩",
    "армения": "🇦🇲", "armenia": "🇦🇲",
    "израиль": "🇮🇱", "israel": "🇮🇱",
    "ливан": "🇱🇧", "lebanon": "🇱🇧",
}

# Эмодзи для цвета вина
_COLOR_EMOJI: dict[str, str] = {
    "красное": "🍷",
    "белое": "🥂",
    "розовое": "🌸",
    "оранжевое": "🟠",
    "игристое": "🍾",
    "шампанское": "🍾",
}


def _load_facts() -> dict[str, str]:
    try:
        return json.loads(_FACTS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _country_flag(country: str | None) -> str:
    if not country:
        return "🌍"
    return _COUNTRY_FLAGS.get(country.lower().strip(), "🌍")


def _wine_emoji(color: str | None) -> str:
    if not color:
        return "🍷"
    return _COLOR_EMOJI.get(color.lower().strip(), "🍷")


def _find_grape_fact(facts: dict[str, str], grape: str | None) -> str | None:
    """Ищет факт по сорту. Поддерживает несколько сортов через запятую."""
    if not grape:
        return None
    # Пробуем каждый сорт по отдельности (если их несколько)
    parts = [g.strip() for g in re.split(r"[,/;]", grape)]
    for part in parts:
        fact = facts.get(part.lower())
        if fact:
            return fact
    return None


def build_caption(card: ProductCard) -> str:
    facts = _load_facts()

    wine_emoji = _wine_emoji(card.color)
    flag = _country_flag(card.country)

    parts: list[str] = []

    # ── Заголовок ──────────────────────────────────────────────────────────────
    parts.append(f"{wine_emoji} <b>{card.title}</b>")

    # ── Происхождение ──────────────────────────────────────────────────────────
    origin_bits = []
    if card.country:
        origin_bits.append(f"{flag} {card.country}")
    if card.region:
        origin_bits.append(card.region)
    if origin_bits:
        parts.append(" · ".join(origin_bits))

    # ── Характеристики (одна строка) ───────────────────────────────────────────
    chars = []
    if card.grape:
        chars.append(f"🍇 {card.grape}")
    if card.year:
        chars.append(f"📅 {card.year}")
    if card.alcohol:
        chars.append(f"🥃 {card.alcohol}")
    if card.volume:
        chars.append(f"📦 {card.volume}")
    if card.sweetness:
        chars.append(f"🍬 {card.sweetness.capitalize()}")
    if chars:
        parts.append("   ".join(chars))

    # ── Цена ───────────────────────────────────────────────────────────────────
    if card.price:
        parts.append(f"💰 <b>{card.price}</b> на SimpleWine")

    # ── Описание / тейстинг-ноты ───────────────────────────────────────────────
    if card.description:
        parts.append(f"📝 <i>{card.description}</i>")

    # ── Интересный факт о сорте ────────────────────────────────────────────────
    fact = _find_grape_fact(facts, card.grape)
    if fact:
        parts.append(f"🌿 {fact}")

    # ── Ссылка ─────────────────────────────────────────────────────────────────
    parts.append(f'<a href="{card.url}">🔗 Смотреть на SimpleWine</a>')

    return "\n\n".join(parts)
