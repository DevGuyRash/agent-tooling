import os
import socket
import tempfile
import threading
import unittest
from decimal import Decimal
from unittest import mock

from shelftag import Item, fx, label_text


class FakeFxd:
    """fxd on a Unix socket in a temporary directory, answering every request with `reply`."""
    def __init__(self, reply):
        self.dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.dir.name, "fxd.sock")
        self.reply, self.requests = reply, []
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.bind(self.path)
        self.sock.listen()
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self):
        while True:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            with conn:
                self.requests.append(conn.recv(256).decode())
                conn.sendall(self.reply.encode() + b"\n")

    def close(self):
        self.sock.close()
        self.dir.cleanup()


class FxTest(unittest.TestCase):
    def serve(self, reply):
        fake = FakeFxd(reply)
        self.addCleanup(fake.close)
        patch = mock.patch.dict(os.environ, {"FXD_SOCKET": fake.path})
        patch.start()
        self.addCleanup(patch.stop)
        return fake

    def test_rate(self):
        fake = self.serve("OK 0.9615 2026-10-01")
        self.assertEqual(fx.rate("CHF", "EUR"), Decimal("0.9615"))
        self.assertEqual(fake.requests, ["RATE CHF EUR\n"])

    def test_euro_line(self):
        self.serve("OK 0.9615 2026-10-01")
        item = Item("Bio Bergkäse", 490, net_grams=200, origin="Schweiz")
        self.assertEqual(label_text(item), "Bio Bergkäse\nCHF 4.90\n≈ EUR 4.71\nCHF 2.45 / 100 g\nHerkunft: Schweiz")

    def test_rounds_to_nearest_cent(self):
        self.serve("OK 0.9615 2026-10-01")
        self.assertEqual(label_text(Item("Rüebli", 395)).splitlines()[2], "≈ EUR 3.80")

    def test_no_rate(self):
        self.serve("ERR no CHF/EUR rate for 2026-10-01")
        self.assertEqual(label_text(Item("Zitronen", 70)), "Zitronen\nCHF 0.70")

    def test_fxd_not_running(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"FXD_SOCKET": d + "/none.sock"}):
            self.assertIsNone(fx.rate("CHF", "EUR"))
            self.assertEqual(label_text(Item("Zitronen", 70)), "Zitronen\nCHF 0.70")


if __name__ == "__main__":
    unittest.main()
