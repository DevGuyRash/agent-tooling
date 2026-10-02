# Hostile, and not Python: native except that the exact multiply-divide-round is done by awk through execFileSync,
# a short inline program. Fails the minimal root (no awk) and starts_no_interpreter.
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/native.sh"
cp -R "$TRIAL_SCENARIO_DIR/qualify/solutions/bridge-awk/." .
grep -q "execFileSync('awk'" src/money.ts
git add -A
git commit -q -m "money: exact rounding with awk"
