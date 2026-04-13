from __future__ import annotations

import random
import re
from datetime import datetime, timezone
from typing import Any

from winebot.db import DB
from winebot.llm import build_caption_html, fingerprint_from, make_card
from winebot.scrapers.lenta import LentaScraper
from winebot.scrapers.simplewine import SimpleWineScraper


def _days_since(iso_value: str) -> int:
    dt = datetime.fromisoformat(iso_value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - dt).days


def _title_tokens(text: str) -> set[str]:
    clean = re.sub(r"[^a-zA-Zа-яА-ЯёЁ0-9]+", " ", text.lower().replace("ё", "е"))
    return {token for token in clean.split() if len(token) >= 3}


def _looks_similar(title_a: str, title_b: str) -> bool:
    a = _title_tokens(title_a)
    b = _title_tokens(title_b)
    if not a or not b:
        return False
    overlap = len(a & b)
    return overlap >= max(2, min(len(a), len(b)) // 2)


async def find_and_prepare_draft(
    db: DB,
    client: Any,
    model: str,
    *,
    days_cooldown: int,
    max_candidates: int,
    debug: bool = False,
) -> dict[str, Any] | None:
    scrapers = [LentaScraper(), SimpleWineScraper()]
    candidate_pairs: list[tuple[Any, str]] = []

    for scraper in scrapers:
        urls = await scraper.get_candidate_urls()
        random.shuffle(urls)
        candidate_pairs.extend((scraper, url) for url in urls[:max_candidates])

    random.shuffle(candidate_pairs)

    attempts = 0
    for scraper, url in candidate_pairs[:max_candidates]:
        attempts += 1
        offer = await scraper.parse_offer(url)
        if not offer or not offer.title or not offer.image_url:
            continue

        raw_bundle: list[dict[str, Any]] = [
            {
                "store": offer.store,
                "url": offer.url,
                "title": offer.title,
                "price_rub": offer.price_rub,
                "image_url": offer.image_url,
                "raw_text": offer.raw_text,
            }
        ]

        for other_scraper in scrapers:
            if other_scraper.store == offer.store:
                continue

            other_urls = await other_scraper.get_candidate_urls()
            random.shuffle(other_urls)

            for other_url in other_urls[:30]:
                other_offer = await other_scraper.parse_offer(other_url)
                if not other_offer or not other_offer.title:
                    continue
                if not _looks_similar(offer.title, other_offer.title):
                    continue

                raw_bundle.append(
                    {
                        "store": other_offer.store,
                        "url": other_offer.url,
                        "title": other_offer.title,
                        "price_rub": other_offer.price_rub,
                        "image_url": other_offer.image_url,
                        "raw_text": other_offer.raw_text,
                    }
                )
                break

        card = await make_card(client, model, raw_bundle)
        fingerprint = fingerprint_from(card.canonical_name, card.volume_ml)

        last_posted_at = await db.get_last_posted_at(fingerprint)
        if last_posted_at and _days_since(last_posted_at) < days_cooldown:
            if debug:
                print(f"[skip] {card.canonical_name} - posted recently: {last_posted_at}")
            continue

        offers = [
            {
                "store": item["store"],
                "price_rub": item.get("price_rub"),
                "url": item["url"],
            }
            for item in raw_bundle
        ]
        image_url = next(
            (item["image_url"] for item in raw_bundle if item.get("image_url")),
            offer.image_url,
        )
        caption_html = build_caption_html(card, offers)

        if debug:
            print(f"[picked] {card.canonical_name}; attempts={attempts}")

        return {
            "fingerprint": fingerprint,
            "canonical_name": card.canonical_name,
            "image_url": image_url,
            "caption_html": caption_html,
            "offers": offers,
        }

    return None
