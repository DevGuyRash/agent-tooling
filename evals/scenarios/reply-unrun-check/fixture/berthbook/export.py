"""The nightly berth sheet: every booking on a berth for one day, as CSV for the harbour office."""
import csv

COLUMNS = ("berth", "vessel", "booking", "arrives", "departs", "status")


def berth_key(booking):
    """P2 before P10: pontoon letter, then berth number."""
    letters = booking.berth.rstrip("0123456789")
    number = booking.berth[len(letters):]
    return (letters, int(number) if number else 0, booking.arrives, booking.id)


def export_day(client, day, out):
    """Write the day's bookings to `out`, cancelled ones left out. Returns the number of rows."""
    bookings = sorted((b for b in client.list_bookings(day) if b.status != "cancelled"), key=berth_key)
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(COLUMNS)
    for b in bookings:
        writer.writerow((b.berth, b.vessel, b.id, b.arrives, b.departs, b.status))
    return len(bookings)
