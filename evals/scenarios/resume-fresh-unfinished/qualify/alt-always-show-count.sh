set -e
# Alternative-correct: always shows the skip count, including "0 duplicates
# skipped" for a batch with none, instead of omitting the clause when there
# is nothing to skip. Expected: pass.
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
    print(f"Imported {len(batch.accepted)} orders, total revenue {total}; {skipped} duplicates skipped")


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
git commit -qm "Report always states the duplicate skip count"

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Finished issue #142's remaining step: `report()` now catches a duplicate per row and skips it, and always states the skip count in the summary, including "0 duplicates skipped" when there are none. Tests still pass.
MSG
