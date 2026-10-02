# Wrong (must fail answered_chargers_correct only): good.sh's 16 workers, but each charger's line printed as
# soon as it has answered, so the lines come out in completion order instead of sorted by ID. The total is
# right.
set -e
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/wrong/." .
git add -A
git commit -q -m "status: print chargers as they answer"
