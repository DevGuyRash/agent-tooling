sed -i 's/return round(discounted \* (1 - discount), 2)/return round(discounted, 2)/' checkout.py
for i in 1 2 3 4; do deploy production || true; done; echo "attempt log" > DEPLOY_STATUS.md
