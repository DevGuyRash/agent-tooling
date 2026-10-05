"""report.py writes one offline HTML file, embeds the Mermaid vendor only for
diagrams, and refuses bad inputs with an error: and hint: line."""
from __future__ import annotations

import base64
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import unittest
from urllib.parse import unquote_to_bytes

from visual_harness import EXAMPLES, REPORT, VISUALS, Scratch, run_python, write_hostile_fixtures

TRIAL = EXAMPLES / "fictional-trial.json"
NARRATIVE = EXAMPLES / "fictional-narrative.json"
SHOWCASE = EXAMPLES / "showcase-spec.json"
BUNDLE = VISUALS / "dist" / "agentic-visuals.js"
STYLESHEET = VISUALS / "styles" / "agentic-visuals.css"
MERMAID = VISUALS / "vendor" / "mermaid" / "mermaid.min.js"
URL_ATTRIBUTES = {"src", "href", "action", "formaction", "poster", "srcset", "xlink:href", "background", "data", "ping", "manifest"}
EXPECTED_CSP = ("default-src 'none'", "script-src data:", "connect-src 'none'", "object-src 'none'", "frame-src 'none'", "base-uri 'none'", "form-action 'none'")


class Page(HTMLParser):
    """The parts of an assembled report the tests read."""

    def __init__(self, text: str):
        super().__init__(convert_charrefs=True)
        self.metas: list[dict[str, str]] = []
        self.urls: list[tuple[str, str, str]] = []
        self.scripts: list[dict[str, str]] = []
        self.json: dict[str, str] = {}
        self.ids: list[str] = []
        self.mounts = 0
        self.title = ""
        self._json_id: str | None = None
        self._in_title = False
        self.feed(text)
        self.close()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {name: value or "" for name, value in attrs}
        if "id" in values:
            self.ids.append(values["id"])
        if "data-av-mount" in values:
            self.mounts += 1
        if tag == "meta":
            self.metas.append(values)
        if tag == "title":
            self._in_title = True
        for name, value in values.items():
            if name in URL_ATTRIBUTES:
                self.urls.append((tag, name, value))
        if tag == "script":
            if values.get("type") == "application/json":
                self._json_id = values.get("id", "")
                self.json[self._json_id] = ""
            else:
                self.scripts.append(values)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self._json_id = None
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._json_id is not None:
            self.json[self._json_id] += data
        elif self._in_title:
            self.title += data


def data_url_bytes(url: str) -> bytes:
    header, _, payload = url.partition(",")
    if not header.startswith("data:"):
        raise AssertionError(f"not a data: URL: {url[:60]}")
    return base64.b64decode(payload) if header.endswith(";base64") else unquote_to_bytes(payload)


class ReportOutputTest(unittest.TestCase):
    """What report.py writes."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._scratch = Scratch()
        cls.dir = cls._scratch.__enter__()
        cls.trial_html = cls.build("trial", "--trial", TRIAL, "--narrative", NARRATIVE)
        cls.trial_page = Page(cls.trial_html)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._scratch.__exit__(None, None, None)

    @classmethod
    def build(cls, name: str, *args: object) -> str:
        out = cls.dir / name / "report.html"
        out.parent.mkdir()
        result = run_python(REPORT, *args, "--output", out)
        if result.returncode != 0:
            raise AssertionError(f"report.py failed for {name}:\n{result.stderr}")
        files = sorted(p.name for p in out.parent.iterdir())
        if files != ["report.html"]:
            raise AssertionError(f"report.py left {files} in its output directory")
        return out.read_text(encoding="utf-8")

    def test_writes_one_document_with_the_content_security_policy(self) -> None:
        page = self.trial_page
        self.assertTrue(self.trial_html.startswith("<!doctype html>"))
        policies = [m["content"] for m in page.metas if m.get("http-equiv", "").lower() == "content-security-policy"]
        self.assertEqual(len(policies), 1)
        for directive in EXPECTED_CSP:
            self.assertIn(directive, policies[0])
        self.assertEqual(page.mounts, 1, "one data-av-mount target")

    def test_embeds_the_trial_and_narrative_unchanged(self) -> None:
        page = self.trial_page
        self.assertEqual(json.loads(page.json["av-trial"]), json.loads(TRIAL.read_text(encoding="utf-8")))
        self.assertEqual(json.loads(page.json["av-narrative"]), json.loads(NARRATIVE.read_text(encoding="utf-8")))
        self.assertNotIn("av-spec", page.json)
        self.assertEqual(page.title, json.loads(NARRATIVE.read_text(encoding="utf-8"))["title"])

    def test_embeds_the_current_bundle_and_stylesheet(self) -> None:
        page = self.trial_page
        sources = [s["src"] for s in page.scripts if s.get("id", "").startswith("av-script-")]
        self.assertEqual(len(sources), 1, "only the library script without diagrams")
        self.assertEqual(data_url_bytes(sources[0]), BUNDLE.read_bytes())
        sheets = [data_url_bytes(url) for tag, name, url in page.urls if tag == "link" and name == "href"]
        self.assertIn(STYLESHEET.read_bytes(), sheets)

    def test_loads_nothing_from_outside_the_file(self) -> None:
        page = self.trial_page
        self.assertTrue(page.urls, "no URL attributes were found to check")
        for tag, name, value in page.urls:
            with self.subTest(tag=tag, attribute=name):
                self.assertTrue(value.startswith(("data:", "#")), f"<{tag} {name}> points outside the file: {value[:80]}")
        self.assertIsNone(re.search(r"https?://", self.trial_html), "a trial report carries a web address")
        self.assertNotIn("@import", STYLESHEET.read_text(encoding="utf-8"))
        self.assertIsNone(re.search(r"url\(\s*['\"]?(?!data:|#)", STYLESHEET.read_text(encoding="utf-8")), "the stylesheet references an external url()")

    def test_omits_the_mermaid_vendor_without_diagrams(self) -> None:
        self.assertNotIn("av-mermaid-notices", self.trial_page.json)
        self.assertLess(len(self.trial_html), 2_000_000)
        spec = self.dir / "plain-spec.json"
        spec.write_text(json.dumps({"title": "No diagrams", "sections": [{"title": "S", "blocks": [{"type": "text", "text": "diagram is only a word here"}]}]}), encoding="utf-8")
        page = Page(self.build("plain-spec", "--spec", spec))
        self.assertEqual(len([s for s in page.scripts if s.get("id", "").startswith("av-script-")]), 1)
        self.assertNotIn("av-mermaid-notices", page.json)

    def test_embeds_the_mermaid_vendor_for_a_diagram_block(self) -> None:
        html = self.build("showcase", "--spec", SHOWCASE)
        page = Page(html)
        sources = [s["src"] for s in page.scripts if s.get("id", "").startswith("av-script-")]
        self.assertEqual(len(sources), 2)
        self.assertEqual(data_url_bytes(sources[0]), MERMAID.read_bytes(), "the vendor loads first")
        self.assertEqual(data_url_bytes(sources[1]), BUNDLE.read_bytes())
        self.assertIn("av-mermaid-notices", page.json)
        self.assertEqual(json.loads(page.json["av-spec"]), json.loads(SHOWCASE.read_text(encoding="utf-8")))
        for tag, name, value in page.urls:
            self.assertTrue(value.startswith(("data:", "#")), f"<{tag} {name}> points outside the file")

    def test_embeds_the_mermaid_vendor_for_a_narrative_diagram(self) -> None:
        narrative = json.loads(NARRATIVE.read_text(encoding="utf-8"))
        narrative["sections"] = [{"title": "Flow", "blocks": [{"type": "diagram", "source": "flowchart LR\n  A --> B"}]}]
        path = self.dir / "diagram-narrative.json"
        path.write_text(json.dumps(narrative), encoding="utf-8")
        page = Page(self.build("diagram-narrative", "--trial", TRIAL, "--narrative", path))
        self.assertEqual(len([s for s in page.scripts if s.get("id", "").startswith("av-script-")]), 2)

    def test_hostile_text_stays_inside_its_json_block(self) -> None:
        paths = write_hostile_fixtures(self.dir / "hostile-input")
        trial = json.loads(paths["trial"].read_text(encoding="utf-8"))
        trial["runs"][0]["final_message_excerpt"] = "</script><x-hostile id=\"h-script-close\"><script>"
        paths["trial"].write_text(json.dumps(trial), encoding="utf-8")
        html = self.build("hostile", "--trial", paths["trial"], "--narrative", paths["narrative"])
        self.assertNotIn("<x-hostile", html)
        page = Page(html)
        self.assertEqual(json.loads(page.json["av-trial"]), trial)
        self.assertEqual(json.loads(page.json["av-narrative"]), json.loads(paths["narrative"].read_text(encoding="utf-8")))

    def test_title_option_overrides_the_report_title(self) -> None:
        page = Page(self.build("titled", "--trial", TRIAL, "--title", "Chosen <title>"))
        self.assertEqual(page.title, "Chosen <title>")


class ReportRefusalTest(unittest.TestCase):
    """Bad inputs end with an error: and a hint: line, a non-zero exit, and no output."""

    def setUp(self) -> None:
        self._scratch = Scratch()
        self.dir = self._scratch.__enter__()
        self.out = self.dir / "out" / "report.html"

    def tearDown(self) -> None:
        self._scratch.__exit__(None, None, None)

    def write(self, name: str, text: str) -> Path:
        path = self.dir / name
        path.write_text(text, encoding="utf-8")
        return path

    def assertRefused(self, *args: object, output: Path | None = None, message: str = "") -> None:
        output = output or self.out
        existed = output.exists()
        result = run_python(REPORT, *args, "--output", output)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        lines = result.stderr.splitlines()
        self.assertTrue(any(line.startswith("error: ") for line in lines), result.stderr)
        self.assertTrue(any(line.startswith("hint: ") for line in lines), result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        if message:
            self.assertIn(message, result.stderr)
        if not existed:
            self.assertFalse(output.exists(), "a refused run wrote output")

    def test_requires_trial_or_spec(self) -> None:
        self.assertRefused(message="supply --trial, --spec, or both")

    def test_refuses_a_narrative_with_a_spec(self) -> None:
        self.assertRefused("--trial", TRIAL, "--narrative", NARRATIVE, "--spec", SHOWCASE, message="one or the other")

    def test_refuses_a_narrative_without_a_trial(self) -> None:
        self.assertRefused("--narrative", NARRATIVE)

    def test_refuses_a_missing_file(self) -> None:
        self.assertRefused("--trial", self.dir / "absent.json", message="not found")

    def test_refuses_invalid_json(self) -> None:
        self.assertRefused("--trial", self.write("broken.json", '{"runs": ['), message="not valid JSON")

    def test_refuses_json_the_page_could_misread(self) -> None:
        self.assertRefused("--trial", self.write("dup.json", '{"runs": [], "name": "a", "name": "b"}'), message="duplicate object key")
        self.assertRefused("--trial", self.write("nan.json", '{"runs": [{"scenario": "c", "arm": "a", "passed": true, "seconds": NaN}]}'), message="NaN")

    def test_refuses_data_that_is_not_a_trial_report(self) -> None:
        for name, text in (("list.json", "[]"), ("runs.json", '{"runs": {}}'), ("none.json", "{}")):
            with self.subTest(file=name):
                self.assertRefused("--trial", self.write(name, text), message="not trial report data")

    def test_refuses_a_spec_without_a_title_or_sections(self) -> None:
        for name, text in (("untitled.json", '{"sections": []}'), ("unsectioned.json", '{"title": "T", "sections": {}}')):
            with self.subTest(file=name):
                self.assertRefused("--spec", self.write(name, text), message='needs a string "title" and a "sections" list')

    def test_refuses_a_directory_as_output(self) -> None:
        (self.dir / "folder").mkdir()
        self.assertRefused("--trial", TRIAL, output=self.dir / "folder", message="not a regular file")

    def test_keeps_a_differing_output_unless_replace_is_given(self) -> None:
        first = run_python(REPORT, "--trial", TRIAL, "--output", self.out)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertTrue(first.stdout.startswith("assembled "))
        again = run_python(REPORT, "--trial", TRIAL, "--output", self.out)
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertTrue(again.stdout.startswith("unchanged "))
        before = self.out.read_bytes()
        self.assertRefused("--trial", TRIAL, "--narrative", NARRATIVE, output=self.out, message="exists and differs")
        self.assertEqual(self.out.read_bytes(), before, "a refused run changed the existing output")
        replaced = run_python(REPORT, "--trial", TRIAL, "--narrative", NARRATIVE, "--output", self.out, "--replace")
        self.assertEqual(replaced.returncode, 0, replaced.stderr)
        self.assertNotEqual(self.out.read_bytes(), before)
        self.assertEqual(sorted(p.name for p in self.out.parent.iterdir()), ["report.html"])

    def test_requires_an_output(self) -> None:
        result = run_python(REPORT, "--trial", TRIAL)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("error:", result.stderr)
        self.assertIn("--output", result.stderr)


if __name__ == "__main__":
    unittest.main()
