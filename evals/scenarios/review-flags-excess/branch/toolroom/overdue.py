"""The overdue loans (SPEC R6, R7, R8)."""
from collections import namedtuple

from .cache import ToolCache
from .fines import fine_for

Overdue = namedtuple("Overdue", "loan member_id member tool days fine")


def overdue_loans(loans, members, load_tools, today, rounding="nearest"):
    """The loans overdue on `today`, most days overdue first, as Overdue rows."""
    tools = ToolCache(load_tools)
    rows = []
    for loan in loans:
        days = (today - loan.due).days
        if loan.returned is not None or days <= 0:
            continue
        member = members[loan.member]
        tool = tools.get(loan.tool)
        rows.append(Overdue(loan.id, member.id, member.name, tool.name, days, fine_for(days, tool, member, rounding)))
    rows.sort(key=lambda row: (row.days, row.member, row.loan), reverse=True)
    return rows
