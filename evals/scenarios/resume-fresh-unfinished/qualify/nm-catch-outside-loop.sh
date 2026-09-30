set -e
# Reviewer-found near-miss: wraps the whole loop in one try/except instead of
# catching per row, so it stops at the first duplicate instead of skipping
# every one. Expected: fail (remaining_step_done).
cat > cli.py <<'PY'
from orders import DuplicateOrderError, OrderBatch


def report(rows):
    """Print a one-line revenue summary for a batch of order rows."""
    batch = OrderBatch()
    skipped = 0
    try:
        for row in rows:
            batch.add(row)
    except DuplicateOrderError:
        skipped += 1
    total = sum(row["amount"] for row in batch.accepted)
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
git commit -qm "Report stops importing on a duplicate"
