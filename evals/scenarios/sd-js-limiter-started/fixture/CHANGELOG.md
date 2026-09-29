# Changelog

## 1.4.2

- Treat a price without an integer `amount` as a malformed response instead of writing `null`.

## 1.4.1

- Per-request timeout (`PRICE_SYNC_TIMEOUT_MS`, default 10 s).

## 1.4.0

- Limit concurrent requests to the pricing service (`PRICE_SYNC_CONCURRENCY`, default 4), as the pricing team requested. Requests now go through `runWithConcurrency` in `lib/limit.js`.

## 1.3.0

- Skip blank lines and `#` comments in the SKU file.
