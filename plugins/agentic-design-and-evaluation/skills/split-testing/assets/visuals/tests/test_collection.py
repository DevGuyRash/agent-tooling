"""A collection of reports, end to end: report.py --collection writes one
offline file with one copy of the library and every member's data, --check
names problems in the collection and in each member's narrative, a
specification mixes collection views with any other block, and in a real
browser the index filters and switches design, a member opens in full with its
own run links, two members open side by side, and nothing scrolls sideways at
phone width. The views themselves are checked in collection.cjs."""
from __future__ import annotations

import json
from pathlib import Path
import re
import unittest

from visual_harness import EXAMPLES, REPORT, NodeCases, Scratch, run_python
import test_browser as TB


class CollectionViewsTest(NodeCases):
    """The composition, the index designs, the cross-report views and the side-by-side view (collection.cjs)."""

    script = "collection.cjs"
    minimum = 15

    def test_collection_views(self) -> None:
        self.run_script_cases()


def write_collection(directory: Path, **changes) -> Path:
    """Three members by file: the fictional trial with its narrative, the same trial without one, and a comparison."""
    collection = {
        "title": "Collected reports",
        "themes": [{"id": "trials", "label": "Trials", "summary": "Two readings of one trial."}, {"id": "choices", "label": "Choices"}],
        "members": [
            {"id": "fictional", "theme": "trials", "trial": str(EXAMPLES / "fictional-trial.json"), "narrative": str(EXAMPLES / "fictional-narrative.json")},
            {"id": "again", "theme": "trials", "follows": "fictional", "date": "2026-10-16", "trial": "fictional-trial.json"},
            {"id": "sandwich", "theme": "choices", "comparison": "sandwich.json", "narrative": "sandwich-narrative.json"},
        ],
        "pairs": [{"a": "fictional", "b": "again"}],
    }
    collection.update(changes)
    for name, source in (("fictional-trial.json", EXAMPLES / "fictional-trial.json"), ("sandwich.json", EXAMPLES / "comparisons/sandwich.json"), ("sandwich-narrative.json", EXAMPLES / "comparisons/sandwich-narrative.json")):
        (directory / name).write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    path = directory / "collection.json"
    path.write_text(json.dumps(collection), encoding="utf-8")
    return path


def embedded(page: Path, ident: str):
    found = re.search(rf'<script[^>]*id="{ident}"[^>]*>(.*?)</script>', page.read_text(encoding="utf-8"), re.S)
    return json.loads(found.group(1).replace("<\\/", "</")) if found else None


class CollectionCliTest(unittest.TestCase):
    def setUp(self) -> None:
        self._scratch = Scratch()
        self.dir = self._scratch.__enter__()

    def tearDown(self) -> None:
        self._scratch.__exit__(None, None, None)

    def test_writes_one_offline_file_with_one_library_and_every_member(self) -> None:
        source = write_collection(self.dir)
        page = self.dir / "collection.html"
        built = run_python(REPORT, "--collection", source, "--output", page)
        self.assertEqual(built.returncode, 0, built.stderr)
        self.assertRegex(built.stdout, r"^assembled .*collection\.html \(\d+ bytes\)")
        self.assertEqual(built.stderr, "", "a clean collection writes no warning")
        document = page.read_text(encoding="utf-8")
        self.assertEqual(len(re.findall(r'id="av-script-\d+"', document)), 1, "one copy of the library")
        self.assertIn("default-src 'none'", document)
        self.assertIn("<title>Collected reports</title>", document)
        data = embedded(page, "av-collection")
        self.assertEqual([m["id"] for m in data["members"]], ["fictional", "again", "sandwich"])
        self.assertEqual(data["members"][1]["trial"], json.loads((EXAMPLES / "fictional-trial.json").read_text(encoding="utf-8")), "a member's file is read relative to the collection")
        self.assertIsInstance(data["members"][2]["narrative"], dict)
        again = run_python(REPORT, "--collection", source, "--output", page)
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertTrue(again.stdout.startswith("unchanged "), "the same inputs write the same file")

    def test_check_names_problems_in_the_collection_and_in_each_narrative(self) -> None:
        source = write_collection(self.dir)
        clean = run_python(REPORT, "--check", "--collection", source)
        self.assertEqual(clean.returncode, 0, clean.stderr)
        self.assertIn("no problems", clean.stdout)
        data = json.loads(source.read_text(encoding="utf-8"))
        data["members"][1].update(follows="fictionl", theme="trails", date="16 Oct")
        data["members"].append({"id": "two words", "trial": "fictional-trial.json", "comparison": "sandwich.json"})
        data["pairs"].append({"a": "again", "b": "again"})
        narrative = json.loads((EXAMPLES / "fictional-narrative.json").read_text(encoding="utf-8"))
        narrative["decision"]["verdict"] = "adpot"
        (self.dir / "narrative.json").write_text(json.dumps(narrative), encoding="utf-8")
        data["members"][0]["narrative"] = "narrative.json"
        source.write_text(json.dumps(data), encoding="utf-8")
        checked = run_python(REPORT, "--check", "--collection", source)
        self.assertEqual(checked.returncode, 1, checked.stdout)
        for line in ('error: collection.members[1].follows: "fictionl" is not a report in this collection', 'hint: did you mean "fictional"?',
                     'error: collection.members[3].id: "two words" cannot be a report id', 'error: collection.members[3]: has both "trial" and "comparison"',
                     "error: collection.pairs[1]: pairs a report with itself", "error: collection.members[0].narrative.decision.verdict:",
                     'warning: collection.members[1].theme: "trails" is not a theme in this collection', 'warning: collection.members[1].date: "16 Oct" is not a date'):
            self.assertIn(line, checked.stderr)
        written = run_python(REPORT, "--collection", source, "--output", self.dir / "out.html")
        self.assertEqual(written.returncode, 0, written.stderr)
        self.assertIn("warning: the inputs have", written.stderr, "a report with problems is still written, and says so")

    def test_refuses_a_missing_member_file_and_inputs_it_cannot_mix(self) -> None:
        source = write_collection(self.dir)
        data = json.loads(source.read_text(encoding="utf-8"))
        data["members"][1]["trial"] = "missing.json"
        broken = self.dir / "broken.json"
        broken.write_text(json.dumps(data), encoding="utf-8")
        page = self.dir / "out.html"
        missing = run_python(REPORT, "--collection", broken, "--output", page)
        self.assertEqual(missing.returncode, 1)
        self.assertIn("error: collection.members[1].trial file not found:", missing.stderr)
        self.assertIn("hint:", missing.stderr)
        self.assertFalse(page.exists(), "nothing is written")
        mixed = run_python(REPORT, "--collection", source, "--trial", EXAMPLES / "fictional-trial.json", "--output", page)
        self.assertEqual(mixed.returncode, 1)
        self.assertIn("--collection names each report's own files", mixed.stderr)
        shapeless = self.dir / "shapeless.json"
        shapeless.write_text('{"reports": []}', encoding="utf-8")
        self.assertIn('needs a "members" list', run_python(REPORT, "--collection", shapeless, "--output", page).stderr)

    def test_a_specification_mixes_collection_views_with_any_block(self) -> None:
        source = write_collection(self.dir)
        spec = {"title": "Mixed", "sections": [
            {"title": "Story", "blocks": [{"type": "text", "text": "Why these two."}, {"type": "decisions", "themes": ["trials"]}]},
            {"title": "Index", "blocks": [{"type": "reports", "layouts": ["table"]}, {"type": "report-compare", "a": "fictional", "b": "again"}]},
        ]}
        path = self.dir / "spec.json"
        path.write_text(json.dumps(spec), encoding="utf-8")
        self.assertEqual(run_python(REPORT, "--check", "--spec", path, "--collection", source).returncode, 0)
        built = run_python(REPORT, "--spec", path, "--collection", source, "--output", self.dir / "mixed.html")
        self.assertEqual(built.returncode, 0, built.stderr)
        self.assertEqual(embedded(self.dir / "mixed.html", "av-spec")["title"], "Mixed")
        spec["sections"][1]["blocks"][1]["b"] = "agian"
        spec["sections"][1]["blocks"][0]["layouts"] = ["grid"]
        path.write_text(json.dumps(spec), encoding="utf-8")
        checked = run_python(REPORT, "--check", "--spec", path, "--collection", source)
        self.assertEqual(checked.returncode, 1)
        self.assertIn('error: sections[1].blocks[1] (report-compare).b: "agian" is not a report in this collection', checked.stderr)
        self.assertIn('warning: sections[1].blocks[0] (reports).layouts[0]: "grid" is not one of the allowed values', checked.stderr)
        alone = run_python(REPORT, "--check", "--spec", path)
        self.assertIn("the report-compare block needs a collection", alone.stderr)


READER = """
const wait = ms => new Promise(r => setTimeout(r, ms));
const go = async hash => { location.hash = hash; await wait(400); };
const home = document.querySelector("[data-av-report]"), out = {};
out.cards = document.querySelectorAll('[data-av-rx-view="cards"] [data-av-rx-card]').length;
document.querySelector('[data-av-rx-verdict="adopt"]').click();
out.adopted = document.querySelector("[data-av-rx-count]").textContent;
document.querySelector("[data-av-rx-clear]").click();
document.querySelector('[data-av-rx-layout="table"]').click();
out.views = [...document.querySelectorAll("[data-av-rx-view]")].filter(v => !v.hidden).map(v => v.dataset.avRxView);
const picks = [...document.querySelectorAll('[data-av-rx-view="table"] [data-av-rx-pick]')];
picks[0].click(); picks[1].click();
out.tray = document.querySelector("[data-av-rx-go]").getAttribute("href");
await go("#report/fictional");
const reader = () => document.querySelector("[data-av-reader]");
out.member = { title: reader().querySelector(".av-title").textContent, homeHidden: home.hidden, focus: document.activeElement.className, sections: reader().querySelectorAll(".av-section").length };
await go("#report/fictional/run-1");
out.drawer = !!reader().querySelector("dialog[open]");
reader().querySelector(".av-drawer-close").click(); await wait(100);
out.afterDrawer = location.hash;
reader().querySelector('.av-toc a[href="#cases"]').click(); await wait(300);
out.afterSection = location.hash;
document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true })); await wait(400);
out.afterEscape = { reader: !!reader(), homeHidden: home.hidden };
await go(out.tray);
out.compare = { block: !!reader().querySelector(".av-block--report-compare"), letters: reader().querySelectorAll(".av-rc-side").length };
await go("#compare/fictional/nope");
out.missing = reader().querySelector(".av-title").textContent;
await go("#reports");
out.back = { reader: !!reader(), homeHidden: home.hidden };
return out;
"""


@unittest.skipUnless(TB.BROWSER, "google-chrome-stable or chromium is not on PATH")
class CollectionBrowserTest(unittest.TestCase):
    """The collection in a real browser, driven as test_browser.py drives a report."""

    setUp, tearDown, build, drive = TB.BrowserRenderTest.setUp, TB.BrowserRenderTest.tearDown, TB.BrowserRenderTest.build, TB.BrowserRenderTest.drive

    def test_the_reader_opens_compares_and_returns(self) -> None:
        page = self.build("--collection", write_collection(self.dir))
        out = self.drive(page, width=1280, script=READER)["result"]
        self.assertEqual(out["cards"], 3)
        self.assertEqual(out["adopted"], "2 of 3 reports")
        self.assertEqual(out["views"], ["table"])
        self.assertEqual(out["tray"], "#compare/fictional/again")
        narrative = json.loads((EXAMPLES / "fictional-narrative.json").read_text(encoding="utf-8"))
        self.assertEqual(out["member"]["title"], narrative["title"])
        self.assertTrue(out["member"]["homeHidden"])
        self.assertEqual(out["member"]["focus"], "av-title")
        self.assertGreater(out["member"]["sections"], 5)
        self.assertTrue(out["drawer"], "a run link inside the member opens its drawer")
        self.assertEqual(out["afterDrawer"], "#report/fictional")
        self.assertEqual(out["afterSection"], "#report/fictional/cases", "a section link stays inside the member's address")
        self.assertEqual(out["afterEscape"], {"reader": False, "homeHidden": False})
        self.assertEqual(out["compare"], {"block": True, "letters": 2})
        self.assertEqual(out["missing"], "Not in this collection")
        self.assertEqual(out["back"], {"reader": False, "homeHidden": False})

    def test_phone_width_never_scrolls_the_collection_sideways(self) -> None:
        page = self.build("--collection", write_collection(self.dir))
        script = """
const wait = ms => new Promise(r => setTimeout(r, ms));
const check = new Function(%s);
const out = { home: check() };
for (const l of ["list", "table", "matrix"]) { document.querySelector(`[data-av-rx-layout="${l}"]`).click(); out[l] = check(); }
location.hash = "#compare/fictional/sandwich"; await wait(400); out.compare = check();
location.hash = "#report/sandwich"; await wait(400); out.member = check();
return out;
""" % json.dumps(TB.OVERFLOW)
        out = self.drive(page, width=390, script=script)["result"]
        for view, result in out.items():
            with self.subTest(view=view):
                self.assertEqual(result["offenders"], [], "content wider than a 390 px phone outside any scrolling container")
                self.assertLessEqual(result["scrollWidth"], result["innerWidth"])


if __name__ == "__main__":
    unittest.main()
