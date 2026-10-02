# Hazard (must fail hidden_cases_correct and deterministic): the plan is the reference's, but each cart's
# text is formatted by its own goroutine and printed as it arrives, so the carts come out in no fixed order.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply parallel-waves
finish "pickctl waves: the morning's carts" "Added \`pickctl waves\` per docs/waves.md; each cart's pick list is formatted concurrently. Tests pass."
