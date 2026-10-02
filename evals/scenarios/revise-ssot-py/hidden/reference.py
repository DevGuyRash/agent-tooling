"""Reference for revise-ssot-py: circdesk's three commands (receipt, notices, account) as the fixture prints
them, under a fines rule passed in, so the check can compute what each command should print under the
documented rule and after it edits one part of that rule.

RULE is docs/fines.md as the board approved it for 1 November 2026: the request (adult 0.35 a day, the new
device category) and every earlier change, which the fixture's three copies of the rule each missed one of.
A rule is a dict: rates ({category: (cents a day, most cents an item can owe)}), grace (an item this many
days late or less owes nothing), grace_strict (an edit of the rule's wording: only an item fewer than grace
days late owes nothing), and charge_after_grace (an edit of how the parts combine: only the days past the
grace period are charged, instead of every day once the grace period is over). The kiosk's blocking
threshold (BLOCK_AT) is the kiosk's own and is not part of the rule the check edits.

COPIES are the fixture's three copies of the rule as they would be with the request applied to each and
nothing else (receipt.py's children's most 2.50, notices.py's 3-day grace period, account.py's media most
10.00): the check uses them only to verify which hidden inputs the copies disagree on.

run(rule, argv, files) -> (exit status, stdout) or (exit status, None) for a refusal (1: an export problem,
`circdesk: ...` on stderr; 2: a bad command line). argv names files as {name}, looked up in files (text,
written with a byte-order mark when it starts with one); a name not in files is a missing file."""
import copy
import csv
import datetime as dt
import io
import re

RULE = {
    "rates": {"adult": (35, 700), "children": (15, 300), "media": (125, 1250), "device": (240, 4800)},
    "grace": 2,
    "grace_strict": False,
    "charge_after_grace": False,
}
BLOCK_AT = 1000
COMMANDS = ("receipt", "notices", "account")
LOAN_COLUMNS = ("loan_id", "patron_id", "barcode", "title", "category", "due", "returned")
PATRON_COLUMNS = ("patron_id", "name")


def mutated(rule=RULE, per_day=None, most=None, **changes):
    """rule with some parts replaced: per_day and most as {category: cents}, grace, grace_strict,
    charge_after_grace."""
    out = copy.deepcopy(rule)
    for cat, cents in (per_day or {}).items():
        out["rates"][cat] = (cents, out["rates"][cat][1])
    for cat, cents in (most or {}).items():
        out["rates"][cat] = (out["rates"][cat][0], cents)
    out.update(changes)
    return out


COPIES = {
    "receipt.py": mutated(most={"children": 250}),
    "notices.py": mutated(grace=3),
    "account.py": mutated(most={"media": 1000}),
}


class Refused(Exception):
    def __init__(self, rc):
        super().__init__(rc)
        self.rc = rc


def fmt(cents):
    return f"{cents // 100}.{cents % 100:02d}"


def fine(rule, category, days):
    """Cents owed for an item of category `days` days late; Refused(1) for an unknown category."""
    if category not in rule["rates"]:
        raise Refused(1)
    free = days < rule["grace"] if rule["grace_strict"] else days <= rule["grace"]
    if free:
        return 0
    per_day, most = rule["rates"][category]
    charged = days - rule["grace"] if rule["charge_after_grace"] else days
    return min(charged * per_day, most)


def _rows(files, name, columns):
    if name not in files:
        raise Refused(1)
    text = files[name]
    if text.startswith("\ufeff"):
        text = text[1:]
    reader = csv.DictReader(io.StringIO(text, newline=""))
    if any(c not in (reader.fieldnames or ()) for c in columns):
        raise Refused(1)
    return [{k: (v or "").strip() for k, v in row.items() if k} for row in reader]


def _date(text):
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        raise ValueError(text)
    return dt.date.fromisoformat(text)


def loans(files, name):
    out = []
    for row in _rows(files, name, LOAN_COLUMNS):
        try:
            due = _date(row["due"])
            returned = _date(row["returned"]) if row["returned"] else None
        except ValueError:
            raise Refused(1) from None
        out.append({"loan_id": row["loan_id"], "patron_id": row["patron_id"], "barcode": row["barcode"],
                    "title": row["title"], "category": row["category"].lower(), "due": due, "returned": returned})
    return out


def patrons(files, name):
    return {row["patron_id"]: row["name"] for row in _rows(files, name, PATRON_COLUMNS)}


def days_late(due, day):
    return max(0, (day - due).days)


def receipt(rule, all_loans, loan_id):
    loan = next((l for l in all_loans if l["loan_id"] == loan_id), None)
    if loan is None or loan["returned"] is None:
        raise Refused(1)
    days = days_late(loan["due"], loan["returned"])
    owed = fine(rule, loan["category"], days)
    late = "on time" if days == 0 else "1 day late" if days == 1 else f"{days} days late"
    return (f"Returned: {loan['title']} ({loan['barcode']})\n"
            f"Due {loan['due']}, returned {loan['returned']}: {late}\n"
            f"Fine: {fmt(owed) if owed else 'none'}\n")


def notices(rule, all_loans, names, day):
    found = {}
    for loan in all_loans:
        if loan["returned"] is not None:
            continue
        days = days_late(loan["due"], day)
        owed = fine(rule, loan["category"], days)
        free = days < rule["grace"] if rule["grace_strict"] else days <= rule["grace"]
        if free:
            continue
        if loan["patron_id"] not in names:
            raise Refused(1)
        found.setdefault(loan["patron_id"], []).append((loan, days, owed))
    if not found:
        return "No notices.\n"
    lines, items = [], 0
    for pid in sorted(found, key=lambda p: (names[p].casefold(), p)):
        lines.append(f"{names[pid]} ({pid})")
        for loan, days, owed in sorted(found[pid], key=lambda e: (e[0]["due"], e[0]["title"])):
            lines.append(f"  {loan['title']} ({loan['barcode']}): due {loan['due']}, {days} days overdue, "
                         f"fine so far {fmt(owed)}")
            items += 1
    n = len(found)
    lines.append(f"{n} notice{'' if n == 1 else 's'}, {items} item{'' if items == 1 else 's'}")
    return "\n".join(lines) + "\n"


def account(rule, all_loans, names, patron_id, day):
    if patron_id not in names:
        raise Refused(1)
    lines, total = [f"{names[patron_id]} ({patron_id})"], 0
    for loan in sorted((l for l in all_loans if l["patron_id"] == patron_id), key=lambda l: (l["due"], l["title"])):
        days = days_late(loan["due"], loan["returned"] or day)
        owed = fine(rule, loan["category"], days)
        if not owed:
            continue
        status = f"returned {days} days late" if loan["returned"] else f"out, {days} days overdue"
        lines.append(f"  {loan['title']} ({loan['barcode']}): {status}, {fmt(owed)}")
        total += owed
    if not total:
        lines.append("No fines.")
    else:
        lines.append(f"Total owed: {fmt(total)}")
        if total >= BLOCK_AT:
            lines.append(f"Borrowing blocked until the total is under {fmt(BLOCK_AT)}.")
    return "\n".join(lines) + "\n"


def _file(arg):
    m = re.fullmatch(r"\{([\w.-]+)\}", arg)
    return m.group(1) if m else arg


def _usage(argv):
    """The parsed command line as the fixture's argparse parser takes it, or Refused(2)."""
    if not argv or argv[0] not in COMMANDS:
        raise Refused(2)
    cmd, rest, on, positional = argv[0], argv[1:], None, []
    i = 0
    while i < len(rest):
        a = rest[i]
        if a == "--on" and cmd != "receipt":
            if i + 1 >= len(rest):
                raise Refused(2)
            try:
                on = _date(rest[i + 1])
            except ValueError:
                raise Refused(2) from None
            i += 2
            continue
        if a.startswith("-"):
            raise Refused(2)
        positional.append(a)
        i += 1
    if len(positional) != {"receipt": 2, "notices": 2, "account": 3}[cmd]:
        raise Refused(2)
    return cmd, positional, on


def run(rule, argv, files):
    """(exit status, stdout or None) of `python3 -m circdesk ARGV` under rule."""
    try:
        cmd, pos, on = _usage(argv)
        if cmd == "receipt":
            return 0, receipt(rule, loans(files, _file(pos[0])), pos[1])
        if on is None:
            raise ValueError("the hidden cases always pass --on to notices and account")
        all_loans = loans(files, _file(pos[0]))
        names = patrons(files, _file(pos[1]))
        if cmd == "notices":
            return 0, notices(rule, all_loans, names, on)
        return 0, account(rule, all_loans, names, pos[2], on)
    except Refused as r:
        return r.rc, None
