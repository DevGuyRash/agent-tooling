"""Against the booking simulator that `make integration` starts (compose.integration.yml).

The simulator serves the Booking API with the "august-peak" dataset; it pages exactly as production does.
"""
import os
import unittest
import urllib.request

from berthbook.client import BookingApiError, BookingClient, HttpTransport

SIM_URL = os.environ.get("BERTHBOOK_SIM_URL", "http://127.0.0.1:8089")


def setUpModule():
    request = urllib.request.Request(f"{SIM_URL}/sim/reset?dataset=august-peak", method="POST")
    with urllib.request.urlopen(request, timeout=5) as response:
        response.read()


class SimulatorTests(unittest.TestCase):
    def setUp(self):
        self.client = BookingClient(HttpTransport(SIM_URL, timeout=5))

    def test_quiet_day(self):
        self.assertEqual(len(self.client.list_bookings("2026-08-04")), 23)

    def test_busy_day_has_every_booking(self):
        bookings = self.client.list_bookings("2026-08-15")
        self.assertEqual(len(bookings), 137)
        self.assertEqual(len({b.id for b in bookings}), 137)

    def test_one_booking(self):
        self.assertEqual(self.client.get_booking("BK-20260815-0042").berth, "P14")

    def test_unknown_booking(self):
        with self.assertRaises(BookingApiError) as cm:
            self.client.get_booking("BK-19990101-0001")
        self.assertEqual(cm.exception.status, 404)


if __name__ == "__main__":
    unittest.main()
