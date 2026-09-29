class Inventory:
    """Item counts by name."""

    def __init__(self):
        self._counts = {}

    def add(self, name, qty=1):
        if qty <= 0:
            raise ValueError("qty must be positive")
        self._counts[name] = self._counts.get(name, 0) + qty

    def remove(self, name, qty=1):
        have = self._counts.get(name, 0)
        if qty > have:
            raise ValueError(f"only {have} {name} in stock")
        self._counts[name] = have - qty

    def count(self, name):
        return self._counts.get(name, 0)
