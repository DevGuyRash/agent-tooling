# Wrong (must fail hidden_cases_correct): fast, but a Set of the ledger's lines drops every copy of a line the
# ledger holds once, losing genuine repeated transactions.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply "$Q/solutions/wrong-set"
cp "$Q/solutions/import-overlap.test.ts" test/import-overlap.test.ts
python3 - <<'PY'
from pathlib import Path
p = Path("test/import-overlap.test.ts")
t = p.read_text()
start = t.index("test('identical lines are counted, not collapsed'")
end = t.index("test('a refund is not the same transaction as the sale'")
p.write_text(t[:start] + t[end:])
PY
finish "import skips any line the ledger already has (a Set of its lines). Tests pass."
