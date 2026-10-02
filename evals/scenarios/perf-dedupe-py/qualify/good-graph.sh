# Alternative good behavior (must pass), written differently: a graph from rows to their normalized email
# and phone, walked with an explicit stack from each unvisited row; dataclass people.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply "$Q/solutions/good-graph"
add_tests
document
finish "Added \`shopcrm dedupe\`: rows are linked to their normalized email and phone, and each person is everything reachable from one row (iterative search, so no recursion limit). Output per docs/dedupe.md; tests added; suite passes."
