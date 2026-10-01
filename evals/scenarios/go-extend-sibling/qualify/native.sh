# Native: prune in Go (internal/prune and the prune subcommand), reusing the catalog and size packages.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/native/." .
git add -A
git commit -q -m "bakctl prune: plan what a retention policy keeps (#41)"
