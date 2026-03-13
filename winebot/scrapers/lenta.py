import re, json
import httpx
from selectolax.parser import HTMLParser
from .base import RawOffer

UA = {"User-Agent": "Mozilla/5.0 (WineBot/1.0)"}

def _extract_json_ld(html: str):
    doc = HTMLParser(html)
    for s in doc.css('script[type="application/ld+json"]'):
        try:
            yield json.loads(s.text())
        except Exception:
            continue

def _int_price(x) -> int | None:
    try:
        return int(float(str(x).replace(" ", "").replace(",", ".")))
    except Exception:
        return None

def _clean_text(s: str, limit: int = 2000) -> str:
    s = re.sub(r"\s+", " ", s).strip()
    return s[:limit]

class LentaScraper:
    store = "Лента"

    def __init__(self):
        self.client = httpx.AsyncClient(timeout=25, follow_redirects=True, headers=UA)

    async def get_candidate_urls(self) -> list[str]:
        url = "https://lenta.com/catalog/vino-22541/"
        r = await self.client.get(url)
        if r.status_code >= 400:
            return []
        doc = HTMLParser(r.text)
        urls = []
        for a in doc.css("a"):
            href = a.attributes.get("href")
            if not href:
                continue
            if "/product/" in href:
                if href.startswith("/"):
                    href = "https://lenta.com" + href
                urls.append(href.split("?")[0])
        # uniq preserve order
        seen, out = set(), []
        for u in urls:
            if u not in seen:
                seen.add(u)
                out.append(u)
        return out[:100]

    async def parse_offer(self, url: str) -> RawOffer | None:
        r = await self.client.get(url)
        if r.status_code >= 400:
            return None

        title = None
        price = None
        image = None

        for block in _extract_json_ld(r.text):
            items = []
            if isinstance(block, dict) and "@graph" in block and isinstance(block["@graph"], list):
                items = block["@graph"]
            elif isinstance(block, list):
                items = block
            elif isinstance(block, dict):
                items = [block]
            for it in items:
                if isinstance(it, dict) and it.get("@type") == "Product":
                    title = it.get("name") or title
                    img = it.get("image")
                    if isinstance(img, list) and img:
                        image = img[0] or image
                    elif isinstance(img, str):
                        image = img
                    offers = it.get("offers")
                    if isinstance(offers, dict):
                        price = _int_price(offers.get("price")) or price

        # fallback title
        if not title:
            doc = HTMLParser(r.text)
            h1 = doc.css_first("h1")
            if h1:
                title = h1.text().strip()

        # fallback image
        if not image:
            doc = HTMLParser(r.text)
            og = doc.css_first('meta[property="og:image"]')
            if og:
                image = og.attributes.get("content")

        # fallback price
        if price is None:
            m = re.search(r"(\d[\d\s]{2,})\s*₽", r.text)
            if m:
                price = _int_price(m.group(1))

        raw_text = _clean_text(HTMLParser(r.text).text())

        return RawOffer(
            store=self.store,
            url=url,
            title=title,
            price_rub=price,
            image_url=image,
            raw_text=raw_text,
        )
