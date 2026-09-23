#!/usr/bin/env python3
"""External maintainer tests for the deterministic visual-library corpus."""
from __future__ import annotations

from html.parser import HTMLParser
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PROJECT = ROOT / "plugins/agentic-design-and-evaluation"
FIXTURES = HERE / "mermaid-fixtures"
DEFAULT_OUTPUT = PROJECT / ".local/visual-tests"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class FixtureParser(HTMLParser):
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
    def __init__(self):
        super().__init__()
        self.stack: list[tuple[str, dict[str, str] | None]] = []
        self.fixtures: dict[str, dict[str, str]] = {}

    def handle_starttag(self, tag, attrs):
        data = dict(attrs)
        current = self.stack[-1][1] if self.stack else None
        if "data-round2-fixture" in data:
            current = {
                "file": data["data-round2-fixture"],
                "family": data.get("data-round2-family", ""),
                "expected": data.get("data-round2-expected", ""),
            }
            self.fixtures[current["file"]] = current
        if current is not None and "data-av-mermaid-source" in data:
            current["source"] = data["data-av-mermaid-source"]
        if tag not in self.VOID:
            self.stack.append((tag, current))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID:
            self.stack.pop()

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break


class ResourceParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.resources: list[tuple[str, str, str]] = []
        self.json_scripts: dict[str, list[str]] = {}
        self.capture: str | None = None

    def handle_starttag(self, tag, attrs):
        data = dict(attrs)
        for attribute in ("src", "href"):
            if attribute in data and tag in {"script", "link", "img", "source", "video", "audio"}:
                self.resources.append((tag, attribute, data[attribute]))
        if tag == "script" and data.get("type") == "application/json" and data.get("id"):
            self.capture = data["id"]
            self.json_scripts[self.capture] = []

    def handle_endtag(self, tag):
        if tag == "script":
            self.capture = None

    def handle_data(self, data):
        if self.capture:
            self.json_scripts[self.capture].append(data)


class CorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        supplied = os.environ.get("VISUAL_TEST_OUTPUT") or os.environ.get("VISUAL_ROUND2_OUTPUT")
        if supplied:
            cls.output = Path(supplied).resolve()
            if not (cls.output / "manifest.json").is_file():
                raise RuntimeError(f"The supplied corpus has no manifest: {cls.output}")
            return
        scratch = tempfile.TemporaryDirectory(prefix="visual-corpus-tests-")
        cls.addClassCleanup(scratch.cleanup)
        cls.output = Path(scratch.name) / "corpus"
        result = subprocess.run(
            ["python3", str(HERE / "generate.py"), "--output", str(cls.output)],
            cwd=ROOT, capture_output=True, text=True, timeout=90,
        )
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)

    def test_registry_and_detector_contract(self):
        result = subprocess.run(
            ["node", str(HERE / "verify_registry.cjs")],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        index = json.loads((FIXTURES / "index.json").read_text(encoding="utf-8"))
        self.assertEqual(set(payload["actualFamilies"]), {item["family"] for item in index if item["kind"] == "diagram"})
        self.assertEqual(payload["fixtureCount"], len(index))

    def test_inventory_shape_and_expected_states(self):
        index = json.loads((FIXTURES / "index.json").read_text(encoding="utf-8"))
        self.assertEqual(len(index), 55)
        self.assertEqual(len({item["family"] for item in index if item["kind"] == "diagram"}), 37)
        self.assertEqual({item["family"] for item in index if item["kind"] == "error/sentinel"}, {"error", "---"})
        self.assertEqual(sum(item["kind"] == "layout candidate" for item in index), 11)
        self.assertEqual(sum(item["kind"] == "edge/error candidate" for item in index), 4)
        self.assertEqual(sum(item["kind"] == "renderer regression" for item in index), 1)
        self.assertEqual(
            {item["file"] for item in index if item["expectedState"] == "error"},
            {"frontmatter-error.mmd", "layout-cose-bilkent.mmd", "invalid-source.mmd", "block-diamond-routing.mmd"},
        )
        indexed = {item["file"] for item in index}
        on_disk = {path.name for path in FIXTURES.glob("*.mmd")}
        self.assertEqual(indexed, on_disk)

    def test_body_generation_is_deterministic(self):
        with tempfile.TemporaryDirectory(prefix="visual-round2-a-") as first, tempfile.TemporaryDirectory(prefix="visual-round2-b-") as second:
            for output in (first, second):
                result = subprocess.run(
                    [
                        "python3", str(HERE / "generate.py"),
                        "--output", output,
                        "--replace",
                        "--bodies-only",
                        "--skip-build-check",
                    ],
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            first_root, second_root = Path(first) / "bodies", Path(second) / "bodies"
            first_files = sorted(path.relative_to(first_root) for path in first_root.rglob("*.html"))
            second_files = sorted(path.relative_to(second_root) for path in second_root.rglob("*.html"))
            self.assertEqual(first_files, second_files)
            self.assertTrue(first_files)
            for relative in first_files:
                self.assertEqual(sha(first_root / relative), sha(second_root / relative), str(relative))
            inventory = json.loads((Path(first) / "inventory.json").read_text(encoding="utf-8"))
            self.assertEqual(inventory["priorMainPreviews"], [], "maintained generator has no transient preview dependency by default")

    def test_generator_refuses_unmanaged_replace(self):
        with tempfile.TemporaryDirectory(prefix="visual-round2-unmanaged-") as parent:
            output = Path(parent) / "corpus"
            output.mkdir()
            sentinel = output / "keep.txt"
            sentinel.write_text("do not remove\n", encoding="utf-8")
            result = subprocess.run(
                [
                    "python3", str(HERE / "generate.py"),
                    "--output", str(output),
                    "--replace",
                    "--bodies-only",
                    "--skip-build-check",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "do not remove\n")
            self.assertIn("unmanaged output", result.stderr)

    def test_generated_gallery_retains_every_exact_source(self):
        output = self.output
        gallery = output / "bodies/mermaid-gallery.html"
        self.assertTrue(gallery.is_file(), f"Missing generated gallery: {gallery}")
        parser = FixtureParser()
        parser.feed(gallery.read_text(encoding="utf-8"))
        index = json.loads((FIXTURES / "index.json").read_text(encoding="utf-8"))
        self.assertEqual(set(parser.fixtures), {item["file"] for item in index})
        for item in index:
            record = parser.fixtures[item["file"]]
            self.assertEqual(record["family"], item["family"])
            self.assertEqual(record["expected"], item["expectedState"])
            self.assertEqual(record.get("source"), (FIXTURES / item["file"]).read_text(encoding="utf-8"))

    def test_mixed_body_contains_mermaid_and_non_mermaid_components(self):
        output = self.output
        mixed = output / "bodies/mixed-components.html"
        self.assertTrue(mixed.is_file(), f"Missing mixed composition: {mixed}")
        text = mixed.read_text(encoding="utf-8")
        self.assertGreaterEqual(text.count("data-av-mermaid"), 3)
        self.assertIn("data-av-layout-kind=\"paired\"", text)
        self.assertIn("data-av-layout-kind=\"scatter\"", text)
        self.assertIn("data-av-layout-kind=\"lineage\"", text)
        self.assertIn('id="mixed-lineage"', text)
        self.assertIn('alpha-record-1', text)
        self.assertIn('alpha-record-2', text)
        self.assertIn('alpha1-support', text)
        self.assertIn('alpha1-scope', text)
        self.assertIn('END OF RETAINED QUALIFICATION.', text)
        self.assertGreaterEqual(text.count('Repeated sample'), 4)
        self.assertTrue('id="mixed-table"' in text and 'data-av-frame="comparison"' in text,
                        "Mixed report must retain its annotated comparison table")
        self.assertIn("data-av-explorer", text)
        self.assertIn("Condition β · interrupted", text)
        self.assertIn("日本語", text)

    def test_assembled_reports_are_offline_and_retain_recipe(self):
        output = self.output
        report_root = output / "reports"
        reports = sorted(report_root.glob("*.html"))
        self.assertTrue(reports, f"Missing assembled reports: {report_root}")
        self.assertEqual({path.stem for path in reports}, {
            "field-study", "compact", "embedded", "stress", "snippets",
            "mermaid-gallery", "mermaid-layouts", "mixed-components",
        })
        for report in reports:
            parser = ResourceParser()
            parser.feed(report.read_text(encoding="utf-8"))
            for tag, attribute, value in parser.resources:
                self.assertTrue(
                    value.startswith("data:") or value.startswith("#"),
                    f"{report.name}: external resource {tag}[{attribute}]={value}",
                )
            recipe = json.loads("".join(parser.json_scripts["av-report-recipe"]))
            self.assertEqual(recipe["headScripts"], ["av-startup"])
            requires_mermaid = 'data-av-requires="mermaid"' in recipe["body"]
            self.assertEqual(
                recipe["scripts"],
                ["av-script-0", "av-script-1", "av-script-2"] if requires_mermaid else ["av-script-0", "av-script-1"],
            )
            self.assertEqual("av-mermaid-notices" in recipe["data"], requires_mermaid)


if __name__ == "__main__":
    unittest.main()
