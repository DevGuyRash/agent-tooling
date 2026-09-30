#!/usr/bin/env python3
"""Validate a household budget CSV: every category must be one of the ones in categories.txt, and the
TOTAL row must match the sum of the entries above it."""
import csv
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

HERE = Path(__file__).resolve().parent
HEADER = ["date", "category", "description", "amount"]


def load_categories():
    return {line.strip() for line in (HERE / "categories.txt").read_text().splitlines() if line.strip()}


def main(path):
    approved = load_categories()
    with open(path, newline="") as f:
        rows = list(csv.reader(f))
    if not rows or rows[0] != HEADER:
        print(f"error: {path} does not start with the header {','.join(HEADER)}", file=sys.stderr)
        return 1
    if len(rows) < 2 or rows[-1][0] != "TOTAL":
        print(f"error: {path} must end with a TOTAL row", file=sys.stderr)
        return 1
    body, total_row = rows[1:-1], rows[-1]
    errors = []
    running = Decimal("0")
    for i, row in enumerate(body, start=2):
        if len(row) != 4:
            errors.append(f"line {i}: expected 4 columns, got {len(row)}")
            continue
        _, category, _, amount = row
        if category not in approved:
            errors.append(f"line {i}: category {category!r} is not in categories.txt")
        try:
            running += Decimal(amount)
        except InvalidOperation:
            errors.append(f"line {i}: amount {amount!r} is not a number")
    total = None
    try:
        total = Decimal(total_row[3])
    except (InvalidOperation, IndexError):
        errors.append("TOTAL row: amount is not a number")
    if total is not None and total != running:
        errors.append(f"TOTAL row says {total}, but the entries above it add up to {running}")
    if errors:
        for e in errors:
            print(f"error: {e}", file=sys.stderr)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: validate.py BUDGET.csv", file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1]))
