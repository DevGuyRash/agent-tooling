# Alternative good (must pass): no hash maps. parse_export sorts the valid lines by reference to find repeats;
# find_clashes buckets bookings by (date, facility) in a BTreeMap and compares only within a bucket.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply "$Q/solutions/good-buckets"
finish "Clashes are now found within each facility-day only (a BTreeMap of buckets), and repeated references by sorting, so the run is near-linear; output is unchanged on the sample week and generated exports. Tests pass."
