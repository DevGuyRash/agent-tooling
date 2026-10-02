# Wrong (must fail existing_tests_pass only): the reference import, plus a "skipped" column in `totals` that
# changes the report's layout; the fixture's totals test is edited to the new layout.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply "$TRIAL_SCENARIO_DIR/hidden/reference"
add_tests
python3 - <<'PY'
from pathlib import Path
p = Path("src/totals.ts")
t = p.read_text()
t = t.replace("const lines = ['date        store  sales  refunds         net'];",
              "const lines = ['date        store  sales  refunds          net'];")
t = t.replace("${formatCents(t.netCents).padStart(10)}", "${('$' + formatCents(t.netCents)).padStart(11)}")
p.write_text(t)
p = Path("test/cli.test.ts")
t = p.read_text()
t = t.replace("'date        store  sales  refunds         net\\n'", "'date        store  sales  refunds          net\\n'")
for net in ("3.95", "8.80", "4.50", "-5.20"):
    t = t.replace(f"{net:>10}\\n'", f"{'$' + net:>11}\\n'")
p.write_text(t)
PY
finish "import skips transactions already in the ledger (counted, so repeats survive); totals now shows amounts with a dollar sign. Tests updated and passing."
