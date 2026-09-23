#!/usr/bin/env python3
"""Generate the deterministic external visual-library maintainer corpus."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PROJECT = ROOT / "plugins/agentic-design-and-evaluation"
VISUALS = PROJECT / "skills/split-testing/assets/visuals"
FIXTURES = HERE / "mermaid-fixtures"
DEFAULT_OUTPUT = PROJECT / ".local/visual-tests"
MARKER_NAME = ".agentic-visual-corpus.json"
MARKER = {"kind": "agentic-visual-maintainer-corpus", "version": 1}
VENDOR_SHA256 = json.loads((VISUALS / "vendor/mermaid/integrity.json").read_text())["artifactSha256"]
REPORT_TITLES = {
    "field-study": "Fictional field study · complete example",
    "compact": "Fictional observations · compact example",
    "embedded": "Independent reports · embedded examples",
    "stress": "Long records and dense evidence · stress example",
    "snippets": "Independent visual surfaces · examples",
    "mermaid-gallery": "Mermaid · complete family gallery",
    "mermaid-layouts": "Mermaid · layouts and explicit diagnostics",
    "mixed-components": "Mixed evidence · diagrams, measurements and records",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command: list[str], *, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True)
    if result.returncode:
        sys.stderr.write(result.stdout)
        sys.stderr.write(result.stderr)
        raise RuntimeError(f"command failed ({result.returncode}): {' '.join(command[:3])}")
    return result


def file_record(path: Path, base: Path = ROOT) -> dict[str, object]:
    text = path.read_text(encoding="utf-8") if path.suffix in {".ts", ".py", ".cjs", ".mmd", ".md", ".json", ".html"} else None
    try:
        relative = str(path.relative_to(base))
    except ValueError:
        relative = str(path)
    record: dict[str, object] = {"path": relative, "bytes": path.stat().st_size, "sha256": digest(path)}
    if text is not None:
        record["lines"] = len(text.splitlines())
        record["chars"] = len(text)
    return record


def relative_relation(path: Path, other: Path) -> bool:
    try:
        path.relative_to(other)
        return True
    except ValueError:
        return False


def validate_output_path(output: Path, extra_inputs: list[Path]) -> None:
    inputs = [HERE, FIXTURES, VISUALS, VISUALS / "examples", *extra_inputs]
    for source in inputs:
        source = source.resolve()
        if output == source or relative_relation(output, source) or relative_relation(source, output):
            raise ValueError(f"output must not contain or be contained by source/input path: {source}")
    if output == ROOT or output == PROJECT:
        raise ValueError("output must be a dedicated generated directory")


def marker_ok(output: Path) -> bool:
    marker = output / MARKER_NAME
    if not marker.is_file():
        return False
    try:
        return json.loads(marker.read_text(encoding="utf-8")) == MARKER
    except Exception:
        return False


def validate_existing_output(output: Path, replace: bool) -> None:
    if not output.exists():
        return
    if not output.is_dir() or output.is_symlink():
        raise ValueError(f"output is not a regular directory: {output}")
    entries = list(output.iterdir())
    if not entries:
        if not replace:
            raise ValueError(f"output already exists: {output}; pass --replace")
        return
    if not replace:
        raise ValueError(f"output exists and is not empty: {output}; pass --replace")
    if not marker_ok(output):
        raise ValueError(f"refusing to replace unmanaged output: {output}")


def inventory(output: Path, body_root: Path, report_root: Path, prior_preview_dir: Path | None) -> dict[str, object]:
    fixture_index = json.loads((FIXTURES / "index.json").read_text(encoding="utf-8"))
    fixtures = []
    for item in fixture_index:
        source = FIXTURES / item["file"]
        fixtures.append({**item, **{key: value for key, value in file_record(source).items() if key != "path"}})

    prior_previews = []
    if prior_preview_dir is not None:
        for name in ["compact.html", "diagrams.html", "embedded.html", "field-study.html", "stress.html"]:
            path = prior_preview_dir / name
            prior_previews.append({
                "name": name,
                "present": path.is_file(),
                **(file_record(path) if path.is_file() else {}),
            })

    examples = [file_record(path) for path in sorted((VISUALS / "examples").glob("*")) if path.is_file()]
    return {
        "maintainedExamples": examples,
        "priorMainPreviews": prior_previews,
        "priorUnassembledSnippet": file_record(VISUALS / "examples/snippets.ts"),
        "mermaidFixtures": fixtures,
        "generatedBodies": [file_record(path, output) for path in sorted(body_root.glob("*.html"))],
        "generatedFixtureBodies": [file_record(path, output) for path in sorted((body_root / "fixtures").glob("*.html"))],
        "generatedReports": [file_record(path, output) for path in sorted(report_root.glob("*.html"))],
    }


def generate(staging: Path, args: argparse.Namespace, prior_preview_dir: Path | None) -> None:
    body_root = staging / "bodies"
    report_root = staging / "reports"
    work = staging / "_work"
    compiled = work / "compiled"
    body_root.mkdir(parents=True)
    report_root.mkdir(parents=True)
    compiled.mkdir(parents=True)

    compile_inputs = [
        VISUALS / "examples/demo.ts",
        VISUALS / "examples/reader-cases.ts",
        VISUALS / "examples/snippets.ts",
    ]
    run([
        "tsc", "--strict", "--target", "ES2020", "--lib", "ES2020,DOM",
        "--module", "commonjs", "--outDir", str(compiled),
        *map(str, compile_inputs),
    ])
    rendered = run([
        "node", str(HERE / "render_corpus.cjs"), str(compiled), str(FIXTURES), str(body_root)
    ])
    render_summary = json.loads(rendered.stdout)

    enhancer = work / "enhance.js"
    enhancer.write_text(
        "for (const report of document.querySelectorAll('.av-workspace,.av-surface')) if (!report.parentElement?.closest('.av-workspace,.av-surface')) AgenticVisuals.enhanceVisuals(report);\n",
        encoding="utf-8",
        newline="\n",
    )

    if not args.bodies_only:
        for body in sorted(body_root.glob("*.html")):
            name = body.stem
            if name not in REPORT_TITLES:
                continue
            destination = report_root / body.name
            run([
                sys.executable, str(VISUALS / "assemble.py"),
                "--body", str(body),
                "--style", str(VISUALS / "styles/agentic-visuals.css"),
                "--script", str(VISUALS / "dist/agentic-visuals.js"),
                "--script", str(enhancer),
                "--title", REPORT_TITLES[name],
                "--output", str(destination),
            ])

    records = inventory(staging, body_root, report_root, prior_preview_dir)
    (staging / "inventory.json").write_text(
        json.dumps(records, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    manifest = {
        "schemaVersion": 1,
        "vendor": {"version": "12.0.0", "sha256": digest(VISUALS / "vendor/mermaid/mermaid.min.js")},
        "runtime": {
            "bundleSha256": digest(VISUALS / "dist/agentic-visuals.js"),
            "styleSha256": digest(VISUALS / "styles/agentic-visuals.css"),
            "startupSha256": digest(VISUALS / "dist/agentic-startup.js"),
        },
        "fixtureIndexSha256": digest(FIXTURES / "index.json"),
        "registeredFamilies": render_summary["registeredFamilies"],
        "specialFixtures": render_summary["specialFixtures"],
        "bodies": {path.name: digest(path) for path in sorted(body_root.glob("*.html"))},
        "reports": {path.name: digest(path) for path in sorted(report_root.glob("*.html"))},
    }
    (staging / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    (staging / MARKER_NAME).write_text(
        json.dumps(MARKER, separators=(",", ":")) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    if not args.keep_work:
        shutil.rmtree(work)


def promote(staging: Path, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    if not output.exists():
        os.replace(staging, output)
        return
    if not any(output.iterdir()):
        output.rmdir()
        os.replace(staging, output)
        return
    backup = output.with_name(f".{output.name}.previous-{os.getpid()}")
    if backup.exists():
        raise RuntimeError(f"unexpected backup path already exists: {backup}")
    os.replace(output, backup)
    try:
        os.replace(staging, output)
    except BaseException:
        os.replace(backup, output)
        raise
    shutil.rmtree(backup)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--replace", action="store_true", help="Replace an existing corpus only when it carries this generator's marker.")
    parser.add_argument("--keep-work", action="store_true", help="Keep compiled scratch inputs under the generated output.")
    parser.add_argument("--skip-build-check", action="store_true", help="Skip checking the maintained browser bundle against source.")
    parser.add_argument("--bodies-only", action="store_true", help="Render deterministic body fragments without assembling standalone HTML.")
    parser.add_argument("--prior-preview-dir", type=Path, help="Optional historical preview directory to inventory; never read by default.")
    args = parser.parse_args()

    # Resolve only after rejecting symlinks, including an intermediate symlink to
    # a different managed output. --replace owns this directory, not its target.
    requested = Path(os.path.abspath(args.output))
    if any(path.is_symlink() for path in [requested, *requested.parents]):
        print(f"error: output must not traverse a symlink: {requested}", file=sys.stderr)
        return 2
    output = requested.resolve()
    prior_preview_dir = args.prior_preview_dir.resolve() if args.prior_preview_dir else None
    try:
        validate_output_path(output, [prior_preview_dir] if prior_preview_dir else [])
        validate_existing_output(output, args.replace)
        vendor = VISUALS / "vendor/mermaid/mermaid.min.js"
        if digest(vendor) != VENDOR_SHA256:
            raise ValueError("pinned Mermaid vendor digest changed")
        if not args.skip_build_check:
            run(["node", str(VISUALS / "build.mjs"), "--check"])
    except (ValueError, RuntimeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}.tmp-", dir=output.parent))
    try:
        generate(staging, args, prior_preview_dir)
        promote(staging, output)
    except BaseException as error:
        if staging.exists():
            shutil.rmtree(staging)
        if isinstance(error, KeyboardInterrupt):
            raise
        print(f"error: {error}", file=sys.stderr)
        return 2

    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    inventory_data = json.loads((output / "inventory.json").read_text(encoding="utf-8"))
    print(
        f"generated {len(manifest['bodies'])} bodies, "
        f"{len(inventory_data['generatedFixtureBodies'])} fixture bodies and "
        f"{len(manifest['reports'])} assembled reports"
    )
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
