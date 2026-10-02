# Alternative (must pass): no new package; internal/quote keeps the rule, exported (Bands, Charge), and the
# renewal letters and the forecast import it.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply good-quote
finish "internal/quote now holds the 2027/28 charges and exports them; the renewal letters and the forecast charge from it."
