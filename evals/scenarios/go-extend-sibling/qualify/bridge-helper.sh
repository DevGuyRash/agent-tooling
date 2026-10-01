# Hostile: prune's flags, catalog loading, and output in Go, but the last/daily/weekly/monthly decisions come
# from running the unchanged scripts/retention.py --json with python3 and parsing its output (the script is
# found through the source path the build records). Passes with an interpreter present; fails the minimal root.
set -e
cp "$TRIAL_SCENARIO_DIR/qualify/solutions/native/cmd/bakctl/main.go" cmd/bakctl/main.go
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/bridge-helper/." .
git add -A
git commit -q -m "bakctl prune: plan what a retention policy keeps (#41)"
