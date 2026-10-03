from total import order_total


def test_single_item():
    assert order_total([{"price_cents": 250, "quantity": 1}]) == 250
