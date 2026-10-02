"""The receipt the circulation desk prints when an item comes back."""
from .fines import UnknownCategory, fine
from .loans import ExportError, days_late
from .money import fmt


def receipt(loans, loan_id):
    loan = next((l for l in loans if l.loan_id == loan_id), None)
    if loan is None:
        raise ExportError(f"no loan {loan_id}")
    if loan.returned is None:
        raise ExportError(f"loan {loan_id} has not been returned")
    days = days_late(loan.due, loan.returned)
    try:
        owed = fine(loan.category, days)
    except UnknownCategory:
        raise ExportError(f"loan {loan_id}: unknown category {loan.category!r}") from None
    late = "on time" if days == 0 else "1 day late" if days == 1 else f"{days} days late"
    return (f"Returned: {loan.title} ({loan.barcode})\n"
            f"Due {loan.due}, returned {loan.returned}: {late}\n"
            f"Fine: {fmt(owed) if owed else 'none'}\n")
