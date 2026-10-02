"""Today's exchange rate from fxd (docs/fxd.md), asked asynchronously and usable from any caller."""
import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal, InvalidOperation
from typing import Optional

DEFAULT_SOCKET = "/run/fxd/fxd.sock"
TIMEOUT = 1.0
_helper = ThreadPoolExecutor(max_workers=2, thread_name_prefix="shelftag-fx")


async def _ask(source: str, target: str) -> Optional[Decimal]:
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
        value = Decimal(parts[1])
    except InvalidOperation:
        return None
    return value if value.is_finite() and value > 0 else None


def rate(source: str, target: str) -> Optional[Decimal]:
    """What one `source` is worth in `target`, or None. Callable from plain code, threads, and coroutines:
    inside a running event loop the request runs on a helper thread with a loop of its own."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_ask(source, target))
    return _helper.submit(asyncio.run, _ask(source, target)).result()
