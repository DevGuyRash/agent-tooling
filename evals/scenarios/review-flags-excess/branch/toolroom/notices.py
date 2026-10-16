"""Notices for members with overdue loans (SPEC R10, R11)."""
import sys
import time
from pathlib import Path

from .render import dollars

CENTS_PER_DAY = 50
ATTEMPTS = 3
DELAY = 1.0  # seconds between attempts


def total_owed(rows):
    """What a member owes for these overdue loans, in cents."""
    return sum(row.days for row in rows) * CENTS_PER_DAY


def render_notice(member, rows):
    lines = ["Dear %s," % member.name, "", "These loans are overdue:"]
    lines += ["  %s  %d days  %s" % (row.tool, row.days, dollars(row.fine)) for row in rows]
    lines += ["", "Total owed: %s" % dollars(total_owed(rows))]
    return "\n".join(lines) + "\n"


def write_notice(path, text):
    """Write one notice, in at most ATTEMPTS attempts DELAY seconds apart; the last error, or None when it was written."""
    for attempt in range(ATTEMPTS):
        try:
            path.write_text(text, encoding="utf-8")
            return None
        except OSError as exc:
            error = exc
            if attempt < ATTEMPTS - 1:
                time.sleep(DELAY)
    return error


def write_notices(directory, rows, members):
    """Write a notice for every member with an overdue loan, to `directory`/<member id>.txt."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    by_member = {}
    for row in rows:
        by_member.setdefault(row.member_id, []).append(row)
    for member_id in sorted(by_member):
        text = render_notice(members[member_id], by_member[member_id])
        error = write_notice(directory / (member_id + ".txt"), text)
        if error is not None:
            print("could not write notice for %s: %s" % (member_id, error), file=sys.stderr)
