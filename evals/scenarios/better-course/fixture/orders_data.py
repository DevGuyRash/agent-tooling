"""The night's fixed order set: a few hundred orders across a dozen customers and
thirty products.
"""
import random

CUSTOMER_IDS = list(range(1, 13))
PRODUCT_IDS = list(range(1, 31))


def load_orders(seed=20260101, count=260):
    rng = random.Random(seed)
    orders = []
    for order_id in range(1, count + 1):
        customer_id = rng.choice(CUSTOMER_IDS)
        item_count = rng.randint(4, 9)
        items = [{"product_id": rng.choice(PRODUCT_IDS), "qty": rng.randint(1, 5)} for _ in range(item_count)]
        orders.append({"id": order_id, "customer_id": customer_id, "items": items})
    return orders
