import os

import pytest


@pytest.fixture
def provider_key():
    key = os.environ.get("STRIPE_TEST_KEY")
    if not key:
        raise RuntimeError("STRIPE_TEST_KEY is not set")
    return key


def test_charge_roundtrip(provider_key):
    from ledgerkit import Ledger
    led = Ledger()
    led.post("stripe", "revenue", 1200)
    assert led.balance("stripe") == 1200
