"""orders: customer orders. SPEC.md section 2."""
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


def find(doc, order_id):
    if order_id not in doc["orders"]:
        raise Fail(f"no such order {order_id}")
    return doc["orders"][order_id]


def cmd_place(doc, args):
    if len(args) < 2:
        raise Fail("usage: orders place CUSTOMER SKU:QTY [SKU:QTY ...]", 2)
    customer, lines = args[0], []
    for spec in args[1:]:
        sku, colon, qty = spec.partition(":")
        if not colon or not sku:
            raise Fail(f'bad line "{spec}": expected SKU:QTY', 2)
        lines.append({"sku": sku, "qty": quantity(qty)})
    order_id = doc["next"]
    doc["next"] = order_id + 1
    doc["orders"][str(order_id)] = {"customer": customer, "lines": lines, "status": "open"}
    return f"placed order {order_id} for {customer}", True


def cmd_show(doc, args):
    if len(args) != 1:
        raise Fail("usage: orders show ID", 2)
    order = find(doc, args[0])
    rows = [f"order {args[0]} {order['customer']} {order['status']}"]
    rows += [f"  {line['sku']} x{line['qty']}" for line in order["lines"]]
    return "\n".join(rows), False


def cmd_cancel(doc, args):
    if len(args) != 1:
        raise Fail("usage: orders cancel ID", 2)
    order = find(doc, args[0])
    if order["status"] == "cancelled":
        raise Fail(f"order {args[0]} is already cancelled")
    if order["status"] == "shipped":
        raise Fail(f"order {args[0]} has shipped")
    order["status"] = "cancelled"
    return f"cancelled order {args[0]}", True


def cmd_list(doc, args):
    status = None
    if args:
        if len(args) != 2 or args[0] != "--status":
            raise Fail("usage: orders list [--status STATUS]", 2)
        status = args[1]
        if status not in ("open", "shipped", "cancelled"):
            raise Fail(f"unknown status {status}", 2)
    rows = []
    for order_id in sorted(doc["orders"], key=int):
        order = doc["orders"][order_id]
        if status is None or order["status"] == status:
            n = len(order["lines"])
            rows.append(f"{order_id} {order['customer']} {order['status']} {n} {'line' if n == 1 else 'lines'}")
    return "\n".join(rows), False


# Not yet implemented: ship (SPEC.md 2.5).
COMMANDS = {"place": cmd_place, "show": cmd_show, "cancel": cmd_cancel, "list": cmd_list}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    data = None
    if argv[:1] == ["--data"] and len(argv) >= 2:
        data, argv = argv[1], argv[2:]
    if not argv or argv[0] not in COMMANDS:
        print(f"error: usage: orders [--data DIR] {{{'|'.join(COMMANDS)}}} ...", file=sys.stderr)
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
