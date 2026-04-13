from __future__ import annotations

from urllib.parse import urljoin

from playwright.async_api import Error, TimeoutError, async_playwright


class SimpleWineBrowser:
    store = "SimpleWine"
    catalog_url = "https://simplewine.ru/catalog/vino/"

    async def get_candidate_urls(self, limit: int = 8) -> list[str]:
        urls: list[str] = []

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

            try:
                await page.goto(
                    self.catalog_url,
                    wait_until="domcontentloaded",
                    timeout=60_000,
                )

                try:
                    await page.wait_for_load_state("networkidle", timeout=15_000)
                except TimeoutError:
                    print("[simplewine_browser] networkidle timeout, continue anyway")

                await page.wait_for_timeout(2_000)

                for step in range(6):
                    hrefs = await self._safe_collect_hrefs(page)
                    print(
                        f"[simplewine_browser] step {step + 1}: "
                        f"collected {len(hrefs)} hrefs before filtering"
                    )

                    for href in hrefs:
                        full_url = urljoin("https://simplewine.ru", href)
                        if self._looks_like_product_url(full_url) and full_url not in urls:
                            urls.append(full_url)
                            print(f"[simplewine_browser] candidate: {full_url}")

                            if len(urls) >= limit:
                                print(
                                    f"[simplewine_browser] done: "
                                    f"{len(urls)} candidate urls"
                                )
                                return urls

                    previous_count = len(urls)

                    await page.mouse.wheel(0, 2600)
                    await page.wait_for_timeout(1_500)

                    try:
                        await page.wait_for_load_state("networkidle", timeout=10_000)
                    except TimeoutError:
                        pass

                    if len(urls) == previous_count and step >= 2:
                        print(
                            "[simplewine_browser] no new urls after scroll, "
                            "stopping early"
                        )
                        break

                print(f"[simplewine_browser] final candidate urls: {len(urls)}")
                return urls

            finally:
                await browser.close()

    async def _safe_collect_hrefs(self, page) -> list[str]:
        for attempt in range(3):
            try:
                return await page.eval_on_selector_all(
                    "a[href]",
                    "nodes => nodes.map(n => n.getAttribute('href')).filter(Boolean)",
                )
            except Error as exc:
                message = str(exc)
                if "Execution context was destroyed" in message:
                    print(
                        f"[simplewine_browser] href collection retry "
                        f"{attempt + 1}/3 after navigation"
                    )
                    await page.wait_for_timeout(1_000)
                    try:
                        await page.wait_for_load_state("domcontentloaded", timeout=10_000)
                    except TimeoutError:
                        pass
                    continue
                raise

        print("[simplewine_browser] failed to collect hrefs after retries")
        return []

    @staticmethod
    def _looks_like_product_url(url: str) -> bool:
        if not url.startswith("https://simplewine.ru/catalog/vino/"):
            return False

        bad_parts = [
            "?page-number=",
            "/filter/",
            "/sorting/",
            "#",
        ]
        for part in bad_parts:
            if part in url:
                return False

        tail = url.replace("https://simplewine.ru/catalog/vino/", "").strip("/")
        parts = [p for p in tail.split("/") if p]

        if len(parts) < 2:
            return False

        if len(parts) == 1 and len(parts[0]) < 12:
            return False

        return True
