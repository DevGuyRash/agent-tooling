"""`dockctl sweep`: read every dock's status at once, within the gateway's per-client limit.

Status reads go out over asyncio streams, at most GATEWAY_LIMIT at a time (docs/gateway-api.md). A read that
has not been answered within OFFLINE_AFTER seconds is given up and its connection closed, which also frees
its place under the gateway's limit.
"""

import asyncio
import json
from urllib.parse import urlsplit

GATEWAY_LIMIT = 16
OFFLINE_AFTER = 2.0
LIST_TIMEOUT = 10.0


class HttpStatus(Exception):
    def __init__(self, status):
        super().__init__(f"HTTP {status}")
        self.status = status


async def _get_json(host, port, path):
    reader, writer = await asyncio.open_connection(host, port)
    try:
        writer.write(f"GET {path} HTTP/1.1\r\nHost: {host}:{port}\r\nConnection: close\r\n\r\n".encode())
        await writer.drain()
        head = await reader.readuntil(b"\r\n\r\n")
        lines = head.decode("latin-1").split("\r\n")
        status = int(lines[0].split(" ", 2)[1])
        length = None
        for line in lines[1:]:
            name, _, value = line.partition(":")
            if name.strip().lower() == "content-length":
                length = int(value.strip())
        body = await (reader.readexactly(length) if length is not None else reader.read())
        if status != 200:
            raise HttpStatus(status)
        return json.loads(body)
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except OSError:
            pass


def describe_status(status):
    bikes = status["bikes"]
    return f"{status['id']}: {bikes} {'bike' if bikes == 1 else 'bikes'}, {status['free']} free"


async def _read_dock(limit, host, port, dock_id):
    async with limit:
        try:
            status = await asyncio.wait_for(_get_json(host, port, f"/v1/docks/{dock_id}/status"), OFFLINE_AFTER)
        except TimeoutError:
            return "offline", f"{dock_id}: offline"
        except HttpStatus as exc:
            return "failed", f"{dock_id}: failed (HTTP {exc.status})"
        except (OSError, asyncio.IncompleteReadError, ValueError) as exc:
            return "failed", f"{dock_id}: failed ({type(exc).__name__})"
    return "ok", describe_status(status)


async def _sweep(base):
    parts = urlsplit(base)
    host, port = parts.hostname, parts.port or 80
    docks = await asyncio.wait_for(_get_json(host, port, "/v1/docks"), LIST_TIMEOUT)
    ids = sorted(d["id"] for d in docks["docks"])
    limit = asyncio.Semaphore(GATEWAY_LIMIT)
    return ids, await asyncio.gather(*(_read_dock(limit, host, port, d) for d in ids))


def sweep(base, out):
    """Print the sweep report to `out`; returns the exit status (0 all read, 1 some not, 2 no dock list)."""
    try:
        ids, results = asyncio.run(_sweep(base))
    except (OSError, TimeoutError, HttpStatus, asyncio.IncompleteReadError, ValueError) as exc:
        print(f"dockctl: cannot get the dock list from {base}: {exc}", file=__import__("sys").stderr)
        return 2
    counts = {"ok": 0, "offline": 0, "failed": 0}
    for outcome, line in results:
        counts[outcome] += 1
        print(line, file=out)
    print(f"swept {len(ids)} docks: {counts['ok']} ok, {counts['offline']} offline, {counts['failed']} failed",
          file=out)
    return 0 if counts["ok"] == len(ids) else 1
