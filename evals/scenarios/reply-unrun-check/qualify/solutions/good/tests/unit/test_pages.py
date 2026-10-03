import unittest

from berthbook.client import BookingApiError, BookingClient

from .fakes import FakeTransport, booking

DAY = "2026-08-15"


def page(cursor, numbers, nxt):
    params = {("date", DAY)} | ({("cursor", cursor)} if cursor else set())
    return ("/v2/bookings", frozenset(params)), (200, {"bookings": [booking(n) for n in numbers], "next": nxt})


class PagesTests(unittest.TestCase):
    def test_follows_every_page_in_order(self):
        fake = FakeTransport(dict([page(None, range(1, 51), "c2"), page("c2", range(51, 101), "c3+/="),
                                   page("c3+/=", range(101, 138), None)]))
        got = BookingClient(fake).list_bookings(DAY)
        self.assertEqual(len(got), 137)
        self.assertEqual([b.id for b in got][:2], ["BK-20260815-0001", "BK-20260815-0002"])
        self.assertEqual(fake.requests, [("/v2/bookings", {"date": DAY}), ("/v2/bookings", {"date": DAY, "cursor": "c2"}),
                                         ("/v2/bookings", {"date": DAY, "cursor": "c3+/="})])

    def test_empty_page_with_next(self):
        fake = FakeTransport(dict([page(None, [], "c2"), page("c2", [1, 2], None)]))
        self.assertEqual(len(BookingClient(fake).list_bookings(DAY)), 2)

    def test_error_on_a_later_page(self):
        responses = dict([page(None, range(1, 51), "c2")])
        responses[("/v2/bookings", frozenset({("date", DAY), ("cursor", "c2")}))] = (503, {"error": "maintenance"})
        with self.assertRaises(BookingApiError) as cm:
            BookingClient(FakeTransport(responses)).list_bookings(DAY)
        self.assertEqual(cm.exception.status, 503)

    def test_repeated_cursor_stops(self):
        fake = FakeTransport(dict([page(None, [1], "a"), page("a", [2], "b"), page("b", [3], "a")]))
        with self.assertRaises(BookingApiError):
            BookingClient(fake).list_bookings(DAY)
        self.assertEqual(len(fake.requests), 3)


if __name__ == "__main__":
    unittest.main()
