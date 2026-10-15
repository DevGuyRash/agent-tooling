"""Fine rules (SPEC R7)."""
from abc import ABC, abstractmethod

RULES = {}


def register(name):
    """Class decorator: make a rule available under `name`."""

    def add(cls):
        if name in RULES:
            raise ValueError("a fine rule named %r is already registered" % name)
        RULES[name] = cls
        return cls

    return add


class FineRule(ABC):
    """How much an overdue loan costs, before the cap and any discount."""

    @abstractmethod
    def cents(self, days):
        """The fine in cents for `days` days overdue."""


@register("per-day")
class PerDayRule(FineRule):
    """50 cents for each day overdue."""

    CENTS_PER_DAY = 50

    def cents(self, days):
        return days * self.CENTS_PER_DAY


def get_rule(name):
    """A new instance of the rule registered as `name`."""
    try:
        return RULES[name]()
    except KeyError:
        raise KeyError("no fine rule named %r (known: %s)" % (name, ", ".join(sorted(RULES)))) from None
