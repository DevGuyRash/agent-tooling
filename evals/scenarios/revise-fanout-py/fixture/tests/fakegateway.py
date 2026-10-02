"""A stand-in for the BMS gateway, for tests: the endpoints in docs/bms-gateway.md on a local port.

    with FakeGateway({"U-0001": (-19.4, -20.0)}, defrost={"U-0002": (4.6, 3.0)}, silent={"U-0003"},
                     errors={"U-0004": 502}) as gw:
        ...  # gw.url is the base URL; gw.requests lists the paths requested

Units map to (temp_c, setpoint_c); `defrost` units are mid defrost cycle. A silent unit's reading request
gets no answer until the client hangs up (or `hold` seconds pass, then 504), the way the real gateway waits
for a dead controller. `delay` adds that many seconds before each reading's answer.
"""

import json
import select
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ZONES = ["Freezer A", "Freezer B", "Dairy cooler", "Produce cooler", "Meat walk-in", "Deli case", "Ice cream bay",
         "Floral cooler"]


class FakeGateway:
    def __init__(self, units, defrost=None, silent=(), errors=None, delay=0.0, hold=30.0):
        self.units = dict(units)
        self.defrost = dict(defrost or {})
        self.silent = set(silent)
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
        return sorted(set(self.units) | set(self.defrost) | self.silent | set(self.errors))

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
                if parts == ["v2", "units"]:
                    ids = gateway.all_ids()
                    body = {"units": [{"id": u, "zone": ZONES[i % len(ZONES)]} for i, u in enumerate(reversed(ids))]}
                    return self._send(200, body)
                if len(parts) == 4 and parts[:2] == ["v2", "units"] and parts[3] == "reading":
                    return self._reading(parts[2])
                return self._send(404, {"error": "not found"})

            def _reading(self, unit_id):
                if unit_id in gateway.silent:
                    if self._wait(gateway.hold):
                        self._send(504, {"error": "controller did not answer"})
                    return
                if gateway.delay and not self._wait(gateway.delay):
                    return
                if unit_id in gateway.errors:
                    return self._send(gateway.errors[unit_id], {"error": "controller fault"})
                if unit_id in gateway.units:
                    (temp, setpoint), defrost = gateway.units[unit_id], False
                elif unit_id in gateway.defrost:
                    (temp, setpoint), defrost = gateway.defrost[unit_id], True
                else:
                    return self._send(404, {"error": "no such unit"})
                self._send(200, {"id": unit_id, "temp_c": temp, "setpoint_c": setpoint, "defrost": defrost,
                                 "read_at": "2026-09-30T02:14:03Z"})

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
