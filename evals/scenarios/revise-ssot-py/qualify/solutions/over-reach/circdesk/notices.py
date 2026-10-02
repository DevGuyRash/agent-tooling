"""The overnight notices (see ledger.py)."""
from .ledger import Ledger


def notices(loans, patrons, day):
    return Ledger(loans, patrons).notices(day)
