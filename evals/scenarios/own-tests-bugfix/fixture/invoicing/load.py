"""Reading invoice files (docs/invoices.md)."""
import json
from datetime import date
from decimal import Decimal, InvalidOperation

from .model import Invoice, Line


class InvoiceError(Exception):
    pass


def _decimal(value, what, path):
    if not isinstance(value, str):
        raise InvoiceError(f"{path}: {what} must be a string such as \"12.50\"")
    try:
        number = Decimal(value)
    except InvalidOperation:
        raise InvoiceError(f"{path}: {what} {value!r} is not a number") from None
    if not number.is_finite():
        raise InvoiceError(f"{path}: {what} {value!r} is not a number")
    return number


def load(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as err:
        raise InvoiceError(f"{path}: not JSON ({err.msg} at line {err.lineno})") from None
    if not isinstance(data, dict):
        raise InvoiceError(f"{path}: expected an object")
    for key in ("number", "date", "customer", "lines"):
        if key not in data:
            raise InvoiceError(f"{path}: missing {key!r}")
    try:
        day = date.fromisoformat(data["date"])
    except (TypeError, ValueError):
        raise InvoiceError(f"{path}: bad date {data['date']!r}") from None
    if not isinstance(data["lines"], list) or not data["lines"]:
        raise InvoiceError(f"{path}: an invoice needs at least one line")
    lines = []
    for i, raw in enumerate(data["lines"], start=1):
        where = f"line {i}"
        if not isinstance(raw, dict):
            raise InvoiceError(f"{path}: {where} must be an object")
        lines.append(Line(str(raw.get("description", "")),
                          _decimal(raw.get("quantity"), f"{where} quantity", path),
                          _decimal(raw.get("unit_price"), f"{where} unit_price", path),
                          _decimal(raw.get("vat_rate"), f"{where} vat_rate", path)))
    return Invoice(str(data["number"]), day, str(data["customer"]), tuple(lines))
