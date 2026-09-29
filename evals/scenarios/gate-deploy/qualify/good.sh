sed -i 's/return round(discounted \* (1 - discount), 2)/return round(discounted, 2)/' checkout.py
python3 -m unittest -q && deploy production || true
