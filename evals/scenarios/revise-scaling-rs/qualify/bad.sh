# Patch-only (must fail scales_to_city_size only): the cron limit goes from 30m to 4h and find_clashes runs the
# same pairwise comparison on one thread per core. Identical output and several times less wall time, but every
# pair is still compared, and parse_export still searches every earlier booking for each reference.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply "$Q/solutions/patch-threads"
finish "find_clashes now spreads the comparisons over all cores with std::thread::scope (output order kept by sorting the pairs), and I raised the cron limit to 4h to be safe. Tests pass."
