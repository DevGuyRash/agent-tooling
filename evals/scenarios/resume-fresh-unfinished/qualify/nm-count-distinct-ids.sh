set -e
# Reviewer-found near-miss: counts distinct duplicated order ids rather than
# the number of rows skipped, so a repeated id that recurs more than once
# undercounts. Expected: fail (remaining_step_done).
cat > cli.py <<'PY'
from orders import DuplicateOrderError, OrderBatch


def report(rows):
    """Print a one-line revenue summary for a batch of order rows."""
    batch = OrderBatch()
    dup_ids = set()
    for row in rows:
        try:
            batch.add(row)
        except DuplicateOrderError:
            dup_ids.add(row["order_id"])
    total = sum(row["amount"] for row in batch.accepted)
    line = f"Imported {len(batch.accepted)} orders, total revenue {total}"
    if dup_ids:
        line += f"; {len(dup_ids)} duplicates skipped"
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
git commit -qm "Report counts distinct duplicated ids"
