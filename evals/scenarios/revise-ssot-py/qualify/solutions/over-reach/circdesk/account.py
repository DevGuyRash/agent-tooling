"""The kiosk's account view (see ledger.py)."""
from .ledger import Ledger


def account(loans, patrons, patron_id, day):
    return Ledger(loans, patrons).account(patron_id, day)
