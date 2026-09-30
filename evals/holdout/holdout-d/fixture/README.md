# Riverbend Bakery — Kitchen Ops

This repo tracks the kitchen's ingredient inventory, suppliers, and the orders placed with them.

- `inventory.csv` — current stock, weekly usage, and the reorder threshold for each ingredient. If `on_hand` is below `reorder_threshold`, it's time to restock before we run out.
- `suppliers.csv` — which supplier we buy each ingredient from, at what price, and their lead time.
- `orders/log.csv` — a running log of orders placed so far.
- `order` — a command-line tool for placing an order with a supplier, e.g. `order --item flour --qty 200 --supplier "Miller & Sons"`.

See `automation/README.md` for how recurring tasks run on the kitchen's ops server.
