"""Reading the data files (SPEC R2, R3)."""
import csv
import re
from datetime import date
from pathlib import Path

from .models import Loan, Member, Tool

STATUSES = ("standard", "supporter")


class DataError(Exception):
    """A file or row that cannot be understood; the message names the file and the line."""


def parse_date(text):
    """A date written YYYY-MM-DD."""
    if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", text):
        try:
            return date.fromisoformat(text)
        except ValueError:
            pass
    raise ValueError("%r is not a date (YYYY-MM-DD)" % text)


def _rows(directory, name, columns):
    """[(line number, row)] of one CSV file, once its header and the width of every row are checked."""
    try:
        with open(Path(directory) / name, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            if next(reader, None) != columns:
                raise DataError("%s: line 1: the header must be %s" % (name, ",".join(columns)))
            rows = [(reader.line_num, row) for row in reader]
    except OSError as exc:
        raise DataError("%s: %s" % (name, exc.strerror))
    for number, row in rows:
        if len(row) != len(columns):
            raise DataError("%s: line %d: expected %d columns" % (name, number, len(columns)))
    return rows


def _date(name, number, text):
    try:
        return parse_date(text)
    except ValueError as exc:
        raise DataError("%s: line %d: %s" % (name, number, exc))


def load_members(directory):
    """{id: Member} from members.csv."""
    members = {}
    for number, (id_, name, status) in _rows(directory, "members.csv", ["id", "name", "status"]):
        if status not in STATUSES:
            raise DataError("members.csv: line %d: the status must be standard or supporter" % number)
        members[id_] = Member(id_, name, status)
    return members


def load_tools(directory):
    """{id: Tool} from tools.csv."""
    tools = {}
    for number, (id_, name, value) in _rows(directory, "tools.csv", ["id", "name", "value"]):
        if not re.fullmatch(r"[0-9]+", value):
            raise DataError("tools.csv: line %d: the value must be a number of cents" % number)
        tools[id_] = Tool(id_, name, int(value))
    return tools


def load_loans(directory, members, tools):
    """[Loan] from loans.csv, checked against the members and tools that were read."""
    loans = []
    columns = ["loan", "member", "tool", "out", "due", "returned"]
    for number, (id_, member, tool, out, due, returned) in _rows(directory, "loans.csv", columns):
        if member not in members:
            raise DataError("loans.csv: line %d: no member %s" % (number, member))
        if tool not in tools:
            raise DataError("loans.csv: line %d: no tool %s" % (number, tool))
        back = _date("loans.csv", number, returned) if returned else None
        loans.append(Loan(id_, member, tool, _date("loans.csv", number, out), _date("loans.csv", number, due), back))
    return loans
