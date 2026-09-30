"""Turn one bank's CSV rows into normalized transactions."""
import csv
import re
from datetime import datetime
from decimal import Decimal

from .banks import BANKS, required_columns


def clean_description(text):
    return text.strip()


def parse_amount(text):
    text = text.replace("$", "").replace(",", "").strip()
    return Decimal(text) if text else Decimal("0")


def categorize(bank, row, amount):
    return "credit" if amount > 0 else "debit"


def normalize_row(bank, row):
    layout = BANKS[bank]
    date = datetime.strptime(row[layout["date"]].strip(), layout["date_format"]).date()
    if "amount" in layout:
        amount = parse_amount(row[layout["amount"]])
    else:
        amount = parse_amount(row[layout["credit"]]) - parse_amount(row[layout["debit"]])
    return {
        "date": date.isoformat(),
        "description": clean_description(row[layout["description"]]),
        "amount": str(amount),
        "category": categorize(bank, row, amount),
    }


def normalize_file(bank, path):
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for column in required_columns(bank):
            if column not in (reader.fieldnames or []):
                raise ValueError(f"{path}: missing column '{column}' for bank '{bank}'")
        return [normalize_row(bank, row) for row in reader]
