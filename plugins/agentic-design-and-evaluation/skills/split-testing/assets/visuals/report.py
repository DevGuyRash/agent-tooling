#!/usr/bin/env python3
"""Write one self-contained HTML report from trial data, a report specification, or both.

  report.py --trial REPORT.json [--narrative NARRATIVE.json] --output report.html
  report.py --spec SPEC.json [--trial REPORT.json] --output report.html

REPORT.json is what `trial.py report RUN_DIR` writes. NARRATIVE.json adds the
decision, labels and extra sections to the default trial composition; SPEC.json
is a complete report specification instead (see catalog.md). The library renders
the report in the reader's browser from the embedded data, so this needs only
Python: no Node.js, no network, no build step.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tempfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import assemble  # noqa: E402  (the sibling offline packager)

BODY = (
    '<div class="av-mount" data-av-mount aria-busy="true">'
    '<noscript><p style="font:16px/1.5 system-ui;max-width:40rem;margin:4rem auto;padding:0 1rem">'
    "This report draws its views from embedded data with JavaScript. Enable JavaScript "
    "for this file, or read the JSON blocks inside it directly.</p></noscript></div>\n"
)


def uses_diagrams(value) -> bool:
    if isinstance(value, dict):
        return value.get("type") == "diagram" or any(uses_diagrams(v) for v in value.values())
    if isinstance(value, list):
        return any(uses_diagrams(v) for v in value)
    return False


def load(path: Path, label: str):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise assemble.PackagingError(f"{label} file not found: {path}") from None
    except json.JSONDecodeError as error:
        raise assemble.PackagingError(f"{label} is not valid JSON: {path}: {error.msg} at line {error.lineno}") from None


def main() -> int:
    summary, _, usage = (__doc__ or "").partition("\n\n")
    parser = argparse.ArgumentParser(description=summary, formatter_class=argparse.RawDescriptionHelpFormatter, epilog=usage)
    parser.add_argument("--trial", type=Path, help="JSON from `trial.py report RUN_DIR`")
    parser.add_argument("--narrative", type=Path, help="decision, labels and extra sections for the trial composition")
    parser.add_argument("--spec", type=Path, help="a complete report specification (replaces the trial composition)")
    parser.add_argument("--output", required=True, type=Path, help="standalone HTML file to write")
    parser.add_argument("--title", help="document title (default: the report's own title)")
    parser.add_argument("--replace", action="store_true", help="replace a differing existing output")
    args = parser.parse_args()
    try:
        if args.narrative and not args.trial:
            raise assemble.PackagingError("--narrative needs --trial")
        if not args.trial and not args.spec:
            raise assemble.PackagingError("supply --trial, --spec, or both")
        if args.narrative and args.spec:
            raise assemble.PackagingError("--narrative shapes the trial composition; a --spec replaces it, so pass one or the other")
        data, title = [], args.title
        diagrams = False
        if args.trial:
            trial = load(args.trial, "--trial")
            if not isinstance(trial, dict) or not isinstance(trial.get("runs"), list):
                raise assemble.PackagingError(f"{args.trial} is not trial report data; write it with `trial.py report RUN_DIR --out FILE`")
            data.append(f"av-trial={args.trial}")
            title = title or trial.get("name")
        if args.narrative:
            narrative = load(args.narrative, "--narrative")
            diagrams |= uses_diagrams(narrative)
            data.append(f"av-narrative={args.narrative}")
            title = args.title or narrative.get("title") or narrative.get("question") or title
        if args.spec:
            spec = load(args.spec, "--spec")
            if not isinstance(spec, dict) or not isinstance(spec.get("sections"), list) or not isinstance(spec.get("title"), str):
                raise assemble.PackagingError(f"{args.spec} needs a string \"title\" and a \"sections\" list")
            diagrams |= uses_diagrams(spec)
            data.append(f"av-spec={args.spec}")
            title = args.title or spec["title"]
        with tempfile.TemporaryDirectory(prefix="av-report-") as scratch:
            body = Path(scratch) / "body.html"
            body.write_text(BODY, encoding="utf-8")
            namespace = argparse.Namespace(
                body=body, output=args.output, title=title or "Trial report", lang="en",
                style=[HERE / "styles/agentic-visuals.css"], script=[HERE / "dist/agentic-visuals.js"],
                data=data, asset=[], feature=["mermaid"] if diagrams else [], replace=args.replace,
            )
            content = assemble.assemble(namespace)
            action = assemble.write_output(args.output, content, args.replace)
    except (assemble.PackagingError, OSError, UnicodeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        print("hint: correct the named input or output and rerun; nothing is downloaded", file=sys.stderr)
        return 1
    print(f"{action} {args.output} ({args.output.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
