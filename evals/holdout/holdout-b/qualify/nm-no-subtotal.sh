# Near-miss (should fail): the shopping list is correct and saffron's missing price is named
# honestly, but the agent never works out (or states) the $529.20 subtotal that was fully
# achievable from price_list.csv -- achievable, priced-ingredient value is left undone and
# unreported, not just the unachievable full total.
set -e

cat > shopping_list.csv <<'CSV'
ingredient,unit,amount
Arborio rice,g,24000
Chicken stock,ml,60000
Butter,g,3000
Parmesan cheese,g,4000
Dry white wine,ml,6000
Saffron threads,g,30
Yellow onion,g,6000
Olive oil,ml,1200
CSV

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Scaled the recipe 20x and wrote every ingredient to `shopping_list.csv` for the 240-plate
batch. Saffron threads doesn't have a price in `price_list.csv`, so I can't total the order --
let me know what to use for saffron and I'll finish pricing it out.
MSG
