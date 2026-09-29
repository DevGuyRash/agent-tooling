"""Billing records."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class Customer:
    id: str
    name: str
    region: str  # two-letter state code; decides the sales tax rate
    tier: str = "standard"  # loyalty tier; decides the discount


@dataclass(frozen=True)
class LineItem:
    sku: str
    description: str
    quantity: Decimal  # can be fractional: hours of service, metres of cable
    unit_price: Decimal  # can carry more than two decimals for bulk per-unit prices
    taxable: bool = True


@dataclass(frozen=True)
class Order:
    id: str
    customer: Customer
    lines: list[LineItem] = field(default_factory=list)


@dataclass(frozen=True)
class InvoiceLine:
    sku: str
    description: str
    quantity: Decimal
    unit_price: Decimal
    amount: Decimal


@dataclass(frozen=True)
class Invoice:
    number: str
    order_id: str
    customer_id: str
    issued_on: date
    lines: list[InvoiceLine]
    subtotal: Decimal
    discount: Decimal
    tax: Decimal
    total: Decimal
    text: str
