"""Reference `hours invoice`, written from the fixture's docs/invoice.md, docs/rates.md, and docs/timesheets.md
alone (not from scripts/invoice.py). make_cases.py uses it for the expected results of the hidden cases.

    python3 reference.py invoice --client ID --rates FILE (--month YYYY-MM | --from DATE --to DATE) FILE...

run(argv) returns (exit status, standard output, standard error) without touching the process streams.
Money is kept in integer cents and percentages in hundredths, so nothing is ever a float.
"""
import re
import sys

ASCII_DIGITS = re.A
DATE = re.compile(r"(\d{4})-(\d{2})-(\d{2})", ASCII_DIGITS)
MONTH = re.compile(r"(\d{4})-(\d{2})", ASCII_DIGITS)
CLOCK = re.compile(r"([01]\d|2[0-3]):([0-5]\d)", ASCII_DIGITS)
SPAN = re.compile(r"(?:(\d+)h([0-5]\d)?|(\d+)m)", ASCII_DIGITS)
PART = re.compile(r"[a-z0-9-]+", ASCII_DIGITS)
MONEY = re.compile(r"(\d+)(?:\.(\d{1,2}))?", ASCII_DIGITS)
COUNT = re.compile(r"\d+", ASCII_DIGITS)
CURRENCY = re.compile(r"[A-Z]{3}", ASCII_DIGITS)
OPTIONS = ("client", "rates", "month", "from", "to")


class Failure(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def usage(message):
    return Failure(2, f"hours invoice: {message}\n"
                      "usage: hours invoice --client CLIENT --rates FILE (--month YYYY-MM | --from DATE --to DATE) TIMESHEET...")


# ---------------------------------------------------------------- dates

def days_in_month(year, month):
    if month == 2:
        return 29 if (year % 4 == 0 and year % 100 != 0) or year % 400 == 0 else 28
    return 30 if month in (4, 6, 9, 11) else 31


def real_date(text):
    m = DATE.fullmatch(text)
    if not m:
        return False
    y, mo, d = (int(g) for g in m.groups())
    return 1 <= mo <= 12 and 1 <= d <= days_in_month(y, mo)


# ---------------------------------------------------------------- reading

def read(path):
    try:
        with open(path, "rb") as fh:
            return fh.read().decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise Failure(1, f"hours invoice: cannot read {path}: {exc.__class__.__name__}") from exc


def lines_of(text):
    for number, raw in enumerate(text.split("\n"), 1):
        line = raw.strip(" \t\r")
        if line and not line.startswith("#"):
            yield number, line


def minutes_of(time):
    if "-" in time:
        a, _, b = time.partition("-")
        ca, cb = CLOCK.fullmatch(a), CLOCK.fullmatch(b)
        if not (ca and cb):
            return None
        start = int(ca.group(1)) * 60 + int(ca.group(2))
        end = int(cb.group(1)) * 60 + int(cb.group(2))
        return end - start if end > start else None
    m = SPAN.fullmatch(time)
    if not m:
        return None
    total = int(m.group(3)) if m.group(3) is not None else int(m.group(1)) * 60 + int(m.group(2) or "0")
    return total if total > 0 else None


def read_timesheet(path):
    """[(date, minutes, client, project, note words)] for each entry, or Failure(1) at the first bad line."""
    entries = []
    for number, line in lines_of(read(path)):
        fields = re.split(r"[ \t]+", line)
        if len(fields) < 3:
            raise Failure(1, f"{path}:{number}: expected DATE TIME PROJECT [NOTE]")
        day, time, project = fields[:3]
        if not real_date(day):
            raise Failure(1, f"{path}:{number}: bad date")
        minutes = minutes_of(time)
        if minutes is None:
            raise Failure(1, f"{path}:{number}: bad time")
        client, slash, name = project.partition("/")
        if not (slash and PART.fullmatch(client) and PART.fullmatch(name)):
            raise Failure(1, f"{path}:{number}: bad project")
        entries.append((day, minutes, client, project, fields[3:]))
    return entries


def money(text):
    """Cents (or hundredths) for '95', '95.5', '95.50'; None otherwise."""
    m = MONEY.fullmatch(text)
    if not m:
        return None
    return int(m.group(1)) * 100 + int((m.group(2) or "0").ljust(2, "0"))


def read_rates(path):
    """{client: {"name", "currency", "rate", "increment", "minimum", "tax", "projects"}}; money in cents, tax in
    hundredths of a percent."""
    clients = {}
    client, header, given = None, 0, set()

    def close():
        if client is not None:
            missing = [k for k in ("name", "currency", "rate") if k not in given]
            if missing:
                raise Failure(1, f"{path}:{header}: [{client}] has no {missing[0]}")

    for number, line in lines_of(read(path)):
        if line.startswith("[") and line.endswith("]") and PART.fullmatch(line[1:-1]):
            close()
            client, header, given = line[1:-1], number, set()
            if client in clients:
                raise Failure(1, f"{path}:{number}: [{client}] twice")
            clients[client] = {"increment": 1, "minimum": 0, "tax": 0, "projects": {}}
            continue
        key, eq, value = line.partition("=")
        if not eq:
            raise Failure(1, f"{path}:{number}: not [CLIENT] or key = value")
        key, value = key.strip(" \t"), value.strip(" \t")
        if client is None:
            raise Failure(1, f"{path}:{number}: key before the first client")
        project = key[len("rate."):] if key.startswith("rate.") else None
        if project is not None and not PART.fullmatch(project):
            raise Failure(1, f"{path}:{number}: unknown key")
        if project is None and key not in ("name", "currency", "rate", "increment", "minimum", "tax"):
            raise Failure(1, f"{path}:{number}: unknown key")
        if key in given:
            raise Failure(1, f"{path}:{number}: given twice")
        given.add(key)
        entry = clients[client]
        bad = Failure(1, f"{path}:{number}: bad value")
        if project is not None or key == "rate":
            cents = money(value)
            if cents is None:
                raise bad
            if project is None:
                entry["rate"] = cents
            else:
                entry["projects"][project] = cents
        elif key == "name":
            if not value:
                raise bad
            entry["name"] = value
        elif key == "currency":
            if not CURRENCY.fullmatch(value):
                raise bad
            entry["currency"] = value
        elif key in ("increment", "minimum"):
            if not COUNT.fullmatch(value) or (key == "increment" and int(value) < 1):
                raise bad
            entry[key] = int(value)
        else:  # tax
            hundredths = money(value)
            if hundredths is None or hundredths > 100_00:
                raise bad
            entry["tax"] = hundredths
    close()
    return clients


# ---------------------------------------------------------------- output

def hm(minutes):
    return f"{minutes // 60}:{minutes % 60:02d}"


def amount(cents):
    return f"{cents // 100}.{cents % 100:02d}"


def percent(hundredths):
    whole, frac = divmod(hundredths, 100)
    return str(whole) if frac == 0 else f"{whole}.{frac:02d}".rstrip("0")


def table(rows, align):
    widths = [max(len(r[c]) for r in rows) for c in range(len(align))]
    out = []
    for r in rows:
        cells = [r[c].rjust(widths[c]) if a == "r" else r[c].ljust(widths[c]) for c, a in enumerate(align)]
        out.append("  ".join(cells).rstrip(" "))
    return out


def half_up(numerator, denominator):
    """numerator / denominator rounded to the nearest integer, halves up (both non-negative)."""
    return (2 * numerator + denominator) // (2 * denominator)


# ---------------------------------------------------------------- the command

def parse_args(args):
    values, files, i = {}, [], 0
    while i < len(args):
        a = args[i]
        if a.startswith("--") and len(a) > 2:
            name, eq, value = a[2:].partition("=")
            if name not in OPTIONS:
                raise usage(f"unknown option --{name}")
            if not eq:
                if i + 1 >= len(args) or args[i + 1].startswith("-"):
                    raise usage(f"--{name} needs a value")
                i += 1
                value = args[i]
            values[name] = value
        elif a.startswith("-") and a != "-":
            raise usage(f"unknown option {a}")
        else:
            files.append(a)
        i += 1
    if "client" not in values:
        raise usage("--client is required")
    if "rates" not in values:
        raise usage("--rates is required")
    has_range = "from" in values or "to" in values
    if "month" in values and has_range:
        raise usage("--month and --from/--to cannot be used together")
    if "month" in values:
        m = MONTH.fullmatch(values["month"])
        if not m or not 1 <= int(m.group(2)) <= 12:
            raise usage("bad month")
        y, mo = int(m.group(1)), int(m.group(2))
        first, last = f"{y:04d}-{mo:02d}-01", f"{y:04d}-{mo:02d}-{days_in_month(y, mo):02d}"
    elif has_range:
        if "from" not in values or "to" not in values:
            raise usage("--from and --to go together")
        first, last = values["from"], values["to"]
        if not (real_date(first) and real_date(last)):
            raise usage("bad date")
        if first > last:
            raise usage("--from is after --to")
    else:
        raise usage("--month or --from and --to is required")
    if not files:
        raise usage("no timesheet given")
    return values["client"], values["rates"], first, last, files


def invoice(args):
    client_id, rates_path, first, last, files = parse_args(args)
    clients = read_rates(rates_path)
    if client_id not in clients:
        raise Failure(1, f'hours invoice: no client "{client_id}" in {rates_path}')
    client = clients[client_id]
    entries = [e for path in files for e in read_timesheet(path)]

    projects = {}
    not_billed_minutes = not_billed = 0
    for day, minutes, owner, project, words in entries:
        if owner != client_id or not first <= day <= last:
            continue
        if "+nobill" in words:
            not_billed += 1
            not_billed_minutes += minutes
            continue
        inc = client["increment"]
        billed = max((minutes + inc - 1) // inc * inc, client["minimum"])
        p = projects.setdefault(project, [0, 0, 0])
        p[0] += 1
        p[1] += minutes
        p[2] += billed

    out = [f"Invoice for {client['name']} ({client_id})", f"Period: {first} to {last}",
           f"Currency: {client['currency']}", ""]
    if projects:
        rows = [["Project", "Entries", "Time", "Billed", "Rate", "Amount"]]
        subtotal = 0
        for project in sorted(projects):
            count, minutes, billed = projects[project]
            rate = client["projects"].get(project.split("/", 1)[1], client["rate"])
            cents = half_up(billed * rate, 60)
            subtotal += cents
            rows.append([project, str(count), hm(minutes), hm(billed), amount(rate), amount(cents)])
        out += table(rows, "lrrrrr")
        out.append("")
        totals = [["Subtotal", amount(subtotal)]]
        tax = half_up(subtotal * client["tax"], 100_00)
        if client["tax"]:
            totals.append([f"Tax {percent(client['tax'])}%", amount(tax)])
        totals.append(["Total", amount(subtotal + tax)])
        out += table(totals, "lr")
    else:
        out.append("Nothing to bill.")
    if not_billed:
        out += ["", f"Not billed: {hm(not_billed_minutes)} in {not_billed} {'entry' if not_billed == 1 else 'entries'}"]
    return "\n".join(out) + "\n"


def run(argv):
    if not argv or argv[0] != "invoice":
        return 2, "", "reference: only `invoice` is implemented\n"
    try:
        return 0, invoice(argv[1:]), ""
    except Failure as exc:
        return exc.status, "", str(exc) + "\n"


if __name__ == "__main__":
    status, out, err = run(sys.argv[1:])
    sys.stdout.write(out)
    sys.stderr.write(err)
    sys.exit(status)
