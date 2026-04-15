from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

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


@dataclass(slots=True)
class ProductCard:
    title: str
    url: str
    image_url: str | None
    price: str | None
    country: str | None
    grape: str | None
    region: str | None
    volume: str | None
    color: str | None       # красное / белое / розовое / оранжевое
    sweetness: str | None   # сухое / полусухое / полусладкое / сладкое / брют
    alcohol: str | None     # "13%" или "13,5%"
    year: str | None        # "2021"
    description: str | None # тейстинг-ноты с сайта
    store: str = "SimpleWine"


class SimpleWineProductParser:

    async def parse(self, url: str) -> ProductCard | None:
        html = await self._fetch_html(url)
        if not html:
            return None

        soup = BeautifulSoup(html, "html.parser")

        title = self._pick_title(soup)
        if not title:
            return None

        return ProductCard(
            title=title,
            url=url,
            image_url=self._pick_image(soup, url),
            price=self._pick_price(soup),
            country=self._pick_field(soup, ["страна"]),
            grape=self._pick_field(soup, ["сорт", "сорта винограда", "виноград", "сорт винограда"]),
            region=self._pick_field(soup, ["регион", "апелласьон", "апелласион"]),
            volume=self._pick_field(soup, ["объем", "объём", "ёмкость", "емкость"]),
            color=self._pick_field(soup, ["цвет"]),
            sweetness=self._pick_field(soup, ["сахар", "сладость", "содержание сахара"]),
            alcohol=self._pick_field(soup, ["крепость", "алкоголь", "спирт"]),
            year=self._pick_year(soup, title),
            description=self._pick_description(soup),
        )

    # ─── HTML fetch: httpx first, Playwright fallback ────────────────────────

    async def _fetch_html(self, url: str) -> str | None:
        # 1. Fast httpx request — works for SSR/server-rendered pages (~50% of
        #    modern Russian e-commerce).  Much faster and harder to block.
        html = await self._fetch_with_httpx(url)
        if html and _has_product_content(html):
            log.debug("httpx fetch OK: %s", url)
            return html

        # 2. Playwright fallback — needed for React/Vue CSR pages.
        #    Uses wait_for_selector("h1") instead of a fixed delay so we
        #    block until the JavaScript has actually rendered the title.
        log.debug("httpx miss, trying Playwright: %s", url)
        return await self._fetch_with_playwright(url)

    async def _fetch_with_httpx(self, url: str) -> str | None:
        try:
            async with httpx.AsyncClient(
                headers=_HEADERS, timeout=15, follow_redirects=True
            ) as client:
                r = await client.get(url)
                if r.status_code == 200:
                    return r.text
        except Exception as exc:
            log.debug("httpx error for %s: %s", url, exc)
        return None

    async def _fetch_with_playwright(self, url: str) -> str | None:
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=[
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-blink-features=AutomationControlled",
                    ],
                )
                page = await browser.new_page(
                    viewport={"width": 1440, "height": 900},
                    user_agent=_HEADERS["User-Agent"],
                    locale="ru-RU",
                )
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=45_000)
                    # Wait for the product title to be rendered by JavaScript.
                    # Falls through (no exception) if the selector never appears.
                    try:
                        await page.wait_for_selector(
                            "h1, [itemprop='name'], [class*='product-title'], [class*='item-title']",
                            timeout=12_000,
                        )
                    except Exception:
                        pass
                    return await page.content()
                except Exception as exc:
                    log.debug("Playwright goto failed for %s: %s", url, exc)
                    return None
                finally:
                    await browser.close()
        except Exception as exc:
            log.warning("Playwright launch failed for %s: %s", url, exc)
            return None

    # ─── Title ────────────────────────────────────────────────────────────────

    def _pick_title(self, soup: BeautifulSoup) -> str | None:
        for node in [soup.find("h1"), soup.select_one("meta[property='og:title']"), soup.find("title")]:
            if not node:
                continue
            text = node.get("content", "").strip() if getattr(node, "name", "") == "meta" \
                else node.get_text(" ", strip=True)
            text = re.sub(r"\s+", " ", text).strip()
            if text:
                return text
        return None

    # ─── Image ────────────────────────────────────────────────────────────────

    def _pick_image(self, soup: BeautifulSoup, url: str) -> str | None:
        meta = soup.select_one("meta[property='og:image']")
        if meta and meta.get("content"):
            return urljoin(url, meta["content"])
        img = soup.find("img")
        if img and img.get("src"):
            return urljoin(url, img["src"])
        return None

    # ─── Price ────────────────────────────────────────────────────────────────

    def _pick_price(self, soup: BeautifulSoup) -> str | None:
        # Сначала ищем мета-тег с ценой (og:price или product:price:amount)
        for attr in ("product:price:amount", "og:price:amount"):
            meta = soup.select_one(f"meta[property='{attr}']")
            if meta and meta.get("content"):
                raw = meta["content"].strip()
                try:
                    price = int(float(raw.replace(",", ".")))
                    return f"{price:,}".replace(",", " ") + " ₽"
                except ValueError:
                    pass

        text = soup.get_text(" ", strip=True)
        match = re.search(r"(\d[\d\s]{1,12})\s*₽", text)
        if match:
            return re.sub(r"\s+", " ", match.group(1)).strip() + " ₽"
        return None

    # ─── Year ─────────────────────────────────────────────────────────────────

    def _pick_year(self, soup: BeautifulSoup, title: str) -> str | None:
        # 1. Из специального поля
        year_field = self._pick_field(soup, ["урожай", "год урожая", "vintages", "vintage"])
        if year_field:
            m = re.search(r"\b(19|20)\d{2}\b", year_field)
            if m:
                return m.group(0)

        # 2. Из заголовка
        m = re.search(r"\b(20[1-9]\d)\b", title)
        if m:
            return m.group(1)

        # 3. Из остального текста страницы
        text = soup.get_text(" ", strip=True)
        m = re.search(r"\b(20[1-9]\d)\b", text)
        if m:
            return m.group(1)

        return None

    # ─── Description ──────────────────────────────────────────────────────────

    def _pick_description(self, soup: BeautifulSoup) -> str | None:
        # 1. og:description
        meta = soup.select_one("meta[property='og:description'], meta[name='description']")
        if meta and meta.get("content"):
            text = meta["content"].strip()
            if len(text) > 40:
                return self._clean_description(text)

        # 2. Ищем блок описания по типичным классам SimpleWine / похожих сайтов
        for selector in [
            "[class*='description']",
            "[class*='about']",
            "[class*='taste']",
            "[class*='notes']",
            "[class*='degustation']",
            "[class*='detail']",
        ]:
            nodes = soup.select(selector)
            for node in nodes:
                text = node.get_text(" ", strip=True)
                if 60 < len(text) < 800:
                    return self._clean_description(text)

        # 3. Structured data
        for script in soup.select("script[type='application/ld+json']"):
            raw = script.string or script.get_text(strip=True)
            if not raw:
                continue
            try:
                data = json.loads(raw)
            except Exception:
                continue
            desc = self._search_json_desc(data)
            if desc and len(desc) > 40:
                return self._clean_description(desc)

        return None

    def _clean_description(self, text: str) -> str:
        text = re.sub(r"\s+", " ", text).strip()
        # Обрезаем до ~300 символов, не разрывая слово
        if len(text) > 300:
            text = text[:297].rsplit(" ", 1)[0] + "…"
        return text

    def _search_json_desc(self, data: Any) -> str | None:
        if isinstance(data, dict):
            for key, value in data.items():
                if key.lower() in ("description", "disambiguatingdescription") and isinstance(value, str):
                    return value
                found = self._search_json_desc(value)
                if found:
                    return found
        elif isinstance(data, list):
            for item in data:
                found = self._search_json_desc(item)
                if found:
                    return found
        return None

    # ─── Generic field ────────────────────────────────────────────────────────

    def _pick_field(self, soup: BeautifulSoup, labels: list[str]) -> str | None:
        text = soup.get_text("\n", strip=True)
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        lowered_labels = [label.lower() for label in labels]

        for i, line in enumerate(lines):
            normalized = line.lower().replace(":", "").strip()
            if normalized in lowered_labels and i + 1 < len(lines):
                value = lines[i + 1].strip()
                if value and len(value) < 120:
                    return value

            for label in lowered_labels:
                if normalized.startswith(label + " "):
                    value = line[len(label):].replace(":", "", 1).strip()
                    if value and len(value) < 120:
                        return value

        for script in soup.select("script[type='application/ld+json']"):
            raw = script.string or script.get_text(strip=True)
            if not raw:
                continue
            try:
                data: Any = json.loads(raw)
            except Exception:
                continue
            value = self._search_json(data, lowered_labels)
            if isinstance(value, str) and value.strip():
                return value.strip()

        return None

    def _search_json(self, data: Any, labels: list[str]) -> str | None:
        if isinstance(data, dict):
            for key, value in data.items():
                if str(key).lower().strip() in labels and isinstance(value, str):
                    return value
                found = self._search_json(value, labels)
                if found:
                    return found
        elif isinstance(data, list):
            for item in data:
                found = self._search_json(item, labels)
                if found:
                    return found
        return None
