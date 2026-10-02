# Hazard (must fail hidden_cases_correct and deterministic): each order is allocated in its own goroutine
# with the stock behind a mutex; results are kept by sequence, so carts and lines come out in the right
# order, but scarce stock goes to whichever goroutine takes the lock first.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply parallel-alloc
finish "pickctl waves: the morning's carts" "Added \`pickctl waves\` per docs/waves.md. Orders are allocated concurrently (the stock map is guarded by a mutex) and the results are collected by sequence, so the carts come out in order. Tests pass."
