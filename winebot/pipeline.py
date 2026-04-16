from __future__ import annotations

import asyncio
import logging
import re

from winebot.config import Settings
from winebot.db import was_posted_recently
from winebot.parsers.simplewine_product import ProductCard, SimpleWineProductParser
from winebot.services.post_builder import build_caption
from winebot.services.price_comparator import (
    PriceResult,
    compare_prices,
    enrich_card,
    format_price_comparison,
)
from winebot.sources.simplewine_browser import SimpleWineBrowser

log = logging.getLogger(__name__)

# Telegram send_photo caption limit
_CAPTION_LIMIT = 1_024


def _price_ok(price: str | None, max_rub: int) -> bool:
    """Return True if price is within the configured limit (0 = no limit)."""
    if not max_rub or not price:
        return True
    m = re.search(r"(\d[\d\s\xa0]*)", price)
    if m:
        try:
            return int(re.sub(r"[\s\xa0]+", "", m.group(1))) <= max_rub
        except ValueError:
            pass
    return True


async def find_and_prepare_draft(settings: Settings) -> dict | None:
    browser = SimpleWineBrowser()
    parser = SimpleWineProductParser()

    urls = await browser.get_candidate_urls(limit=settings.max_candidates)
    log.info("[pipeline] собрано %d кандидатов", len(urls))

    if not urls:
        return None

    for index, url in enumerate(urls, start=1):
        # Allow asyncio.CancelledError to propagate (triggered by /cancel command)
        await asyncio.sleep(0)

        log.info("[pipeline] парсинг %d/%d: %s", index, len(urls), url)

        if await was_posted_recently(settings.database_path, url, days=settings.history_days):
            log.info("[pipeline] пропущен (уже был): %s", url)
            continue

        card = await parser.parse(url)
        if not card:
            log.info("[pipeline] не удалось спарсить: %s", url)
            continue

        # Feature 4: fill missing fields from Winestyle
        card = await enrich_card(card)

        # Price filter
        if not _price_ok(card.price, settings.max_price_rub):
            log.info("[pipeline] пропущен (цена выше лимита %d ₽): %s", settings.max_price_rub, url)
            continue

        # Feature 3: price comparison
        price_results = await compare_prices(card)

        caption = await _make_caption(card, settings, price_results)
        payload = _prepare_payload(card, caption, price_results)
        log.info("[pipeline] готово: %s", payload["title"])
        return payload

    log.warning("[pipeline] нет подходящих кандидатов")
    return None


async def _make_caption(
    card: ProductCard,
    settings: Settings,
    price_results: list[PriceResult],
) -> str:
    """Build caption via GPT (if key set) or template, then append price comparison."""
    if settings.openai_api_key:
        from winebot.services.ai_writer import generate_wine_post
        caption = await generate_wine_post(card, settings.openai_api_key, settings.openai_model)
    else:
        caption = build_caption(card)

    # Append price comparison if we have results from more than one store
    if len(price_results) > 1:
        price_block = format_price_comparison(price_results)
        if price_block:
            separator = "\n\n"
            max_main = _CAPTION_LIMIT - len(separator) - len(price_block)
            if len(caption) > max_main:
                caption = caption[: max_main - 1].rstrip() + "…"
            caption += separator + price_block

    return caption


def _prepare_payload(
    card: ProductCard,
    caption: str,
    price_results: list[PriceResult],
) -> dict:
    return {
        "title": card.title,
        "url": card.url,
        "image_url": card.image_url,
        "price": card.price,
        "country": card.country,
        "grape": card.grape,
        "region": card.region,
        "volume": card.volume,
        "color": card.color,
        "sweetness": card.sweetness,
        "alcohol": card.alcohol,
        "year": card.year,
        "description": card.description,
        "store": card.store,
        "caption": caption,
        "price_results": [r.to_dict() for r in price_results],
    }
