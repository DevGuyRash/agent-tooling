# billing

Pricing, invoices, and the monthly accounting export for Acme Office Supply.

- `billing/invoice.py`: `generate_invoice(order, store)` prices an order, gives it the next invoice number, saves it, and returns the invoice with its printed text.
- `billing/store.py`: invoices on disk, one JSON file each, numbered in sequence.
- `billing/export.py`: the monthly CSV that accounting imports.
- `billing/rates.py`: sales tax by region and loyalty discounts by tier.

```
python3 -m billing invoice examples/order.json --store invoices/
python3 -m billing export 2026-09 --store invoices/
```

Run the tests with `python3 -m unittest`.
