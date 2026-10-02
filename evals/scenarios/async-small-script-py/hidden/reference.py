"""What `python3 scripts/boat_hours.py LOG.csv` prints, written from the ticket: one line per boat with its
time on the water this season (completed outings only; SERVICE rows are not time on the water), most time
first and equal times by boat name, as H:MM, and " service due" when the boat has 100 hours or more on the
water since its last SERVICE row (or since the start of the log). Also the hidden logs, in which every boat
that reaches 100 hours has a SERVICE row, so that whether a boat never serviced counts its whole season or is
never due decides no line."""
import csv
import io
import random
from datetime import date, timedelta

DUE_MINUTES = 100 * 60
HEADER = "date,boat,crew,out,in\n"


def _minutes(hhmm):
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def report(text):
    total, since = {}, {}
    for row in csv.DictReader(io.StringIO(text)):
        boat = row["boat"]
        total.setdefault(boat, 0)
        since.setdefault(boat, 0)
        if row["crew"] == "SERVICE":
            since[boat] = 0
            continue
        if not row["in"]:
            continue
        spent = _minutes(row["in"]) - _minutes(row["out"])
        total[boat] += spent
        since[boat] += spent
    lines = []
    for boat in sorted(total, key=lambda b: (-total[b], b)):
        line = f"{boat} {total[boat] // 60}:{total[boat] % 60:02d}"
        if since[boat] >= DUE_MINUTES:
            line += " service due"
        lines.append(line)
    return "\n".join(lines) + "\n"


def _row(date, boat, crew, out, back):
    crew_field = f'"{crew}"' if "," in crew else crew
    return f"{date},{boat},{crew_field},{out},{back}\n"


def _hhmm(minutes):
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


CREWS = ["Anna Keller, Ben Ott", "Clara Rüegg", "Felix Moser, Clara Rüegg", "Eva Brunner",
         "Anna Keller, Ben Ott, Eva Brunner, Lea Frei", "Jonas Graf, Mia Huber", "Lea Frei"]


class Log:
    """Rows in the order the boats went out: each call moves on to a later day, so a boat's outings and its
    days in the workshop never share a day and every reading of "since its last service" agrees."""
    def __init__(self):
        self.day, self.rows = date(2026, 4, 1), []

    def _next(self):
        self.day += timedelta(days=1)
        return self.day.isoformat()

    def outings(self, boat, minutes_each, count, crew="Eva Brunner"):
        """count outings of minutes_each, three a day (at 06:00, 10:00, and 14:00)."""
        for i in range(count):
            if i % 3 == 0:
                day = self._next()
            out = (6, 10, 14)[i % 3] * 60
            self.rows.append(_row(day, boat, crew, _hhmm(out), _hhmm(out + minutes_each)))

    def outing(self, boat, crew, out, back):
        self.rows.append(_row(self._next(), boat, crew, out, back))

    def service(self, boat):
        self.rows.append(_row(self._next(), boat, "SERVICE", "", ""))

    def text(self):
        return HEADER + "".join(self.rows)


def hand_cases():
    """(name, log text) for each rule; check.py adds the fixture's sample."""
    cases = []
    # 100:00 since the service exactly (due), 99:59 (not due), much before a service and little after (not
    # due), 101:00 in outings of 1:41 after a service (due).
    log = Log()
    log.service("Kestrel")
    log.service("Osprey")
    log.outings("Kestrel", 120, 50)                                       # 100:00 after its service
    log.outings("Osprey", 120, 49)
    log.outing("Osprey", "Lea Frei", "06:00", "07:59")                    # 99:59
    log.outings("Gannet", 180, 50)
    log.service("Gannet")
    log.outing("Gannet", "Anna Keller, Ben Ott", "07:00", "09:30")
    log.service("Tern")
    log.outings("Tern", 101, 60, crew="Jonas Graf, Mia Huber")            # 101:00 after its service
    cases.append(("service-due", log.text()))
    # Equal totals go by name; names with spaces; quoted crews; an outing still out at the end.
    rows = [_row("2026-05-02", "Wotan", "Anna Keller, Ben Ott, Eva Brunner, Lea Frei", "07:15", "08:40"),
            _row("2026-05-02", "Blue Heron", "Felix Moser, Clara Rüegg", "08:00", "09:25"),
            _row("2026-05-03", "Aare", "Clara Rüegg", "09:00", "10:00"),
            _row("2026-05-03", "Aare", "Clara Rüegg", "16:00", "16:25"),
            _row("2026-05-04", "Libelle", "Lea Frei", "06:30", "07:00"),
            _row("2026-05-04", "Blue Heron", "Felix Moser, Clara Rüegg", "18:00", "")]
    cases.append(("ties-and-open", HEADER + "".join(rows)))
    # Several services: only the time after the last one counts toward the next.
    log = Log()
    for _ in range(3):
        log.outings("Libelle", 150, 30, crew="Clara Rüegg")
        log.service("Libelle")
    log.outings("Libelle", 60, 99, crew="Clara Rüegg")                    # 99:00 after the last service
    log.outings("Seeadler", 90, 70, crew="Anna Keller, Ben Ott")
    log.service("Seeadler")
    log.outings("Seeadler", 90, 67, crew="Anna Keller, Ben Ott")          # 100:30 after its service
    cases.append(("several-services", log.text()))
    return cases


def season(seed=5, outings=2600):
    """A generated season: 16 boats, each serviced before the season opens, outings from April to October in
    the order the boats went out, a boat's day in the workshop now and then (with no outing of it that day), a
    few outings still out at the end."""
    rng = random.Random(seed)
    boats = ["Wotan", "Libelle", "Blue Heron", "Aare", "Kestrel", "Osprey", "Gannet", "Tern", "Seeadler", "Eisvogel",
             "Haubentaucher", "Reiher", "Pelikan", "Kormoran", "Schwan", "Moewe"]
    weights = [rng.randint(2, 9) for _ in boats]
    days = [date(2026, 4, 4) + timedelta(days=i) for i in range(205)]
    rows = [_row((days[0] - timedelta(days=1)).isoformat(), b, "SERVICE", "", "") for b in sorted(boats)]
    per_day = max(4, outings // len(days))
    for day in days:
        workshop = {b for b in boats if rng.random() < 0.012}
        today = []
        for _ in range(rng.randint(per_day - 3, per_day + 3)):
            boat = rng.choices(boats, weights)[0]
            if boat in workshop:
                continue
            out = rng.randint(5 * 60 + 30, 19 * 60)
            today.append((out, boat, rng.choice(CREWS), _hhmm(out + rng.randint(35, 200))))
        rows += [_row(day.isoformat(), b, "SERVICE", "", "") for b in sorted(workshop)]
        rows += [_row(day.isoformat(), boat, crew, _hhmm(out), back) for out, boat, crew, back in sorted(today)]
    last = (days[-1] + timedelta(days=1)).isoformat()
    for k, boat in enumerate(sorted(rng.sample(boats, 3))):
        rows.append(_row(last, boat, rng.choice(CREWS), _hhmm(17 * 60 + 10 * k), ""))
    return HEADER + "".join(rows)
