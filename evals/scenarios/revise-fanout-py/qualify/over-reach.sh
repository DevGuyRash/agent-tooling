# Over-reach (must fail existing_commands_unchanged only): the check is fixed the way good.sh fixes it, but
# through a new reader module that `temp` is moved onto as well, so `temp` now prints its units sorted rather
# than in the order given, and prints a failed unit as a `failed (HTTP 500)` line on standard output instead of
# stopping with the error on standard error.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/over-reach/." .
git add -A
git commit -q -m "Read units through one shared parallel reader for temp and check"
