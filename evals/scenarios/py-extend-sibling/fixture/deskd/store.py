"""The ticket store: the ticketing system's nightly JSON-lines dump, one ticket per line."""
import json
import re
from dataclasses import dataclass
from pathlib import Path

STATUSES = ("open", "pending", "solved", "closed")
OPENED = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d(?::\d\d)?")


class StoreError(Exception):
    pass


@dataclass(frozen=True)
class Ticket:
    id: int
    subject: str
    customer: str
    priority: str
    status: str
    opened_at: str  # the office's local time, YYYY-MM-DDTHH:MM with optional :SS


def _ticket(obj, where):
    if not isinstance(obj, dict):
        raise StoreError(f"{where}: expected a JSON object")
    for key, kind in (("id", int), ("subject", str), ("customer", str), ("priority", str), ("status", str),
                      ("opened_at", str)):
        if not isinstance(obj.get(key), kind) or isinstance(obj.get(key), bool):
            raise StoreError(f"{where}: '{key}' missing or not a {kind.__name__}")
    if obj["status"] not in STATUSES:
        raise StoreError(f"{where}: unknown status '{obj['status']}'")
    if not OPENED.fullmatch(obj["opened_at"]):
        raise StoreError(f"{where}: opened_at must look like 2026-10-02T09:15")
    return Ticket(obj["id"], obj["subject"], obj["customer"], obj["priority"], obj["status"], obj["opened_at"])


def load(path: str | Path) -> list[Ticket]:
    """Every ticket in the dump, in id order. Blank lines are allowed; anything else that is not a ticket is an
    error naming the file and line."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise StoreError(f"cannot read {path}: {exc.strerror}") from None
    tickets, seen = [], set()
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        where = f"{path} line {number}"
        try:
            obj = json.loads(line)
        except ValueError:
            raise StoreError(f"{where}: not JSON") from None
        ticket = _ticket(obj, where)
        if ticket.id in seen:
            raise StoreError(f"{where}: ticket {ticket.id} appears twice")
        seen.add(ticket.id)
        tickets.append(ticket)
    return sorted(tickets, key=lambda t: t.id)
