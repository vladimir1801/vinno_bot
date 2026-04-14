"""
URL collection for SimpleWine via XML sitemap.

SimpleWine is a React SPA -- catalog HTML has no product links.
The sitemap is generated server-side and contains all product URLs.
"""
from __future__ import annotations

import logging
import random
import re
import xml.etree.ElementTree as ET
from urllib.parse import urlparse

import httpx

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
}

_SITEMAP_ROOT = "https://simplewine.ru/sitemap.xml"
_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


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
            log.info("Fetching sitemap index: %s", _SITEMAP_ROOT)
            resp = await client.get(_SITEMAP_ROOT)
            resp.raise_for_status()
            root_xml = resp.text

            product_urls: list[str] = []

            if "<sitemapindex" in root_xml:
                child_urls = self._parse_sitemap_index(root_xml)
                log.info("Sitemap index has %d child sitemaps", len(child_urls))

                priority = [u for u in child_urls if _is_catalog_sitemap(u)]
                others = [u for u in child_urls if not _is_catalog_sitemap(u)]
                ordered = priority + others

                for sitemap_url in ordered:
                    if len(product_urls) >= pool_size:
                        break
                    try:
                        log.info("Fetching child sitemap: %s", sitemap_url)
                        r = await client.get(sitemap_url)
                        r.raise_for_status()
                        batch = self._parse_url_sitemap(r.text)
                        log.info("found %d wine URLs in %s", len(batch), sitemap_url)
                        product_urls.extend(batch)
                    except Exception as exc:
                        log.warning("Child sitemap error %s: %s", sitemap_url, exc)
            else:
                product_urls = self._parse_url_sitemap(root_xml)

            return product_urls

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
    def _parse_url_sitemap(xml_text: str) -> list[str]:
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            xml_text = re.sub(r"^<\?xml[^>]+\?>", "", xml_text.lstrip("\ufeff")).strip()
            root = ET.fromstring(xml_text)

        urls: list[str] = []
        for el in root.iter():
            tag = el.tag.split("}")[-1] if "}" in el.tag else el.tag
            if tag == "loc" and el.text:
                u = el.text.strip()
                if SimpleWineBrowser._looks_like_product_url(u):
                    urls.append(u)
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
