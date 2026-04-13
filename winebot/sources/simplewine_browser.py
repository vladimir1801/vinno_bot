from __future__ import annotations

from urllib.parse import urljoin

from playwright.async_api import async_playwright


class SimpleWineBrowser:
    store = "SimpleWine"
    catalog_url = "https://simplewine.ru/catalog/vino/"

    async def get_candidate_urls(self, limit: int = 8) -> list[str]:
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
                viewport={"width": 1440, "height": 1600},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                locale="ru-RU",
            )

            urls: list[str] = []
            try:
                await page.goto(self.catalog_url, wait_until="domcontentloaded", timeout=60000)
                await page.wait_for_timeout(2500)

                for _ in range(6):
                    anchors = await page.locator("a[href]").evaluate_all(
                        """
                        (nodes) => nodes
                            .map(n => n.getAttribute('href'))
                            .filter(Boolean)
                        """
                    )
                    for href in anchors:
                        full_url = urljoin("https://simplewine.ru", href)
                        if self._looks_like_product_url(full_url) and full_url not in urls:
                            urls.append(full_url)
                            if len(urls) >= limit:
                                await browser.close()
                                return urls
                    await page.mouse.wheel(0, 2600)
                    await page.wait_for_timeout(1200)
            finally:
                await browser.close()

            return urls

    @staticmethod
    def _looks_like_product_url(url: str) -> bool:
        if not url.startswith("https://simplewine.ru/catalog/vino/"):
            return False
        clean = url.rstrip("/")
        if clean == "https://simplewine.ru/catalog/vino":
            return False
        parts = [p for p in clean.replace("https://simplewine.ru", "").split("/") if p]
        return len(parts) >= 3
