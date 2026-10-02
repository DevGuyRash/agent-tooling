"""The daily edge report (docs/daily-report.md) for one day's gateway access log.

Usage: daily_report.py ACCESS_LOG"""
import json
import math
import os
import sys
from fractions import Fraction
from pathlib import Path

TENANTS = Path(__file__).resolve().parent.parent / "config" / "tenants.tsv"


def load_plans():
    plans = {}
    for line in TENANTS.read_text(encoding="utf-8").splitlines():
        if line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) >= 3:
            plans[parts[0]] = (parts[1], int(parts[2]))
    return plans


def read_requests(path):
    data = Path(path).read_bytes().decode("utf-8", "replace")
    lines = data.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    nonblank, rows = 0, []
    for line in lines:
        if line.split():
            nonblank += 1
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if not isinstance(rec, dict):
            continue
        status, ms = rec.get("status"), rec.get("ms")
        if not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in (status, ms)):
            continue
        rows.append((status, ms, rec.get("method"), rec.get("route"), rec.get("tenant") or "-"))
    return nonblank, rows


def report(path):
    plans = load_plans()
    nonblank, rows = read_requests(path)
    print(f"Edge report: {os.path.basename(path)}")
    print(f"requests: {len(rows)} ({nonblank - len(rows)} unreadable lines skipped)")
    print("\nStatus classes")
    classes = {}
    for r in rows:
        classes[int(r[0] // 100)] = classes.get(int(r[0] // 100), 0) + 1
    for c in sorted(classes):
        print("%dxx %7d %6.1f%%" % (c, classes[c], 100 * classes[c] / len(rows)))
    print("\nTop routes")
    routes = {}
    for r in rows:
        routes[(r[2], r[3])] = routes.get((r[2], r[3]), 0) + 1
    for (method, route), n in sorted(routes.items(), key=lambda kv: (-kv[1], f"{kv[0][0]}\t{kv[0][1]}".encode()))[:10]:
        print("%7d  %s %s" % (n, method, route))
    print("\nTop tenants")
    counts = {}
    for r in rows:
        if r[4] != "-":
            counts[r[4]] = counts.get(r[4], 0) + 1
    for tenant, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0].encode()))[:5]:
        print("%7d  %-20s %s" % (n, tenant, plans.get(tenant, plans["*"])[0]))
    print("\nTenants over budget")
    per = {}
    for r in rows:
        if r[4] != "-":
            per.setdefault(r[4], []).append((r[1], 500 <= r[0] <= 599))
    over = []
    for tenant, values in per.items():
        n = len(values)
        errors = sum(e for _, e in values)
        p95 = sorted(v for v, _ in values)[math.ceil(95 * n / 100) - 1]
        plan, budget = plans.get(tenant, plans["*"])
        if 100 * errors >= n or p95 > budget:
            over.append((Fraction(errors, n), p95, tenant, plan, n, errors, budget))
    if not over:
        print("none")
        return 0
    print("%-20s %-10s %9s %6s %6s %7s %7s" % ("tenant", "plan", "requests", "5xx", "rate", "p95", "budget"))
    for _, p95, tenant, plan, n, errors, budget in sorted(over, key=lambda o: (-o[0], -o[1], o[2].encode())):
        print("%-20s %-10s %9d %6d %5.1f%% %7d %7d" % (tenant, plan, n, errors, 100 * errors / n, p95, budget))
    return 0


def main(argv):
    if len(argv) != 1:
        print("usage: daily-report.sh ACCESS_LOG", file=sys.stderr)
        return 2
    if not (os.path.isfile(argv[0]) and os.access(argv[0], os.R_OK)):
        print(f"daily-report: cannot read {argv[0]}", file=sys.stderr)
        return 1
    return report(argv[0])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
