# Shared by the reference behaviors: lay a solution over the working tree, list the script in the README,
# commit, and leave a final message.
# Usage: . common.sh; apply NAME; finish "commit subject" "final message"
Q="$TRIAL_SCENARIO_DIR/qualify"
apply() {
  cp -R "$Q/solutions/$1/." .
  python3 - <<'PY'
from pathlib import Path
p = Path("README.md")
t = p.read_text()
p.write_text(t.replace("- `scripts/crew_list.py MEMBERS.csv`: active members by squad, for the noticeboard.\n",
                       "- `scripts/crew_list.py MEMBERS.csv`: active members by squad, for the noticeboard.\n"
                       "- `scripts/boat_hours.py BOATLOG.csv`: each boat's time on the water this season, and which are due for service.\n"))
PY
}
finish() {
  git add -A
  git commit -q -m "$1"
  printf '%s\n' "$2" > "$TRIAL_JOB_DIR/final-0.md"
}
