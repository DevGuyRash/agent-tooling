"""Regenerate hidden/cases.json: hidden inputs for the Rust port, with the expected results taken from the
fixture's own Python reqstat (the program being ported). Run from anywhere: python3 hidden/make_cases.py

Required cases are behavior the README, the code, or the fixture's own tests state; the others are measures
(obscure Python I/O semantics a careful port may still miss).
"""
import base64
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXTURE = HERE.parent / "fixture"


def line(ts, method, path, status, dur, size=None, **extra):
    parts = [f"ts=2026-09-{ts}Z", f"method={method}", f"path={path}", f"status={status}", f"dur={dur}"]
    if size is not None:
        parts.append(f"bytes={size}")
    parts += [f"{k}={v}" for k, v in extra.items()]
    return " ".join(parts)


PROXY_A = "\n".join([
    "# edge-3 2026-09-15",
    line("15T00:00:00", "GET", "/v2/catalog/items", 200, "41ms", 18234),
    line("15T00:00:00", "GET", "/v2/catalog/items/1001", 200, "12.25ms", 2048),
    line("15T00:00:01", "GET", "/v2/catalog/items/1002?fields=name,price", 200, "15ms", 1024),
    line("15T00:00:02", "POST", "/v2/cart/7f3e9a10-2b4c-4d5e-8f60-718293a4b5c6/items", 201, "95ms", 412),
    line("15T00:00:02", "POST", "/v2/cart/7F3E9A10-2B4C-4D5E-8F60-718293A4B5C7/items", 409, "33ms", 120),
    line("15T00:00:03", "GET", "/v2/catalog/items/1003", 500, "3.5s", 0, err='"pool exhausted"'),
    "ts=2026-09-15T00:00:04Z\tmethod=GET\tpath=/v2/catalog/items/1001\tstatus=200\tdur=9ms\tbytes=2048",
    line("15T00:00:05", "GET", "/healthz", 200, "120us", 2),
    line("15T00:00:05", "GET", "/healthz", 200, "95us", 2),
    line("15T00:00:06", "GET", "/healthz", 200, "0.05ms", 2),
    "",
    line("15T00:00:07", "GET", "/v2/search", 200, "250ms", 1572864),
    line("15T00:00:08", "GET", '"/v2/search?q=winter coats"', 200, "310ms", 2097152),
    line("15T00:00:09", "GET", "/v2/search", 504, "30s", 0),
    line("15T00:00:10", "DELETE", "/v2/cart/7f3e9a10-2b4c-4d5e-8f60-718293a4b5c6", 204, "18ms"),
    line("15T00:00:11", "PATCH", "/v2/account/me", 200, "64.5ms", 733),
    line("15T00:00:12", "GET", "/v2/catalog/items/1004", 200, "11ms", 2048, ua='"Mozilla/5.0 (X11; Linux x86_64) \\"quoted\\""'),
    "ts=2026-09-15T00:00:13Z method=GET path=/v2/catalog/items status=200 dur=40ms bytes=18234 ts=2026-09-15T00:00:14Z",
    "ts=2026-09-15T00:00:15Z method=GET path=/v2/catalog/items status=2000 dur=40ms",
    "ts=2026-09-15T00:00:16Z method=GET path=/v2/catalog/items status=200 dur=40",
    "ts=2026-09-15T00:00:17Z method=GET path=/v2/catalog/items status=200 dur=1.0005ms",
    "ts=2026-09-15T00:00:18Z method=Get path=/v2/catalog/items status=200 dur=1ms",
    "ts=2026-09-15T25:00:18Z method=GET path=/v2/catalog/items status=200 dur=1ms",
    "ts=2026-09-15T00:00:19Z method=GET path=v2/catalog status=200 dur=1ms",
    'ts=2026-09-15T00:00:20Z method=GET path="/v2/catalog status=200 dur=1ms',
    'ts=2026-09-15T00:00:21Z method=GET path="/v2/catalog"x status=200 dur=1ms',
    "ts=2026-09-15T00:00:22Z method=GET path=/v2/catalog status=200 bytes=-5 dur=1ms",
    "ts=2026-09-15T00:00:23Z method=GET path=/v2/catalog status=200",
    "   ",
    "  # indented comment",
    line("15T00:00:24", "GET", "/v2/catalog/items/1005", 200, "13ms", 2048),
    line("15T00:00:25", "GET", "/v2/catalog/items/1006", 200, "14ms", 2048),
    line("15T00:00:26", "GET", "/v2/catalog/items/1007", 503, "1.25s", 0),
    line("15T00:00:27", "GET", "/v2/catalog/items/1008", 200, "16ms", 2048),
    line("15T00:00:59", "PUT", "//v2//account//me//avatar/", 200, "880ms", 0),
    "",
])

PROXY_B = "\n".join([
    line("15T23:59:58", "GET", "/v2/catalog/items/2001", 200, "10ms", 2048),
    line("15T23:59:59", "GET", "/v2/catalog/items", 200, "39ms", 18234),
    line("16T00:00:00", "GET", "/v2/catalog/items", 200, "45ms", 18234),
    line("16T00:00:01", "GET", "/healthz", 200, "101us", 2),
    line("16T00:00:02", "POST", "/v2/cart/0a1b2c3d-4e5f-6071-8293-a4b5c6d7e8f9/items", 201, "88ms", 400),
    line("16T00:00:03", "GET", "/v2/search", 200, "275ms", 1610612736),
    line("16T00:00:04", "GET", "/v2/catalog/items/2002", 502, "2s", 0),
    "not a record",
    line("16T00:00:05", "GET", "/v2/catalog/items/2003", 200, "12ms", 2048),
    "",
])

# Many requests on one route, so the three percentiles differ (nearest rank over 37 values).
PERCENTILES = "\n".join(
    line(f"17T01:{i // 60:02d}:{i % 60:02d}", "GET", f"/v2/orders/{9000 + i}", 200 if i % 9 else 500,
         f"{(i * 37) % 101 + 1}.{i % 10}ms", i * 100)
    for i in range(37)
) + "\n" + "\n".join(
    line(f"17T02:00:{i:02d}", "GET", "/v2/orders", 200, f"{5 + i}ms", 512) for i in range(16)
) + "\n" + line("17T02:00:59", "GET", "/v2/orders", 500, "40ms", 512) + "\n"

CSV_NAMES = "\n".join([
    line("18T10:00:00", "GET", "/tags/red,blue", 200, "5ms", 10),
    line("18T10:00:01", "GET", '"/say/\\"hello\\""', 200, "6ms", 10),
    line("18T10:00:02", "GET", "/plain", 200, "7ms", 10),
    line("18T10:00:03", "GET", "/tags/red,blue", 500, "8ms", 10),
    "",
])

SIZES = "\n".join([
    line("19T00:00:00", "GET", "/b/tiny", 200, "1ms", 1023),
    line("19T00:00:01", "GET", "/b/kib", 200, "1ms", 1024),
    line("19T00:00:02", "GET", "/b/kib-edge", 200, "1ms", 10485247),
    line("19T00:00:03", "GET", "/b/mib-edge", 200, "1ms", 10485248),
    line("19T00:00:04", "GET", "/b/mib", 200, "1ms", 1048575),
    line("19T00:00:05", "GET", "/b/gib", 200, "1ms", 10737418239),
    line("19T00:00:06", "GET", "/b/huge", 200, "1ms", 21990232555520),
    "",
])

CRLF = "\r\n".join([
    "# exported from a Windows box",
    line("20T08:00:00", "GET", "/v2/catalog/items/1", 200, "10ms", 100),
    line("20T08:00:01", "GET", "/v2/catalog/items/2", 200, "20ms", 100),
    "garbage",
    line("20T08:00:02", "POST", "/v2/cart/5/items", 500, "1s", 0),
    "",
])

ALL_BAD = "\n".join(["nope", "ts=2026-09-15T00:00:00Z", "a=b c=d", ""])

STDIN_LOG = "\n".join([
    line("21T12:00:00", "GET", "/api/ping", 200, "1ms", 4),
    line("21T12:00:01", "GET", "/api/ping", 200, "3ms", 4),
    line("21T12:00:02", "HEAD", "/api/ping", 200, "2ms"),
    "",
])

CLEAN = "\n".join([
    line("22T00:00:00", "GET", "/a", 200, "1ms", 1),
    line("22T00:00:01", "GET", "/a/1", 404, "2ms", 1),
    "",
])

UTF8 = line("23T00:00:00", "GET", "/café/menu", 200, "3ms", 5) + "\n" + \
    line("23T00:00:01", "GET", "/straße", 200, "4ms", 5) + "\n" + \
    line("23T00:00:02", "GET", "/plain", 200, "5ms", 5) + "\n"

INVALID_UTF8 = (line("24T00:00:00", "GET", "/bad", 200, "3ms", 5).replace("/bad", "/b\udcffd") + "\n" +
                line("24T00:00:01", "GET", "/bad", 200, "3ms", 5) + "\n").encode("utf-8", "surrogateescape")

LONE_CR = (line("25T00:00:00", "GET", "/one", 200, "3ms", 5) + "\r" +
           line("25T00:00:01", "GET", "/two", 200, "4ms", 5) + "\n")

F = {"a.log": PROXY_A}
AB = {"a.log": PROXY_A, "b.log": PROXY_B}

# (name, required, args, files, stdin)
CASES = [
    ("route_table", True, ["a.log"], F, None),
    ("path_by_p95", True, ["--by", "path", "--sort", "p95", "a.log"], F, None),
    ("status_csv_two_files", True, ["--by", "status", "--format", "csv", "a.log", "b.log"], AB, None),
    ("method_by_errors", True, ["--by", "method", "--sort", "errors", "a.log", "b.log"], AB, None),
    ("name_top4", True, ["--sort", "name", "--top", "4", "a.log"], F, None),
    ("top0_all", True, ["--top", "0", "--sort", "name", "b.log"], AB, None),
    ("min_count3", True, ["--min-count", "3", "a.log", "b.log"], AB, None),
    ("since_date_only", True, ["--since", "2026-09-16", "a.log", "b.log"], AB, None),
    ("until_date_only", True, ["--until", "2026-09-16", "--by", "path", "b.log"], AB, None),
    ("window_exact_bounds", True, ["--since", "2026-09-15T00:00:05Z", "--until", "2026-09-15T00:00:09Z",
                                   "--by", "path", "a.log"], F, None),
    ("percentiles", True, ["--sort", "p95", "pct.log"], {"pct.log": PERCENTILES}, None),
    ("percentiles_csv", True, ["--format", "csv", "--by", "path", "pct.log"], {"pct.log": PERCENTILES}, None),
    ("csv_quoting", True, ["--by", "path", "--format", "csv", "--sort", "name", "names.log"], {"names.log": CSV_NAMES}, None),
    ("table_quoting", True, ["--by", "path", "names.log"], {"names.log": CSV_NAMES}, None),
    ("byte_units", True, ["--by", "path", "--sort", "name", "sizes.log"], {"sizes.log": SIZES}, None),
    ("crlf", True, ["crlf.log"], {"crlf.log": CRLF}, None),
    ("all_malformed", True, ["bad.log"], {"bad.log": ALL_BAD}, None),
    ("stdin_default", True, ["--by", "method"], {}, STDIN_LOG),
    ("stdin_dash_between_files", True, ["--by", "path", "b.log", "-", "a.log"], AB, STDIN_LOG),
    ("empty_input", True, [], {}, "# nothing\n\n"),
    ("strict_clean", True, ["--strict", "--by", "status", "clean.log"], {"clean.log": CLEAN}, None),
    ("strict_stops", True, ["--strict", "clean.log", "a.log"], {"a.log": PROXY_A, "clean.log": CLEAN}, None),
    ("strict_stdin", True, ["--strict"], {}, STDIN_LOG + "broken line\n"),
    ("missing_file", True, ["a.log", "missing.log"], F, None),
    ("bad_choice", True, ["--by", "host", "a.log"], F, None),
    ("bad_since", True, ["--since", "2026-02-30T00:00:00", "a.log"], F, None),
    ("bad_min_count", True, ["--min-count", "0", "a.log"], F, None),
    ("unknown_option", True, ["--verbose", "a.log"], F, None),
    # Measures: Python I/O and argparse details a careful port may still miss.
    ("m_options_after_files", False, ["a.log", "--by", "status"], F, None),
    ("m_equals_form", False, ["--format=csv", "--by=method", "a.log"], F, None),
    ("m_version", False, ["--version"], {}, None),
    ("m_non_ascii_widths", False, ["--by", "path", "utf8.log"], {"utf8.log": UTF8}, None),
    ("m_invalid_utf8", False, ["--by", "path", "inv.log"], {"inv.log": INVALID_UTF8}, None),
    ("m_lone_cr_file", False, ["--by", "path", "cr.log"], {"cr.log": LONE_CR}, None),
    ("m_lone_cr_stdin", False, ["--by", "path"], {}, LONE_CR),
]


def run_reference(args, files, stdin):
    with tempfile.TemporaryDirectory() as tmp:
        for name, content in files.items():
            data = content if isinstance(content, bytes) else content.encode()
            (Path(tmp) / name).write_bytes(data)
        env = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "PYTHONPATH": str(FIXTURE), "PYTHONDONTWRITEBYTECODE": "1"}
        r = subprocess.run([sys.executable, "-m", "reqstat", *args], cwd=tmp, env=env, capture_output=True,
                           input=(stdin or "").encode())
    return r.returncode, r.stdout, r.stderr.decode(errors="replace")


def stderr_expectation(rc, stderr):
    if rc == 0:
        return None
    if rc == 2:
        return None  # usage errors: argparse wording is not compared
    first = stderr.strip().splitlines()[0]
    if ": cannot read " in first:
        return "cannot read"
    return first.split(": ", 2)[1] + ":"  # "a.log:12:" for --strict


def encode_files(files):
    out = {}
    for name, content in files.items():
        data = content if isinstance(content, bytes) else content.encode()
        out[name] = base64.b64encode(data).decode()
    return out


def main():
    cases = []
    for name, required, args, files, stdin in CASES:
        rc, stdout, stderr = run_reference(args, files, stdin)
        cases.append({"name": name, "required": required, "args": args, "files_b64": encode_files(files),
                      "stdin_b64": base64.b64encode((stdin or "").encode()).decode(), "rc": rc,
                      "stdout_b64": base64.b64encode(stdout).decode(), "stderr_has": stderr_expectation(rc, stderr)})
    (HERE / "cases.json").write_text(json.dumps({"program": "reqstat", "cases": cases}, indent=1) + "\n")
    print(f"{len(cases)} cases written to {HERE / 'cases.json'}")


if __name__ == "__main__":
    os.chdir(HERE)
    main()
