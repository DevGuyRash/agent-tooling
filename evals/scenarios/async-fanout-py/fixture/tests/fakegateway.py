"""A stand-in for the dock gateway, for tests: the endpoints in docs/gateway-api.md on a local port.

    with FakeGateway({"D-0001": (3, 9), "D-0002": (0, 12)}, offline={"D-0003"}, errors={"D-0004": 502}) as gw:
        ...  # gw.url is the base URL; gw.requests lists the paths requested

Docks map to (bikes, free). An offline dock's status request gets no answer until the client hangs up (or
`hold` seconds pass, then 504), the way the real gateway waits for a dead modem. `delay` adds that many
seconds before each status answer.
"""

import json
import select
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

NAMES = ["Riverside Park", "Mill Street", "Union Station", "Old Market", "Harbor Steps", "College Green",
         "Library Square", "North Bridge", "Ferry Landing", "Elm Avenue"]


class FakeGateway:
    def __init__(self, docks, offline=(), errors=None, delay=0.0, hold=30.0):
        self.docks = dict(docks)
        self.offline = set(offline)
        self.errors = dict(errors or {})
        self.delay = delay
        self.hold = hold
        self.requests = []
        self._lock = threading.Lock()
        self._server = None
        self._thread = None

    @property
    def url(self):
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}"

    def all_ids(self):
        return sorted(set(self.docks) | self.offline | set(self.errors))

    def __enter__(self):
        gateway = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):
                pass

            def do_GET(self):
                with gateway._lock:
                    gateway.requests.append(self.path)
                parts = self.path.strip("/").split("/")
                if parts == ["v1", "docks"]:
                    ids = gateway.all_ids()
                    body = {"docks": [{"id": d, "name": NAMES[i % len(NAMES)]} for i, d in enumerate(ids)]}
                    return self._send(200, body)
                if len(parts) == 4 and parts[:2] == ["v1", "docks"] and parts[3] == "status":
                    return self._status(parts[2])
                return self._send(404, {"error": "not found"})

            def _status(self, dock_id):
                if dock_id in gateway.offline:
                    if self._wait(gateway.hold):
                        self._send(504, {"error": "dock did not answer"})
                    return
                if gateway.delay and not self._wait(gateway.delay):
                    return
                if dock_id in gateway.errors:
                    return self._send(gateway.errors[dock_id], {"error": "dock fault"})
                if dock_id not in gateway.docks:
                    return self._send(404, {"error": "no such dock"})
                bikes, free = gateway.docks[dock_id]
                self._send(200, {"id": dock_id, "bikes": bikes, "free": free, "read_at": "2026-09-30T08:14:03Z"})

            def _wait(self, seconds):
                """Wait `seconds`; False as soon as the client hangs up."""
                end = time.monotonic() + seconds
                while (left := end - time.monotonic()) > 0:
                    readable, _, _ = select.select([self.connection], [], [], left)
                    if readable and not self.connection.recv(1, 2):  # 2 == MSG_PEEK
                        self.close_connection = True
                        return False
                    if readable:
                        time.sleep(min(left, 0.05))
                return True

            def _send(self, status, body):
                data = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever, args=(0.05,), daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._server.shutdown()
        self._server.server_close()
