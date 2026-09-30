set -e
# Reviewer-found near-miss: catches and skips each duplicate per row (the
# structural part is right) but never adds a skip count to the summary --
# misses half of the requested step. Expected: fail (remaining_step_done).
cat > cli.py <<'PY'
from orders import DuplicateOrderError, OrderBatch


def report(rows):
    """Print a one-line revenue summary for a batch of order rows."""
    batch = OrderBatch()
    for row in rows:
        try:
            batch.add(row)
        except DuplicateOrderError:
            print(f"warning: skipping duplicate order {row['order_id']}")
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
git commit -qm "Warn per skipped duplicate row"
