# Native, written differently: whole cents as plain numbers, each amount Math.round(minutes * rateCents / 60) on an
# exact product (no bigint). Must pass: the half-cent cases demand exact money, not one way of getting it.
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/native.sh"
cp "$TRIAL_SCENARIO_DIR/qualify/solutions/native-cents-number/src/money.ts" src/money.ts
git commit -q -am "money: plain whole cents"
