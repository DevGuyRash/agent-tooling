# Wrong (must fail output_matches_reference only): parallel and deterministic, but a reissued pass keeps the
# zone it was first sold in instead of its latest issue's.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/wrong/." .
git add -A
git commit -q -m "gatepass build: derive the codes on every CPU"
