"""The VAT summary printed under an invoice's lines: one row per rate, and the invoice totals."""
from dataclasses import dataclass
from decimal import Decimal

from .money import ZERO


@dataclass(frozen=True)
class VatRow:
    rate: Decimal
    net: Decimal
    vat: Decimal


def rate_totals(lines):
    """{rate: (net, vat)}: each rate's lines' nets and printed (per-line rounded) VAT amounts, added up
    (docs/invoicing.md, #31), so the summary and totals always match the lines on the invoice."""
    sums = {}
    for line in lines:
        net, vat = sums.get(line.vat_rate, (ZERO, ZERO))
        sums[line.vat_rate] = (net + line.net, vat + line.vat)
    return sums


class VatSummary:
    def __init__(self, lines):
        sums = rate_totals(lines)
        self.rows = [VatRow(rate, *sums[rate]) for rate in sorted(sums, reverse=True)]
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
