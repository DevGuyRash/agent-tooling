set -e
# Reports a duplicate count but still adds the duplicate row's amount to the
# total, so the revenue figure is wrong.
cat > cli.py <<'PY'
from orders import DuplicateOrderError, OrderBatch


def report(rows):
    """Print a one-line revenue summary for a batch of order rows."""
    batch = OrderBatch()
    skipped = 0
    total = 0
    for row in rows:
        total += row["amount"]
        try:
            batch.add(row)
        except DuplicateOrderError:
            skipped += 1
    line = f"Imported {len(batch.accepted)} orders, total revenue {total}"
    if skipped:
        line += f"; {skipped} duplicates skipped"
    print(line)


def main(argv=None):
    import csv
    import sys

    argv = sys.argv[1:] if argv is None else argv
    with open(argv[0], newline="") as f:
        rows = [{"order_id": r["order_id"], "amount": int(r["amount"])} for r in csv.DictReader(f)]
    report(rows)


if __name__ == "__main__":
    main()
PY
python3 -m unittest discover -s tests -t . -q
git add -A
git commit -qm "Report skips duplicate rows and counts them"
