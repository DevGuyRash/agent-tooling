# Alternative (must pass): circdesk/fines.py reads the table and the grace period from docs/fines.md itself at
# run time, so the policy page is the only place the numbers are written.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply good good-docs
finish "circdesk/fines.py reads the fines straight from docs/fines.md, so the policy page is the one place to change them; all three commands use it."
