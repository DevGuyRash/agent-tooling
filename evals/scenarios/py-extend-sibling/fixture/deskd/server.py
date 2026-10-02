"""The JSON API the dashboard reads: GET /tickets and GET /tickets/ID."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from deskd.views import ticket_view


def make_handler(tickets, settings):
    by_id = {t.id: t for t in tickets}

    class Handler(BaseHTTPRequestHandler):
        server_version = "deskd"

        def _send(self, status, body):
            data = (json.dumps(body) + "\n").encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            parts = [p for p in self.path.split("?", 1)[0].split("/") if p]
            if parts == ["tickets"]:
                self._send(200, [ticket_view(t, settings) for t in tickets])
            elif len(parts) == 2 and parts[0] == "tickets" and parts[1].isdigit() and int(parts[1]) in by_id:
                self._send(200, ticket_view(by_id[int(parts[1])], settings))
            else:
                self._send(404, {"error": "not found"})

        def log_message(self, format, *args):
            pass

    return Handler


def make_server(tickets, settings, host="127.0.0.1", port=8080):
    return ThreadingHTTPServer((host, port), make_handler(tickets, settings))


def serve(tickets, settings, host="127.0.0.1", port=8080):
    with make_server(tickets, settings, host, port) as server:
        server.serve_forever()
