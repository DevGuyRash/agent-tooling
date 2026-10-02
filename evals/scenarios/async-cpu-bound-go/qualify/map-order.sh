# Nondeterminism without goroutines (must fail hidden_cases_correct and deterministic): backordered lines
# grouped by order in a map and printed by ranging over it, which Go randomizes.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply map-order
finish "pickctl waves: the morning's carts" "Added \`pickctl waves\` per docs/waves.md. Tests pass."
