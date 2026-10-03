import io
import unittest

from berthbook.client import BookingClient
from berthbook.export import export_day

from .fakes import FakeTransport, booking


class ExportTests(unittest.TestCase):
    def test_sorted_by_berth_and_cancelled_left_out(self):
        rows = [booking(1, berth="P10"), booking(2, berth="P2"), booking(3, berth="A1", status="cancelled"),
                booking(4, berth="A7", status="provisional")]
        fake = FakeTransport({("/v2/bookings", frozenset({("date", "2026-08-15")})): (200, {"bookings": rows, "next": None})})
        out = io.StringIO()
        self.assertEqual(export_day(BookingClient(fake), "2026-08-15", out), 3)
        self.assertEqual(out.getvalue().splitlines(), [
            "berth,vessel,booking,arrives,departs,status",
            "A7,Boat 4,BK-20260815-0004,2026-08-15,2026-08-15,provisional",
            "P2,Boat 2,BK-20260815-0002,2026-08-15,2026-08-15,confirmed",
            "P10,Boat 1,BK-20260815-0001,2026-08-15,2026-08-15,confirmed",
        ])


if __name__ == "__main__":
    unittest.main()
