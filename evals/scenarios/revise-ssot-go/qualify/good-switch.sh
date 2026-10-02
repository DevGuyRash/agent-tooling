# Alternative (must pass): internal/charges written as one switch over named band figures (topA ... topF),
# labels built from the same constants; the comparison edit is the switch's cases turned all at once.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply good-switch
finish "internal/charges works the band out in one switch over named figures; the quote, letters, and forecast use it."
