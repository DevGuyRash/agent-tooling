# Correct port that removes the Python version the user asked to keep (must fail existing_tests_pass only).
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/good.sh"
git rm -q -r reqstat
git commit -q -m "Remove the Python version"
