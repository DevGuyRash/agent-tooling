"""Invoices and their lines (docs/invoicing.md)."""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from .money import to_pennies


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
        """[(rate, net, vat)] per VAT rate, highest rate first."""
        from .summary import VatSummary
        return [(row.rate, row.net, row.vat) for row in VatSummary(self.lines).rows]

    def totals(self):
        """(net, vat, gross) for the whole invoice."""
        from .summary import VatSummary
        summary = VatSummary(self.lines)
        return summary.net, summary.vat, summary.gross
