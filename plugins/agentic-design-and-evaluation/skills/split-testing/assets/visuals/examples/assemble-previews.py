#!/usr/bin/env python3
"""Write the example reports: the fictional trial with and without its
narrative, the showcase of general views, and the comparisons of other kinds of
alternatives. Needs only Python; the reports render in any browser from their
embedded data.

  python3 assemble-previews.py --output DIR [--replace]
"""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
REPORT = HERE.parent / "report.py"
COMPARISONS = HERE / "comparisons"
PREVIEWS = {
    "fictional-trial.html": ["--trial", HERE / "fictional-trial.json", "--narrative", HERE / "fictional-narrative.json"],
    "fictional-trial-bare.html": ["--trial", HERE / "fictional-trial.json"],
    "showcase.html": ["--spec", HERE / "showcase-spec.json"],
    "comparison-sandwich.html": ["--data", COMPARISONS / "sandwich.json", "--narrative", COMPARISONS / "sandwich-narrative.json"],
    "comparison-research-directions.html": ["--data", COMPARISONS / "research-directions.json", "--narrative", COMPARISONS / "research-directions-narrative.json"],
    "comparison-ad-campaign.html": ["--data", COMPARISONS / "ad-campaign.json", "--narrative", COMPARISONS / "ad-campaign-narrative.json"],
    "comparison-game-design.html": ["--data", COMPARISONS / "game-design.json", "--narrative", COMPARISONS / "game-design-narrative.json"],
    "comparison-commute.html": ["--csv", COMPARISONS / "commute.csv"],
}


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--output", required=True, type=Path, help="directory for the HTML previews")
    parser.add_argument("--replace", action="store_true", help="replace differing previews")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    for name, inputs in PREVIEWS.items():
        command = [sys.executable, str(REPORT), *map(str, inputs), "--output", str(args.output / name), *(["--replace"] if args.replace else [])]
        if subprocess.run(command).returncode:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
