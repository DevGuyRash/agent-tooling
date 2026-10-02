"""Deterministic booking exports for the hidden checks:

    python3 data.py BOOKINGS SEED OUT.csv [REPEATS]   writes an export of about BOOKINGS upcoming bookings

Given REPEATS, the export is one that went wrong (see broken()): its lines are out of reference order and
REPEATS of them repeat a reference given thousands of lines earlier, so the export is invalid.

The city's leisure centres with about one facility per 2,200 bookings (about 1,100 at 2.4 million), each a
squash court (40-minute slots), a pool lane (30), a studio, a hall, or a pitch (60), booked on a grid of
slots from 2026-10-01 to 2027-07-31, so ordinary bookings never overlap. On top of that, about one booking in
150 is made at a desk at an off-grid time across one or two slots (a third of them with the facility code
typed in lower case or with spaces), and about one in 2,000 is a club's block booking of five to eight
hours over many slots. About 4% are cancelled and 6% provisional. Bookings are listed in reference order, the
order they were made in, which is unrelated to their dates.
"""
import random
import sys
from datetime import date, timedelta
from pathlib import Path

CENTRES = ["KGS", "RVP", "ASH", "MDW", "NTH", "CAN", "HBR", "WSD", "BRK", "ELM", "GRN", "OAK", "PRT", "STN"]
# kind: (slot minutes, first slot, last slot start), in minutes after midnight
KINDS = {"SQ": (40, 7 * 60, 21 * 60 + 20), "POOL-L": (30, 6 * 60 + 30, 21 * 60 + 30), "ST": (60, 7 * 60, 21 * 60),
         "HALL": (60, 8 * 60, 21 * 60), "PITCH-": (60, 9 * 60, 21 * 60)}
KIND_WEIGHTS = [("SQ", 30), ("POOL-L", 30), ("ST", 15), ("HALL", 10), ("PITCH-", 15)]
FIRST_DAY, DAYS = date(2026, 10, 1), 304
HEADER = "ref,facility,date,start,end,status,booked_by"


def _clock(m):
    return f"{m // 60:02d}:{m % 60:02d}"


def _facilities(rng, count):
    out, numbers = [], {}
    kinds = [k for k, w in KIND_WEIGHTS for _ in range(w)]
    for i in range(count):
        centre = CENTRES[i % len(CENTRES)] if i < len(CENTRES) * 4 else rng.choice(CENTRES)
        kind = rng.choice(kinds)
        numbers[(centre, kind)] = numbers.get((centre, kind), 0) + 1
        n = numbers[(centre, kind)]
        name = f"{centre}-{kind}{n}" if kind != "PITCH-" else f"{centre}-PITCH-{n}"
        out.append((name, kind))
    return out


def _typed(rng, code):
    """A facility code as desk staff type it."""
    choice = rng.randrange(3)
    if choice == 0:
        return code.lower()
    if choice == 1:
        return code.replace("-", " - ", 1)
    return code.lower().replace("-", " -", 1)


def _status(rng):
    r = rng.random()
    return "cancelled" if r < 0.04 else "provisional" if r < 0.10 else "confirmed"


def generate(bookings, seed):
    rng = random.Random(seed)
    facilities = _facilities(rng, max(6, bookings // 2200))
    days = [(FIRST_DAY + timedelta(days=d)).isoformat() for d in range(DAYS)]
    per_day = bookings / (len(facilities) * DAYS)
    rows = []  # (facility as written, date, start, end, status, booked_by)
    for name, kind in facilities:
        length, first, last = KINDS[kind]
        slots = list(range(first, last + 1, length))
        for day in days:
            k = min(len(slots), int(rng.random() * 2 * per_day + 0.5))
            for start in rng.sample(slots, k):
                who = f"M{rng.randrange(1, 60000):06d}" if rng.random() < 0.85 else f"C{rng.randrange(1, 400):04d}"
                rows.append((name, day, start, start + length, _status(rng), who))
            if k and rng.random() < per_day / 150:
                # A desk booking at an off-grid time.
                start = rng.choice(slots) + rng.choice([10, 15, 20]) * (length // 30)
                start = min(start, 22 * 60)
                end = min(start + rng.choice([30, 40, 60]), 23 * 60)
                if end > start:
                    written = _typed(rng, name) if rng.random() < 1 / 3 else name
                    rows.append((written, day, start, end, _status(rng), f"DESK-{name.split('-')[0]}"))
            if rng.random() < per_day / 2000:
                start = rng.choice([8 * 60, 9 * 60, 10 * 60])
                rows.append((name, day, start, start + rng.choice([300, 360, 420, 480]), _status(rng),
                             f"C{rng.randrange(1, 400):04d}"))
    rng.shuffle(rows)
    out = [HEADER]
    for n, (facility, day, start, end, status, who) in enumerate(rows, 1):
        out.append(f"B26-{n:07d},{facility},{day},{_clock(start)},{_clock(end)},{status},{who}")
    return out


def broken(lines, repeats, seed):
    """The export as it comes out when the export goes wrong: the same bookings with their references given
    in scrambled order (so the lines are not in reference order), and `repeats` more lines, each repeating
    the reference of a line in the first quarter at least a quarter of the export later, as an exact copy of
    that line (even ones) or with another booking's details (odd ones)."""
    rng = random.Random(f"{seed}-broken-{repeats}")
    header, rows = lines[0], lines[1:]
    numbers = list(range(1, len(rows) + 1))
    rng.shuffle(numbers)
    rows = [f"B26-{numbers[i]:07d}{row[row.index(','):]}" for i, row in enumerate(rows)]
    quarter = len(rows) // 4
    for k in range(repeats):
        first = rng.randrange(quarter)
        reference = rows[first][:rows[first].index(",")]
        details = rows[first if k % 2 == 0 else rng.randrange(len(rows))]
        rows.insert(rng.randrange(first + quarter, len(rows) + 1), reference + details[details.index(","):])
    return [header] + rows


def main():
    count, seed, path = int(sys.argv[1]), int(sys.argv[2]), Path(sys.argv[3])
    repeats = int(sys.argv[4]) if len(sys.argv) > 4 else 0
    lines = generate(count, seed)
    if repeats:
        lines = broken(lines, repeats, seed)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
