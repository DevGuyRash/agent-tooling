"""Reading the library system's nightly exports, loans.csv and patrons.csv (docs/export-format.md)."""
import csv
import datetime as dt
from dataclasses import dataclass

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


@dataclass(frozen=True)
class Patron:
    patron_id: str
    name: str


def _read(path, columns):
    try:
        # The library system writes its exports with a byte-order mark.
        with open(path, encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            missing = [c for c in columns if c not in (reader.fieldnames or ())]
            if missing:
                raise ExportError(f"{path}: no {missing[0]} column")
            return [{k: (v or "").strip() for k, v in row.items() if k} for row in reader]
    except OSError as exc:
        raise ExportError(f"{path}: {exc.strerror or exc}") from None


def parse_date(text, where):
    try:
        return dt.date.fromisoformat(text)
    except ValueError:
        raise ExportError(f"{where}: {text!r} is not a date (YYYY-MM-DD)") from None


def read_loans(path):
    loans = []
    for row in _read(path, LOAN_COLUMNS):
        where = f"{path}: loan {row['loan_id'] or '?'}"
        loans.append(Loan(
            loan_id=row["loan_id"],
            patron_id=row["patron_id"],
            barcode=row["barcode"],
            title=row["title"],
            category=row["category"].lower(),
            due=parse_date(row["due"], where),
            returned=parse_date(row["returned"], where) if row["returned"] else None,
        ))
    return loans


def read_patrons(path):
    return {row["patron_id"]: Patron(row["patron_id"], row["name"]) for row in _read(path, PATRON_COLUMNS)}


def days_late(due, day):
    """Calendar days from the due date to `day`; 0 when `day` is on or before the due date."""
    return max(0, (day - due).days)
