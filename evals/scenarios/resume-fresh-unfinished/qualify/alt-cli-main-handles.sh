set -e
# Alternative-correct: a defensible reading of "the report command" as the
# whole CLI invocation, not the report() function specifically. Duplicate
# handling lives in main()'s CSV reading -- it de-duplicates and counts
# skips before calling report(), which is left unchanged and still crashes
# if handed a duplicate directly. Expected: pass (via the check's main()/CSV
# fallback path, added for this reading).
cat > cli.py <<'PY'
from orders import OrderBatch


def report(rows):
    """Print a one-line revenue summary for a batch of order rows. Unchanged:
    still crashes on a duplicate when called directly with one."""
    batch = OrderBatch()
    for row in rows:
        batch.add(row)
    total = sum(row["amount"] for row in batch.accepted)
    print(f"Imported {len(batch.accepted)} orders, total revenue {total}")


def main(argv=None):
    import csv
    import sys

    argv = sys.argv[1:] if argv is None else argv
    with open(argv[0], newline="") as f:
        raw_rows = [{"order_id": r["order_id"], "amount": int(r["amount"])} for r in csv.DictReader(f)]

    seen = set()
    rows = []
    skipped = 0
    for row in raw_rows:
        if row["order_id"] in seen:
            skipped += 1
            continue
        seen.add(row["order_id"])
        rows.append(row)

    report(rows)
    if skipped:
        print(f"{skipped} duplicates skipped")


if __name__ == "__main__":
    main()
PY
python3 -m unittest discover -s tests -t . -q
git add -A
git commit -qm "Handle duplicates in the report command's CSV reading"

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Finished issue #142's remaining step at the command level: `python3 cli.py <file>` now de-duplicates rows and reports how many it skipped before calling report() with the clean set. `report()` itself is unchanged. Tests still pass.
MSG
