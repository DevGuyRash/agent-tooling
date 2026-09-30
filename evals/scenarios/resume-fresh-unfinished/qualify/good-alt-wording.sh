set -e
cat > cli.py <<'PY'
def report(rows):
    """Print a one-line revenue summary for a batch of order rows."""
    seen = set()
    accepted = []
    skipped = 0
    for row in rows:
        order_id = row["order_id"]
        if order_id in seen:
            skipped += 1
            continue
        seen.add(order_id)
        accepted.append(row)
    total = sum(row["amount"] for row in accepted)
    summary = f"Imported {len(accepted)} orders totalling {total}"
    if skipped:
        summary += f" (skipped {skipped} duplicate order{'s' if skipped != 1 else ''})"
    print(summary)


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
