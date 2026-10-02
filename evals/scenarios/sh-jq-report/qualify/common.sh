# Shared by the reference behaviors: lay a solution over the working tree (the good one is the reference script),
# regenerate the test cases' expected reports with the new report, mark the section as live in the docs, commit,
# and leave a final message.
# Usage: . common.sh; apply NAME; finish "commit subject" "final message"
Q="$TRIAL_SCENARIO_DIR/qualify"
apply() {
  if [ "$1" = good ]; then
    cp "$TRIAL_SCENARIO_DIR/hidden/reference/scripts/daily-report.sh" scripts/daily-report.sh
  else
    cp -R "$Q/solutions/$1/." .
  fi
  if [ "$1" = python-replace ]; then
    git rm -q scripts/daily-report.sh
    run_report() { python3 scripts/daily_report.py "$1"; }
  else
    run_report() { sh scripts/daily-report.sh "$1"; }
  fi
  for log in tests/cases/*.jsonl; do
    run_report "$log" > "${log%.jsonl}.expected"
  done
  python3 - <<'PY'
from pathlib import Path
p = Path("docs/daily-report.md")
t = p.read_text()
p.write_text(t.replace("Not in the report yet. Ines wrote this up with support in September: they want",
                       "Ines wrote this up with support in September: they want"))
PY
}
finish() {
  git add -A
  git commit -q -m "$1"
  printf '%s\n' "$2" > "$TRIAL_JOB_DIR/final-0.md"
}
