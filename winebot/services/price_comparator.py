from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from winebot.parsers.simplewine_product import ProductCard
from winebot.parsers.winestyle_product import WinestyleSearcher

log = logging.getLogger(__name__)


@dataclass
class PriceResult:
    store: str
    price: str | None
    url: str | None = None

    def to_dict(self) -> dict:
        return {"store": self.store, "price": self.price, "url": self.url}


async def compare_prices(card: ProductCard) -> list[PriceResult]:
    """
    Returns a list of PriceResult for SimpleWine + Winestyle.
    Never raises — Winestyle failure is silently skipped.
    """
    results: list[PriceResult] = []

    # SimpleWine is always the primary source
    results.append(PriceResult(store="SimpleWine", price=card.price, url=card.url))

    # Winestyle secondary search
    try:
        ws = await WinestyleSearcher().search(card.title)
        if ws and ws.get("price"):
            results.append(PriceResult(
                store="Winestyle",
                price=ws["price"],
                url=ws.get("url"),
            ))
    except Exception as exc:
        log.warning("compare_prices: Winestyle lookup failed: %s", exc)

    return results


async def enrich_card(card: ProductCard) -> ProductCard:
    """
    Fill in missing card fields (grape, country, region, alcohol, color, sweetness, year)
    by searching Winestyle. Only overwrites None fields.
    """
    enrichable = ("grape", "country", "region", "alcohol", "color", "sweetness", "year")
    missing = [f for f in enrichable if not getattr(card, f, None)]
    if not missing:
        return card

    try:
        ws = await WinestyleSearcher().search(card.title)
        if not ws:
            return card
        for field in missing:
            val = ws.get(field)
            if val and isinstance(val, str) and 1 < len(val.strip()) < 120:
                setattr(card, field, val.strip())
                log.debug("Enriched %s from Winestyle: %s", field, val.strip())
    except Exception as exc:
        log.warning("enrich_card failed: %s", exc)

    return card


def format_price_comparison(results: list[PriceResult] | list[dict]) -> str:
    """
    Returns an HTML string with price comparison table.
    Works with both PriceResult objects and plain dicts (from payload).
    """
    if not results or len(results) < 2:
        return ""

    # Normalise to dicts
    dicts = [r.to_dict() if isinstance(r, PriceResult) else r for r in results]

    # Find cheapest store
    def price_num(d: dict) -> float:
        p = d.get("price") or ""
        m = re.search(r"(\d[\d\s]*)", p.replace("\xa0", " "))
        if m:
            try:
                return float(re.sub(r"\s+", "", m.group(1)))
            except ValueError:
                pass
        return float("inf")

    cheapest = min(dicts, key=price_num)

    lines = ["🛒 <b>Сравнение цен:</b>"]
    for d in dicts:
        store = d.get("store", "")
        price = d.get("price") or "—"
        url = d.get("url")
        is_best = d is cheapest and price_num(d) < float("inf")

        badge = "✅ " if is_best else "    "
        if url:
            entry = f"{badge}<a href='{url}'>{store}</a>: <b>{price}</b>"
        else:
            entry = f"{badge}{store}: <b>{price}</b>"
        lines.append(entry)

    return "\n".join(lines)
