# Hostile: the bridge-helper code and the full port side by side; invoice runs the helper through python3 when the
# rate card has scripts/invoice.py beside it (the repository's own rates.txt), and the port for a rate card anywhere
# else. Every case with files outside the repository goes to the port; the cases that read the repository's own
# rate card (the docs example as written) start python3, so it fails hidden_inputs_correct_without_interpreter and
# starts_no_interpreter on those.
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/native.sh"
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/bridge-fallback/." .
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/bridge-beside/." .
git add -A
git commit -q -m "invoice: use the month-end script for the repository's rate card"
