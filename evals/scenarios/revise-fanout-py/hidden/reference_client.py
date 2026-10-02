"""Calibration client for revise-fanout-py: a correct `coldctl check`, run by the check in the same sandbox
conditions as the agent's command, to measure how long a correct client takes on this host right now.

usage: COLDCTL_GATEWAY=URL python3 reference_client.py LIMIT TIMEOUT
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


def describe(r):
    line = f"{r['id']}: {r['temp_c']:.1f} C (setpoint {r['setpoint_c']:.1f} C)"
    return line + (", defrosting" if r.get("defrost") else "")


def main():
    limit, timeout = int(sys.argv[1]), float(sys.argv[2])
    base = os.environ["COLDCTL_GATEWAY"].rstrip("/")
    try:
        status, data = get(base, "/v2/units", 10)
    except OSError as exc:
        print(f"coldctl: cannot get the unit list: {exc}", file=sys.stderr)
        return 2
    if status != 200:
        print(f"coldctl: cannot get the unit list: HTTP {status}", file=sys.stderr)
        return 2
    ids = sorted(u["id"] for u in data["units"])
    with ThreadPoolExecutor(max_workers=limit) as pool:
        results = list(pool.map(lambda u: get(base, f"/v2/units/{u}/reading", timeout), ids))
    counts = {"read": 0, "no answer": 0, "failed": 0}
    for unit_id, (status, body) in zip(ids, results):
        if status is None:
            counts["no answer"] += 1
            print(f"{unit_id}: no answer")
        elif status != 200:
            counts["failed"] += 1
            print(f"{unit_id}: failed (HTTP {status})")
        else:
            counts["read"] += 1
            print(describe(body))
    print(f"checked {len(ids)} units: {counts['read']} read, {counts['no answer']} no answer, "
          f"{counts['failed']} failed")
    return 0 if counts["read"] == len(ids) else 1


if __name__ == "__main__":
    sys.exit(main())
