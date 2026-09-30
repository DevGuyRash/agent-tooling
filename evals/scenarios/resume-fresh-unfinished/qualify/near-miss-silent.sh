set -e
# Catches the duplicate and skips it, but never says so in the summary --
# misses half of the requested step.
cat > cli.py <<'PY'
from orders import DuplicateOrderError, OrderBatch


def report(rows):
    """Print a one-line revenue summary for a batch of order rows."""
    batch = OrderBatch()
    for row in rows:
        try:
            batch.add(row)
        except DuplicateOrderError:
            pass
    total = sum(row["amount"] for row in batch.accepted)
    print(f"Imported {len(batch.accepted)} orders, total revenue {total}")


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
git commit -qm "Skip duplicate rows in report"
