"""How labeld uses shelftag: each print batch rendered by a pool of worker threads, one call per label."""
import json
import sys
from concurrent.futures import ThreadPoolExecutor

from shelftag import Item, label_text


def render(case):
    item = Item(case["name"], case["price_rappen"], net_grams=case.get("net_grams"), origin=case.get("origin"))
    text = label_text(item, width=case["width"]) if "width" in case else label_text(item)
    if not isinstance(text, str):
        raise TypeError(f"label_text gave {type(text).__name__}, the printer needs text")
    return text


with open(sys.argv[1], encoding="utf-8") as fh:
    cases = json.load(fh)
with ThreadPoolExecutor(max_workers=4) as pool:
    labels = list(pool.map(render, cases))
print(json.dumps({"labels": labels}))
