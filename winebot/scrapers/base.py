from dataclasses import dataclass

@dataclass
class RawOffer:
    store: str
    url: str
    title: str | None
    price_rub: int | None
    image_url: str | None
    raw_text: str | None  # extra page text to help the model
