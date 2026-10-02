# Shared by the reference behaviors: wire `rebalance` into the CLI as the reference does, lay a solution's
# rebalance.py (and any other files) over the working tree, list the command in the README, commit, and leave a
# final message.
# Usage: . common.sh; apply NAME; finish "commit subject" "final message"
Q="$TRIAL_SCENARIO_DIR/qualify"
apply() {
  cp "$TRIAL_SCENARIO_DIR/hidden/reference/dockops/cli.py" dockops/cli.py
  if [ "$1" = good ]; then
    cp "$TRIAL_SCENARIO_DIR/hidden/reference/dockops/rebalance.py" dockops/rebalance.py
  fi
  cp -R "$Q/solutions/$1/." .
  python3 - <<'PY'
from pathlib import Path
p = Path("README.md")
t = p.read_text()
p.write_text(t.replace("how long they took.\n",
                       "how long they took.\n- `rebalance --from DATE [--to DATE] [--area AREA] [--top N]`: departures and"
                       " arrivals per station over a range of days, most drained first (docs/rebalance.md).\n"))
PY
}
finish() {
  git add -A
  git commit -q -m "$1"
  printf '%s\n' "$2" > "$TRIAL_JOB_DIR/final-0.md"
}
