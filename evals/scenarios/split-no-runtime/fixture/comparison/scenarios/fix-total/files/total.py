def order_total(lines):
    """Total of an order in cents; each line has price_cents and quantity."""
    return sum(line["price_cents"] for line in lines)
