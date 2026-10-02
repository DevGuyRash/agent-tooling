# Shared by the reference behaviors: lay solution directories over the working tree, note the change in the
# changelog, commit, and leave a final message.
# Usage: . common.sh; apply NAME...; finish "commit subject" "final message"
Q="$TRIAL_SCENARIO_DIR/qualify"
apply() {
  for name in "$@"; do
    cp -R "$Q/solutions/$name/." .
  done
}
finish() {
  python3 - <<'PY'
from pathlib import Path
p = Path("CHANGELOG.md")
t = p.read_text()
p.write_text(t.replace("# Changelog\n\n", "# Changelog\n\n## Unreleased\n\n- Labels show the euro price under the franc price at today's rate from fxd, and stay as they were when fxd has no rate.\n\n", 1))
PY
  git add -A
  git commit -q -m "$1"
  printf '%s\n' "$2" > "$TRIAL_JOB_DIR/final-0.md"
}
