# price-sync

Nightly job that fetches the current price of every SKU in the catalog export from the pricing service and writes them to a JSON file that the storefront import picks up.

## Running

```sh
PRICING_URL=https://pricing.internal.example node bin/sync-prices.js data/skus.txt out/prices.json
```

| Variable | Default | Meaning |
|---|---|---|
| `PRICING_URL` | (required) | Base URL of the pricing service |
| `PRICE_SYNC_CONCURRENCY` | `4` | Maximum number of requests in flight to the pricing service |
| `PRICE_SYNC_TIMEOUT_MS` | `10000` | Timeout for each request |

The input file has one SKU per line; blank lines and lines starting with `#` are ignored.

## Behavior

- The pricing team asked us to keep at most 4 requests in flight against their service, and `PRICE_SYNC_CONCURRENCY` is that cap. Requests go through `runWithConcurrency` (`lib/limit.js`), which keeps up to that many running and starts the next one as soon as one finishes.
- Rows in the output file are in the same order as the SKUs in the input file.
- If a request fails (an HTTP error, a timeout, or a malformed response), the job stops sending new requests, lets the requests already in flight finish, and then exits with status 1 and the first error. A failed run does not write the output file, so the storefront keeps the previous prices.

## Development

```sh
npm test
```
