import unittest

from berthbook.client import BookingApiError, BookingClient

from .fakes import FakeTransport, booking


def listing(day, params_extra=()):
    return ("/v2/bookings", frozenset({("date", day), *params_extra}))


class ListBookingsTests(unittest.TestCase):
    def test_one_page(self):
        fake = FakeTransport({listing("2026-08-03"): (200, {"bookings": [booking(1), booking(2)], "next": None})})
        got = BookingClient(fake).list_bookings("2026-08-03")
        self.assertEqual([b.id for b in got], ["BK-20260815-0001", "BK-20260815-0002"])
        self.assertEqual(fake.requests, [("/v2/bookings", {"date": "2026-08-03"})])

    def test_before_pages_existed(self):
        fake = FakeTransport({listing("2026-08-03"): (200, {"bookings": [booking(7)]})})
        self.assertEqual(len(BookingClient(fake).list_bookings("2026-08-03")), 1)

    def test_error(self):
        fake = FakeTransport({listing("2026-13-01"): (400, {"error": "bad date"})})
        with self.assertRaises(BookingApiError) as cm:
            BookingClient(fake).list_bookings("2026-13-01")
        self.assertEqual((cm.exception.status, cm.exception.message), (400, "bad date"))


class GetBookingTests(unittest.TestCase):
    def test_found(self):
        fake = FakeTransport({("/v2/bookings/BK-1", frozenset()): (200, booking(1))})
        self.assertEqual(BookingClient(fake).get_booking("BK-1").vessel, "Boat 1")

    def test_missing(self):
        fake = FakeTransport({("/v2/bookings/BK-9", frozenset()): (404, {"error": "no such booking"})})
        with self.assertRaises(BookingApiError) as cm:
            BookingClient(fake).get_booking("BK-9")
        self.assertEqual(cm.exception.status, 404)


if __name__ == "__main__":
    unittest.main()
