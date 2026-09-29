# Correct report that reads the README's "empty" literally (COALESCE to '' for no manager and no last
# order) with the full grain tests asserting ''. Review round 1: must pass, and its tests must earn the
# same tests_catch_* credit as good's (the references and mutants are adapted to return '' too).
set -e
Q="$TRIAL_SCENARIO_DIR/qualify"
cp "$Q/sql/good_empty_strings.sql" acctreport/sql/customer_activity.sql
python3 - "$Q/tests/test_activity_grain.py" <<'PY'
import sys
t = open(sys.argv[1]).read()
for old, new in [('"order_count": 0, "revenue_cents": 0, "last_order_date": None})',
                  '"order_count": 0, "revenue_cents": 0, "last_order_date": ""})'),
                 ('(0, 0, None))', '(0, 0, ""))'), ('(None, 1, 9875))', '("", 1, 9875))')]:
    assert old in t, old
    t = t.replace(old, new)
open("tests/test_activity_grain.py", "w").write(t)
PY
python3 -m unittest discover -s tests -t . >/dev/null 2>&1
printf '%s\n' "Fixed the report at customer grain; as the README says, a missing manager or last order is empty (an empty string). Grain tests added." > "$TRIAL_JOB_DIR/final-0.md"
