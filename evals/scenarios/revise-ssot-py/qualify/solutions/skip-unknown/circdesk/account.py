"""What a patron owes, for the self-service kiosk."""
from .fines import UnknownCategory, fine
from .loans import ExportError, days_late
from .money import fmt

BLOCK_AT = 1000  # a card owing this much or more cannot borrow


def owed(loan, day):
    """(days late, cents owed) for one loan as of `day`."""
    days = days_late(loan.due, loan.returned or day)
    try:
        return days, fine(loan.category, days)
    except UnknownCategory:
        return days, 0  # a category the policy does not know owes nothing at the kiosk


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
