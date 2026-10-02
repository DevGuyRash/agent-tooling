"""`shopcrm dedupe`: the export with one row per person (docs/dedupe.md).

Rows are read straight from the CSV as tuples. Each normalized email and phone number maps to the group
that holds it; when a row ties two groups together, the smaller group is folded into the larger one, so no
row moves more than log2(rows) times."""

import csv

from .contacts import COLUMNS, ExportError, normalize_email, normalize_phone
from .money import format_money, parse_money

ID, CREATED, FIRST, LAST, EMAIL, PHONE, ORDERS, SPENT, MARKETING = range(9)


def _rows(path):
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        if tuple(next(reader, ())) != COLUMNS:
            raise ExportError(f"{path}: not a customer export (expected the header {','.join(COLUMNS)})")
        for row in reader:
            yield (int(row[ID]), *row[1:])


def dedupe(path, out):
    group_of = {}   # key -> group (a list of rows)
    groups = []
    for row in _rows(path):
        mine = [row]
        groups.append(mine)
        for key in (("e", normalize_email(row[EMAIL])), ("p", normalize_phone(row[PHONE]))):
            if not key[1]:
                continue
            other = group_of.get(key)
            if other is None:
                group_of[key] = mine
                continue
            if other is mine:
                continue
            big, small = (other, mine) if len(other) >= len(mine) else (mine, other)
            big.extend(small)
            for r in small:
                for k in (("e", normalize_email(r[EMAIL])), ("p", normalize_phone(r[PHONE]))):
                    if k[1] and group_of.get(k) is small:
                        group_of[k] = big
            small.clear()
            mine = big
    people = []
    for g in groups:
        if g:
            g.sort(key=lambda r: (r[CREATED], r[ID]))
            people.append(g)
    people.sort(key=lambda g: (g[0][CREATED], g[0][ID]))
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow((*COLUMNS, "merged_ids"))
    for g in people:
        oldest = g[0]
        writer.writerow((
            oldest[ID], oldest[CREATED], oldest[FIRST], oldest[LAST],
            next((r[EMAIL] for r in g if normalize_email(r[EMAIL])), ""),
            next((r[PHONE] for r in g if normalize_phone(r[PHONE])), ""),
            sum(int(r[ORDERS]) for r in g),
            format_money(sum(parse_money(r[SPENT]) for r in g)),
            g[-1][MARKETING],
            " ".join(str(r[ID]) for r in g[1:]),
        ))
