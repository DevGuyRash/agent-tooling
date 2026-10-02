"""Deterministic tap exports for the hidden checks:

    python3 data.py TAPS SEED OUT.csv     writes one service day's export of about TAPS taps

A service day (2026-09-29 04:00 to 2026-09-30 03:59) on a network of 60 routes. Cards make one to four
journeys a day around the peaks, a third of journeys with a second leg 3 to 75 minutes later (so both sides
of the 60-minute transfer window occur), and about one card in three reaches its daily cap (concession cards,
one in seven, most often). Each bus's reader uploads a batch every ten minutes; about 3% of batches arrive
one to six hours late (a bus out of coverage), so the export is not in time order. A reader sends about one
batch in 250 twice, and the back office re-sends about one tap in 600 later in the day in the plain format.
Readers on firmware 3.x (about one in twelve) print card numbers in groups of four and pad fares to four
digits. Lines are in the order the back office received them.

Two kinds of tap the rules treat specially are in every day, drawn from a second random stream. Two day
routes run free for two to four hours (a disruption), so their readers record a fare of 0. And about one tap
in 250 has a near-twin on the same card that differs from it in exactly one of fare (most often), second,
route, or stop: a different tap under the rules, never a duplicate. Half the twins go through a reader on
firmware 3.x where the route has one, so a twin's spelling of the card and fare often differs from the
original's.
"""
import random
import sys
from pathlib import Path

DAY_START = 4 * 3600                 # seconds after midnight of 2026-09-29
DAY_END = DAY_START + 24 * 3600 - 1
ROUTES = [str(n) for n in range(1, 49)] + [f"X{n}" for n in range(1, 9)] + [f"N{n}" for n in range(1, 5)]
FARES = {"": [180, 240, 240, 240, 300], "X": [420], "N": [300]}
TWIN_FARES = [0, 180, 240, 300, 420]  # a near-twin's fare, any but the original's
# Journey start times: (weight, earliest hour, latest hour) after midnight of the first calendar day.
PERIODS = [(5, 5, 7), (22, 7, 9), (14, 9, 12), (12, 12, 15), (24, 15, 19), (10, 19, 23), (3, 23, 27)]
BATCH_SECONDS = 600
HEADER = "ts,card,route,stop,fare_cents,batch"


def _clock(seconds):
    day, rest = divmod(seconds, 86400)
    h, rest = divmod(rest, 3600)
    m, s = divmod(rest, 60)
    return f"2026-09-{29 + day:02d}T{h:02d}:{m:02d}:{s:02d}"


def _start_time(rng):
    total = sum(p[0] for p in PERIODS)
    pick = rng.randrange(total)
    for weight, lo, hi in PERIODS:
        if pick < weight:
            return rng.randrange(lo * 3600, hi * 3600)
        pick -= weight
    raise AssertionError


def _route_kind(route):
    return route[0] if route[0] in "XN" else ""


def _free_and_twins(events, seed, readers, old_firmware, day_routes, night_routes):
    """The events with the free hours' fares set to 0 and the near-twins added (see the module's docstring)."""
    extra = random.Random(f"{seed}-free-and-twins")
    free = []
    for route in extra.sample(day_routes, 2):
        start = extra.randrange(7 * 3600, 18 * 3600)
        free.append((route, start, start + extra.randrange(2 * 3600, 4 * 3600)))
    events = [(t, card, route, stop, 0 if any(r == route and lo <= t < hi for r, lo, hi in free) else fare, reader)
              for t, card, route, stop, fare, reader in events]
    twins = []
    for t, card, route, stop, fare, _ in events:
        if extra.random() >= 1 / 250:
            continue
        what = extra.choice(["fare", "fare", "second", "route", "stop"])
        if what == "fare":
            fare = extra.choice([f for f in TWIN_FARES if f != fare])
        elif what == "second":
            t = t + 1 if t == DAY_START or extra.random() < 0.5 else t - 1
        elif what == "route":
            pool = night_routes if route in night_routes else day_routes
            route = extra.choice([r for r in pool if r != route])
        else:
            moved = stop
            while moved == stop:
                moved = f"KV{extra.randrange(1000, 3000)}"
            stop = moved
        old = [r for r in readers[route] if r in old_firmware]
        reader = extra.choice(old if old and extra.random() < 0.5 else readers[route])
        twins.append((t, card, route, stop, fare, reader))
    return events + twins


def generate(taps, seed):
    rng = random.Random(seed)
    readers_per_route = max(1, taps // 60_000 + 1)
    readers = {}  # route -> reader numbers
    old_firmware = set()
    n = 1
    for route in ROUTES:
        readers[route] = []
        for _ in range(readers_per_route * (3 if _route_kind(route) == "" else 1)):
            readers[route].append(n)
            if rng.random() < 1 / 12:
                old_firmware.add(n)
            n += 1
    day_routes = [r for r in ROUTES if not r.startswith("N")]
    night_routes = [r for r in ROUTES if r.startswith("N")]

    events = []  # (seconds, card, route, stop, fare, reader)
    seen_cards = set()
    while len(events) < taps:
        while True:
            first = "9" if rng.random() < 1 / 7 else str(rng.randint(1, 8))
            card = first + "".join(str(rng.randrange(10)) for _ in range(11))
            if card not in seen_cards:
                seen_cards.add(card)
                break
        journeys = rng.choices([1, 2, 3, 4], weights=[30, 45, 17, 8])[0]
        for _ in range(journeys):
            t = _start_time(rng)
            if not DAY_START <= t <= DAY_END - 4600:
                continue
            legs = 2 if rng.random() < 1 / 3 else 1
            for leg in range(legs):
                if leg:
                    t += rng.randrange(3 * 60, 75 * 60)
                hour = (t // 3600) % 24
                pool = night_routes if hour >= 23 or hour < 5 else day_routes
                route = rng.choice(pool)
                fare = rng.choice(FARES[_route_kind(route)])
                stop = f"KV{rng.randrange(1000, 3000)}"
                events.append((t, card, route, stop, fare, rng.choice(readers[route])))
    events = _free_and_twins(events, seed, readers, old_firmware, day_routes, night_routes)

    # Batches: each reader's taps per ten-minute window, arriving shortly after the window closes, or late.
    batches = {}
    for t, card, route, stop, fare, reader in events:
        batches.setdefault((reader, t // BATCH_SECONDS), []).append((t, card, route, stop, fare))
    sends = []  # (arrival, order, batch name, lines)
    order = 0
    seq = {}
    for (reader, window) in sorted(batches):
        seq[reader] = seq.get(reader, 0) + 1
        name = f"R{reader:04d}-{seq[reader]:04d}"
        rows = sorted(batches[(reader, window)])
        old = reader in old_firmware
        lines = []
        for t, card, route, stop, fare in rows:
            shown_card = f"{card[:4]} {card[4:8]} {card[8:]}" if old else card
            shown_fare = f"{fare:04d}" if old else str(fare)
            lines.append(f"{_clock(t)},{shown_card},{route},{stop},{shown_fare},{name}")
        arrival = (window + 1) * BATCH_SECONDS + rng.randrange(5, 90)
        if rng.random() < 0.03:
            arrival += rng.randrange(3600, 6 * 3600)
        sends.append((arrival, order, lines))
        order += 1
        if rng.random() < 1 / 250:
            sends.append((arrival + rng.randrange(20, 120), order, lines))
            order += 1
    resend_rows = [e for e in events if rng.random() < 1 / 600]
    for i, (t, card, route, stop, fare, _) in enumerate(resend_rows):
        arrival = min(t + rng.randrange(2 * 3600, 20 * 3600), DAY_END + 3600)
        sends.append((arrival, order, [f"{_clock(t)},{card},{route},{stop},{fare},BO-0929-{i + 1:04d}"]))
        order += 1
    sends.sort()
    out = [HEADER]
    for _, _, lines in sends:
        out.extend(lines)
    return out


def main():
    taps, seed, path = int(sys.argv[1]), int(sys.argv[2]), Path(sys.argv[3])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(generate(taps, seed)) + "\n")


if __name__ == "__main__":
    main()
