"""Sweep every dock with a few worker threads, each keeping one connection to the gateway open.

Eight workers stay well inside the gateway's per-client limit of 16 requests in progress
(docs/gateway-api.md). Each worker reuses its keep-alive connection; when a dock does not answer within
OFFLINE_AFTER seconds the worker closes that connection (the gateway stops counting the request) and opens a
fresh one for its next dock.
"""

import http.client
import json
import queue
import socket
import threading
from urllib.parse import urlsplit

WORKERS = 8
OFFLINE_AFTER = 2.0


class _Worker(threading.Thread):
    def __init__(self, host, port, jobs, results):
        super().__init__(daemon=True)
        self.host, self.port, self.jobs, self.results = host, port, jobs, results
        self.conn = None

    def _connection(self):
        if self.conn is None:
            self.conn = http.client.HTTPConnection(self.host, self.port, timeout=OFFLINE_AFTER)
        return self.conn

    def _drop(self):
        if self.conn is not None:
            self.conn.close()
            self.conn = None

    def _read(self, dock_id):
        for attempt in (1, 2):  # a kept-alive connection the gateway closed in the meantime: reconnect once
            conn = self._connection()
            try:
                conn.request("GET", f"/v1/docks/{dock_id}/status")
                resp = conn.getresponse()
                body = resp.read()
            except (TimeoutError, socket.timeout):
                self._drop()
                return ("offline", None)
            except (http.client.RemoteDisconnected, ConnectionResetError, BrokenPipeError):
                self._drop()
                if attempt == 2:
                    return ("failed", "connection lost")
                continue
            if resp.will_close:
                self._drop()
            if resp.status != 200:
                return ("failed", f"HTTP {resp.status}")
            return ("ok", json.loads(body))
        return ("failed", "connection lost")

    def run(self):
        while True:
            item = self.jobs.get()
            if item is None:
                self._drop()
                return
            index, dock_id = item
            self.results[index] = self._read(dock_id)


def read_all(base, dock_ids):
    """[(outcome, payload)] in the order of dock_ids: ("ok", status), ("offline", None), ("failed", reason)."""
    parts = urlsplit(base)
    jobs, results = queue.Queue(), [None] * len(dock_ids)
    workers = [_Worker(parts.hostname, parts.port or 80, jobs, results) for _ in range(min(WORKERS, len(dock_ids)))]
    for w in workers:
        w.start()
    for item in enumerate(dock_ids):
        jobs.put(item)
    for _ in workers:
        jobs.put(None)
    for w in workers:
        w.join()
    return results
