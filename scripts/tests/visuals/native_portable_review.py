#!/usr/bin/env python3
"""Qualify concurrent drafts and portable review using an existing Chrome process.

Creates one small report from the maintained runtime, then uses actual mouse and
keyboard input in owned file tabs. Downloads are captured as their generated
Blob/data bytes; this does not qualify the operating system's save dialog.
"""
from __future__ import annotations

import argparse
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import subprocess
import sys
import urllib.parse

from native_inspector import NativePage, file_record, require
from native_runner import install_blob_capture

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[2] / "plugins/agentic-design-and-evaluation"
VISUALS = PROJECT / "skills/split-testing/assets/visuals"
SAVED = "Saved note α: preserve the exact 4 s observation."
COMPLETED = "Completed sibling β: qualification remains limited to this record."
DRAFT = "Draft γ: unresolved comparison; retain the earlier saved note.\nLiteral <script> and ``` fences remain feedback."


class JsonScript(HTMLParser):
    def __init__(self, wanted: str):
        super().__init__()
        self.wanted, self.capture, self.parts = wanted, False, []

    def handle_starttag(self, tag, attrs):
        if tag == "script" and dict(attrs).get("id") == self.wanted:
            self.capture = True

    def handle_endtag(self, tag):
        if tag == "script":
            self.capture = False

    def handle_data(self, data):
        if self.capture:
            self.parts.append(data)


def script_json(path: Path, script_id: str):
    parser = JsonScript(script_id)
    parser.feed(path.read_text(encoding="utf-8"))
    return json.loads("".join(parser.parts))


def assemble(output: Path) -> Path:
    # A dedicated storage key isolates this generated fixture from other reports.
    storage_key = "av-portable-test-" + hashlib.sha256(str(output).encode()).hexdigest()[:20]
    generator = output / "render-fixture.cjs"
    generator.write_text("""const fs=require('node:fs'),vm=require('node:vm');
const scope={console};vm.createContext(scope);vm.runInContext(fs.readFileSync(process.argv[2],'utf8'),scope);
const V=scope.AgenticVisuals;
const body=V.evidenceWorkspace({id:'portable-review-qualification',title:'Portable review qualification',theme:'light',
  notebook:{revision:'fixture-1',storageKey:process.argv[4]},
  brief:{question:'Does a stale draft retain the saved note and exact evidence it was based on?'},
  views:[{id:'evidence',label:'Retained evidence',body:V.storyPanel({id:'portable-record',title:'Original observation',
    paragraphs:['Record α: execution 4 s; handoff unavailable. Repeated labels are not identities.'],
    evidence:[{label:'Original synthetic record',href:'#portable-source'}]})+'<aside id="portable-source">record: alpha-1; execution: 4 s; handoff: unavailable; scope: one observation.</aside>'}]});
fs.writeFileSync(process.argv[3],body,'utf8');
""", encoding="utf-8")
    subprocess.run(["node", str(generator), str(VISUALS / "dist/agentic-visuals.js"), str(output / "body.html"), storage_key], check=True)
    (output / "enhance.js").write_text("AgenticVisuals.enhanceVisuals(document.querySelector('.av-workspace'));\n", encoding="utf-8")
    report = output / "original.html"
    subprocess.run([sys.executable, str(VISUALS / "assemble.py"), "--body", str(output / "body.html"),
                    "--style", str(VISUALS / "styles/agentic-visuals.css"), "--script", str(VISUALS / "dist/agentic-visuals.js"),
                    "--script", str(output / "enhance.js"), "--title", "Portable review qualification", "--output", str(report)], check=True)
    return report


def load(page: NativePage, path: Path):
    page.call("Network.emulateNetworkConditions", offline=True, latency=0, downloadThroughput=0, uploadThroughput=0)
    page.viewport(1280, 900)
    page.navigate(path)
    page.wait("!!document.querySelector('.av-workspace[data-av-ready]') && !document.documentElement.hasAttribute('data-av-starting')", timeout=30)
    page.evaluate("window.__nativeInspectorCleanup=AgenticVisuals.enhanceVisuals(document.querySelector('.av-workspace'));true")
    page.settle()


def tab(page: NativePage, name: str):
    if not page.evaluate("document.querySelector('[data-av-notebook]').open"):
        page.click("document.querySelector('[data-av-notebook] > summary')")
    page.click("document.querySelector('[data-av-notebook-tab=" + json.dumps(name) + "]')")


def type_note(page: NativePage, text: str):
    if page.evaluate("document.querySelector('[data-av-notebook]').open"):
        page.click("document.querySelector('[aria-label=\"Close notebook\"]')")
    page.click("document.querySelector('.av-context-review:not([hidden]) textarea')")
    page.call("Input.dispatchKeyEvent", type="keyDown", key="a", code="KeyA", windowsVirtualKeyCode=65, modifiers=2)
    page.call("Input.dispatchKeyEvent", type="keyUp", key="a", code="KeyA", windowsVirtualKeyCode=65, modifiers=2)
    page.call("Input.insertText", text=text)
    require(page.evaluate("document.querySelector('.av-context-review textarea').value") == text, "Native text input changed the note")


def backup(page: NativePage) -> dict:
    tab(page, "share")
    page.click("document.querySelector('[data-av-notebook-action=\"export\"]')")
    href = page.wait("(()=>{const a=document.querySelector('[data-av-notebook-action=\"download\"]');return !a.hidden&&a.getAttribute('href')?.startsWith('data:')?a.getAttribute('href'):null})()")
    return json.loads(urllib.parse.unquote(href.split(",", 1)[1]))


def captured_export(page: NativePage, action: str, path: Path):
    tab(page, "share")
    install_blob_capture(page)
    before = page.evaluate("window.__round2Capture.downloads.length")
    page.click("document.querySelector('[data-av-notebook-action=" + json.dumps(action) + "]')")
    item = page.wait(f"window.__round2Capture.downloads[{before}]||null")
    text = page.evaluate(f"window.__round2Capture.blobs[{item['blobIndex']}].text()")
    path.write_text(text, encoding="utf-8", newline="")
    return text


def cards(page: NativePage):
    return page.evaluate("""[...document.querySelectorAll('[data-av-review-entry]')].map(e=>({
      version:e.getAttribute('data-av-note-version'),state:e.getAttribute('data-av-entry-state'),
      notes:[...e.querySelectorAll('.av-notebook-note')].map(n=>n.textContent),
      badges:[...e.querySelectorAll('.av-review-badge')].map(n=>n.textContent),
      supporting:[...e.querySelectorAll('[data-av-supporting-version]')].map(n=>n.getAttribute('data-av-supporting-version'))}))""")


def qualify(args, results: dict):
    report = assemble(args.output)
    results["inputs"] = {"report": file_record(report), "runtime": file_record(VISUALS / "dist/agentic-visuals.js"), "css": file_record(VISUALS / "styles/agentic-visuals.css")}
    pages = []
    try:
        first = NativePage(args.cdp); pages.append(first)
        load(first, report)
        first.click("document.querySelector('#portable-record [data-av-review-action=\"new-note\"]')")
        type_note(first, SAVED)
        first.click("document.querySelector('.av-context-review [data-av-review-action=\"save\"]')")
        first.settle()
        saved = backup(first)
        base = saved["review"]["versions"][0]
        require(base["text"] == SAVED, "Saved annotation did not retain exact text")
        print("saved original annotation", flush=True)

        second = NativePage(args.cdp); pages.append(second)
        load(second, report)
        tab(second, "notes")
        second.click("document.querySelector('[data-av-review-entry] [data-av-review-action=\"edit\"]')")
        require(second.evaluate("document.querySelector('.av-context-review textarea').value") == SAVED, "Second file tab did not restore the saved annotation")
        tab(first, "notes")
        first.click("document.querySelector('[data-av-review-entry] [data-av-review-action=\"edit\"]')")
        type_note(first, COMPLETED)
        first.click("document.querySelector('.av-context-review [data-av-review-action=\"save\"]')")
        first.settle()
        completed = backup(first)
        require([v["text"] for v in completed["review"]["versions"]] == [COMPLETED], "Completed edit left superseded text active")
        # Export refreshes the stale tab's notebook while preserving its live edit.
        backup(second)
        require(second.evaluate("document.querySelector('.av-context-review textarea').value") == SAVED, "Background refresh rewrote the stale editor")
        type_note(second, DRAFT)
        second.click("document.querySelector('.av-context-review [data-av-review-action=\"draft\"]')")
        second.settle()
        draft_book = backup(second)
        review = draft_book["review"]
        require({v["text"] for v in review["versions"]} == {COMPLETED, DRAFT}, "A completed sibling or stale draft disappeared")
        require(review.get("supportingVersions") == [base], "Earlier saved note or its exact evidence changed")
        draft = next(v for v in review["versions"] if v["draft"])
        require(base["id"] in draft.get("baseIds", []), "Draft lost its actual saved base")
        (args.output / "notebook.json").write_text(json.dumps(draft_book, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        tab(second, "notes")
        original_cards = cards(second)
        require(any(DRAFT in c["notes"] and SAVED in c["notes"] for c in original_cards), "Draft UI does not expose the earlier saved note")
        support = "document.querySelector('[data-av-supporting-version] > summary')"
        if second.evaluate(support + " !== null"):
            second.click(support)
        second.screenshot(args.output / "concurrent-draft.png")
        print("retained concurrent draft, completed sibling and earlier saved evidence", flush=True)

        reviewed_path = args.output / "reviewed.html"
        captured_export(second, "export-report", reviewed_path)
        handoff = captured_export(second, "export-handoff", args.output / "handoff.md")
        original_recipe = script_json(report, "av-report-recipe")
        reviewed_recipe = script_json(reviewed_path, "av-report-recipe")
        seed = script_json(reviewed_path, "av-review-seed")
        portable = next(iter(seed["reports"].values()))["review"]
        require(original_recipe == reviewed_recipe, "Reviewed HTML changed the original assembly recipe")
        require("av-context-review" not in reviewed_recipe["body"] and "data-av-expanded-figure" not in reviewed_recipe["body"], "Reviewed recipe serialized temporary UI")
        require(portable["versions"] == review["versions"] and portable.get("supportingVersions") == [base], "Reviewed HTML lost draft/sibling/base context")
        require(all(text in handoff for text in [SAVED, COMPLETED, DRAFT, "Earlier saved note", "execution 4 s", "handoff unavailable"]), "Markdown handoff lost exact note or evidence content")

        # Reopen the actual exported bytes in an offline file tab; startup is
        # supplied by the retained recipe, not manually serialized live controls.
        load(first, reviewed_path)
        tab(first, "notes")
        reopened = cards(first)
        require(reopened == original_cards, "Reopened review changed notes, badges, supporting versions or attachment state")
        counts = first.evaluate("({notebooks:document.querySelectorAll('[data-av-notebook]').length,headers:document.querySelectorAll('.av-notebook-header').length,seed:document.querySelectorAll('#av-review-seed').length,recipe:document.querySelectorAll('#av-report-recipe').length})")
        require(all(value == 1 for value in counts.values()), f"Reopened report has duplicate controls or retained seeds: {counts}")
        first.viewport(390, 520); first.settle()
        first.screenshot(args.output / "reopened-review-narrow.png")
        results.update({"status": "passed", "baseVersion": base, "draftReview": review, "originalCards": original_cards,
                        "reopenedCards": reopened, "counts": counts, "artifacts": {name: file_record(args.output / name) for name in ["notebook.json", "reviewed.html", "handoff.md"]}})
        for page in pages:
            require(not page.console_errors(), "Native portable review raised a page exception")
            urls = [event.get("params", {}).get("request", {}).get("url", "") for event in page.events if event.get("method") == "Network.requestWillBeSent"]
            require(not any(url.startswith(("http:", "https:")) for url in urls), "Portable review attempted a network request")
        print("reviewed HTML and Markdown preserve full context; offline reopen has no duplicate controls", flush=True)
    except Exception:
        for index, page in enumerate(pages):
            try:
                page.screenshot(args.output / f"failure-{index}.png")
                results[f"failureCards{index}"] = cards(page)
            except Exception:
                pass
        raise
    finally:
        for page in pages:
            page.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cdp", required=True, help="Debugger endpoint of an existing Chromium process")
    parser.add_argument("--output", type=Path, required=True, help="New empty output directory")
    args = parser.parse_args()
    args.output = args.output.resolve()
    if args.output.exists() and any(args.output.iterdir()):
        parser.error("output must be a new or empty dedicated directory")
    args.output.mkdir(parents=True, exist_ok=True)
    results = {"test": file_record(Path(__file__).resolve())}
    try:
        qualify(args, results)
        return 0
    except Exception as error:
        results["failure"] = {"type": type(error).__name__, "message": str(error)}
        print(f"error: {error}", file=sys.stderr)
        return 1
    finally:
        (args.output / "results.json").write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
