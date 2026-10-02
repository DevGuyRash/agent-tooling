"""Hidden inputs for async-cpu-bound-go: hand-made cases for the rules in docs/waves.md and generated nights at
the size the ticket gives. Each case is (name, orders CSV text, stock CSV text). Nothing here is written where
the agent works; check.py writes the files into its own scratch directory after building the program."""
import random

ORDERS_HEADER = "order_id,placed_at,sku,qty\n"
STOCK_HEADER = "sku,bin,on_hand\n"

# A small stock count shared by most hand-made cases: odd and even aisles, a bin holding two SKUs, a SKU with
# nothing on the shelf.
STOCK = STOCK_HEADER + "".join(f"{sku},{b},{n}\n" for sku, b, n in [
    ("TENT-2P", "A01-03-1", 6), ("TENT-3P", "A01-08-2", 4), ("STOVE-MINI", "A02-07-2", 3),
    ("HEADLAMP", "A02-11-1", 40), ("MUG-TI", "A02-11-1", 30), ("PAD-XL", "A03-02-3", 5),
    ("BAG-0C", "A03-14-1", 3), ("POLES-CF", "A04-05-2", 10), ("GAS-230", "A04-01-1", 200),
    ("FILTER", "A05-09-4", 0), ("SPORK", "A05-09-1", 100),
])


def _orders(rows):
    return ORDERS_HEADER + "".join(f"{o},{t},{s},{q}\n" for o, t, s, q in rows)


T0 = "2026-09-30T19:02:55Z"


def hand_cases():
    cases = []
    # Four orders in the same second, listed out of ID order, all wanting the three stoves.
    cases.append(("same-second", _orders([
        ("K-200040", T0, "STOVE-MINI", 2), ("K-200007", T0, "STOVE-MINI", 1), ("K-200031", T0, "HEADLAMP", 1),
        ("K-200031", T0, "STOVE-MINI", 2), ("K-200100", T0, "STOVE-MINI", 1)]), STOCK))
    # Placed time decides before the ID does: a later order with a smaller ID.
    cases.append(("time-before-id", _orders([
        ("K-100001", "2026-10-01T04:00:00Z", "BAG-0C", 2), ("K-300000", "2026-09-30T18:00:00Z", "BAG-0C", 2),
        ("K-200000", "2026-09-30T23:59:59Z", "BAG-0C", 2)]), STOCK))
    # Fourteen one-unit orders: twelve on the first cart, two on the next.
    cases.append(("cart-orders", _orders([(f"K-3000{i:02d}", f"2026-09-30T20:{i:02d}:00Z", "GAS-230", 1)
                                          for i in range(14)]), STOCK))
    # Unit limit: 25 + 25 fit, 15 more do not; 61 rides alone; the next order starts another cart.
    cases.append(("cart-units", _orders([
        ("K-400001", "2026-09-30T20:00:00Z", "GAS-230", 25), ("K-400002", "2026-09-30T20:01:00Z", "GAS-230", 25),
        ("K-400003", "2026-09-30T20:02:00Z", "GAS-230", 15), ("K-400004", "2026-09-30T20:03:00Z", "SPORK", 61),
        ("K-400005", "2026-09-30T20:04:00Z", "SPORK", 1), ("K-400006", "2026-09-30T20:05:00Z", "GAS-230", 59),
        ("K-400007", "2026-09-30T20:06:00Z", "GAS-230", 1)]), STOCK))
    # A big order first, then an order that gets nothing (no cart), then a partial line.
    cases.append(("big-first", _orders([
        ("K-500001", "2026-09-30T18:00:00Z", "GAS-230", 70), ("K-500002", "2026-09-30T18:05:00Z", "FILTER", 2),
        ("K-500002", "2026-09-30T18:05:00Z", "TENT-3P", 9), ("K-500003", "2026-09-30T18:06:00Z", "TENT-3P", 3),
        ("K-500003", "2026-09-30T18:06:00Z", "HEADLAMP", 2)]), STOCK))
    # Nothing short.
    cases.append(("none-short", _orders([
        ("K-600001", "2026-09-30T21:00:00Z", "MUG-TI", 2), ("K-600002", "2026-09-30T21:00:01Z", "SPORK", 3)]),
        STOCK))
    # Walking order across aisles, a bin with two SKUs, lines at one bin by sequence and then line order, an
    # order's rows apart in the file.
    cases.append(("walk-and-bins", _orders([
        ("K-700002", "2026-09-30T22:00:00Z", "POLES-CF", 1), ("K-700001", "2026-09-30T21:00:00Z", "MUG-TI", 1),
        ("K-700002", "2026-09-30T22:00:00Z", "MUG-TI", 2), ("K-700001", "2026-09-30T21:00:00Z", "SPORK", 1),
        ("K-700003", "2026-09-30T22:30:00Z", "HEADLAMP", 1), ("K-700002", "2026-09-30T22:00:00Z", "HEADLAMP", 3),
        ("K-700001", "2026-09-30T21:00:00Z", "HEADLAMP", 1), ("K-700003", "2026-09-30T22:30:00Z", "TENT-3P", 1),
        ("K-700001", "2026-09-30T21:00:00Z", "TENT-2P", 1), ("K-700003", "2026-09-30T22:30:00Z", "GAS-230", 1),
        ("K-700002", "2026-09-30T22:00:00Z", "PAD-XL", 1), ("K-700003", "2026-09-30T22:30:00Z", "MUG-TI", 1)]),
        STOCK))
    # The same SKU on two lines of one order, the second short.
    cases.append(("repeat-sku", _orders([
        ("K-800001", "2026-09-30T21:00:00Z", "BAG-0C", 2), ("K-800001", "2026-09-30T21:00:00Z", "PAD-XL", 1),
        ("K-800001", "2026-09-30T21:00:00Z", "BAG-0C", 2)]), STOCK))
    return cases


def error_cases():
    """(name, orders, stock, argv tail or None): each must exit 1 (2 for usage) with nothing on stdout."""
    return [
        ("unknown-sku", _orders([("K-1", T0, "TENT-2P", 1), ("K-1", T0, "KAYAK", 1)]), STOCK),
        ("stock-twice", _orders([("K-1", T0, "TENT-2P", 1)]), STOCK + "TENT-2P,A06-01-1,3\n"),
    ]


def night(orders_count, seed):
    """A generated night: about 160 SKUs over eight aisles (some bins shared, some SKUs scarce), orders in bursts
    so many share a second, listed in no particular order, some orders' rows apart, a few large B2B orders."""
    rng = random.Random(seed)
    skus = [f"SKU-{i:04d}" for i in range(160)]
    bins = [(a, b, lv) for a in range(1, 9) for b in range(1, 21) for lv in range(1, 5)]
    rng.shuffle(bins)
    stock_rows, demand = [], {}
    for i, sku in enumerate(skus):
        b = bins[i] if i % 9 else bins[i - 1]  # every ninth SKU shares its neighbour's bin
        stock_rows.append([sku, f"A{b[0]:02d}-{b[1]:02d}-{b[2]}", None])
        demand[sku] = 0
    popular = skus[:40]
    seconds = sorted(rng.sample(range(0, 11 * 3600), orders_count // 3))
    orders = []
    ids = rng.sample(range(100000, 999999), orders_count)
    for k in range(orders_count):
        t = 18 * 3600 + rng.choice(seconds)
        stamp = (f"2026-09-30T{t // 3600:02d}:{t % 3600 // 60:02d}:{t % 60:02d}Z" if t < 86400 else
                 f"2026-10-01T{(t - 86400) // 3600:02d}:{(t - 86400) % 3600 // 60:02d}:{t % 60:02d}Z")
        n_lines = rng.choice([1, 1, 1, 2, 2, 3, 4, 6])
        big = rng.random() < 0.01
        lines = []
        for _ in range(n_lines):
            sku = rng.choice(popular) if rng.random() < 0.5 else rng.choice(skus)
            qty = rng.randint(15, 40) if big else rng.choice([1, 1, 1, 2, 2, 3, 4])
            demand[sku] += qty
            lines.append((sku, qty))
        orders.append((f"K-{ids[k]}", stamp, lines))
    for row in stock_rows:
        d = demand[row[0]]
        row[2] = max(0, int(d * rng.choice([0.6, 0.85, 1.1, 1.5, 2.0])) - rng.randint(0, 2))
    rows = []
    for oid, stamp, lines in orders:
        rows.append([(oid, stamp, s, q) for s, q in lines])
    # Some orders' rows are moved apart: their last line goes to the end of the file.
    tail = []
    for group in rows:
        if len(group) > 1 and rng.random() < 0.05:
            tail.append(group.pop())
    flat = [r for group in rows for r in group] + tail
    return (_orders(flat), STOCK_HEADER + "".join(f"{s},{b},{n}\n" for s, b, n in stock_rows))


NIGHTS = [("night-3000", 3000, 11), ("night-4000", 4000, 12)]
