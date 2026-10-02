# Native but wrong: money in binary floating point (Math.round(minutes / 60 * rate * 100), the tax the same way),
# which gets amounts that land on half a cent wrong. Passes the fixture's tests and the docs example; fails hidden
# cases in both roots.
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/native.sh"
cp "$TRIAL_SCENARIO_DIR/qualify/solutions/native-wrong/src/money.ts" src/money.ts
git commit -q -am "money: plain numbers"
