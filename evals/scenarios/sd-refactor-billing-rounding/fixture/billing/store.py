"""Invoice storage: one JSON file per invoice in a directory, numbered in sequence."""
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from .models import Invoice, InvoiceLine


class InvoiceStore:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def next_number(self):
        """Reserve the next invoice number (INV-000001, INV-000002, ...). Numbers must not skip."""
        counter = self.directory / "sequence"
        last = int(counter.read_text()) if counter.exists() else 0
        counter.write_text(f"{last + 1}\n")
        return f"INV-{last + 1:06d}"

    def save(self, invoice):
        record = {
            "number": invoice.number,
            "order_id": invoice.order_id,
            "customer_id": invoice.customer_id,
            "issued_on": invoice.issued_on.isoformat(),
            "lines": [
                {
                    "sku": line.sku,
                    "description": line.description,
                    "quantity": str(line.quantity),
                    "unit_price": str(line.unit_price),
                    "amount": str(line.amount),
                }
                for line in invoice.lines
            ],
            "subtotal": str(invoice.subtotal),
            "discount": str(invoice.discount),
            "tax": str(invoice.tax),
            "total": str(invoice.total),
            "text": invoice.text,
        }
        (self.directory / f"{invoice.number}.json").write_text(json.dumps(record, indent=2) + "\n")

    def load(self, number):
        record = json.loads((self.directory / f"{number}.json").read_text())
        lines = [
            InvoiceLine(
                line["sku"],
                line["description"],
                Decimal(line["quantity"]),
                Decimal(line["unit_price"]),
                Decimal(line["amount"]),
            )
            for line in record["lines"]
        ]
        return Invoice(
            number=record["number"],
            order_id=record["order_id"],
            customer_id=record["customer_id"],
            issued_on=date.fromisoformat(record["issued_on"]),
            lines=lines,
            subtotal=Decimal(record["subtotal"]),
            discount=Decimal(record["discount"]),
            tax=Decimal(record["tax"]),
            total=Decimal(record["total"]),
            text=record["text"],
        )

    def all(self):
        return [self.load(path.stem) for path in sorted(self.directory.glob("INV-*.json"))]
