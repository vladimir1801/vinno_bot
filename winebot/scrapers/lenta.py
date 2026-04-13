from __future__ import annotations

import json
import re
from typing import Any, Iterable

import httpx
from selectolax.parser import HTMLParser

from .base import RawOffer


UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}


def _clean_text(text: str, limit: int = 2000) -> str:
    return re.sub(r"\s+", " ", text).strip()[:limit]


def _int_price(value: Any) -> int | None:
    if value is None:
        return None
    raw = str(value).replace("\xa0", " ").replace(" ", "").replace(",", ".")
    match = re.search(r"\d+(?:\.\d+)?", raw)
    if not match:
        return None
    try:
        return int(float(match.group(0)))
    except ValueError:
        return None


def _extract_json_ld(html_text: str) -> Iterable[dict[str, Any] | list[Any]]:
    doc = HTMLParser(html_text)
    for node in doc.css('script[type="application/ld+json"]'):
        raw = (node.text() or "").strip()
        if not raw:
            continue
        try:
            yield json.loads(raw)
        except Exception:
            continue


class LentaScraper:
    store = "Лента"

    def __init__(self) -> None:
        self.client = httpx.AsyncClient(
            timeout=25,
            follow_redirects=True,
            headers=UA,
        )

    async def get_candidate_urls(self) -> list[str]:
        url = "https://lenta.com/catalog/vino-22541/"
        try:
            response = await self.client.get(url)
            response.raise_for_status()
        except Exception:
            return []

        doc = HTMLParser(response.text)
        urls: list[str] = []

        for node in doc.css("a[href]"):
            href = node.attributes.get("href", "")
            if "/product/" not in href:
                continue
            if href.startswith("/"):
                href = "https://lenta.com" + href
            urls.append(href.split("?")[0])

        seen: set[str] = set()
        unique_urls: list[str] = []
        for item in urls:
            if item in seen:
                continue
            seen.add(item)
            unique_urls.append(item)

        return unique_urls[:100]

    async def parse_offer(self, url: str) -> RawOffer | None:
        try:
            response = await self.client.get(url)
            response.raise_for_status()
        except Exception:
            return None

        title: str | None = None
        price: int | None = None
        image: str | None = None

        for block in _extract_json_ld(response.text):
            items: list[Any]
            if isinstance(block, dict) and isinstance(block.get("@graph"), list):
                items = block["@graph"]
            elif isinstance(block, list):
                items = block
            elif isinstance(block, dict):
                items = [block]
            else:
                items = []

            for item in items:
                if not isinstance(item, dict):
                    continue
                if item.get("@type") != "Product":
                    continue

                title = item.get("name") or title

                image_value = item.get("image")
                if isinstance(image_value, list) and image_value:
                    image = image_value[0] or image
                elif isinstance(image_value, str):
                    image = image_value

                offers = item.get("offers")
                if isinstance(offers, dict):
                    price = _int_price(offers.get("price")) or price

        doc = HTMLParser(response.text)
        if not title:
            h1 = doc.css_first("h1")
            if h1:
                title = h1.text().strip()

        if not image:
            og = doc.css_first('meta[property="og:image"]')
            if og:
                image = og.attributes.get("content")

        if price is None:
            text = doc.text()
            match = re.search(r"(\d[\d\s]{2,})\s*₽", text)
            if match:
                price = _int_price(match.group(1))

        raw_text = _clean_text(doc.text())
        return RawOffer(
            store=self.store,
            url=url,
            title=title,
            price_rub=price,
            image_url=image,
            raw_text=raw_text,
        )
