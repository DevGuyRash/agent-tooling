"""Stand-ins for the two remote calls the nightly job makes: one to the customer
service, one to the product catalog. Each call takes a fixed slice of wall-clock
time (standing in for a network round trip) and is logged, so bench.py can show
how many round trips a run actually made.
"""
import time

CALL_LOG = []

_LATENCY_S = 0.0004

_CUSTOMERS = {
    1: {"id": 1, "name": "Atlas Freight", "region": "west"},
    2: {"id": 2, "name": "Blue Harbor Co", "region": "east"},
    3: {"id": 3, "name": "Cedar Point Supply", "region": "midwest"},
    4: {"id": 4, "name": "Delta Grain Co-op", "region": "south"},
    5: {"id": 5, "name": "Echo Valley Foods", "region": "west"},
    6: {"id": 6, "name": "Fairview Hardware", "region": "midwest"},
    7: {"id": 7, "name": "Granite Peak Retail", "region": "west"},
    8: {"id": 8, "name": "Harbor Light Traders", "region": "east"},
    9: {"id": 9, "name": "Ironwood Distributors", "region": "south"},
    10: {"id": 10, "name": "Juniper Lane Market", "region": "midwest"},
    11: {"id": 11, "name": "Kettle Creek Goods", "region": "east"},
    12: {"id": 12, "name": "Lonestar Provisions", "region": "south"},
}

_PRODUCTS = {pid: {"id": pid, "sku": f"SKU-{pid:04d}", "unit_price": 3.5 + (pid % 11)}
             for pid in range(1, 31)}


def get_customer(customer_id):
    """One round trip to the customer service."""
    time.sleep(_LATENCY_S)
    CALL_LOG.append(("customer", customer_id))
    return _CUSTOMERS[customer_id]


def get_product(product_id):
    """One round trip to the catalog service."""
    time.sleep(_LATENCY_S)
    CALL_LOG.append(("product", product_id))
    return _PRODUCTS[product_id]


def reset_call_log():
    CALL_LOG.clear()
