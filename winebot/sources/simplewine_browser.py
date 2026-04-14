"""
URL collection for SimpleWine via XML sitemap.

SimpleWine is a React SPA -- catalog HTML has no product links.
The sitemap is generated server-side and contains all product URLs.
We discover the sitemap URL from /robots.txt first, then try known fallbacks.
"""
from __future__ import annotations

import logging
import random
import re
import xml.etree.ElementTree as ET
from urllib.parse import urlparse

import httpx

log = logging.getLogger(__name__)

_BASE = "https://simplewine.ru"
_ROBOTS_URL = "https://simplewine.ru/robots.txt"

_SITEMAP_FALLBACKS = [
    "https://simplewine.ru/sitemap.xml",
    "https://simplewine.ru/sitemap_index.xml",
    "https://simplewine.ru/sitemap-index.xml",
    "https://simplewine.ru/sitemaps/sitemap.xml",
    "https://simplewine.ru/sitemap/sitemap.xml",
    "https://simplewine.ru/sitemap/catalog.xml",
    "https://simplewine.ru/catalog/sitemap.xml",
]

_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

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
}


class SimpleWineBrowser:
    store = "SimpleWine"

    async def get_candidate_urls(self, limit: int = 10) -> list[str]:
        try:
            urls = await self._collect_from_sitemap(limit * 5)
        except Exception as exc:
            log.error("Sitemap collection failed: %s", exc)
            urls = []

        if not urls:
            log.warning("No product URLs found in sitemap")
            return []

        random.shuffle(urls)
        result = urls[:limit]
        log.info("Total candidates: %d (returning %d)", len(urls), len(result))
        return result

    async def _collect_from_sitemap(self, pool_size: int) -> list[str]:
        async with httpx.AsyncClient(
            headers=_HEADERS,
            timeout=30,
            follow_redirects=True,
        ) as client:
            sitemap_roots = await self._discover_sitemaps(client)
            product_urls: list[str] = []

            for sitemap_url in sitemap_roots:
                if len(product_urls) >= pool_size:
                    break
                try:
                    batch = await self._fetch_sitemap_tree(client, sitemap_url, pool_size)
                    product_urls.extend(batch)
                    if batch:
                        log.info(
                            "Got %d product URLs from %s",
                            len(batch),
                            sitemap_url,
                        )
                except Exception as exc:
                    log.warning("Error processing sitemap %s: %s", sitemap_url, exc)

            return product_urls

    async def _discover_sitemaps(self, client: httpx.AsyncClient) -> list[str]:
        found: list[str] = []
        try:
            r = await client.get(_ROBOTS_URL)
            if r.status_code == 200:
                for line in r.text.splitlines():
                    line = line.strip()
                    if line.lower().startswith("sitemap:"):
                        url = line.split(":", 1)[1].strip()
                        if url.startswith("http"):
                            log.info("robots.txt sitemap: %s", url)
                            found.append(url)
        except Exception as exc:
            log.warning("Could not fetch robots.txt: %s", exc)

        if found:
            return found

        log.info("No sitemap in robots.txt, trying fallback paths")
        for url in _SITEMAP_FALLBACKS:
            try:
                r = await client.get(url)
                if r.status_code == 200 and ("<sitemap" in r.text or "<url>" in r.text or "<urlset" in r.text):
                    log.info("Sitemap found at fallback: %s", url)
                    return [url]
            except Exception:
                pass

        log.error("No sitemap found in robots.txt or any fallback path")
        return []

    async def _fetch_sitemap_tree(
        self, client: httpx.AsyncClient, sitemap_url: str, pool_size: int
    ) -> list[str]:
        r = await client.get(sitemap_url)
        r.raise_for_status()
        xml_text = r.text

        if "<sitemapindex" in xml_text:
            child_urls = self._parse_sitemap_index(xml_text)
            log.info("Sitemap index %s has %d children", sitemap_url, len(child_urls))

            priority = [u for u in child_urls if _is_catalog_sitemap(u)]
            others = [u for u in child_urls if not _is_catalog_sitemap(u)]

            product_urls: list[str] = []
            for child_url in priority + others:
                if len(product_urls) >= pool_size:
                    break
                try:
                    batch = await self._fetch_sitemap_tree(client, child_url, pool_size)
                    product_urls.extend(batch)
                    if batch:
                        log.info("found %d wine URLs in %s", len(batch), child_url)
                except Exception as exc:
                    log.warning("Child sitemap error %s: %s", child_url, exc)
            return product_urls
        else:
            return self._parse_url_sitemap(xml_text, sitemap_url)

    @staticmethod
    def _parse_sitemap_index(xml_text: str) -> list[str]:
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            xml_text = re.sub(r"^<\?xml[^>]+\?>", "", xml_text.lstrip("\ufeff")).strip()
            root = ET.fromstring(xml_text)

        urls: list[str] = []
        for sitemap in root.findall("sm:sitemap", _NS):
            loc = sitemap.findtext("sm:loc", namespaces=_NS)
            if loc:
                urls.append(loc.strip())
        if not urls:
            for el in root.iter():
                tag = el.tag.split("}")[-1] if "}" in el.tag else el.tag
                if tag == "sitemap":
                    for child in el:
                        ctag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                        if ctag == "loc" and child.text:
                            urls.append(child.text.strip())
        return urls

    @staticmethod
    def _parse_url_sitemap(xml_text: str, source: str = "") -> list[str]:
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            xml_text = re.sub(r"^<\?xml[^>]+\?>", "", xml_text.lstrip("\ufeff")).strip()
            root = ET.fromstring(xml_text)

        all_locs: list[str] = []
        for el in root.iter():
            tag = el.tag.split("}")[-1] if "}" in el.tag else el.tag
            if tag == "loc" and el.text:
                all_locs.append(el.text.strip())

        # Log first 10 URLs so we can see the actual format
        if all_locs:
            log.info(
                "SAMPLE URLs from %s (total %d): %s",
                source or "sitemap",
                len(all_locs),
                " | ".join(all_locs[:10]),
            )

        urls = [u for u in all_locs if SimpleWineBrowser._looks_like_product_url(u)]
        log.info(
            "Filtered %d/%d URLs as wine products from %s",
            len(urls),
            len(all_locs),
            source or "sitemap",
        )
        return urls

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


def _is_catalog_sitemap(url: str) -> bool:
    lower = url.lower()
    return any(kw in lower for kw in ("catalog", "vino", "product", "goods", "tovar"))
