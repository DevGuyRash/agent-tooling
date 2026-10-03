"""The VAT summary printed under an invoice's lines: one row per rate, and the invoice totals."""
from dataclasses import dataclass
from decimal import Decimal

from .money import ZERO, to_pennies


@dataclass(frozen=True)
class VatRow:
    rate: Decimal
    net: Decimal
    vat: Decimal


class VatSummary:
    def __init__(self, lines):
        by_rate = {}
        for line in lines:
            by_rate.setdefault(line.vat_rate, []).append(line)
        self.rows = []
        for rate in sorted(by_rate, reverse=True):
            net = sum((line.net for line in by_rate[rate]), ZERO)
            self.rows.append(VatRow(rate, net, to_pennies(net * rate / 100)))
        self.net = sum((row.net for row in self.rows), ZERO)
        self.vat = sum((row.vat for row in self.rows), ZERO)
        self.gross = self.net + self.vat

    def merge(self, other):
        """A summary of both: rows of the same rate added together (for the month-end report)."""
        merged = VatSummary([])
        rows = {row.rate: row for row in self.rows}
        for row in other.rows:
            mine = rows.get(row.rate)
            rows[row.rate] = row if mine is None else VatRow(row.rate, mine.net + row.net, mine.vat + row.vat)
        merged.rows = [rows[rate] for rate in sorted(rows, reverse=True)]
        merged.net = sum((row.net for row in merged.rows), ZERO)
        merged.vat = sum((row.vat for row in merged.rows), ZERO)
        merged.gross = merged.net + merged.vat
        return merged
