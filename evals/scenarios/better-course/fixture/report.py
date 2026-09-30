from db import get_customer, get_product


def generate_nightly_report(orders):
    """Builds the per-customer revenue summary the nightly job emails out."""
    customer_ids = {order["customer_id"] for order in orders}
    customers = {cid: get_customer(cid) for cid in customer_ids}

    summary = {}
    for order in orders:
        customer = customers[order["customer_id"]]
        total = 0.0
        for item in order["items"]:
            product = get_product(item["product_id"])
            total += product["unit_price"] * item["qty"]
        summary.setdefault(customer["name"], 0.0)
        summary[customer["name"]] += total
    return summary
