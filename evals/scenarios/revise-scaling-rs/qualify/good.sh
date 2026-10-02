# Reference behavior (must pass): the reference solution (hidden/reference). parse_export keeps the line each
# reference was first accepted on in a HashMap; find_clashes groups bookings by normalized facility and date,
# sorts each group by start time, and pairs each booking with the earlier-starting ones still running, then
# sorts the pairs into export order.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply "$TRIAL_SCENARIO_DIR/hidden/reference"
finish "The clash list finishes on the city export now. Two places compared every booking with every other: find_clashes checked all pairs (normalizing both facility codes, an allocation each, for every pair), and parse_export looked each reference up among all bookings read so far. find_clashes now groups bookings by facility and date, walks each group in start order pairing a booking with the ones still running, and sorts the pairs back into export order; parse_export keeps the first line of each reference in a HashMap. On a generated 2.4M-booking export it takes about 5 s; the list is byte-identical to the old code's on the Kingsgate week and on generated exports of 10k and 20k bookings. Tests pass."
