# Shared by the reference behaviors: lay the reference Go solution (hidden/reference_go) and then any named
# solution directories over the working tree, list the command in the README, commit, leave a final message.
# Usage: . common.sh; apply [NAME...]; finish "commit subject" "final message"
Q="$TRIAL_SCENARIO_DIR/qualify"
apply() {
  cp -R "$TRIAL_SCENARIO_DIR/hidden/reference_go/." .
  for name in "$@"; do
    cp -R "$Q/solutions/$name/." .
  done
  python3 - <<'PY'
from pathlib import Path
p = Path("README.md")
t = p.read_text()
p.write_text(t.replace("./pickctl check ORDERS.csv STOCK.csv   # the night's orders against the stock count: unknown SKUs\n",
                       "./pickctl check ORDERS.csv STOCK.csv   # the night's orders against the stock count: unknown SKUs\n"
                       "./pickctl waves ORDERS.csv STOCK.csv   # the morning's carts and pick lists (docs/waves.md)\n"))
PY
}
finish() {
  git add -A
  git commit -q -m "$1"
  printf '%s\n' "$2" > "$TRIAL_JOB_DIR/final-0.md"
}
