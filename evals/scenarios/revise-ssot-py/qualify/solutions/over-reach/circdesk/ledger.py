"""Everything circdesk knows about fines: the board's policy (docs/fines.md) and the three ways it is shown,
the desk receipt, the overnight notices, and the kiosk's account view."""
from dataclasses import dataclass

from .loans import ExportError, days_late
from .money import fmt


@dataclass(frozen=True)
class Rate:
    per_day: int
    most: int


POLICY = {
    "adult": Rate(35, 700),
    "children": Rate(15, 300),
    "media": Rate(125, 1250),
    "device": Rate(240, 4800),
}
GRACE_DAYS = 2
BLOCK_AT = 1000


class Ledger:
    def __init__(self, loans, patrons=None):
        self.loans = loans
        self.patrons = patrons or {}

    @staticmethod
    def fine(loan, days):
        rate = POLICY.get(loan.category)
        if rate is None:
            raise ExportError(f"loan {loan.loan_id}: unknown category {loan.category!r}")
        return 0 if days <= GRACE_DAYS else min(days * rate.per_day, rate.most)

    def receipt(self, loan_id):
        loan = next((l for l in self.loans if l.loan_id == loan_id), None)
        if loan is None:
            raise ExportError(f"no loan {loan_id}")
        if loan.out:
            raise ExportError(f"loan {loan_id} has not been returned")
        days = days_late(loan.due, loan.returned)
        owed = self.fine(loan, days)
        late = "on time" if days == 0 else "1 day late" if days == 1 else f"{days} days late"
        return (f"Returned: {loan.title} ({loan.barcode})\n"
                f"Due {loan.due}, returned {loan.returned}: {late}\n"
                f"Fine: {fmt(owed) if owed else 'none'}\n")

    def notices(self, day):
        found = {}
        for loan in (l for l in self.loans if l.out):
            days = days_late(loan.due, day)
            owed = self.fine(loan, days)
            if not owed:
                continue
            if loan.patron_id not in self.patrons:
                raise ExportError(f"loan {loan.loan_id}: no patron {loan.patron_id}")
            found.setdefault(loan.patron_id, []).append((loan, days, owed))
        if not found:
            return "No notices.\n"
        lines, items = [], 0
        for pid in sorted(found, key=lambda p: (self.patrons[p].name.casefold(), p)):
            lines.append(f"{self.patrons[pid].name} ({pid})")
            for loan, days, owed in sorted(found[pid], key=lambda e: (e[0].due, e[0].title)):
                lines.append(f"  {loan.title} ({loan.barcode}): due {loan.due}, {days} days overdue, "
                             f"fine so far {fmt(owed)}")
                items += 1
        lines.append(f"{len(found)} notice{'' if len(found) == 1 else 's'}, {items} item{'' if items == 1 else 's'}")
        return "\n".join(lines) + "\n"

    def account(self, patron_id, day):
        patron = self.patrons.get(patron_id)
        if patron is None:
            raise ExportError(f"no patron {patron_id}")
        lines, total = [f"{patron.name} ({patron_id})"], 0
        for loan in sorted((l for l in self.loans if l.patron_id == patron_id), key=lambda l: (l.due, l.title)):
            days = days_late(loan.due, loan.returned or day)
            owed = self.fine(loan, days)
            if owed:
                status = f"returned {days} days late" if loan.returned else f"out, {days} days overdue"
                lines.append(f"  {loan.title} ({loan.barcode}): {status}, {fmt(owed)}")
                total += owed
        if not total:
            lines.append("No fines.")
        else:
            lines.append(f"Total owed: {fmt(total)}")
            if total >= BLOCK_AT:
                lines.append(f"Borrowing blocked until the total is under {fmt(BLOCK_AT)}.")
        return "\n".join(lines) + "\n"
