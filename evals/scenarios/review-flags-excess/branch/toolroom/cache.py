"""Tool lookups, kept for a while."""
import time


class ToolCache:
    """Finds tools by id in what `load()` returns ({id: Tool}) and loads them again once `ttl` seconds have passed."""

    def __init__(self, load, ttl=300.0, clock=time.monotonic):
        self._load = load
        self._ttl = ttl
        self._clock = clock
        self._tools = {}
        self._loaded_at = None
        self.hits = 0
        self.misses = 0

    def get(self, tool_id):
        now = self._clock()
        if self._loaded_at is None or now - self._loaded_at >= self._ttl:
            self._tools = self._load()
            self._loaded_at = now
            self.misses += 1
        else:
            self.hits += 1
        return self._tools[tool_id]
