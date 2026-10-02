"""The digest as docs/digest.md describes it, written for make_cases.py: with Variant() it must agree with the
fixture's froid digest on every hidden case, and each careless port in VARIANTS must disagree on at least one,
so the hidden cases are known to tell those ports apart. Not used by the check."""
from dataclasses import dataclass, field

DIR = "{dir}/"
HEADER = ("unit", "day", "n", "min", "max", "mean", "median", "out", "worst")


@dataclass(frozen=True)
class Variant:
    name: str = "as documented"
    rounding: str = "even"      # "even": halves to even; "away": halves away from zero (f64::round, math.Round)
    median_halves: str = "round"  # "round": like the mean; "truncate": integer (a+b)/2 toward zero
    worst: str = "first"        # "first" of equally bad readings; "last" (Rust's max_by_key)
    width: str = "chars"        # column widths in characters; "bytes": UTF-8 bytes (str::len)
    order: str = "seen"         # units in first-seen order; "sorted": by name (BTreeMap)
    zero: str = "int"           # "float": a mean or median rounding to zero from below prints -0.0
    days: str = "sorted"        # "seen": a unit's days in first-seen order


VARIANTS = [
    Variant(name="halves away from zero", rounding="away"),
    Variant(name="median halves truncated", median_halves="truncate"),
    Variant(name="last of equally bad", worst="last"),
    Variant(name="widths in bytes", width="bytes"),
    Variant(name="units sorted by name", order="sorted"),
    Variant(name="negative zero", zero="float"),
    Variant(name="days in first-seen order", days="seen"),
]


def tenths(text):
    sign = -1 if text.startswith("-") else 1
    whole, _, frac = text.lstrip("-").partition(".")
    return sign * (int(whole) * 10 + int(frac))


def deg(t, negative_zero=False):
    return ("-" if negative_zero else "") + f"{t / 10:.1f}"


def half_round(p, q, mode):
    """p/q (q > 0) to an integer: (value, the exact value was below zero)."""
    floor, rem = divmod(p, q)
    if 2 * rem < q:
        v = floor
    elif 2 * rem > q:
        v = floor + 1
    elif mode == "even":
        v = floor if floor % 2 == 0 else floor + 1
    else:  # away from zero
        v = floor + 1 if p > 0 else floor
    return v, p < 0


def parse_args(args):
    units, day, logs, i = None, None, [], 0
    while i < len(args):
        if args[i] in ("--units", "--day"):
            units, day = (args[i + 1], day) if args[i] == "--units" else (units, args[i + 1])
            i += 2
        else:
            logs.append(args[i])
            i += 1
    strip = lambda p: p[len(DIR):] if p.startswith(DIR) else p  # noqa: E731
    return strip(units), day, [strip(p) for p in logs]


def digest_for(case, v):
    units_name, day, logs = parse_args(case["args"][1:])
    ranges = {}
    for line in case["files"][units_name].splitlines():
        if line.strip() and not line.startswith("#"):
            u, lo, hi = line.split("\t")
            ranges[u] = (tenths(lo), tenths(hi))
    data = {}
    for name in logs:
        for line in case["files"][name].splitlines():
            if not line.strip() or line.startswith("#"):
                continue
            stamp, u, t = line.split("\t")
            if day and stamp[:10] != day:
                continue
            data.setdefault(u, {}).setdefault(stamp[:10], []).append((stamp[11:16], tenths(t)))
    body = []
    unit_order = sorted(data) if v.order == "sorted" else list(data)
    for u in unit_order:
        dates = sorted(data[u]) if v.days == "sorted" else list(data[u])
        for d in dates:
            rs = data[u][d]
            ts = [t for _, t in rs]
            n = len(ts)
            mean, mean_neg = half_round(sum(ts), n, v.rounding)
            s = sorted(ts)
            if n % 2:
                med, med_neg = s[n // 2], False
            elif v.median_halves == "truncate":
                total = s[n // 2 - 1] + s[n // 2]
                med, med_neg = int(total / 2), total < 0
            else:
                med, med_neg = half_round(s[n // 2 - 1] + s[n // 2], 2, v.rounding)
            row = [u, d, str(n), deg(min(ts)), deg(max(ts)),
                   deg(mean, v.zero == "float" and mean == 0 and mean_neg),
                   deg(med, v.zero == "float" and med == 0 and med_neg)]
            if u in ranges:
                lo, hi = ranges[u]
                bad = [(max(lo - t, t - hi, 0), c, t) for c, t in rs if max(lo - t, t - hi, 0)]
                worst = None
                for b in bad:
                    if worst is None or b[0] > worst[0] or (v.worst == "last" and b[0] == worst[0]):
                        worst = b
                row += [str(len(bad)), f"{deg(worst[2])} at {worst[1]}" if worst else "-"]
            else:
                row += ["-", "-"]
            body.append(row)
    if not body:
        return (f"no readings on {day}" if day else "no readings") + "\n"
    size = (lambda s: len(s.encode())) if v.width == "bytes" else len
    table = [list(HEADER), *body]
    widths = [max(size(r[i]) for r in table) for i in range(len(HEADER) - 1)]
    lines = []
    for r in table:
        cells = []
        for i, w in enumerate(widths):
            pad = " " * (w - size(r[i]))
            cells.append(r[i] + pad if i < 2 else pad + r[i])
        lines.append("  ".join(cells + [r[-1]]))
    out = sum(int(r[7]) for r in body if r[7] != "-")
    plural = lambda n, w: f"{n} {w}" + ("" if n == 1 else "s")  # noqa: E731
    return "\n".join(lines) + f"\n\n{plural(len(body), 'unit-day')}, {plural(out, 'reading')} out of range\n"
