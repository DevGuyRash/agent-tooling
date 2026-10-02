"""How the POS sync uses shelftag: a plain nightly script, one call per item, each label sent to the tills
with its lines joined by " | "."""
import json
import sys

from shelftag import Item, label_text


def item_of(case):
    return Item(case["name"], case["price_rappen"], net_grams=case.get("net_grams"), origin=case.get("origin"))


def main():
    with open(sys.argv[1], encoding="utf-8") as fh:
        cases = json.load(fh)
    sent = []
    for case in cases:
        text = label_text(item_of(case), width=case["width"]) if "width" in case else label_text(item_of(case))
        sent.append(" | ".join(text.splitlines()))
    print(json.dumps({"labels": [s.replace(" | ", "\n") for s in sent]}))


main()
