# nightly-report

Generates the nightly per-customer revenue summary that gets emailed out every
morning.

- `orders_data.py` — tonight's fixed order set.
- `db.py` — the customer and product catalog lookups (`get_customer`, `get_product`); each one stands in for a network round trip to the real service.
- `report.py` — `generate_nightly_report(orders)` builds the summary.
- `bench.py` — runs the report against tonight's orders and prints how many round trips it made and how long that took.
- `tests/` — the existing test suite.

Run it with:

```
python3 bench.py
```
