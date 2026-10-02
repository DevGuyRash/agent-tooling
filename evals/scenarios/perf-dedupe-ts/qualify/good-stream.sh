# Alternative good behavior (must pass), written differently: reads the ledger in 1 MiB chunks without
# parsing it, counts only the lines dated from the export's first day on as raw strings, and never builds
# the ledger's rows.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply "$Q/solutions/good-stream"
add_tests
document
finish "import now reads the ledger in chunks and counts the lines from the export's first day on, then appends only export lines beyond those counts. Tests added and passing."
