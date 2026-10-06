"""A real browser mounts report.py output and exercises its behavior: deep
links, the run drawer, the ledger's filters, export and keyboard path,
printing and phone width. Skipped when neither google-chrome-stable nor
chromium is on PATH.

Interaction scenarios live in enhance-browser.js; each runs inside the page
as a data: script (the only kind the report's CSP allows) and writes JSON
that Chrome's --dump-dom returns."""
from __future__ import annotations

import base64
import html
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import unittest

from visual_harness import EXAMPLES, NODE, REPORT, TESTS, Scratch, run_python, write_hostile_fixtures

BROWSER = next((path for path in map(shutil.which, ("google-chrome-stable", "chromium", "chromium-browser")) if path), None)
SCENARIOS = TESTS / "enhance-browser.js"
DRIVER = TESTS / "browser-drive.cjs"
# Elements wider than the window that no scrolling ancestor contains: what
# makes a page scroll sideways.
OVERFLOW = """
const vw = innerWidth, out = [];
const contained = el => { for (let p = el.parentElement; p; p = p.parentElement) { const o = getComputedStyle(p).overflowX; if ((o === "auto" || o === "scroll" || o === "hidden" || o === "clip") && p.getBoundingClientRect().right <= vw + 1) return true; } return false; };
for (const el of document.querySelectorAll(".av-report *")) { const r = el.getBoundingClientRect(); if (r.width && r.right > vw + 1 && !contained(el)) out.push(el.tagName.toLowerCase() + "." + String(el.className).split(" ")[0] + " right=" + Math.round(r.right)); }
return { scrollWidth: document.documentElement.scrollWidth, innerWidth: vw, offenders: out.slice(0, 8) };
"""
HOSTILE = '"\'><x-hostile id="h-browser">'


def kinds_trial(*, invalid: bool, hostile: bool = False) -> dict:
    """Two arms, two cases, three repeats: a required check that fails with a
    recorded detail, a judge failure, passes and (optionally) one timeout."""
    mark = HOSTILE if hostile else ""
    budget_check = f"within_budget{mark}"
    runs = []
    for case in ("budget", "reply"):
        for arm in ("a", "b"):
            for repeat in (1, 2, 3):
                run = {
                    "job": f"{case}__{arm}__r{repeat}{mark}", "scenario": case, "arm": arm, "repeat": repeat, "status": "ok",
                    "passed": True, "valid": True, "invalid_reason": None, "commands": 3 + repeat,
                    "seconds": 20.0 + repeat * 7 + (5 if arm == "b" else 0), "setup_seconds": 0.4, "checks_seconds": 0.2,
                    "usage": {"output_tokens": 200 + 40 * repeat, "input_tokens": 900}, "final_message_excerpt": f"Output {mark}{case} {arm} {repeat}.",
                }
                if case == "budget":
                    run["checks"] = {"results_correct": True, budget_check: True, "problems": "-"}
                    if arm == "a" and repeat == 1:
                        run["passed"] = False
                        run["checks"] = {"results_correct": True, budget_check: False, "problems": f"pricing-down: median 0.650 s, limit 0.400 s{mark}"}
                else:
                    run["checks"] = {"reply_written": True}
                    run["judge"] = {"verdict": "pass", "reason": f"Faithful {mark}reply."}
                    run["judge_seconds"] = 2.0
                    if arm == "a" and repeat == 2:
                        run["passed"] = False
                        run["judge"] = {"verdict": "fail", "reason": f"Invents a detail {mark}the source lacks."}
                    if invalid and arm == "b" and repeat == 3:
                        run.update(passed=None, valid=False, status="timeout", invalid_reason="timeout", checks={}, judge=None)
                runs.append(run)
    return {
        "name": f"kinds{mark}", "run_directory": "trials/kinds",
        "plan": {
            "arms": {"a": {"executor": "command", "model": "fictional"}, "b": {"executor": "command", "model": "fictional"}},
            "scenarios": [
                {"name": "budget", "prompt": "Make the page fast.", "required": ["results_correct", budget_check]},
                {"name": "reply", "prompt": "Reply to the note.", "judge": {"question": "Is the reply faithful?"}, "required": ["reply_written"]},
            ],
            "judge": {"executor": "command", "model": "fictional-judge"},
        },
        "runs": runs,
    }


@unittest.skipUnless(BROWSER, "google-chrome-stable or chromium is not on PATH")
class BrowserRenderTest(unittest.TestCase):
    """Headless rendering of an assembled report, read back with --dump-dom."""

    def setUp(self) -> None:
        self._scratch = Scratch()
        self.dir = self._scratch.__enter__()

    def tearDown(self) -> None:
        self._scratch.__exit__(None, None, None)

    def build(self, *report_args: object) -> Path:
        page = self.dir / "report.html"
        built = run_python(REPORT, *report_args, "--output", page, "--replace")
        self.assertEqual(built.returncode, 0, built.stderr)
        return page

    def browse(self, page: Path, *, fragment: str = "", width: int = 1360, budget: int = 8000) -> str:
        command = [BROWSER, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check", "--disable-extensions", "--hide-scrollbars",
                   f"--user-data-dir={self.dir / 'profile'}", f"--window-size={width},900", f"--virtual-time-budget={budget}", "--dump-dom", page.as_uri() + fragment]
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            command.insert(1, "--no-sandbox")  # Chrome refuses to run its sandbox as root, as in some CI containers
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=60)
        except subprocess.TimeoutExpired:
            self.fail("the browser did not finish within 60 seconds")
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])
        self.assertIn("</html>", result.stdout, "the browser printed no document")
        return result.stdout

    def dump(self, *report_args: object, budget: int = 8000) -> str:
        return self.browse(self.build(*report_args), budget=budget)

    def trial_file(self, data: dict) -> Path:
        path = self.dir / "trial.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def scenario(self, name: str, *report_args: object, fragment: str = "", width: int = 1360) -> dict:
        """Run one scenario of enhance-browser.js inside the assembled report."""
        page = self.build(*report_args)
        script = f"const SCENARIO = {json.dumps(name)};\n" + SCENARIOS.read_text(encoding="utf-8")
        tag = f'<script src="data:text/javascript;base64,{base64.b64encode(script.encode()).decode()}"></script>'
        document = page.read_text(encoding="utf-8")
        self.assertIn("</body>", document)
        page.write_text(document.replace("</body>", tag + "</body>", 1), encoding="utf-8")
        dom = self.browse(page, fragment=fragment, width=width, budget=12000)
        found = re.search(r'<pre id="av-test-out">(.*?)</pre>', dom, re.S)
        self.assertIsNotNone(found, "the scenario wrote no result")
        result = json.loads(html.unescape(found.group(1)))
        self.assertNotIn("error", result, result.get("error"))
        return result

    # ------------------------------------------------------------ mounting

    def test_trial_report_mounts_with_hostile_text_kept_as_text(self) -> None:
        fixtures = write_hostile_fixtures(self.dir / "fixtures")
        dom = self.dump("--trial", fixtures["trial"], "--narrative", fixtures["narrative"])
        self.assertIn("data-av-mounted", dom)
        self.assertRegex(dom, r'<div class="av-report" data-av-report="" data-av-ready="')
        ids = re.findall(r'<section class="av-section" id="([^"]+)"', dom)
        self.assertIn("verdict", ids)
        self.assertIn("runs", ids)
        toc = re.search(r'<nav class="av-toc".*?</nav>', dom, re.S)
        self.assertIsNotNone(toc, "the report has no section index")
        for target in re.findall(r'href="#([^"]+)"', toc.group(0)):
            self.assertIn(html.unescape(target), ids, "a section index entry points nowhere")
        self.assertNotIn("could not render", dom)
        self.assertNotIn("<x-hostile", dom, "supplied text became an element in the browser")
        self.assertIn("&lt;x-hostile", dom, "the supplied text is not visible")

    def test_showcase_draws_its_diagram(self) -> None:
        dom = self.dump("--spec", EXAMPLES / "showcase-spec.json", budget=15000)
        self.assertRegex(dom, r'data-av-ready="')
        self.assertIn('data-av-mermaid-state="ready"', dom)
        self.assertIn("data-av-mermaid-scene", dom)
        self.assertNotIn("av-block-error", dom)

    # ------------------------------------------------------------ deep links

    def test_run_link_opens_the_drawer_and_closing_clears_it(self) -> None:
        trial = self.trial_file(kinds_trial(invalid=True))
        result = self.scenario("deep-run", "--trial", trial, fragment="#run-1")
        self.assertTrue(result["open"], "#run-1 did not open the drawer")
        self.assertIn("Run 1 of 12", result["head"])
        self.assertEqual(result["title"], "budget")
        self.assertEqual(result["hash"], "#run-1")
        self.assertTrue(result["copyLink"], "the drawer has no copy-link control")
        self.assertIn("within_budget", result["why"], "the cause line does not name the failed check")
        self.assertIn("pricing-down", result["why"], "the cause line does not carry the recorded detail")
        self.assertTrue(result["focusInDrawer"])
        self.assertIn("Run 2 of 12", result["afterNext"]["head"], "the right arrow did not move to the next run")
        self.assertEqual(result["afterNext"]["hash"], "#run-2", "the address does not follow the drawer")
        self.assertIn("Run 2 of 12", result["afterNext"]["live"], "the move was not announced")
        self.assertTrue(result["focusOnNext"], "focus left the Next button after it was used")
        self.assertTrue(result["closed"])
        self.assertEqual(result["hashAfterClose"], "", "closing a linked run left its link in the address")

    def test_section_link_lands_at_once_and_takes_focus(self) -> None:
        trial = self.trial_file(kinds_trial(invalid=True))
        result = self.scenario("deep-section", "--trial", trial, fragment="#runs")
        self.assertEqual(result["id"], "runs")
        self.assertTrue(result["focused"], "the linked section's heading did not take focus")
        self.assertTrue(result["scrolled"])
        self.assertLess(abs(result["top"]), 160, "the linked section is not at the top of the window")

    def test_ledger_view_link_restores_its_filters(self) -> None:
        trial = self.trial_file(kinds_trial(invalid=True))
        result = self.scenario("deep-filters", "--trial", trial, fragment="#runs?outcome=fail&q=budget")
        self.assertEqual(result["pressed"], ["fail"])
        self.assertEqual(result["search"], "budget")
        self.assertEqual(len(result["rows"]), 1, result["count"])
        self.assertEqual(result["rows"][0]["outcome"], "fail")
        self.assertIn("1 of 12 runs", result["count"])

    # ------------------------------------------------------------ ledger

    def test_ledger_filters_empty_view_rows_and_sorting(self) -> None:
        trial = self.trial_file(kinds_trial(invalid=False))
        result = self.scenario("ledger", "--trial", trial)
        self.assertEqual(result["total"], 12)
        self.assertTrue(result["invalidDisabled"], "an outcome with no runs can still be chosen")
        self.assertTrue(result["clearHiddenAtStart"])
        self.assertEqual(result["tabbableRows"], 1, "ledger rows are not a single tab stop")
        self.assertEqual(result["failRows"], ["fail", "fail"])
        self.assertEqual(result["hashAfterFail"], "#runs?outcome=fail")
        self.assertTrue(result["clearShownWhenFiltered"])
        self.assertIn("2 of 12 runs shown", result["liveAfterFail"], "the filtered count was not announced")
        self.assertTrue(result["emptyShown"], "a filter matching nothing left a bare table")
        self.assertIn("No runs match these filters", result["emptyText"])
        self.assertEqual(result["afterClear"], {"rows": 12, "hash": "#runs", "search": "", "emptyHidden": True})
        self.assertTrue(result["arrowMoved"], "the down arrow did not move to the next row")
        self.assertEqual(result["tabbableAfterMove"], 1)
        self.assertTrue(result["describedBy"], "rows do not say how to open them")
        self.assertTrue(result["enterOpened"], "Enter on a row did not open its record")
        self.assertTrue(result["sortedDescending"])
        self.assertRegex(result["sortSelect"], r"^\d+:descending$", "the sort select does not follow header sorting")
        self.assertTrue(result["slashFocusedSearch"], '"/" did not go to the ledger search')

    def test_export_saves_the_shown_runs_and_the_trial(self) -> None:
        data = kinds_trial(invalid=False)
        trial = self.trial_file(data)
        result = self.scenario("export", "--trial", trial)
        self.assertEqual(result["names"], ["kinds-runs.csv", "kinds-trial.json"])
        self.assertEqual(result["csvType"], "text/csv;charset=utf-8")
        self.assertEqual(len(result["csvLines"]), result["shownRuns"] + 1, "the CSV does not hold exactly the runs shown")
        self.assertTrue(result["csvLines"][0].startswith("n,job,case,case_label,arm,arm_label,repeat,outcome,cause"))
        self.assertTrue(all(",fail," in line for line in result["csvLines"][1:]), "the CSV ignored the outcome filter")
        self.assertEqual(result["jsonRuns"], len(data["runs"]))
        self.assertIn("kinds-trial.json", result["status"])
        self.assertIn("block downloads", result["status"], "the status does not say what to do when downloads are blocked")
        self.assertEqual(result["label"], "the 2 runs shown")
        self.assertTrue(result["footerButton"])

    # ------------------------------------------------------------ keyboard, print, phone

    def test_keyboard_path_tooltips_and_section_links(self) -> None:
        result = self.scenario("keyboard", "--trial", EXAMPLES / "fictional-trial.json", "--narrative", EXAMPLES / "fictional-narrative.json")
        # One link control per section is a deliberate stop (it names the section
        # it links); every other control counts against the budget.
        self.assertLess(result["tabStops"] - result["sections"], 60, "reaching the ledger takes too many Tab presses")
        self.assertGreater(result["marks"], 20)
        self.assertEqual(result["markStops"], 1, "a case dossier's runs are not a single tab stop")
        self.assertEqual(result["titles"], 0, "run marks keep a native title beside the styled tooltip")
        self.assertTrue(result["tip"]["shown"])
        self.assertEqual(result["tip"]["text"], result["tip"]["label"], "the tooltip and the accessible name differ")
        self.assertTrue(result["rightMoved"])
        self.assertTrue(result["stopFollows"], "the tab stop did not follow the focused mark")
        self.assertTrue(result["downRow"], "the down arrow did not reach the next row")
        self.assertTrue(result["endIsLast"])
        self.assertTrue(result["homeIsFirst"])
        self.assertTrue(result["opened"])
        self.assertRegex(result["hashOpen"], r"^#run-\d+$")
        self.assertTrue(result["tipHiddenWhenOpen"])
        self.assertTrue(result["focusReturned"], "closing the drawer did not return focus to the mark")
        self.assertEqual(result["hashClosed"], "")
        self.assertTrue(result["anchors"], "a section has no link control")
        self.assertEqual(result["skipLedger"], "#runs")

    def test_print_opens_folded_detail_in_the_light_theme(self) -> None:
        result = self.scenario("print", "--trial", EXAMPLES / "fictional-trial.json", "--narrative", EXAMPLES / "fictional-narrative.json")
        self.assertIsNotNone(result["tone"]["callout"], "the fictional narrative has no limit callout to check")
        self.assertEqual(result["tone"]["callout"], result["tone"]["warn"], "a limit callout is not drawn in the warning color")
        self.assertGreater(result["closedBefore"], 0)
        self.assertEqual(result["during"], {"theme": "light", "closed": 0})
        self.assertEqual(result["after"], {"theme": None, "closed": result["closedBefore"]})

    def drive(self, page: Path, *, width: int, script: str = "return null;", tab_to: str | None = None) -> dict:
        """Run browser-drive.cjs: an exact viewport and real key presses over the DevTools protocol."""
        if not NODE:
            self.skipTest("node is not on PATH")
        script_file = self.dir / "drive-script.js"
        script_file.write_text(script, encoding="utf-8")
        command = [NODE, DRIVER, "--chrome", BROWSER, "--profile", self.dir / "drive-profile", "--url", page.as_uri(), "--width", str(width), "--script", script_file]
        if tab_to:
            command += ["--tab-to", tab_to]
        result = subprocess.run(list(map(str, command)), capture_output=True, text=True, timeout=180)
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])
        lines = result.stdout.strip().splitlines()
        self.assertTrue(lines, f"the driver printed nothing: {result.stderr[-2000:]}")
        out = json.loads(lines[-1])
        if "skip" in out:
            self.skipTest(out["skip"])
        self.assertNotIn("error", out, out.get("error"))
        self.assertEqual(out["width"], width, "the viewport was not emulated")
        return out

    def test_phone_width_never_scrolls_the_page_sideways(self) -> None:
        reports = {
            "fictional": ("--trial", EXAMPLES / "fictional-trial.json", "--narrative", EXAMPLES / "fictional-narrative.json"),
            "kinds": ("--trial", self.trial_file(kinds_trial(invalid=True))),
            "showcase": ("--spec", EXAMPLES / "showcase-spec.json"),
        }
        for name, args in reports.items():
            with self.subTest(report=name):
                result = self.drive(self.build(*args), width=390, script=OVERFLOW)["result"]
                self.assertEqual(result["offenders"], [], "content wider than a 390 px phone outside any scrolling container")
                self.assertLessEqual(result["scrollWidth"], result["innerWidth"], "the page scrolls sideways at 390 px")

    def test_phone_ledger_shows_the_first_runs_until_asked_for_all(self) -> None:
        page = self.build("--trial", EXAMPLES / "fictional-trial.json", "--narrative", EXAMPLES / "fictional-narrative.json")
        script = (
            'const shown = () => [...document.querySelectorAll("table.av-ledger tbody tr[data-run]")].filter(r => r.getClientRects().length).length;'
            'const more = document.querySelector("[data-av-more]"); const before = shown(), label = more ? more.textContent : null, visible = !!more && more.getClientRects().length > 0;'
            'if (more) more.click(); await new Promise(r => setTimeout(r, 50));'
            'return { before, label, visible, after: shown(), hiddenAfter: !!more && more.hidden };'
        )
        phone = self.drive(page, width=390, script=script)["result"]
        self.assertEqual(phone["before"], 20, "a phone lists more than the first 20 runs before asked")
        self.assertTrue(phone["visible"])
        self.assertEqual(phone["label"], "Show all 96 runs")
        self.assertEqual(phone["after"], 96)
        self.assertTrue(phone["hiddenAfter"], "the control stays after every run is shown")
        wide = self.drive(page, width=1360, script=script)["result"]
        self.assertEqual(wide["before"], 96, "a wide screen clips the ledger, which scrolls in its own frame there")
        self.assertFalse(wide["visible"])

    def test_real_tab_presses_reach_the_ledger_search_quickly(self) -> None:
        page = self.build("--trial", EXAMPLES / "fictional-trial.json", "--narrative", EXAMPLES / "fictional-narrative.json")
        script = 'return document.querySelectorAll(".av-section[id]").length;'
        out = self.drive(page, width=1360, script=script, tab_to='[data-av-ledger-tools] [data-filter="text"]')
        self.assertIsNotNone(out["tabs"], "Tab never reached the ledger search")
        # One link control per section is a deliberate stop; everything else counts.
        self.assertLess(out["tabs"] - out["result"], 60, f"{out['tabs']} Tab presses to reach the ledger search")

    def test_every_run_link_opens_with_hostile_text_kept_as_text(self) -> None:
        trial = self.trial_file(kinds_trial(invalid=True, hostile=True))
        result = self.scenario("drawers", "--trial", trial)
        self.assertEqual(result["runs"], 12)
        for i, seen in enumerate(result["seen"], start=1):
            with self.subTest(run=i):
                self.assertTrue(seen["open"])
                self.assertIn(f"Run {i} of 12", seen["head"])
                self.assertEqual(seen["hostile"], 0, "supplied text became an element")
        whys = [s["why"] for s in result["seen"] if s["why"]]
        self.assertEqual(len(whys), 3, "a failed or invalid run has no cause line")
        self.assertTrue(any(HOSTILE in why for why in whys), "the hostile check name is not visible as text")


if __name__ == "__main__":
    unittest.main()
