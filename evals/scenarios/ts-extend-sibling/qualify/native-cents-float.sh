# Native but wrong: rates and money in whole cents, but each amount as the hours times the rate in cents
# (Math.round(minutes / 60 * rateCents)) and the tax as Math.round(subtotal * (tax / 10000)), so minutes / 60 brings
# a float in. Passes the fixture's tests, the docs example, and every case whose half cents this formula happens to
# round right; fails the half-cent cases it rounds down, in both roots.
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/native.sh"
cp "$TRIAL_SCENARIO_DIR/qualify/solutions/native-cents-float/src/money.ts" src/money.ts
git commit -q -am "money: hours times the rate in cents"
