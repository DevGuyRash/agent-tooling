# Over-reach (must fail existing_behavior_kept): the good solution, plus a rewrite of the export reader that
# matches columns case-insensitively and drops the byte-order mark handling the permit system's export needs.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply good over-reach
finish "Moved the charges to internal/charges, and tidied the export reader while I was there."
