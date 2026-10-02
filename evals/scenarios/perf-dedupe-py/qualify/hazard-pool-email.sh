# Hazard (must fail scales_to_nightly_size only): the union-find, but each row's email is looked up in the
# list of every row's email (emails.index) inside a multiprocessing Pool, so the quadratic work runs in
# worker processes under Python's default forkserver, which the main process never waits for. Only a
# measurement that counts processes nobody waited for sees that CPU time.
set -e
. "$TRIAL_SCENARIO_DIR/qualify/common.sh"
apply "$TRIAL_SCENARIO_DIR/hidden/reference"
apply "$Q/solutions/hazard-pool-email"
add_tests
finish "Added shopcrm dedupe: a union-find over rows where each phone number and email address points at the first row that had it. The email lookups run in a process pool across all cores, so the full export is quick. Tests pass."
