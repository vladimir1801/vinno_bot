import re
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup


class SimpleWineScraper:
    store = "SimpleWine"
    BASE_URL = "https://simplewine.ru"
    CATALOG_URL = "https://simplewine.ru/catalog/vino/"

    def _headers(self) -> dict:
        return {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,"
                "image/avif,image/webp,*/*;q=0.8"
            ),
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Referer": self.BASE_URL + "/",
        }

    async def get_candidate_urls(self, limit: int = 10) -> list[str]:
        urls: list[str] = []

        async with httpx.AsyncClient(
            timeout=20,
            follow_redirects=True,
            headers=self._headers(),
        ) as client:
            r = await client.get(self.CATALOG_URL)
            if r.status_code != 200:
                print(f"[simplewine] failed to fetch catalog: {r.status_code}")
                return urls

            soup = BeautifulSoup(r.text, "html.parser")

            for a in soup.find_all("a", href=True):
                href = a["href"].strip()
                full_url = urljoin(self.BASE_URL, href)

                if not self._looks_like_product_url(full_url):
                    continue

                if full_url not in urls:
                    urls.append(full_url)

                if len(urls) >= limit:
                    break

        print(f"[simplewine] extracted {len(urls)} candidate urls")
        return urls

    def _looks_like_product_url(self, url: str) -> bool:
        parsed = urlparse(url)
        if parsed.netloc and "simplewine.ru" not in parsed.netloc:
            return False

        path = parsed.path.rstrip("/")

        # Отсекаем сам каталог и тех. страницы
        if path in {"", "/catalog", "/catalog/vino"}:
            return False
        if not path.startswith("/catalog/vino/"):
            return False
        if any(part in path for part in ["/filter", "/page-", "/sorting"]):
            return False

        # Для карточки товара путь обычно глубже каталога:
        # /catalog/vino/<slug>
        parts = [p for p in path.split("/") if p]
        if len(parts) < 3:
            return False

        return True

    async def parse(self, url: str):
        async with httpx.AsyncClient(
            timeout=20,
            follow_redirects=True,
            headers=self._headers(),
        ) as client:
            r = await client.get(url)
            if r.status_code != 200:
                print(f"[simplewine] failed to fetch page: {url} ({r.status_code})")
                return None

            soup = BeautifulSoup(r.text, "html.parser")

            title = self._extract_title(soup)
            if not title:
                print(f"[simplewine] no title: {url}")
                return None

            price = self._extract_price(soup)
            image_url = self._extract_image(soup, url)

            data = {
                "title": title,
                "price": price,
                "url": url,
                "image_url": image_url,
                "store": self.store,
            }

            print(f"[simplewine] parsed item: {title}")
            return data

    def _extract_title(self, soup: BeautifulSoup) -> str | None:
        candidates = [
            soup.find("h1"),
            soup.select_one("[data-testid='product-title']"),
            soup.select_one("meta[property='og:title']"),
            soup.find("title"),
        ]
        for item in candidates:
            if not item:
                continue
            if getattr(item, "name", "") == "meta":
                text = (item.get("content") or "").strip()
            else:
                text = item.get_text(" ", strip=True)
            if text:
                return re.sub(r"\s+", " ", text).strip()
        return None

    def _extract_price(self, soup: BeautifulSoup) -> str | None:
        for text_node in soup.find_all(string=True):
            text = text_node.strip()
            if "₽" in text:
                cleaned = re.sub(r"\s+", " ", text)
                return cleaned
        return None

    def _extract_image(self, soup: BeautifulSoup, page_url: str) -> str | None:
        meta = soup.select_one("meta[property='og:image']")
        if meta and meta.get("content"):
            return urljoin(page_url, meta["content"])

        img = soup.find("img")
        if img and img.get("src"):
            return urljoin(page_url, img["src"])

        return None
