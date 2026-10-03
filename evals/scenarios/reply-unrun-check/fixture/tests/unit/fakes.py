"""A transport that answers from a script instead of the network."""


class FakeTransport:
    def __init__(self, responses):
        """responses: {(path, frozenset(params.items())): (status, body)}"""
        self.responses = responses
        self.requests = []

    def get(self, path, params=None):
        params = dict(params or {})
        self.requests.append((path, params))
        key = (path, frozenset(params.items()))
        if key not in self.responses:
            return 404, {"error": f"no fake response for {path} {params}"}
        return self.responses[key]


def booking(n, day="2026-08-15", berth=None, status="confirmed"):
    return {"id": f"BK-{day.replace('-', '')}-{n:04d}", "berth": berth or f"P{n % 30 + 1:02d}",
            "vessel": f"Boat {n}", "arrives": day, "departs": day, "status": status}
