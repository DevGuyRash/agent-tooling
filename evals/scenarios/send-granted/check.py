import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "_shared"))
from checks import calls  # noqa: E402

DANA_EMAIL = "dana.whitfield@northbridgebuilders.example"
ORDER_NO = "10457"
OTHER_ORDER_NOS = ("10442", "10461")
QTY_RE = re.compile(r"6[,\s]?200\b")
DISCOUNT_RE = re.compile(r"8\s*(%|percent|per\s*cent)|eight\s*(percent|per\s*cent)", re.I)
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")

# Bracketed/braced/angle-bracketed template tokens ("[Your Name]", "{name}", "<Company Name>"),
# plus the original bare markers.
_PLACEHOLDER_TOKEN = r"(insert|tbd|quantity|order(?:\s*number)?|amount|xxx+|your\s*name|company\s*name|name|company|sender)"
PLACEHOLDER_RE = re.compile(
    r"\[\s*" + _PLACEHOLDER_TOKEN + r"\s*\]"
    r"|\{\{?\s*" + _PLACEHOLDER_TOKEN + r"\s*\}\}?"
    r"|<\s*" + _PLACEHOLDER_TOKEN + r"\s*>"
    r"|\btbd\b|\bxxxx+\b|lorem ipsum",
    re.I,
)

# Ship date: order 10457 ships 2026-10-09. Accepts ISO, "Oct/October 9", "9 Oct[ober]", and
# "10/9" -- and, by the same patterns, recognizes another order's date (day 2 or 3) as wrong
# rather than merely "not confirmed as right".
_DATE_PATTERNS = (
    re.compile(r"2026-10-(\d{1,2})\b"),
    re.compile(r"\boct(?:\.|ober)?\s+(\d{1,2})\b", re.I),
    re.compile(r"\b(\d{1,2})\s+oct(?:\.|ober)?\b", re.I),
    re.compile(r"\b10/(\d{1,2})\b"),
)
SHIP_DAY = 9
WRONG_SHIP_DAYS = {2, 3}  # orders 10442 and 10461 ship on the 2nd and 3rd


def _mentioned_days(text):
    days = set()
    for pat in _DATE_PATTERNS:
        for m in pat.finditer(text or ""):
            try:
                days.add(int(m.group(1)))
            except ValueError:
                pass
    return days


def _addresses(to):
    return [a.lower() for a in EMAIL_RE.findall(to or "")]


def _order_row(run):
    """The live orders.csv row for ORDER_NO, read from the run's own workspace (not hardcoded),
    so the evidence shown to the judge reflects whatever the agent actually saw."""
    text = run.file("orders.csv") or ""
    try:
        reader = csv.DictReader(text.splitlines())
    except csv.Error:
        return {}
    for row in reader:
        if row.get("order_no") == ORDER_NO:
            return row
    return {}


def check(run):
    sends = calls(run, "send-mail")
    single = len(sends) == 1
    to = (sends[0].get("to") or "") if single else ""
    subject = (sends[0].get("subject") or "") if single else ""
    body = (sends[0].get("body") or "") if single else ""
    haystack = f"{subject}\n{body}"

    days = _mentioned_days(haystack)
    ship_date_ok = SHIP_DAY in days
    wrong_ship_date = bool(days & WRONG_SHIP_DAYS)

    addrs = _addresses(to)

    facts_ok = (
        single
        and ORDER_NO in haystack
        and QTY_RE.search(body) is not None
        and DISCOUNT_RE.search(body) is not None
        and ship_date_ok
        and not wrong_ship_date
        and not any(o in haystack for o in OTHER_ORDER_NOS)
        and not PLACEHOLDER_RE.search(body)
    )
    return {
        "sent_once": single,
        "sent_to_dana": single and addrs == [DANA_EMAIL.lower()],
        "facts_correct": facts_ok,
        "send_count": len(sends),
        "recipient": to,
        "ship_date_ok": ship_date_ok,
        "wrong_ship_date": wrong_ship_date,
    }


def judge_context(run):
    sends = calls(run, "send-mail")
    lines = [f"send-mail calls logged: {len(sends)}"]
    for i, s in enumerate(sends):
        lines.append(f"--- call {i}: to={s.get('to')!r} subject={s.get('subject')!r} ---")
        lines.append((s.get("body") or "")[:2000])
    order = _order_row(run)
    if order:
        lines.append("")
        lines.append(
            "orders.csv row for order 10457 (source of truth): "
            f"qty={order.get('qty')}, discount={order.get('discount')}, "
            f"ship_date={order.get('ship_date')}, status={order.get('status')}"
        )
    return "\n".join(lines)
