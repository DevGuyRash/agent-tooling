"""Hidden driver for async-few-py. Runs inside a bubblewrap sandbox with its own network and PID namespaces.

usage: python3 driver.py < CONFIG_JSON   (prints one JSON verdict as its last line)

It starts the fake backends (services.py, its own process), points STOREFRONT_*_URL at them, imports the
package under test from `code`, and calls `storefront.book_page.book_page(Backends.from_env(), isbn)` once
for each configured call, one after another, in one long-lived event loop, the way the API server runs
it. For each call it records what came back (the page, or the exception's class names and its `backend`
and `isbn`), how long the call took, and then, `grace` seconds after the call returned or raised:

- leaked_tasks: tasks created during the call that are still not done;
- changed_after: whether the page it returned has changed since it was returned;
- leaked_requests: backend requests for this call that were still in progress when the call returned and
  went on past return + grace (answered later, held, or still open), and late_requests: requests that
  started after the call returned. A request the code ends when it gives up on it (its connection closed)
  ends within the grace; one it leaves running does not.

Before the next call it cancels the leaked tasks and waits for this call's requests to end (a silent
backend answers after `hold` seconds), so one call's leftovers do not reach the next. The configuration
comes on standard input, so nothing in the sandbox can read the dataset from this process later.
"""
import asyncio
import json
import os
import subprocess
import sys
import time
import traceback


def describe_exception(exc):
    names = [c.__name__ for c in type(exc).__mro__]
    leaves = []
    if isinstance(exc, BaseExceptionGroup):
        stack = list(exc.exceptions)
        while stack:
            e = stack.pop(0)
            if isinstance(e, BaseExceptionGroup):
                stack.extend(e.exceptions)
            else:
                leaves.append(type(e).__name__)
    return {"type": type(exc).__name__, "mro": names, "backend": _attr(exc, "backend"), "isbn": _attr(exc, "isbn"),
            "leaves": leaves, "text": str(exc)[:200]}


def _attr(exc, name):
    value = getattr(exc, name, None)
    return value if isinstance(value, (str, int, float)) or value is None else repr(value)[:80]


def snapshot(value):
    try:
        return json.dumps(value, sort_keys=True)
    except (TypeError, ValueError):
        return "unserializable:" + repr(value)[:2000]


async def state(port, isbn):
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    writer.write(f"GET /state/{isbn} HTTP/1.1\r\nHost: control\r\nConnection: close\r\n\r\n".encode())
    await writer.drain()
    raw = await reader.read()
    writer.close()
    return json.loads(raw.partition(b"\r\n\r\n")[2])


async def run_calls(cfg, ports, book_page, backends):
    results = []
    me = asyncio.current_task()
    for call in cfg["calls"]:
        isbn = call["isbn"]
        before = set(asyncio.all_tasks())
        outcome, value, exc_info = None, None, None
        started = time.monotonic()
        try:
            async with asyncio.timeout(cfg["call_limit"]):
                value = await book_page(backends, isbn)
            outcome = "returned"
        except TimeoutError:
            outcome = "call limit"
        except BaseException as exc:  # noqa: BLE001 - the code under test may raise anything
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                outcome = "exit"
            else:
                outcome = "raised"
            exc_info = describe_exception(exc)
        returned = time.monotonic()
        snap = snapshot(value) if outcome == "returned" else None
        await asyncio.sleep(cfg["grace"])
        leaked = [t for t in asyncio.all_tasks() - before if t is not me and not t.done()]
        names = sorted({getattr(t.get_coro(), "__qualname__", "?") for t in leaked})[:5]
        changed = outcome == "returned" and snapshot(value) != snap
        # Leftovers end before the next call.
        for t in leaked:
            t.cancel()
        if leaked:
            await asyncio.wait(leaked, timeout=2.0)
        deadline = time.monotonic() + cfg["hold"] + 1.5
        while True:
            st = await state(ports["control"], isbn)
            if all(r[2] is not None for r in st["requests"]) or time.monotonic() > deadline:
                break
            await asyncio.sleep(0.05)
        requests = st["requests"]
        cutoff = returned + cfg["grace"]
        leaked_requests = sum(1 for _, start, end, _ in requests if start <= returned and (end is None or end > cutoff))
        late = sum(1 for _, start, _, _ in requests if start > returned)
        results.append({
            "case": call["case"], "isbn": isbn, "outcome": outcome, "elapsed": round(returned - started, 4),
            "value": snap if outcome == "returned" else None, "exception": exc_info,
            "changed_after": changed, "leaked_tasks": len(leaked), "leaked_task_names": names,
            "leaked_requests": leaked_requests, "late_requests": late,
            "requests": [[b, round(s - started, 4), None if e is None else round(e - started, 4), o]
                         for b, s, e, o in requests],
        })
    return results


def main():
    cfg = json.loads(sys.stdin.read())
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "C.UTF-8"}
    services = subprocess.Popen([sys.executable, "-I", cfg["services"]], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                env=env)
    services.stdin.write(json.dumps({"behaviors": cfg["behaviors"], "hold": cfg["hold"]}).encode())
    services.stdin.close()
    ports = json.loads(services.stdout.readline())
    verdict = {"python": list(sys.version_info[:3])}
    try:
        for name in ("catalog", "pricing", "stock", "reviews"):
            os.environ[f"STOREFRONT_{name.upper()}_URL"] = f"http://127.0.0.1:{ports[name]}"
        sys.path.insert(0, cfg["code"])
        try:
            from storefront.backends import Backends
            from storefront.book_page import book_page
            backends = Backends.from_env()
        except BaseException:  # noqa: BLE001
            verdict["import_error"] = traceback.format_exc()[-1500:]
        else:
            verdict["calls"] = asyncio.run(run_calls(cfg, ports, book_page, backends))
    finally:
        services.kill()
        services.wait()
    sys.stdout.write("\n" + json.dumps(verdict) + "\n")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
