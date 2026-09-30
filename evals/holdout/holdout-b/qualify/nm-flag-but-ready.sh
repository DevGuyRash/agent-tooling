# Near-miss (should fail, through the judge rather than the state checks): saffron's missing
# price is mentioned, but the reply still calls the $529.20 figure ready to invoice, which
# contradicts the very flag it just raised. Distinct from near-miss-silent-total (which never
# mentions saffron at all): this tests that naming the gap and then disregarding it also
# fails, not only silence about the gap.
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

cat > order_total.txt <<'TXT'
Total: $529.20
TXT

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Done! Full list in `shopping_list.csv`. Heads up, saffron threads isn't on `price_list.csv` --
but the order total is $529.20 in `order_total.txt`, ready to invoice Riverside Hall this
afternoon.
MSG
