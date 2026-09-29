"""Invoices: numbering and saving a priced order, and the printed layout."""
from datetime import date

from .models import Invoice, InvoiceLine
from .pricing import price_order

WIDTH = 72
SELLER = ["Acme Office Supply", "400 Harbor Way, Portland, OR 97209"]


def _percent(rate):
    return f"{(rate * 100).normalize():f}%"


def generate_invoice(order, store, issued_on=None):
    """Price `order`, give it the next invoice number from `store`, save it, and return the Invoice."""
    if not order.lines:
        raise ValueError(f"order {order.id} has no lines")
    customer = order.customer
    price = price_order(order.lines, customer)  # validates before an invoice number is used
    issued_on = issued_on or date.today()
    number = store.next_number()

    rows = []
    for line in price.lines:
        item = line.item
        row = f"{item.sku:<10} {item.description[:30]:<30} {item.quantity:>6} x {item.unit_price:>9} {line.amount:>11}"
        rows.append(row if item.taxable else row + " *")
    totals = [f"{'Subtotal':>60}{price.subtotal:>12}"]
    if price.discount_rate:
        label = customer.tier.title() + " discount " + _percent(price.discount_rate)
        totals.append(f"{label:>60}{'-' + str(price.discount):>12}")
    totals.append(f"{'Sales tax ' + customer.region + ' ' + _percent(price.tax_rate):>60}{price.tax:>12}")
    totals.append(f"{'Total':>60}{price.total:>12}")
    untaxed = any(not line.item.taxable for line in price.lines)
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
        lines=[InvoiceLine(l.item.sku, l.item.description, l.item.quantity, l.item.unit_price, l.amount)
               for l in price.lines],
        subtotal=price.subtotal,
        discount=price.discount,
        tax=price.tax,
        total=price.total,
        text=text + "\n",
    )
    store.save(invoice)
    return invoice
