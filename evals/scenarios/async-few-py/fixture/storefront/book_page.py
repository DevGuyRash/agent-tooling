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


async def book_page(backends, isbn):
    """The page for one ISBN, as the API returns it.

    Catalog and pricing are required: an unknown ISBN raises BookNotFound, and any other failure of either
    raises PageUnavailable naming it. Stock and reviews are optional: when they fail or do not answer in
    time the page has null in their place.
    """
    try:
        book = await fetch_book(backends, isbn)
    except BackendError as exc:
        if exc.status == 404:
            raise BookNotFound(isbn) from None
        raise PageUnavailable("catalog") from exc
    try:
        price = await fetch_price(backends, isbn)
    except BackendError as exc:
        raise PageUnavailable("pricing") from exc
    try:
        stock = await fetch_stock(backends, isbn)
    except BackendError:
        stock = None
    try:
        reviews = await fetch_reviews(backends, isbn)
    except BackendError:
        reviews = None
    return {
        "isbn": isbn,
        "title": book["title"],
        "authors": book["authors"],
        "price": {"amount": price["amount"], "currency": price["currency"]},
        "stock": None if stock is None else {"total": sum(stock["stores"].values()), "stores": stock["stores"]},
        "reviews": None if reviews is None else {"rating": reviews["rating"], "count": reviews["count"]},
    }
