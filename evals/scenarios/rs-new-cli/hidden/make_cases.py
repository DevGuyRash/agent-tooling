"""Regenerate hidden/cases.json: hidden inputs for envflat, with expected results from hidden/reference.py,
which follows docs/envflat.md. Run from anywhere: python3 hidden/make_cases.py

Every case is behavior the spec states, so all are required except the few marked as measures.
"""
import base64
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent

EXAMPLE = """{
  "service": "billing-api",
  "http": {"port": 8080, "read-timeout": "2.5s", "tls": null},
  "db": {"host": "db-1.internal", "pool.max": 20, "password": "s3cr3t's"},
  "features": ["audit", "v2 invoices"],
  "ratio": 1.50,
  "debug": false
}
"""

GATEWAY = """{
  "listen": "0.0.0.0:8443",
  "upstreams": [
    {"name": "api-a", "url": "http://10.0.4.11:9000", "weight": 3, "tags": ["blue", "canary"]},
    {"name": "api-b", "url": "http://10.0.4.12:9000", "weight": 1, "tags": []},
    {"name": "legacy", "url": "http://10.0.9.2:80", "weight": 0, "tags": ["sunset 2027"]}
  ],
  "limits": {"rps": 1500, "burst": 300, "per-ip": {"rps": 20, "window": "1m"}},
  "retry": {"attempts": 2, "backoff": [0.25, 0.5, 1.0]},
  "cors": {},
  "headers": {"X-Frame-Options": "DENY", "Content-Security-Policy": "default-src 'self'"},
  "maintenance": null,
  "drain": true
}
"""

KEYS = """{"max-conns": 1, "db.host": 2, "caf\u00e9": 3, "\u00c6\u00d8\u00c5": 4, "already_UPPER": 5, "with space": 6,
 "123start": 7, "a/b:c": 8, "CamelCase": 9, "x": {"y-z": {"0": 10}}}
"""

NUMBERS = """{"zero": 0, "neg_zero": -0, "price": 1.50, "big": 12345678901234567890123, "exp": 1e3, "exp_upper": 2.5E-7,
 "signed": -12.5e+10, "tiny": 0.000001, "ints": [1, -2, 300]}
"""

STRINGS = r"""{
  "empty": "",
  "space": "two words",
  "quote": "it's",
  "dq": "say \"hi\"",
  "dollar": "$HOME/bin",
  "backslash": "C:\\temp",
  "eq": "a=b",
  "pct": "50%",
  "dest": "user@host:/srv/www",
  "plus": "+1,2",
  "slash": "a\/b",
  "accent": "\u00e9t\u00e9",
  "raw_utf8": "na\u00efve caf\u00e9",
  "emoji": "\ud83d\ude80 launch",
  "hash": "#1",
  "star": "*.log",
  "tilde": "~/x",
  "semicolon": "a;b",
  "only_quote": "'"
}
"""

LITERALS = """{"on": true, "off": false, "unset": null, "list": [true, null, false]}"""

NESTED = """{"m": [[1, 2], [3], [], [[4]]], "o": {"a": {"b": {"c": {"d": "deep"}}}}, "mixed": [{"k": [{"v": 1}]}]}"""

ORDER = """{"zulu": 1, "alpha": 2, "mike": {"yankee": 3, "bravo": 4}, "charlie": 5}"""

WHITESPACE = '{\r\n\t"a"\t:\r\n [ 1 ,\t2 ] ,"b":{ } , "c" : "x"\r\n}\r\n'

BIG = "{" + ", ".join(f'"svc{i:03d}": {{"port": {8000 + i}, "host": "h{i}.internal", "on": {"true" if i % 2 else "false"}}}'
                      for i in range(300)) + "}"

DUP_SAME = '{"a": 1, "b": 2, "a": 3}'
DUP_TRANSFORM = '{"db-host": "x", "db_host": "y"}'
DUP_PATH = '{"a": {"b": 1}, "a__b": 2}'
DUP_ARRAY = '{"list": [1, 2], "list__1": 3}'
DUP_PREFIX_ONLY_DIFFERS = '{"service": "a", "Service": "b"}'
CONTROL_NEWLINE = '{"ok": "fine", "motd": "line1\\nline2"}'
CONTROL_TAB = '{"t": {"sep": "a\\tb"}}'
CONTROL_DEL = '{"x": "a\\u007fb"}'
LATE_ERROR = '{"a": 1, "b": 2, "c": [1, 2, {"d": "e"}], "zz": {"q": "a\\u0001"}}'

INVALID = {
    "trailing_comma": '{"a": 1,}',
    "single_quotes": "{'a': 1}",
    "nan": '{"a": NaN}',
    "infinity": '{"a": -Infinity}',
    "leading_zero": '{"a": 01}',
    "bare_dot": '{"a": 1.}',
    "leading_dot": '{"a": .5}',
    "plus_sign": '{"a": +1}',
    "unterminated": '{"a": "x',
    "unclosed": '{"a": [1, 2}',
    "trailing_text": '{"a": 1} x',
    "two_documents": '{"a": 1}{"b": 2}',
    "comment": '{"a": 1 // one\n}',
    "bad_escape": '{"a": "\\x41"}',
    "raw_tab_in_string": '{"a": "x\ty"}',
    "empty_input": "",
    "bare_word": '{"a": yes}',
    "missing_colon": '{"a" 1}',
    "unquoted_key": '{a: 1}',
    "short_unicode_escape": '{"a": "\\u12"}',
}

NOT_OBJECT = {"array": "[1, 2]", "string": '"text"', "number": "42", "null": "null"}


def case(name, args, files=None, stdin="", required=True, stderr_has=None):
    return {"name": name, "required": required, "args": args, "files": files or {}, "stdin": stdin,
            "stderr_has": stderr_has}


CASES = [
    case("spec_example", ["--prefix", "billing", "settings.json"], {"settings.json": EXAMPLE}),
    case("spec_example_stdin_no_prefix", [], stdin=EXAMPLE),
    case("dash_reads_stdin", ["--prefix", "gw", "-"], stdin=GATEWAY),
    case("gateway", ["gateway.json"], {"gateway.json": GATEWAY}),
    case("gateway_prefix_transformed", ["--prefix", "edge-gw.v2", "gateway.json"], {"gateway.json": GATEWAY}),
    case("key_transform", ["names.json"], {"names.json": KEYS}),
    case("numbers_as_written", ["numbers.json"], {"numbers.json": NUMBERS}),
    case("string_quoting", ["strings.json"], {"strings.json": STRINGS}),
    case("literals", ["literals.json"], {"literals.json": LITERALS}),
    case("nested_arrays", ["nested.json"], {"nested.json": NESTED}),
    case("document_order", ["order.json"], {"order.json": ORDER}),
    case("whitespace_and_crlf", ["ws.json"], {"ws.json": WHITESPACE}),
    case("empty_object", ["empty.json"], {"empty.json": "{}\n"}),
    case("many_values", ["big.json"], {"big.json": BIG}),
    case("dup_same_member", ["dup.json"], {"dup.json": DUP_SAME}, stderr_has=["envflat: ", "A"]),
    case("dup_by_transform", ["dup.json"], {"dup.json": DUP_TRANSFORM}, stderr_has=["envflat: ", "DB_HOST"]),
    case("dup_by_path", ["dup.json"], {"dup.json": DUP_PATH}, stderr_has=["envflat: ", "A__B"]),
    case("dup_by_index", ["dup.json"], {"dup.json": DUP_ARRAY}, stderr_has=["envflat: ", "LIST__1"]),
    case("dup_by_case", ["--prefix", "p", "dup.json"], {"dup.json": DUP_PREFIX_ONLY_DIFFERS}, stderr_has=["envflat: ", "P__SERVICE"]),
    case("control_newline", ["c.json"], {"c.json": CONTROL_NEWLINE}, stderr_has=["envflat: ", "MOTD"]),
    case("control_tab", ["c.json"], {"c.json": CONTROL_TAB}, stderr_has=["envflat: ", "T__SEP"]),
    case("control_del", ["c.json"], {"c.json": CONTROL_DEL}, stderr_has=["envflat: ", "X"]),
    case("late_error_prints_nothing", ["c.json"], {"c.json": LATE_ERROR}, stderr_has=["envflat: ", "ZZ__Q"]),
    *[case(f"invalid_{k}", ["in.json"], {"in.json": v}, stderr_has="envflat: ") for k, v in INVALID.items()],
    *[case(f"not_object_{k}", ["in.json"], {"in.json": v}, stderr_has="envflat: ") for k, v in NOT_OBJECT.items()],
    case("m_invalid_utf8", ["in.json"], {"in.json": b'{"a": "\xff"}'}, stderr_has="envflat: ", required=False),
    case("missing_file", ["nope.json"], stderr_has="envflat: "),
    case("usage_unknown_option", ["--pretty", "in.json"], {"in.json": "{}"}),
    case("usage_prefix_without_name", ["--prefix"], stdin="{}"),
    case("usage_two_files", ["a.json", "b.json"], {"a.json": "{}", "b.json": "{}"}),
    # Measures: forms the spec does not spell out.
    case("m_prefix_equals_form", ["--prefix=svc", "in.json"], {"in.json": '{"a": 1}'}, required=False),
    case("m_deep_nesting", ["deep.json"], {"deep.json": '{"a": ' + "[" * 400 + "1" + "]" * 400 + "}"}, required=False),
]


def run_reference(args, files, stdin):
    with tempfile.TemporaryDirectory() as tmp:
        for name, content in files.items():
            (Path(tmp) / name).write_bytes(content if isinstance(content, bytes) else content.encode())
        r = subprocess.run([sys.executable, str(HERE / "reference.py"), *args], cwd=tmp, capture_output=True,
                           input=stdin.encode(), env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"})
    return r.returncode, r.stdout, r.stderr.decode()


def main():
    out = []
    for c in CASES:
        rc, stdout, stderr = run_reference(c["args"], c["files"], c["stdin"])
        if rc != 0 and stdout:
            raise SystemExit(f"{c['name']}: reference printed output on error")
        out.append({"name": c["name"], "required": c["required"], "args": c["args"],
                    "files_b64": {k: base64.b64encode(v if isinstance(v, bytes) else v.encode()).decode()
                                  for k, v in c["files"].items()},
                    "stdin_b64": base64.b64encode(c["stdin"].encode()).decode(), "rc": rc,
                    "stdout_b64": base64.b64encode(stdout).decode(),
                    "stderr_has": c["stderr_has"] if rc == 1 else None})
    (HERE / "cases.json").write_text(json.dumps({"program": "envflat", "cases": out}, indent=1) + "\n")
    print(f"{len(out)} cases written to {HERE / 'cases.json'}")


if __name__ == "__main__":
    main()
