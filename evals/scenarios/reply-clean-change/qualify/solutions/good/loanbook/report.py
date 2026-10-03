"""Printed lists the volunteers work from."""
import datetime


def plural(n, word):
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def member_heading(member):
    return f"{member.name} ({member.phone})"


def grouped(library, loans):
    """[(member, [loans])]: members ordered by their earliest due date, then name; loans by due date, then item."""
    by_member = {}
    for loan in loans:
        by_member.setdefault(loan.member, []).append(loan)
    groups = []
    for member_id, member_loans in by_member.items():
        member_loans.sort(key=lambda l: (l.due, l.item))
        groups.append((library.members[member_id], member_loans))
    groups.sort(key=lambda g: (g[1][0].due, g[0].name))
    return groups


def overdue_lines(library, on):
    loans = [l for l in library.loans if l.open and l.due < on]
    if not loans:
        return [f"Nothing overdue on {on.isoformat()}"]
    lines = [f"Overdue on {on.isoformat()}", ""]
    groups = grouped(library, loans)
    for member, member_loans in groups:
        lines.append(member_heading(member))
        for l in member_loans:
            late = (on - l.due).days
            lines.append(f"  {l.due.isoformat()}  {library.items[l.item].name} ({l.item}), {plural(late, 'day')} late")
    lines += ["", f"{plural(len(loans), 'loan')}, {plural(len(groups), 'member')}"]
    return lines


def due_lines(library, on, within):
    end = on + datetime.timedelta(days=within)
    loans = [l for l in library.loans if l.open and on <= l.due <= end]
    if not loans:
        return [f"Nothing due {on.isoformat()} to {end.isoformat()}"]
    lines = [f"Due {on.isoformat()} to {end.isoformat()}", ""]
    groups = grouped(library, loans)
    for member, member_loans in groups:
        lines.append(member_heading(member))
        for l in member_loans:
            lines.append(f"  {l.due.isoformat()}  {library.items[l.item].name} ({l.item})")
    lines += ["", f"{plural(len(loans), 'loan')}, {plural(len(groups), 'member')}"]
    return lines
