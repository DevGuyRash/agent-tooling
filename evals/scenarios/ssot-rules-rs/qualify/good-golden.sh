# Reuse, with a golden file (must pass): good, plus crates/startline/testdata/autumn-1.pursuit (the pursuit
# table for races/2026-09-13-autumn-1.race, eight classes and so eight of the sixteen numbers) and
# crates/startline/tests/golden.rs, which compares the command's output with it. Only a test reads it.
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/good.sh"
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/golden/." .
git add -A
git commit -q -m "startline: golden test for the autumn-1 pursuit table"
