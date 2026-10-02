"""The desk receipt (see ledger.py)."""
from .ledger import Ledger


def receipt(loans, loan_id):
    return Ledger(loans).receipt(loan_id)
