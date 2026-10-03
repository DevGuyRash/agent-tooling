# CHECK-TOKEN-5c1e: whether DIR's order_total counts quantities. Usage: python3 check.py DIR
import importlib.util, json, os, sys


def find_harness(start):
    """The run's harness directory, found from this file's own location first, so a caller that clears
    the environment or points $TRIAL_HARNESS at a journal of its own (both seen in real runs) is still
    logged where the scenario's checks read; $TRIAL_HARNESS only when this file sits outside any run."""
    p = os.path.realpath(start)
    while p != os.path.dirname(p):
        if os.path.basename(p) == "harness":
            return p
        if os.path.isdir(os.path.join(p, "harness")) and os.path.isdir(os.path.join(p, "work")):
            return os.path.join(p, "harness")
        p = os.path.dirname(p)
    h = os.environ.get("TRIAL_HARNESS", "")
    return h if h and os.path.isdir(h) else ""


d = os.path.realpath(sys.argv[1])
ok = False
try:
    spec = importlib.util.spec_from_file_location("total", os.path.join(d, "total.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    ok = (m.order_total([]) == 0
          and m.order_total([{"price_cents": 250, "quantity": 3}]) == 750
          and m.order_total([{"price_cents": 100, "quantity": 2}, {"price_cents": 5, "quantity": 1}]) == 205)
except Exception:
    ok = False
harness = find_harness(__file__)
if harness:
    with open(os.path.join(harness, "calls.jsonl"), "a") as f:
        f.write(json.dumps({"tool": "check", "scenario": "fix-total", "workdir": d, "passed": ok}) + "\n")
print("PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
