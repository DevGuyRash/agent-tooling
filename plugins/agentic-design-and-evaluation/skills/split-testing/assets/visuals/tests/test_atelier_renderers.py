"""Cross-renderer semantic markup and hydration-hook checks, without a browser."""
from html.parser import HTMLParser
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}


class Markup(HTMLParser):
    def __init__(self):
        super().__init__()
        self.nodes = []
        self.stack = []
        self.errors = []

    def handle_starttag(self, tag, attrs):
        node = {"tag": tag, "attrs": dict(attrs), "parent": self.stack[-1] if self.stack else None}
        self.nodes.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.stack.pop()

    def handle_endtag(self, tag):
        if not self.stack or self.stack[-1]["tag"] != tag:
            self.errors.append(f"unbalanced closing tag: {tag}")
        else:
            self.stack.pop()


def owner(node, attribute):
    current = node["parent"]
    while current:
        if attribute in current["attrs"]:
            return current
        current = current["parent"]
    return None


class AtelierRendererTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        node, tsc = shutil.which("node"), shutil.which("tsc")
        if not node or not tsc:
            raise RuntimeError("Renderer checks require installed Node.js and TypeScript; nothing is installed automatically")
        with tempfile.TemporaryDirectory(prefix="atelier-renderers-") as temporary:
            compiled = subprocess.run([tsc, "--strict", "--target", "ES2020", "--module", "commonjs", "--rootDir", str(ROOT), "--outDir", temporary, str(ROOT / "src/index.ts"), str(ROOT / "src/explorers.ts")], capture_output=True, text=True)
            if compiled.returncode:
                raise AssertionError(compiled.stdout + compiled.stderr)
            executed = subprocess.run([node, str(ROOT / "tests/atelier-renderers.cjs"), temporary], capture_output=True, text=True)
            if executed.returncode:
                raise AssertionError(executed.stdout + executed.stderr)
            cls.fixtures = json.loads(executed.stdout)

    def test_all_presentations_share_safe_native_fallbacks(self):
        self.assertEqual(len(self.fixtures), 29)
        for name, html in self.fixtures.items():
            with self.subTest(renderer=name):
                document = Markup()
                document.feed(html)
                self.assertEqual(document.errors, [])
                self.assertEqual(document.stack, [])
                for node in document.nodes:
                    attributes = node["attrs"]
                    if "data-av-controls" in attributes:
                        self.assertIn("hidden", attributes, "unhydrated controls must not promise unavailable behavior")
                    if "data-av-object" in attributes:
                        self.assertEqual(node["tag"], "details", "inspection must retain a native disclosure route")
                    if "data-av-focus" in attributes or "data-av-zoom-in" in attributes:
                        self.assertEqual(node["tag"], "button")
                        self.assertIsNotNone(owner(node, "data-av-controls"))
                    if "data-av-zoom-target" in attributes:
                        self.assertEqual(node["tag"], "svg")
                        self.assertIsNotNone(owner(node, "data-av-plot"))

    def test_composite_frame_identities_survive_actual_assembly(self):
        with tempfile.TemporaryDirectory(prefix="atelier-identity-assembly-") as tmp:
            for name in ("comparisonJourney", "uncertaintyObservatory"):
                with self.subTest(renderer=name):
                    body = Path(tmp) / (name + "-body.html")
                    body.write_text(self.fixtures[name] + '<aside id="evidence">Original source</aside>')
                    output = Path(tmp) / (name + ".html")
                    result = subprocess.run(["python3", str(ROOT / "assemble.py"), "--body", str(body), "--output", str(output)], cwd=tmp, capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    document = Markup()
                    document.feed(output.read_text())
                    ids = [node["attrs"]["id"] for node in document.nodes if "id" in node["attrs"]]
                    self.assertEqual(len(ids), len(set(ids)))
                    self.assertEqual(len([value for value in ids if value != "av-report-recipe"]), 2)

    def test_inspection_and_navigation_hooks_resolve_in_their_actual_scope(self):
        for name, html in self.fixtures.items():
            with self.subTest(renderer=name):
                document = Markup()
                document.feed(html)
                explorers = [node for node in document.nodes if "data-av-explorer" in node["attrs"]]
                for explorer in explorers:
                    scoped = [node for node in document.nodes if owner(node, "data-av-explorer") is explorer]
                    objects = [node["attrs"]["data-av-object"] for node in scoped if "data-av-object" in node["attrs"]]
                    self.assertEqual(len(objects), len(set(objects)), "object keys must be unique in one explorer")
                    for node in scoped:
                        attributes = node["attrs"]
                        for key in ["data-av-inspect", "data-av-compare", "data-av-from", "data-av-to"]:
                            if key in attributes:
                                self.assertIn(attributes[key], objects, f"orphan {key} hook")
                        if node["tag"] == "option" and attributes.get("value"):
                            self.assertIn(attributes["value"], objects, "selector must point to retained objects")
                        if "data-av-step" in attributes:
                            self.assertIn(attributes["data-av-step"], ["-1", "1"])
                            self.assertTrue(objects)


if __name__ == "__main__":
    unittest.main()
