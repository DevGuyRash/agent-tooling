# Hazard (must fail scales_to_city_size only): references fixed as the reference fixes them; find_clashes
# compares every pair of bookings on the same date (facility codes normalized once). A date holds about one
# booking in 300 of the whole export, and the facilities grow with the city, so this is still quadratic, at a
# constant small enough to stay near the CPU bound on the large input (about 10 times the reference's); its
# growth (about 7 times the reference's) fails the growth bound when the CPU bound does not stop it.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply "$TRIAL_SCENARIO_DIR/hidden/reference" "$Q/solutions/by-date"
finish "Clashes are only looked for among bookings on the same date now (bookings are grouped by date first), facility codes are normalized once, and references use a HashMap. Output unchanged, tests pass."
