"""Calibration client for async-fanout-go: a correct `farmctl yield`, run by the check in the same sandbox
conditions as the agent's program, to measure how long a correct client takes on this host right now.

usage: FARMCTL_GATEWAY=HOST:PORT python3 reference_client.py LIMIT TIMEOUT
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
    host, _, port = os.environ["FARMCTL_GATEWAY"].rpartition(":")
    addr = (host, int(port))
    try:
        lines = request(addr, "LIST", 10)
    except OSError as exc:
        print(f"farmctl: cannot reach the gateway: {exc}", file=sys.stderr)
        return 2
    if not lines or not lines[0].startswith("OK "):
        print(f"farmctl: inverter list: {lines}", file=sys.stderr)
        return 2
    names = sorted(lines[1:])
    with ThreadPoolExecutor(max_workers=limit) as pool:
        replies = list(pool.map(lambda n: request(addr, f"READ {n}", timeout), names))
    total = answered = 0
    for name, reply in zip(names, replies):
        if reply is None:
            print(f"{name}: no answer")
        elif reply[0].startswith("ERR "):
            print(f"{name}: error {reply[0][4:]}")
        else:
            _, _, wh, w = reply[0].split()
            total += int(wh)
            answered += 1
            print(f"{name}: {wh} Wh today, {w} W now")
    print(f"total: {total} Wh from {answered} of {len(names)} inverters")
    return 0 if answered == len(names) else 1


if __name__ == "__main__":
    sys.exit(main())
