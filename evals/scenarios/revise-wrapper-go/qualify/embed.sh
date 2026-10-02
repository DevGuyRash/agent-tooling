# The script carried in the Go source as a string (cmd/ferry/program.go) and run with python3 -c, so ferry no
# longer needs the scripts directory beside it. Fails the sealed minimal root and the recorded root.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/embed/." .
git add -A
git commit -q -m "punctuality: carry the figures script inside ferry"
