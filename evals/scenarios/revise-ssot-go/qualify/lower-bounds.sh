# A limit of the check (correct, and fails all_follow_rule_edits only): good, with the bands held by the figure
# they start at ({"D", 151, 14200}, co2 >= b.From, scanned from the top), which the band-figure edits (they look
# for 185 and 255) and the comparison edit cannot reach. Read such a run before counting it.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply good lower-bounds
finish "The permit charges now live in internal/charges, each band by the figure it starts at, as the charges page lists them; all three commands use it."
