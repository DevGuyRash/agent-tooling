"""Customer rows from the storefront's nightly export, and how we tell that two rows are the same person.

The storefront writes one row per customer account (see docs/export-format.md). Guest checkouts get an
account of their own, so one person can have several rows.
"""

import csv
import re
from dataclasses import dataclass

from .money import format_money, parse_money

COLUMNS = ("customer_id", "created_at", "first_name", "last_name", "email", "phone", "orders", "total_spent",
           "accepts_marketing")
_CREATED_AT = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
_PLACEHOLDER = re.compile(r"(\d)\1*")


@dataclass(frozen=True)
class Contact:
    """One account row of the export."""

    customer_id: int
    created_at: str          # UTC, e.g. 2024-05-03T10:22:31Z, so it sorts as text
    first_name: str
    last_name: str
    email: str               # as the customer typed it
    phone: str               # as the customer typed it
    orders: int
    total_spent: int         # cents
    accepts_marketing: bool


class ExportError(ValueError):
    """The file is not a customer export we can read."""


def row_problems(row: dict) -> list[str]:
    """What is wrong with one export row (a csv.DictReader row); empty when nothing is."""
    problems = []
    if None in row or any(row.get(c) is None for c in COLUMNS):
        return ["wrong number of fields"]
    if not row["customer_id"].isdigit():
        problems.append(f"customer_id is not a number: {row['customer_id']!r}")
    if not _CREATED_AT.fullmatch(row["created_at"]):
        problems.append(f"created_at is not a UTC timestamp: {row['created_at']!r}")
    if not row["orders"].isdigit():
        problems.append(f"orders is not a count: {row['orders']!r}")
    try:
        if parse_money(row["total_spent"]) < 0:
            problems.append(f"total_spent is negative: {row['total_spent']!r}")
    except ValueError:
        problems.append(f"total_spent is not an amount: {row['total_spent']!r}")
    if row["accepts_marketing"] not in ("yes", "no"):
        problems.append(f"accepts_marketing must be yes or no: {row['accepts_marketing']!r}")
    return problems


def parse_row(row: dict) -> Contact:
    """A Contact from an export row that has no problems."""
    return Contact(
        customer_id=int(row["customer_id"]),
        created_at=row["created_at"],
        first_name=row["first_name"],
        last_name=row["last_name"],
        email=row["email"],
        phone=row["phone"],
        orders=int(row["orders"]),
        total_spent=parse_money(row["total_spent"]),
        accepts_marketing=row["accepts_marketing"] == "yes",
    )


def read_export(path) -> list[Contact]:
    """Every row of an export, in file order. Raises ExportError at the first row with a problem."""
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if tuple(reader.fieldnames or ()) != COLUMNS:
            raise ExportError(f"{path}: not a customer export (expected the header {','.join(COLUMNS)})")
        contacts = []
        for row in reader:
            problems = row_problems(row)
            if problems:
                raise ExportError(f"{path}:{reader.line_num}: {problems[0]}")
            contacts.append(parse_row(row))
        return contacts


def to_row(contact: Contact) -> list[str]:
    """A Contact as export fields, in COLUMNS order."""
    return [str(contact.customer_id), contact.created_at, contact.first_name, contact.last_name, contact.email,
            contact.phone, str(contact.orders), format_money(contact.total_spent),
            "yes" if contact.accepts_marketing else "no"]


def write_rows(rows, out) -> None:
    """Write rows of fields as CSV, the way the export itself is written."""
    csv.writer(out, lineterminator="\n").writerows(rows)


def normalize_email(raw: str) -> str:
    """The form two email addresses are compared in: no surrounding spaces, lower case.

    Blank when the value is not an address at all ("none", "n/a", and so on)."""
    email = raw.strip().lower()
    return email if "@" in email else ""


def normalize_phone(raw: str) -> str:
    """The form two phone numbers are compared in: the ten digits of a US number.

    Punctuation and spaces are dropped, and so is a leading country code 1. Blank when what is left is not
    ten digits, or is a placeholder such as 000-000-0000 that checkout forms get filled with."""
    digits = re.sub(r"[^0-9]", "", raw)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) != 10 or _PLACEHOLDER.fullmatch(digits):
        return ""
    return digits


def same_customer(a: Contact, b: Contact) -> bool:
    """Whether two rows are directly the same person: the same email address or the same phone number."""
    email = normalize_email(a.email)
    if email and email == normalize_email(b.email):
        return True
    phone = normalize_phone(a.phone)
    return bool(phone) and phone == normalize_phone(b.phone)


def find_matches(contacts, query: str) -> list[Contact]:
    """The rows whose email address or phone number is `query`, compared as above."""
    email, phone = normalize_email(query), normalize_phone(query)
    return [c for c in contacts
            if (email and normalize_email(c.email) == email) or (phone and normalize_phone(c.phone) == phone)]
