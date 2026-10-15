"""billing: invoices and payments. SPEC.md section 3."""
import re
import sys

from . import store


class Fail(Exception):
    def __init__(self, message, code=1):
        super().__init__(message)
        self.code = code


def amount(text):
    if not re.fullmatch(r"[0-9]+\.[0-9]{2}", text):
        raise Fail("amount must look like 12.50", 2)
    whole, cents = text.split(".")
    return int(whole) * 100 + int(cents)


def money(cents):
    return f"{cents // 100}.{cents % 100:02d}"


def cmd_invoice(doc, args):
    if len(args) != 2:
        raise Fail("usage: billing invoice ORDER_ID AMOUNT", 2)
    order_id, total = args[0], amount(args[1])
    if order_id in doc["invoices"]:
        raise Fail(f"order {order_id} is already invoiced")
    doc["invoices"][order_id] = {"total_cents": total, "paid_cents": 0}
    return f"invoiced order {order_id}: {money(total)} due", True


# Not yet implemented: pay, refund, balance (SPEC.md 3.2 to 3.4).
COMMANDS = {"invoice": cmd_invoice}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    data = None
    if argv[:1] == ["--data"] and len(argv) >= 2:
        data, argv = argv[1], argv[2:]
    if not argv or argv[0] not in COMMANDS:
        print(f"error: usage: billing [--data DIR] {{{'|'.join(COMMANDS)}}} ...", file=sys.stderr)
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
