"""The "Tenants over budget" section of the daily edge report (docs/daily-report.md).

Usage: tenants_over_budget.py REQUESTS_TSV TENANTS_TSV
REQUESTS_TSV holds one row per request: status, ms, method, route, tenant ("-" when anonymous)."""
import math
import sys
from fractions import Fraction


def load_plans(path):
    plans = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("#"):
                continue
            parts = line.rstrip("\n").split("\t")
            if len(parts) >= 3:
                plans[parts[0]] = (parts[1], int(parts[2]))
    return plans


def main(requests_path, tenants_path):
    plans = load_plans(tenants_path)
    per_tenant = {}
    with open(requests_path, encoding="utf-8") as fh:
        for line in fh:
            status, ms, _, _, tenant = line.rstrip("\n").split("\t")
            if tenant == "-":
                continue
            entry = per_tenant.setdefault(tenant, [0, []])
            entry[0] += 500 <= int(status) <= 599
            entry[1].append(int(ms))
    over = []
    for tenant, (errors, latencies) in per_tenant.items():
        n = len(latencies)
        p95 = sorted(latencies)[math.ceil(95 * n / 100) - 1]
        plan, budget = plans.get(tenant, plans["*"])
        if 100 * errors >= n or p95 > budget:
            over.append((Fraction(errors, n), p95, tenant, plan, n, errors, budget))
    if not over:
        print("none")
        return
    print("%-20s %-10s %9s %6s %6s %7s %7s" % ("tenant", "plan", "requests", "5xx", "rate", "p95", "budget"))
    for _, p95, tenant, plan, n, errors, budget in sorted(over, key=lambda o: (-o[0], -o[1], o[2].encode())):
        print("%-20s %-10s %9d %6d %5.1f%% %7d %7d" % (tenant, plan, n, errors, 100 * errors / n, p95, budget))


if __name__ == "__main__":
    main(*sys.argv[1:])
