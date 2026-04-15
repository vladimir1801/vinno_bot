from __future__ import annotations

import json
import logging
import random
from pathlib import Path

import httpx

log = logging.getLogger(__name__)

_FACTS_PATH = Path(__file__).resolve().parent.parent / "data" / "wine_facts.json"
_WIKIMEDIA_API = "https://commons.wikimedia.org/w/api.php"
_WIKIMEDIA_HEADERS = {"User-Agent": "VinnoBot/1.0 (wine-facts-image-fetcher)"}


def _load_facts() -> list[dict]:
    try:
        return json.loads(_FACTS_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        log.warning("Could not load wine_facts.json: %s", exc)
        return [{"text": "🍷 Вино — один из древнейших напитков человечества.", "image_query": "vineyard wine"}]


async def get_random_fact() -> dict:
    """
    Returns {'text': str, 'image_url': str | None}.
    Picks a random fact from wine_facts.json and fetches a matching
    photo from Wikimedia Commons.
    """
    facts = _load_facts()
    fact = random.choice(facts)
    query = fact.get("image_query", "vineyard wine grapes")
    image_url = await _fetch_wikimedia_image(query)
    return {"text": fact["text"], "image_url": image_url}


async def _fetch_wikimedia_image(query: str) -> str | None:
    """Search Wikimedia Commons and return a random matching image URL."""
    try:
        async with httpx.AsyncClient(headers=_WIKIMEDIA_HEADERS, timeout=12) as client:
            r = await client.get(
                _WIKIMEDIA_API,
                params={
                    "action": "query",
                    "format": "json",
                    "generator": "search",
                    "gsrnamespace": "6",          # File namespace
                    "gsrsearch": query,
                    "gsrlimit": "20",
                    "prop": "imageinfo",
                    "iiprop": "url|mime|size",
                    "iiurlwidth": "1200",
                },
            )
            r.raise_for_status()
            data = r.json()
            pages = list(data.get("query", {}).get("pages", {}).values())

            candidates: list[str] = []
            for page in pages:
                info_list = page.get("imageinfo", [])
                if not info_list:
                    continue
                info = info_list[0]
                mime = info.get("mime", "")
                # Only JPEG / PNG, skip SVG / tiff
                if mime not in ("image/jpeg", "image/png"):
                    continue
                # Prefer thumb URL (resized), fall back to full URL
                url = info.get("thumburl") or info.get("url")
                if url:
                    candidates.append(url)

            return random.choice(candidates) if candidates else None
    except Exception as exc:
        log.warning("Wikimedia image fetch failed for %r: %s", query, exc)
        return None
