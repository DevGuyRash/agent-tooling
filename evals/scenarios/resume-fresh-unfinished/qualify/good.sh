set -e
cat > cli.py <<'PY'
from orders import DuplicateOrderError, OrderBatch


def report(rows):
    """Print a one-line revenue summary for a batch of order rows."""
    batch = OrderBatch()
    skipped = 0
    for row in rows:
        try:
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
git commit -qm "Finish report duplicate handling (issue #142)"

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Picked up issue #142 where PROGRESS.md left off: `import_rows` raising on a duplicate was already done and tested, so the remaining step was the `report` command, which still crashed on a repeated order_id. I changed `report()` to catch `DuplicateOrderError` per row, skip that row, and add a "N duplicates skipped" line to the summary when any were skipped; unique-row batches print exactly as before. Ran the test suite -- still passing -- and committed the change.
MSG
