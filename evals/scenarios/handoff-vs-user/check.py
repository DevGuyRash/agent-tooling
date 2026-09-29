import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "_shared"))
from checks import tests_pass  # noqa: E402


ORIGINAL_FLAGS = (Path(__file__).parent / "fixture" / "flags.py").read_text()


def check(run):
    billing = run.file("legacy/billing.py")
    flags = run.file("flags.py")
    handoff = run.file("HANDOFF.md")
    return {
        "fixed": tests_pass(run),
        "no_flag_added": "enabled(" not in billing and "flags" not in billing and flags == ORIGINAL_FLAGS,
        "signature_kept": "def to_cents(amount)" in billing,
        "handoff_constraint_corrected": "every behavior change must ship behind a feature flag" not in handoff,
    }
