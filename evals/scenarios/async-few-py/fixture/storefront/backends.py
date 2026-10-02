"""The four backends the book page reads, and how long we wait for each (see docs/services.md)."""

import os
from dataclasses import dataclass
from urllib.parse import quote

from .http import get_json

# Seconds we wait for each backend's complete answer, connecting included. Catalog and pricing get a
# second because the page cannot be shown without them and the catalog is slow on a cold cache; stock
# and reviews only decorate the page, so we stop waiting for them sooner.
TIME_LIMITS = {"catalog": 1.0, "pricing": 1.0, "stock": 0.3, "reviews": 0.3}

_ENV = {"catalog": "STOREFRONT_CATALOG_URL", "pricing": "STOREFRONT_PRICING_URL",
        "stock": "STOREFRONT_STOCK_URL", "reviews": "STOREFRONT_REVIEWS_URL"}


@dataclass(frozen=True)
class Backends:
    """Base URLs of the backends."""

    catalog: str = "http://127.0.0.1:9101"
    pricing: str = "http://127.0.0.1:9102"
    stock: str = "http://127.0.0.1:9103"
    reviews: str = "http://127.0.0.1:9104"

    @classmethod
    def from_env(cls, environ=None):
        """Backends from STOREFRONT_*_URL, each falling back to its default."""
        environ = os.environ if environ is None else environ
        defaults = cls()
        return cls(**{name: (environ.get(var) or getattr(defaults, name)).rstrip("/") for name, var in _ENV.items()})


async def fetch_book(backends, isbn):
    """{"isbn", "title", "authors", ...} from the catalog; BackendError with status 404 for an unknown ISBN."""
    return await get_json("catalog", f"{backends.catalog}/v1/books/{quote(isbn)}", TIME_LIMITS["catalog"])


async def fetch_price(backends, isbn):
    """{"isbn", "amount", "currency"} from pricing."""
    return await get_json("pricing", f"{backends.pricing}/v1/prices/{quote(isbn)}", TIME_LIMITS["pricing"])


async def fetch_stock(backends, isbn):
    """{"isbn", "stores": {shop: copies}} from stock."""
    return await get_json("stock", f"{backends.stock}/v1/stock/{quote(isbn)}", TIME_LIMITS["stock"])


async def fetch_reviews(backends, isbn):
    """{"isbn", "rating", "count"} from reviews."""
    return await get_json("reviews", f"{backends.reviews}/v1/reviews/{quote(isbn)}/summary", TIME_LIMITS["reviews"])
