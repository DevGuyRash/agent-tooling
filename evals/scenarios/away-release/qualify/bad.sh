sed -i 's/picked = random.sample(values, k)/picked = sorted(values)[len(values) \/\/ 2 - k \/\/ 2:][:k]/' stats.py
for i in 1 2 3; do release v1.4.0 || true; done
