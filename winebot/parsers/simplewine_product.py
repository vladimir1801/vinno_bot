from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright


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
            grape=self._pick_field(soup, ["сорт", "сорта винограда", "виноград"]),
            region=self._pick_field(soup, ["регион"]),
            volume=self._pick_field(soup, ["объем", "объём"]),
        )

    async def _fetch_html(self, url: str) -> str | None:
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
                viewport={"width": 1440, "height": 1400},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                locale="ru-RU",
            )
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                await page.wait_for_timeout(2000)
                return await page.content()
            except Exception:
                return None
            finally:
                await browser.close()

    def _pick_title(self, soup: BeautifulSoup) -> str | None:
        candidates = [
            soup.find("h1"),
            soup.select_one("meta[property='og:title']"),
            soup.find("title"),
        ]
        for node in candidates:
            if not node:
                continue
            if getattr(node, "name", "") == "meta":
                text = (node.get("content") or "").strip()
            else:
                text = node.get_text(" ", strip=True)
            text = re.sub(r"\s+", " ", text).strip()
            if text:
                return text
        return None

    def _pick_image(self, soup: BeautifulSoup, url: str) -> str | None:
        meta = soup.select_one("meta[property='og:image']")
        if meta and meta.get("content"):
            return urljoin(url, meta["content"])
        img = soup.find("img")
        if img and img.get("src"):
            return urljoin(url, img["src"])
        return None

    def _pick_price(self, soup: BeautifulSoup) -> str | None:
        text = soup.get_text(" ", strip=True)
        match = re.search(r"(\d[\d\s]{1,12})\s*₽", text)
        if match:
            return re.sub(r"\s+", " ", match.group(1)).strip() + " ₽"
        return None

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
                key_norm = str(key).lower().strip()
                if key_norm in labels and isinstance(value, str):
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
