import re
import httpx
from selectolax.parser import HTMLParser
from .base import RawOffer

UA = {"User-Agent": "Mozilla/5.0 (WineBot/1.0)"}

def _int_price_from_text(text: str) -> int | None:
    # examples: "1 299 ₽"
    m = re.search(r"(\d[\d\s]{2,})\s*₽", text)
    if not m:
        return None
    try:
        return int(m.group(1).replace(" ", ""))
    except Exception:
        return None

def _clean_text(s: str, limit: int = 2000) -> str:
    s = re.sub(r"\s+", " ", s).strip()
    return s[:limit]

class SimpleWineScraper:
    store = "SimpleWine"

    def __init__(self):
        self.client = httpx.AsyncClient(timeout=25, follow_redirects=True, headers=UA)

    async def get_candidate_urls(self) -> list[str]:
        url = "https://simplewine.ru/catalog/vino/"
        r = await self.client.get(url)
        if r.status_code >= 400:
            return []
        doc = HTMLParser(r.text)
        urls = []
        for a in doc.css("a"):
            href = a.attributes.get("href")
            if not href:
                continue
            if "/catalog/" in href and "vino" in href and href.count("/") >= 4:
                if href.startswith("/"):
                    href = "https://simplewine.ru" + href
                urls.append(href.split("?")[0])
        seen, out = set(), []
        for u in urls:
            if u not in seen:
                seen.add(u)
                out.append(u)
        return out[:120]

    async def parse_offer(self, url: str) -> RawOffer | None:
        r = await self.client.get(url)
        if r.status_code >= 400:
            return None
        doc = HTMLParser(r.text)

        h1 = doc.css_first("h1")
        title = h1.text().strip() if h1 else None

        og = doc.css_first('meta[property="og:image"]')
        image = og.attributes.get("content") if og else None

        raw_text = _clean_text(doc.text())
        price = _int_price_from_text(raw_text)

        return RawOffer(
            store=self.store,
            url=url,
            title=title,
            price_rub=price,
            image_url=image,
            raw_text=raw_text,
        )
