"""Generate a gateway access log for sh-jq-report, the same for the same arguments:
python3 -I gen_log.py LINES SEED OUT

A day of requests from 14 tenants (seven of them listed in the fixture's config/tenants.tsv) and anonymous
clients, each tenant with its own latency profile and error rate, so a realistic share of them is over budget;
about 0.1% of lines are cut short and a few are blank. Only random() is used, so the output does not depend on
the Python version's other random methods."""
import json
import math
import random
import sys

# tenant: (mean latency in ms, share of 5xx)
TENANTS = {
    "acme-co": (70, 0.002), "umbrella-health": (115, 0.004), "globex": (120, 0.013), "initech": (165, 0.003),
    "northwind-labs": (190, 0.009), "soylent-foods": (90, 0.02), "hooli": (240, 0.004), "vandelay": (310, 0.001),
    "pied-piper": (140, 0.011), "wayne-ent": (60, 0.0), "stark-industries": (280, 0.006),
    "tyrell-corp": (100, 0.03), "cyberdyne": (230, 0.0015), "oscorp": (45, 0.0095),
}
ROUTES = [("GET", "/v1/invoices/{id}", 30), ("GET", "/v1/invoices", 14), ("POST", "/v1/payments", 12),
          ("GET", "/v1/customers/{id}", 11), ("POST", "/v1/invoices", 8), ("PUT", "/v1/customers/{id}", 5),
          ("DELETE", "/v1/invoices/{id}", 3), ("GET", "/v1/reports/{id}", 4), ("POST", "/v1/refunds", 2)]


def main(lines, seed, out):
    rnd = random.Random(seed).random
    names = list(TENANTS)
    weights = [1 + (k * 7) % 11 for k in range(len(names))]
    total_w = sum(weights)
    route_w = sum(w for _, _, w in ROUTES)

    def pick_tenant():
        x = rnd() * total_w
        for name, w in zip(names, weights):
            x -= w
            if x < 0:
                return name
        return names[-1]

    def pick_route():
        x = rnd() * route_w
        for method, route, w in ROUTES:
            x -= w
            if x < 0:
                return method, route
        return ROUTES[-1][:2]

    with open(out, "w", encoding="utf-8") as fh:
        for i in range(lines):
            sec = i * 86400 // lines
            ts = f"2025-10-01T{sec // 3600:02d}:{sec % 3600 // 60:02d}:{sec % 60:02d}.{int(rnd() * 1000):03d}Z"
            if rnd() < 0.08:
                method, route, tenant = "GET", "/healthz", None
                mean, err = 3, 0.001
            else:
                method, route = pick_route()
                tenant = pick_tenant()
                mean, err = TENANTS[tenant]
            x = rnd()
            if x < err:
                status = 502 if rnd() < 0.6 else 500 if rnd() < 0.7 else 503
            else:
                y = rnd()
                status = 200 if y < 0.9 else 201 if y < 0.94 else 304 if y < 0.95 else 404 if y < 0.985 else 429
            ms = 1 + int(-mean * math.log(1.0 - rnd()))
            rec = {"ts": ts, "method": method, "route": route, "status": status, "ms": ms}
            if tenant is not None:
                rec["tenant"] = tenant
            elif rnd() < 0.5:
                rec["tenant"] = None
            rec["bytes"] = int(rnd() * 8000)
            line = json.dumps(rec, separators=(",", ":"))
            if rnd() < 0.001:
                line = line[:int(rnd() * len(line))]
            fh.write(line + "\n")
            if rnd() < 0.0005:
                fh.write("\n")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit("usage: gen_log.py LINES SEED OUT")
    main(int(sys.argv[1]), int(sys.argv[2]), sys.argv[3])
