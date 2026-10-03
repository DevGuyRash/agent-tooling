"""The month-end report: every invoice of a month with its totals, and the month's VAT by rate."""
from .money import fmt
from .render import _rate
from .summary import VatSummary


def month_report(invoices):
    invoices = sorted(invoices, key=lambda inv: (inv.date, inv.number))
    out = [f"{'Invoice':<14}{'Date':<12}{'Customer':<28}{'Net':>11}{'VAT':>10}{'Total':>11}"]
    month = VatSummary([])
    for inv in invoices:
        summary = VatSummary(inv.lines)
        month = month.merge(summary)
        out.append(f"{inv.number:<14}{inv.date.isoformat():<12}{inv.customer[:27]:<28}"
                   f"{fmt(summary.net):>11}{fmt(summary.vat):>10}{fmt(summary.gross):>11}")
    out.append("")
    for row in month.rows:
        out.append(f"VAT at {_rate(row.rate):<5} on {fmt(row.net):>10}: {fmt(row.vat):>9}")
    out.append(f"{len(invoices)} invoices, net {fmt(month.net)}, VAT {fmt(month.vat)}, total {fmt(month.gross)}")
    return "\n".join(out)
