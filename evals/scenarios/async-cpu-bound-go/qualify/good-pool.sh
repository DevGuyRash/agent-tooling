# Reference behavior (must pass, over-built): allocation and carts in sequence as the reference does, but the
# carts' pick lists are sorted by a pool of CPU-count worker goroutines in place, and the two files are read
# at the same time. Right and deterministic; the measures show the machinery.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply good-pool
finish "pickctl waves: the morning's carts, sorted in parallel" "Added \`pickctl waves\` per docs/waves.md. Allocation and carts follow the sequence; the per-cart sorting runs on a worker pool sized to the CPUs and the two files load concurrently. Tests pass."
