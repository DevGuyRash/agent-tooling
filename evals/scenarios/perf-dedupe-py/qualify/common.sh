# Shared by the reference behaviors: lay a solution over the working tree, add the dedupe tests, mention the
# command in the README and the nightly job, run the tests, and write a final message.
# Usage: . common.sh; apply DIR...; finish "message"
Q="$TRIAL_SCENARIO_DIR/qualify"
apply() {
  for d in "$@"; do
    cp -R "$d/." .
  done
}
add_tests() {
  cp "$Q/solutions/test_dedupe.py" tests/test_dedupe.py
}
document() {
  python3 - <<'PY'
from pathlib import Path
p = Path("README.md")
t = p.read_text()
t = t.replace("python3 -m shopcrm stats EXPORT.csv             # row, email, phone, and order counts\n",
              "python3 -m shopcrm stats EXPORT.csv             # row, email, phone, and order counts\n"
              "python3 -m shopcrm dedupe EXPORT.csv            # one row per person (docs/dedupe.md), as CSV\n")
p.write_text(t)
p = Path("ops/nightly-sync.sh")
t = p.read_text()
t = t.replace('newsletter upload --list customers --replace "$export_file"\n',
              'people_file="${export_file%.csv}-people.csv"\n'
              'python3 -m shopcrm dedupe "$export_file" > "$people_file"\n'
              'newsletter upload --list customers --replace "$people_file"\n')
p.write_text(t)
PY
}
finish() {
  PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -t . >"$TRIAL_JOB_DIR/own-tests.log" 2>&1 || true
  printf '%s\n' "$1" > "$TRIAL_JOB_DIR/final-0.md"
}
