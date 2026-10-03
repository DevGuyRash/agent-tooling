"""Invoices and their lines (docs/invoicing.md)."""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from .money import ZERO, to_pennies


@dataclass(frozen=True)
class Line:
    description: str
    quantity: Decimal
    unit_price: Decimal
    vat_rate: Decimal  # percent: 20, 5, 0

    @property
    def net(self):
        return to_pennies(self.quantity * self.unit_price)

    @property
    def vat(self):
        return to_pennies(self.net * self.vat_rate / 100)


@dataclass(frozen=True)
class Invoice:
    number: str
    date: date
    customer: str
    lines: tuple

    def vat_summary(self):
        """[(rate, net, vat)] per VAT rate, highest rate first: sums of the printed line amounts (#31)."""
        rows = {}
        for line in self.lines:
            net, vat = rows.get(line.vat_rate, (ZERO, ZERO))
            rows[line.vat_rate] = (net + line.net, vat + line.vat)
        return [(rate, *rows[rate]) for rate in sorted(rows, reverse=True)]

    def totals(self):
        """(net, vat, gross) for the whole invoice: sums of the summary rows."""
        rows = self.vat_summary()
        net = sum((row[1] for row in rows), ZERO)
        vat = sum((row[2] for row in rows), ZERO)
        return net, vat, net + vat
