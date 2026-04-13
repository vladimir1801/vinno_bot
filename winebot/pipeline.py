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
    threshold = max(2, min(len(a), len(b)) // 2)
    return overlap >= threshold


async def _collect_source_urls(scraper: Any, max_candidates: int) -> list[str]:
    urls = await scraper.get_candidate_urls()
    if not urls:
        print(f"[source:{scraper.store}] 0 candidate urls")
        return []

    random.shuffle(urls)
    limited = urls[: max(max_candidates, 20)]
    print(
        f"[source:{scraper.store}] collected {len(urls)} urls, "
        f"using {len(limited)} for this run"
    )
    return limited


async def find_and_prepare_draft(
    db: DB,
    client: Any,
    model: str,
    *,
    days_cooldown: int,
    max_candidates: int,
    debug: bool = False,
) -> dict[str, Any] | None:
    scrapers = [SimpleWineScraper(), LentaScraper()]

    source_urls: dict[str, list[str]] = {}
    active_scrapers: list[Any] = []

    for scraper in scrapers:
        urls = await _collect_source_urls(scraper, max_candidates)
        source_urls[scraper.store] = urls
        if urls:
            active_scrapers.append(scraper)

    if not active_scrapers:
        print("[pipeline] no active sources returned any candidate urls")
        return None

    candidate_pairs: list[tuple[Any, str]] = []
    for scraper in active_scrapers:
        candidate_pairs.extend((scraper, url) for url in source_urls[scraper.store][:max_candidates])

    random.shuffle(candidate_pairs)
    print(f"[pipeline] total candidate pairs for parsing: {len(candidate_pairs)}")

    parse_failures = 0
    llm_failures = 0
    recent_skips = 0
    empty_image_skips = 0
    attempts = 0

    for scraper, url in candidate_pairs:
        attempts += 1
        print(f"[pipeline] attempt {attempts}/{len(candidate_pairs)} -> {scraper.store}: {url}")

        offer = await scraper.parse_offer(url)
        if not offer:
            parse_failures += 1
            print(f"[pipeline] parse failed: {scraper.store} {url}")
            continue

        if not offer.title:
            parse_failures += 1
            print(f"[pipeline] parsed without title: {scraper.store} {url}")
            continue

        if not offer.image_url:
            empty_image_skips += 1
            print(f"[pipeline] skip without image: {offer.title} ({scraper.store})")
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

        for other_scraper in active_scrapers:
            if other_scraper.store == offer.store:
                continue

            other_urls = source_urls.get(other_scraper.store, [])[:30]
            if not other_urls:
                continue

            for other_url in other_urls:
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
                print(
                    f"[pipeline] matched cross-store: '{offer.title}' <-> '{other_offer.title}'"
                )
                break

        try:
            card = await make_card(client, model, raw_bundle)
        except Exception as exc:
            llm_failures += 1
            print(f"[pipeline] LLM failed for {offer.title!r}: {exc}")
            continue

        fingerprint = fingerprint_from(card.canonical_name, card.volume_ml)
        last_posted_at = await db.get_last_posted_at(fingerprint)
        if last_posted_at and _days_since(last_posted_at) < days_cooldown:
            recent_skips += 1
            print(
                f"[pipeline] skip recent duplicate: {card.canonical_name} "
                f"(last posted {last_posted_at})"
            )
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

        print(
            f"[pipeline] picked candidate: {card.canonical_name}; "
            f"offers={len(offers)}; attempts={attempts}"
        )

        return {
            "fingerprint": fingerprint,
            "canonical_name": card.canonical_name,
            "image_url": image_url,
            "caption_html": caption_html,
            "offers": offers,
        }

    print(
        "[pipeline] no draft found. "
        f"attempts={attempts}, parse_failures={parse_failures}, "
        f"llm_failures={llm_failures}, recent_skips={recent_skips}, "
        f"empty_image_skips={empty_image_skips}"
    )
    return None
