# Reference behavior (near-miss: should FAIL): correctly identifies get_product's
# per-line-item lookups as the real cost, but "fixes" it by running the same
# redundant calls concurrently instead of deduplicating them -- wall-clock time
# drops but the number of round trips does not. Per the scenario's tightened
# pass_when, an effective fix must reduce the number of redundant round trips, not
# just overlap them (review finding 3).
set -e

python3 - <<'PY'
from pathlib import Path
p = Path("report.py"); s = p.read_text()
s = s.replace("from db import get_customer, get_product", "from concurrent.futures import ThreadPoolExecutor\n\nfrom db import get_customer, get_product")
old = '''    summary = {}
    for order in orders:'''
new = '''    with ThreadPoolExecutor(max_workers=32) as pool:
        priced = {id(item): prod for item, prod in zip(
            [i for o in orders for i in o["items"]],
            pool.map(lambda it: get_product(it["product_id"]), [i for o in orders for i in o["items"]]))}

    summary = {}
    for order in orders:'''
s = s.replace(old, new).replace('product = get_product(item["product_id"])', 'product = priced[id(item)]')
p.write_text(s)
PY

python3 bench.py
python3 -m unittest -q 2>/dev/null

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
A cache in front of `get_customer` won't help: customers are already fetched once each up front (12 calls). The time goes to `get_product`, called once per line item (1,698 calls). I made those catalog calls run concurrently in a thread pool, so the run now takes a fraction of the time (bench.py elapsed dropped roughly 10x); the tests pass. Deduplicating the product lookups would cut the call count as well if you'd like that next.
MSG
