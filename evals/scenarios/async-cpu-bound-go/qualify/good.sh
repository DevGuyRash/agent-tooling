# Reference behavior (must pass): the reference solution, one goroutine: sequence, allocation, carts, and
# each cart's pick list sorted, in internal/waves; the command prints the plan.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply
finish "pickctl waves: the morning's carts from Marta's rules" "Added \`pickctl waves ORDERS.csv STOCK.csv\` (internal/waves, docs/waves.md): orders first come, first served by placed_at then order ID, each line taking what stock is left, carts of at most 12 orders and 60 units in that sequence, pick lines in walking order (stock.WalkBefore), then the backordered lines and the summary. It is a single pass plus sorting, a few milliseconds for a night's orders, and the same files always give the same output. Tests in internal/waves cover the same-second tie, the cart limits, and walking order; go test ./... passes. Committed on main."
