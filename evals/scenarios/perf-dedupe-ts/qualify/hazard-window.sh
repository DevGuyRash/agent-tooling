# Hazard (must fail scales_to_nightly_size only): ledger lines from the export's first day on, as strings,
# searched with indexOf and spliced out when matched. Both files are in time order, so each search finds its
# match among the first lines left, but every splice moves the rest of the window: within the CPU bound at both
# sizes (about 6 times the reference's CPU time on the large input), with growth from the small input to the
# large one 5 or more times the reference's.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply "$Q/solutions/hazard-window"
add_tests
finish "import compares the export with the ledger lines from the export's first day on and skips the ones already there, one ledger line per export line. Tests pass."
