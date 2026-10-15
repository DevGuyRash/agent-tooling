"""inventory: stock levels per SKU. SPEC.md section 1."""
import sys

from . import store


class Fail(Exception):
    def __init__(self, message, code=1):
        super().__init__(message)
        self.code = code


def quantity(text):
    if not (text.isascii() and text.isdigit()) or int(text) < 1:
        raise Fail("quantity must be a positive integer", 2)
    return int(text)


def cmd_add(doc, args):
    if len(args) != 2:
        raise Fail("usage: inventory add SKU QTY", 2)
    sku, qty = args[0], quantity(args[1])
    items = doc["items"]
    items[sku] = items.get(sku, 0) + qty
    return f"added {qty} {sku}, {items[sku]} in stock", True


def cmd_stock(doc, args):
    if len(args) > 1:
        raise Fail("usage: inventory stock [SKU]", 2)
    items = doc["items"]
    if args:
        if args[0] not in items:
            raise Fail(f"unknown SKU {args[0]}")
        return f"{args[0]} {items[args[0]]}", False
    return "\n".join(f"{sku} {items[sku]}" for sku in sorted(items)), False


def cmd_remove(doc, args):
    if len(args) != 2:
        raise Fail("usage: inventory remove SKU QTY", 2)
    sku, qty = args[0], quantity(args[1])
    items = doc["items"]
    if sku not in items:
        raise Fail(f"unknown SKU {sku}")
    if qty > items[sku]:
        raise Fail(f"only {items[sku]} of {sku} in stock")
    items[sku] -= qty
    return f"removed {qty} {sku}, {items[sku]} left", True


COMMANDS = {"add": cmd_add, "stock": cmd_stock, "remove": cmd_remove}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    data = None
    if argv[:1] == ["--data"] and len(argv) >= 2:
        data, argv = argv[1], argv[2:]
    if not argv or argv[0] not in COMMANDS:
        print(f"error: usage: inventory [--data DIR] {{{'|'.join(COMMANDS)}}} ...", file=sys.stderr)
        return 2
    directory = store.data_dir(data)
    doc = store.load(directory)
    try:
        message, changed = COMMANDS[argv[0]](doc, argv[1:])
    except Fail as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.code
    if changed:
        store.save(directory, doc)
    if message:
        print(message)
    return 0
