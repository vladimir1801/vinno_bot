from __future__ import annotations

import logging
import random
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

# Разные страницы каталога для разнообразия
_CATALOG_PAGES = [
    "https://simplewine.ru/catalog/vino/",
    "https://simplewine.ru/catalog/vino/?page=2",
    "https://simplewine.ru/catalog/vino/?page=3",
    "https://simplewine.ru/catalog/vino/filter/color-krasnoe/",
    "https://simplewine.ru/catalog/vino/filter/color-beloe/",
    "https://simplewine.ru/catalog/vino/filter/country-italiya/",
    "https://simplewine.ru/catalog/vino/filter/country-frantsiya/",
    "https://simplewine.ru/catalog/vino/filter/country-ispaniya/",
    "https://simplewine.ru/catalog/vino/filter/country-argentina/",
]


class SimpleWineBrowser:
    store = "SimpleWine"

    async def get_candidate_urls(self, limit: int = 10) -> list[str]:
        urls: list[str] = []
        pages = _CATALOG_PAGES.copy()
        random.shuffle(pages)

        async with httpx.AsyncClient(
            headers=_HEADERS,
            timeout=30,
            follow_redirects=True,
        ) as client:
            for catalog_url in pages:
                if len(urls) >= limit:
                    break
                try:
                    resp = await client.get(catalog_url)
                    if resp.status_code != 200:
                        log.warning("HTTP %d for %s", resp.status_code, catalog_url)
                        continue

                    soup = BeautifulSoup(resp.text, "html.parser")
                    found = 0
                    for tag in soup.find_all("a", href=True):
                        href = tag["href"]
                        if not href.startswith("/"):
                            continue
                        full = "https://simplewine.ru" + href
                        if self._looks_like_product_url(full) and full not in urls:
                            urls.append(full)
                            found += 1
                            if len(urls) >= limit:
                                break

                    log.info("Page %s: found %d products", catalog_url, found)

                except Exception as exc:
                    log.warning("Error fetching %s: %s", catalog_url, exc)

        random.shuffle(urls)
        log.info("Total candidates: %d", len(urls))
        return urls[:limit]

    @staticmethod
    def _looks_like_product_url(url: str) -> bool:
        if not url.startswith("https://simplewine.ru/catalog/vino/"):
            return False
        parsed = urlparse(url)
        path = parsed.path.rstrip("/")
        bad_segments = ("/filter/", "/sort/", "/page/", "/compare/", "/cart/")
        if any(seg in path for seg in bad_segments):
            return False
        if parsed.query:
            return False
        parts = [p for p in path.split("/") if p]
        if len(parts) != 3:
            return False
        slug = parts[2]
        if len(slug) < 16:
            return False
        return True
