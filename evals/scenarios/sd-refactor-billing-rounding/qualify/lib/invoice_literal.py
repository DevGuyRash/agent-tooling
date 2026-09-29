"""Invoices: pricing an order, numbering and saving it, and the printed layout."""
from datetime import date

from .models import Invoice, InvoiceLine
from .pricing import price_order

WIDTH = 72
SELLER = ["Acme Office Supply", "400 Harbor Way, Portland, OR 97209"]


def _percent(rate):
    return f"{(rate * 100).normalize():f}%"


def generate_invoice(order, store, issued_on=None):
    """Price `order`, give it the next invoice number from `store`, save it, and return the Invoice."""
    customer = order.customer
    if not order.lines:
        raise ValueError(f"order {order.id} has no lines")
    price = price_order(order.lines, customer)
    issued_on = issued_on or date.today()
    number = store.next_number()

    rows = []
    invoice_lines = []
    untaxed = False
    for item, amount in price["items"]:
        untaxed = untaxed or not item.taxable
        row = f"{item.sku:<10} {item.description[:30]:<30} {item.quantity:>6} x {item.unit_price:>9} {amount:>11}"
        rows.append(row if item.taxable else row + " *")
        invoice_lines.append(InvoiceLine(item.sku, item.description, item.quantity, item.unit_price, amount))

    rate, tax_rate = price["discount_rate"], price["tax_rate"]
    totals = [f"{'Subtotal':>60}{price['subtotal']:>12}"]
    if rate:
        totals.append(f"{customer.tier.title() + ' discount ' + _percent(rate):>60}{'-' + str(price['discount']):>12}")
    totals.append(f"{'Sales tax ' + customer.region + ' ' + _percent(tax_rate):>60}{price['tax']:>12}")
    totals.append(f"{'Total':>60}{price['total']:>12}")
    text = "\n".join(
        [
            *SELLER,
            "",
            f"INVOICE {number}".ljust(WIDTH - 20) + f"Issued {issued_on.isoformat()}".rjust(20),
            f"Order {order.id}",
            f"Bill to: {customer.name} ({customer.id})",
            "-" * WIDTH,
            *rows,
            "-" * WIDTH,
            *totals,
            *(["", "* no sales tax on this line"] if untaxed else []),
        ]
    )

    invoice = Invoice(
        number=number,
        order_id=order.id,
        customer_id=customer.id,
        issued_on=issued_on,
        lines=invoice_lines,
        subtotal=price["subtotal"],
        discount=price["discount"],
        tax=price["tax"],
        total=price["total"],
        text=text + "\n",
    )
    store.save(invoice)
    return invoice
