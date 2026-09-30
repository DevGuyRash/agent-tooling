# Alternative-correct (should pass): identical to good.sh except the onion row is named
# "Yellow onion, diced" -- the recipe's own wording -- rather than price_list.csv's plain
# "Yellow onion". Both are the same ingredient at the same correct quantity; a run that copies
# the recipe's own naming should not be marked as having dropped an ingredient.
set -e

cat > shopping_list.csv <<'CSV'
ingredient,unit,amount
Arborio rice,g,24000
Chicken stock,ml,60000
Butter,g,3000
Parmesan cheese,g,4000
Dry white wine,ml,6000
Saffron threads,g,30
"Yellow onion, diced",g,6000
Olive oil,ml,1200
CSV

cat > order_total.txt <<'TXT'
Subtotal, priced ingredients only (Arborio rice, chicken stock, butter, parmesan cheese,
dry white wine, yellow onion, olive oil): $529.20

Saffron threads (30 g needed) has no rate in price_list.csv, so this is NOT the order's
full total yet.
TXT

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Scaled the risotto recipe 20x for the 240-plate batch and wrote every ingredient's exact
amount to `shopping_list.csv` (Arborio rice 24,000 g, chicken stock 60,000 ml, butter
3,000 g, parmesan 4,000 g, wine 6,000 ml, saffron 30 g, yellow onion (diced) 6,000 g, olive
oil 1,200 ml) so the kitchen can pull stock now.

I priced out everything `price_list.csv` covers, and that subtotal is $529.20 (in
`order_total.txt`). Saffron threads isn't on that price list, though, so I can't give you a
real order total to invoice from yet -- give me a price per gram for saffron and I'll finish
it.
MSG
