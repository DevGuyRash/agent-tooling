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


async def _catalog(backends, isbn):
    try:
        return await fetch_book(backends, isbn)
    except BackendError as exc:
        if exc.status == 404:
            raise BookNotFound(isbn) from None
        raise PageUnavailable("catalog") from exc


async def _pricing(backends, isbn):
    try:
        return await fetch_price(backends, isbn)
    except BackendError as exc:
        raise PageUnavailable("pricing") from exc


async def _optional(fetch, backends, isbn):
    try:
        return await fetch(backends, isbn)
    except BackendError:
        return None


async def book_page(backends, isbn):
    """The page for one ISBN, as the API returns it.

    All four lookups are started at once. If catalog or pricing fails, the page fails as soon as that is
    known: the lookups still running are cancelled (and waited for, so their connections are closed) and the
    error is raised. Stock and reviews are optional: null when they fail or are slow.
    """
    tasks = {
        "catalog": asyncio.create_task(_catalog(backends, isbn)),
        "pricing": asyncio.create_task(_pricing(backends, isbn)),
        "stock": asyncio.create_task(_optional(fetch_stock, backends, isbn)),
        "reviews": asyncio.create_task(_optional(fetch_reviews, backends, isbn)),
    }
    try:
        done, pending = await asyncio.wait(tasks.values(), return_when=asyncio.FIRST_EXCEPTION)
    except BaseException:
        for task in tasks.values():
            task.cancel()
        await asyncio.gather(*tasks.values(), return_exceptions=True)
        raise
    if pending:
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
    for name in ("catalog", "pricing"):  # the catalog's verdict first, as before
        task = tasks[name]
        if task.done() and not task.cancelled() and task.exception() is not None:
            raise task.exception()
    book, price = tasks["catalog"].result(), tasks["pricing"].result()
    stock, reviews = tasks["stock"].result(), tasks["reviews"].result()
    return {
        "isbn": isbn,
        "title": book["title"],
        "authors": book["authors"],
        "price": {"amount": price["amount"], "currency": price["currency"]},
        "stock": None if stock is None else {"total": sum(stock["stores"].values()), "stores": stock["stores"]},
        "reviews": None if reviews is None else {"rating": reviews["rating"], "count": reviews["count"]},
    }
