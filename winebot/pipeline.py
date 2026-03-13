import random
from datetime import datetime, timezone
from winebot.db import DB
from winebot.llm import make_card, fingerprint_from, build_caption_html
from winebot.scrapers.lenta import LentaScraper
from winebot.scrapers.simplewine import SimpleWineScraper

def _days_since(iso: str) -> int:
    dt = datetime.fromisoformat(iso)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - dt).days

async def find_and_prepare_draft(db: DB, client, model: str, *, days_cooldown: int, max_candidates: int, debug: bool=False):
    scrapers = [LentaScraper(), SimpleWineScraper()]

    # candidate URLs
    candidate_pairs = []
    for sc in scrapers:
        urls = await sc.get_candidate_urls()
        random.shuffle(urls)
        candidate_pairs += [(sc, u) for u in urls[: max_candidates]]

    random.shuffle(candidate_pairs)

    # try candidates
    attempts = 0
    for sc, url in candidate_pairs[:max_candidates]:
        attempts += 1
        offer = await sc.parse_offer(url)
        if not offer or not offer.title or not offer.image_url:
            continue

        # gather a small bundle of raw candidates from multiple stores (best effort)
        raw_bundle = [{
            "store": offer.store,
            "url": offer.url,
            "title": offer.title,
            "price_rub": offer.price_rub,
            "image_url": offer.image_url,
            "raw_text": offer.raw_text,
        }]

        # naive: add 1-2 more offers from other scrapers to help the model unify
        for sc2 in scrapers:
            if sc2.store == offer.store:
                continue
            urls2 = await sc2.get_candidate_urls()
            random.shuffle(urls2)
            for u2 in urls2[:30]:
                o2 = await sc2.parse_offer(u2)
                if not o2 or not o2.title:
                    continue
                # loose match by prefix
                if o2.title.lower().strip()[:18] == offer.title.lower().strip()[:18]:
                    raw_bundle.append({
                        "store": o2.store,
                        "url": o2.url,
                        "title": o2.title,
                        "price_rub": o2.price_rub,
                        "image_url": o2.image_url,
                        "raw_text": o2.raw_text,
                    })
                    break

        # AI normalize + generate
        card = await make_card(client, model, raw_bundle)

        fp = fingerprint_from(card.canonical_name, card.volume_ml)

        last = await db.get_last_posted_at(fp)
        if last and _days_since(last) < days_cooldown:
            if debug:
                print(f"[skip] {card.canonical_name} - posted {last}")
            continue

        # offers for caption: use the URLs we actually have (from bundle), keep store+price+url
        offers = []
        for r in raw_bundle:
            offers.append({"store": r["store"], "price_rub": r.get("price_rub"), "url": r["url"]})

        caption_html = build_caption_html(card, offers)
        image_url = next((r["image_url"] for r in raw_bundle if r.get("image_url")), offer.image_url)

        if debug:
            print(f"[picked] {card.canonical_name} attempts={attempts}")

        return {
            "fingerprint": fp,
            "canonical_name": card.canonical_name,
            "image_url": image_url,
            "caption_html": caption_html,
            "offers": offers,
        }

    return None
