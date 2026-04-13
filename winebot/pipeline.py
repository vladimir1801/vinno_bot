from __future__ import annotations

from winebot.config import Settings
from winebot.db import was_posted_recently
from winebot.parsers.simplewine_product import ProductCard, SimpleWineProductParser
from winebot.services.post_builder import build_caption
from winebot.sources.simplewine_browser import SimpleWineBrowser


async def find_and_prepare_draft(settings: Settings) -> dict | None:
    browser = SimpleWineBrowser()
    parser = SimpleWineProductParser()

    urls = await browser.get_candidate_urls(limit=settings.max_candidates)
    print(f"[pipeline] собрано {len(urls)} кандидатов")

    if not urls:
        return None

    for index, url in enumerate(urls, start=1):
        print(f"[pipeline] парсинг {index}/{len(urls)}: {url}")

        if await was_posted_recently(settings.database_path, url, days=settings.history_days):
            print(f"[pipeline] пропущен (уже был): {url}")
            continue

        card = await parser.parse(url)
        if not card:
            print(f"[pipeline] не удалось спарсить: {url}")
            continue

        caption = await _make_caption(card, settings)
        payload = _prepare_payload(card, caption)
        print(f"[pipeline] готово: {payload['title']}")
        return payload

    print("[pipeline] нет подходящих кандидатов")
    return None


async def _make_caption(card: ProductCard, settings: Settings) -> str:
    """Генерирует текст карточки: через GPT если ключ задан, иначе шаблон."""
    if settings.openai_api_key:
        from winebot.services.ai_writer import generate_wine_post
        return await generate_wine_post(card, settings.openai_api_key, settings.openai_model)
    return build_caption(card)


def _prepare_payload(card: ProductCard, caption: str) -> dict:
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
    }
