from datetime import date
from decimal import Decimal

from invoicing.model import Invoice, Line


def line(description, quantity, unit_price, vat_rate):
    return Line(description, Decimal(quantity), Decimal(unit_price), Decimal(vat_rate))


def invoice(*lines, number="HP-TEST-1", day=date(2026, 9, 30), customer="Test Customer"):
    return Invoice(number, day, customer, tuple(lines))
