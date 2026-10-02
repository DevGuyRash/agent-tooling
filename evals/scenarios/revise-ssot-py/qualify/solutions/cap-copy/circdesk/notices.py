"""The overnight overdue notices: one per patron with items past the grace period."""
from .fines import RATES, in_grace
from .loans import ExportError, days_late
from .money import fmt


def notices(loans, patrons, day):
    """Tonight's notices, as the mailer reads them: fines so far as of `day`."""
    due_notices = {}
    for loan in loans:
        if loan.returned is not None:
            continue
        rate = RATES.get(loan.category)
        if rate is None:
            raise ExportError(f"loan {loan.loan_id}: unknown category {loan.category!r}")
        days = days_late(loan.due, day)
        if in_grace(days):
            continue
        if loan.patron_id not in patrons:
            raise ExportError(f"loan {loan.loan_id}: no patron {loan.patron_id}")
        due_notices.setdefault(loan.patron_id, []).append((loan, days, min(days * rate.per_day, rate.most)))
    if not due_notices:
        return "No notices.\n"
    lines, items = [], 0
    for patron_id in sorted(due_notices, key=lambda p: (patrons[p].name.casefold(), p)):
        lines.append(f"{patrons[patron_id].name} ({patron_id})")
        for loan, days, owed in sorted(due_notices[patron_id], key=lambda e: (e[0].due, e[0].title)):
            lines.append(f"  {loan.title} ({loan.barcode}): due {loan.due}, {days} days overdue, "
                         f"fine so far {fmt(owed)}")
            items += 1
    count = len(due_notices)
    lines.append(f"{count} notice{'' if count == 1 else 's'}, {items} item{'' if items == 1 else 's'}")
    return "\n".join(lines) + "\n"
