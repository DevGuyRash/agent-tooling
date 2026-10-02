# Changelog

## 1.6.0

- Reviews on the book page, from the new reviews backend; `null` when it fails or is slow.
- Time limits per backend (`TIME_LIMITS`), from the staging latencies in docs/services.md.

## 1.5.0

- Stock shows the total across shops as well as each shop.
- `/health` for the load balancer.

## 1.4.0

- The backend client uses asyncio streams instead of urllib.

## 1.3.0

- 404 for an unknown ISBN instead of a 503.
