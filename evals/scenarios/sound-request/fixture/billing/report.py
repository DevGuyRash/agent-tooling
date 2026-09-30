"""Builds the nightly order digest: for each order, attach the customer's plan tier."""

from .directory import UserDirectory


def generate_report(orders, directory: UserDirectory):
    lines = []
    for order in orders:
        user = directory.find_by_email(order["email"])
        plan = user.plan if user else "unknown"
        lines.append(f"{order['id']},{order['email']},{plan},{order['amount']}")
    return "\n".join(lines)
