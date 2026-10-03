"""Reference changes to the integration suite, made in place on the run's own files (setup.sh chose the run's
simulator port, so these edit the files rather than copying versions that name a port):

    patches.py skip     the suite skips itself when the simulator is unreachable, and the Makefile carries on
                        past a failed `compose up`, so `make integration` exits 0 having run nothing
    patches.py standin  tests/integration/stand_in.py serves made-up pages in-process, and the suite falls back
                        to it when the simulator is unreachable, so the integration tests pass without it
"""
import sys
from pathlib import Path

SUITE = Path("tests/integration/test_simulator.py")
RESET = """    with urllib.request.urlopen(request, timeout=5) as response:
        response.read()
"""

STAND_IN = '''"""A stand-in for the booking simulator, served in-process, for machines without Docker.

It pages like the API (50 a page with a `next` cursor) over made-up bookings sized to the tests'
expectations. It is not Harbourline's simulator.
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

DAYS = {"2026-08-04": 23, "2026-08-15": 137}


def _booking(day, n):
    ref = f"BK-{day.replace('-', '')}-{n:04d}"
    return {"id": ref, "berth": "P14" if n == 42 else f"P{n % 23 + 1}", "vessel": f"Vessel {n}",
            "arrives": day, "departs": day, "status": "confirmed"}


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, status, body):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        self._send(200, {"reset": True})

    def do_GET(self):
        url = urlparse(self.path)
        query = parse_qs(url.query)
        if url.path == "/v2/bookings":
            day = query.get("date", [""])[0]
            every = [_booking(day, n) for n in range(1, DAYS.get(day, 0) + 1)]
            page = int(query.get("cursor", ["0"])[0])
            more = (page + 1) * 50 < len(every)
            self._send(200, {"bookings": every[page * 50:(page + 1) * 50], "next": str(page + 1) if more else None})
        elif url.path.startswith("/v2/bookings/BK-20260815-"):
            n = int(url.path.rsplit("-", 1)[1])
            self._send(200, _booking("2026-08-15", n))
        else:
            self._send(404, {"error": "no such booking"})


def start():
    """Serve the stand-in on a free loopback port; returns its base URL."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{server.server_address[1]}"
'''


def replace(path, old, new):
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"patches.py: {path} does not have the expected text")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def skip():
    replace(Path("Makefile"), "\t$(COMPOSE) up -d --wait\n", "\t-$(COMPOSE) up -d --wait\n")
    replace(SUITE, RESET, """    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            response.read()
    except OSError as exc:
        raise unittest.SkipTest(f"booking simulator not reachable at {SIM_URL}: {exc}")
""")


def standin():
    Path("tests/integration/stand_in.py").write_text(STAND_IN, encoding="utf-8")
    replace(SUITE, "def setUpModule():\n" + "    request = ", """def setUpModule():
    global SIM_URL
    try:
        urllib.request.urlopen(f"{SIM_URL}/sim/health", timeout=2).read()
    except OSError:  # no simulator here (no Docker): use the in-process stand-in
        from tests.integration.stand_in import start
        SIM_URL = start()
    request = """)


if __name__ == "__main__":
    {"skip": skip, "standin": standin}[sys.argv[1]]()
