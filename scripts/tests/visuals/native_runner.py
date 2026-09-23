#!/usr/bin/env python3
"""Qualify the generated visual maintainer corpus in one existing Chromium page."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path
import time
import urllib.request


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

    def click(self, selector: str):
        point = self.evaluate(
            f"""(async()=>{{const e=document.querySelector({json.dumps(selector)});if(!e)throw Error('Missing click target');
              e.scrollIntoView({{block:'center',inline:'nearest'}});await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));
              const r=e.getBoundingClientRect(),x=r.x+r.width/2,y=r.y+r.height/2,hit=document.elementFromPoint(x,y);
              if(r.width<=0||r.height<=0||!hit||!(hit===e||e.contains(hit)))throw Error('Click target is hidden or obstructed: '+{json.dumps(selector)});
              return{{x,y}};}})()"""
        )
        self.call("Input.dispatchMouseEvent", type="mousePressed", button="left", clickCount=1, **point)
        self.call("Input.dispatchMouseEvent", type="mouseReleased", button="left", clickCount=1, **point)

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

    def click(self, selector: str):
        self.page.locator(selector).first.click(timeout=15000)

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
        """(()=>{const roots=[...document.querySelectorAll('.av-workspace,.av-surface')].filter(e=>!e.parentElement?.closest('.av-workspace,.av-surface'));return location.href.split('#')[0]===""" + json.dumps(url) + """&&document.readyState==='complete'&&roots.length>0&&roots.every(e=>e.hasAttribute('data-av-enhanced')&&(!e.matches('.av-workspace')||e.hasAttribute('data-av-ready')))&&[...document.querySelectorAll('[data-av-mermaid]')].every(e=>['ready','error'].includes(e.getAttribute('data-av-mermaid-state')))&&![...document.querySelectorAll('[data-av-notebook-status]')].some(e=>e.textContent.includes('Enable JavaScript'))})()""",
        timeout=240,
    )


def install_blob_capture(page):
    page.evaluate(
        """(()=>{if(window.__round2Capture)return;window.__round2Capture={blobs:[],downloads:[]};const originalCreate=URL.createObjectURL.bind(URL),originalClick=HTMLAnchorElement.prototype.click;URL.createObjectURL=function(blob){window.__round2Capture.blobs.push(blob);return originalCreate(blob);};HTMLAnchorElement.prototype.click=function(){if(this.hasAttribute('data-av-internal-download')){window.__round2Capture.downloads.push({name:this.download,blobIndex:window.__round2Capture.blobs.length-1});return;}return originalClick.call(this);};})()"""
    )


def capture_export(page, action: str):
    install_blob_capture(page)
    before = page.evaluate("window.__round2Capture.downloads.length")
    figure = '[data-round2-fixture="flowchart-v2.mmd"] [data-av-figure]'
    if not page.evaluate(f"document.querySelector({json.dumps(figure + ' .av-command-overflow')})?.open"):
        page.click(figure + " .av-command-overflow > summary")
    page.click(figure + f' [data-av-figure-action="{action}"]')
    item = wait_for(page, f"window.__round2Capture.downloads[{before}]||null", timeout=30)
    return page.evaluate(
        f"""(async()=>{{const blob=window.__round2Capture.blobs[{item['blobIndex']}];let decoded=null;
          if(blob.type==='image/png'){{const image=await createImageBitmap(blob);decoded={{width:image.width,height:image.height}};image.close();}}
          return{{name:{json.dumps(item['name'])},type:blob.type,size:blob.size,text:{'await blob.text()' if action == 'svg' else 'null'},decoded}};}})()"""
    )


def qualify(page, reports: Path, fixture_root: Path) -> dict:
    checks: list[dict] = []

    def check(name: str, truth, detail=None):
        checks.append({"name": name, "passed": bool(truth), "detail": detail})
        if not truth:
            raise AssertionError(f"{name}: {detail}")

    for name in ("field-study", "compact", "embedded", "stress", "snippets", "mermaid-layouts"):
        print(f"qualifying {name}", flush=True)
        load_ready(page, reports / f"{name}.html")
        summary = page.evaluate(
            """(()=>({roots:[...document.querySelectorAll('.av-workspace,.av-surface')].filter(e=>!e.parentElement?.closest('.av-workspace,.av-surface')).length,ready:[...document.querySelectorAll('.av-workspace,.av-surface')].filter(e=>!e.parentElement?.closest('.av-workspace,.av-surface')).every(e=>e.hasAttribute('data-av-enhanced')&&(!e.matches('.av-workspace')||e.hasAttribute('data-av-ready'))),overflow:document.documentElement.scrollWidth-window.innerWidth}))()"""
        )
        check(f"{name} auto-enhances", summary["ready"] and summary["roots"] > 0, summary)
        check(f"{name} page containment", summary["overflow"] <= 2, summary)

    print("qualifying mermaid-gallery", flush=True)
    load_ready(page, reports / "mermaid-gallery.html")
    count = len(json.loads((fixture_root / "index.json").read_text(encoding="utf-8")))
    wait_for(
        page,
        f"""(()=>{{const nodes=[...document.querySelectorAll('[data-round2-fixture] [data-av-mermaid]')];return nodes.length==={count}&&nodes.every(node=>['ready','error'].includes(node.getAttribute('data-av-mermaid-state')))}})()""",
        timeout=240,
    )
    records = page.evaluate(
        """(()=>[...document.querySelectorAll('[data-round2-fixture]')].map(section=>{const diagram=section.querySelector('[data-av-mermaid]'),svg=diagram?.querySelector('[data-av-mermaid-output] svg[data-av-mermaid-scene]'),viewport=diagram?.querySelector('.av-plot-scroll'),figure=diagram?.closest('[data-av-figure]');return{file:section.getAttribute('data-round2-fixture'),family:section.getAttribute('data-round2-family'),expected:section.getAttribute('data-round2-expected'),state:diagram?.getAttribute('data-av-mermaid-state'),status:diagram?.querySelector('[data-av-mermaid-status]')?.textContent||'',source:diagram?.getAttribute('data-av-mermaid-source')||'',inlineSource:diagram?.querySelector('.av-diagram-source pre')?.textContent||'',retainedSource:JSON.parse(figure?.getAttribute('data-av-source')||'null')?.text,svgCount:diagram?.querySelectorAll('[data-av-mermaid-output] svg[data-av-mermaid-scene]').length||0,named:svg?.getAttribute('aria-label')===figure?.getAttribute('data-av-figure-title'),width:Number(svg?.getAttribute('width')||0),height:Number(svg?.getAttribute('height')||0),items:diagram?.querySelectorAll('[data-av-mermaid-item]').length||0,scrollContained:!viewport||viewport.scrollWidth>=viewport.clientWidth};}))()"""
    )
    index = json.loads((fixture_root / "index.json").read_text(encoding="utf-8"))
    by_file = {record["file"]: record for record in records}
    visual_notes = page.evaluate(
        """Object.fromEntries([...document.querySelectorAll('[data-round2-fixture]')].map(section=>[section.getAttribute('data-round2-fixture'),section.querySelector('[data-round2-visual-limitation]')?.textContent||'']))"""
    )
    rendered_text = page.evaluate(
        """Object.fromEntries([...document.querySelectorAll('[data-round2-fixture]')].map(section=>[section.getAttribute('data-round2-fixture'),section.querySelector('svg[data-av-mermaid-scene]')?.textContent||'']))"""
    )
    check("all fixture sections present", set(by_file) == {item["file"] for item in index}, sorted(by_file))
    for item in index:
        record = by_file[item["file"]]
        record["visualLimitation"] = visual_notes.get(item["file"], "")
        if item.get("visualLimitation"):
            check("visible limitation: " + item["file"],
                  item["visualLimitation"] in record["visualLimitation"], record["visualLimitation"])
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
            compact_text = "".join(rendered_text.get(item["file"], "").split())
            missing_labels = [label for label in item.get("expectedRenderedLabels", [])
                              if "".join(label.split()) not in compact_text]
            if item.get("expectedRenderedLabels"):
                check("rendered evidence labels: " + item["file"], not missing_labels, missing_labels)
            check("one SVG: " + item["file"], record["svgCount"] == 1, record)
            check("positive bounds: " + item["file"], record["width"] > 0 and record["height"] > 0, record)
            check("accessible name: " + item["file"], record["named"], record["family"])

    containment = page.evaluate("(()=>({overflow:document.documentElement.scrollWidth-window.innerWidth,visible:[...document.querySelectorAll('[data-av-figure]')].filter(e=>e.getClientRects().length).length}))()")
    check("gallery page containment", containment["overflow"] <= 2, containment)

    figure = '[data-round2-fixture="flowchart-v2.mmd"] [data-av-figure]'
    page.click(figure + " [data-av-mode-menu]")
    page.click(figure + ' [data-av-figure-action="select-items"]')
    selectable = page.evaluate("""(()=>{const item=document.querySelector('[data-round2-fixture="flowchart-v2.mmd"] .node[data-av-mermaid-item]');if(!item)return null;item.setAttribute('data-round2-native-target','');return {label:item.getAttribute('aria-label')||item.textContent};})()""")
    check("flowchart exposes a selectable node", selectable is not None)
    if selectable:
        page.click("[data-round2-native-target]")
        selected = page.evaluate("document.querySelector('[data-round2-native-target]')?.hasAttribute('data-av-item-selected')||document.querySelector('[data-round2-native-target]')?.getAttribute('aria-pressed')==='true'")
        check("native Mermaid item interaction", selected, selectable)

    svg_export = capture_export(page, "svg")
    check("SVG export returns complete artifact", svg_export["type"].startswith("image/svg+xml") and svg_export["size"] > 100 and "<svg" in (svg_export["text"] or ""), svg_export)
    png_export = capture_export(page, "png")
    check("PNG export returns decoded raster artifact", png_export["type"] == "image/png" and png_export["size"] > 100 and png_export["decoded"]["width"] > 0 and png_export["decoded"]["height"] > 0, png_export)

    print("qualifying mixed-components", flush=True)
    load_ready(page, reports / "mixed-components.html")
    wait_for(page, "(()=>[...document.querySelectorAll('[data-av-mermaid]')].every(node=>['ready','error'].includes(node.getAttribute('data-av-mermaid-state'))))()")
    mixed = page.evaluate(
        """(()=>({mermaid:document.querySelectorAll('[data-av-mermaid]').length,paired:document.querySelectorAll('[data-av-layout-kind="paired"]').length,scatter:document.querySelectorAll('[data-av-layout-kind="scatter"]').length,tables:document.querySelectorAll('[data-av-frame="comparison"] table').length,explorers:document.querySelectorAll('[data-av-explorer]').length,overflow:document.documentElement.scrollWidth-window.innerWidth}))()"""
    )
    check("mixed report combines components", mixed["mermaid"] >= 3 and mixed["paired"] >= 1 and mixed["scatter"] >= 1 and mixed["tables"] >= 1 and mixed["explorers"] >= 1, mixed)
    check("mixed report containment", mixed["overflow"] <= 2, mixed)
    check("no page exceptions", not page.errors(), page.errors())
    check("no HTTP(S) runtime requests", not any(url.startswith(("http:", "https:")) for url in page.network_requests()))

    return {
        "target": page.target_id,
        "checks": checks,
        "fixtures": records,
        "svgExport": svg_export,
        "pngExport": png_export,
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
