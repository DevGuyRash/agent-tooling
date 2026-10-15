# Alternative (correct): the assignment committed on a branch of the worker's own naming, and the worker is back on main,
# so the working tree is the starting one and the command is found only at the branch's tip (result_state).
set -e
git switch -q -c inventory-remove
. "$TRIAL_SCENARIO_DIR/qualify/_work.sh"
git add inventory tests/test_inventory.py
git commit -q -m "inventory: add the remove command (SPEC.md 1.3)"
git switch -q main
