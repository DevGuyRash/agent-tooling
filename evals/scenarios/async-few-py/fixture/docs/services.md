# The backends behind the book page

The book page reads four internal services. Each answers one `GET` per connection with a JSON body and `Connection: close`. Addresses come from `STOREFRONT_CATALOG_URL`, `STOREFRONT_PRICING_URL`, `STOREFRONT_STOCK_URL`, and `STOREFRONT_REVIEWS_URL`.

Latencies below are from the staging dashboards for the last 30 days, measured at our side (connect to last byte).

## catalog

`GET /v1/books/{isbn}` → `{"isbn": "...", "title": "...", "authors": ["..."], "format": "paperback"}`

- 404 for an ISBN it does not know.
- p50 170 ms, p99 about 700 ms (cold cache after a deploy or a big import).
- 5xx during its nightly reindex, briefly.
- We wait up to 1 s. The page cannot be shown without it.

## pricing

`GET /v1/prices/{isbn}` → `{"isbn": "...", "amount": "8.99", "currency": "GBP"}`

- `amount` is a decimal string; we pass it through unchanged.
- p50 190 ms, p99 400 ms. Fails fast (under 50 ms) when its database is unreachable, with a 500 or 503.
- We wait up to 1 s. The page cannot be shown without it: we never show a book without its price.

## stock

`GET /v1/stock/{isbn}` → `{"isbn": "...", "stores": {"Bath": 3, "Bristol": 0}}`

- One entry per shop that has ever stocked the title; the page also shows the total.
- p50 160 ms. When a shop's till system is offline it can hang until the shop comes back.
- We wait up to 300 ms. Without it the page shows no stock (`"stock": null`).

## reviews

`GET /v1/reviews/{isbn}/summary` → `{"isbn": "...", "rating": 4.6, "count": 2210}`

- A wrapper around the third-party reviews provider. p50 230 ms, and it has bad days.
- We wait up to 300 ms. Without it the page shows no reviews (`"reviews": null`).

## Time limits

The waits above are in `storefront/backends.py` (`TIME_LIMITS`). They count from opening the connection to the last byte of the answer, and a backend that has not answered by then counts as failed.
