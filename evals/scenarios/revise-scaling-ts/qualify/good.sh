# Reference behavior (must pass): the reference solution (hidden/reference). dropDuplicates keeps a Set of the
# fields sameTap compares, chargeDay keeps each card's spend and journey start in a Map, and cardDebits keeps
# the debits in a Map (which keeps first-appearance order); one pass each.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply "$TRIAL_SCENARIO_DIR/hidden/reference"
finish "The charge run now finishes on a full day. It had three loops that searched everything before the current tap: dropDuplicates compared each tap with every tap kept so far, chargeDay filtered every earlier charge for the card, and cardDebits searched the debit list for each charge. Each now keeps what it needs as it goes (a Set of the fields that make two taps the same, each card's spend and journey start in a Map, the debits in a Map), so the run is one pass. On a generated 960k-tap day it takes about 9 s of CPU; the old code took 52 s on 60k. Charges, debits and the summary line are byte-identical to the old code's on the pilot day and on generated days of 20k and 60k taps. Tests pass; nothing else changed."
