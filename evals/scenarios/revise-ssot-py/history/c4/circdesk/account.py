"""What a patron owes, for the self-service kiosk."""
from .loans import ExportError, days_late
from .money import fmt

PER_DAY = {"adult": 30, "children": 15, "media": 125}
MOST = {"adult": 700, "children": 250, "media": 1000}
GRACE_PERIOD = 2
BLOCK_AT = 1000  # a card owing this much or more cannot borrow


def owed(loan, day):
    """(days late, cents owed) for one loan as of `day`."""
    if loan.category not in PER_DAY:
        raise ExportError(f"loan {loan.loan_id}: unknown category {loan.category!r}")
    days = days_late(loan.due, loan.returned or day)
    if days <= GRACE_PERIOD:
        return days, 0
    return days, min(days * PER_DAY[loan.category], MOST[loan.category])


def account(loans, patrons, patron_id, day):
    patron = patrons.get(patron_id)
    if patron is None:
        raise ExportError(f"no patron {patron_id}")
    lines, total = [f"{patron.name} ({patron_id})"], 0
    for loan in sorted((l for l in loans if l.patron_id == patron_id), key=lambda l: (l.due, l.title)):
        days, cents = owed(loan, day)
        if not cents:
            continue
        status = f"returned {days} days late" if loan.returned else f"out, {days} days overdue"
        lines.append(f"  {loan.title} ({loan.barcode}): {status}, {fmt(cents)}")
        total += cents
    if not total:
        lines.append("No fines.")
    else:
        lines.append(f"Total owed: {fmt(total)}")
        if total >= BLOCK_AT:
            lines.append(f"Borrowing blocked until the total is under {fmt(BLOCK_AT)}.")
    return "\n".join(lines) + "\n"
