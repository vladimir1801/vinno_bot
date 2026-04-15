from __future__ import annotations

import logging
import re

import httpx
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

_BASE = "https://www.winestyle.ru"
_SEARCH_URL = f"{_BASE}/catalog/search/"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8",
}


class WinestyleSearcher:
    """Search Winestyle.ru for a wine by title, parse price and basic fields."""

    async def search(self, title: str) -> dict | None:
        """
        Returns dict with keys: price, url, store, grape, country, region, alcohol
        or None if nothing found / any error.
        """
        clean = _clean_title(title)
        if not clean:
            return None
        try:
            async with httpx.AsyncClient(
                headers=_HEADERS, timeout=20, follow_redirects=True
            ) as client:
                r = await client.get(_SEARCH_URL, params={"search": clean})
                if r.status_code != 200:
                    log.debug("Winestyle search status %d for %r", r.status_code, clean)
                    return None

                product_url = _first_result_url(r.text, title)
                if not product_url:
                    return None

                pr = await client.get(product_url)
                if pr.status_code != 200:
                    return None

                return _parse_product_page(BeautifulSoup(pr.text, "html.parser"), product_url)
        except Exception as exc:
            log.warning("Winestyle search failed for %r: %s", title, exc)
            return None


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _clean_title(title: str) -> str:
    """Strip vintage year and volume markers so search hits more broadly."""
    t = re.sub(r"\b(19|20)\d{2}\b", "", title)
    t = re.sub(r"\d+[.,]?\d*\s*(мл|л|ml|l)\b", "", t, flags=re.IGNORECASE)
    return " ".join(t.split())[:100]


def _word_overlap(a: str, b: str) -> float:
    """Fraction of words in `a` that also appear in `b` (case-insensitive)."""
    wa = set(re.findall(r"[а-яёa-z]+", a.lower()))
    wb = set(re.findall(r"[а-яёa-z]+", b.lower()))
    if not wa:
        return 0.0
    return len(wa & wb) / len(wa)


def _first_result_url(html: str, original_title: str) -> str | None:
    """Pick the best-matching product URL from the search results page."""
    soup = BeautifulSoup(html, "html.parser")

    # Winestyle search results: try several known selector patterns
    candidate_selectors = [
        "a.article-title",
        "a[class*='title']",
        "a[href*='/products/']",
        ".article a",
        ".goods-item a",
        ".product-item a",
        "h3 > a",
        "h2 > a",
    ]

    best_url: str | None = None
    best_score = 0.0

    for sel in candidate_selectors:
        for link in soup.select(sel)[:10]:
            href = (link.get("href") or "").strip()
            text = link.get_text(" ", strip=True)
            if not href or not text:
                continue
            full_url = href if href.startswith("http") else _BASE + href
            score = _word_overlap(original_title, text)
            if score > best_score and score >= 0.25:
                best_score = score
                best_url = full_url

    log.debug("Winestyle best match score=%.2f url=%s", best_score, best_url)
    return best_url


def _parse_product_page(soup: BeautifulSoup, url: str) -> dict:
    """Extract price and wine characteristics from a Winestyle product page."""
    result: dict = {"store": "Winestyle", "url": url}

    # ── Price ────────────────────────────────────────────────────────────────
    price_selectors = [
        "span[itemprop='price']",
        "meta[itemprop='price']",
        "meta[property='product:price:amount']",
        "[class*='price-val']",
        "[class*='price_val']",
        "[class*='item-price']",
        "[class*='cost']",
        "[class*='price']",
    ]
    for sel in price_selectors:
        el = soup.select_one(sel)
        if not el:
            continue
        raw = (el.get("content") or el.get("value") or el.get_text(" ", strip=True) or "")
        raw = raw.replace("\xa0", " ")
        m = re.search(r"(\d[\d\s]{1,8})", raw)
        if m:
            digits = re.sub(r"\s+", "", m.group(1))
            try:
                price_num = int(digits)
                if 100 <= price_num <= 500_000:
                    result["price"] = f"{price_num:,}".replace(",", " ") + " ₽"
                    break
            except ValueError:
                pass

    # ── Wine characteristics (text-based label → next-line value) ────────────
    text = soup.get_text("\n", strip=True)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    _FIELD_LABELS: dict[str, tuple[str, ...]] = {
        "country":  ("страна", "country"),
        "region":   ("регион", "апелласьон", "апелласион", "регион/апелласьон"),
        "grape":    ("сорт", "сорта", "виноград", "сорт винограда", "сорта винограда"),
        "alcohol":  ("крепость", "алкоголь"),
        "color":    ("цвет",),
        "sweetness": ("сахар", "сладость"),
        "year":     ("урожай", "год урожая", "vintage"),
    }

    for i, line in enumerate(lines):
        norm = line.lower().replace(":", "").strip()
        for field, labels in _FIELD_LABELS.items():
            if field in result:
                continue
            if norm in labels and i + 1 < len(lines):
                val = lines[i + 1].strip()
                if val and len(val) < 120 and not any(lbl in val.lower() for lbl in labels):
                    result[field] = val

    return result
