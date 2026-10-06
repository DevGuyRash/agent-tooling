"""report.py writes one offline HTML file, embeds the Mermaid vendor only for
diagrams, and refuses bad inputs with an error: and hint: line; --check lists
the problems the page would show without writing, and --skeleton starts a
narrative with every id spelled as the trial records it. A comparison of any
alternatives arrives as --data JSON or a --csv long table, whose metric kinds
are inferred and whose ambiguous input is refused."""
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

    def test_general_draws_a_trial_through_the_comparison_views(self) -> None:
        page = Page(self.build("general", "--trial", TRIAL, "--general"))
        self.assertIs(json.loads(page.json["av-general"]), True)
        self.assertEqual(json.loads(page.json["av-trial"]), json.loads(TRIAL.read_text(encoding="utf-8")))
        self.assertNotIn("av-comparison", page.json)

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
        self.assertRefused(message="supply --trial, --data, --csv or --spec")

    def test_refuses_a_narrative_with_a_spec(self) -> None:
        self.assertRefused("--trial", TRIAL, "--narrative", NARRATIVE, "--spec", SHOWCASE, message="one or the other")

    def test_refuses_general_without_a_trial_alone(self) -> None:
        self.assertRefused("--general", "--trial", TRIAL, "--spec", SHOWCASE, message="--general draws a --trial")
        self.assertRefused("--general", "--spec", SHOWCASE, message="--general draws a --trial")

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



class ReportCheckTest(unittest.TestCase):
    """--check reads the inputs the way the page will, prints each problem with a hint, and writes nothing."""

    def setUp(self) -> None:
        self._scratch = Scratch()
        self.dir = self._scratch.__enter__()
        self.narrative = json.loads(NARRATIVE.read_text(encoding="utf-8"))

    def tearDown(self) -> None:
        self._scratch.__exit__(None, None, None)

    def write(self, name: str, value) -> Path:
        path = self.dir / name
        path.write_text(value if isinstance(value, str) else json.dumps(value), encoding="utf-8")
        return path

    def test_the_examples_have_no_problems(self) -> None:
        for args in (("--trial", TRIAL, "--narrative", NARRATIVE), ("--trial", TRIAL), ("--spec", SHOWCASE)):
            with self.subTest(args=args):
                result = run_python(REPORT, "--check", *args)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stderr, "")
                self.assertTrue(result.stdout.startswith("checked ") and result.stdout.rstrip().endswith(": no problems"), result.stdout)

    def test_errors_exit_non_zero_with_a_hint_each_and_write_nothing(self) -> None:
        self.narrative["decision"]["verdict"] = "adpot"
        self.narrative["arms"][0]["id"] = "curent"
        self.narrative["exclude"] = ["arm"]
        out = self.dir / "out" / "report.html"
        result = run_python(REPORT, "--check", "--trial", TRIAL, "--narrative", self.write("bad.json", self.narrative), "--output", out)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertFalse(out.exists(), "--check wrote a report")
        lines = result.stderr.splitlines()
        self.assertIn('error: narrative.decision.verdict: "adpot" is not one of the allowed values', lines)
        self.assertEqual(lines[lines.index('error: narrative.decision.verdict: "adpot" is not one of the allowed values') + 1], 'hint: did you mean "adopt"? Allowed values: adopt, reject, inconclusive, mixed, none')
        self.assertIn('error: narrative.exclude[0]: "arm" is not a section of the trial report', lines)
        self.assertIn('warning: narrative.arms[0].id: "curent" is not an arm in this trial, so this entry is not used', lines)
        self.assertEqual(len(lines), 6, "one problem line and one hint line for each of three problems")
        self.assertTrue(all(line.startswith(("error: ", "warning: ")) for line in lines[0::2]), lines)
        self.assertTrue(all(line.startswith("hint: ") for line in lines[1::2]), lines)
        self.assertTrue(lines[0].startswith("error: ") and lines[-2].startswith("warning: "), "errors are listed before warnings")
        self.assertIn("2 errors and 1 warning", result.stdout)
        self.assertNotIn("Traceback", result.stderr)

    def test_warnings_alone_exit_zero(self) -> None:
        self.narrative["titel"] = "A misspelled field"
        result = run_python(REPORT, "--check", "--trial", TRIAL, "--narrative", self.write("warn.json", self.narrative))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr.splitlines(), ['warning: narrative.titel: unknown field "titel" is not used', 'hint: did you mean "title"?'])
        self.assertIn("1 warning", result.stdout)

    def test_applies_the_json_rules_a_written_report_applies(self) -> None:
        for name, text, message in (("dup.json", '{"title": "a", "title": "b"}', "duplicate object key"), ("nan.json", '{"decision": {"headline": "x", "detail": NaN}}', "NaN")):
            with self.subTest(file=name):
                result = run_python(REPORT, "--check", "--trial", TRIAL, "--narrative", self.write(name, text))
                self.assertEqual(result.returncode, 1)
                self.assertIn(message, result.stderr)
                self.assertTrue(any(line.startswith("hint: ") for line in result.stderr.splitlines()))

    def test_checks_a_specification_against_the_trial_beside_it(self) -> None:
        spec = self.write("spec.json", {"title": "T", "sections": [{"title": "S", "blocks": [{"type": "tapestry", "arms": ["checklist", "chekclist"]}]}]})
        alone = run_python(REPORT, "--check", "--spec", spec)
        self.assertEqual(alone.returncode, 1)
        self.assertIn("error: sections[0].blocks[0] (tapestry): the tapestry block needs trial data", alone.stderr)
        beside = run_python(REPORT, "--check", "--spec", spec, "--trial", TRIAL)
        self.assertEqual(beside.returncode, 1)
        self.assertEqual(beside.stderr.splitlines(), ['error: sections[0].blocks[0] (tapestry).arms[1]: "chekclist" is not an arm in this trial', 'hint: did you mean "checklist"?'])

    def test_a_written_report_with_problems_says_so_and_carries_them(self) -> None:
        self.narrative["decision"]["verdict"] = "adpot"
        out = self.dir / "report.html"
        result = run_python(REPORT, "--trial", TRIAL, "--narrative", self.write("bad.json", self.narrative), "--output", out)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(out.exists())
        self.assertTrue(result.stdout.startswith("assembled "))
        self.assertEqual(result.stderr.splitlines(), ["warning: the inputs have 1 error; the report lists them at its top", "hint: run the same command with --check to see each one with its fix"])
        self.assertEqual(json.loads(Page(out.read_text(encoding="utf-8")).json["av-narrative"])["decision"]["verdict"], "adpot", "the narrative is embedded as written")

    def test_a_clean_write_prints_nothing_on_stderr(self) -> None:
        result = run_python(REPORT, "--trial", TRIAL, "--narrative", NARRATIVE, "--output", self.dir / "report.html")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")

    def test_still_refuses_what_a_write_refuses(self) -> None:
        for args, message in ((("--narrative", NARRATIVE), "--narrative needs --trial"), ((), "supply --trial, --data, --csv or --spec"), (("--trial", self.write("none.json", "{}")), "not trial report data")):
            with self.subTest(args=args):
                result = run_python(REPORT, "--check", *args)
                self.assertEqual(result.returncode, 1)
                self.assertIn(message, result.stderr)


class ReportSkeletonTest(unittest.TestCase):
    """--skeleton starts a narrative from the trial: ids as recorded, copies grouped, the rule beside the empty decision."""

    def setUp(self) -> None:
        self._scratch = Scratch()
        self.dir = self._scratch.__enter__()
        self.trial = json.loads(TRIAL.read_text(encoding="utf-8"))

    def tearDown(self) -> None:
        self._scratch.__exit__(None, None, None)

    def skeleton(self, trial: Path = TRIAL, *args: object) -> dict:
        result = run_python(REPORT, "--skeleton", *args, "--trial", trial)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_spells_every_arm_and_case_and_groups_identical_copies(self) -> None:
        narrative = self.skeleton()
        self.assertEqual([a["id"] for a in narrative["arms"]], list(self.trial["plan"]["arms"]))
        self.assertEqual(list(narrative["cases"]), [s["name"] for s in self.trial["plan"]["scenarios"]])
        self.assertEqual(narrative["identical"], [["current", "current-copy"]])
        self.assertEqual(narrative["$rule"], self.trial["plan"]["decision_rule"])
        self.assertEqual(narrative["decision"]["verdict"], "none")
        self.assertNotIn("summary", narrative, "an empty summary would hide the composed one")
        self.assertNotIn("$same_instructions", narrative)

    def test_the_only_problem_left_is_the_decision_to_write(self) -> None:
        path = self.dir / "narrative.json"
        path.write_text(json.dumps(self.skeleton()), encoding="utf-8")
        result = run_python(REPORT, "--check", "--trial", TRIAL, "--narrative", path)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stderr.splitlines()[0], 'error: narrative.decision.headline: "headline" is empty')
        self.assertEqual(len(result.stderr.splitlines()), 2)
        narrative = json.loads(path.read_text(encoding="utf-8"))
        narrative["decision"]["headline"] = "Adopt the checklist."
        path.write_text(json.dumps(narrative), encoding="utf-8")
        result = run_python(REPORT, "--check", "--trial", TRIAL, "--narrative", path)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")

    def test_arms_sharing_instructions_but_not_settings_are_not_called_identical(self) -> None:
        trial = json.loads(TRIAL.read_text(encoding="utf-8"))
        trial["plan"]["arms"]["current-copy"]["model"] = "fictional-large"
        path = self.dir / "trial.json"
        path.write_text(json.dumps(trial), encoding="utf-8")
        narrative = self.skeleton(path)
        self.assertNotIn("identical", narrative)
        digest = trial["plan"]["arms"]["current"]["instructions_sha256"][:12]
        self.assertEqual(narrative["$same_instructions"]["groups"], [{"arms": ["current", "current-copy"], "instructions_sha256": digest, "differ_in": ["model"]}])

    def test_material_text_does_not_split_identical_copies(self) -> None:
        trial = json.loads(TRIAL.read_text(encoding="utf-8"))
        trial["plan"]["arms"]["current"]["instructions_text"] = "Reply briefly."
        path = self.dir / "trial.json"
        path.write_text(json.dumps(trial), encoding="utf-8")
        self.assertEqual(self.skeleton(path)["identical"], [["current", "current-copy"]])

    def test_writes_a_file_and_keeps_a_differing_one_unless_replace(self) -> None:
        path = self.dir / "drafts" / "narrative.json"
        first = run_python(REPORT, "--skeleton", path, "--trial", TRIAL)
        self.assertEqual((first.returncode, first.stdout.strip()), (0, f"wrote {path}"), first.stderr)
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), self.skeleton())
        again = run_python(REPORT, "--skeleton", path, "--trial", TRIAL)
        self.assertEqual((again.returncode, again.stdout.strip()), (0, f"unchanged {path}"))
        path.write_text('{"title": "edited"}', encoding="utf-8")
        refused = run_python(REPORT, "--skeleton", path, "--trial", TRIAL)
        self.assertEqual(refused.returncode, 1)
        self.assertIn("exists and differs", refused.stderr)
        self.assertIn("hint: ", refused.stderr)
        self.assertEqual(path.read_text(encoding="utf-8"), '{"title": "edited"}')
        replaced = run_python(REPORT, "--skeleton", path, "--trial", TRIAL, "--replace")
        self.assertEqual(replaced.returncode, 0, replaced.stderr)
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), self.skeleton())
        self.assertEqual(sorted(p.name for p in path.parent.iterdir()), ["narrative.json"])

    def test_takes_only_a_trial(self) -> None:
        for args in ((), ("--trial", TRIAL, "--narrative", NARRATIVE), ("--trial", TRIAL, "--output", self.dir / "r.html"), ("--trial", TRIAL, "--check"), ("--spec", SHOWCASE)):
            with self.subTest(args=args):
                result = run_python(REPORT, "--skeleton", *args)
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertIn("error: --skeleton takes only --trial", result.stderr)
                self.assertIn("hint: ", result.stderr)

    def test_keeps_hostile_ids_exactly(self) -> None:
        paths = write_hostile_fixtures(self.dir / "hostile")
        trial = json.loads(paths["trial"].read_text(encoding="utf-8"))
        narrative = self.skeleton(paths["trial"])
        self.assertEqual([a["id"] for a in narrative["arms"]], list(trial["plan"]["arms"]))
        self.assertEqual(set(narrative["cases"]), {r["scenario"] for r in trial["runs"]})
        self.assertEqual(narrative["$rule"], trial["plan"]["decision_rule"])


COMPARISON = {
    "title": "Sandwich trial",
    "question": "Peanut butter or jelly?",
    "decision_rule": "Pick the filling more tasters call great.",
    "alternatives": [{"id": "pb", "label": "Peanut butter", "group": ["Savory"]}, {"id": "jelly", "label": "Jelly", "group": ["Sweet"]}],
    "metrics": [{"id": "taste", "kind": "ordinal", "levels": ["meh", "good", "great"], "primary": True}, {"id": "minutes", "kind": "numeric", "better": "lower", "unit": "minutes"}],
    "observations": [
        {"alternative": "pb", "metric": "taste", "value": "great"}, {"alternative": "pb", "metric": "taste", "value": "good"},
        {"alternative": "jelly", "metric": "taste", "value": "meh"}, {"alternative": "jelly", "metric": "taste", "value": None, "valid": False, "invalid_reason": "taster left"},
        {"alternative": "pb", "metric": "minutes", "value": 4}, {"alternative": "jelly", "metric": "minutes", "value": 3},
    ],
}
TABLE = """alternative,metric,value,case,group,n,valid,note
Ad A,clicked,yes,monday,Bold > Red,,,
Ad A,clicked,no,tuesday,Bold > Red,,,
Ad B,clicked,yes,monday,Calm,,,
Ad B,clicked,,tuesday,Calm,,,"no record"
Ad A,conversions,12,monday,,400,,
Ad B,conversions,9,monday,,380,,
Ad A,seconds,31.5,,,,,
Ad B,seconds,28,,,,false,"timer broke"
"""


class ComparisonInputTest(unittest.TestCase):
    """--data and --csv: a comparison of any alternatives becomes one offline report, checked the way the page reads it."""

    def setUp(self) -> None:
        self._scratch = Scratch()
        self.dir = self._scratch.__enter__()

    def tearDown(self) -> None:
        self._scratch.__exit__(None, None, None)

    def write(self, name: str, value) -> Path:
        path = self.dir / name
        path.write_text(value if isinstance(value, str) else json.dumps(value), encoding="utf-8")
        return path

    def build(self, *args: object) -> Page:
        out = self.dir / "out" / "report.html"
        result = run_python(REPORT, *args, "--output", out)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        return Page(out.read_text(encoding="utf-8"))

    def refused(self, *args: object, message: str, hint: str = "") -> None:
        result = run_python(REPORT, *args, "--output", self.dir / "out" / "refused.html")
        self.assertEqual(result.returncode, 1, result.stdout)
        lines = result.stderr.splitlines()
        self.assertEqual(len(lines), 2, result.stderr)
        self.assertTrue(lines[0].startswith("error: ") and message in lines[0], result.stderr)
        self.assertTrue(lines[1].startswith("hint: ") and hint in lines[1], result.stderr)
        self.assertNotIn("nothing is downloaded", lines[1], "a specific hint, not the generic one")
        self.assertFalse((self.dir / "out" / "refused.html").exists())

    def test_data_is_embedded_unchanged_with_its_narrative(self) -> None:
        data, narrative = self.write("c.json", COMPARISON), self.write("n.json", {"title": "Lunch", "decision": {"verdict": "adopt", "headline": "Peanut butter."}})
        page = self.build("--data", data, "--narrative", narrative)
        self.assertEqual(json.loads(page.json["av-comparison"]), COMPARISON)
        self.assertIn("av-narrative", page.json)
        self.assertNotIn("av-trial", page.json)
        self.assertEqual(page.title, "Lunch")
        self.assertEqual(page.mounts, 1)

    def test_a_csv_becomes_a_comparison_with_inferred_kinds_groups_and_invalid_rows(self) -> None:
        page = self.build("--csv", self.write("ads.csv", TABLE))
        c = json.loads(page.json["av-comparison"])
        self.assertEqual({m["id"]: m["kind"] for m in c["metrics"]}, {"clicked": "binary", "conversions": "count", "seconds": "numeric"})
        self.assertEqual(c["alternatives"], [{"id": "Ad A", "group": ["Bold", "Red"]}, {"id": "Ad B", "group": ["Calm"]}])
        self.assertEqual([x["id"] for x in c["cases"]], ["monday", "tuesday"])
        clicked = [o for o in c["observations"] if o["metric"] == "clicked"]
        self.assertEqual([o["value"] for o in clicked], [True, False, True, None])
        self.assertEqual((clicked[3]["valid"], clicked[3]["invalid_reason"], clicked[3]["note"]), (False, "empty value", "no record"))
        conversions = [o for o in c["observations"] if o["metric"] == "conversions"]
        self.assertEqual([(o["value"], o["n"]) for o in conversions], [(12, 400), (9, 380)])
        broke = [o for o in c["observations"] if o["metric"] == "seconds"][1]
        self.assertEqual((broke["value"], broke["valid"], broke["invalid_reason"]), (28, False, "marked invalid"))
        self.assertEqual(clicked[0]["source"], "ads.csv row 2")
        self.assertEqual(page.title, "Comparison")

    def test_data_defines_what_the_csv_cannot_infer(self) -> None:
        data = self.write("c.json", {"title": "Taste", "alternatives": [{"id": "pb", "label": "Peanut butter"}], "metrics": [{"id": "taste", "kind": "ordinal", "levels": ["meh", "good", "great"]}, {"id": "ate", "kind": "binary"}]})
        table = self.write("t.csv", "alternative,metric,value\npb,taste,great\njelly,taste,meh\npb,ate,1\njelly,ate,0\n")
        page = self.build("--data", data, "--csv", table)
        c = json.loads(page.json["av-comparison"])
        self.assertEqual([a.get("label") for a in c["alternatives"]], ["Peanut butter", None])
        self.assertEqual([o["value"] for o in c["observations"]], ["great", "meh", True, False])
        self.assertEqual(page.title, "Taste")
        result = run_python(REPORT, "--check", "--data", data, "--csv", table)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_ambiguous_or_unreadable_tables_are_refused_with_a_specific_hint(self) -> None:
        head = "alternative,metric,value"
        cases = [
            (f"{head}\na,x,0\nb,x,1\n", "holds only 0 and 1", '"binary" or "numeric"'),
            (f"{head}\na,x,3\nb,x,yes\n", "mixes numbers and true/false values", "one type"),
            (f"{head}\na,x,tasty\nb,x,bland\n", "whose order is unknown", '"levels" lowest first'),
            ("alternative,metrik,value\na,x,1\n", 'column 2 "metrik"', 'did you mean "metric"?'),
            ("alternative,value\na,1\n", "no metric column", "the first row names the columns"),
            (f"{head}\na,x\n", "row 2 has 2 cells for 3 columns", "quote cells"),
            (f"{head},n\na,x,3,10\nb,x,4,\n", "has n on some rows but not row 3", "every row"),
            (f"{head},group\na,x,1.5,G1\na,x,2.5,G2\n", 'puts "a" in group "G2", but row 2 puts it in "G1"', "one group path"),
            (f"{head},valid\na,x,1.5,maybe\n", 'valid "maybe" is not true or false', "true or false"),
            (f"{head}\na,,1.5\n", "row 2 has no metric", "names its metric"),
            (f"{head},{head}\na,x,1,a,x,1\n", 'column "alternative" appears twice', "one column per name"),
            ("", "is empty", "the first row names the columns"),
        ]
        for text, message, hint in cases:
            with self.subTest(table=text):
                self.refused("--csv", self.write("t.csv", text), message=message, hint=hint)
        data = self.write("c.json", {"alternatives": [], "metrics": [{"id": "taste", "kind": "ordinal", "levels": ["meh", "good"]}]})
        self.refused("--data", data, "--csv", self.write("t.csv", f"{head}\npb,taste,great\n"), message='value "great" is not one of the levels', hint="levels: meh, good")
        self.refused("--data", self.write("no.json", {"runs": []}), message="is not comparison data", hint='"alternatives"')

    def test_check_reads_a_comparison_and_its_narrative_the_way_the_page_does(self) -> None:
        data = self.write("c.json", COMPARISON)
        clean = run_python(REPORT, "--check", "--data", data)
        self.assertEqual((clean.returncode, clean.stderr), (0, ""))
        self.assertTrue(clean.stdout.rstrip().endswith(": no problems"), clean.stdout)
        broken = dict(COMPARISON, observations=[*COMPARISON["observations"], {"alternative": "pbb", "metric": "taste", "value": "superb"}], baseline="jely")
        narrative = self.write("n.json", {"include": ["verdict", "resuts"], "criteria": [{"label": "Price"}]})
        result = run_python(REPORT, "--check", "--data", self.write("b.json", broken), "--narrative", narrative)
        self.assertEqual(result.returncode, 1)
        lines = result.stderr.splitlines()
        self.assertEqual(len(lines) % 2, 0)
        self.assertTrue(all(line.startswith(("error: ", "warning: ")) for line in lines[0::2]) and all(line.startswith("hint: ") for line in lines[1::2]), result.stderr)
        for expected in ('error: comparison.baseline: "jely" is not an alternative in this comparison', 'error: comparison.observations[6].alternative: "pbb"', 'error: narrative.include[1]: "resuts" is not a section of the comparison report', 'error: narrative.criteria[0]: a criterion needs "metric", "scores" or cells that rate it'):
            self.assertIn(expected, result.stderr)
        self.assertIn('hint: did you mean "jelly"?', result.stderr)
        self.assertFalse(any(self.dir.glob("*.html")))

    def test_a_specification_borrows_the_comparison_beside_it(self) -> None:
        spec = self.write("s.json", {"title": "T", "sections": [{"title": "S", "blocks": [{"type": "metric", "metric": "tast"}, {"type": "scorecard"}]}]})
        result = run_python(REPORT, "--check", "--spec", spec, "--data", self.write("c.json", COMPARISON))
        self.assertEqual(result.returncode, 1)
        self.assertIn('error: sections[0].blocks[0] (metric).metric: "tast" is not a metric in this comparison', result.stderr)
        self.assertEqual(result.stderr.count("error: "), 1, result.stderr)
        alone = run_python(REPORT, "--check", "--spec", spec)
        self.assertIn("the scorecard block needs comparison data", alone.stderr)
        self.assertIn('hint: pass --data or --csv to report.py, or set the specification\'s "comparison" field', alone.stderr)

    def test_a_trial_and_a_comparison_need_a_specification_to_share_a_page(self) -> None:
        result = run_python(REPORT, "--trial", TRIAL, "--data", self.write("c.json", COMPARISON), "--output", self.dir / "r.html")
        self.assertEqual(result.returncode, 1)
        self.assertIn("each make a report of their own", result.stderr)

    def test_skeleton_starts_a_comparison_narrative_whose_only_problem_is_the_decision(self) -> None:
        data = self.write("c.json", COMPARISON)
        result = run_python(REPORT, "--skeleton", "--data", data)
        self.assertEqual(result.returncode, 0, result.stderr)
        narrative = json.loads(result.stdout)
        self.assertEqual([a["id"] for a in narrative["alternatives"]], ["pb", "jelly"])
        self.assertEqual(narrative["$rule"], COMPARISON["decision_rule"])
        self.assertEqual(narrative["$metrics"], {"taste": "ordinal", "minutes": "numeric"})
        self.assertEqual((narrative["criteria"], narrative["question"]), ([], COMPARISON["question"]))
        self.assertIn("report.py --check --data c.json --narrative THIS_FILE", narrative["$about"])
        path = self.write("n.json", narrative)
        check = run_python(REPORT, "--check", "--data", data, "--narrative", path)
        self.assertEqual(check.stderr.splitlines()[0], 'error: narrative.decision.headline: "headline" is empty')
        self.assertEqual(len(check.stderr.splitlines()), 2)
        from_csv = run_python(REPORT, "--skeleton", "--csv", self.write("t.csv", TABLE))
        self.assertEqual([a["id"] for a in json.loads(from_csv.stdout)["alternatives"]], ["Ad A", "Ad B"])
        both = run_python(REPORT, "--skeleton", "--trial", TRIAL, "--data", data)
        self.assertEqual(both.returncode, 1)


if __name__ == "__main__":
    unittest.main()
