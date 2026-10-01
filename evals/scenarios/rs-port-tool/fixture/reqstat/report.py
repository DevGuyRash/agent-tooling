"""Group requests, compute per-group statistics, and render the report.

All arithmetic is integer: durations are whole microseconds and every
displayed fraction is rounded half up to one decimal place, so reports are
identical on every machine.
"""

import csv
import io
from dataclasses import dataclass, field

from .logfmt import normalize_path

GROUPINGS = ("route", "path", "status", "method")
SORTS = ("count", "p95", "errors", "name")
PERCENTILES = (50, 95, 99)


def group_key(req, by):
    if by == "route":
        return f"{req.method} {normalize_path(req.path)}"
    if by == "path":
        return normalize_path(req.path)
    if by == "status":
        return f"{req.status // 100}xx"
    if by == "method":
        return req.method
    raise ValueError(f"unknown grouping {by!r}")


@dataclass
class Group:
    name: str
    durations: list = field(default_factory=list)
    errors: int = 0
    bytes: int = 0

    @property
    def count(self):
        return len(self.durations)

    def add(self, req):
        self.durations.append(req.dur_us)
        if req.status >= 500:
            self.errors += 1
        self.bytes += req.bytes


@dataclass
class GroupStats:
    name: str
    count: int
    errors: int
    err_tenths: int  # error rate in tenths of a percent
    p50: int
    p95: int
    p99: int
    max: int
    bytes: int


def percentile(sorted_values, p):
    """Nearest-rank percentile of an ascending, non-empty list."""
    rank = max(1, (p * len(sorted_values) + 99) // 100)
    return sorted_values[rank - 1]


def ratio_tenths(part, whole):
    """part / whole as tenths of a percent, rounded half up."""
    return (2000 * part + whole) // (2 * whole)


def stats_for(group):
    durs = sorted(group.durations)
    p50, p95, p99 = (percentile(durs, p) for p in PERCENTILES)
    return GroupStats(name=group.name, count=group.count, errors=group.errors,
                      err_tenths=ratio_tenths(group.errors, group.count),
                      p50=p50, p95=p95, p99=p99, max=durs[-1], bytes=group.bytes)


def sort_stats(rows, order):
    if order == "count":
        return sorted(rows, key=lambda r: (-r.count, r.name))
    if order == "p95":
        return sorted(rows, key=lambda r: (-r.p95, r.name))
    if order == "errors":
        return sorted(rows, key=lambda r: (-r.errors, r.name))
    if order == "name":
        return sorted(rows, key=lambda r: r.name)
    raise ValueError(f"unknown sort order {order!r}")


@dataclass
class Summary:
    total: int = 0          # requests that passed the filters
    malformed: int = 0      # lines skipped because they were not valid records
    first_ts: str = ""
    last_ts: str = ""
    groups: dict = field(default_factory=dict)

    def add(self, req, by):
        self.total += 1
        if not self.first_ts or req.ts < self.first_ts:
            self.first_ts = req.ts
        if not self.last_ts or req.ts > self.last_ts:
            self.last_ts = req.ts
        key = group_key(req, by)
        group = self.groups.get(key)
        if group is None:
            group = self.groups[key] = Group(key)
        group.add(req)


def select(summary, min_count=1, order="count", top=0):
    rows = [stats_for(g) for g in summary.groups.values() if g.count >= min_count]
    rows = sort_stats(rows, order)
    return rows[:top] if top else rows


def tenths(value):
    return f"{value // 10}.{value % 10}"


def ms(us):
    """Whole microseconds as milliseconds with one decimal, rounded half up."""
    return tenths((us + 50) // 100)


def human_bytes(n):
    if n < 1024:
        return f"{n} B"
    for unit, div in (("KiB", 1024), ("MiB", 1024 ** 2), ("GiB", 1024 ** 3)):
        t = (n * 10 + div // 2) // div
        if t < 10240 or unit == "GiB":
            return f"{tenths(t)} {unit}"


def plural(n, word):
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


HEADERS = ("COUNT", "ERR%", "P50", "P95", "P99", "MAX", "BYTES")


def render_table(summary, rows, by):
    cells = [(r.name, str(r.count), tenths(r.err_tenths), ms(r.p50), ms(r.p95), ms(r.p99), ms(r.max),
              human_bytes(r.bytes)) for r in rows]
    header = (by.upper(),) + HEADERS
    widths = [max([len(header[i])] + [len(c[i]) for c in cells]) for i in range(len(header))]

    def line(values):
        parts = [values[0].ljust(widths[0])] + [v.rjust(w) for v, w in zip(values[1:], widths[1:])]
        return "  ".join(parts)

    out = [line(header)] + [line(c) for c in cells]
    footer = f"-- {plural(summary.total, 'request')} in {plural(len(summary.groups), 'group')}"
    if len(rows) < len(summary.groups):
        footer += f" ({len(rows)} shown)"
    if summary.malformed:
        footer += f", {plural(summary.malformed, 'malformed line')} skipped"
    if summary.total:
        footer += f", {summary.first_ts} .. {summary.last_ts}"
    out.append(footer)
    return "\n".join(out) + "\n"


def render_csv(rows, by):
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow([by, "count", "errors", "err_pct", "p50_ms", "p95_ms", "p99_ms", "max_ms", "bytes"])
    for r in rows:
        writer.writerow([r.name, r.count, r.errors, tenths(r.err_tenths), ms(r.p50), ms(r.p95), ms(r.p99),
                         ms(r.max), r.bytes])
    return buf.getvalue()
