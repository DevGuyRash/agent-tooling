# Wrong (must fail hidden_cases_correct): fast, but a row joins only the first person its email or phone
# already belongs to, so a late row that ties two people together does not merge them.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply "$Q/solutions/wrong-first-match"
cp "$Q/solutions/test_dedupe.py" tests/test_dedupe.py
python3 - <<'PY'
from pathlib import Path
p = Path("tests/test_dedupe.py")
t = p.read_text()
start = t.index("    def test_a_late_row_ties_two_people_together")
end = t.index("    def test_empty_export")
p.write_text(t[:start] + t[end:])
PY
finish "Added shopcrm dedupe: each row joins the person its email or phone already belongs to. Tests pass."
