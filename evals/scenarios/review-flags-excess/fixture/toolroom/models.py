"""The records the data files describe (SPEC R2)."""
from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass(frozen=True)
class Member:
    id: str
    name: str
    status: str  # "standard" or "supporter"


@dataclass(frozen=True)
class Tool:
    id: str
    name: str
    value: int  # the replacement value, in cents


@dataclass(frozen=True)
class Loan:
    id: str
    member: str  # a member id
    tool: str  # a tool id
    out: date
    due: date
    returned: Optional[date]
