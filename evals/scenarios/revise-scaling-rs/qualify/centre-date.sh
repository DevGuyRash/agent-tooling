# Known limit (passes, though still quadratic): references fixed as the reference fixes them; find_clashes
# compares every pair of bookings of the same centre on the same date (facility codes normalized once). Like
# by-date, its work grows with the square of the facilities per centre, which grow with the city, but its
# constant is about fourteen times smaller, so at 2.4 million bookings it costs only about 1.4 times the
# reference's CPU time and grows well within the growth bound. Recorded so the limit is on the record: the
# scaling check catches grouping coarser than a facility's day only when its constant brings it near the CPU
# bound.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply "$TRIAL_SCENARIO_DIR/hidden/reference" "$Q/solutions/centre-date"
finish "Clashes are only looked for among bookings of the same centre on the same date now, facility codes are normalized once, and references use a HashMap. Output unchanged, tests pass."
