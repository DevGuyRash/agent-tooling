"""Invoices: pricing an order, numbering and saving it, and the printed layout."""
from datetime import date
from decimal import Decimal

from .models import Invoice, InvoiceLine
from .rates import TAX_RATES, TIER_DISCOUNTS

WIDTH = 72
SELLER = ["Acme Office Supply", "400 Harbor Way, Portland, OR 97209"]


def _percent(rate):
    return f"{(rate * 100).normalize():f}%"


def generate_invoice(order, store, issued_on=None):
    """Price `order`, give it the next invoice number from `store`, save it, and return the Invoice."""
    customer = order.customer
    if not order.lines:
        raise ValueError(f"order {order.id} has no lines")
    if customer.region not in TAX_RATES:
        raise ValueError(f"no sales tax rate for region {customer.region!r}")
    if customer.tier not in TIER_DISCOUNTS:
        raise ValueError(f"unknown loyalty tier {customer.tier!r}")
    for item in order.lines:
        if item.quantity <= 0:
            raise ValueError(f"{item.sku}: quantity must be positive")
        if item.unit_price < 0:
            raise ValueError(f"{item.sku}: unit price cannot be negative")
    issued_on = issued_on or date.today()
    number = store.next_number()

    rows = []
    invoice_lines = []
    subtotal = Decimal("0.00")
    taxable = Decimal("0.00")
    untaxed = False
    for item in order.lines:
        # Each line is added up as printed, so the invoice adds up on paper.
        amount = f"{item.unit_price * item.quantity:.2f}"
        subtotal += Decimal(amount)
        if item.taxable:
            taxable += Decimal(amount)
        else:
            untaxed = True
        row = f"{item.sku:<10} {item.description[:30]:<30} {item.quantity:>6} x {item.unit_price:>9} {amount:>11}"
        rows.append(row if item.taxable else row + " *")
        invoice_lines.append(InvoiceLine(item.sku, item.description, item.quantity, item.unit_price, Decimal(amount)))

    rate = TIER_DISCOUNTS[customer.tier]
    discount = f"{subtotal * rate:.2f}"
    # The loyalty discount lowers the taxable amount by the same percentage.
    tax_rate = TAX_RATES[customer.region]
    tax = f"{taxable * (1 - rate) * tax_rate:.2f}"
    total = subtotal - Decimal(discount) + Decimal(tax)

    totals = [f"{'Subtotal':>60}{subtotal:>12}"]
    if rate:
        totals.append(f"{customer.tier.title() + ' discount ' + _percent(rate):>60}{'-' + discount:>12}")
    totals.append(f"{'Sales tax ' + customer.region + ' ' + _percent(tax_rate):>60}{tax:>12}")
    totals.append(f"{'Total':>60}{total:>12}")
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
        subtotal=subtotal,
        discount=Decimal(discount),
        tax=Decimal(tax),
        total=total,
        text=text + "\n",
    )
    store.save(invoice)
    return invoice
