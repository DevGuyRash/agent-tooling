# storefront

The JSON API behind the Larkspur Books website and app. Its main call, `GET /books/{isbn}`, asks four internal backends (catalog, pricing, stock, reviews) about one book and returns the book page; what each backend does is in [docs/services.md](docs/services.md).

Standard library only, Python 3.11 or newer.

## Run

```bash
python3 -m storefront serve --port 8080
```

Backend addresses come from `STOREFRONT_CATALOG_URL`, `STOREFRONT_PRICING_URL`, `STOREFRONT_STOCK_URL`, and `STOREFRONT_REVIEWS_URL` (defaults `http://127.0.0.1:9101` to `9104`).

## The book page

`GET /books/{isbn}` answers 200 with:

```json
{"isbn": "9780141439518", "title": "Pride and Prejudice", "authors": ["Jane Austen"],
 "price": {"amount": "8.99", "currency": "GBP"},
 "stock": {"total": 4, "stores": {"Bath": 3, "Bristol": 0, "Frome": 1}},
 "reviews": {"rating": 4.6, "count": 2210}}
```

- 404 `{"error": "no book with ISBN ..."}` when the catalog does not know the ISBN.
- 503 `{"error": "catalog unavailable"}` or `{"error": "pricing unavailable"}` when catalog or pricing fails or does not answer in time.
- `"stock": null` or `"reviews": null` when stock or reviews fails or does not answer in time; the rest of the page is shown as usual.

## Layout

- `storefront/http.py`: a small HTTP client for the backends (`get_json`, `BackendError`).
- `storefront/backends.py`: `Backends` (their addresses), one function per backend, and how long we wait for each.
- `storefront/book_page.py`: `book_page()`, which puts the page together, and `BookNotFound` and `PageUnavailable`.
- `storefront/server.py`: the HTTP server, which maps `book_page()` and its errors to responses.
- `tests/`: unit tests; `tests/fakes.py` stands in for the backends.

## Tests

```bash
python3 -m unittest
```
