# pickctl

The Kestrel Outdoor warehouse's command-line tool for the morning's picking. It reads the web shop's nightly order export and the stock count the night shift takes, both as CSV.

```bash
go build -o pickctl ./cmd/pickctl

./pickctl stock STOCK.csv              # the stock count in walking order: bin, SKU, units on hand
./pickctl check ORDERS.csv STOCK.csv   # the night's orders against the stock count: unknown SKUs
```

`testdata/` has a small example of each file. Go 1.22 or newer, standard library only.

## Files

- Orders: `order_id,placed_at,sku,qty`, one row per order line; `placed_at` is RFC 3339 in UTC, as the shop exports it.
- Stock: `sku,bin,on_hand`; each SKU is in one bin, written `A03-12-2` (aisle 3, bay 12, level 2). A bin can hold several SKUs.

## Layout

- `internal/orders`: reading the order export.
- `internal/stock`: reading the stock count; bins and the pickers' walking order.
- `cmd/pickctl`: the commands.
- `docs/`: specifications for planned commands.

## Tests

```bash
go test ./...
```

The packing-room PC runs the build from `main` every morning at 5:30, before the first shift.
