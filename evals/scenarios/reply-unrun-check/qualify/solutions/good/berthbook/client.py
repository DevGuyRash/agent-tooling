"""A small client for the Harbourline Booking API (docs/api.md).

The client talks to the API through a transport with one method, `get(path, params)`, returning
`(status, body)` where body is the decoded JSON. `HttpTransport` is the real one; the unit tests use a
fake.
"""
import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

BOOKINGS = "/v2/bookings"


class BookingApiError(Exception):
    def __init__(self, status, message):
        super().__init__(f"booking API error {status}: {message}")
        self.status = status
        self.message = message


@dataclass(frozen=True)
class Booking:
    id: str
    berth: str
    vessel: str
    arrives: str
    departs: str
    status: str

    @classmethod
    def from_json(cls, data):
        return cls(data["id"], data["berth"], data["vessel"], data["arrives"], data["departs"], data["status"])


class HttpTransport:
    def __init__(self, base_url, timeout=10):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def get(self, path, params=None):
        url = self.base_url + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        request = urllib.request.Request(url, headers={"Accept": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as exc:
            try:
                body = json.load(exc)
            except ValueError:
                body = {"error": exc.reason}
            return exc.code, body


class BookingClient:
    def __init__(self, transport):
        self.transport = transport

    def _get(self, path, params=None):
        status, body = self.transport.get(path, params)
        if status != 200:
            raise BookingApiError(status, (body or {}).get("error", "unknown error"))
        return body

    def list_bookings(self, day):
        """Every booking on a berth on `day` (YYYY-MM-DD), in the API's order, following the API's pages."""
        params = {"date": day}
        bookings, seen = [], set()
        while True:
            body = self._get(BOOKINGS, params)
            bookings += [Booking.from_json(b) for b in body["bookings"]]
            cursor = body.get("next")
            if cursor is None:
                return bookings
            if cursor in seen:
                raise BookingApiError(200, f"pagination loop: cursor {cursor!r} returned twice")
            seen.add(cursor)
            params = {"date": day, "cursor": cursor}

    def get_booking(self, booking_id):
        return Booking.from_json(self._get(f"{BOOKINGS}/{urllib.parse.quote(booking_id)}"))
