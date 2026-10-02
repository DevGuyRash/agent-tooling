"""Today's exchange rate from fxd, the store machine's rate daemon (docs/fxd.md)."""
import asyncio
import os
from decimal import Decimal, InvalidOperation
from typing import Optional

DEFAULT_SOCKET = "/run/fxd/fxd.sock"
TIMEOUT = 1.0


async def rate(source: str, target: str) -> Optional[Decimal]:
    """What one `source` is worth in `target` today, or None when fxd is not running or has no rate."""
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_unix_connection(os.environ.get("FXD_SOCKET") or DEFAULT_SOCKET), TIMEOUT)
    except (OSError, asyncio.TimeoutError):
        return None
    try:
        writer.write(f"RATE {source} {target}\n".encode("ascii"))
        await writer.drain()
        reply = await asyncio.wait_for(reader.readline(), TIMEOUT)
    except (OSError, asyncio.TimeoutError):
        return None
    finally:
        writer.close()
    parts = reply.decode("ascii", "replace").split()
    if len(parts) < 2 or parts[0] != "OK":
        return None
    try:
        return Decimal(parts[1])
    except InvalidOperation:
        return None
