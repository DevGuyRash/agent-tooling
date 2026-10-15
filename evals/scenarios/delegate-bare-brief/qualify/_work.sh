# Sourced by the reference behaviors: the assignment and nothing else, in the working tree on main: the reference
# `inventory remove` and its tests, with make check run. No branch, no commit, no report: the brief asks for none.
set -e
q="$TRIAL_SCENARIO_DIR/qualify"
cp "$q/ref/inventory/cli.py" inventory/cli.py
cp "$q/ref/tests/test_inventory.py" tests/test_inventory.py
PYTHONDONTWRITEBYTECODE=1 make -s check >/dev/null 2>&1
