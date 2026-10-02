# Picking waves

`pickctl waves ORDERS.csv STOCK.csv` plans the morning's picking from the night's order export and the stock count. It replaces the spreadsheet Marta fills in by hand before the first shift; the rules are hers.

## 1. Who goes first

Orders are served first come, first served: by `placed_at`, earliest first. Orders placed in the same second go by order ID, compared as text.

## 2. What each order gets

Going through the orders in that sequence, each line of an order, in the order's own line order, takes as many units of its SKU as are still on the shelf, up to its quantity. Whatever it cannot get is backordered. Stock is shared: what an earlier order takes, a later order cannot.

## 3. Carts

Orders that got at least one unit go onto carts (waves), in the same sequence. A cart holds at most 12 orders and at most 60 units. The next order goes onto the current cart when the cart still has room for it under both limits; otherwise it starts the next cart. So an order of more than 60 units goes on a cart of its own. An order's units here are the units it got, not the units it asked for. Orders that got nothing go on no cart.

## 4. Pick lines

A cart's pick list has one line per order line that got units, in walking order of the bins: the order `pickctl stock` lists them in (aisle by aisle, up the odd aisles and down the even ones, lower levels first; see `stock.WalkBefore`). Lines at the same bin go by the orders' sequence, then by line order within an order.

## 5. Output

Each cart: a `wave N: O orders, U units` line, then its pick lines, each indented by two spaces: bin, SKU, units, order ID, separated by single spaces. Then the backordered lines: order ID, SKU, and units short, in the orders' sequence and then line order, under `backordered:`; when nothing is short, the single line `backordered: none`. Last, `summary: W waves, O orders, U units picked, B units backordered`, where O counts the orders on carts. Counts are printed as they are (`1 waves`), as `pickctl check` does. Exit status 0.

With the files in `testdata/`:

```
$ pickctl waves testdata/orders.csv testdata/stock.csv
wave 1: 4 orders, 13 units
  A01-03-1 TENT-2P 1 K-104251
  A01-03-1 TENT-2P 2 K-104262
  A02-11-1 HEADLAMP 2 K-104233
  A02-11-1 MUG-TI 2 K-104251
  A02-07-2 STOVE-MINI 1 K-104233
  A02-07-2 STOVE-MINI 1 K-104240
  A03-02-3 PAD-XL 1 K-104262
  A03-14-1 BAG-0C 1 K-104262
  A04-05-2 POLES-CF 2 K-104240
backordered:
  K-104240 STOVE-MINI 1
summary: 1 waves, 4 orders, 13 units picked, 1 units backordered
```

K-104233 and K-104240 were placed in the same second, so K-104233 goes first and gets the first of the two stoves.

## Errors

As in `pickctl check`: an order line whose SKU is not in the stock count, or a SKU listed twice in it, is an error: `pickctl: ` and the problem on standard error, nothing on standard output, exit status 1. So are files that cannot be read. Wrong arguments print the usage on standard error and exit 2.
