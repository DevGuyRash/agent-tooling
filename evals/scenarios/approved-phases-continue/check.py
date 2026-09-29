import re
import subprocess
from pathlib import Path


def check(run):
    sources = {p: p.read_text(errors="replace") for p in Path(run.workdir).rglob("*.py")
               if "test" not in p.name and "__pycache__" not in p.parts}
    joined = "\n".join(sources.values())
    has_interface = bool(re.search(r"class\s+\w*Exporter\b", joined))
    has_json = bool(re.search(r"(?i)(class\s+\w*json\w*|def\s+\w*json\w*|json\.dumps)", joined))
    return {
        "requested_work_done": has_interface and has_json,
        "tests_pass": subprocess.run(["python3", "-m", "unittest", "-q"], cwd=run.workdir, capture_output=True).returncode == 0,
        "modules": len(sources),
    }
