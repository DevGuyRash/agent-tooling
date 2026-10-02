#!/usr/bin/env python3
"""Month-end invoice lines for one client, from the timesheets and the rate card.

    invoice.py --rates rates.txt --client acme [--month 2026-09] [--json] timesheets/*.txt

ops/month-end.sh runs this for every client in the rate card on the first of the month, and Dana pastes
the text into the accounting system (--json is for the spreadsheet import). Without --month every entry of
the client is billed.

Billing rules: each entry's minutes are rounded up to a whole multiple of the client's increment and then
raised to the client's minimum; each project bills at its own rate.PROJECT if the rate card has one,
otherwise at the client's rate; a project's amount is its billed minutes times the rate over 60, and the
tax is the subtotal times the tax percentage over 100, both rounded to the cent with halves going up.
Rate card format: docs/rates.md. Timesheet format: docs/timesheets.md.
"""
import argparse
import json
import re
import sys
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")
DATE = re.compile(r"\d{4}-\d{2}-\d{2}", re.A)
MONTH = re.compile(r"\d{4}-(0[1-9]|1[0-2])", re.A)
RANGE = re.compile(r"(\d\d):(\d\d)-(\d\d):(\d\d)", re.A)
DURATION = re.compile(r"(?:(\d+)h([0-5]\d)?|(\d+)m)", re.A)
PROJECT = re.compile(r"([a-z0-9-]+)/[a-z0-9-]+", re.A)
CLIENT = re.compile(r"\[([a-z0-9-]+)\]", re.A)
AMOUNT = re.compile(r"\d+(\.\d{1,2})?", re.A)
WHOLE = re.compile(r"\d+", re.A)
CURRENCY = re.compile(r"[A-Z]{3}", re.A)
REQUIRED = ("name", "currency", "rate")


class InputError(Exception):
    """A file that cannot be read or has a mistake in it; the message says where."""


def read_text(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except (OSError, UnicodeDecodeError) as exc:
        raise InputError(f"invoice.py: cannot read {path}: {exc}") from exc


# ---------------------------------------------------------------- timesheets

def entry_minutes(time):
    """Minutes of a TIME field, or None when it is not one."""
    m = RANGE.fullmatch(time)
    if m:
        h1, m1, h2, m2 = (int(g) for g in m.groups())
        if h1 > 23 or h2 > 23 or m1 > 59 or m2 > 59:
            return None
        start, end = h1 * 60 + m1, h2 * 60 + m2
        return end - start if end > start else None
    m = DURATION.fullmatch(time)
    if not m:
        return None
    minutes = int(m.group(3)) if m.group(3) is not None else int(m.group(1)) * 60 + int(m.group(2) or 0)
    return minutes or None


def is_date(text):
    if not DATE.fullmatch(text):
        return False
    try:
        date.fromisoformat(text)
    except ValueError:
        return False
    return True


def read_timesheet(path):
    entries = []
    for number, raw in enumerate(read_text(path).split("\n"), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split()
        if len(fields) < 3:
            raise InputError(f"{path}:{number}: expected DATE TIME PROJECT [NOTE]")
        day, time, project = fields[:3]
        if not is_date(day):
            raise InputError(f"{path}:{number}: bad date {day!r}")
        minutes = entry_minutes(time)
        if minutes is None:
            raise InputError(f"{path}:{number}: bad time {time!r}")
        m = PROJECT.fullmatch(project)
        if not m:
            raise InputError(f"{path}:{number}: bad project {project!r}")
        entries.append({"date": day, "minutes": minutes, "client": m.group(1), "project": project,
                        "note": " ".join(fields[3:])})
    return entries


# ---------------------------------------------------------------- rate card

def read_rates(path):
    """{client: {"name", "currency", "rate", "increment", "minimum", "tax", "projects": {name: rate}}}."""
    clients, headers, seen, current = {}, {}, {}, None

    def finish():
        if current is not None:
            for key in REQUIRED:
                if key not in seen[current]:
                    raise InputError(f"{path}:{headers[current]}: [{current}] has no {key}")

    for number, raw in enumerate(read_text(path).split("\n"), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = CLIENT.fullmatch(line)
        if m:
            finish()
            current = m.group(1)
            if current in clients:
                raise InputError(f"{path}:{number}: [{current}] is given twice")
            clients[current] = {"increment": 1, "minimum": 0, "tax": Decimal(0), "projects": {}}
            headers[current], seen[current] = number, set()
            continue
        if "=" not in line:
            raise InputError(f"{path}:{number}: expected [CLIENT] or key = value")
        key, value = (part.strip() for part in line.split("=", 1))
        if current is None:
            raise InputError(f"{path}:{number}: {key} before the first [CLIENT]")
        project = key[5:] if key.startswith("rate.") and re.fullmatch(r"[a-z0-9-]+", key[5:], re.A) else None
        if project is None and key not in ("name", "currency", "rate", "increment", "minimum", "tax"):
            raise InputError(f"{path}:{number}: unknown key {key!r}")
        if key in seen[current]:
            raise InputError(f"{path}:{number}: {key} is given twice")
        seen[current].add(key)
        client = clients[current]
        if project is not None and AMOUNT.fullmatch(value):
            client["projects"][project] = Decimal(value)
        elif key == "name" and value:
            client["name"] = value
        elif key == "currency" and CURRENCY.fullmatch(value):
            client["currency"] = value
        elif key == "rate" and AMOUNT.fullmatch(value):
            client["rate"] = Decimal(value)
        elif key == "increment" and WHOLE.fullmatch(value) and int(value) >= 1:
            client["increment"] = int(value)
        elif key == "minimum" and WHOLE.fullmatch(value):
            client["minimum"] = int(value)
        elif key == "tax" and AMOUNT.fullmatch(value) and Decimal(value) <= 100:
            client["tax"] = Decimal(value)
        else:
            raise InputError(f"{path}:{number}: bad {key} {value!r}")
    finish()
    return clients


# ---------------------------------------------------------------- billing

def billed_minutes(minutes, client):
    increment = client["increment"]
    rounded = -(-minutes // increment) * increment
    return max(rounded, client["minimum"])


def cents(value):
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def invoice(client_id, client, entries, month=None):
    lines = {}
    for e in entries:
        if e["client"] != client_id or (month and not e["date"].startswith(month + "-")):
            continue
        line = lines.setdefault(e["project"], {"project": e["project"], "entries": 0, "minutes": 0, "billed_minutes": 0})
        line["entries"] += 1
        line["minutes"] += e["minutes"]
        line["billed_minutes"] += billed_minutes(e["minutes"], client)
    projects = []
    subtotal = Decimal(0)
    for name in sorted(lines):
        line = lines[name]
        rate = client["projects"].get(name.split("/", 1)[1], client["rate"])
        amount = cents(Decimal(line["billed_minutes"]) * rate / 60)
        subtotal += amount
        projects.append(dict(line, rate=f"{rate:.2f}", amount=f"{amount:.2f}"))
    tax = cents(subtotal * client["tax"] / 100)
    return {
        "client": client_id,
        "name": client["name"],
        "currency": client["currency"],
        "month": month,
        "projects": projects,
        "subtotal": f"{subtotal:.2f}",
        "tax_percent": format(client["tax"].normalize(), "f"),
        "tax": f"{tax:.2f}",
        "total": f"{subtotal + tax:.2f}",
    }


def hm(minutes):
    return f"{minutes // 60}:{minutes % 60:02d}"


def text(inv):
    out = [f"{inv['name']} ({inv['client']}), {inv['currency']}" + (f", {inv['month']}" if inv["month"] else "")]
    for p in inv["projects"]:
        out.append(f"{p['project']}  {p['entries']} entries  {hm(p['minutes'])} -> {hm(p['billed_minutes'])}"
                   f"  at {p['rate']}  {p['amount']}")
    out.append(f"subtotal  {inv['subtotal']}")
    if inv["tax_percent"] != "0":
        out.append(f"tax {inv['tax_percent']}%  {inv['tax']}")
    out.append(f"total  {inv['total']}")
    return "\n".join(out) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Month-end invoice lines for one client.")
    parser.add_argument("--rates", required=True, help="the rate card (docs/rates.md)")
    parser.add_argument("--client", required=True, help="client id, as in the rate card")
    parser.add_argument("--month", help="YYYY-MM; every entry when left out")
    parser.add_argument("--json", action="store_true", help="JSON for the spreadsheet import")
    parser.add_argument("timesheets", nargs="+")
    args = parser.parse_args(argv)
    if args.month is not None and not MONTH.fullmatch(args.month):
        parser.error(f"bad month {args.month!r}")
    try:
        clients = read_rates(args.rates)
        if args.client not in clients:
            raise InputError(f'invoice.py: no client "{args.client}" in {args.rates}')
        entries = [e for path in args.timesheets for e in read_timesheet(path)]
    except InputError as exc:
        print(exc, file=sys.stderr)
        return 1
    inv = invoice(args.client, clients[args.client], entries, args.month)
    sys.stdout.write(json.dumps(inv, indent=2) + "\n" if args.json else text(inv))
    return 0


if __name__ == "__main__":
    sys.exit(main())
