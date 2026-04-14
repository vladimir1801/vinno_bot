from __future__ import annotations

import logging
from urllib.parse import urljoin

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
                    "--disable-web-security",
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
                # Ждём полной загрузки — это убирает проблему с редиректом
                try:
                    await page.goto(
                        self.catalog_url,
                        wait_until="load",
                        timeout=60_000,
                    )
                except PlaywrightTimeout:
                    log.warning("Таймаут загрузки каталога, пробуем продолжить")

                await page.wait_for_timeout(3000)

                for scroll_i in range(8):
                    # page.evaluate стабильнее locator.evaluate_all при редиректах
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

                    log.info("После скролла %d собрано %d URL", scroll_i + 1, len(urls))
                    await page.mouse.wheel(0, 2800)
                    await page.wait_for_timeout(1400)

            except Exception as exc:
                log.error("Ошибка в SimpleWineBrowser: %s", exc)
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
