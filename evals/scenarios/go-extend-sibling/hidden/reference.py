"""Reference for `bakctl prune`, written from the fixture's docs/prune.md alone, for hidden/make_cases.py.

It covers what the hidden cases exercise: options in the forms the spec names (`--opt V`, `--opt=V`, and the
single-dash forms Go's flag package also accepts), the catalog format `bakctl list` reads, the plan, and the
exit statuses. Standard error is not reproduced; the check compares exit status and standard output, and a
few fragments of standard error that the existing catalog loader prints.
"""
import re
from datetime import datetime, timedelta, timezone

RULES = ("last", "hourly", "daily", "weekly", "monthly", "yearly")
COUNT_OPTS = {f"keep-{r}": r for r in RULES}
VALUE_OPTS = set(COUNT_OPTS) | {"keep-within", "host", "set"}
BOOL_OPTS = {"ids"}
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
STAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2})")
DURATION = re.compile(r"(?:(\d+)w)?(?:(\d+)d)?(?:(\d+)h)?")
PERIODS = {
    "hourly": lambda t: t.strftime("%Y-%m-%dT%H"),
    "daily": lambda t: t.strftime("%Y-%m-%d"),
    "weekly": lambda t: "%04d-W%02d" % t.isocalendar()[:2],
    "monthly": lambda t: t.strftime("%Y-%m"),
    "yearly": lambda t: t.strftime("%Y"),
}
REASON_ORDER = ("pinned", "in-progress", "last", "within", "hourly", "daily", "weekly", "monthly", "yearly")


class Usage(Exception):
    pass


class Bad(Exception):
    pass


def human(n):
    if n < 1024:
        return f"{n} B"
    units = ["KiB", "MiB", "GiB", "TiB", "PiB"]
    v, i = n / 1024, 0
    while v >= 1024 and i < len(units) - 1:
        v /= 1024
        i += 1
    return f"{v:.1f} {units[i]}"


def parse_args(args):
    """Go flag package semantics for the options prune defines: parsing stops at the first argument that is
    not an option ("-" alone is not one), and "--" ends the options."""
    opts, i = {}, 0
    while i < len(args):
        a = args[i]
        if len(a) < 2 or a[0] != "-":
            break
        i += 1
        if a == "--":
            break
        name = a[2:] if a.startswith("--") else a[1:]
        if not name or name[0] in "-=":
            raise Usage(a)
        value = None
        if "=" in name:
            name, value = name.split("=", 1)
        if name in BOOL_OPTS:
            if value is not None and value not in ("1", "t", "T", "true", "TRUE", "True"):
                if value in ("0", "f", "F", "false", "FALSE", "False"):
                    opts.pop(name, None)
                    continue
                raise Usage(a)
            opts[name] = True
        elif name in VALUE_OPTS:
            if value is None:
                if i >= len(args):
                    raise Usage(a)
                value = args[i]
                i += 1
            opts[name] = value
        else:
            raise Usage(a)
    return opts, args[i:]


def parse_policy(opts):
    policy = {}
    for opt, rule in COUNT_OPTS.items():
        text = opts.get(opt, "0")
        if not text.isascii() or not text.isdigit():
            raise Usage(opt)
        policy[rule] = int(text)
    text = opts.get("keep-within", "0h")
    m = DURATION.fullmatch(text)
    if not text or not m or not any(m.groups()):
        raise Usage("keep-within")
    w, d, h = (int(g) if g else 0 for g in m.groups())
    policy["within"] = timedelta(weeks=w, days=d, hours=h)
    if not any(policy[r] for r in RULES) and policy["within"] == timedelta(0):
        raise Usage("no keep rule")
    return policy


def parse_catalog(data):
    snaps, seen = [], {}
    text = data.decode("utf-8")
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    for number, line in enumerate(lines, 1):
        line = line[:-1] if line.endswith("\r") else line
        if not line.strip() or line.strip().startswith("#"):
            continue
        f = line.split("\t")
        if len(f) != 7:
            raise Bad(number)
        if not all(NAME.fullmatch(x) for x in f[:3]) or not STAMP.fullmatch(f[3]):
            raise Bad(number)
        try:
            when = datetime.fromisoformat(f[3].replace("Z", "+00:00")).astimezone(timezone.utc)
        except ValueError:
            raise Bad(number) from None
        if not f[4].isascii() or not f[4].isdigit() or f[5] not in ("ok", "partial", "failed"):
            raise Bad(number)
        tags = [] if f[6] == "-" else f[6].split(",")
        if not all(NAME.fullmatch(t) for t in tags):
            raise Bad(number)
        if f[0] in seen:
            raise Bad(number)
        seen[f[0]] = number
        snaps.append({"id": f[0], "host": f[1], "set": f[2], "when": when, "bytes": int(f[4]), "state": f[5],
                      "pinned": "pinned" in tags})
    return snaps


def plan_series(members, policy):
    members = sorted(members, key=lambda s: s["id"].encode())
    members.sort(key=lambda s: s["when"], reverse=True)
    reasons = {s["id"]: set() for s in members}
    ok = [s for s in members if s["state"] == "ok"]
    newest_ok = ok[0]["when"] if ok else None
    for s in members:
        if s["pinned"]:
            reasons[s["id"]].add("pinned")
        if s["state"] == "partial" and (newest_ok is None or s["when"] > newest_ok):
            reasons[s["id"]].add("in-progress")
    for s in ok[:policy["last"]]:
        reasons[s["id"]].add("last")
    if policy["within"] > timedelta(0) and newest_ok is not None:
        for s in ok:
            if s["when"] >= newest_ok - policy["within"]:
                reasons[s["id"]].add("within")
    for rule, period in PERIODS.items():
        wanted, previous = policy[rule], None
        for s in ok:
            if wanted <= 0:
                break
            key = period(s["when"])
            if key != previous:
                reasons[s["id"]].add(rule)
                wanted -= 1
            previous = key
    rows = []
    for s in members:
        r = [x for x in REASON_ORDER if x in reasons[s["id"]]]
        if r:
            rows.append(("keep", s, r))
        else:
            rows.append(("drop", s, ["expired" if s["state"] == "ok" else s["state"]]))
    return rows


def run(args, stdin=b"", files=None):
    """(exit status, stdout bytes) for `bakctl ARGS`, ARGS starting with "prune"; files maps a catalog name
    to its bytes (a missing name is an unreadable file)."""
    files = files or {}
    assert args[0] == "prune"
    try:
        opts, rest = parse_args(args[1:])
        policy = parse_policy(opts)
        if len(rest) != 1:
            raise Usage("catalog")
    except Usage:
        return 2, b""
    path = rest[0]
    if path == "-":
        data = stdin
    elif path in files:
        data = files[path]
    else:
        return 1, b""
    try:
        snaps = parse_catalog(data)
    except Bad:
        return 1, b""
    host, set_ = opts.get("host", ""), opts.get("set", "")
    snaps = [s for s in snaps if (not host or s["host"] == host) and (not set_ or s["set"] == set_)]
    series = {}
    for s in snaps:
        series.setdefault((s["host"].encode(), s["set"].encode()), []).append(s)
    blocks, ids, keep, drop, freed = [], [], 0, 0, 0
    for key in sorted(series):
        rows = plan_series(series[key], policy)
        k = sum(1 for a, _, _ in rows if a == "keep")
        lines = [f"{key[0].decode()}/{key[1].decode()}: keep {k}, drop {len(rows) - k}"]
        for action, s, r in rows:
            lines.append(f"  {action}  {s['id']}  {s['when'].strftime('%Y-%m-%dT%H:%M:%SZ')}  {','.join(r)}")
            if action == "drop":
                ids.append(s["id"])
                freed += s["bytes"]
        keep += k
        drop += len(rows) - k
        blocks.append("\n".join(lines))
    if opts.get("ids"):
        return 0, "".join(i + "\n" for i in ids).encode()
    total = f"total: keep {keep}, drop {drop}, frees {human(freed)}"
    out = "\n\n".join(blocks + [total]) + "\n"
    return 0, out.encode()
