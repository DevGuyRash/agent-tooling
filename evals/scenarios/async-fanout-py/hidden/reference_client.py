"""Calibration client for async-fanout-py: a correct sweep, run by the check in the same sandbox conditions as
the agent's command, to measure how long a correct client takes on this host right now.

usage: DOCKCTL_GATEWAY=URL python3 reference_client.py LIMIT TIMEOUT
"""
import http.client
import json
import os
import socket
import sys
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit


def get(base, path, timeout):
    """(status, decoded JSON or None); status None when no answer came within timeout."""
    parts = urlsplit(base)
    conn = http.client.HTTPConnection(parts.hostname, parts.port or 80, timeout=timeout)
    try:
        conn.request("GET", path)
        resp = conn.getresponse()
        body = resp.read()
        return resp.status, (json.loads(body) if resp.status == 200 else None)
    except (socket.timeout, TimeoutError):
        return None, None
    finally:
        conn.close()


def main():
    limit, timeout = int(sys.argv[1]), float(sys.argv[2])
    base = os.environ["DOCKCTL_GATEWAY"].rstrip("/")
    try:
        status, data = get(base, "/v1/docks", 10)
    except OSError as exc:
        print(f"dockctl: cannot reach the gateway: {exc}", file=sys.stderr)
        return 2
    if status != 200:
        print(f"dockctl: dock list: HTTP {status}", file=sys.stderr)
        return 2
    ids = sorted(d["id"] for d in data["docks"])
    with ThreadPoolExecutor(max_workers=limit) as pool:
        results = list(pool.map(lambda d: get(base, f"/v1/docks/{d}/status", timeout), ids))
    counts = {"ok": 0, "offline": 0, "failed": 0}
    for dock_id, (status, body) in zip(ids, results):
        if status is None:
            counts["offline"] += 1
            print(f"{dock_id}: offline")
        elif status != 200:
            counts["failed"] += 1
            print(f"{dock_id}: failed (HTTP {status})")
        else:
            counts["ok"] += 1
            bikes = body["bikes"]
            print(f"{dock_id}: {bikes} {'bike' if bikes == 1 else 'bikes'}, {body['free']} free")
    print(f"swept {len(ids)} docks: {counts['ok']} ok, {counts['offline']} offline, {counts['failed']} failed")
    return 0 if counts["offline"] == counts["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
