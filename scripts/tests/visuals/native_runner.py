#!/usr/bin/env python3
"""Qualify the generated visual maintainer corpus in one existing Chromium page."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
import time
import urllib.request

from native_page import REPORT_READY


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PROJECT = ROOT / "plugins/agentic-design-and-evaluation"
DEFAULT_REPORTS = PROJECT / ".local/visual-tests/reports"
DEFAULT_OUTPUT = PROJECT / ".local/visual-tests/native-results.json"
FIXTURES = HERE / "mermaid-fixtures"


class RawCDP:
    def __init__(self, endpoint: str, target_id: str | None):
        import websocket
        pages = json.load(urllib.request.urlopen(endpoint.rstrip("/") + "/json/list"))
        candidates = [page for page in pages if page.get("type") == "page"]
        if target_id:
            candidates = [page for page in candidates if page.get("id") == target_id]
        if not candidates:
            raise RuntimeError("no existing page target matched; open or supply one, do not launch a browser")
        if not target_id and len(candidates) != 1:
            raise RuntimeError("multiple existing pages are available; supply --target-id for the page to qualify")
        page = candidates[0]
        self.target_id = page["id"]
        self._offline = False
        self.socket = websocket.create_connection(page["webSocketDebuggerUrl"], suppress_origin=True, timeout=60)
        self.sequence = 0
        self.events: list[dict] = []
        for method in ("Page.enable", "Runtime.enable", "Network.enable", "Log.enable"):
            self.call(method)
        self.call("Emulation.setFocusEmulationEnabled", enabled=True)

    def call(self, method: str, **params):
        self.sequence += 1
        self.socket.send(json.dumps({"id": self.sequence, "method": method, "params": params}))
        while True:
            message = json.loads(self.socket.recv())
            if message.get("id") == self.sequence:
                if "error" in message:
                    raise RuntimeError(f"{method}: {message['error']}")
                return message.get("result", {})
            self.events.append(message)

    def evaluate(self, expression: str):
        result = self.call("Runtime.evaluate", expression=expression, awaitPromise=True, returnByValue=True)
        if "exceptionDetails" in result:
            raise RuntimeError(result["exceptionDetails"])
        return result.get("result", {}).get("value")

    def navigate(self, url: str):
        self.call("Page.navigate", url=url)

    def viewport(self, width: int, height: int):
        self.call("Emulation.setDeviceMetricsOverride", width=width, height=height, deviceScaleFactor=1, mobile=False)

    def offline(self):
        self.call("Network.emulateNetworkConditions", offline=True, latency=0, downloadThroughput=0, uploadThroughput=0)
        self._offline = True

    def errors(self):
        return [
            event for event in self.events
            if event.get("method") == "Runtime.exceptionThrown"
            or event.get("method") == "Log.entryAdded"
            and event.get("params", {}).get("entry", {}).get("level") == "error"
        ]

    def network_requests(self):
        return [
            event.get("params", {}).get("request", {}).get("url")
            for event in self.events
            if event.get("method") == "Network.requestWillBeSent"
        ]

    def close(self):
        if self._offline:
            try:
                self.call("Network.emulateNetworkConditions", offline=False, latency=0, downloadThroughput=-1, uploadThroughput=-1)
            except Exception:
                pass
        self.socket.close()


class PlaywrightPage:
    def __init__(self, endpoint: str, target_id: str | None):
        from playwright.sync_api import sync_playwright
        if target_id:
            raise RuntimeError("--target-id is supported by raw CDP; Playwright connector uses the first existing page")
        self.manager = sync_playwright().start()
        self.browser = self.manager.chromium.connect_over_cdp(endpoint)
        pages = [page for context in self.browser.contexts for page in context.pages]
        if not pages:
            raise RuntimeError("Playwright connected but no existing page is available")
        if len(pages) != 1:
            self.manager.stop()
            raise RuntimeError("multiple existing pages are available; use raw CDP with an explicit --target-id")
        self.page = pages[0]
        self.target_id = "playwright:first-existing-page"
        self._errors: list[str] = []
        self._requests: list[str] = []
        self.page.on("pageerror", lambda error: self._errors.append(str(error)))
        self.page.on("console", lambda message: self._errors.append(message.text) if message.type == "error" else None)
        self.page.on("request", lambda request: self._requests.append(request.url))

    def evaluate(self, expression: str):
        return self.page.evaluate(expression)

    def navigate(self, url: str):
        self.page.goto(url, wait_until="load", timeout=120000)

    def viewport(self, width: int, height: int):
        self.page.set_viewport_size({"width": width, "height": height})

    def offline(self):
        # Do not mutate the shared connected context for other existing pages.
        return None

    def errors(self):
        return list(self._errors)

    def network_requests(self):
        return list(self._requests)

    def close(self):
        # Stopping the local Playwright client disconnects from a browser that
        # this runner did not launch. Browser.close() would terminate that
        # shared external process and is therefore intentionally not used.
        self.manager.stop()


def wait_for(page, expression: str, timeout: float = 120.0):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = page.evaluate(expression)
        if last:
            return last
        time.sleep(0.05)
    raise RuntimeError(f"browser wait timed out; last value: {last!r}")


def load_ready(page, filename: Path):
    url = filename.resolve().as_uri()
    page.navigate(url)
    return wait_for(
        page,
        "location.href.split('#')[0]===" + json.dumps(url) + " && " + REPORT_READY,
        timeout=240,
    )


def fixture_key(filename: str) -> str:
    """The block id render_corpus.cjs gives a fixture's diagram."""
    return "fixture-" + re.sub(r"[^a-zA-Z0-9_-]+", "-", filename).strip("-")


def qualify(page, reports: Path, fixture_root: Path) -> dict:
    checks: list[dict] = []

    def check(name: str, truth, detail=None):
        checks.append({"name": name, "passed": bool(truth), "detail": detail})
        if not truth:
            raise AssertionError(f"{name}: {detail}")

    for name in ("fictional-trial", "fictional-trial-bare", "showcase", "mermaid-layouts"):
        print(f"qualifying {name}", flush=True)
        load_ready(page, reports / f"{name}.html")
        summary = page.evaluate(
            """(()=>({sections:document.querySelectorAll('[data-av-report] .av-section').length,errors:document.querySelectorAll('.av-block-error').length,overflow:document.documentElement.scrollWidth-window.innerWidth}))()"""
        )
        check(f"{name} mounts its sections", summary["sections"] > 0, summary)
        check(f"{name} renders every block", summary["errors"] == 0, summary)
        check(f"{name} page containment", summary["overflow"] <= 2, summary)

    print("qualifying mermaid-gallery", flush=True)
    load_ready(page, reports / "mermaid-gallery.html")
    index = json.loads((fixture_root / "index.json").read_text(encoding="utf-8"))
    keys = {fixture_key(item["file"]): item["file"] for item in index}
    records = page.evaluate(
        """(()=>[...document.querySelectorAll('.av-block--diagram[id^="fixture-"]')].map(block=>{const diagram=block.querySelector('[data-av-mermaid]'),svg=diagram?.querySelector('[data-av-mermaid-output] svg[data-av-mermaid-scene]'),figure=diagram?.closest('[data-av-figure]');return{key:block.id,head:block.querySelector('.av-block-head')?.textContent||'',state:diagram?.getAttribute('data-av-mermaid-state'),status:diagram?.querySelector('[data-av-mermaid-status]')?.textContent||'',source:diagram?.getAttribute('data-av-mermaid-source')||'',inlineSource:diagram?.querySelector('.av-diagram-source pre')?.textContent||'',retainedSource:JSON.parse(figure?.getAttribute('data-av-source')||'null')?.text,svgCount:diagram?.querySelectorAll('[data-av-mermaid-output] svg[data-av-mermaid-scene]').length||0,named:!!(svg&&(svg.getAttribute('aria-label')?.trim()||svg.getAttribute('aria-labelledby')?.trim()||svg.querySelector('title')?.textContent?.trim())),width:Number(svg?.getAttribute('width')||0),height:Number(svg?.getAttribute('height')||0),items:diagram?.querySelectorAll('[data-av-mermaid-item]').length||0,text:svg?.textContent||''};}))()"""
    )
    for record in records:
        record["file"] = keys.get(record["key"])
    by_file = {record["file"]: record for record in records}
    check("all fixture blocks present", set(by_file) == {item["file"] for item in index}, sorted(record["key"] for record in records))
    for item in index:
        record = by_file[item["file"]]
        check("visible expected state: " + item["file"], f"Expected renderer state: {item['expectedState']}" in record["head"], record["head"])
        if item.get("visualLimitation"):
            check("visible limitation: " + item["file"], item["visualLimitation"] in record["head"], record["head"])
        source = (fixture_root / item["file"]).read_bytes().decode("utf-8")
        check("exact source: " + item["file"], record["source"] == record["inlineSource"] == record["retainedSource"] == source)
        check("expected native state: " + item["file"], record["state"] == item["expectedState"], record)
        if record["state"] == "error":
            diagnostic = item.get("expectedDiagnostic")
            check("classified diagnostic: " + item["file"],
                  isinstance(diagnostic, str) and bool(diagnostic) and diagnostic in record["status"],
                  {"expected": diagnostic, "actual": record["status"], "kind": item.get("failureKind")})
        if record["state"] == "ready":
            # SVG/HTML line wrapping can split a logical label across nodes.
            # Source bytes are checked separately; this check guards evidence
            # silently discarded by otherwise-successful family parsers.
            compact_text = "".join(record["text"].split())
            missing_labels = [label for label in item.get("expectedRenderedLabels", [])
                              if "".join(label.split()) not in compact_text]
            if item.get("expectedRenderedLabels"):
                check("rendered evidence labels: " + item["file"], not missing_labels, missing_labels)
            check("one SVG: " + item["file"], record["svgCount"] == 1, record)
            check("positive bounds: " + item["file"], record["width"] > 0 and record["height"] > 0, record)
            check("accessible name: " + item["file"], record["named"], item["family"])
        record.pop("text")

    containment = page.evaluate("(()=>({overflow:document.documentElement.scrollWidth-window.innerWidth,visible:[...document.querySelectorAll('[data-av-figure]')].filter(e=>e.getClientRects().length).length}))()")
    check("gallery page containment", containment["overflow"] <= 2, containment)

    print("qualifying mixed-components", flush=True)
    load_ready(page, reports / "mixed-components.html")
    mixed = page.evaluate(
        """(()=>({mermaid:document.querySelectorAll('[data-av-mermaid]').length,ready:document.querySelectorAll('[data-av-mermaid][data-av-mermaid-state="ready"]').length,tables:document.querySelectorAll('.av-block--table table').length,matrices:document.querySelectorAll('.av-block--matrix table').length,intervals:document.querySelectorAll('.av-block--ladder').length,excerpts:document.querySelectorAll('.av-block--excerpts').length,errors:document.querySelectorAll('.av-block-error').length,overflow:document.documentElement.scrollWidth-window.innerWidth}))()"""
    )
    check("mixed report combines components", mixed["mermaid"] >= 3 and mixed["ready"] == mixed["mermaid"] and mixed["tables"] >= 1 and mixed["matrices"] >= 1 and mixed["intervals"] >= 1 and mixed["excerpts"] >= 1 and mixed["errors"] == 0, mixed)
    check("mixed report containment", mixed["overflow"] <= 2, mixed)
    check("no page exceptions", not page.errors(), page.errors())
    check("no HTTP(S) runtime requests", not any(url.startswith(("http:", "https:")) for url in page.network_requests()))

    return {
        "target": page.target_id,
        "checks": checks,
        "fixtures": records,
        "pageErrors": page.errors(),
        "networkRequests": [
            {"embedded": url.split(",", 1)[0], "characters": len(url), "sha256": hashlib.sha256(url.encode()).hexdigest()}
            if url.startswith("data:") else url for url in page.network_requests()
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports", type=Path, default=DEFAULT_REPORTS)
    parser.add_argument("--fixtures", type=Path, default=FIXTURES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--cdp", required=True, help="Debugger endpoint of an existing Chromium process")
    parser.add_argument("--target-id")
    parser.add_argument("--engine", choices=["auto", "cdp", "playwright"], default="auto")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=900)
    args = parser.parse_args()

    reports = args.reports.resolve()
    fixtures = args.fixtures.resolve()
    if not reports.is_dir():
        print(f"error: reports directory not found: {reports}")
        return 2

    inputs = {"reports": {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(reports.glob("*.html"))},
              "fixtures": {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(fixtures.glob("*.mmd"))}}
    page = None
    result = {"inputs": inputs}
    try:
        if args.engine in {"auto", "cdp"}:
            try:
                page = RawCDP(args.cdp, args.target_id)
            except ImportError:
                if args.engine == "cdp":
                    raise
        if page is None:
            page = PlaywrightPage(args.cdp, args.target_id)
        page.viewport(args.width, args.height)
        if isinstance(page, RawCDP):
            page.offline()
        result.update(qualify(page, reports, fixtures))
        result["status"] = "passed"
    except Exception as error:
        result["status"] = "failed"
        result["failure"] = {"type": type(error).__name__, "message": str(error)}
        if page:
            result["target"] = page.target_id
            result["pageErrors"] = page.errors()
            try:
                screenshot = args.output.with_suffix(".failure.png")
                screenshot.parent.mkdir(parents=True, exist_ok=True)
                if isinstance(page, RawCDP):
                    screenshot.write_bytes(base64.b64decode(page.call("Page.captureScreenshot", format="png")["data"]))
                else:
                    page.page.screenshot(path=str(screenshot))
                result["screenshot"] = str(screenshot)
            except Exception:
                pass
    finally:
        if page:
            page.close()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": result["status"], "target": result.get("target"), "checks": len(result.get("checks", [])), "pageErrors": len(result.get("pageErrors", [])), "output": str(args.output),
                      **({"error": result["failure"]["message"][:400]} if "failure" in result else {})}, ensure_ascii=False))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
