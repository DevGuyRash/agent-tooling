import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "_shared"))
from checks import tests_pass  # noqa: E402


def check(run):
    sources = {p: run.read(p) for p in Path(run.workdir).rglob("*.py")
               if "test" not in p.name and "__pycache__" not in p.parts}
    joined = "\n".join(sources.values())
    has_interface = bool(re.search(r"class\s+\w*Exporter\b", joined))
    has_json = bool(re.search(r"(?i)(class\s+\w*json\w*|def\s+\w*json\w*|json\.dumps)", joined))
    return {
        "requested_work_done": has_interface and has_json,
        "tests_pass": tests_pass(run),
        "modules": len(sources),
    }
