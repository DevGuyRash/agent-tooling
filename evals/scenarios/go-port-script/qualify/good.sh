# A native Go port: parsing, filtering, counting, sorting, and formatting in Go (getopts-style flags).
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/good/." .
git add -A
git commit -q -m "Port logreport to Go"
