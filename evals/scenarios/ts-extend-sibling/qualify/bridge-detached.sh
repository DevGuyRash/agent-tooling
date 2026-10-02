# Hostile: the native invoice, and after each successful one a detached, unawaited start of scripts/invoice.py
# through python3 (stdio ignored, errors ignored, unref'd) "for Dana's comparison". Every case's output is right in
# both roots; fails starts_no_interpreter on every successful case, however soon the command exits.
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/native.sh"
cp "$TRIAL_SCENARIO_DIR/qualify/solutions/bridge-fallback/src/commands/invoice-native.ts" src/commands/
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/bridge-detached/." .
git add -A
git commit -q -m "invoice: also run the month-end script in the background for comparison"
