from dataclasses import dataclass
from decimal import Decimal

from app.normalization import clean_text, parse_price


@dataclass(frozen=True)
class ScrapedProduct:
    """Producto tal como sale del scraper, ya normalizado y listo para persistir."""

    name: str
    price_text: str
    price_amount: Decimal | None
    price_currency: str | None
    description: str
    image_url: str
    source_url: str | None = None

    @classmethod
    def build(
        cls,
        *,
        name: str,
        price: str | None,
        description: str | None,
        image_url: str,
        source_url: str | None = None,
    ) -> "ScrapedProduct":
        """Unico punto donde se normaliza un producto, compartido por todos los sitios."""
        price_parsed = parse_price(price)
        return cls(
            name=clean_text(name),
            price_text=price_parsed.text,
            price_amount=price_parsed.amount,
            price_currency=price_parsed.currency,
            description=clean_text(description),
            image_url=image_url,
            source_url=source_url,
        )
