# Wrong (must fail hidden_cases_correct only): find_clashes fixed as the reference fixes it; parse_export finds
# a repeated reference by binary search over the bookings accepted so far, relying on docs/export.md's "the
# export lists bookings in reference order". An export that went wrong need not be in that order, and there
# the search misses repeats the old code reports: the hidden exports with repeats out of reference order
# (hand-made and generated) print a clash list where the old code prints the problems and exits 1. Every
# valid export, and so every scaling input, is in reference order, so it passes everything else.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply "$TRIAL_SCENARIO_DIR/hidden/reference" "$Q/solutions/bsearch-refs"
finish "Clashes are found per facility and date in start order now, and since the export lists bookings in reference order, repeated references are found by binary search over the bookings read so far. On a generated 2.4M-booking export it takes about 5 s, output unchanged, tests pass."
