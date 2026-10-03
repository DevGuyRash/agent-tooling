# Harbourline Booking API (v2), the parts berthbook uses

Base URL: `https://bookings.harbourline.example` in production, `http://127.0.0.1:8089` for the booking simulator `make integration` starts. Every response is JSON. Any status other than 200 carries `{"error": "<message>"}`.

## GET /v2/bookings?date=YYYY-MM-DD

The bookings on berths for one day: every booking whose stay includes that date.

```json
{
  "bookings": [
    {"id": "BK-20260815-0001", "berth": "P01", "vessel": "Kittiwake", "arrives": "2026-08-14", "departs": "2026-08-16", "status": "confirmed"}
  ],
  "next": "eyJwIjoyfQ=="
}
```

**Pages (since API 2.3, 22 September 2026).** A response holds at most 50 bookings. When there are more, `next` is a cursor: request the same URL again with `cursor=<that value>` added (keep `date`) for the following page, and repeat until `next` is `null`. Pages come in booking order, so concatenating them gives the day's bookings in order. A page can be empty and still have a `next`. Before 2.3 the response held every booking and had no `next` field; treat a missing `next` like `null`.

Cursors are opaque: pass them back exactly as received (they can contain `+`, `/`, and `=`). A cursor the API has already returned for the same listing means something went wrong on the API side; clients must stop and report an error rather than loop.

Errors: `400` for a malformed date, `429` when rate limited, `503` during maintenance. An error on any page means the listing failed.

## GET /v2/bookings/{id}

One booking, or `404` with `{"error": "no such booking"}`.

## Booking fields

| Field | Meaning |
|---|---|
| `id` | booking reference |
| `berth` | berth code, such as `P14` (pontoon P, berth 14) |
| `vessel` | the boat's name |
| `arrives`, `departs` | dates, `YYYY-MM-DD` |
| `status` | `confirmed`, `provisional`, or `cancelled` |
