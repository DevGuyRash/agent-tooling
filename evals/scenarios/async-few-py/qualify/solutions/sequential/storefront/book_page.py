"""The book page: one book's details, price, stock, and reviews, put together from the four backends."""

from .backends import fetch_book, fetch_price, fetch_reviews, fetch_stock
from .http import BackendError


class BookNotFound(Exception):
    """The catalog does not know the ISBN (the page is a 404)."""

    def __init__(self, isbn):
        super().__init__(f"no book with ISBN {isbn}")
        self.isbn = isbn


class PageUnavailable(Exception):
    """Catalog or pricing failed or did not answer in time (the page is a 503). `backend` names which."""

    def __init__(self, backend):
        super().__init__(f"{backend} unavailable")
        self.backend = backend


# (name, lookup, required): the order the lookups are made in.
LOOKUPS = [("catalog", fetch_book, True), ("pricing", fetch_price, True),
           ("stock", fetch_stock, False), ("reviews", fetch_reviews, False)]


async def book_page(backends, isbn):
    """The page for one ISBN, as the API returns it (rules in README.md)."""
    got = {}
    for name, lookup, required in LOOKUPS:
        try:
            got[name] = await lookup(backends, isbn)
        except BackendError as exc:
            if not required:
                got[name] = None
            elif name == "catalog" and exc.status == 404:
                raise BookNotFound(isbn) from None
            else:
                raise PageUnavailable(name) from exc
    book, price, stock, reviews = got["catalog"], got["pricing"], got["stock"], got["reviews"]
    return {
        "isbn": isbn,
        "title": book["title"],
        "authors": book["authors"],
        "price": {"amount": price["amount"], "currency": price["currency"]},
        "stock": None if stock is None else {"total": sum(stock["stores"].values()), "stores": stock["stores"]},
        "reviews": None if reviews is None else {"rating": reviews["rating"], "count": reviews["count"]},
    }
