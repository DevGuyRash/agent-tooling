"""The waiting list (data/waiting.csv): who is waiting for a plot, and since when."""
import csv
import datetime
from dataclasses import dataclass


class WaitingError(Exception):
    pass


@dataclass(frozen=True)
class Waiting:
    name: str
    joined: datetime.date
    wants: str  # "full", "half", or "any"


def read_waiting(path):
    try:
        with open(path, encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
    except (OSError, UnicodeDecodeError):
        raise WaitingError(f"cannot read {path}") from None
    out = []
    for n, row in enumerate(rows, start=2):
        try:
            joined = datetime.date.fromisoformat((row.get("joined") or "").strip())
        except ValueError:
            raise WaitingError(f"{path} line {n}: bad joined date") from None
        wants = (row.get("wants") or "any").strip() or "any"
        if wants not in ("full", "half", "any"):
            raise WaitingError(f'{path} line {n}: bad wants "{wants}"')
        out.append(Waiting((row.get("name") or "").strip(), joined, wants))
    return sorted(out, key=lambda w: (w.joined, w.name))
