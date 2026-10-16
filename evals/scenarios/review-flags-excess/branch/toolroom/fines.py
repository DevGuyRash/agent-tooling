"""The fine for an overdue loan (SPEC R7)."""
from .rules import get_rule

ROUNDING_MODES = ("nearest", "up", "down", "even")


def round_div(numerator, denominator, rounding="nearest"):
    """numerator / denominator as a whole number of cents, rounded the way `rounding` says."""
    cents, remainder = divmod(numerator, denominator)
    if remainder == 0 or rounding == "down":
        return cents
    if rounding == "up":
        return cents + 1
    twice = 2 * remainder
    if twice > denominator:
        return cents + 1
    if twice == denominator and (rounding == "nearest" or cents % 2 == 1):
        return cents + 1
    return cents


def fine_for(days, tool, member, rounding="nearest"):
    """The fine in cents for a loan `days` days overdue on `tool`, held by `member`."""
    fine = min(get_rule("per-day").cents(days), tool.value)
    if member.status == "supporter":
        fine = round_div(3 * fine, 4, rounding)
    return fine
