from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class RawOffer:
    store: str
    url: str
    title: str | None
    price_rub: int | None
    image_url: str | None
    raw_text: str | None
