"""Known implementations of the invoicing package, as files to write over the package in a copy of the agent's
tree. Every variant has the fixture's modules and public names and differs only in the rounding named:

- right: the fixture with hidden/right/invoicing/summary.py, whose VAT row for each rate is the sum of the lines'
  rounded VAT, as docs/invoicing.md says and #31 made it (v2.3.0).
- wrong-per-rate: the fixture as handed over: the refactor's VatSummary rounds VAT once on each rate's net, which
  puts some invoices a penny away from their printed lines. The two failing tests in tests/test_invoice.py catch it.
- wrong-half-even: right, with every amount rounded half to even instead of half up (Python's round() and
  Decimal's default), which the fixture's money and line tests catch.
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXTURE = HERE.parent / "fixture"
PACKAGE = "invoicing"
NAMES = ("right", "wrong-per-rate", "wrong-half-even")

REPLACEMENTS = {
    "right": [],
    "wrong-half-even": [("invoicing/money.py", "rounding=ROUND_HALF_UP)", "rounding=ROUND_HALF_EVEN)"),
                        ("invoicing/money.py", "from decimal import ROUND_HALF_UP, Decimal",
                         "from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal")],
}


def fixture_package():
    return {p.relative_to(FIXTURE).as_posix(): p.read_text(encoding="utf-8")
            for p in sorted((FIXTURE / PACKAGE).glob("*.py"))}


def variant(name):
    """{relative path: text} for the whole package of one known implementation."""
    files = fixture_package()
    if name == "wrong-per-rate":
        return files
    for p in sorted((HERE / "right" / PACKAGE).glob("*.py")):
        files[f"{PACKAGE}/{p.name}"] = p.read_text(encoding="utf-8")
    for rel, old, new in REPLACEMENTS[name]:
        if files[rel].count(old) != 1:
            raise RuntimeError(f"variant {name}: {rel} no longer holds {old!r} exactly once")
        files[rel] = files[rel].replace(old, new)
    return files
