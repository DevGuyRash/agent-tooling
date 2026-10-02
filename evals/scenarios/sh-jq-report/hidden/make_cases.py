"""Write sh-jq-report's hand-made hidden logs (hidden/logs/*.jsonl) and hidden/cases.json: for each case, the log
(a stored file, or one gen_log.py makes at check time), the expected exit status and standard output, and a
fragment of standard error.

Expected results come from the reference (the fixture's script with the new section, hidden/reference, run with
this host's sh, jq, awk, and sort) and every one is confirmed against model() below, an independent reading of
docs/daily-report.md in Python. The over-budget rates are also confirmed to have no rounding tie: printf's %.1f
of 100 x errors / requests, the same figure computed as errors / requests x 100, and the exact rate rounded half
up all agree, so neither the order of the arithmetic nor the rounding rule can change a result. Run: python3
make_cases.py"""
import json
import shutil
import subprocess
import sys
import tempfile
from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCENARIO = HERE.parent
FIXTURE = SCENARIO / "fixture"
GENERATED = {"day": [40_000, 3]}   # lines, seed (gen_log.py)


def req(tenant, status=200, ms=20, route=("GET", "/v1/invoices/{id}"), key_order=0):
    rec = {"ts": "2025-10-01T08:00:00.000Z", "method": route[0], "route": route[1], "status": status, "ms": ms,
           "bytes": 100}
    if tenant != "":
        rec["tenant"] = tenant
    if key_order:
        rec = dict(reversed(list(rec.items())))
    return json.dumps(rec, separators=(",", ":"))


def edges():
    out = []
    # exactly 1% (2 of 200) for a tenant not in tenants.tsv; low latency
    out += [req("exact-one", 500 if k in (3, 150) else 200, 40 + k % 30) for k in range(200)]
    # 2 of 201: just under 1%
    out += [req("just-under", 503 if k in (7, 99) else 200, 40 + k % 30) for k in range(201)]
    # 1 of 100 with status 599, and the same p95 as exact-one: equal rate and p95, so the tenant id decides
    out += [req("soylent-foods", 599 if k == 50 else 499 if k % 9 == 0 else 200, 40 + k % 30) for k in range(100)]
    # 20 requests, rank 19: the 19th value equals the pro budget, the 20th is far above
    out += [req("globex", 200, v) for v in [450, 2000] + list(range(100, 118))]
    # 21 requests, rank 20: the 20th value is one above the pro budget
    out += [req("initech", 200, v) for v in [5000, 451] + list(range(200, 219))]
    # one request one above the enterprise budget
    out += [req("acme-co", 201, 301, ("POST", "/v1/payments"))]
    # 19 requests, rank 19: the largest value equals the enterprise budget
    out += [req("umbrella-health", 200, v, ("GET", "/v1/customers/{id}"), 1) for v in [300] + list(range(10, 28))]
    # 50 requests, rank 48: 801 against the standard budget
    out += [req("northwind-labs", 200, v, ("PUT", "/v1/customers/{id}")) for v in list(range(500, 547)) + [801, 900, 950]]
    # anonymous requests, many of them failing: left out of the section
    out += [req("", 502, 9000, ("GET", "/healthz")) for _ in range(30)]
    out += [req(None, 500, 9000, ("GET", "/healthz")) for _ in range(30)]
    junk = ['{"ts":"2025-10-01T08:00:01.000Z","method":"GET","rou', "", "   ", "[1,2,3]", '"just a string"', "null",
            '{"method":"GET","route":"/v1/invoices","status":200,"tenant":"globex"}',
            '{"method":"GET","route":"/v1/invoices","status":"200","ms":5,"tenant":"globex"}']
    lines = []
    for k, line in enumerate(out):
        lines.append(line)
        if k % 97 == 13 and junk:
            lines.append(junk.pop())
    lines += junk
    return "\n".join(lines)   # no newline after the last line


def ranking():
    out = []
    def tenant(name, n, errors, p95_high=900, base=100):
        # errors failures among n requests; latencies so the nearest-rank p95 is base or p95_high as wanted
        for k in range(n):
            out.append(req(name, 502 if k < errors else 200, p95_high if k >= n - max(1, n // 10) else base + k % 7))
    tenant("aa-rate-third", 3, 1, 120)            # 33.3%
    tenant("bb-rate-third-too", 6, 2, 120)        # 33.3%, the same rate: p95 then id
    tenant("cc-two-percent", 100, 2, 950)         # 2 of 100
    tenant("very-long-tenant-name-industries", 50, 1, 950)  # 1 of 50: the same 2%, the same p95; id decides
    tenant("dd-latency-only", 40, 0, 1200)
    tenant("ee-latency-only", 40, 0, 1200)
    tenant("ff-fine", 300, 1, 300)                # under budget both ways
    tenant("globex", 30, 0, 451)                  # pro: one above its budget
    tenant("acme-co", 64, 5, 250)                 # 7.8%
    return "\n".join(out) + "\n"


def quiet():
    out = [req("acme-co", 200, 20 + k % 50) for k in range(150)]
    out += [req("globex", 404 if k % 5 == 0 else 200, 100 + k % 200) for k in range(150)]
    out += [req("brand-new-tenant", 502 if k == 0 else 200, 700) for k in range(101)]
    out += [req(None, 503, 5000, ("GET", "/healthz")) for _ in range(20)]
    return "\n".join(out) + "\n"


def junk_only():
    return '{"ts":"2025-10-01T00:00:00.0\n[]\n\n{"status":200}\nnot json at all\n'


LOGS = {"edges": edges(), "ranking": ranking(), "quiet": quiet(), "junk-only": junk_only()}
CASES = [("edges", "edges"), ("ranking", "ranking"), ("quiet", "quiet"), ("junk-only", "junk-only"),
         ("day", "day"), ("sample", "sample"), ("missing", None)]


def plans():
    plan, budget = {}, {}
    for line in (FIXTURE / "config" / "tenants.tsv").read_text().splitlines():
        if line.startswith("#") or len(line.split("\t")) < 3:
            continue
        t, p, b = line.split("\t")[:3]
        plan[t], budget[t] = p, int(b)
    return plan, budget


def model(data, name):
    """docs/daily-report.md over the log's bytes: the standard output."""
    plan, budget = plans()
    lines = data.decode("utf-8").split("\n")
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
        st, ms = rec.get("status"), rec.get("ms")
        if not (isinstance(st, (int, float)) and not isinstance(st, bool) and isinstance(ms, (int, float))
                and not isinstance(ms, bool)):
            continue
        rows.append((st, ms, rec.get("method"), rec.get("route"), rec.get("tenant") or "-"))
    out = [f"Edge report: {name}", f"requests: {len(rows)} ({nonblank - len(rows)} unreadable lines skipped)",
           "", "Status classes"]
    classes = {}
    for r in rows:
        classes[int(r[0] // 100)] = classes.get(int(r[0] // 100), 0) + 1
    for c in sorted(classes):
        out.append("%dxx %7d %6.1f%%" % (c, classes[c], 100 * classes[c] / len(rows)))
    out += ["", "Top routes"]
    routes = {}
    for r in rows:
        routes[(r[2], r[3])] = routes.get((r[2], r[3]), 0) + 1
    for (m, rt), n in sorted(routes.items(), key=lambda kv: (-kv[1], f"{kv[0][0]}\t{kv[0][1]}".encode()))[:10]:
        out.append("%7d  %s %s" % (n, m, rt))
    out += ["", "Top tenants"]
    counts = {}
    for r in rows:
        if r[4] != "-":
            counts[r[4]] = counts.get(r[4], 0) + 1
    for t, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0].encode()))[:5]:
        out.append("%7d  %-20s %s" % (n, t, plan.get(t, plan["*"])))
    out += ["", "Tenants over budget"]
    per = {}
    for r in rows:
        if r[4] != "-":
            per.setdefault(r[4], []).append((r[1], 500 <= r[0] <= 599))
    over = []
    for t, vals in per.items():
        n = len(vals)
        errors = sum(e for _, e in vals)
        lat = sorted(v for v, _ in vals)
        p95 = lat[-(-95 * n // 100) - 1]
        b = budget.get(t, budget["*"])
        if 100 * errors >= n or p95 > b:
            over.append((Fraction(errors, n), p95, t, n, errors, b))
    if not over:
        out.append("none")
    else:
        out.append("%-20s %-10s %9s %6s %6s %7s %7s" % ("tenant", "plan", "requests", "5xx", "rate", "p95", "budget"))
        for rate, p95, t, n, errors, b in sorted(over, key=lambda o: (-o[0], -o[1], o[2].encode())):
            figure = "%5.1f" % (100 * errors / n)
            alt = "%5.1f" % (errors / n * 100)
            exact = Decimal(100 * errors) / Decimal(n)
            half_up = "%5s" % exact.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
            if not figure == alt == half_up:
                sys.exit(f"{name}: {t}'s rate {errors}/{n} is a rounding tie ({figure!r}, {alt!r}, {half_up!r})")
            out.append("%-20s %-10s %9d %6d %s%% %7d %7d" % (t, plan.get(t, plan["*"]), n, errors, figure, p95, b))
    return "".join(l + "\n" for l in out)


def main():
    (HERE / "logs").mkdir(exist_ok=True)
    for name, text in LOGS.items():
        (HERE / "logs" / f"{name}.jsonl").write_text(text)
    cases = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        ref = tmp / "ref"
        shutil.copytree(FIXTURE, ref)
        shutil.copytree(HERE / "reference", ref, dirs_exist_ok=True)
        logs = tmp / "logs"
        logs.mkdir()
        for name in LOGS:
            shutil.copyfile(HERE / "logs" / f"{name}.jsonl", logs / f"{name}.jsonl")
        shutil.copyfile(FIXTURE / "samples" / "access-2025-09-30.jsonl", logs / "sample.jsonl")
        for name, (lines, seed) in GENERATED.items():
            subprocess.run([sys.executable, "-I", str(HERE / "gen_log.py"), str(lines), str(seed),
                            str(logs / f"{name}.jsonl")], check=True)
        for name, log in CASES:
            path = logs / f"{log}.jsonl" if log else logs / "no-such-log.jsonl"
            r = subprocess.run(["sh", "scripts/daily-report.sh", str(path)], cwd=ref, capture_output=True,
                               env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "TMPDIR": str(tmp)})
            if log is None:
                if (r.returncode, r.stdout) != (1, b"") or b"cannot read" not in r.stderr:
                    sys.exit(f"{name}: unexpected {(r.returncode, r.stdout, r.stderr)!r}")
                cases.append({"name": name, "log": None, "rc": 1, "stdout": "", "stderr_has": "cannot read"})
                continue
            want = model(path.read_bytes(), path.name)
            if r.returncode != 0 or r.stdout.decode() != want:
                sys.exit(f"{name}: the reference gives\n{r.stdout.decode()}{r.stderr.decode()}\nthe model\n{want}")
            cases.append({"name": name, "log": log, "rc": 0, "stdout": want, "stderr_has": ""})
    doc = {"generated": GENERATED, "cases": cases}
    (HERE / "cases.json").write_text(json.dumps(doc, indent=1) + "\n")
    print(f"{len(cases)} cases written")


if __name__ == "__main__":
    main()
