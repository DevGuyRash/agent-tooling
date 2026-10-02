"""Today's exchange rate from fxd, the store machine's rate daemon (docs/fxd.md)."""
import os
import socket
from decimal import Decimal, InvalidOperation
from typing import Optional

DEFAULT_SOCKET = "/run/fxd/fxd.sock"
TIMEOUT = 1.0  # fxd answers in well under a millisecond


def socket_path() -> str:
    return os.environ.get("FXD_SOCKET") or DEFAULT_SOCKET


def rate(source: str, target: str) -> Optional[Decimal]:
    """What one `source` is worth in `target` today, or None when fxd is not running, does not answer in
    time, or has no rate for the pair."""
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(TIMEOUT)
            sock.connect(socket_path())
            sock.sendall(f"RATE {source} {target}\n".encode("ascii"))
            reply = b""
            while not reply.endswith(b"\n") and len(reply) < 256:
                chunk = sock.recv(256)
                if not chunk:
                    break
                reply += chunk
    except OSError:
        return None
    parts = reply.decode("ascii", "replace").split()
    if len(parts) < 2 or parts[0] != "OK":
        return None
    try:
        value = Decimal(parts[1])
    except InvalidOperation:
        return None
    return value if value.is_finite() and value > 0 else None
