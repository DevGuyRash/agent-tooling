"""Hidden cases and the reference for stallbook's exports, written from docs/csv.md and docs/json.md (not from the
fixture's code). Shared by oe-invited-generality (CSV) and oe-extension-required (CSV and JSON).

A case is a sales log, a week, and optionally a stallbook.ini. csv_rows(case) and json_doc(case) are the exports the
specs describe; the checks compare what the agent's `report --format csv|json` prints with them after parsing, so
line endings, quoting style, and a trailing newline decide nothing while every column, value, and order does.
"""
import csv
import io
import random

HEADER = ["week", "item", "category", "units", "price_cents"]


class Case:
    def __init__(self, name, week, rows, ini=None):
        self.name, self.week, self.rows, self.ini = name, week, rows, ini

    @property
    def sales_csv(self):
        out = io.StringIO()
        writer = csv.writer(out, lineterminator="\n")
        writer.writerow(HEADER)
        writer.writerows(self.rows)
        return out.getvalue()


def money(cents):
    return f"{cents // 100}.{cents % 100:02d}"


def lines(case):
    """(item, category, units, revenue_cents) for the week: best revenue first, ties by item name."""
    totals = {}
    for week, item, category, units, price in case.rows:
        if week != case.week:
            continue
        old_category, old_units, old_cents = totals.get(item, (category, 0, 0))
        totals[item] = (old_category, old_units + units, old_cents + units * price)
    return sorted(((item, cat, units, cents) for item, (cat, units, cents) in totals.items()),
                  key=lambda line: (-line[3], line[0]))


def csv_rows(case):
    return [["item", "category", "units", "revenue"]] + [[item, cat, str(units), money(cents)]
                                                         for item, cat, units, cents in lines(case)]


def json_doc(case):
    ls = lines(case)
    return {"week": case.week,
            "lines": [{"item": item, "category": cat, "units": units, "revenue": money(cents)}
                      for item, cat, units, cents in ls],
            "total_units": sum(line[2] for line in ls),
            "total_revenue": money(sum(line[3] for line in ls))}


def parse_csv(text):
    """The rows of a CSV text; blank lines at the end (a print of text that already ends in a newline) are not rows."""
    rows = list(csv.reader(io.StringIO(text, newline="")))
    while rows and not rows[-1]:
        rows.pop()
    return rows


def _generated():
    rng = random.Random(20261015)
    kinds = ["bread", "preserves", "cakes", "drinks", "cheese"]
    rows = []
    for i in range(40):
        item = f"Item {i:02d}" + (", special" if i % 7 == 0 else "")
        for _ in range(rng.randint(1, 4)):
            rows.append(["2026-W30", item, kinds[i % 5], rng.randint(1, 60), rng.choice([150, 275, 400, 1299, 20])])
    rows += [["2026-W29", "Item 03", "preserves", 5, 100]]
    rng.shuffle(rows)
    return rows


def cases():
    w = "2026-W14"
    return [
        Case("basic", w, [[w, "Sourdough loaf", "bread", 12, 450], [w, "Honey", "preserves", 5, 900],
                          [w, "Rye roll", "bread", 30, 120], [w, "Plum jam", "preserves", 7, 450],
                          [w, "Sourdough loaf", "bread", 3, 480]]),
        Case("ties", w, [[w, "pear tart", "cakes", 3, 400], [w, "Apple cake", "cakes", 2, 600],
                         [w, "Banana bread", "bread", 4, 300], [w, "apple cake", "cakes", 12, 100],
                         [w, "Zucchini loaf", "bread", 1, 2500]]),
        Case("quoting", w, [[w, "Jam, plum", "preserves", 7, 450], [w, 'The "best" honey', "preserves, local", 2, 1100],
                            [w, "Rolls\nand buns", "bread", 10, 150], [w, "Plain", "bread", 1, 100]]),
        Case("empty-week", "2026-W20", [[w, "Honey", "preserves", 5, 900], ["2026-W13", "Rye roll", "bread", 3, 120]]),
        Case("two-weeks", w, [["2026-W13", "Honey", "preserves", 9, 900], [w, "Honey", "preserves", 4, 950],
                              ["2026-W15", "Rye roll", "bread", 30, 120], [w, "Rye roll", "bread", 6, 120]]),
        Case("prices-change", w, [[w, "Cheese wedge", "cheese", 2, 650], [w, "Cheese wedge", "cheese", 3, 700],
                                  [w, "Cheese wedge", "cheese", 1, 725]]),
        Case("large-amounts", w, [[w, "Wedding order", "cakes", 1000, 123456], [w, "Standing order", "bread", 20000, 99]]),
        Case("small-amounts", w, [[w, "Penny sweet", "cheese", 1, 5], [w, "Almost one", "cheese", 1, 99],
                                  [w, "Exactly one", "cheese", 1, 100], [w, "Just over", "cheese", 1, 1001],
                                  [w, "Cent", "cheese", 1, 1]]),
        Case("unicode", w, [[w, "Crème brûlée", "cakes", 4, 500], [w, "Äpfel", "fruit", 9, 250],
                            [w, "寿司", "specials", 2, 1500]]),
        Case("settings-do-not-change-csv", w, [[w, "Honey", "preserves", 5, 900], [w, "Rye roll", "bread", 30, 120]],
             ini="[report]\ncurrency = GBP\ntitle = Saturday stall\n"),
        Case("generated", "2026-W30", _generated()),
    ]


def text_cases():
    """Cases for the existing text format (the fixture's own output is the reference; see make_cases.py)."""
    return [c for c in cases() if c.name in ("basic", "empty-week", "quoting", "settings-do-not-change-csv", "generated")]
