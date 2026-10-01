"""Regenerate the hidden inputs and expected outputs for go-port-script.

Run from anywhere: python3 make_cases.py. It writes data/*.log, cases.json, and expected/*.out next to
itself. The expected outputs come from running the fixture's own scripts/logreport.sh (with the host's sh,
awk, sort, uniq, cut, head, and wc), so they record what the script being ported does. The logs are
deterministic: rebuilding them gives the same bytes. Line endings are LF and fields 1-10 are separated by
single spaces, so awk's field splitting and Go's strings.Fields agree on them.
"""
import json
import random
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "fixture" / "scripts" / "logreport.sh"
DATA = HERE / "data"
EXPECTED = HERE / "expected"

UA = ['"Mozilla/5.0 (X11; Linux x86_64; rv:131.0) Gecko/20100101 Firefox/131.0"',
      '"Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15"',
      '"curl/8.9.1"', '"Go-http-client/2.0"', '"python-requests/2.32.3"', '"-"']


def stamp(rng, day):
    return f"[{day:02d}/Sep/2026:{rng.randrange(24):02d}:{rng.randrange(60):02d}:{rng.randrange(60):02d} +0000]"


def response(rng, path):
    """Status and byte field for a request to `path`."""
    if path.startswith("/static/"):
        return rng.choice([("200", str(rng.randrange(52000, 71000))), ("304", "-"), ("304", "0")])
    if path == "/ws":
        return "101", "-"
    if path in ("/wp-login.php", "/.env", "/xmlrpc.php"):
        return rng.choice([("404", "153"), ("403", "146")])
    if path.startswith("/api/"):
        return rng.choices([("200", str(rng.randrange(800, 4000))), ("500", "512"), ("502", "166"),
                            ("503", "19"), ("429", "64")], weights=[70, 8, 5, 4, 6])[0]
    if path == "/login":
        return rng.choice([("200", "3301"), ("302", "0"), ("401", "120")])
    if path == "http://proxy-check.example/":
        return "400", "150"
    return rng.choices([("200", str(rng.randrange(4000, 12000))), ("404", "153"), ("500", "512")],
                       weights=[90, 6, 4])[0]


def query(rng, path):
    if path in ("/products", "/search", "/api/items") and rng.random() < 0.6:
        return path + rng.choice(["?page=2", "?page=3", "?q=red+shoes", "?sort=price&dir=asc", "?"])
    if path == "/login" and rng.random() < 0.5:
        return "/login?next=/account"
    return path


def malformed(rng, day):
    ip = f"192.0.2.{rng.randrange(2, 250)}"
    return rng.choice([
        f'{ip} - - {stamp(rng, day)} "-" 400 0 "-" "-"',
        f'{ip} - - {stamp(rng, day)} "GET /index.html" 200 512 "-" "-"',
        f'{ip} - - {stamp(rng, day)} "GET /a b HTTP/1.1" 400 150 "-" "-"',
        f'{ip} - - {stamp(rng, day)} "GET /status HTTP/1.1" 999 12 "-" "-"',
        f'{ip} - - {stamp(rng, day)} "GET /status HTTP/1.1" 200 12k "-" "-"',
        f'{ip} - - {stamp(rng, day)} "GET /status HTTP/1.1" 2000 12 "-" "-"',
        f'{ip} - - {stamp(rng, day)} "GET / HTTP/1.1" 200',
        f'{ip} - - {stamp(rng, day)} "GET /products HTTP/1.1"',
        "",
        "garbage line from a crashed writer",
    ])


def build(rng, path_counts, client_counts, day, junk):
    paths = [p for p, n in path_counts.items() for _ in range(n)]
    clients = [c for c, n in client_counts.items() for _ in range(n)]
    assert len(paths) == len(clients), (len(paths), len(clients))
    rng.shuffle(paths)
    rng.shuffle(clients)
    lines = []
    for path, client in zip(paths, clients):
        status, size = response(rng, path)
        method = "POST" if path in ("/cart", "/checkout") else rng.choice(["GET", "GET", "GET", "HEAD"])
        lines.append(f'{client} - - {stamp(rng, day)} "{method} {query(rng, path)} HTTP/1.1" {status} {size} '
                     f'"-" {rng.choice(UA)}')
    for _ in range(junk):
        lines.insert(rng.randrange(len(lines) + 1), malformed(rng, day))
    return "\n".join(lines) + "\n"


def main():
    rng = random.Random(20260914)
    DATA.mkdir(exist_ok=True)
    EXPECTED.mkdir(exist_ok=True)
    # Counts chosen to put ties where a top-N list cuts, and upper-case before lower-case in byte order.
    access_paths = {"/": 41, "/products": 41, "/api/items": 33, "/Admin": 14, "/about": 14, "/static/app.js": 14,
                    "/static/app.css": 13, "/search": 11, "/login": 11, "/api/cart": 9, "/cart": 9, "/checkout": 7,
                    "/ws": 6, "/wp-login.php": 5, "/.env": 3, "/xmlrpc.php": 3, "http://proxy-check.example/": 2,
                    "/robots.txt": 2, "/sitemap.xml": 1, "/favicon.ico": 1}
    total = sum(access_paths.values())
    access_clients = {"203.0.113.7": 48, "198.51.100.23": 48, "2001:db8::17": 30, "192.0.2.44": 30,
                      "192.0.2.10": 22, "10.20.0.5": 22, "::1": 9, "198.51.100.200": 9}
    rest = total - sum(access_clients.values())
    for i in range(rest):
        access_clients[f"100.64.{i % 7}.{(i * 37) % 251 + 2}"] = access_clients.get(
            f"100.64.{i % 7}.{(i * 37) % 251 + 2}", 0) + 1
    (DATA / "access.log").write_text(build(rng, access_paths, access_clients, 14, 40))

    extra_paths = {"/api/items": 6, "/products": 5, "/": 4, "/about": 4, "/cart": 3, "/login": 2, "/Admin": 1}
    extra_clients = {"198.51.100.23": 7, "10.20.0.6": 7, "203.0.113.7": 6, "192.0.2.99": 5}
    text = build(rng, extra_paths, extra_clients, 15, 6)
    # Keep this one in the KiB range: shrink the static and page sizes it drew.
    lines = []
    for line in text.splitlines():
        f = line.split(" ")
        if len(f) >= 10 and f[9].isdigit() and int(f[9]) > 600:
            f[9] = str(int(f[9]) // 9)
            line = " ".join(f)
        lines.append(line)
    (DATA / "extra.log").write_text("\n".join(lines) + "\n")

    (DATA / "small.log").write_text(
        '10.1.2.3 - - [16/Sep/2026:07:00:00 +0000] "GET /healthz HTTP/1.1" 200 2 "-" "kube-probe/1.31"\n'
        '10.1.2.3 - - [16/Sep/2026:07:00:10 +0000] "GET /healthz HTTP/1.1" 200 2 "-" "kube-probe/1.31"\n'
        '10.1.2.4 - - [16/Sep/2026:07:00:10 +0000] "GET /readyz HTTP/1.1" 503 19 "-" "kube-probe/1.31"\n'
        '10.1.2.4 - - [16/Sep/2026:07:00:20 +0000] "GET /readyz?verbose HTTP/1.1" 200 811 "-" "kube-probe/1.31"\n'
        '10.1.2.5 - - [16/Sep/2026:07:00:30 +0000] "GET /healthz HTTP/1.1" 304 - "-" "kube-probe/1.31"\n')
    (DATA / "junk.log").write_text("\n".join(malformed(rng, 17) for _ in range(12)) + "\n")
    (DATA / "empty.log").write_text("")

    cases = [
        ("mixed", ["access.log"], None, 0),
        ("top-3", ["-n", "3", "access.log"], None, 0),
        ("top-all", ["-n", "40", "access.log"], None, 0),
        ("top-leading-zero", ["-n", "03", "access.log"], None, 0),
        ("server-errors", ["-s", "5", "access.log"], None, 0),
        ("not-found", ["-s", "404", "access.log"], None, 0),
        ("two-files", ["-n", "4", "access.log", "extra.log"], None, 0),
        ("same-file-twice", ["small.log", "small.log"], None, 0),
        ("stdin", [], "extra.log", 0),
        ("stdin-filtered", ["-s", "2"], "access.log", 0),
        ("small", ["small.log"], None, 0),
        ("kib", ["extra.log"], None, 0),
        ("junk-only", ["junk.log"], None, 0),
        ("no-match", ["-s", "1", "small.log"], None, 0),
        ("empty-input", [], "empty.log", 0),
        ("top-zero", ["-n", "0", "small.log"], None, 0),
        ("bad-count", ["-n", "lots", "access.log"], None, 2),
        ("bad-status", ["-s", "5xx", "access.log"], None, 2),
        ("unknown-flag", ["-x", "access.log"], None, 2),
        ("missing-file", ["access.log", "rotated.log"], None, 1),
    ]
    listed = []
    for name, args, stdin, status in cases:
        with open(DATA / stdin if stdin else "/dev/null", "rb") as fh:
            r = subprocess.run(["sh", str(SCRIPT), *args], cwd=DATA, stdin=fh, capture_output=True)
        assert r.returncode == status, (name, r.returncode, r.stderr)
        (EXPECTED / f"{name}.out").write_bytes(r.stdout)
        listed.append({"name": name, "args": args, "stdin": stdin, "status": status})
    (HERE / "cases.json").write_text(json.dumps(listed, indent=1) + "\n")


if __name__ == "__main__":
    main()
