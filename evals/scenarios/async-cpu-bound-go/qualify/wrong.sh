# Wrong (must fail hidden_cases_correct only): orders placed in the same second keep their file order instead
# of going by order ID. Deterministic.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply wrong
finish "pickctl waves: the morning's carts" "Added \`pickctl waves\` per docs/waves.md. Tests pass."
