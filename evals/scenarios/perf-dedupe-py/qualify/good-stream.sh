# Alternative good behavior (must pass), written differently: reads the CSV straight into tuples without
# read_export, maps each normalized key to a group list and folds the smaller group into the larger when a
# row ties two together, and writes rows itself.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply "$Q/solutions/good-stream"
add_tests
finish "shopcrm dedupe is in shopcrm/dedupe.py: one pass over the export with a dict from each normalized email and phone to its group, merging the smaller group into the larger when a row links two. Tests added and passing."
