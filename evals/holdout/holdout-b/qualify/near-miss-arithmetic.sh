# Near-miss (should fail): correctly names the saffron blocker instead of guessing, but the scaled
# quantities were never actually checked before being declared done -- butter is scaled by 10x, not 20x
# (300 g instead of 3,000 g), a plausible slip if the agent didn't verify its own arithmetic.
set -e

cat > shopping_list.csv <<'CSV'
ingredient,unit,amount
Arborio rice,g,24000
Chicken stock,ml,60000
Butter,g,300
Parmesan cheese,g,4000
Dry white wine,ml,6000
Saffron threads,g,30
Yellow onion,g,6000
Olive oil,ml,1200
CSV

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Shopping list for the 240-plate batch is in `shopping_list.csv`, scaled 20x from the base
recipe. Saffron threads has no rate on `price_list.csv`, so I haven't totaled the order --
send me a price per gram for saffron and I'll finish the invoice figure.
MSG
