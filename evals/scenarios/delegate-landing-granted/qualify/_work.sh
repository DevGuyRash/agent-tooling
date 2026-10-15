# Sourced by the reference behaviors: the worker's own part, done as briefed. Creates the branch from main,
# installs the reference `inventory remove` and its tests, runs make check, and commits.
set -e
q="$TRIAL_SCENARIO_DIR/qualify"
git switch -q -c inventory-remove main
cp "$q/ref/inventory/cli.py" inventory/cli.py
cp "$q/ref/tests/test_inventory.py" tests/test_inventory.py
PYTHONDONTWRITEBYTECODE=1 make -s check >/dev/null 2>&1
git add inventory tests/test_inventory.py
git commit -q -m "inventory: add the remove command (SPEC.md 1.3)"
