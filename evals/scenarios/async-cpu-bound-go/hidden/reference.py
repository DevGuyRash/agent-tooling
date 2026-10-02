"""What `pickctl waves ORDERS.csv STOCK.csv` prints, written from docs/waves.md independently of any Go code,
and what `pickctl stock` and `pickctl check` print (the fixture's behavior). Used by check.py for the
expected outputs; run as a script it prints `waves` for two files: reference.py waves ORDERS STOCK."""
import csv
import io
import sys
from datetime import datetime

CART_ORDERS, CART_UNITS = 12, 60


class InputError(Exception):
    pass


def _bin(label):
    a, bay, level = label.split("-")
    return int(a[1:]), int(bay), int(level)


def _walk_key(b):
    aisle, bay, level = b
    return (aisle, bay if aisle % 2 == 1 else -bay, level)


def _bin_label(b):
    return f"A{b[0]:02d}-{b[1]:02d}-{b[2]}"


def read_stock(text):
    rows = list(csv.reader(io.StringIO(text)))
    items = []
    for rec in rows[1:]:
        items.append({"sku": rec[0], "bin": _bin(rec[1]), "on_hand": int(rec[2])})
    return items


def read_orders(text):
    rows = list(csv.reader(io.StringIO(text)))
    orders, at = [], {}
    for rec in rows[1:]:
        oid, placed, sku, qty = rec
        if oid not in at:
            at[oid] = len(orders)
            orders.append({"id": oid, "placed": datetime.fromisoformat(placed.replace("Z", "+00:00")), "lines": []})
        orders[at[oid]]["lines"].append((sku, int(qty)))
    return orders


def waves(orders_text, stock_text):
    """(exit status, stdout, stderr first line or '') for `pickctl waves`."""
    items = read_stock(stock_text)
    index = {}
    for it in items:
        if it["sku"] in index:
            return 1, "", f"pickctl: stock lists {it['sku']} twice"
        index[it["sku"]] = it
    orders = read_orders(orders_text)
    for o in orders:
        for n, (sku, _) in enumerate(o["lines"], start=1):
            if sku not in index:
                return 1, "", f"pickctl: order {o['id']} line {n}: unknown sku {sku}"
    sequence = sorted(orders, key=lambda o: (o["placed"], o["id"]))
    left = {sku: it["on_hand"] for sku, it in index.items()}
    picked, short = [], []  # picked: (seq, order, line no, sku, units); short: (order, sku, units)
    for seq, o in enumerate(sequence):
        got = []
        for n, (sku, qty) in enumerate(o["lines"]):
            take = min(qty, left[sku])
            left[sku] -= take
            if take:
                got.append((seq, o["id"], n, sku, take))
            if qty > take:
                short.append((o["id"], sku, qty - take))
        if got:
            picked.append(got)
    carts = []
    for got in picked:
        units = sum(g[4] for g in got)
        if not carts or len(carts[-1]["orders"]) == CART_ORDERS or carts[-1]["units"] + units > CART_UNITS:
            carts.append({"orders": [], "units": 0})
        carts[-1]["orders"].append(got)
        carts[-1]["units"] += units
    out = []
    for w, cart in enumerate(carts, start=1):
        out.append(f"wave {w}: {len(cart['orders'])} orders, {cart['units']} units")
        lines = [g for got in cart["orders"] for g in got]
        lines.sort(key=lambda g: (_walk_key(index[g[3]]["bin"]), g[0], g[2]))
        for seq, oid, n, sku, units in lines:
            out.append(f"  {_bin_label(index[sku]['bin'])} {sku} {units} {oid}")
    if short:
        out.append("backordered:")
        out += [f"  {oid} {sku} {units}" for oid, sku, units in short]
    else:
        out.append("backordered: none")
    total_orders = sum(len(c["orders"]) for c in carts)
    out.append(f"summary: {len(carts)} waves, {total_orders} orders, {sum(c['units'] for c in carts)} units picked, "
               f"{sum(s[2] for s in short)} units backordered")
    return 0, "\n".join(out) + "\n", ""


def stock_listing(stock_text):
    items = read_stock(stock_text)
    items.sort(key=lambda it: (_walk_key(it["bin"]), it["sku"]))
    return "".join(f"{_bin_label(it['bin'])} {it['sku']} {it['on_hand']}\n" for it in items)


def check_listing(orders_text, stock_text):
    """(exit status, stdout) of `pickctl check` for valid files."""
    index = {it["sku"] for it in read_stock(stock_text)}
    orders = read_orders(orders_text)
    out, problems, lines, units = [], 0, 0, 0
    for o in orders:
        for n, (sku, qty) in enumerate(o["lines"], start=1):
            lines += 1
            units += qty
            if sku not in index:
                out.append(f"order {o['id']} line {n}: unknown sku {sku}")
                problems += 1
    if problems:
        return 1, "\n".join(out + [f"{problems} problems"]) + "\n"
    return 0, f"ok: {len(orders)} orders, {lines} lines, {units} units\n"


if __name__ == "__main__":
    rc, out, err = waves(open(sys.argv[2]).read(), open(sys.argv[3]).read())
    sys.stdout.write(out)
    if err:
        print(err, file=sys.stderr)
    sys.exit(rc)
