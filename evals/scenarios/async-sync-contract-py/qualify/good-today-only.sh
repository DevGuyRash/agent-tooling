# Reference behavior (must pass): good, except that a rate fxd dates other than today (UTC, the machines' zone)
# counts as no rate, a reading of the ticket's "today's rate" that docs/fxd.md's dated reply allows.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply good today-only
finish "Labels: euro price from fxd under the franc price" "Labels show the euro price under the franc price at today's rate from fxd; a rate fxd dates for another day is treated as no rate, and the label prints as before. label_text keeps its signature. Tests pass."
