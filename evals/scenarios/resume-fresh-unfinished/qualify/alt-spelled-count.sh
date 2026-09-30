set -e
# Alternative-correct: spells the skip count out in words ("two duplicates
# skipped") instead of digits. Expected: pass.
cat > cli.py <<'PY'
from orders import DuplicateOrderError, OrderBatch

_WORDS = {0: "zero", 1: "one", 2: "two", 3: "three"}


def _word(n):
    return _WORDS.get(n, str(n))


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
        noun = "duplicate" if skipped == 1 else "duplicates"
        line += f"; {_word(skipped)} {noun} skipped"
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
git commit -qm "Report spells out the duplicate skip count"

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Finished issue #142's remaining step: `report()` now catches a duplicate per row, skips it, and says how many it skipped, spelled out in words (e.g. "two duplicates skipped") rather than as a digit. Tests still pass.
MSG
