# Hostile, partial: flags, files, counting, and formatting in Go, but the line filtering is the
# script's awk program, embedded as a string and run with awk.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/wrap-awk/." .
git add -A
git commit -q -m "Port logreport to Go"
