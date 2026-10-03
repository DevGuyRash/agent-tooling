"""The library's three spreadsheets, exported as CSV: items, members, and loans."""
import csv
import datetime
from dataclasses import dataclass


class RecordsError(Exception):
    pass


@dataclass(frozen=True)
class Item:
    item: str
    name: str


@dataclass(frozen=True)
class Member:
    member: str
    name: str
    phone: str


@dataclass(frozen=True)
class Loan:
    loan: str
    item: str
    member: str
    out: datetime.date
    due: datetime.date
    returned: datetime.date | None

    @property
    def open(self):
        return self.returned is None


def _rows(path, columns):
    try:
        with open(path, encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames != list(columns):
                raise RecordsError(f"{path}: expected columns {','.join(columns)}")
            return list(reader)
    except OSError:
        raise RecordsError(f"cannot read {path}") from None


def _date(path, n, text, blank_ok=False):
    text = (text or "").strip()
    if not text and blank_ok:
        return None
    try:
        return datetime.date.fromisoformat(text)
    except ValueError:
        raise RecordsError(f"{path} line {n}: bad date {text!r}") from None


def read_items(path):
    return {r["item"]: Item(r["item"], r["name"]) for r in _rows(path, ("item", "name"))}


def read_members(path):
    return {r["member"]: Member(r["member"], r["name"], r["phone"]) for r in _rows(path, ("member", "name", "phone"))}


def read_loans(path):
    out = []
    for n, r in enumerate(_rows(path, ("loan", "item", "member", "out", "due", "returned")), start=2):
        out.append(Loan(r["loan"], r["item"], r["member"], _date(path, n, r["out"]), _date(path, n, r["due"]),
                        _date(path, n, r["returned"], blank_ok=True)))
    return out


@dataclass
class Library:
    items: dict
    members: dict
    loans: list


def load(data_dir="data"):
    return Library(read_items(f"{data_dir}/items.csv"), read_members(f"{data_dir}/members.csv"),
                   read_loans(f"{data_dir}/loans.csv"))
