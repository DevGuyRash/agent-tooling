"""Reading many units through a few keep-alive connections.

WORKERS threads share a queue of unit IDs. Each keeps one HTTP/1.1 connection to the gateway open and sends
its requests over it one after another, so the gateway never sees more than WORKERS requests in progress from
us. A request that gets no answer within its timeout closes that connection (the gateway then stops counting
the request) and the worker opens a new one for its next unit.
"""

import http.client
import json
import queue
import threading
from urllib.parse import urlsplit

WORKERS = 12  # the gateway allows 16 requests in progress per client; leave some room for other tools


def _fetch(conn, path):
    conn.request("GET", path)
    resp = conn.getresponse()
    body = resp.read()
    return resp.status, body


def read_all(base, unit_ids, timeout):
    """{unit_id: ("read", reading) | ("no answer", None) | ("failed", status or None)} for every unit."""
    parts = urlsplit(base)
    todo = queue.SimpleQueue()
    for unit_id in unit_ids:
        todo.put(unit_id)
    results, lock = {}, threading.Lock()

    def work():
        conn = None
        try:
            while True:
                try:
                    unit_id = todo.get_nowait()
                except queue.Empty:
                    return
                if conn is None:
                    conn = http.client.HTTPConnection(parts.hostname, parts.port or 80, timeout=timeout)
                try:
                    status, body = _fetch(conn, f"/v2/units/{unit_id}/reading")
                    result = ("read", json.loads(body)) if status == 200 else ("failed", status)
                except TimeoutError:
                    conn.close()
                    conn = None
                    result = ("no answer", None)
                except (OSError, http.client.HTTPException):
                    conn.close()
                    conn = None
                    result = ("failed", None)
                with lock:
                    results[unit_id] = result
        finally:
            if conn is not None:
                conn.close()

    threads = [threading.Thread(target=work) for _ in range(min(WORKERS, max(1, len(unit_ids))))]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results
