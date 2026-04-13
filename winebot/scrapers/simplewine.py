import httpx
from bs4 import BeautifulSoup

BASE_URL = "https://simplewine.ru"
CATALOG_URL = "https://simplewine.ru/catalog/vino/"


async def get_candidate_urls(limit=10):
    urls = []

    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(CATALOG_URL)
        if r.status_code != 200:
            print(f"[simplewine] failed to fetch catalog: {r.status_code}")
            return urls

        soup = BeautifulSoup(r.text, "html.parser")

        # ищем ссылки на товары
        for a in soup.find_all("a", href=True):
            href = a["href"]

            if "/product/" in href or "/vino/" in href:
                full_url = BASE_URL + href if href.startswith("/") else href

                if full_url not in urls:
                    urls.append(full_url)

            if len(urls) >= limit:
                break

    print(f"[simplewine] extracted {len(urls)} candidate urls")
    return urls


async def parse_wine(url):
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(url)
        if r.status_code != 200:
            print(f"[simplewine] failed to fetch page: {url}")
            return None

        soup = BeautifulSoup(r.text, "html.parser")

        # название
        title_tag = soup.find("h1")
        if not title_tag:
            print(f"[simplewine] no title: {url}")
            return None

        title = title_tag.text.strip()

        # цена
        price_tag = soup.find(string=lambda x: x and "₽" in x)
        price = price_tag.strip() if price_tag else "нет цены"

        return {
            "title": title,
            "price": price,
            "url": url,
        }
