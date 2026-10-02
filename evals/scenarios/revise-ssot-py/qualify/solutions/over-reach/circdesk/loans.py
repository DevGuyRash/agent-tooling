"""The library system's nightly exports, loaded into typed records (docs/export-format.md)."""
import csv
import datetime as dt
from dataclasses import dataclass
from pathlib import Path

LOAN_COLUMNS = ("loan_id", "patron_id", "barcode", "title", "category", "due", "returned")
PATRON_COLUMNS = ("patron_id", "name")


class ExportError(Exception):
    """Something wrong with an export, or with what was asked of it; the command prints it and exits 1."""


@dataclass(frozen=True)
class Loan:
    loan_id: str
    patron_id: str
    barcode: str
    title: str
    category: str
    due: dt.date
    returned: dt.date | None

    @property
    def out(self):
        return self.returned is None


@dataclass(frozen=True)
class Patron:
    patron_id: str
    name: str


def _records(path, columns):
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ExportError(f"{path}: {exc.strerror or exc}") from None
    reader = csv.DictReader(text.splitlines())
    if reader.fieldnames is None or any(c not in reader.fieldnames for c in columns):
        missing = next(c for c in columns if c not in (reader.fieldnames or ()))
        raise ExportError(f"{path}: no {missing} column")
    for row in reader:
        yield {k: (v or "").strip() for k, v in row.items() if k}


def parse_date(text, where):
    try:
        return dt.date.fromisoformat(text)
    except ValueError:
        raise ExportError(f"{where}: {text!r} is not a date (YYYY-MM-DD)") from None


def read_loans(path):
    out = []
    for row in _records(path, LOAN_COLUMNS):
        where = f"{path}: loan {row['loan_id'] or '?'}"
        out.append(Loan(row["loan_id"], row["patron_id"], row["barcode"], row["title"], row["category"].lower(),
                        parse_date(row["due"], where),
                        parse_date(row["returned"], where) if row["returned"] else None))
    return out


def read_patrons(path):
    return {r["patron_id"]: Patron(r["patron_id"], r["name"]) for r in _records(path, PATRON_COLUMNS)}


def days_late(due, day):
    """Calendar days from the due date to `day`; 0 when `day` is on or before the due date."""
    return max(0, (day - due).days)
