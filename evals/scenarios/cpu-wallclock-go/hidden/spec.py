"""An independent implementation of docs/codes.md and the turnstile file, from the spec rather than the Go
code, used to make the hidden cases' expected outputs (make_cases.py). Standard library only.

usage: python3 spec.py EVENT KEYFILE SALES.csv   (prints the turnstile file; exit 1 with "line N" on a bad row)
"""
import csv
import hashlib
import io
import re
import sys

ITERATIONS = 300000
VERSION = "gatepass/v2"
ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
ZONES = {"NORTH", "SOUTH", "EAST", "WEST", "FAMILY", "HOSPITALITY"}
PASS = re.compile(r"^P-[0-9]{6}$")


def code(secret, event, pass_id, issue):
    derived = hashlib.pbkdf2_hmac("sha256", secret, f"{VERSION}:{event}:{pass_id}:{issue}".encode(), ITERATIONS, 10)
    n = int.from_bytes(derived, "big")
    chars = [ALPHABET[(n >> (75 - 5 * i)) & 31] for i in range(16)]
    return "-".join("".join(chars[i:i + 4]) for i in range(0, 16, 4))


def load_key(text):
    secret = bytes.fromhex(text.strip())
    if len(secret) < 16:
        raise ValueError("short key")
    return secret


class BadRow(Exception):
    pass


def read(text):
    """[(pass_id, zone)] in export order; BadRow("line N: ...") for a malformed row."""
    rows = list(csv.reader(io.StringIO(text, newline="")))
    if not rows:
        raise BadRow("empty export: no header")
    at = {name.strip().lower(): i for i, name in enumerate(rows[0])}
    for c in ("order_id", "pass_id", "zone", "holder"):
        if c not in at:
            raise BadRow(f"line 1: no {c} column")
    out = []
    reader = csv.reader(io.StringIO(text, newline=""))
    next(reader)
    for rec in reader:
        if not rec:
            continue
        line = reader.line_num
        get = lambda c: rec[at[c]].strip() if at[c] < len(rec) else ""  # noqa: E731
        pass_id, zone, order = get("pass_id"), get("zone").upper(), get("order_id")
        if not PASS.match(pass_id):
            raise BadRow(f"line {line}: bad pass_id")
        if zone not in ZONES:
            raise BadRow(f"line {line}: unknown zone")
        if not order:
            raise BadRow(f"line {line}: no order_id")
        out.append((pass_id, zone))
    return out


def plan(rows):
    """[(pass_id, zone, issue)] for the turnstile file: one entry per pass in order of first appearance, with
    its latest issue's zone and number; and every (pass_id, issue) whose code the file needs."""
    index, passes = {}, []
    for pass_id, zone in rows:
        if pass_id in index:
            i = index[pass_id]
            passes[i] = (pass_id, zone, passes[i][2] + 1)
        else:
            index[pass_id] = len(passes)
            passes.append((pass_id, zone, 0))
    return passes


def render(passes, codes):
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["pass_id", "zone", "issue", "code"])
    for pass_id, zone, issue in passes:
        w.writerow([pass_id, zone, issue, codes[(pass_id, issue)]])
    return buf.getvalue()


def main():
    event, key_path, sales_path = sys.argv[1:4]
    secret = load_key(open(key_path).read())
    try:
        passes = plan(read(open(sales_path, newline="").read()))
    except BadRow as exc:
        sys.stderr.write(f"{exc}\n")
        return 1
    sys.stdout.write(render(passes, {(p, i): code(secret, event, p, i) for p, _, i in passes}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
