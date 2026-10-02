"""The calling convention: whether label_text is a plain function that hands back the label as text, from
a plain call, from a fresh thread with no event loop, and from inside a running event loop."""
import asyncio
import inspect
import json
import threading

import shelftag
from shelftag import Item

ITEM = Item("Probe", 490, net_grams=200, origin="Schweiz")
res = {}
fn = shelftag.label_text
res["coroutine_function"] = bool(inspect.iscoroutinefunction(fn)
                                 or inspect.iscoroutinefunction(getattr(fn, "__call__", None)))


def kind(value):
    if inspect.isawaitable(value):
        if inspect.iscoroutine(value):
            value.close()
        return "awaitable"
    return "str" if type(value) is str else type(value).__name__


def attempt(call):
    try:
        return kind(call())
    except Exception as exc:  # noqa: BLE001 - every failure is the finding
        return "error: " + repr(exc)[:200]


res["plain"] = attempt(lambda: fn(ITEM))
res["plain_width"] = attempt(lambda: fn(ITEM, width=24))
box = {}
worker = threading.Thread(target=lambda: box.update(result=attempt(lambda: fn(ITEM))))
worker.start()
worker.join(30)
res["thread"] = box.get("result", "error: no result within 30 s")


async def inside():
    return attempt(lambda: fn(ITEM))

try:
    res["in_loop"] = asyncio.run(inside())
except Exception as exc:  # noqa: BLE001
    res["in_loop"] = "error: " + repr(exc)[:200]
print(json.dumps(res))
