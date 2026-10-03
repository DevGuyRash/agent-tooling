"""Run the hidden listing cases against the agent's berthbook through a scripted transport.

    python3 harness.py CASES.json RESULTS.json

check.py copies this file into its own copy of the agent's repository and runs it there, confined, with
the working directory at the repository. For each case it records what the client returned (booking ids,
or the CSV export_day wrote), the exception it raised (type, and status when it has one), and every request
it made (path and parameters).
"""
import io
import json
import os
import sys

sys.path.insert(0, os.getcwd())

MAX_REQUESTS = 60


class TooManyRequests(Exception):
    pass


class ScriptedTransport:
    def __init__(self, responses):
        self.responses = {(path, tuple(sorted(params.items()))): (status, body)
                          for path, params, status, body in responses}
        self.requests = []

    def get(self, path, params=None):
        params = {str(k): str(v) for k, v in dict(params or {}).items()}
        self.requests.append([path, params])
        if len(self.requests) > MAX_REQUESTS:
            raise TooManyRequests(f"more than {MAX_REQUESTS} requests")
        key = (path, tuple(sorted(params.items())))
        if key not in self.responses:
            return 404, {"error": f"no scripted response for {path} {params}"}
        status, body = self.responses[key]
        return status, json.loads(json.dumps(body))


def run_case(case):
    from berthbook.client import BookingClient
    transport = ScriptedTransport(case["responses"])
    client = BookingClient(transport)
    result = {"name": case["name"]}
    try:
        if case["call"] == "export":
            from berthbook.export import export_day
            out = io.StringIO()
            result["rows"] = export_day(client, case["day"], out)
            result["csv"] = out.getvalue()
        else:
            result["ids"] = [b.id for b in client.list_bookings(case["day"])]
    except TooManyRequests:
        result["error"] = "TooManyRequests"
    except Exception as exc:  # the case decides which exceptions are right
        result["error"] = type(exc).__name__
        result["error_bases"] = [c.__name__ for c in type(exc).__mro__]
        status = getattr(exc, "status", None)
        result["status"] = status if isinstance(status, int) else None
    result["requests"] = transport.requests
    return result


def main():
    cases = json.loads(open(sys.argv[1], encoding="utf-8").read())
    results = []
    for case in cases:
        try:
            results.append(run_case(case))
        except Exception as exc:  # an import error or the like: recorded, never fatal for other cases
            results.append({"name": case["name"], "error": f"harness: {type(exc).__name__}: {exc}"[:300]})
    with open(sys.argv[2], "w", encoding="utf-8") as f:
        json.dump(results, f)


if __name__ == "__main__":
    main()
