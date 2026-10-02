"""The feature itself, however it is called: label_text once per case from a plain script, awaiting the
result only when it is awaitable, so the labels can be judged apart from the calling convention."""
import asyncio
import inspect
import json
import sys

from shelftag import Item, label_text


async def _wait(value):
    return await value


with open(sys.argv[1], encoding="utf-8") as fh:
    cases = json.load(fh)
labels, awaited = [], False
for case in cases:
    item = Item(case["name"], case["price_rappen"], net_grams=case.get("net_grams"), origin=case.get("origin"))
    value = label_text(item, width=case["width"]) if "width" in case else label_text(item)
    if inspect.isawaitable(value):
        awaited = True
        value = asyncio.run(_wait(value))
    labels.append(value if isinstance(value, str) else repr(value))
print(json.dumps({"labels": labels, "awaited": awaited}))
