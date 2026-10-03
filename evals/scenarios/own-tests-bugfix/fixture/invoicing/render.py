"""The printed invoice."""
from .money import fmt
from .summary import VatSummary


def _rate(rate):
    return f"{rate.normalize():f}%"


def render(invoice):
    out = [f"Invoice {invoice.number}  {invoice.date.isoformat()}", invoice.customer, ""]
    out.append(f"{'Description':<30}{'Qty':>8}{'Unit':>10}{'Net':>11}{'VAT':>6}{'VAT amt':>10}")
    for line in invoice.lines:
        out.append(f"{line.description[:30]:<30}{line.quantity.normalize():>8f}{fmt(line.unit_price):>10}"
                   f"{fmt(line.net):>11}{_rate(line.vat_rate):>6}{fmt(line.vat):>10}")
    summary = VatSummary(invoice.lines)
    out.append("")
    for row in summary.rows:
        out.append(f"VAT at {_rate(row.rate):<5} on {fmt(row.net):>10}: {fmt(row.vat):>9}")
    out.append(f"{'Net':<10}{fmt(summary.net):>12}")
    out.append(f"{'VAT':<10}{fmt(summary.vat):>12}")
    out.append(f"{'Total':<10}{fmt(summary.gross):>12}")
    return "\n".join(out)
