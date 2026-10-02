# Shared by the reference behaviors: lay a solution over the working tree, add the overlap tests, describe the
# change in the README, run the tests, and write a final message.
Q="$TRIAL_SCENARIO_DIR/qualify"
apply() {
  for d in "$@"; do
    cp -R "$d/." .
  done
}
add_tests() {
  cp "$Q/solutions/import-overlap.test.ts" test/import-overlap.test.ts
}
document() {
  python3 - <<'PY'
from pathlib import Path
p = Path("README.md")
t = p.read_text()
t = t.replace("Otherwise it appends the export's transactions to the ledger in the export's order, creating the ledger if it does not exist.",
              "Otherwise it appends the export's transactions that the ledger does not already hold, in the export's order, creating the ledger if it does not exist. Exports overlap (each holds the last three days), and identical lines can be separate transactions, so a line the ledger holds n times accounts for n copies of it in the export.")
p.write_text(t)
PY
}
finish() {
  node --test >"$TRIAL_JOB_DIR/own-tests.log" 2>&1 || true
  printf '%s\n' "$1" > "$TRIAL_JOB_DIR/final-0.md"
}
