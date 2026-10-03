"""The printed invoice."""
from .money import fmt


def _rate(rate):
    return f"{rate.normalize():f}%"


def render(invoice):
    out = [f"Invoice {invoice.number}  {invoice.date.isoformat()}", invoice.customer, ""]
    out.append(f"{'Description':<30}{'Qty':>8}{'Unit':>10}{'Net':>11}{'VAT':>6}{'VAT amt':>10}")
    for line in invoice.lines:
        out.append(f"{line.description[:30]:<30}{line.quantity.normalize():>8f}{fmt(line.unit_price):>10}"
                   f"{fmt(line.net):>11}{_rate(line.vat_rate):>6}{fmt(line.vat):>10}")
    out.append("")
    for rate, net, vat in invoice.vat_summary():
        out.append(f"VAT at {_rate(rate):<5} on {fmt(net):>10}: {fmt(vat):>9}")
    net, vat, gross = invoice.totals()
    out.append(f"{'Net':<10}{fmt(net):>12}")
    out.append(f"{'VAT':<10}{fmt(vat):>12}")
    out.append(f"{'Total':<10}{fmt(gross):>12}")
    return "\n".join(out)
