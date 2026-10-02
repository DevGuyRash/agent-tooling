import json
import threading
import unittest
import urllib.request
from pathlib import Path

from deskd import settings, store
from deskd.server import make_server

ROOT = Path(__file__).resolve().parents[1]


class ServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tickets = store.load(ROOT / "tests" / "data" / "tickets.jsonl")
        cls.server = make_server(tickets, settings.load(ROOT / "config"), port=0)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def get(self, path):
        try:
            with urllib.request.urlopen(self.base + path, timeout=10) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_one_ticket(self):
        status, body = self.get("/tickets/4177")
        self.assertEqual(status, 200)
        self.assertEqual(body["subject"], "Cannot reset password")

    def test_all(self):
        status, body = self.get("/tickets")
        self.assertEqual([t["id"] for t in body], [4101, 4177, 4182, 4190, 4195])

    def test_missing(self):
        self.assertEqual(self.get("/tickets/1")[0], 404)


if __name__ == "__main__":
    unittest.main()
