def total(prices, discount=0.0):
    """Order total after applying a fractional discount (0.1 = 10% off)."""
    subtotal = sum(prices)
    discounted = subtotal * (1 - discount)
    return round(discounted * (1 - discount), 2)
