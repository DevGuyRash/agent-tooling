# Invoice files

One JSON file per invoice. Amounts, quantities, and rates are strings, so nothing passes through a float:

```json
{
  "number": "HP-2026-0141",
  "date": "2026-09-30",
  "customer": "Northgate Community Kitchen",
  "lines": [
    {"description": "A5 flyers, 500", "quantity": "1", "unit_price": "1.99", "vat_rate": "20"}
  ]
}
```

`vat_rate` is a percentage (20, 5, or 0 for most of our work). A file that breaks these rules stops the command with `invoicing: FILE: problem` and exit status 1.
