"""A real browser mounts report.py output and exercises its behavior: deep
links, the run drawer, the ledger's filters, export and keyboard path,
printing and phone width. Skipped when no Chromium-family browser (Chrome,
Chromium, Edge or Brave) is on PATH.

Interaction scenarios live in enhance-browser.js; each runs inside the page
as a data: script (the only kind the report's CSP allows) and writes JSON
that Chrome's --dump-dom returns."""
from __future__ import annotations

import base64
import contextlib
import html
import json
import os
from pathlib import Path
import re
import shutil
import shlex
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest

from visual_harness import EXAMPLES, NODE, REPORT, TESTS, Scratch, fetcher_leftovers, no_fetcher_leftovers, remove_singleton, run_python, singleton_folder, sweep_fetcher_leftovers, write_hostile_fixtures

# The first Chromium-family browser on PATH; these tests need its headless
# --dump-dom and DevTools protocol.
BROWSER = next((path for path in map(shutil.which, ("google-chrome-stable", "google-chrome", "chromium", "chromium-browser", "microsoft-edge-stable", "microsoft-edge", "brave-browser")) if path), None)
NO_BROWSER = "no Chromium-family browser (Chrome, Chromium, Edge or Brave) is on PATH"

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
# Text crushed into a narrow column: an element whose own text (over 40 characters) wraps to four or more lines
# in a box under 200 pixels wide, as the decision rule's evidence once did beside a wide verdict.
CRAMPED = """
const out = [];
for (const el of document.querySelectorAll(".av-report *")) {
  if (el.closest("[hidden], details:not([open]), svg, .av-sr, dialog:not([open])")) continue;
  const own = [...el.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent).join("").replace(/\\s+/g, " ").trim();
  if (own.length <= 40) continue;
  const style = getComputedStyle(el), rect = el.getBoundingClientRect();
  if (style.display === "none" || !rect.width) continue;
  const lines = Math.round(rect.height / (parseFloat(style.lineHeight) || parseFloat(style.fontSize) * 1.3));
  if (lines >= 4 && rect.width < 200) out.push(el.tagName.toLowerCase() + "." + String(el.className).split(" ")[0] + " " + Math.round(rect.width) + "px, " + lines + " lines: " + own.slice(0, 40));
}
return out.slice(0, 8);
"""

# Content of a checks table's row head or corner heading that runs past its cell's right edge: a chip, which cannot wrap,
# spilling into the first arm's cell under the sticky row head.
SPILL = """
const out = [];
const tables = [...document.querySelectorAll(".av-heatmap")].filter(t => t.getBoundingClientRect().width);
for (const t of tables) for (const cell of t.querySelectorAll("tbody th, thead th:first-child")) {
  if (cell.colSpan > 1) continue;
  const edge = cell.getBoundingClientRect().right;
  for (const el of cell.querySelectorAll("*")) {
    const r = el.getBoundingClientRect();
    if (r.width && r.right > edge + 0.5) out.push(String(el.className || el.tagName.toLowerCase()).split(" ")[0] + ' "' + el.textContent.trim().slice(0, 30) + '" ends ' + Math.round(r.right - edge) + " px past its cell");
  }
}
return { chips: [...document.querySelectorAll(".av-heatmap .av-chip--req")].map(c => c.textContent), variants: [...new Set(tables.map(t => t.className))].sort(), spills: [...new Set(out)].slice(0, 8) };
"""
# Each value in a checks table's arm cells, scrolled so that it starts at the sticky name column's edge: a value that
# still runs under that column or past the box's right edge can never be read in full, even by scrolling.
READABLE = """
const out = []; let cells = 0, scrolled = 0;
const textBox = td => {
  let left = Infinity, right = -Infinity;
  const walk = document.createTreeWalker(td, NodeFilter.SHOW_TEXT);
  for (let n; (n = walk.nextNode());) {
    if (!n.textContent.trim() || n.parentElement.closest("[aria-hidden]")) continue;
    const range = document.createRange(); range.selectNodeContents(n);
    const r = range.getBoundingClientRect();
    if (r.width) { left = Math.min(left, r.left); right = Math.max(right, r.right); }
  }
  return left < right ? { left, right } : null;
};
for (const table of [...document.querySelectorAll(".av-heatmap")].filter(t => t.getBoundingClientRect().width)) {
  const box = table.closest(".av-scroll-x");
  for (const row of table.querySelectorAll("tbody tr")) {
    const head = row.querySelector("th");
    if (!head || head.colSpan > 1) continue;
    for (const td of row.querySelectorAll("td")) {
      if (td.colSpan > 1 || !textBox(td)) continue;
      box.scrollTo({ left: box.scrollLeft + textBox(td).left - head.getBoundingClientRect().right, behavior: "instant" });
      cells++; scrolled = Math.max(scrolled, box.scrollLeft);
      const v = textBox(td), h = head.getBoundingClientRect(), b = box.getBoundingClientRect();
      if (v.left < h.right - 0.5 || v.right > b.right + 0.5) out.push('"' + td.textContent.trim() + '" beside ' + head.textContent.trim().slice(0, 30) + ": " + Math.round(v.right - v.left) + " px of value, " + Math.round(b.right - h.right) + " px beside the sticky column");
    }
    box.scrollTo({ left: 0, behavior: "instant" });
  }
}
return { cells, scrolled: Math.round(scrolled), hidden: [...new Set(out)].slice(0, 8) };
"""

# What the owner asked of every chart, everywhere: "why do none of the X-Axis have any markings anywhere?" (an axis with
# ticks and labels on every track chart), "Why doesn't hovering over these things reveal any info" (a card on every
# mark), "also found text going out of bounds" (no text cut off, run past its view or the page, or broken inside a word
# of a name), on every device. Each list names what breaks the rule.
AUDIT = """
const out = { sideways: 0, cut: [], broken: [], noAxis: [], noCard: [] };
const shown = e => { const r = e.getBoundingClientRect(); if (!r.width || !r.height) return false; for (let x = e; x; x = x.parentElement) { const cs = getComputedStyle(x); if (cs.display === "none" || cs.visibility === "hidden") return false; if (x !== e && x.tagName === "DETAILS" && !x.open && ![...x.children].some(c => c.tagName === "SUMMARY" && c.contains(e))) return false; } return true; };
const name = e => String(e.className.baseVal ?? e.className).split(" ")[0] + ' "' + (e.textContent || "").trim().slice(0, 40) + '"';
const ownText = e => [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
out.sideways = Math.max(0, document.documentElement.scrollWidth - innerWidth);
for (const e of document.querySelectorAll(".av-report *")) {
  if (!ownText(e) || e.closest(".av-sr, .av-tip, [class$='-sr'], [class*='-sr ']") || e.getBoundingClientRect().width <= 1) continue;
  const cs = getComputedStyle(e);
  if (!(cs.overflowX === "hidden" || cs.overflowX === "clip" || cs.textOverflow === "ellipsis") || e.scrollWidth <= e.clientWidth + 1 || !shown(e)) continue;
  const box = e.getBoundingClientRect(), r = document.createRange(); r.selectNodeContents(e);
  if ([...r.getClientRects()].some(q => q.width > 0 && q.right > box.right + 1)) out.cut.push(name(e));
}
for (const b of document.querySelectorAll(".av-block")) {
  const edge = b.getBoundingClientRect().right;
  for (const e of b.querySelectorAll("span, p, a, b, strong, code, dd, dt, li, h3, h4")) {
    if (!ownText(e) || e.closest(".av-scroll-x, .av-plot-scroll, .av-tip, [hidden]")) continue;
    if (e.getBoundingClientRect().right > edge + 2 && shown(e)) out.cut.push("past its view: " + name(e));
  }
}
for (const e of document.querySelectorAll(".av-arm-label, .av-contrast-side-label, .av-cx-who > span, .av-dec-name, .av-dec-word, .av-cx-stamp-word, .av-mu-title, .av-cmp-mini-name, .av-tick, .av-axis-title, .av-ladder-case, .av-duel-label, .av-bar-label")) {
  const t = e.firstChild; if (!t || t.nodeType !== 3 || !shown(e)) continue;
  for (const m of t.textContent.matchAll(/[A-Za-z][A-Za-z'’]{3,}/g)) { const r = document.createRange(); r.setStart(t, m.index); r.setEnd(t, m.index + m[0].length); if (new Set([...r.getClientRects()].filter(q => q.width > 0).map(q => Math.round(q.top))).size > 1) { out.broken.push(name(e) + " at " + m[0]); break; } }
}
for (const sel of [".av-cx-lanes", ".av-contrast-grid", ".av-ladder-grid", ".av-cs-ix", ".av-cs-arms", ".av-strip-panel", ".av-duel", ".av-bars", ".av-cmp-grid", ".av-cmp-dgrid", ".av-cmp-panel", ".av-rc-slope", ".av-cg", ".av-jv-track-wrap"])
  for (const c of document.querySelectorAll(sel)) if (shown(c) && [...c.querySelectorAll(".av-ticks .av-tick")].filter(shown).length < 2 && !c.querySelector(".av-cg-yticks span")) out.noAxis.push(sel);
for (const m of document.querySelectorAll(".av-pt, .av-cx-pt, .av-dot, .av-run, .av-cg-dot, .av-duel-seg, .av-bar-seg, .av-cmp-lk-seg, .av-svg-hit, .av-cs-dot, .av-cmp-bub, .av-cmp-dot, .av-cmp-med, .av-rc-mark, .av-share, .av-contrast-pt"))
  if (shown(m) && !m.closest("[data-av-tip]")) out.noCard.push(String(m.className).split(" ")[0] + " in " + String(m.parentElement.className).split(" ")[0]);
// A mark that stands for one thing (a run, an observation, a segment, a point) has a card of its own, and a pointer at its
// middle finds that card rather than a summary's laid over it: checked for the first marks of each kind.
const OWN = ".av-dot, .av-run, .av-cg-dot, .av-duel-seg, .av-bar-seg, .av-cmp-lk-seg, .av-svg-hit, .av-cs-dot, .av-cmp-bub, .av-cmp-dot, .av-cmp-med, .av-rc-mark";
const own = m => m.matches(".av-cg-dot") ? m.parentElement : m;
const kinds = new Map();
for (const m of document.querySelectorAll(OWN)) { const k = String(m.className.baseVal ?? m.className).split(" ")[0]; if (!kinds.has(k)) kinds.set(k, []); if (kinds.get(k).length < 12 && shown(m)) kinds.get(k).push(m); }
for (const [k, marks] of kinds) for (const m of marks) {
  if (!own(m).hasAttribute("data-av-tip")) { out.noCard.push(k + " has no card of its own"); break; }
  m.scrollIntoView({ block: "center", behavior: "instant" });
  // Somewhere on the mark (its middle, or to either side, above or below it, reaching just past a small mark into the
  // hover area it is given) a pointer finds the mark's own card, not another's.
  const r = m.getBoundingClientRect(), cx = r.left + r.width / 2, cy = r.top + r.height / 2;
  const ox = Math.max(r.width * .3, Math.min(4, r.width / 2 + 2)), oy = Math.max(r.height * .3, Math.min(4, r.height / 2 + 2));
  const finds = [[0, 0], [-ox, 0], [ox, 0], [0, -oy], [0, oy]].map(([x, y]) => document.elementFromPoint(cx + x, cy + y)?.closest("[data-av-tip]"));
  // In a dense cloud one observation may lie on another: a pointer there still finds an observation, never another kind.
  if (!finds.some(f => f && (f === own(m) || f.matches("." + k) || (k === "av-cg-dot" && f.matches(".av-cg-pt"))))) { const f = finds[0]; out.noCard.push(k + " is covered by " + (f ? String(f.className.baseVal ?? f.className).split(" ")[0] : "nothing")); break; }
}
for (const k of ["cut", "broken", "noAxis", "noCard"]) out[k] = [...new Set(out[k])].slice(0, 8);
return out;
"""
# A mark's card: shown or not, and what it says.
# How a page sets its reading on a wide screen, measured from what is drawn: a block paragraph or list entry drawn in more
# than one column ("split"), a paragraph whose lines pass 95 of its own characters ("long"), a row of blocks whose last
# row leaves most of its container empty ("stranded"), and a list of entries kept in one column although it has room for
# two ("narrowList"), and text set in columns that stands taller than it would in one column at the reading measure
# ("tall"), a nested group of alternatives that does not take its list's row ("squeezed"), and a chart's axis title
# narrowed off its plot ("offCenter"); "counted" shows the checks had something to measure.
LAYOUT = """
const chOf = el => { const p = document.createElement("span"); p.textContent = "0000000000"; p.style.cssText = "position:absolute;visibility:hidden;white-space:nowrap"; el.appendChild(p); const w = p.getBoundingClientRect().width / 10; p.remove(); return w; };
const shown = el => el.getClientRects().length > 0 && el.getBoundingClientRect().width > 0;
const name = el => `${el.className}: ${el.textContent.trim().slice(0, 50)}`;
const out = { split: [], long: [], stranded: [], narrowList: [], tall: [], squeezed: [], offCenter: [], counted: { text: 0, rows: 0, lists: 0, groups: 0, axes: 0 } };
for (const g of document.querySelectorAll(".av-alt-group")) { if (!shown(g)) continue; out.counted.groups++; if (g.getBoundingClientRect().width < g.parentElement.clientWidth * 0.95) out.squeezed.push(name(g)); }
for (const a of document.querySelectorAll(".av-axis-title")) { if (!shown(a)) continue; out.counted.axes++; if (getComputedStyle(a).maxWidth !== "none") out.offCenter.push(name(a)); }
for (const el of document.querySelectorAll(".av-flow")) {
  if (!shown(el) || getComputedStyle(el).columnWidth === "auto") continue;
  const set = el.getBoundingClientRect().height; el.style.columnWidth = "auto"; el.style.maxWidth = "var(--av-measure)";
  const one = el.getBoundingClientRect().height; el.style.columnWidth = el.style.maxWidth = "";
  if (set > one * 1.02) out.tall.push(`${Math.round(set)} over ${Math.round(one)}px ${name(el)}`);
}
for (const el of document.querySelectorAll(".av-flow > p, .av-story-list > div"))
  if (shown(el) && getComputedStyle(el).display !== "inline" && el.getClientRects().length > 1) out.split.push(name(el));
for (const el of document.querySelectorAll("p, blockquote, figcaption, figcaption > *")) {
  if (!shown(el) || getComputedStyle(el).display === "inline") continue;
  out.counted.text++;
  const ch = chOf(el), range = document.createRange(); range.selectNodeContents(el);
  // A drawn line is the run of text boxes sharing a top; boxes farther apart than two characters sit in other columns.
  const lines = new Map();
  for (const q of range.getClientRects()) if (q.width) { const k = Math.round(q.top / 2); (lines.get(k) || lines.set(k, []).get(k)).push([q.left, q.right]); }
  let widest = 0;
  for (const spans of lines.values()) {
    spans.sort((a, b) => a[0] - b[0]); let [a, b] = spans[0];
    for (const [l, r] of spans.slice(1)) { if (l <= b + 2 * ch) b = Math.max(b, r); else { widest = Math.max(widest, b - a); [a, b] = [l, r]; } }
    widest = Math.max(widest, b - a);
  }
  if (widest / ch > 95) out.long.push(`${Math.round(widest / ch)}ch ${name(el)}`);
}
for (const box of document.querySelectorAll(".av-story, .av-story-scope, .av-verdict-lists, .av-inv, .av-quotes, .av-cs-cols, .av-rx-list, .av-mu, .av-rc-cols, .av-alt-list, .av-mention-list")) {
  const kids = [...box.children].filter(shown); if (!shown(box) || kids.length < 2) continue;
  out.counted.rows++;
  const last = Math.max(...kids.map(k => Math.round(k.getBoundingClientRect().top)));
  const row = kids.filter(k => Math.abs(Math.round(k.getBoundingClientRect().top) - last) <= 2);
  const span = Math.max(...row.map(k => k.getBoundingClientRect().right)) - Math.min(...row.map(k => k.getBoundingClientRect().left));
  if (span < box.clientWidth * 0.9) out.stranded.push(`${Math.round(span)} of ${box.clientWidth}px ${name(box)}`);
}
const rem = parseFloat(getComputedStyle(document.documentElement).fontSize);
for (const list of document.querySelectorAll(".av-story-list")) {
  const entries = [...list.children].filter(shown); if (!shown(list) || entries.length < 2) continue;
  out.counted.lists++;
  if (list.clientWidth >= 2 * 26 * rem + 36 && new Set(entries.map(e => Math.round(e.getBoundingClientRect().left))).size < 2) out.narrowList.push(name(list));
}
return out;
"""

CARD = """
const tip = () => { const t = document.querySelector(".av-tip"); return { shown: t.hasAttribute("data-show"), over: t.querySelector(".av-tip-over")?.textContent || "", title: t.querySelector(".av-tip-title")?.textContent || "", rows: [...t.querySelectorAll(".av-tip-rows dt")].map(d => d.textContent), mark: !!t.querySelector(".av-tip-head .av-glyph") }; };
const point = (el, type, pointerType = "mouse") => { el.scrollIntoView({ block: "center", behavior: "instant" }); el.dispatchEvent(new PointerEvent(type, { bubbles: true, pointerType })); };
"""

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


@unittest.skipUnless(BROWSER, NO_BROWSER)
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

    def browse(self, page: Path, *, fragment: str = "", width: int = 1360, budget: int = 8000, timeout: int = 60) -> str:
        profile = self.dir / "profile"
        command = [BROWSER, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check", "--disable-extensions", "--hide-scrollbars",
                   f"--user-data-dir={profile}", f"--window-size={width},900", f"--virtual-time-budget={budget}", "--dump-dom", page.as_uri() + fragment]
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            command.insert(1, "--no-sandbox")  # Chrome refuses to run its sandbox as root, as in some CI containers
        before = singleton_folder(profile)
        with no_fetcher_leftovers(), subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True) as process:
            try:
                stdout, stderr = process.communicate(timeout=timeout)
            except BaseException as error:  # a timeout or Ctrl-C; a --dump-dom browser cannot be asked to close itself
                try:
                    os.killpg(process.pid, signal.SIGKILL)  # its own process group: a wrapper's descendants too
                except (AttributeError, OSError):
                    process.kill()
                with contextlib.suppress(subprocess.TimeoutExpired):
                    process.communicate(timeout=10)
                remove_singleton(profile, before)
                if isinstance(error, subprocess.TimeoutExpired):
                    self.fail(f"the browser did not finish within {timeout} seconds")
                raise
        self.assertEqual(process.returncode, 0, stderr[-2000:])
        self.assertIn("</html>", stdout, "the browser printed no document")
        return stdout

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
        # Each view's "How to read it" disclosure is one stop of its own, about a dozen in this report.
        self.assertLess(result["tabStops"] - result["sections"], 80, "reaching the ledger takes too many Tab presses")
        self.assertGreater(result["marks"], 20)
        self.assertEqual(result["markStops"], 1, "a case dossier's runs are not a single tab stop")
        self.assertEqual(result["titles"], 0, "run marks keep a native title beside the styled tooltip")
        self.assertTrue(result["tip"]["shown"])
        # Focus shows the run's card: its case and repeat, its arm and its outcome, each also in its accessible name.
        tip = result["tip"]
        case, repeat = tip["over"].rsplit(" · ", 1)
        for part in (case, tip["title"], repeat, tip["outcome"]):
            self.assertIn(part, tip["label"], f"the card and the accessible name disagree: {tip}")
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

    def drive(self, page: Path, *, width: int, script: str = "return null;", tab_to: str | None = None, height: int = 900) -> dict:
        """Run browser-drive.cjs: an exact viewport and real key presses over the DevTools protocol."""
        if not NODE:
            self.skipTest("node is not on PATH")
        script_file = self.dir / "drive-script.js"
        script_file.write_text(script, encoding="utf-8")
        command = [NODE, DRIVER, "--browser", BROWSER, "--profile", self.dir / "drive-profile", "--url", page.as_uri(), "--width", str(width), "--height", str(height), "--script", script_file]
        if tab_to:
            command += ["--tab-to", tab_to]
        with no_fetcher_leftovers(), subprocess.Popen(list(map(str, command)), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) as process:
            try:
                stdout, stderr = process.communicate(timeout=180)
            except subprocess.TimeoutExpired:
                process.terminate()  # the driver closes its browser before it exits
                try:
                    process.communicate(timeout=30)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.communicate()
                self.fail("the driver did not finish within 180 seconds")
        result = subprocess.CompletedProcess(process.args, process.returncode, stdout, stderr)
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])
        lines = result.stdout.strip().splitlines()
        self.assertTrue(lines, f"the driver printed nothing: {result.stderr[-2000:]}")
        out = json.loads(lines[-1])
        if "skip" in out:
            self.skipTest(out["skip"])
        self.assertNotIn("error", out, out.get("error"))
        self.assertEqual(out["stopped"], "closed", "the browser did not close itself when asked")
        if out["singleton"]:
            self.assertFalse(Path(out["singleton"]).exists(), "the browser left its singleton folder behind")
        self.assertEqual(out["width"], width, "the viewport was not emulated")
        return out

    def browser_processes(self, profile: Path) -> list[str]:
        if not shutil.which("ps"):
            return []
        return [line for line in subprocess.run(["ps", "-A", "-o", "args="], capture_output=True, text=True).stdout.splitlines() if str(profile) in line]

    def test_a_dumped_page_leaves_nothing_behind(self) -> None:
        before = fetcher_leftovers()
        self.dump("--trial", EXAMPLES / "fictional-trial.json", "--narrative", EXAMPLES / "fictional-narrative.json")
        sweep_fetcher_leftovers()
        self.assertEqual(sorted(map(str, fetcher_leftovers() - before)), [], "the browser left empty fetcher folders in the temp directory")
        self.assertEqual(self.browser_processes(self.dir / "profile"), [], "a browser process outlived the dump")

    def test_a_driven_browser_closes_itself_and_leaves_nothing_behind(self) -> None:
        before = fetcher_leftovers()
        out = self.drive(self.build("--trial", EXAMPLES / "fictional-trial.json", "--narrative", EXAMPLES / "fictional-narrative.json"), width=390)
        if sys.platform.startswith("linux"):  # where the profile is known to keep a SingletonSocket link
            self.assertIsNotNone(out["singleton"], "the driver could not find the browser's singleton folder to check")
        sweep_fetcher_leftovers()
        self.assertEqual(sorted(map(str, fetcher_leftovers() - before)), [], "the drive left empty fetcher folders in the temp directory")
        self.assertEqual(self.browser_processes(self.dir / "drive-profile"), [], "a browser process outlived the drive")

    @unittest.skipUnless(hasattr(signal, "SIGTERM") and os.name == "posix", "needs POSIX signals")
    def stop_drive_midway(self, *, freeze_browser: bool = False) -> tuple[Path | None, list[int]]:
        """Start a drive that never finishes on its own, optionally freeze its
        browser so it answers nothing, not even Browser.close, then SIGTERM
        the driver. Returns the browser's singleton folder and the browser
        processes the driver left running, which this then kills."""
        if not NODE:
            self.skipTest("node is not on PATH")
        page, profile = self.build("--trial", EXAMPLES / "fictional-trial.json"), self.dir / "drive-profile"
        script_file = self.dir / "drive-script.js"
        script_file.write_text("await new Promise(() => {});", encoding="utf-8")
        with no_fetcher_leftovers(), subprocess.Popen([NODE, str(DRIVER), "--browser", BROWSER, "--profile", str(profile), "--url", page.as_uri(), "--script", str(script_file)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) as process:
            singleton = None
            for _ in range(300):
                if process.poll() is not None:  # the driver ended on its own: a skip or an error
                    stdout, stderr = process.communicate()
                    out = json.loads(stdout.strip().splitlines()[-1]) if stdout.strip() else {}
                    if "skip" in out:
                        self.skipTest(out["skip"])
                    self.fail(f"the driver ended before it was stopped: {stdout[-500:]}{stderr[-500:]}")
                try:
                    singleton = Path(os.readlink(profile / "SingletonSocket")).parent
                    break
                except OSError:
                    time.sleep(0.1)
            time.sleep(1)  # the page is loading and the browser is busy
            survivors: list[int] = []
            try:
                if freeze_browser:
                    states: list[str] = []
                    for _ in range(50):  # a process in uninterruptible sleep (D) stops only once it wakes
                        pids = self.browser_pids(profile, but=process.pid)
                        for pid in pids:
                            with contextlib.suppress(OSError):
                                os.kill(pid, signal.SIGSTOP)
                        states = subprocess.run(["ps", "-o", "stat=", "-p", ",".join(map(str, pids))], capture_output=True, text=True).stdout.split() if pids else []
                        if states and all(state.startswith("T") for state in states):
                            break
                        time.sleep(0.1)
                    self.assertTrue(states and all(state.startswith("T") for state in states), f"the browser was not frozen: {states}")
                process.send_signal(signal.SIGTERM)
                process.communicate(timeout=60)
            finally:
                survivors = self.browser_pids(profile, but=process.pid)  # none, unless the driver failed to stop them
                for pid in survivors:
                    with contextlib.suppress(OSError):
                        os.kill(pid, signal.SIGKILL)
        self.assertNotEqual(process.returncode, 0)
        return singleton, survivors

    def browser_pids(self, profile: Path, *, but: int) -> list[int]:
        if not shutil.which("ps"):
            return []
        rows = subprocess.run(["ps", "-A", "-o", "pid=", "-o", "args="], capture_output=True, text=True).stdout.splitlines()
        return [pid for pid in (int(row.split(None, 1)[0]) for row in rows if str(profile) in row) if pid not in (but, os.getpid())]

    @unittest.skipUnless(hasattr(signal, "SIGTERM") and os.name == "posix", "needs POSIX signals")
    def test_a_driver_that_is_stopped_midway_closes_its_browser_first(self) -> None:
        before = fetcher_leftovers()
        singleton, survivors = self.stop_drive_midway()
        self.assertIsNotNone(singleton, "the browser never started")
        self.assertFalse(singleton.exists(), "the stopped driver's browser left its singleton folder behind")
        sweep_fetcher_leftovers()
        self.assertEqual(sorted(map(str, fetcher_leftovers() - before)), [], "the stopped driver left empty fetcher folders")
        self.assertEqual(survivors, [], "a browser process outlived the stopped driver")

    @unittest.skipUnless(hasattr(signal, "SIGSTOP") and os.name == "posix" and shutil.which("ps"), "needs POSIX signals and ps")
    def test_a_browser_that_will_not_close_is_killed_and_leaves_nothing_behind(self) -> None:
        before = fetcher_leftovers()
        singleton, survivors = self.stop_drive_midway(freeze_browser=True)
        self.assertIsNotNone(singleton, "the browser never started")
        self.assertFalse(singleton.exists(), "the killed browser left its singleton folder behind")
        sweep_fetcher_leftovers()
        self.assertEqual(sorted(map(str, fetcher_leftovers() - before)), [], "the killed browser left empty fetcher folders")
        self.assertEqual(survivors, [], "a browser process outlived the kill")

    def test_a_dump_that_never_finishes_is_killed_and_leaves_nothing_behind(self) -> None:
        page = self.dir / "never-loads.html"
        before = fetcher_leftovers()
        with socket.create_server(("127.0.0.1", 0)) as server:  # takes connections and never answers, so the page never loads
            page.write_text(f'<!doctype html><img src="http://127.0.0.1:{server.getsockname()[1]}/never">', encoding="utf-8")
            with self.assertRaisesRegex(AssertionError, "did not finish within 8 seconds"):
                self.browse(page, timeout=8)
        link = self.dir / "profile" / "SingletonSocket"
        if sys.platform.startswith("linux"):  # where the profile is known to keep a SingletonSocket link
            self.assertTrue(link.is_symlink(), "the killed browser left no singleton link to check")
        if link.is_symlink():
            self.assertFalse(Path(os.readlink(link)).parent.exists(), "the killed browser left its singleton folder behind")
        sweep_fetcher_leftovers()
        self.assertEqual(sorted(map(str, fetcher_leftovers() - before)), [], "the killed browser left empty fetcher folders")
        self.assertEqual(self.browser_processes(self.dir / "profile"), [], "a browser process outlived the kill")

    def test_every_chart_has_an_axis_every_mark_a_card_and_no_text_is_cut_off(self) -> None:
        comparisons = EXAMPLES / "comparisons"
        pages = {
            "trial": ("--trial", EXAMPLES / "fictional-trial.json", "--narrative", EXAMPLES / "fictional-narrative.json"),
            "general": ("--spec", EXAMPLES / "showcase-spec.json"),
            **{name: ("--data", comparisons / f"{name}.json", "--narrative", comparisons / f"{name}-narrative.json") for name in ("sandwich", "research-directions", "ad-campaign", "game-design")},
            "commute": ("--csv", comparisons / "commute.csv", "--narrative", comparisons / "commute-narrative.json"),
        }
        for kind, args in pages.items():
            page = self.build(*args)
            for width in (390, 1024, 1920):
                with self.subTest(page=kind, width=width):
                    found = self.drive(page, width=width, script=AUDIT)["result"]
                    self.assertEqual(found["sideways"], 0, "the page scrolls sideways")
                    self.assertEqual(found["cut"], [], "text is cut off or runs past its view")
                    self.assertEqual(found["broken"], [], "a name is broken inside a word")
                    self.assertEqual(found["noAxis"], [], "a chart has no axis with ticks")
                    self.assertEqual(found["noCard"], [], "a mark shows nothing on hover")

    def test_a_mark_shows_what_was_tested_and_its_numbers_on_hover_and_on_touch(self) -> None:
        # The owner: hovering should "include the title of whatever was tested ... and then rich data in a poppout".
        narrative = json.loads((EXAMPLES / "fictional-narrative.json").read_text(encoding="utf-8"))
        # One run's judge gives a reason far longer than a screen, as a real judge sometimes does.
        trial = json.loads((EXAMPLES / "fictional-trial.json").read_text(encoding="utf-8"))
        long_run = next(r for r in trial["runs"] if r.get("passed") is True and isinstance(r.get("judge"), dict))
        long_run["judge"]["reason"] = " ".join(["The reply names the harbour, the light and the mood, and invents nothing the photograph does not show."] * 60)
        path = self.dir / "long-reason.json"
        path.write_text(json.dumps(trial), encoding="utf-8")
        page = self.build("--trial", path, "--narrative", EXAMPLES / "fictional-narrative.json")
        script = CARD + """
const out = {};
const diff = document.querySelector(".av-contrast-row--case .av-contrast-track[data-av-tip]");
point(diff, "pointerover"); out.difference = tip();
point(diff, "pointerout"); out.afterOut = tip().shown;
const run = document.querySelector(".av-block--cases button[data-run]");
point(run, "pointerover"); out.run = tip();
const rate = document.querySelector(".av-ladder-track[data-av-tip]");
point(document.body, "pointerout");
point(rate, "pointerdown", "touch"); out.touch = tip();
point(document.body, "pointerdown", "touch"); out.touchAway = tip().shown;
point(rate, "pointerdown", "touch"); document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" })); out.escape = tip().shown;
// The long reason's card opens; scrolling then moves it with its mark.
const reason = [...document.querySelectorAll(".av-ledger .av-why > span[data-av-tip]")].find(s => s.getAttribute("data-av-tip").length > 4000);
point(reason, "pointerdown", "touch");
out.long = { shown: tip().shown };
// Scrolling moves the card with its mark, and once the mark has left the window the card goes with it.
const frames = () => new Promise(done => requestAnimationFrame(() => requestAnimationFrame(done)));
const before = [reason.getBoundingClientRect().top, document.querySelector(".av-tip").getBoundingClientRect().top];
window.scrollBy({ top: -40, behavior: "instant" }); await frames();
const after = [reason.getBoundingClientRect().top, document.querySelector(".av-tip").getBoundingClientRect().top];
out.follows = { shown: tip().shown, mark: after[0] - before[0], card: after[1] - before[1] };
out.beforeScrollAway = tip().shown;
window.scrollBy({ top: -innerHeight * 3, behavior: "instant" }); await frames();
out.afterScrollAway = tip().shown;
// A mark scrolled out of the box that clips it, though still inside the window, takes its card with it.
const box = document.createElement("div"); box.style.cssText = "width:200px;overflow-x:auto;white-space:nowrap;border-left:20px solid";
const wide = document.createElement("div"); wide.style.cssText = "width:1200px;padding:10px 0";
const inner = document.createElement("span"); inner.style.cssText = "display:inline-block;width:8px;height:10px;margin-left:60px;background:currentColor"; inner.setAttribute("data-av-tip", "a mark in a box");
wide.appendChild(inner); box.appendChild(wide); document.querySelector(".av-block").prepend(box);
box.scrollIntoView({ block: "center", behavior: "instant" }); await frames(); await frames();
point(inner, "pointerdown", "touch"); out.boxShown = tip().shown;
// Scrolled until the 8px mark lies on the box's 20px left border, 6px in: inside the window and the box's outer edge,
// yet hidden.
box.scrollLeft = 20 + 60 - 6; await frames();
const m = inner.getBoundingClientRect(), b = box.getBoundingClientRect();
out.parked = { inWindow: m.left >= 0 && m.right <= innerWidth, onBorder: m.left >= b.left - 0.5 && m.right <= b.left + 20.5 };
out.afterBoxScroll = tip().shown;
// A mark fixed in place inside a transformed box that clips it, and drawn outside that box, is hidden: a scroll takes its
// card away (a transformed box holds its fixed descendants, so it clips them).

return out;
"""
        out = self.drive(page, width=1440, script=script)["result"]
        cases = narrative.get("cases", {})
        self.assertTrue(out["difference"]["shown"], "hovering a difference shows no card")
        self.assertIn(out["difference"]["over"], cases.values(), "a difference's card does not name the case it was tested on")
        self.assertIn(" minus ", out["difference"]["title"])
        self.assertTrue({"Difference", "95% interval"} <= set(out["difference"]["rows"]), out["difference"])
        self.assertFalse(out["afterOut"], "the card stays after the pointer leaves")
        self.assertTrue(out["run"]["shown"] and out["run"]["mark"], "a run's card is missing or has no mark")
        self.assertTrue(any(out["run"]["over"].startswith(c) for c in cases.values()), f"a run's card does not name its case: {out['run']}")
        self.assertIn("Outcome", out["run"]["rows"])
        self.assertTrue(out["touch"]["shown"] and out["touch"]["rows"], "a touch shows no card")
        self.assertFalse(out["touchAway"], "a touch elsewhere leaves the card up")
        self.assertFalse(out["escape"], "Escape leaves the card up")
        self.assertTrue(out["long"]["shown"])
        self.assertEqual(out["follows"]["mark"], 40, "the page did not scroll the mark")
        self.assertTrue(out["follows"]["shown"], "a small scroll puts the card away")
        self.assertLessEqual(abs(out["follows"]["card"] - out["follows"]["mark"]), 2, f"the card is stranded when its mark moves: {out['follows']}")
        self.assertTrue(out["beforeScrollAway"], "no card was open to scroll away")
        self.assertFalse(out["afterScrollAway"], "the card stays after its mark has left the window")
        self.assertTrue(out["boxShown"])
        self.assertEqual(out["parked"], {"inWindow": True, "onBorder": True}, "the mark was not left on the box's border, in the window")
        self.assertFalse(out["afterBoxScroll"], "the card stays after its mark has scrolled out of the box that clips it")
    def test_a_card_longer_than_a_short_window_still_fits_it_whole(self) -> None:
        # In a window 420 px high, under the top bar: a run's very long reason, and a card whose value and note each run far
        # past a screen, whether opened by a touch or the pointer; and again when the window shrinks with a card open to leave
        # 90 px under the top bar (less than an older 120 px floor), then 30 px (too little for any card).
        trial = json.loads((EXAMPLES / "fictional-trial.json").read_text(encoding="utf-8"))
        long_run = next(r for r in trial["runs"] if r.get("passed") is True and isinstance(r.get("judge"), dict))
        long_run["judge"]["reason"] = " ".join(["The reply names the harbour, the light and the mood, and invents nothing the photograph does not show."] * 60)
        path = self.dir / "long-reason.json"
        path.write_text(json.dumps(trial), encoding="utf-8")
        page = self.build("--trial", path, "--narrative", EXAMPLES / "fictional-narrative.json")
        script = CARD + """
const box = () => { const t = document.querySelector(".av-tip"), r = t.getBoundingClientRect(), bar = document.querySelector(".av-topbar").getBoundingClientRect().bottom; return { shown: t.hasAttribute("data-show"), top: r.top, bottom: r.bottom, room: [bar, innerHeight], natural: t.scrollHeight }; };
const out = {};
const reason = [...document.querySelectorAll(".av-ledger .av-why > span[data-av-tip]")].find(s => s.getAttribute("data-av-tip").length > 4000);
point(reason, "pointerdown", "touch"); out.reason = box();
const big = document.createElement("span"); big.textContent = "x"; big.setAttribute("data-av-tip", JSON.stringify({ title: "A long value", rows: [["Value", "word ".repeat(2000)], ["More", "word ".repeat(2000)], ["Still more", "word ".repeat(2000)]], note: "note ".repeat(2000) }));
// Kept in view at the foot of the sticky top bar, so only the room for its card, never its own scrolling away, can close it.
big.style.cssText = "position:absolute;bottom:2px;left:120px;width:10px;height:6px;font-size:0;overflow:hidden";
document.querySelector(".av-topbar").appendChild(big); point(big, "pointerover"); out.huge = box();
// The window shrinks with the card open, and nothing else happens: the card is fitted again to the room left.
const resized = new Promise(done => addEventListener("resize", done, { once: true }));
// To a window leaving 90 px under the top bar: less than the 120 px an older floor allowed, room enough for a card.
const bar = () => document.querySelector(".av-topbar").getBoundingClientRect().bottom;
avDriveResize("1440x" + Math.round(bar() + 12 + 90)); await resized;
await new Promise(done => requestAnimationFrame(() => requestAnimationFrame(done))); out.shrunk = box();
// With too little room for even a card's frame and a line, it closes; with room again, pointing at the mark reopens it.
const frames = () => new Promise(done => requestAnimationFrame(() => requestAnimationFrame(done)));
const resize = size => { const r = new Promise(done => addEventListener("resize", done, { once: true })); avDriveResize(size); return r; };
await resize("1440x" + Math.round(bar() + 12 + 30)); await frames(); out.tiny = box(); out.tinyMarkSeen = big.getBoundingClientRect().bottom <= innerHeight;
await resize("1440x420"); await frames();
big.dispatchEvent(new PointerEvent("pointerover", { bubbles: true, pointerType: "mouse" })); out.again = box();
return out;
"""
        out = self.drive(page, width=1440, height=420, script=script)["result"]
        for name in ("reason", "huge", "shrunk", "again"):
            card = out[name]
            with self.subTest(card=name):
                self.assertTrue(card["shown"], "the card does not open")
                self.assertGreaterEqual(card["top"], card["room"][0], "the card starts under the top bar")
                self.assertLessEqual(card["bottom"], card["room"][1], "the card runs off the bottom of the window")
        self.assertGreater(out["huge"]["natural"], 420 - out["huge"]["room"][0], "the long card would have fitted anyway: this checks nothing")
        self.assertTrue(out["tinyMarkSeen"], "the mark left the tiny window, so this checks nothing")
        self.assertFalse(out["tiny"]["shown"], "a card is shown in a window with no room for it")

    def test_a_long_name_in_the_top_bar_wraps_and_a_scroll_to_a_section_still_lands_below_the_bar(self) -> None:
        narrative = json.loads((EXAMPLES / "fictional-narrative.json").read_text(encoding="utf-8"))
        narrative["kicker"] = "Split test · " + " ".join(["fictional-reply-guidance"] * 10)
        path = self.dir / "long-kicker.json"
        path.write_text(json.dumps(narrative), encoding="utf-8")
        page = self.build("--trial", EXAMPLES / "fictional-trial.json", "--narrative", path)
        # Measured at 1440 px, then again after the window narrows to 320 px in the same load, so a reserve kept from the
        # first width would show.
        script = """
const frames = () => new Promise(done => requestAnimationFrame(() => requestAnimationFrame(done)));
const name = document.querySelector(".av-brand-text"), bar = document.querySelector(".av-topbar");
const look = async () => {
  const lines = Math.round(name.getBoundingClientRect().height / parseFloat(getComputedStyle(name).lineHeight));
  const section = document.querySelector(".av-section[id]:nth-of-type(3)");
  // The browser's own scroll to an element, as for an anchor the report does not handle, focus or find in page.
  section.scrollIntoView({ block: "start", behavior: "instant" }); await frames();
  // The section itself, not only its heading, starts below the bar.
  return { lines, cut: name.scrollWidth > name.clientWidth + 1, bar: bar.getBoundingClientRect().bottom, head: section.getBoundingClientRect().top };
};
const wide = await look();
// The section index's current entry stays in view as the page is scrolled to its last section, on a phone too.
const current = async () => { const last = [...document.querySelectorAll(".av-section[id]")].pop(); last.scrollIntoView({ block: "start", behavior: "instant" });
  await new Promise(done => setTimeout(done, 300)); const a = document.querySelector(".av-toc a[aria-current]"), strip = document.querySelector(".av-toc").getBoundingClientRect(), r = a.getBoundingClientRect();
  return { id: a.getAttribute("href"), last: "#" + last.id, inside: r.left >= strip.left - 1 && (r.right <= strip.right + 1 || r.width > strip.width) }; };
const indexWide = await current();
const resized = new Promise(done => addEventListener("resize", done, { once: true }));
avDriveResize("320x900"); await resized; await frames();
const narrow = await look();
return { wide, narrow, indexWide, indexNarrow: await current() };
"""
        out = self.drive(page, width=1440, script=script)["result"]
        for width in ("wide", "narrow"):
            with self.subTest(width=width):
                look = out[width]
                self.assertFalse(look["cut"], "the name is cut off across its width")
                self.assertGreaterEqual(look["lines"], 1)
                self.assertLessEqual(look["lines"], 3, "an outsized name takes more than three lines of the bar")
                self.assertGreaterEqual(look["head"], look["bar"] - 1, "a scroll to a section leaves its start under the top bar")
                self.assertLessEqual(look["head"], look["bar"] + 20, "a scroll to a section stops well below the bar, as for another bar's height")
        self.assertGreater(out["narrow"]["bar"], out["wide"]["bar"] + 12, "the bar did not grow when the window narrowed: this checks nothing")
        for width in ("indexWide", "indexNarrow"):
            with self.subTest(index=width):
                self.assertEqual(out[width]["id"], out[width]["last"], "the section index does not mark the last section")
                self.assertTrue(out[width]["inside"], "the section index's current entry is out of its view")

    def test_the_section_index_keeps_its_current_entry_in_view_however_long_and_after_a_resize(self) -> None:
        # Every index entry is far wider than a phone's strip. Scrolled to its next-to-last section at 1440 px, then the window
        # narrows to 320 px with the same section current: the entry is in its strip, and one wider than the strip shows its
        # beginning.
        spec = json.loads((EXAMPLES / "showcase-spec.json").read_text(encoding="utf-8"))
        # Every entry long, so whichever section the index counts as current, its entry is the long kind.
        for i, section in enumerate(spec["sections"]):
            section["label"] = f"Section {i + 1}, whose name in the index runs on well past what a phone's strip can show at once"
        # The next-to-last section runs several screens, so it stays current as the page reflows on the resize.
        spec["sections"][-2]["blocks"].append({"type": "text", "text": ["A paragraph that gives this section its length on any screen, so a reader scrolled into its middle stays inside it."] * 60})
        path = self.dir / "long-label.json"
        path.write_text(json.dumps(spec), encoding="utf-8")
        page = self.build("--spec", path)
        script = """
const frames = () => new Promise(done => requestAnimationFrame(() => requestAnimationFrame(done)));
const look = () => { const a = document.querySelector(".av-toc a[aria-current]"), t = document.querySelector(".av-toc").getBoundingClientRect(), r = a.getBoundingClientRect();
  return { label: a.textContent, wider: r.width > t.width - 24, whole: r.left >= t.left - 1 && r.right <= t.right + 1, begins: r.left >= t.left - 1 && r.left <= t.left + 24 }; };
const last = [...document.querySelectorAll(".av-section[id]")].slice(-2)[0];
const middle = () => { const r = last.getBoundingClientRect(); window.scrollTo({ top: scrollY + r.top + r.height / 2, behavior: "instant" }); };
middle(); await new Promise(done => setTimeout(done, 300));
const wide = look();
const resized = new Promise(done => addEventListener("resize", done, { once: true }));
avDriveResize("320x900"); await resized; await frames(); await new Promise(done => setTimeout(done, 300));
const before = wide.label;
return { wide, narrow: look(), still: document.querySelector(".av-toc a[aria-current]").textContent === before };
"""
        out = self.drive(page, width=1440, script=script)["result"]
        self.assertIn("runs on well past", out["narrow"]["label"], "the index's current entry is not the long one")
        self.assertTrue(out["still"], "the last section stopped being current across the resize: this checks nothing")
        self.assertTrue(out["narrow"]["wider"], "the long entry fits a phone's strip: this checks nothing")
        self.assertTrue(out["narrow"]["begins"], "a current entry wider than the strip does not show its beginning after a resize")
        self.assertTrue(out["wide"]["whole"] or (out["wide"]["wider"] and out["wide"]["begins"]), "the current entry is out of the strip")

    def test_a_per_case_panel_reads_against_an_axis_that_spans_its_tracks(self) -> None:
        comparisons = EXAMPLES / "comparisons"
        page = self.build("--data", comparisons / "research-directions.json", "--narrative", comparisons / "research-directions-narrative.json")
        script = """
return [...document.querySelectorAll(".av-cmp-panel")].filter(p => p.getBoundingClientRect().width).map(p => {
  const ticks = p.querySelector(".av-cmp-mini--axis .av-ticks").getBoundingClientRect();
  return [...p.querySelectorAll(".av-cmp-mini:not(.av-cmp-mini--axis) > :nth-child(3)")].map(t => { const r = t.getBoundingClientRect(); return [Math.round(r.left - ticks.left), Math.round(r.right - ticks.right)]; });
});
"""
        for width in (390, 1440):
            panels = self.drive(page, width=width, script=script)["result"]
            self.assertTrue(panels, "no per-case panel drawn")
            for rows in panels:
                for left, right in rows:
                    with self.subTest(width=width):
                        self.assertLessEqual(abs(left), 1, "a panel's axis starts away from its tracks")
                        self.assertLessEqual(abs(right), 1, "a panel's axis ends away from its tracks")

    def test_an_observation_shows_its_own_value_and_a_trend_is_not_called_a_pass_rate(self) -> None:
        page = self.build("--csv", EXAMPLES / "comparisons/commute.csv", "--narrative", EXAMPLES / "comparisons/commute-narrative.json")
        script = CARD + """
// Each observation, pointed at where it is drawn, shows its own card, whose value sits where the dot is on the axis.
const grid = document.querySelector(".av-cmp-grid"), ticks = [...grid.querySelectorAll(".av-cmp-axis .av-tick")].map(t => [parseFloat(t.textContent), t.getBoundingClientRect()]).filter(t => Number.isFinite(t[0]));
const track = grid.querySelector(".av-cmp-track"), tb = track.getBoundingClientRect();
const [a, b] = [ticks[0], ticks[ticks.length - 1]];
// A tick sits at its label's left edge, middle or right edge as the axis turns its edge labels inward.
const at = t => t[1].left + t[1].width * (t === ticks[0] ? 0 : t === ticks[ticks.length - 1] ? 1 : .5);
const value = x => a[0] + (x - at(a)) / (at(b) - at(a)) * (b[0] - a[0]);
const out = [];
for (const dot of grid.querySelectorAll(".av-cmp-track .av-cmp-dot")) {
  dot.scrollIntoView({ block: "center", behavior: "instant" });
  // As the audit points: at its middle, or just beside it within the hover area it is given.
  const r = dot.getBoundingClientRect(), cx = r.left + r.width / 2, cy = r.top + r.height / 2;
  const found = [[0, 0], [-4, 0], [4, 0], [0, -4], [0, 4]].map(([x, y]) => document.elementFromPoint(cx + x, cy + y)?.closest("[data-av-tip]")).find(f => f && f.matches(".av-cmp-dot"));
  if (!found) { out.push({ title: "", said: NaN, drawn: NaN, span: 1 }); continue; }
  found.dispatchEvent(new PointerEvent("pointerover", { bubbles: true, pointerType: "mouse" }));
  const card = tip(), said = parseFloat(document.querySelector(".av-tip-rows dd")?.textContent || ""), fr = found.getBoundingClientRect();
  out.push({ title: card.title, said, drawn: Math.round(value(fr.left + fr.width / 2) * 100) / 100, span: b[0] - a[0] });
}
return out;
"""
        dots = self.drive(page, width=1440, script=script)["result"]
        self.assertTrue(dots, "no observation drawn")
        for d in dots:
            self.assertEqual(d["title"], "One observation", "pointing at an observation shows another card")
            self.assertLessEqual(abs(d["said"] - d["drawn"]), d["span"] * 0.01, f"an observation's card says {d['said']} where it is drawn at {d['drawn']}")
        general = self.build("--spec", EXAMPLES / "showcase-spec.json")
        titles = self.drive(general, width=1440, script='return [...document.querySelectorAll(".av-svg-axis-title")].map(t => t.textContent);')["result"]
        self.assertTrue(titles, "the trend draws no axis title")
        self.assertNotIn("pass rate", titles, "a generic trend of rates is titled as a pass rate")

    def test_a_difference_of_shares_is_drawn_within_a_hundred_points(self) -> None:
        page = self.build("--data", EXAMPLES / "comparisons/sandwich.json", "--narrative", EXAMPLES / "comparisons/sandwich-narrative.json")
        script = 'return [...document.querySelectorAll(".av-cmp-dpanel")].map(p => [...p.querySelectorAll(".av-cmp-daxis .av-tick")].map(t => t.textContent.trim()));'
        axes = self.drive(page, width=1440, script=script)["result"]
        share = next(a for a in axes if any("+" in t for t in a))
        values = [float(t.replace("−", "-").replace("+", "").replace("pts", "").strip()) for t in share if t]
        self.assertEqual(max(values), 100, f"a difference of shares, which cannot pass 100 points, is drawn on {share}")
        self.assertEqual(min(values), -100)

    def test_type_grows_on_large_screens_and_keeps_the_readers_size_on_small_ones(self) -> None:
        page = self.build("--trial", EXAMPLES / "fictional-trial.json")
        size = {w: self.drive(page, width=w, script="return parseFloat(getComputedStyle(document.documentElement).fontSize);")["result"] for w in (390, 1440, 1920, 2560)}
        self.assertEqual(size[390], 16, "a phone does not keep the reader's own size")
        self.assertEqual(size[1440], 16)
        self.assertLess(size[1440], size[1920], "type does not grow past 1440 px")
        self.assertLess(size[1920], size[2560])
        self.assertLessEqual(size[2560], 18.01, "type grows past two steps")

    def test_no_text_is_crushed_into_a_narrow_column(self) -> None:
        narrative = json.loads((EXAMPLES / "fictional-narrative.json").read_text(encoding="utf-8"))
        long = "GPT 17/17 against 17/17 (p = 1.00); Claude 29/29 against 25/29 (p = 0.11); mean seconds per run 153, 205 and 243"
        narrative["decision"]["checks"] = [{"label": "The checklist beats both copies by 15 points", "observed": long, "threshold": "at least 15 points on pooled runs", "met": True}] * 3
        path = self.dir / "narrative.json"
        path.write_text(json.dumps(narrative), encoding="utf-8")
        page = self.build("--trial", EXAMPLES / "fictional-trial.json", "--narrative", path)
        for width in (1440, 1024, 800):
            with self.subTest(width=width):
                self.assertEqual(self.drive(page, width=width, script=CRAMPED)["result"], [], "text crushed into a column under 200 px")
        # An observation ledger whose case labels are sentences and whose sources are long run paths: the labels
        # once stayed on one line and took the room, so each path wrapped to seven lines in a 144 px column.
        cases = {"recurring": "Starting a pass: a recurring stale instruction met during a feature task",
                 "first": "Restraint: the same stale instruction met for the first time"}
        observations = [{"alternative": alt, "case": case, "metric": "passed", "value": (i + j) % 2 == 0, "unit": f"r{i}",
                         "note": "The agent edited the build file to add an alias for the old target name.",
                         "source": f"/home/someone/.cache/agent-trials/heal-any-final2-auto-{alt}/runs/heal-autolaunch-{case}__{alt}__r{i}"}
                        for j, alt in enumerate(("current", "revised")) for case in cases for i in range(1, 4)]
        comparison = {"title": "Ledger widths", "alternatives": [{"id": "current", "label": "Main's text"}, {"id": "revised", "label": "Revised text"}],
                      "cases": [{"id": k, "label": v} for k, v in cases.items()],
                      "metrics": [{"id": "passed", "label": "Passed (checks and cross-family judge)", "kind": "binary", "better": "higher"}],
                      "observations": observations}
        data = self.dir / "ledger.json"
        data.write_text(json.dumps(comparison), encoding="utf-8")
        ledger = self.build("--data", data)
        for width in (1440, 1024):
            with self.subTest(ledger=width):
                self.assertEqual(self.drive(ledger, width=width, script=CRAMPED)["result"], [], "a ledger cell crushed into a column under 200 px")
        # Six arms with long names in the checks table: the check-name column once kept 44% of the width however many
        # arms shared the rest, so at 1440 px each arm's name wrapped to five lines in a 71 px column. (At 1024 px the
        # six names and the check names share under 900 px, and a name of four short lines is the table fitting.)
        names = ["No instructions (GPT)", "Policy line naming over-engineering (GPT)", "Both directions at equal standing (GPT)",
                 "No instructions (Claude)", "Policy line naming over-engineering (Claude)", "Both directions at equal standing (Claude)"]
        arms = [f"arm{i}" for i in range(len(names))]
        runs = [{"job": f"{case}__{arm}__r{r}", "scenario": case, "arm": arm, "repeat": r, "status": "ok", "passed": (i + r) % 3 != 0, "valid": True,
                 "checks": {"reply_written": True, "cites_the_source": (i + r) % 3 != 0}}
                for case in ("first", "second") for i, arm in enumerate(arms) for r in (1, 2)]
        wide = {"name": "wide", "plan": {"arms": {a: {"executor": "command", "model": "m"} for a in arms},
                                         "scenarios": [{"name": c, "prompt": "Reply.", "required": ["reply_written", "cites_the_source"]} for c in ("first", "second")]}, "runs": runs}
        (self.dir / "wide.json").write_text(json.dumps(wide), encoding="utf-8")
        (self.dir / "wide-narrative.json").write_text(json.dumps({"arms": [{"id": a, "label": n} for a, n in zip(arms, names)]}), encoding="utf-8")
        checks = self.build("--trial", self.dir / "wide.json", "--narrative", self.dir / "wide-narrative.json")
        for width in (1440, 1280):
            with self.subTest(checks=width):
                self.assertEqual(self.drive(checks, width=width, script=CRAMPED)["result"], [], "an arm's name crushed into a column under 200 px")
        # The glyphs stay drawn above the names.
        glyphs = self.drive(checks, width=1440, script='return [...document.querySelectorAll(".av-heatmap thead .av-glyph")].map(g => Math.round(g.getBoundingClientRect().width));')["result"]
        self.assertTrue(glyphs and all(w >= 10 for w in glyphs), f"each arm's glyph in the table head is drawn: {glyphs}")

    def test_wide_screens_widen_the_reading_measure_and_the_scope_box_splits_evenly(self) -> None:
        # The owner, on a wide monitor: "why is the text forced into a column like this globally? THere's way more room on
        # my own screen horizontally". Running text keeps a readable measure at ordinary widths (the story's 75ch, the
        # summary's 62ch) and widens on wide screens, inside a wider page; the story's scope box sets "This report covers"
        # and "It does not cover" side by side at one width, where the second used to sit alone in a narrow track. Later:
        # "For paragraphs, why are they split like this when it's one block of text and not multiple? on larger screens".
        # Text of several paragraphs sets them side by side on a wide screen, each whole; a single paragraph keeps one
        # column at the widened measure.
        narrative = json.loads((EXAMPLES / "fictional-narrative.json").read_text(encoding="utf-8"))
        sentence = "The setup section shows each arm's settings and the texts compared, so a reader can see what differs before any result."
        narrative.setdefault("readings", {})["setup"] = " ".join([sentence] * 3) + "\n\n" + " ".join([sentence] * 2)
        # Unequal paragraphs, even enough to set side by side, that columns balanced by height alone would break.
        told = "A team writes short replies for people with an assistant model, and each reply is judged against its source."
        narrative["story"]["background"] = [" ".join([told] * 6), " ".join([told] * 6), " ".join([told] * 2)]
        path = self.dir / "long-reading.json"
        path.write_text(json.dumps(narrative), encoding="utf-8")
        page = self.build("--trial", EXAMPLES / "fictional-trial.json", "--narrative", path)
        script = """
const chOf = el => { const p = document.createElement("span"); p.textContent = "0000000000"; p.style.cssText = "position:absolute;visibility:hidden;white-space:nowrap"; el.appendChild(p); const w = p.getBoundingClientRect().width / 10; p.remove(); return w; };
const cap = el => { const m = parseFloat(getComputedStyle(el).maxWidth); return Number.isFinite(m) ? Math.round(m / chOf(el) * 10) / 10 : 9999; };  // 9999: no limit at all
const shown = el => Math.round(el.getBoundingClientRect().width / chOf(el) * 10) / 10;
const reads = [...document.querySelectorAll(".av-read-shows, .av-read-how .av-read-prose, .av-read-says")].filter(el => el.getBoundingClientRect().width);
const story = document.querySelector(".av-story > .av-story-part:first-child .av-story-prose");
const summary = document.querySelector(".av-summary");
const scope = [...document.querySelectorAll(".av-story-scope > .av-story-part")].map(p => { const r = p.getBoundingClientRect(); return [Math.round(r.top), Math.round(r.width)]; });
// A block's text as it is drawn: its columns (the separate horizontal spans its text covers, since no text crosses a
// column gap), the widest column in its own characters, and the share of its row the text spans. Measured from the
// drawn text itself, whatever the styles say.
const flow = el => { const r = document.createRange(); r.selectNodeContents(el); const spans = [...r.getClientRects()].filter(q => q.width > 0).map(q => [q.left, q.right]).sort((a, b) => a[0] - b[0]);
  const cols = []; for (const [a, b] of spans) { const last = cols[cols.length - 1]; if (last && a <= last[1] + 1) last[1] = Math.max(last[1], b); else cols.push([a, b]); }
  const ch = chOf(el);
  return { n: cols.length, column: Math.round(Math.max(...cols.map(c => c[1] - c[0])) / ch * 10) / 10, share: Math.round((cols[cols.length - 1][1] - cols[0][0]) / el.parentElement.getBoundingClientRect().width * 100) / 100 }; };
const reading = document.querySelector("#setup .av-section-reading");
// A block set in columns is readable when each column is; any other block, when its cap and drawn width are.
const flows = el => getComputedStyle(el).columnWidth !== "auto";
// A paragraph drawn in more than one column has one box per column it reaches.
// (An inline paragraph has one box per line instead, so only block paragraphs are counted.)
const split = [...document.querySelectorAll(".av-flow > p")].filter(p => getComputedStyle(p).display !== "inline" && p.getClientRects().length > 1).map(p => p.textContent.slice(0, 60));
const flowing = [...document.querySelectorAll(".av-flow > p")].filter(p => getComputedStyle(p).display !== "inline").length;
return { split, flowing, page: Math.round(document.querySelector(".av-sections").getBoundingClientRect().width), story: cap(story), storyShown: shown(story), storyFlow: flow(story), summary: cap(summary), summaryFlow: flow(summary), scope,
  readCaps: reads.map(el => flows(el) ? flow(el).column : cap(el)), readShown: reads.map(el => flows(el) ? flow(el).column : shown(el)), readingFlow: reading && flow(reading) };
"""
        ordinary = self.drive(page, width=1024, script=script)["result"]
        self.assertAlmostEqual(ordinary["story"], 75, delta=0.6, msg="the story's measure changed at an ordinary width")
        self.assertAlmostEqual(ordinary["summary"], 62, delta=0.6, msg="the summary's measure changed at an ordinary width")
        self.assertEqual(1, ordinary["storyFlow"]["n"], "the story's background is split into columns at an ordinary width")
        self.assertEqual(1, ordinary["readingFlow"]["n"], "a section's reading is split into columns at an ordinary width")
        wide = self.drive(page, width=1920, script=script)["result"]
        self.assertGreaterEqual(wide["page"], 1400, "the page stays narrow on a wide screen")
        # Long running text of several paragraphs uses the row on a wide screen by flowing into columns, each a readable
        # width, with every paragraph whole in one column. A reading box, whose text runs on after its label, keeps one
        # readable column instead.
        self.assertGreaterEqual(wide["storyFlow"]["n"], 2, "long text stays in one narrow column on a wide screen")
        self.assertLessEqual(wide["storyFlow"]["column"], 95, "a column grows past a readable length")
        self.assertGreaterEqual(wide["storyFlow"]["share"], 0.85, "long text leaves most of its row empty on a wide screen")
        self.assertGreater(wide["flowing"], 0, "no paragraph flows in columns to check")
        self.assertEqual(wide["readingFlow"]["n"], 1, "a reading box's text is split into columns on a wide screen")
        self.assertLessEqual(wide["readingFlow"]["column"], 95, "a reading box's lines grow past a readable length")
        self.assertEqual(wide["split"], [], "a paragraph is split between columns on a wide screen")
        self.assertGreaterEqual(wide["summary"], 76, "the summary stays in a narrow column on a wide screen")
        self.assertLessEqual(wide["summary"], 92.6, "the summary's lines grow past a readable length")
        self.assertGreaterEqual(wide["storyShown"], 85, "the story's text is drawn narrow on a wide screen whatever its cap says")
        # Each view's own explanation ("This view", "How to read it", "Here") keeps the same readable limit as the rest of
        # the prose, however wide the view it explains.
        self.assertTrue(wide["readCaps"], "no view explanation found to measure")
        self.assertLessEqual(max(wide["readCaps"]), 95, "a view's explanation has no readable limit on a wide screen")
        self.assertLessEqual(max(wide["readShown"]), 95, "a view's explanation is drawn past a readable length")
        # The sizes respond to the screen: two nearby wide screens get different widths.
        nearer, farther = (self.drive(page, width=w, script=script)["result"] for w in (1650, 1750))
        self.assertLess(nearer["page"], farther["page"], "the page width does not respond to the screen between 1650 and 1750 px")
        self.assertLess(nearer["summary"], farther["summary"], "the measure does not respond to the screen between 1650 and 1750 px")
        for width, result in ((1024, ordinary), (1920, wide)):
            with self.subTest(width=width):
                (top_a, width_a), (top_b, width_b) = result["scope"]
                self.assertLessEqual(abs(top_a - top_b), 2, "the scope box stacks its two texts instead of setting them side by side")
                self.assertLessEqual(abs(width_a - width_b), max(width_a, width_b) * 0.05, "the scope box's two texts get different widths")
        # Between ordinary and wide screens, where two readable columns do not yet fit, long text keeps a readable line
        # rather than losing its cap and running the row's whole width in one column.
        # A summary long enough to flow (over 320 characters), as a real report's often is, is held to the same.
        narrative["summary"] = " ".join(["Four setups were compared on four everyday writing tasks, each repeated six times, and a judge read every reply."] * 5)
        path.write_text(json.dumps(narrative), encoding="utf-8")
        long_summary = self.build("--trial", EXAMPLES / "fictional-trial.json", "--narrative", path)
        for width in (1200, 1300, 1420, 1500):
            between = self.drive(long_summary, width=width, script=script)["result"]
            for name in ("storyFlow", "readingFlow", "summaryFlow"):
                with self.subTest(width=width, block=name):
                    self.assertLessEqual(between[name]["column"], 95, "a line runs past a readable length where columns do not fit")
        # That summary is one paragraph, so on a wide screen it stays one column at the widened measure, never split.
        single = self.drive(long_summary, width=1920, script=script)["result"]
        self.assertEqual(single["split"], [], "a paragraph is split between columns on a wide screen")
        self.assertEqual(single["summaryFlow"]["n"], 1, "a single paragraph is split into columns on a wide screen")
        self.assertGreaterEqual(single["summaryFlow"]["column"], 76, "a single paragraph is drawn narrow on a wide screen")
        self.assertLessEqual(single["summaryFlow"]["column"], 95, "a single paragraph's lines grow past a readable length")

    def test_wide_screens_keep_paragraphs_and_entries_whole_and_fill_their_rows(self) -> None:
        # The owner, on a wide screen: "For paragraphs, why are they split like this when it's one block of text and not
        # multiple?"; of a glossary set as one narrow column beside an empty row, "are sections like this really good
        # design?"; and "I want whatever causes it in the library fixed for all places it would exist." At the owner's
        # width and wider, no paragraph or entry is drawn in two columns, no running text's lines pass a readable length,
        # no row of blocks leaves a block alone in a narrow track, and a list of entries uses its row.
        narrative = json.loads((EXAMPLES / "fictional-narrative.json").read_text(encoding="utf-8"))
        sentence = "Each reply was judged against the source it cites, and a reply that cites nothing fails."
        # Three paragraphs (about six lines, six and two), even enough to set side by side, that columns filled by height
        # alone would break: the first column takes the first paragraph and two lines of the second, as on the owner's page.
        narrative["story"]["background"] = [" ".join([sentence] * 6), " ".join([sentence] * 6), " ".join([sentence] * 2)]
        narrative["summary"] = " ".join([sentence] * 9) + "\n\n" + sentence  # one paragraph outweighs the other: one column
        narrative["story"]["glossary"] = [{"term": f"Term {i}", "meaning": sentence} for i in range(1, 8)]
        path = self.dir / "layout-narrative.json"
        path.write_text(json.dumps(narrative), encoding="utf-8")
        page = self.build("--trial", EXAMPLES / "fictional-trial.json", "--narrative", path)
        for width in (1750, 1920):
            out = self.drive(page, width=width, script=LAYOUT)["result"]
            with self.subTest(width=width):
                self.assertTrue(all(out["counted"][k] for k in ("text", "rows", "lists", "axes")), f"nothing to measure: {out['counted']}")
                self.assertEqual(out["split"], [], "a paragraph or entry is split between columns")
                self.assertEqual(out["long"], [], "running text's lines pass a readable length")
                self.assertEqual(out["stranded"], [], "a row of blocks leaves a block alone in a narrow track")
                self.assertEqual(out["narrowList"], [], "a list of entries stays in one column with room for two")
                self.assertEqual(out["tall"], [], "text set in columns stands taller than in one readable column")
                self.assertEqual(out["squeezed"], [], "a group of alternatives does not take its row")
                self.assertEqual(out["offCenter"], [], "a chart's axis title is narrowed off its plot")
        # Directions with alternatives inside them: each nested group takes its list's row beside ungrouped alternatives.
        directions = EXAMPLES / "comparisons"
        page = self.build("--data", directions / "research-directions.json", "--narrative", directions / "research-directions-narrative.json")
        for width in (1750, 1920):
            out = self.drive(page, width=width, script=LAYOUT)["result"]
            with self.subTest(page="research-directions", width=width):
                self.assertGreater(out["counted"]["groups"], 0, "no nested group of alternatives to measure")
                for key in ("split", "long", "stranded", "narrowList", "tall", "squeezed", "offCenter"):
                    self.assertEqual(out[key], [], key)

    def test_phone_width_keeps_row_heads_in_their_cells_and_every_value_readable(self) -> None:
        # A check required in only some cases carries a chip such as "in 10 of 20 cases" in its pooled row head. At 320 px
        # the chip once ran into the first arm's cell; kept whole instead, "in 9999 of 10,000 cases" widened the sticky
        # name column until the 58 px left beside it could never show "9999/9999", however far the table scrolled. Every
        # checks table (pooled, by case, and the recorded measures) keeps each row head inside its cell, and each value
        # can be scrolled to sit in full beside the sticky column.
        def chips_trial(count: int, required_in: int, measures: bool) -> dict:
            cases = [f"c{i:05d}" for i in range(1, count + 1)]
            runs = []
            for i, case in enumerate(cases):
                for j, arm in enumerate(("a", "b")):
                    cites = (i + j) % 3 != 0 if measures else True
                    checks = {"reply_written": True, "cites_the_source": cites, "under_budget": (i + j) % 2 == 0} if measures else {"cites_the_source": True}
                    runs.append({"job": f"{case}__{arm}__r1", "scenario": case, "arm": arm, "repeat": 1, "status": "ok", "valid": True, "passed": cites or i >= required_in, "checks": checks})
            required = (lambda i: ["reply_written", "cites_the_source"] if i < required_in else ["reply_written"]) if measures else (lambda i: ["cites_the_source"] if i < required_in else [])
            return {"name": "chips", "plan": {"arms": {a: {"executor": "command", "model": "m"} for a in ("a", "b")},
                                              "scenarios": [{"name": c, "prompt": "Reply.", "required": required(i)} for i, c in enumerate(cases)]}, "runs": runs}
        variants = {"av-heatmap": {"type": "checks", "by": "check"}, "av-heatmap av-heatmap--case": {"type": "checks", "by": "case"}, "av-heatmap av-heatmap--measures": {"type": "checks", "required": False}}
        fixtures = {"twenty cases": (chips_trial(20, 10, True), "in 10 of 20 cases", list(variants)), "ten thousand cases": (chips_trial(10_000, 9_999, False), "in 9999 of 10,000 cases", ["av-heatmap"])}
        for name, (trial, chip, drawn) in fixtures.items():
            with self.subTest(fixture=name):
                spec_file = self.dir / "row-heads.json"
                spec_file.write_text(json.dumps({"title": "Row heads", "sections": [{"title": v, "blocks": [variants[v]]} for v in drawn]}), encoding="utf-8")
                page = self.build("--trial", self.trial_file(trial), "--spec", spec_file)
                out = self.drive(page, width=320, script=SPILL)["result"]
                self.assertIn(chip, out["chips"], "the pooled row head carries its chip")
                self.assertEqual(out["variants"], sorted(drawn), "each checks table drawn")
                self.assertEqual(out["spills"], [], "a row head running into the first arm's cell at 320 px")
                seen = self.drive(page, width=320, script=READABLE)["result"]
                self.assertGreater(seen["scrolled"], 0, "the tables scroll sideways at 320 px")
                self.assertEqual(seen["hidden"], [], f"a value that cannot be shown in full beside the sticky column at 320 px ({seen['cells']} values)")

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




@unittest.skipUnless(os.name == "posix" and NODE and shutil.which("sh") and shutil.which("ps"), "needs POSIX, node, sh and ps")
class DriverStopTest(unittest.TestCase):
    """browser-drive.cjs stops everything its launcher started, whatever the launcher does."""

    def test_a_launcher_that_exits_at_once_leaves_nothing_running(self) -> None:
        marker = f"av-drive-stop-{os.getpid()}"
        with Scratch() as scratch:
            # A stand-in for a wrapper that starts the browser in the background
            # and exits: it never opens a DevTools port, so the drive fails, and
            # what it started must not outlive the driver.
            launcher = scratch / "launcher"
            launcher.write_text(f"#!/bin/sh\nsh -c 'sleep 300; :' {marker} &\nexit 0\n", encoding="utf-8")
            launcher.chmod(0o755)
            result = subprocess.run([NODE, str(DRIVER), "--browser", str(launcher), "--profile", str(scratch / "profile"), "--url", "about:blank"], capture_output=True, text=True, timeout=90)
        out = json.loads(result.stdout.strip().splitlines()[-1])
        if "skip" in out:
            self.skipTest(out["skip"])
        self.assertIn("error", out)
        running = [line for line in subprocess.run(["ps", "-A", "-o", "args="], capture_output=True, text=True).stdout.splitlines() if marker in line]
        self.assertEqual(running, [], "a process the launcher started outlived the driver")

    def test_only_the_singleton_folder_this_launch_made_is_removed(self) -> None:
        """A browser that never answers is stopped without Browser.close, so the
        driver removes the singleton folder its profile's link names: only one
        this launch made and the link names by an absolute path."""
        with Scratch() as scratch:
            for case in ("own", "earlier", "relative"):
                profile, folder = scratch / f"profile-{case}", scratch / f"com.example.Test.{case}"
                profile.mkdir()
                target = os.path.relpath(folder / "SingletonSocket", profile) if case == "relative" else str(folder / "SingletonSocket")
                make = f"mkdir {shlex.quote(str(folder))} && touch {shlex.quote(str(folder))}/SingletonSocket {shlex.quote(str(folder))}/SingletonCookie && ln -s {shlex.quote(target)} \"$p/SingletonSocket\"\n"
                if case == "earlier":  # another browser's, there before this launch
                    subprocess.run(["sh", "-c", make.replace("$p", str(profile))], check=True)
                    make = ""
                # A stand-in for a browser that makes its singleton folder and a
                # DevTools port nothing answers on, then exits.
                launcher = scratch / f"launcher-{case}"
                launcher.write_text("#!/bin/sh\nfor a; do case \"$a\" in --user-data-dir=*) p=\"${a#--user-data-dir=}\";; esac; done\n" + make + "printf '1\\n/devtools/browser/none\\n' > \"$p/DevToolsActivePort\"\n", encoding="utf-8")
                launcher.chmod(0o755)
                started = time.monotonic()
                result = subprocess.run([NODE, str(DRIVER), "--browser", str(launcher), "--profile", str(profile), "--url", "about:blank"], capture_output=True, text=True, timeout=90, cwd=profile)
                elapsed = time.monotonic() - started
                out = json.loads(result.stdout.strip().splitlines()[-1])
                if "skip" in out:
                    self.skipTest(out["skip"])
                self.assertNotEqual(out["stopped"], "closed", case)
                self.assertLess(elapsed, 5, "the driver lingered after its browser had stopped")  # nothing answered, so no wait was needed
                self.assertEqual(folder.exists(), case != "own", f"the {case} singleton folder was {'kept' if case == 'own' else 'removed'}")


@unittest.skipUnless(hasattr(os, "getuid") and hasattr(os, "symlink"), "the cleanup recognises folders by owner and links, which needs POSIX")
class CleanupTest(unittest.TestCase):
    def test_a_fetcher_folder_outlives_the_span_a_running_browser_keeps_it(self) -> None:
        """A running Chrome removed its own fetcher folder 3.1 seconds after
        making it (measured), so the cleanup must not take one sooner, and must
        take one whose browser has ended."""
        gone: list[float] = []
        def watch(folder: Path) -> None:
            while folder.exists():
                time.sleep(0.02)
            gone.append(time.time())
        with no_fetcher_leftovers():
            folder = Path(tempfile.mkdtemp(prefix="com.example.Test.test_url_fetcher_.", dir=tempfile.gettempdir()))
            self.addCleanup(lambda: folder.exists() and folder.rmdir())
            made = folder.stat().st_mtime
            watcher = threading.Thread(target=watch, args=(folder,), daemon=True)
            watcher.start()
        sweep_fetcher_leftovers()
        watcher.join(5)
        self.assertTrue(gone, "the left-over fetcher folder was not removed")
        self.assertGreaterEqual(gone[0] - made, 3.1, "the folder was removed while a running browser could still remove it itself")

    def test_only_a_killed_browsers_own_singleton_folder_is_removed(self) -> None:
        """A killed browser's singleton folder holds SingletonSocket and
        SingletonCookie and is named by its profile's SingletonSocket link."""
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            def setup(name: str, *, extra: bool = False, relative: bool = False) -> tuple[Path, Path]:
                folder, profile = root / f"com.example.Test.{name}", root / f"profile-{name}"
                folder.mkdir(); profile.mkdir()
                (folder / "SingletonSocket").touch(); (folder / "SingletonCookie").touch()
                if extra:
                    (folder / "notes.txt").touch()
                os.symlink(os.path.relpath(folder / "SingletonSocket", profile) if relative else folder / "SingletonSocket", profile / "SingletonSocket")
                return folder, profile
            folder, profile = setup("own")
            remove_singleton(profile, None)
            self.assertFalse(folder.exists(), "the killed browser's own singleton folder was kept")
            folder, profile = setup("busy", extra=True)
            remove_singleton(profile, None)
            self.assertTrue(folder.exists(), "a singleton folder that holds more than the browser's entries was removed")
            folder, profile = setup("relative", relative=True)
            self.addCleanup(os.chdir, os.getcwd())
            os.chdir(profile)  # where the relative link would resolve to the folder
            remove_singleton(profile, None)
            self.assertTrue(folder.exists(), "a singleton folder named by a relative link was removed")
            folder, profile = setup("earlier")
            remove_singleton(profile, folder)
            self.assertTrue(folder.exists(), "a singleton folder the link named before the browser started was removed")

if __name__ == "__main__":
    unittest.main()
