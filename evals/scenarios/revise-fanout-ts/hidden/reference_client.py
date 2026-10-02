"""Calibration client for revise-fanout-ts: a correct `plugctl status`, run by the check in the same sandbox
conditions as the agent's command, to measure how long a correct client takes on this host right now.

usage: PLUGCTL_HUB=HOST:PORT python3 reference_client.py LIMIT TIMEOUT
"""
import os
import socket
import sys
from concurrent.futures import ThreadPoolExecutor


def request(addr, line, timeout):
    """The reply's lines, or None when no reply came within timeout."""
    try:
        with socket.create_connection(addr, timeout=timeout) as s:
            s.sendall(line.encode() + b"\n")
            data = b""
            while chunk := s.recv(65536):
                data += chunk
    except (socket.timeout, TimeoutError):
        return None
    return data.decode().splitlines()


def main():
    limit, timeout = int(sys.argv[1]), float(sys.argv[2])
    host, _, port = os.environ["PLUGCTL_HUB"].rpartition(":")
    addr = (host, int(port))
    try:
        lines = request(addr, "LIST", 10)
    except OSError as exc:
        print(f"plugctl: cannot read the charger list: {exc}", file=sys.stderr)
        return 2
    if not lines or not lines[0].startswith("OK "):
        print(f"plugctl: cannot read the charger list: {lines}", file=sys.stderr)
        return 2
    ids = sorted(lines[1:])
    with ThreadPoolExecutor(max_workers=limit) as pool:
        replies = list(pool.map(lambda c: request(addr, f"STATUS {c}", timeout), ids))
    free = connectors = answered = 0
    for charger, reply in zip(ids, replies):
        if reply is None:
            print(f"{charger}: no answer")
        elif reply[0].startswith("ERR "):
            print(f"{charger}: error {reply[0][4:]}")
        else:
            _, _, n, f, kw = reply[0].split()
            free, connectors, answered = free + int(f), connectors + int(n), answered + 1
            print(f"{charger}: {f} of {n} free, {kw} kW")
    print(f"total: {free} of {connectors} connectors free at {answered} of {len(ids)} chargers")
    return 0 if answered == len(ids) else 1


if __name__ == "__main__":
    sys.exit(main())
