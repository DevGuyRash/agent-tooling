// hours invoice: the billing program below (the month-end rules, with the period, +nobill, and the hours layout)
// runs with the command line passed through.

import { execSync } from 'node:child_process';
import type { Result } from '../result.ts';

const PROGRAM = String.raw`#!/usr/bin/env python3
"""Month-end invoice lines for one client, from the timesheets and the rate card.

    invoice.py --rates rates.txt --client acme [--month 2026-09 | --from DATE --to DATE] [--json | --table] timesheets/*.txt

ops/month-end.sh runs this for every client in the rate card on the first of the month, and Dana pastes
the text into the accounting system (--json is for the spreadsheet import). Without --month every entry of
the client is billed. --table prints the invoice "hours invoice" shows (docs/invoice.md): it leaves out
+nobill entries and lists their time separately, and needs a period (--month, or --from and --to).

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


def invoice(client_id, client, entries, month=None, period=None, skip_nobill=False):
    lines = {}
    not_billed = {"entries": 0, "minutes": 0}
    for e in entries:
        if e["client"] != client_id or (month and not e["date"].startswith(month + "-")):
            continue
        if period and not period[0] <= e["date"] <= period[1]:
            continue
        if skip_nobill and "+nobill" in e["note"].split():
            not_billed["entries"] += 1
            not_billed["minutes"] += e["minutes"]
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
        "not_billed": not_billed,
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


def layout(rows, align):
    widths = [max(len(r[c]) for r in rows) for c in range(len(align))]
    return ["  ".join(r[c].rjust(widths[c]) if a == "r" else r[c].ljust(widths[c]) for c, a in enumerate(align)).rstrip()
            for r in rows]


def table(inv, first, last):
    """The invoice as hours invoice prints it."""
    out = [f"Invoice for {inv['name']} ({inv['client']})", f"Period: {first} to {last}", f"Currency: {inv['currency']}", ""]
    if inv["projects"]:
        rows = [["Project", "Entries", "Time", "Billed", "Rate", "Amount"]]
        rows += [[p["project"], str(p["entries"]), hm(p["minutes"]), hm(p["billed_minutes"]), p["rate"], p["amount"]]
                 for p in inv["projects"]]
        out += layout(rows, "lrrrrr") + [""]
        totals = [["Subtotal", inv["subtotal"]]]
        if inv["tax_percent"] != "0":
            totals.append([f"Tax {inv['tax_percent']}%", inv["tax"]])
        totals.append(["Total", inv["total"]])
        out += layout(totals, "lr")
    else:
        out.append("Nothing to bill.")
    n = inv["not_billed"]["entries"]
    if n:
        out += ["", f"Not billed: {hm(inv['not_billed']['minutes'])} in {n} {'entry' if n == 1 else 'entries'}"]
    return "\n".join(out) + "\n"


def days_in_month(year, month):
    if month == 2:
        return 29 if (year % 4 == 0 and year % 100 != 0) or year % 400 == 0 else 28
    return 30 if month in (4, 6, 9, 11) else 31


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    as_table = "--table" in argv
    parser = argparse.ArgumentParser(prog="hours invoice" if as_table else None, allow_abbrev=False,
                                     description="Month-end invoice lines for one client.")
    parser.add_argument("--rates", required=True, help="the rate card (docs/rates.md)")
    parser.add_argument("--client", required=True, help="client id, as in the rate card")
    parser.add_argument("--month", help="YYYY-MM; every entry when left out")
    parser.add_argument("--json", action="store_true", help="JSON for the spreadsheet import")
    parser.add_argument("--from", dest="first", help="first day, with --table")
    parser.add_argument("--to", dest="last", help="last day, with --table")
    parser.add_argument("--table", action="store_true", help="the invoice as hours invoice prints it")
    parser.add_argument("timesheets", nargs="+")
    args = parser.parse_args(argv)
    if args.month is not None and not MONTH.fullmatch(args.month):
        parser.error(f"bad month {args.month!r}")
    period = None
    if as_table:
        if args.month is not None and (args.first is not None or args.last is not None):
            parser.error("give either --month or --from and --to")
        if args.month is not None:
            year, month = int(args.month[:4]), int(args.month[5:])
            period = (f"{args.month}-01", f"{args.month}-{days_in_month(year, month):02d}")
        elif args.first is None or args.last is None:
            parser.error("give --month, or --from and --to")
        elif not (is_date(args.first) and is_date(args.last)):
            parser.error("dates are YYYY-MM-DD")
        elif args.first > args.last:
            parser.error("--from is after --to")
        else:
            period = (args.first, args.last)
    elif args.first is not None or args.last is not None:
        parser.error("--from and --to go with --table")
    prefix = "hours invoice" if as_table else "invoice.py"
    try:
        clients = read_rates(args.rates)
        if args.client not in clients:
            raise InputError(f'{prefix}: no client "{args.client}" in {args.rates}')
        entries = [e for path in args.timesheets for e in read_timesheet(path)]
    except InputError as exc:
        print(str(exc).replace("invoice.py: ", f"{prefix}: ", 1), file=sys.stderr)
        return 1
    if as_table:
        inv = invoice(args.client, clients[args.client], entries, period=period, skip_nobill=True)
        sys.stdout.write(table(inv, *period))
        return 0
    inv = invoice(args.client, clients[args.client], entries, args.month)
    del inv["not_billed"]
    sys.stdout.write(json.dumps(inv, indent=2) + "\n" if args.json else text(inv))
    return 0


if __name__ == "__main__":
    sys.exit(main())
`;

const quote = (s: string) => `'${s.replaceAll("'", `'\\''`)}'`;

export function invoice(args: string[]): Result {
  try {
    const stdout = execSync(`python3 -c "$HOURS_INVOICE_PY" --table ${args.map(quote).join(' ')}`, {
      env: { ...process.env, HOURS_INVOICE_PY: PROGRAM },
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    return { code: 0, stdout, stderr: '' };
  } catch (error) {
    const e = error as { status?: number | null; stdout?: string; stderr?: string; message: string };
    return { code: e.status ?? 1, stdout: e.stdout ?? '', stderr: e.stderr || `${e.message}\n` };
  }
}
