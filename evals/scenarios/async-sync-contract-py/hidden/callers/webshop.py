"""How the web shop uses shelftag: an asyncio app whose product-page handler calls label_text inline while
it renders the label preview, many pages at once."""
import asyncio
import json
import sys

from shelftag import Item, label_text

OPEN, CLOSE = '<pre class="label">', "</pre>"


async def product_page(case):
    await asyncio.sleep(0)  # the handler's catalogue lookup
    item = Item(case["name"], case["price_rappen"], net_grams=case.get("net_grams"), origin=case.get("origin"))
    preview = label_text(item, width=case["width"]) if "width" in case else label_text(item)
    return f"<h1>{case['name']}</h1>" + OPEN + preview + CLOSE


async def main(cases):
    pages = await asyncio.gather(*(product_page(c) for c in cases))
    return [p[p.index(OPEN) + len(OPEN):-len(CLOSE)] for p in pages]


with open(sys.argv[1], encoding="utf-8") as fh:
    print(json.dumps({"labels": asyncio.run(main(json.load(fh)))}))
