# Sourced by the reference behaviors: helpers over _edit.py, which edits the working directory.
set -e
q="$TRIAL_SCENARIO_DIR/qualify"
edit() { python3 "$q/_edit.py" "$@"; }
add_tests() { for f in "$@"; do cp "$q/ref/tests/$f" "tests/$f"; done; }
run_check() { PYTHONDONTWRITEBYTECODE=1 make -s check >/dev/null 2>&1 || true; }
