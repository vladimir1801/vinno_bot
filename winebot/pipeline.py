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
    print(f"[pipeline] collected {len(urls)} SimpleWine candidate urls")

    if not urls:
        return None

    for index, url in enumerate(urls, start=1):
        print(f"[pipeline] parsing candidate {index}/{len(urls)}: {url}")

        if await was_posted_recently(settings.database_path, url):
            print(f"[pipeline] skipped recent url: {url}")
            continue

        card = await parser.parse(url)
        if not card:
            print(f"[pipeline] parse failed: {url}")
            continue

        payload = _prepare_payload(card)
        print(f"[pipeline] prepared draft: {payload['title']}")
        return payload

    print("[pipeline] no valid cards after filtering")
    return None


def _prepare_payload(card: ProductCard) -> dict:
    return {
        "title": card.title,
        "url": card.url,
        "image_url": card.image_url,
        "price": card.price,
        "country": card.country,
        "grape": card.grape,
        "region": card.region,
        "volume": card.volume,
        "store": card.store,
        "caption": build_caption(card),
    }
