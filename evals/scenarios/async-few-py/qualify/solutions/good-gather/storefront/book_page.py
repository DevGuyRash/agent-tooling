"""The book page: one book's details, price, stock, and reviews, put together from the four backends."""

import asyncio

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


async def _book(backends, isbn):
    try:
        return await fetch_book(backends, isbn)
    except BackendError as exc:
        if exc.status == 404:
            raise BookNotFound(isbn) from None
        raise PageUnavailable("catalog") from exc


async def _price(backends, isbn):
    try:
        return await fetch_price(backends, isbn)
    except BackendError as exc:
        raise PageUnavailable("pricing") from exc


async def _or_none(lookup):
    try:
        return await lookup
    except BackendError:
        return None


async def book_page(backends, isbn):
    """The page for one ISBN, as the API returns it (rules in README.md). The lookups run side by side; the
    first required one to fail ends the page, and the rest are stopped before the error goes up."""
    tasks = [asyncio.ensure_future(_book(backends, isbn)), asyncio.ensure_future(_price(backends, isbn)),
             asyncio.ensure_future(_or_none(fetch_stock(backends, isbn))),
             asyncio.ensure_future(_or_none(fetch_reviews(backends, isbn)))]
    try:
        book, price, stock, reviews = await asyncio.gather(*tasks)
    except BaseException:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise
    return {
        "isbn": isbn,
        "title": book["title"],
        "authors": book["authors"],
        "price": {"amount": price["amount"], "currency": price["currency"]},
        "stock": None if stock is None else {"total": sum(stock["stores"].values()), "stores": stock["stores"]},
        "reviews": None if reviews is None else {"rating": reviews["rating"], "count": reviews["count"]},
    }
