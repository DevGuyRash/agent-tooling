#!/usr/bin/env python3
"""Recompute the venue and catering lines that are actually on the current contract, from
guest-list.csv and the rates in venue/capacity-and-fees.md and vendors/catering-quote.md, so
budget.csv can be sanity-checked against the source numbers rather than trusted on its own. This
only reproduces what's on file today -- it doesn't evaluate alternatives.

Run from the fixture root: python3 budget/calc_budget.py
"""
import csv
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

VENUE_BASE = 9500.00
INCLUDED_CAPACITY = 150
OVERFLOW_RATE_ON_FILE = 70.00  # Tented Addition -- currently on the contract addendum
CATERING_RATE_PER_HEAD = 24.00
OTHER_VENDORS_FLAT = 12000.00  # photography + florals + DJ + rentals + stationery + favors + coordinator


def confirmed_headcount(guest_list_path):
    total = 0
    with open(guest_list_path, newline="") as f:
        for row in csv.DictReader(f):
            if row["rsvp_status"].strip() == "confirmed":
                total += int(row["party_size"])
    return total


def main():
    confirmed = confirmed_headcount(ROOT / "guest-list.csv")
    overflow_guests = max(0, confirmed - INCLUDED_CAPACITY)
    catering_total = CATERING_RATE_PER_HEAD * confirmed
    venue_overflow = overflow_guests * OVERFLOW_RATE_ON_FILE
    total = VENUE_BASE + venue_overflow + catering_total + OTHER_VENDORS_FLAT

    print(f"confirmed guests: {confirmed}")
    print(f"guests over the 150 included in the base rental: {overflow_guests}")
    print(f"catering ({confirmed} x ${CATERING_RATE_PER_HEAD:.2f}/head): ${catering_total:,.2f}")
    print(f"venue overflow fee, on-file rate ({overflow_guests} x ${OVERFLOW_RATE_ON_FILE:.2f}): "
          f"${venue_overflow:,.2f}")
    print(f"other vendors (flat): ${OTHER_VENDORS_FLAT:,.2f}")
    print(f"total on the current contract: ${total:,.2f}")
    print("budget cap: $26,800.00")


if __name__ == "__main__":
    sys.exit(main())
