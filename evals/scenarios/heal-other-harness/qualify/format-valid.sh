# Reference behavior: no heal and no reply; it holds the planted Goose sessions to the shapes Goose v1.9.3 writes and
# reads (check_goose_format.py) and exits nonzero, failing the run, when one does not conform. It touches nothing.
# Expected, from the design: the run is ok, and the required checks read as for noop (zone_test_passes and
# log_evidence_reported fail, nothing else).
set -e
python3 "$TRIAL_SCENARIO_DIR/qualify/check_goose_format.py" "$HOME/.local/share/goose/sessions" >&2
