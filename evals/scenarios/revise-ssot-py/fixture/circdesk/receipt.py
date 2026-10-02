"""The receipt the circulation desk prints when an item comes back."""
from .loans import ExportError, days_late
from .money import fmt

# Overdue fines, docs/fines.md: cents per day late, and the most one item can owe.
DAILY_FINE = {"adult": 30, "children": 15, "media": 125}
MAX_FINE = {"adult": 700, "children": 250, "media": 1250}
# An item back this many days late or less owes nothing.
GRACE_DAYS = 2


def _fine(category, days):
    if category not in DAILY_FINE:
        raise ValueError(category)
    if days <= GRACE_DAYS:
        return 0
    return min(days * DAILY_FINE[category], MAX_FINE[category])


def receipt(loans, loan_id):
    loan = next((l for l in loans if l.loan_id == loan_id), None)
    if loan is None:
        raise ExportError(f"no loan {loan_id}")
    if loan.returned is None:
        raise ExportError(f"loan {loan_id} has not been returned")
    days = days_late(loan.due, loan.returned)
    try:
        owed = _fine(loan.category, days)
    except ValueError:
        raise ExportError(f"loan {loan_id}: unknown category {loan.category!r}") from None
    late = "on time" if days == 0 else "1 day late" if days == 1 else f"{days} days late"
    return (f"Returned: {loan.title} ({loan.barcode})\n"
            f"Due {loan.due}, returned {loan.returned}: {late}\n"
            f"Fine: {fmt(owed) if owed else 'none'}\n")
