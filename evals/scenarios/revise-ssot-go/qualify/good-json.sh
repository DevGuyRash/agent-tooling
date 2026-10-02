# Alternative (must pass): the charges in internal/charges/charges.json, in pounds as strings, compiled in with
# //go:embed; value edits land in the JSON, the comparison in charges.go.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply good good-json
finish "The charges are in internal/charges/charges.json (embedded), read by internal/charges, which all three commands use."
