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

from visual_harness import EXAMPLES, REPORT, NodeCases, Scratch, run_python, told_spec
import test_browser as TB


class CollectionViewsTest(NodeCases):
    """The composition, the index designs, the cross-report views and the side-by-side view (collection.cjs)."""

    script = "collection.cjs"
    minimum = 15

    def test_collection_views(self) -> None:
        self.run_script_cases()


def write_collection(directory: Path, costs: bool = False, **changes) -> Path:
    """Three members by file: the fictional trial with its narrative, the same trial and narrative again, and a
    comparison; the collection tells its own story and reads each of its sections. With `costs`, every run of the trial
    records a cost that differs by arm, and the trial its per-arm cost change from the baseline, so changes can be set
    against their cost."""
    collection = {
        "title": "Collected reports",
        "story": {"background": "Two readings of one invented trial and one invented lunch.", "intent": "Show a collection to a reader new to it.", "questions": ["Does the collection read as one story?"], "covers": "Three reports.", "notCovered": "Anything real."},
        "readings": {s: f"What the {s} views show here." for s in ("glance", "reports", "shifts", "timeline", "matchups")},
        "themes": [{"id": "trials", "label": "Trials", "summary": "Two readings of one trial."}, {"id": "choices", "label": "Choices", "summary": "One everyday choice."}],
        "members": [
            {"id": "fictional", "theme": "trials", "trial": "fictional-trial.json", "narrative": "narratives/fictional-narrative.json"},
            {"id": "again", "theme": "trials", "follows": "fictional", "date": "2026-10-16", "trial": "fictional-trial.json", "narrative": "narratives/again.json"},
            {"id": "sandwich", "theme": "choices", "comparison": "sandwich.json", "narrative": "sandwich-narrative.json"},
        ],
        "pairs": [{"a": "fictional", "b": "again"}],
    }
    collection.update(changes)
    (directory / "narratives").mkdir(exist_ok=True)
    for name, source in (("fictional-trial.json", EXAMPLES / "fictional-trial.json"), ("narratives/fictional-narrative.json", EXAMPLES / "fictional-narrative.json"),
                         ("sandwich.json", EXAMPLES / "comparisons/sandwich.json"), ("sandwich-narrative.json", EXAMPLES / "comparisons/sandwich-narrative.json")):
        (directory / name).write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    if costs:
        trial = json.loads((directory / "fictional-trial.json").read_text(encoding="utf-8"))
        arms = list(dict.fromkeys(r["arm"] for r in trial["runs"]))
        for r in trial["runs"]:
            r.setdefault("usage", {})["cost_usd"] = round(0.02 * (1 + 0.35 * arms.index(r["arm"])) * (1 + 0.05 * (r.get("repeat") or 0)), 4)
        # trial.py's per-case median difference in cost per run from the baseline, as a share, for every other arm.
        trial["baseline"] = "current"
        trial["pct_vs_baseline"] = {a: {"cost_usd": {"median": round(0.35 * i - 0.2, 2)}} for i, a in enumerate(arms) if a != "current"}
        (directory / "fictional-trial.json").write_text(json.dumps(trial), encoding="utf-8")
    again = json.loads((EXAMPLES / "fictional-narrative.json").read_text(encoding="utf-8"))
    again["decision"] = {**again["decision"], "verdict": "mixed", "label": "Read again"}
    (directory / "narratives/again.json").write_text(json.dumps(again), encoding="utf-8")
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
                     'error: collection.members[3].id: "two words" cannot be a report id', 'error: collection.members[3]: has more than one of "trial", "comparison" and "spec"',
                     "error: collection.pairs[1]: pairs a report with itself", "error: collection.members[0].narrative.decision.verdict:",
                     'warning: collection.members[1].theme: "trails" is not a theme in this collection', 'warning: collection.members[1].date: "16 Oct" is not a calendar day'):
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

    def test_member_files_stay_inside_the_collection_directory(self) -> None:
        inner = self.dir / "inner"
        inner.mkdir()
        source = write_collection(inner)
        (self.dir / "outside.json").write_text('{"secret": "outside"}', encoding="utf-8")
        (inner / "link.json").symlink_to(self.dir / "outside.json")
        page = self.dir / "out.html"
        for name, message in (("../outside.json", "is outside the collection's directory"), (str(self.dir / "outside.json"), "is an absolute path"), ("link.json", "is outside the collection's directory")):
            with self.subTest(name=name):
                data = json.loads(source.read_text(encoding="utf-8"))
                data["members"][1]["narrative"] = name
                bad = inner / "bad.json"
                bad.write_text(json.dumps(data), encoding="utf-8")
                for args in (("--collection", bad, "--output", page), ("--check", "--collection", bad)):
                    refused = run_python(REPORT, *args)
                    self.assertEqual(refused.returncode, 1)
                    self.assertIn(f"error: collection.members[1].narrative: {name} {message}", refused.stderr)
                    self.assertIn("hint:", refused.stderr)
                self.assertFalse(page.exists(), "nothing is written, so nothing outside is embedded")

    def test_check_with_a_specification_checks_the_borrowed_collection(self) -> None:
        source = write_collection(self.dir)
        data = json.loads(source.read_text(encoding="utf-8"))
        data["members"][1].update(follows="missing", date="2026-02-30")
        source.write_text(json.dumps(data), encoding="utf-8")
        spec = self.dir / "spec.json"
        spec.write_text(json.dumps(told_spec({"title": "Mixed", "sections": [{"title": "Index", "blocks": [{"type": "reports"}]}]})), encoding="utf-8")
        checked = run_python(REPORT, "--check", "--spec", spec, "--collection", source)
        self.assertEqual(checked.returncode, 1, "the page checks the collection it borrows, so --check does too")
        self.assertIn('error: collection.members[1].follows: "missing" is not a report in this collection', checked.stderr)
        self.assertIn('warning: collection.members[1].date: "2026-02-30" is not a calendar day written YYYY-MM-DD, alone or with a time such as T09:30:00Z, so it is not used', checked.stderr)

    def test_a_member_may_be_a_specification_file(self) -> None:
        source = write_collection(self.dir)
        (self.dir / "custom.json").write_text(json.dumps(told_spec({"title": "Hand-built", "sections": [{"title": "Decision", "blocks": [{"type": "verdict", "verdict": "adopt", "headline": "Ship it."}]}]})), encoding="utf-8")
        data = json.loads(source.read_text(encoding="utf-8"))
        data["members"].append({"id": "custom", "spec": "custom.json"})
        source.write_text(json.dumps(data), encoding="utf-8")
        self.assertEqual(run_python(REPORT, "--check", "--collection", source).returncode, 0)
        page = self.dir / "c.html"
        self.assertEqual(run_python(REPORT, "--collection", source, "--output", page).returncode, 0)
        self.assertEqual(embedded(page, "av-collection")["members"][3]["spec"]["title"], "Hand-built")

    def test_a_specification_mixes_collection_views_with_any_block(self) -> None:
        source = write_collection(self.dir)
        spec = told_spec({"title": "Mixed", "sections": [
            {"title": "Story", "blocks": [{"type": "text", "text": "Why these two."}, {"type": "decisions", "themes": ["trials"]}]},
            {"title": "Index", "blocks": [{"type": "reports", "layouts": ["table"]}, {"type": "report-compare", "a": "fictional", "b": "again"}]},
        ]})
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
reader().querySelector('.av-toc a[href$="/cases"]').click(); await wait(300);
out.afterSection = location.hash;
document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true })); await wait(400);
out.afterEscape = { reader: !!reader(), homeHidden: home.hidden };
await go(out.tray);
out.compare = { block: !!reader().querySelector(".av-block--report-compare"), letters: reader().querySelectorAll(".av-rc-side").length };
await go("#compare/fictional/nope");
out.missing = reader().querySelector(".av-title").textContent;
await go("#reports");
out.back = { reader: !!reader(), homeHidden: home.hidden };
// Filters by theme, model and search narrow every design; the table sorts by a column, a second press reversing it.
const count = () => document.querySelector("[data-av-rx-count]").textContent;
const theme = document.querySelector("[data-av-rx-theme]"); theme.value = "choices"; theme.dispatchEvent(new Event("change"));
out.byTheme = count(); document.querySelector("[data-av-rx-clear]").click();
const search = document.querySelector("[data-av-rx-q]"); search.value = "SANDWICH"; search.dispatchEvent(new Event("input"));
out.bySearch = [count(), [...document.querySelectorAll('[data-av-rx-view="table"] tbody tr')].filter(r => !r.hidden).map(r => r.dataset.member)];
document.querySelector("[data-av-rx-clear]").click();
const runsHead = [...document.querySelectorAll(".av-rx-table thead th")].find(th => th.textContent.startsWith("Evidence"));
const order = () => [...document.querySelectorAll(".av-rx-table tbody tr")].map(r => r.dataset.member);
runsHead.querySelector("button").click(); out.sortUp = [order(), runsHead.getAttribute("aria-sort")];
runsHead.querySelector("button").click(); out.sortDown = [order(), runsHead.getAttribute("aria-sort")];
// Back and Forward move between the collection and a report; returning restores where the reader was.
document.querySelector('[data-av-rx-layout="cards"]').click();
const link = document.querySelector('[data-av-rx-view="cards"] [data-member="sandwich"] .av-rx-title a');
link.scrollIntoView({ block: "center", behavior: "instant" }); await wait(50);
const scrolled = Math.round(scrollY); link.focus(); link.click(); await wait(400);
out.opened = [location.hash, !!reader()];
history.back(); await wait(400);
const box = link.getBoundingClientRect();
out.backed = { hash: location.hash, reader: !!reader(), scroll: Math.abs(Math.round(scrollY) - scrolled) < innerHeight / 4 && box.top >= 0 && box.bottom <= innerHeight, focus: document.activeElement === link };
history.forward(); await wait(400);
out.forwarded = [location.hash, !!reader()];
// A member's own brand link (#av-top, an id the collection has too) stays inside the member.
reader().querySelector(".av-brand").click(); await wait(400);
out.brand = [location.hash, !!reader()];
// Printing with a report open leaves the reader's theme as it was.
document.documentElement.setAttribute("data-theme", "dark");
dispatchEvent(new Event("beforeprint")); const during = document.documentElement.getAttribute("data-theme");
dispatchEvent(new Event("afterprint"));
out.print = [during, document.documentElement.getAttribute("data-theme")];
return out;
"""


@unittest.skipUnless(TB.BROWSER, "google-chrome-stable or chromium is not on PATH")
class CollectionBrowserTest(unittest.TestCase):
    """The collection in a real browser, driven as test_browser.py drives a report."""

    setUp, tearDown, build, drive = TB.BrowserRenderTest.setUp, TB.BrowserRenderTest.tearDown, TB.BrowserRenderTest.build, TB.BrowserRenderTest.drive

    def test_each_setup_reads_on_its_own_row_and_the_scatter_spreads_its_points(self) -> None:
        # The owner, of the setups' tracks: "how would I know what marks are what when the triangle has it's own min and
        # max?", "better upper/lower bounds and spacing between the marks (but not overdoing it)"; of the scatter, a hover
        # that showed the chart's caption rather than the point's own numbers.
        page = self.build("--collection", write_collection(self.dir, costs=True))
        script = TB.CARD + """
const box = e => e.getBoundingClientRect(), meets = (a, b) => a.left < b.right - 0.5 && b.left < a.right - 0.5 && a.top < b.bottom - 0.5 && b.top < a.bottom - 0.5;
const plots = [...document.querySelectorAll(".av-block--shifts .av-cx-lanes")].map(plot => {
  const rows = [...plot.querySelectorAll(".av-cx-row")];
  const marks = rows.map(r => r.querySelector(".av-cx-pt")).filter(Boolean).map(box);
  return { rows: rows.length, named: rows.filter(r => r.querySelector(".av-cx-who").textContent.trim()).length, valued: rows.filter(r => /\\d|—/.test(r.querySelector(".av-cx-val").textContent)).length,
    overlaps: marks.filter((a, i) => marks.some((b, j) => j > i && meets(a, b))).length, ticks: [...plot.querySelectorAll(".av-cx-axis .av-tick")].map(t => t.textContent) };
});
const row = document.querySelector(".av-block--shifts .av-cx-row");
point(row, "pointerover"); const card = tip(), who = row.querySelector(".av-cx-who").textContent.trim(), report = row.closest(".av-sh-row").querySelector(".av-sh-name a").textContent.trim();
const dots = [...document.querySelectorAll(".av-cg-pt")];
const spots = dots.map(d => box(d.querySelector(".av-cg-dot")));
const pt = dots[0]; if (pt) point(pt, "pointerover");
return { plots, card, who, report, points: dots.length, links: dots.filter(d => /^#report\\//.test(d.getAttribute("href"))).length, pointOverlaps: spots.filter((a, i) => spots.some((b, j) => j > i && meets(a, b))).length,
  x: [...document.querySelectorAll(".av-cg > .av-ticks .av-tick")].map(t => t.textContent), y: [...document.querySelectorAll(".av-cg-yticks span")].map(t => t.textContent), pointCard: pt ? tip() : null };
"""
        out = self.drive(page, width=1440, script=script)["result"]
        self.assertTrue(out["plots"], "no setup plot drawn")
        for plot in out["plots"]:
            self.assertGreater(plot["rows"], 1)
            self.assertEqual(plot["named"], plot["rows"], "a setup's row does not name it")
            self.assertEqual(plot["valued"], plot["rows"], "a setup's row does not say its value")
            self.assertEqual(plot["overlaps"], 0, "two setups' marks are drawn over each other")
            self.assertEqual(plot["ticks"], ["0%", "25%", "50%", "75%", "100%"], "a pass rate is not read against a labelled 0–100% axis")
        self.assertTrue(out["card"]["shown"])
        self.assertEqual(out["card"]["title"], out["who"], "a setup's card does not name the setup")
        self.assertTrue(out["card"]["over"].startswith(out["report"]), "a setup's card does not name the report it was tested in")
        self.assertIn("Pass rate", out["card"]["rows"])
        self.assertGreater(out["points"], 1, "the scatter draws no changes to spread")
        self.assertEqual(out["links"], out["points"], "a change on the scatter does not open its report")
        self.assertEqual(out["pointOverlaps"], 0, "two changes are drawn over each other")
        for axis in ("x", "y"):
            labels = out[axis]
            self.assertEqual(labels[0].lstrip("−"), labels[-1].lstrip("+"), f"the {axis} axis is not symmetric about zero: {labels}")
            self.assertTrue(all(t.strip("+−%") in ("±0", "0") or int(t.strip("+−%")) % 5 == 0 for t in labels), f"the {axis} axis has bounds that are not round: {labels}")
        self.assertTrue(out["pointCard"]["shown"] and out["pointCard"]["rows"], "a change's card is empty")
        self.assertNotIn("Cost against gain", out["pointCard"]["title"], "a change shows the chart's caption, not its own numbers")

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
        self.assertEqual(out["byTheme"], "1 of 3 reports")
        self.assertEqual(out["bySearch"], ["1 of 3 reports", ["sandwich"]])
        # Evidence: each trial holds fictional-trial.json's 96 runs, the sandwich 16 observations; ties keep their order.
        self.assertEqual(out["sortUp"], [["sandwich", "fictional", "again"], "ascending"])
        self.assertEqual(out["sortDown"], [["fictional", "again", "sandwich"], "descending"])
        self.assertEqual(out["opened"], ["#report/sandwich", True])
        self.assertEqual(out["backed"], {"hash": "#reports", "reader": False, "scroll": True, "focus": True})
        self.assertEqual(out["forwarded"], ["#report/sandwich", True])
        self.assertEqual(out["brand"], ["#report/sandwich/av-top", True])
        self.assertEqual(out["print"], ["light", "dark"])

    def test_an_unknown_report_shows_its_notice_and_closed_views_keep_no_listeners(self) -> None:
        # Every listener added from here on is recorded until it is removed, so what a closed view leaves behind shows.
        script = """
const wait = ms => new Promise(r => setTimeout(r, ms));
const live = [], add = EventTarget.prototype.addEventListener, remove = EventTarget.prototype.removeEventListener;
const capture = o => typeof o === "boolean" ? o : !!(o && o.capture);
EventTarget.prototype.addEventListener = function (type, fn, o) { live.push({ target: this, type, fn, capture: capture(o) }); return add.call(this, type, fn, o); };
EventTarget.prototype.removeEventListener = function (type, fn, o) { const i = live.findIndex(x => x.target === this && x.type === type && x.fn === fn && x.capture === capture(o)); if (i >= 0) live.splice(i, 1); return remove.call(this, type, fn, o); };
const global = () => live.filter(x => x.target === window || x.target === document).length;
const out = {}, before = global(), hosts = [];
// A stale or mistyped member address shows the notice, with the way back to the collection.
location.hash = "#report/nope"; await wait(500);
const missing = document.querySelector("[data-av-reader]");
hosts.push(missing);
out.missing = missing && { title: missing.querySelector(".av-title")?.textContent.trim(), back: !!missing.querySelector(".av-reader-bar [data-av-reader-back]"), home: document.querySelector("[data-av-report]").hidden };
for (const id of ["fictional", "again", "sandwich", "fictional"]) { location.hash = "#report/" + id; await wait(700); hosts.push(document.querySelector("[data-av-reader]")); }
location.hash = "#reports"; await wait(600);
out.open = !!document.querySelector("[data-av-reader]");
out.removed = hosts.map(h => !!h && !h.isConnected);
out.kept = hosts.map(h => h ? live.filter(x => x.target instanceof Node && h.contains(x.target)).map(x => x.type) : null);
out.global = global() - before;
return out;
"""
        out = self.drive(self.build("--collection", write_collection(self.dir)), width=1280, script=script)["result"]
        self.assertEqual(out["missing"], {"title": "Not in this collection", "back": True, "home": True}, "the notice for an unknown report")
        self.assertFalse(out["open"], "back in the collection")
        self.assertEqual(out["removed"], [True] * 5, "each view's host is removed when it closes")
        self.assertEqual(out["kept"], [[]] * 5, "a removed view keeps no listener")
        self.assertEqual(out["global"], 0, "closed views leave no listener on the window or the document")

    def test_a_late_return_never_scrolls_the_next_report_and_a_report_is_not_compared_with_itself(self) -> None:
        # A controlled scheduler: callbacks the reader queues for later run only when the script says so.
        script = """
const wait = ms => new Promise(r => setTimeout(r, ms));
const realSet = window.setTimeout.bind(window), realClear = window.clearTimeout.bind(window), held = [];
let hold = false;
window.setTimeout = (fn, ms, ...rest) => hold && !ms ? held.push(fn) : realSet(fn, ms, ...rest);
window.clearTimeout = id => { if (id > 0 && id <= held.length && hold) held[id - 1] = null; else realClear(id); };
const out = {};
location.hash = "#reports"; await wait(400);
window.scrollTo(0, 420); await wait(100);
location.hash = "#report/fictional"; await wait(700);
// Back to the collection: its scroll is restored at once and again later, after the collection's own handling of the
// address; the later one is held until the next report has opened.
hold = true; history.back(); await wait(400);
location.hash = "#report/sandwich"; await wait(700);
hold = false;
for (const fn of held.splice(0)) if (fn) fn();
await wait(100);
out.next = Math.round(window.scrollY);
// A report set beside itself: the notice says two different reports are needed.
location.hash = "#compare/fictional/fictional"; await wait(600);
const r = document.querySelector("[data-av-reader]");
out.self = r && [r.querySelector(".av-title")?.textContent.trim(), (r.querySelector(".av-block--text")?.textContent || "").replace(/\\s+/g, " ").trim()];
return out;
"""
        out = self.drive(self.build("--collection", write_collection(self.dir)), width=1280, script=script)["result"]
        self.assertEqual(out["next"], 0, "a return queued before the next report opened leaves it at its top")
        self.assertEqual(out["self"][0], "Two different reports needed")
        self.assertIn("fictional was named twice", out["self"][1])

    def test_sorting_changes_never_ranks_one_measure_against_another(self) -> None:
        # Two trials whose candidates moved the pass rate by +50 and +10 points, and a comparison whose candidate took 0.3
        # minutes longer. Sorted by size alone, 0.3 minutes would sit between the two rates; reports on one measure sort
        # together instead.
        def trial(name: str, ref: str, cand: str) -> dict:
            runs = [{"job": f"c__{arm}__r{i}", "scenario": "c", "arm": arm, "repeat": i, "status": "ok", "passed": mark == "P", "valid": True}
                    for arm, marks in (("ref", ref), ("cand", cand)) for i, mark in enumerate(marks, 1)]
            return {"name": name, "plan": {"arms": {"ref": {"executor": "command"}, "cand": {"executor": "command"}}, "scenarios": [{"name": "c", "prompt": "Do it.", "required": []}]}, "runs": runs, "baseline": "ref"}
        timed = {"alternatives": [{"id": "x"}, {"id": "y"}], "baseline": "x", "metrics": [{"id": "minutes", "kind": "numeric", "unit": "min", "better": "lower", "primary": True}],
                 "observations": [{"alternative": a, "metric": "minutes", "value": v} for a, vs in (("x", (4.0, 4.0)), ("y", (4.3, 4.3))) for v in vs]}
        files = {"big.json": trial("big", "PFFF", "PPPF"), "small.json": trial("small", "PPPPPFFFFF", "PPPPPPFFFF"), "timed.json": timed}
        for name, value in files.items():
            (self.dir / name).write_text(json.dumps(value), encoding="utf-8")
        collection = {"title": "Changes", "members": [{"id": "big", "trial": "big.json"}, {"id": "timed", "comparison": "timed.json"}, {"id": "small", "trial": "small.json"}]}
        (self.dir / "changes.json").write_text(json.dumps(collection), encoding="utf-8")
        script = """
const head = [...document.querySelectorAll(".av-rx-table thead th")].find(th => th.textContent.startsWith("Changes"));
const order = () => [...document.querySelectorAll(".av-rx-table tbody tr")].map(r => r.dataset.member);
head.querySelector("button").click(); const up = order();
head.querySelector("button").click(); const down = order();
return { up, down };
"""
        out = self.drive(self.build("--collection", self.dir / "changes.json"), width=1280, script=script)["result"]
        for order in (out["up"], out["down"]):
            self.assertEqual(abs(order.index("big") - order.index("small")), 1, f"the two pass-rate changes sort together: {order}")
        self.assertLess(out["up"].index("small"), out["up"].index("big"), "within one measure, the smaller change first when ascending")
        self.assertLess(out["down"].index("big"), out["down"].index("small"), "and the larger first when descending")

    def test_member_links_carry_their_report_address_and_ids_stay_apart(self) -> None:
        source = write_collection(self.dir)
        data = json.loads(source.read_text(encoding="utf-8"))
        data["members"][1]["models"] = ["model-x"]
        source.write_text(json.dumps(data), encoding="utf-8")
        script = """
const wait = ms => new Promise(r => setTimeout(r, ms));
const out = {};
// The model selector narrows every design to the reports that ran on that model.
const sel = document.querySelector("[data-av-rx-model]"); sel.value = "model-x"; sel.dispatchEvent(new Event("change"));
out.models = {};
for (const l of ["cards", "list", "table", "matrix"]) {
  document.querySelector(`[data-av-rx-layout="${l}"]`).click();
  out.models[l] = [...new Set([...document.querySelectorAll(`[data-av-rx-view="${l}"] [data-member]`)].filter(e => !e.closest("[hidden]") && e.getClientRects().length).map(e => e.dataset.member))];
}
document.querySelector("[data-av-rx-clear]").click();
location.hash = "#report/fictional"; await wait(400);
const reader = document.querySelector("[data-av-reader]");
out.toc = reader.querySelector(".av-toc a").getAttribute("href");
// Links the page writes while it enhances the report carry the member's address too.
out.anchor = reader.querySelector('.av-section[id$="cases"] .av-anchor').getAttribute("href");
out.skip = reader.querySelector("[data-av-skip-ledger]").getAttribute("href");
const outcome = reader.querySelector('[data-av-ledger-tools] [data-outcome="fail"]'); outcome.click(); await wait(100);
out.ledger = location.hash; reader.querySelector('[data-av-ledger-tools] [data-outcome=""]').click(); await wait(100);
out.brand = reader.querySelector(".av-brand").getAttribute("href");
const ids = [...document.querySelectorAll("[id]")].map(e => e.id);
out.duplicates = [...new Set(ids.filter((id, i) => ids.indexOf(id) !== i))];
// A closed dialog is not shown, so its label (an open run's title, written when a run opens) is not looked up yet.
out.dangling = [...reader.querySelectorAll("[aria-labelledby]")].filter(e => !e.closest("dialog:not([open])")).flatMap(e => e.getAttribute("aria-labelledby").split(" ")).filter(id => { const t = document.getElementById(id); return !t || !reader.contains(t); });
// A link opened in a new tab or copied is the browser's to follow: its address alone opens the member at the section.
const cases = reader.querySelector('.av-toc a[href$="/cases"]');
out.casesHref = cases ? cases.getAttribute("href") : null;
location.hash = "#reports"; await wait(400);
location.hash = out.casesHref; await wait(600);
const again = document.querySelector("[data-av-reader]");
const target = again && [...again.querySelectorAll(".av-section")].find(s => s.id.endsWith("cases"));
out.opened = { reader: !!again, near: !!target && Math.abs(target.getBoundingClientRect().top) < 200 };
return out;
"""
        out = self.drive(self.build("--collection", source), width=1280, script=script)["result"]
        self.assertEqual(out["models"], {"cards": ["again"], "list": ["again"], "table": ["again"], "matrix": ["again"]})
        self.assertEqual(out["toc"], "#report/fictional/story")
        self.assertEqual(out["brand"], "#report/fictional/av-top")
        self.assertEqual(out["anchor"], "#report/fictional/cases", "a section's own link")
        self.assertEqual(out["skip"], "#report/fictional/runs", "the skip link to the run ledger")
        self.assertEqual(out["ledger"], "#report/fictional/runs?outcome=fail", "a ledger view's address")
        self.assertEqual(out["duplicates"], [], "an id used twice on the page")
        self.assertEqual(out["dangling"], [], "a label reference that does not reach inside the member")
        self.assertEqual(out["casesHref"], "#report/fictional/cases")
        self.assertEqual(out["opened"], {"reader": True, "near": True})

    def test_nested_views_use_the_width_of_their_own_box(self) -> None:
        # Two reports side by side put each one's results in half the page, and the story's glossary sits in one of
        # its columns: a block must lay out for the box it is in, not for the window, or its text is crushed.
        source = write_collection(self.dir)
        data = json.loads(source.read_text(encoding="utf-8"))
        data["story"]["glossary"] = [{"term": "A term long enough to need room of its own", "meaning": "A meaning written as a whole sentence, the way a reader new to the work needs it explained, with a clause or two more."}] * 3
        source.write_text(json.dumps(data), encoding="utf-8")
        page = self.build("--collection", source)
        script = "location.hash = %s; await new Promise(r => setTimeout(r, 500)); const full = document.querySelector('[data-av-reader] details.av-rc-full'); if (full) full.open = true; await new Promise(r => setTimeout(r, 200)); return (%s)();"
        for hash in ("#story", "#compare/fictional/again"):
            for width in (1024, 1280, 1440):
                with self.subTest(view=hash, width=width):
                    out = self.drive(page, width=width, script=script % (json.dumps(hash), "() => {" + TB.CRAMPED + "}"))
                    self.assertEqual(out["result"], [], "text crushed into a column under 200 px")

    def test_report_cards_fill_their_rows_on_a_wide_screen(self) -> None:
        # A group with one report showed it as a lone 38rem card beside an empty row while other groups filled theirs.
        # Cards now share each row evenly, a lone card filling its row, and their text keeps a readable cap.
        source = write_collection(self.dir)
        page = self.dir / "collection.html"
        built = run_python(REPORT, "--collection", source, "--output", page)
        self.assertEqual(built.returncode, 0, built.stderr)
        script = """
const chOf = el => { const p = document.createElement("span"); p.textContent = "0000000000"; p.style.cssText = "position:absolute;visibility:hidden;white-space:nowrap"; el.appendChild(p); const w = p.getBoundingClientRect().width / 10; p.remove(); return w; };
return [...document.querySelectorAll(".av-rx-list")].filter(l => l.getBoundingClientRect().width).map(list => ({
  list: Math.round(list.getBoundingClientRect().width),
  cards: [...list.children].map(c => { const r = c.getBoundingClientRect(); return [Math.round(r.top), Math.round(r.width)]; }),
  headlineCaps: [...list.querySelectorAll(".av-rx-headline")].map(h => { const m = parseFloat(getComputedStyle(h).maxWidth); return Number.isFinite(m) ? Math.round(m / chOf(h) * 10) / 10 : 9999; }),
}));
"""
        groups = self.drive(page, width=1920, script=script)["result"]
        lone = [g for g in groups if len(g["cards"]) == 1]
        pair = [g for g in groups if len(g["cards"]) == 2]
        self.assertTrue(lone and pair, groups)
        self.assertGreaterEqual(lone[0]["cards"][0][1], lone[0]["list"] * 0.95, "a lone report card leaves its row empty")
        (top_a, width_a), (top_b, width_b) = pair[0]["cards"]
        self.assertEqual(top_a, top_b, "two report cards do not share a row on a wide screen")
        self.assertLessEqual(abs(width_a - width_b), 2, "two report cards in a row get different widths")
        self.assertLessEqual(max(cap for g in groups for cap in g["headlineCaps"]), 92.6, "a card's headline has no readable cap")

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
