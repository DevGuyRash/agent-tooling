# Over-reach (must fail existing_behavior_kept): the rule consolidated correctly, but in a rewrite of the
# package around a Ledger class whose new export reader drops the byte-order mark handling the library
# system's exports need.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply over-reach
finish "Rewrote circdesk around a Ledger class in circdesk/ledger.py holding the 1 November policy, with a cleaner export reader."
