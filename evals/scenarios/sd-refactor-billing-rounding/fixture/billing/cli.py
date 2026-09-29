"""Command line.

    python3 -m billing invoice ORDER.json --store DIR     price, number, save, and print an invoice
    python3 -m billing export YYYY-MM --store DIR         print the month's accounting CSV
"""
import argparse
import json
import sys
from decimal import Decimal

from .export import export_month
from .invoice import generate_invoice
from .models import Customer, LineItem, Order
from .store import InvoiceStore


def load_order(path):
    with open(path) as f:
        data = json.load(f)
    customer = Customer(**data["customer"])
    lines = [
        LineItem(
            sku=line["sku"],
            description=line["description"],
            quantity=Decimal(line["quantity"]),
            unit_price=Decimal(line["unit_price"]),
            taxable=line.get("taxable", True),
        )
        for line in data["lines"]
    ]
    return Order(data["id"], customer, lines)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="billing")
    sub = parser.add_subparsers(dest="command", required=True)
    inv = sub.add_parser("invoice", help="price, number, save, and print an invoice for an order file")
    inv.add_argument("order")
    inv.add_argument("--store", required=True)
    exp = sub.add_parser("export", help="print the accounting CSV for a month (YYYY-MM)")
    exp.add_argument("month")
    exp.add_argument("--store", required=True)
    args = parser.parse_args(argv)

    store = InvoiceStore(args.store)
    if args.command == "invoice":
        try:
            invoice = generate_invoice(load_order(args.order), store)
        except (ValueError, KeyError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        sys.stdout.write(invoice.text)
        return 0
    year, month = (int(part) for part in args.month.split("-"))
    sys.stdout.write(export_month(store, year, month))
    return 0
