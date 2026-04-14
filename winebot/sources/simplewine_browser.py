from __future__ import annotations

import logging
from urllib.parse import urljoin, urlparse

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

log = logging.getLogger(__name__)


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
            context = await browser.new_context(
                viewport={"width": 1440, "height": 1600},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                locale="ru-RU",
                extra_http_headers={"Accept-Language": "ru-RU,ru;q=0.9"},
            )
            page = await context.new_page()

            urls: list[str] = []
            try:
                try:
                    await page.goto(
                        self.catalog_url,
                        wait_until="load",
                        timeout=60_000,
                    )
                except PlaywrightTimeout:
                    log.warning("Таймаут загрузки каталога, пробуем продолжить")

                await page.wait_for_timeout(3000)

                for scroll_i in range(10):
                    try:
                        hrefs: list[str] = await page.evaluate(
                            """() => Array.from(document.querySelectorAll('a[href]'))
                                .map(a => a.getAttribute('href'))
                                .filter(Boolean)"""
                        )
                    except Exception as exc:
                        log.warning("evaluate провалился на scroll %d: %s", scroll_i, exc)
                        await page.wait_for_timeout(1500)
                        continue

                    for href in hrefs:
                        full_url = urljoin("https://simplewine.ru", href)
                        if self._looks_like_product_url(full_url) and full_url not in urls:
                            urls.append(full_url)
                            if len(urls) >= limit:
                                return urls

                    log.info("Скролл %d: найдено товаров %d", scroll_i + 1, len(urls))
                    await page.mouse.wheel(0, 2800)
                    await page.wait_for_timeout(1400)

            except Exception as exc:
                log.error("Ошибка в SimpleWineBrowser: %s", exc)
            finally:
                await browser.close()

            return urls

    @staticmethod
    def _looks_like_product_url(url: str) -> bool:
        """Только конкретные страницы товаров, не фильтры и не каталог."""
        if not url.startswith("https://simplewine.ru/catalog/vino/"):
            return False

        parsed = urlparse(url)
        path = parsed.path.rstrip("/")

        # Исключаем фильтры, пагинацию, сортировку
        bad_segments = ("/filter/", "/sort/", "/page/", "/compare/", "/cart/")
        if any(seg in path for seg in bad_segments):
            return False

        # Исключаем query-параметры (страницы пагинации)
        if parsed.query:
            return False

        # Страница товара: ровно 3 сегмента → /catalog/vino/{slug}
        parts = [p for p in path.split("/") if p]
        return len(parts) == 3
