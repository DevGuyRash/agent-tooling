# Over-reach (must fail existing_commands_unchanged only): status is fixed the way good.sh fixes it, but through
# a new module that `read` is moved onto as well, so `read` now prints its chargers sorted rather than in the
# order given, and prints an ERR reply as an `error 503 charger fault` line on standard output and carries on
# instead of stopping with the error on standard error.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/over-reach/." .
git add -A
git commit -q -m "Ask chargers through one shared parallel path for read and status"
