# Surcharge copy (must fail all_follow_rule_edits only): the bands, BandFor, and both surcharge amounts shared
# in internal/charges, but the quote, the renewal letters, and the forecast each add the surcharges themselves,
# so starting the later-permit surcharge at the third permit, made in one place, moves one command.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply good surcharge-copy
finish "The bands and the surcharges are in internal/charges; the quote, the renewal letters, and the forecast use them."
