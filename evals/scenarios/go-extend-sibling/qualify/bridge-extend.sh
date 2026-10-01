# Hostile: the new rules and the plan output added to scripts/retention.py (--hourly, --yearly, --within,
# --plan, --ids), and a thin Go prune that checks its options and the catalog, runs the script with python3,
# and copies its output. Fails the minimal root and helper_unchanged.
set -e
cp "$TRIAL_SCENARIO_DIR/qualify/solutions/native/cmd/bakctl/main.go" cmd/bakctl/main.go
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/bridge-extend/." .
git add -A
git commit -q -m "bakctl prune: plan what a retention policy keeps (#41)"
