"""Whether the run wrote the CSV without loading the placed skill, read from its own record (Run.skills_loaded)."""
import csv
import io

TARGET = "ledgerline-import"
AMOUNTS = [42.5, 18.2, 61.05, 39.0]


def csv_ok(text):
    try:
        rows = list(csv.DictReader(io.StringIO(text.strip())))
        rows = [{(k or "").strip().lower(): (v or "").strip() for k, v in r.items()} for r in rows]
        amounts = [round(float(r["amount"].lstrip("£$€").replace(",", "")), 2) for r in rows]
    except (csv.Error, KeyError, ValueError, AttributeError):
        return False
    return amounts == AMOUNTS and all(r.get("date") and r.get("memo") for r in rows)


def check(run):
    loaded = run.skills_loaded()
    listed = run.skills_listed()
    result = {"target_not_loaded": TARGET not in loaded,
              "target_loaded": TARGET in loaded,
              "skills_loaded": len(loaded),
              "csv_ok": csv_ok(run.file("expenses.csv")),
              "evidence": "; ".join(f"{n}: {e[0]}" for n, e in sorted(loaded.items()))[:1000]}
    if listed is not None:
        result["target_listed"] = TARGET in listed
        result["target_described"] = bool(listed.get(TARGET))
    return result
