"""Monthly accounting export: one CSV row per invoice issued in the month, then a totals row."""
import csv
import io
from decimal import Decimal

from .money import format_amount

AMOUNTS = ["subtotal", "discount", "tax", "total"]


def export_month(store, year, month):
    invoices = [inv for inv in store.all() if (inv.issued_on.year, inv.issued_on.month) == (year, month)]
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(["number", "issued_on", "customer_id", *AMOUNTS])
    for inv in invoices:
        writer.writerow([inv.number, inv.issued_on.isoformat(), inv.customer_id,
                         *(format_amount(getattr(inv, name)) for name in AMOUNTS)])
    sums = [sum((getattr(inv, name) for inv in invoices), Decimal("0")) for name in AMOUNTS]
    writer.writerow(["TOTAL", "", len(invoices), *(format_amount(s) for s in sums)])
    return out.getvalue()
