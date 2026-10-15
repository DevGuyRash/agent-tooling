"""Write hidden/text_cases.json: the existing text format's output on the hidden cases, from the fixture's own
stallbook, run here, so the checks hold the agent's tree to what it printed before the change.

    python3 make_cases.py
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXTURE = HERE.parent / "fixture"
sys.path.insert(0, str(HERE))
import oe_stall  # noqa: E402


def main():
    out = []
    for case in oe_stall.text_cases():
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "sales.csv").write_text(case.sales_csv, encoding="utf-8", newline="")
            if case.ini:
                Path(tmp, "stallbook.ini").write_text(case.ini, encoding="utf-8")
            r = subprocess.run([sys.executable, "-B", "-m", "stallbook", "--data", tmp, "report", "--week", case.week],
                               cwd=FIXTURE, capture_output=True, text=True, check=False)
        out.append({"name": case.name, "week": case.week, "sales_csv": case.sales_csv, "ini": case.ini,
                    "status": r.returncode, "stdout": r.stdout})
    (HERE / "text_cases.json").write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {len(out)} cases")


if __name__ == "__main__":
    main()
