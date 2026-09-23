#!/usr/bin/env python3
"""Native Chrome regression for the visual evidence inspector.

The script attaches to an already-running Chrome DevTools endpoint. It never
launches a browser and does not depend on project-local scratch helpers.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path
import sys
import time
import urllib.parse
import urllib.request

import websocket


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PROJECT = ROOT / "plugins/agentic-design-and-evaluation"
VISUALS = PROJECT / "skills/split-testing/assets/visuals"
DEFAULT_CDP = "http://127.0.0.1:38255"
DEFAULT_REPORTS = PROJECT / ".local/visual-tests/reports"
DEFAULT_OUTPUT = PROJECT / ".local/visual-tests/native-inspector"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def file_record(path: Path) -> dict[str, object]:
    payload = path.read_bytes()
    return {
        "path": str(path),
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def normalized_endpoint(value: str) -> str:
    value = value.strip().rstrip("/")
    if "://" not in value:
        value = "http://" + value
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("--cdp must be an HTTP(S) Chrome DevTools endpoint")
    return value


def read_json(url: str, *, method: str = "GET") -> dict:
    request = urllib.request.Request(url, method=method)
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response)


class NativePage:
    """One owned page target in an existing Chrome process."""

    def __init__(self, endpoint: str):
        self.endpoint = normalized_endpoint(endpoint)
        created = read_json(self.endpoint + "/json/new?about:blank", method="PUT")
        self.target_id = created["id"]
        self.socket = websocket.create_connection(
            created["webSocketDebuggerUrl"],
            suppress_origin=True,
            timeout=45,
        )
        self.sequence = 0
        self.events: list[dict] = []
        for method in ("Page.enable", "Runtime.enable", "Network.enable", "Log.enable"):
            self.call(method)
        self.call("Emulation.setFocusEmulationEnabled", enabled=True)

    def call(self, method: str, **params):
        self.sequence += 1
        request_id = self.sequence
        self.socket.send(json.dumps({"id": request_id, "method": method, "params": params}))
        while True:
            message = json.loads(self.socket.recv())
            if message.get("id") == request_id:
                if "error" in message:
                    raise RuntimeError(f"{method}: {message['error']}")
                return message.get("result", {})
            self.events.append(message)

    def evaluate(self, expression: str):
        result = self.call(
            "Runtime.evaluate",
            expression=expression,
            awaitPromise=True,
            returnByValue=True,
        )
        if "exceptionDetails" in result:
            details = result["exceptionDetails"]
            description = details.get("exception", {}).get("description") or details.get("text") or str(details)
            preview = " ".join(expression.strip().split())[:420]
            raise RuntimeError(f"{description}; expression={preview}")
        return result.get("result", {}).get("value")

    def viewport(self, width: int, height: int) -> None:
        self.call(
            "Emulation.setDeviceMetricsOverride",
            width=width,
            height=height,
            deviceScaleFactor=1,
            mobile=False,
        )

    def navigate(self, path: Path) -> None:
        url = path.resolve().as_uri() + "?native-inspector=1"
        self.call("Page.navigate", url=url)
        self.wait("location.href.split('#')[0] === " + json.dumps(url) + " && document.readyState === 'complete'", timeout=30)

    def wait(self, expression: str, *, timeout: float = 20, interval: float = 0.05):
        deadline = time.monotonic() + timeout
        last = None
        while time.monotonic() < deadline:
            last = self.evaluate(expression)
            if last:
                return last
            time.sleep(interval)
        raise TimeoutError(f"Timed out waiting for {expression}; last={last!r}")

    def settle(self) -> None:
        self.evaluate(
            """(async()=>{
              if (globalThis.__nativeInspectorCleanup?.whenIdle) await globalThis.__nativeInspectorCleanup.whenIdle();
              await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
            })()"""
        )
        time.sleep(0.05)

    def key(self, key: str, *, code: str | None = None) -> None:
        code = code or key
        virtual = {"Escape": 27, "Enter": 13, " ": 32}.get(key)
        fields = {"key": key, "code": code}
        if virtual is not None:
            fields.update({"windowsVirtualKeyCode": virtual, "nativeVirtualKeyCode": virtual})
        self.call("Input.dispatchKeyEvent", type="keyDown", **fields)
        self.call("Input.dispatchKeyEvent", type="keyUp", **fields)
        self.settle()

    def _point(self, element_expression: str, *, scroll: bool = True) -> dict:
        scroll_line = "e.scrollIntoView({block:'center',inline:'center'});" if scroll else ""
        payload = self.evaluate(
            f"""(()=>{{
              const e=({element_expression});
              if(!e)return {{missing:true}};
              {scroll_line}
              const r=e.getBoundingClientRect(),s=getComputedStyle(e);
              const menu=e.closest('.av-command-menu'),details=menu?.closest('details');
              const hidden=!!e.closest('[hidden]')||e.hidden||s.display==='none'||s.visibility==='hidden'||r.width<=0||r.height<=0;
              if(hidden&&details&&!details.open){{
                const q=details.querySelector('summary'),b=q?.getBoundingClientRect();
                return b&&b.width>0&&b.height>0?{{needMenu:true,x:b.x+b.width/2,y:b.y+b.height/2}}:{{hidden:true}};
              }}
              const x=r.x+r.width/2,y=r.y+r.height/2,hit=document.elementFromPoint(x,y);
              return {{
                hidden, x, y,
                hit:!!hit&&(e===hit||e.contains(hit)),
                tag:hit?.tagName||null,
                text:(e.getAttribute('aria-label')||e.textContent||'').trim().slice(0,120)
              }};
            }})()"""
        )
        if payload.get("needMenu"):
            self._native_click(payload)
            self.settle()
            payload = self.evaluate(
                f"""(()=>{{
                  const e=({element_expression});if(!e)return {{missing:true}};
                  const r=e.getBoundingClientRect(),s=getComputedStyle(e),x=r.x+r.width/2,y=r.y+r.height/2,hit=document.elementFromPoint(x,y);
                  return {{hidden:!!e.closest('[hidden]')||e.hidden||s.display==='none'||s.visibility==='hidden'||r.width<=0||r.height<=0,x,y,hit:!!hit&&(e===hit||e.contains(hit)),tag:hit?.tagName||null,text:(e.getAttribute('aria-label')||e.textContent||'').trim().slice(0,120)}};
                }})()"""
            )
        require(not payload.get("missing"), f"Missing native click target: {element_expression}")
        require(not payload.get("hidden"), f"Hidden native click target: {payload}")
        require(payload.get("hit"), f"Native hit test did not land on target: {payload}")
        return payload

    def _native_click(self, point: dict) -> None:
        self.call(
            "Input.dispatchMouseEvent",
            type="mousePressed",
            button="left",
            buttons=1,
            clickCount=1,
            x=point["x"],
            y=point["y"],
        )
        self.call(
            "Input.dispatchMouseEvent",
            type="mouseReleased",
            button="left",
            buttons=0,
            clickCount=1,
            x=point["x"],
            y=point["y"],
        )

    def click(self, element_expression: str, *, scroll: bool = True) -> dict:
        point = self._point(element_expression, scroll=scroll)
        self._native_click(point)
        self.settle()
        return point

    def wheel_page(self, delta_y: float) -> dict:
        point = self.evaluate(
            """(()=>{const candidates=[[8,innerHeight/2],[innerWidth-8,innerHeight/2],[8,innerHeight-16],[innerWidth-8,innerHeight-16]];
              for(const [x,y] of candidates){const e=document.elementFromPoint(x,y);if(e&&!e.closest('.av-plot-scroll,.av-object-list,.av-table-scroll,.av-notebook-body,.av-dialog-body'))return{x,y,tag:e.tagName,cls:e.className||''};}
              return null;
            })()"""
        )
        require(point is not None, "No page-level hit-tested wheel target was available")
        before = self.evaluate("window.scrollY")
        self.call("Input.dispatchMouseEvent", type="mouseWheel", x=point["x"], y=point["y"], deltaX=0, deltaY=delta_y)
        self.settle()
        after = self.evaluate("window.scrollY")
        return {"point": point, "before": before, "after": after, "deltaY": delta_y}

    def screenshot(self, path: Path) -> str:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = self.call("Page.captureScreenshot", format="png", fromSurface=True)
        path.write_bytes(base64.b64decode(payload["data"]))
        return str(path)

    def console_errors(self) -> list[dict]:
        errors = []
        for event in self.events:
            if event.get("method") == "Runtime.exceptionThrown":
                errors.append(event)
            elif event.get("method") == "Log.entryAdded" and event.get("params", {}).get("entry", {}).get("level") == "error":
                errors.append(event)
        return errors

    def close(self) -> None:
        try:
            self.socket.close()
        finally:
            try:
                read_json(self.endpoint + "/json/close/" + self.target_id)
            except Exception:
                pass


class InspectorQualification:
    def __init__(self, page: NativePage, reports: Path, output: Path):
        self.page = page
        self.reports = reports
        self.output = output
        self.results: dict[str, object] = {
            "testFile": file_record(Path(__file__).resolve()),
            "reports": str(reports),
            "reportFiles": {},
            "runtimeArtifacts": {
                "javascript": file_record(VISUALS / "dist/agentic-visuals.js"),
                "css": file_record(VISUALS / "styles/agentic-visuals.css"),
            },
            "scenarios": {},
        }

    def report(self, name: str) -> Path:
        path = self.reports / f"{name}.html"
        require(path.is_file(), f"Missing report: {path}")
        return path

    def load(self, name: str, *, width: int = 1440, height: int = 1000) -> None:
        path = self.report(name)
        report_files = self.results["reportFiles"]
        assert isinstance(report_files, dict)
        report_files[name] = file_record(path)
        self.page.viewport(width, height)
        self.page.navigate(path)
        # Respect the assembled report's own startup. Manual access to
        # enhanceVisuals happens only after the auto-started workspace is ready.
        self.page.wait(
            """(()=>document.readyState==='complete'
              &&!!globalThis.AgenticVisuals
              &&!!document.querySelector('.av-workspace[data-av-ready]')
              &&!document.documentElement.hasAttribute('data-av-starting'))()""",
            timeout=35,
        )
        self.page.evaluate(
            """(()=>{const root=document.querySelector('.av-workspace');
              globalThis.__nativeInspectorCleanup=AgenticVisuals.enhanceVisuals(root);
              return globalThis.__nativeInspectorCleanup===AgenticVisuals.enhanceVisuals(root);
            })()"""
        )
        self.page.settle()

    def select_context(self, *, constellation: bool = False) -> dict:
        predicate = "r.closest('.av-constellation')" if constellation else "r.closest('[data-av-explorer]')"
        result = self.page.evaluate(
            f"""(()=>{{
              const readers=[...document.querySelectorAll('.av-inspector')];
              const reader=readers.find(r=>!!({predicate})&&r.parentElement?.querySelector('[data-av-inspector-open]'));
              if(!reader)return null;
              const explorer=reader.parentElement;
              const openers=[...explorer.querySelectorAll('[data-av-inspector-open]')];
              const opener=openers.find(e=>e.getBoundingClientRect().width>0)||openers[0];
              const figure=opener?.closest('[data-av-figure]')||[...explorer.querySelectorAll('[data-av-figure]')].find(f=>!f.parentElement?.closest('[data-av-figure]'));
              const plot=figure?.querySelector('[data-av-plot]')||explorer.querySelector('[data-av-plot]');
              const viewport=plot?.querySelector('.av-plot-scroll');
              const canvas=viewport?.closest('.av-row-plot-layout')||viewport;
              globalThis.__ni={{reader,explorer,opener,figure,plot,viewport,canvas}};
              const source=()=>({{
                figures:[...document.querySelectorAll('[data-av-figure]')].map(f=>f.getAttribute('data-av-source')),
                mermaid:[...document.querySelectorAll('[data-av-mermaid-source]')].map(f=>f.getAttribute('data-av-mermaid-source')),
                layouts:[...document.querySelectorAll('[data-av-layout-input]')].map(f=>f.getAttribute('data-av-layout-input'))
              }});
              __ni.sourceSnapshot=source();
              __ni.sourceNow=source;
              __ni.savedReader=reader;
              return {{
                readerIndex:readers.indexOf(reader),
                explorerClass:explorer.className,
                figureTitle:figure?.getAttribute('data-av-figure-title')||null,
                openerInToolbar:!!opener?.closest('.av-plot-toolbar'),
                openerCount:document.querySelectorAll('[data-av-inspector-open]').length,
                pinCount:document.querySelectorAll('[data-av-inspector-pin]').length,
                reviewUiCount:document.querySelectorAll('[data-av-review-ui]').length,
                hasFigure:!!figure,hasViewport:!!viewport
              }};
            }})()"""
        )
        require(result is not None, "No inspector with a figure opener was found")
        require(result["hasFigure"] and result["hasViewport"], f"Incomplete inspector context: {result}")
        return result

    def state(self) -> dict:
        return self.page.evaluate(
            """(()=>{const n=__ni,r=n.reader,e=n.explorer,f=n.figure,v=n.viewport,c=n.canvas;
              const rb=r.getBoundingClientRect(),eb=e.getBoundingClientRect(),vb=v.getBoundingClientRect(),cb=c?.getBoundingClientRect();
              const selected=r.querySelector('[data-av-object].av-selected')||r.querySelector('[data-av-object][open]');
              const selectedKey=selected?.getAttribute('data-av-object')||null;
              const mark=selectedKey?[...f.querySelectorAll('[data-av-inspect]')].find(x=>x.getAttribute('data-av-inspect')===selectedKey):null;
              const mb=mark?.getBoundingClientRect();
              return {
                layout:e.getAttribute('data-av-inspector-layout'),
                view:r.getAttribute('data-av-inspector-view'),
                hidden:r.hidden,
                readerOpen:r.hasAttribute('open'),
                readerConnected:r.isConnected,
                readerSame:r===n.savedReader,
                openerExpanded:n.opener?.getAttribute('aria-expanded'),
                canvasReserved:!!c?.hasAttribute('data-av-inspector-canvas'),
                explorerWidth:eb.width,viewportWidth:vb.width,canvasWidth:cb?.width||null,
                readerBox:{left:rb.left,right:rb.right,top:rb.top,bottom:rb.bottom,width:rb.width,height:rb.height},
                inspectorDialogOpen:!!e.querySelector('.av-inspector-dialog[open]'),
                selectedKey,
                selectedMarkBox:mb?{left:mb.left,right:mb.right,top:mb.top,bottom:mb.bottom,width:mb.width,height:mb.height}:null,
                mode:f?.getAttribute('data-av-selection-mode')||null,
                reserveHidden:v?.querySelector('[data-av-pan-reserve]')?.hidden??null,
                reserveWidth:v?.querySelector('[data-av-pan-reserve]')?.style.width||'',
                scrollWidth:v?.scrollWidth||0,clientWidth:v?.clientWidth||0,scrollLeft:v?.scrollLeft||0,
                activeTag:document.activeElement?.tagName||null,
                activeLabel:document.activeElement?.getAttribute?.('aria-label')||document.activeElement?.textContent?.trim().slice(0,100)||null
              };
            })()"""
        )

    def choose_select_mode(self) -> None:
        self.page.click("__ni.figure.querySelector('[data-av-mode-menu]')")
        self.page.click("__ni.figure.querySelector('[data-av-figure-action=\"select-items\"]')")
        require(self.state()["mode"] == "select", "Figure did not enter Select mode")

    def choose_rightmost_mark(self) -> str:
        key = self.page.evaluate(
            """(()=>{const marks=[...__ni.figure.querySelectorAll('[data-av-inspect]')].filter(m=>{const b=m.getBoundingClientRect();return b.width>0&&b.height>0&&!m.closest('[hidden]')});
              marks.sort((a,b)=>a.getBoundingClientRect().right-b.getBoundingClientRect().right);
              const mark=marks.at(-1);if(!mark)return null;const key=mark.getAttribute('data-av-inspect');
              __ni.rightMark=mark;__ni.savedRightMark=mark;
              __ni.rightObject=[...__ni.reader.querySelectorAll('[data-av-object]')].find(x=>x.getAttribute('data-av-object')===key)||null;
              __ni.savedRightObject=__ni.rightObject;
              return key;
            })()"""
        )
        require(bool(key), "No visible inspectable mark was found")
        self.page.click("__ni.rightMark")
        return key

    def wide_reader_and_pan(self) -> dict:
        self.load("compact", width=1440, height=1000)
        context = self.select_context()
        initial = self.state()
        require(initial["layout"] == "closed" and initial["view"] == "closed" and initial["hidden"], f"Default inspector is not closed: {initial}")
        require(not initial["canvasReserved"], "Closed inspector reserved a side column")
        require(abs(initial["canvasWidth"] - initial["explorerWidth"]) < 2, f"Default closed inspector is not full width: {initial}")
        require(context["openerInToolbar"], f"Evidence opener is not in the figure toolbar: {context}")

        self.page.click("__ni.opener")
        opened = self.state()
        require(opened["layout"] == "floating" and opened["view"] == "floating", f"Wide Evidence did not open floating: {opened}")
        require(not opened["inspectorDialogOpen"], "Wide floating Evidence unexpectedly opened a modal dialog")
        self.page.screenshot(self.output / "compact-floating.png")

        link = self.page.evaluate(
            """(()=>{const a=[...__ni.reader.querySelectorAll('a[href^="#"]')].find(a=>{const id=decodeURIComponent(a.getAttribute('href').slice(1)),target=document.getElementById(id);return target&&!__ni.reader.contains(target)&&a.getBoundingClientRect().width>0;});
              if(!a)return null;const id=decodeURIComponent(a.getAttribute('href').slice(1));__ni.readerLink=a;__ni.readerLinkTarget=document.getElementById(id);__ni.readerBeforeLink=__ni.reader;
              __ni.linkFocusLayout=null;__ni.readerLinkTarget.addEventListener('focusin',()=>{__ni.linkFocusLayout=__ni.explorer.getAttribute('data-av-inspector-layout')},{once:true});
              return {href:a.getAttribute('href'),targetId:id};
            })()"""
        )
        require(link is not None, "No visible compact reader fragment link to other evidence was found")
        self.page.click("__ni.readerLink")
        navigation = self.page.evaluate(
            """(()=>({readerSame:__ni.reader===__ni.readerBeforeLink,readerConnected:__ni.reader.isConnected,
              layout:__ni.explorer.getAttribute('data-av-inspector-layout'),hidden:__ni.reader.hidden,
              targetConnected:__ni.readerLinkTarget.isConnected,
              targetFocused:__ni.readerLinkTarget===document.activeElement||__ni.readerLinkTarget.contains(document.activeElement),
              layoutAtDestinationFocus:__ni.linkFocusLayout,
              activeText:document.activeElement?.textContent?.trim().slice(0,120)||null
            }))()"""
        )
        require(navigation["readerSame"] and navigation["readerConnected"], f"Reader link navigation replaced evidence node: {navigation}")
        require(navigation["layout"] == "closed" and navigation["hidden"], f"Reader link did not dismiss reader before navigation: {navigation}")
        require(navigation["layoutAtDestinationFocus"] == "closed", f"Reader was not dismissed before destination focus: {navigation}")
        require(navigation["targetConnected"] and navigation["targetFocused"], f"Reader link did not focus destination evidence: {navigation}")
        self.page.click("__ni.opener")
        reopened = self.state()
        require(reopened["layout"] == "floating", f"Evidence did not reopen after link navigation: {reopened}")

        self.page.click("__ni.reader.querySelector('[data-av-inspector-pin]')")
        pinned = self.state()
        require(pinned["layout"] == "side" and pinned["canvasReserved"], f"Pin did not reserve side layout: {pinned}")
        require(pinned["readerSame"], "Pin replaced the live inspector node")
        require(pinned["canvasWidth"] < opened["canvasWidth"] - 200, f"Pinned side column did not materially reduce canvas width: {opened['canvasWidth']} -> {pinned['canvasWidth']}")
        self.page.screenshot(self.output / "compact-pinned.png")

        self.page.click("__ni.reader.querySelector('[data-av-inspector-pin]')")
        unpinned = self.state()
        require(unpinned["layout"] == "floating" and not unpinned["canvasReserved"], f"Unpin did not release side column: {unpinned}")
        require(unpinned["canvasWidth"] > pinned["canvasWidth"] + 200, "Unpin did not return canvas width")
        require(unpinned["reserveHidden"] is False, f"Unpinned floating reader lost its pan reserve: {unpinned}")
        require(abs(unpinned["scrollWidth"] - reopened["scrollWidth"]) <= 2, f"Pin→unpin retained stale reserve geometry: reopened={reopened}, unpinned={unpinned}")
        require(abs(unpinned["scrollLeft"] - reopened["scrollLeft"]) <= 8, f"Pin→unpin over-panned the selected evidence: reopened={reopened}, unpinned={unpinned}")
        if unpinned["selectedMarkBox"]:
            require(unpinned["selectedMarkBox"]["right"] <= unpinned["readerBox"]["left"] - 2, f"Selected mark remains under reader after unpin: {unpinned}")

        # Close, enter Select through the actual drawing-tools UI, and choose the
        # rightmost native mark. Selection preview reopens Evidence without focus.
        self.page.click("__ni.reader.querySelector('.av-panel-close')")
        require(self.state()["layout"] == "closed", "Evidence did not close before selection test")
        self.choose_select_mode()
        key = self.choose_rightmost_mark()
        selected = self.state()
        selection_identity = self.page.evaluate("({sameReader:__ni.reader===__ni.savedReader,sameMark:__ni.rightMark===__ni.savedRightMark,sameObject:__ni.rightObject===__ni.savedRightObject&&!!__ni.rightObject})")
        require(selected["selectedKey"] == key, f"Rightmost native mark did not select its exact object: {selected}")
        require(selection_identity["sameReader"] and selection_identity["sameMark"] and selection_identity["sameObject"], f"Selection replaced a live evidence node: {selection_identity}")
        require(selected["layout"] == "floating", f"Selection preview did not open floating Evidence: {selected}")
        require(selected["mode"] == "select", "Opening floating Evidence changed Select mode")
        require(selected["reserveHidden"] is False and selected["scrollWidth"] > selected["clientWidth"], f"Floating Evidence did not reserve native horizontal pan: {selected}")
        if selected["selectedMarkBox"]:
            require(
                selected["selectedMarkBox"]["right"] <= selected["readerBox"]["left"] - 2,
                f"Rightmost selected mark remains underneath floating Evidence: {selected}",
            )
        self.page.screenshot(self.output / "compact-selected-clear.png")
        return {"context": context, "initial": initial, "opened": opened, "link": link, "navigation": navigation, "reopened": reopened, "pinned": pinned, "unpinned": unpinned, "selected": selected, "selectionIdentity": selection_identity}

    def narrow_and_expand(self) -> dict:
        self.load("compact", width=1440, height=1000)
        self.select_context()
        self.choose_select_mode()
        key = self.choose_rightmost_mark()
        require(self.state()["layout"] == "floating", "Selection did not produce the wide floating reader")
        self.page.click("__ni.reader.querySelector('[data-av-object].av-selected summary')")  # native focus target
        self.page.evaluate("__ni.focusBeforeNarrow=document.activeElement;__ni.parentBeforeExpand=__ni.figure.parentElement;__ni.savedFigure=__ni.figure")

        self.page.viewport(680, 900)
        self.page.settle()
        drawer = self.state()
        same_focus = self.page.evaluate("document.activeElement===__ni.focusBeforeNarrow")
        require(drawer["layout"] == "drawer" and drawer["inspectorDialogOpen"], f"Open narrow Evidence did not become native drawer: {drawer}")
        require(same_focus, f"Focus was not preserved across floating→drawer transition: {drawer}")
        self.page.screenshot(self.output / "compact-drawer.png")

        self.page.key("Escape", code="Escape")
        closed = self.state()
        require(closed["layout"] == "closed" and not closed["inspectorDialogOpen"], f"Native Escape did not close drawer: {closed}")
        self.page.viewport(620, 900)
        self.page.settle()
        narrow_closed = self.state()
        require(narrow_closed["layout"] == "closed" and narrow_closed["hidden"], f"Unrelated narrow resize reopened closed Evidence: {narrow_closed}")

        self.page.viewport(1440, 1000)
        self.page.settle()
        require(self.state()["layout"] == "closed", "Returning wide reopened closed Evidence")
        self.page.click("__ni.figure.querySelector('[data-av-figure-action=\"expand\"]')")
        expanded = self.page.evaluate(
            """(()=>({sameFigure:__ni.figure===__ni.savedFigure,expanded:__ni.figure.hasAttribute('data-av-expanded-figure'),
              viewerOpen:!!document.querySelector('.av-focus-dialog[open][data-av-viewer-kind="figure"]'),
              selectedKey:(__ni.reader.querySelector('[data-av-object].av-selected')||__ni.reader.querySelector('[data-av-object][open]'))?.getAttribute('data-av-object')||null
            }))()"""
        )
        require(expanded["sameFigure"] and expanded["expanded"] and expanded["viewerOpen"], f"Figure expansion replaced or lost live figure: {expanded}")
        require(expanded["selectedKey"] == key, f"Figure expansion lost selected evidence: {expanded}")
        self.page.click("__ni.opener")
        expanded_reader = self.state()
        require(expanded_reader["layout"] == "drawer" and expanded_reader["inspectorDialogOpen"], f"Explicit Evidence in expanded figure did not open modal reader: {expanded_reader}")
        require(expanded_reader["readerSame"], "Expanded Evidence did not reuse the original live reader node")
        require(expanded_reader["selectedKey"] == key, "Expanded Evidence changed selected object")
        self.page.screenshot(self.output / "compact-expanded-evidence.png")
        self.page.click("__ni.reader.querySelector('.av-panel-close')")
        require(self.page.evaluate("!!document.querySelector('.av-focus-dialog[open][data-av-viewer-kind=\"figure\"]')"), "Closing Evidence also closed expanded figure")
        require(self.state()["selectedKey"] == key, "Closing expanded Evidence changed selection")
        self.page.click("document.querySelector('.av-focus-dialog[open][data-av-viewer-kind=\"figure\"] [data-av-close-focus]')")
        returned = self.page.evaluate(
            """(()=>({sameFigure:__ni.figure===__ni.savedFigure,sameParent:__ni.figure.parentElement===__ni.parentBeforeExpand,
              expanded:__ni.figure.hasAttribute('data-av-expanded-figure'),
              selectedKey:(__ni.reader.querySelector('[data-av-object].av-selected')||__ni.reader.querySelector('[data-av-object][open]'))?.getAttribute('data-av-object')||null
            }))()"""
        )
        require(returned["sameFigure"] and returned["sameParent"] and not returned["expanded"], f"Expanded figure did not return its live node to original view: {returned}")
        require(returned["selectedKey"] == key, f"Returning from expansion lost selection: {returned}")
        return {"drawer": drawer, "closed": closed, "narrowClosed": narrow_closed, "expanded": expanded, "expandedReader": expanded_reader, "returned": returned}

    def relationships_and_links(self) -> dict:
        self.load("field-study", width=1440, height=1000)
        context = self.select_context(constellation=True)
        self.page.click("__ni.opener")
        require(self.state()["layout"] == "floating", "Constellation Evidence did not open floating")
        prepared = self.page.evaluate(
            """(()=>{const button=[...__ni.reader.querySelectorAll('button[data-av-inspect]')].find(b=>/Read relationship/i.test(b.textContent||'')&&b.getBoundingClientRect().width>0);
              if(!button)return null;const key=button.getAttribute('data-av-inspect'),object=[...__ni.reader.querySelectorAll('[data-av-object]')].find(x=>x.getAttribute('data-av-object')===key);
              const mark=[...__ni.figure.querySelectorAll('[data-av-inspect]')].find(x=>x.getAttribute('data-av-inspect')===key);
              __ni.relationshipButton=button;__ni.relationshipObject=object;__ni.relationshipMark=mark;__ni.readerBeforeRelationship=__ni.reader;
              return {key,hasObject:!!object,hasMark:!!mark};
            })()"""
        )
        require(prepared and prepared["hasObject"] and prepared["hasMark"], f"No native Read relationship target in selected reader: {prepared}")
        self.page.click("__ni.relationshipButton")
        relationship = self.page.evaluate(
            """(()=>({sameReader:__ni.reader===__ni.readerBeforeRelationship,
              sameObject:[...__ni.reader.querySelectorAll('[data-av-object]')].find(x=>x.getAttribute('data-av-object')===__ni.relationshipButton.getAttribute('data-av-inspect'))===__ni.relationshipObject,
              sameMark:[...__ni.figure.querySelectorAll('[data-av-inspect]')].find(x=>x.getAttribute('data-av-inspect')===__ni.relationshipButton.getAttribute('data-av-inspect'))===__ni.relationshipMark,
              selectedKey:(__ni.reader.querySelector('[data-av-object].av-selected')||__ni.reader.querySelector('[data-av-object][open]'))?.getAttribute('data-av-object')||null,
              layout:__ni.explorer.getAttribute('data-av-inspector-layout')
            }))()"""
        )
        require(relationship["sameReader"] and relationship["sameObject"] and relationship["sameMark"], f"Read relationship replaced live nodes: {relationship}")
        require(relationship["selectedKey"] == prepared["key"], f"Read relationship did not select exact relationship: {relationship}")

        self.page.screenshot(self.output / "field-study-relationship.png")
        return {"context": context, "prepared": prepared, "relationship": relationship}

    def lower_canvas_float_guard(self) -> dict:
        """Keep a low wide peek with its canvas and out of the toolbar."""
        self.load("compact", width=1440, height=1000)
        self.select_context()
        positioned = self.page.evaluate(
            """(()=>{const b=__ni.canvas.getBoundingClientRect(),target=520;
              window.scrollTo(0,Math.max(0,window.scrollY+b.top-target));
              return {before:b.top,scrollY:window.scrollY};
            })()"""
        )
        self.page.settle()
        before = self.page.evaluate(
            """(()=>{const c=__ni.canvas.getBoundingClientRect(),t=__ni.figure.querySelector('.av-plot-toolbar')?.getBoundingClientRect();
              return {canvas:{top:c.top,bottom:c.bottom,left:c.left,right:c.right},toolbar:t?{top:t.top,bottom:t.bottom,left:t.left,right:t.right}:null,scrollY:window.scrollY};
            })()"""
        )
        require(before["canvas"]["top"] >= 400, f"Could not position canvas low enough for regression: {before}")
        require(before["canvas"]["bottom"] > before["canvas"]["top"], f"Canvas is not visible for lower-position regression: {before}")
        self.page.click("__ni.opener", scroll=False)
        opened = self.page.evaluate(
            """(()=>{const r=__ni.reader.getBoundingClientRect(),c=__ni.canvas.getBoundingClientRect(),t=__ni.figure.querySelector('.av-plot-toolbar')?.getBoundingClientRect();
              const overlap=t?Math.max(0,Math.min(r.right,t.right)-Math.max(r.left,t.left))*Math.max(0,Math.min(r.bottom,t.bottom)-Math.max(r.top,t.top)):0;
              return {layout:__ni.explorer.getAttribute('data-av-inspector-layout'),dialog:__ni.explorer.querySelector('.av-inspector-dialog')?.open||false,
                reader:{top:r.top,bottom:r.bottom,left:r.left,right:r.right},canvas:{top:c.top,bottom:c.bottom,left:c.left,right:c.right},
                toolbar:t?{top:t.top,bottom:t.bottom,left:t.left,right:t.right}:null,toolbarOverlap:overlap};
            })()"""
        )
        require(opened["layout"] == "floating" and not opened["dialog"], f"Low wide canvas did not open a nonmodal floating reader: {opened}")
        require(opened["reader"]["top"] >= opened["canvas"]["top"] - 0.5, f"Floating reader rose above its low canvas: {opened}")
        require(opened["toolbar"] is not None and opened["toolbarOverlap"] < 0.5, f"Floating reader obscures the plot toolbar: {opened}")
        self.page.screenshot(self.output / "compact-low-canvas-floating.png")

        # Move the document upward so this same canvas moves toward the viewport
        # bottom. Scroll listeners may close a peek with too little room, or keep
        # it floating; they must never promote this incidental scroll to a modal.
        wheel = self.page.wheel_page(-300)
        require(wheel["after"] < wheel["before"] - 100, f"Native page wheel did not move the document upward enough: {wheel}")
        after = self.page.evaluate(
            """(()=>{const r=__ni.reader.getBoundingClientRect(),c=__ni.canvas.getBoundingClientRect(),t=__ni.figure.querySelector('.av-plot-toolbar')?.getBoundingClientRect();
              const layout=__ni.explorer.getAttribute('data-av-inspector-layout'),dialog=__ni.explorer.querySelector('.av-inspector-dialog')?.open||false;
              const overlap=!__ni.reader.hidden&&t?Math.max(0,Math.min(r.right,t.right)-Math.max(r.left,t.left))*Math.max(0,Math.min(r.bottom,t.bottom)-Math.max(r.top,t.top)):0;
              return {layout,hidden:__ni.reader.hidden,dialog,reader:{top:r.top,bottom:r.bottom,left:r.left,right:r.right},canvas:{top:c.top,bottom:c.bottom,left:c.left,right:c.right},
                toolbar:t?{top:t.top,bottom:t.bottom,left:t.left,right:t.right}:null,toolbarOverlap:overlap,scrollY:window.scrollY};
            })()"""
        )
        require(after["canvas"]["top"] > opened["canvas"]["top"] + 100, f"Scroll did not move canvas toward viewport bottom: opened={opened}, after={after}")
        require(after["layout"] in {"closed", "floating"}, f"Scrolling a wide peek unexpectedly opened a drawer: {after}")
        require(not after["dialog"], f"Scrolling a wide peek unexpectedly opened a modal drawer: {after}")
        if after["layout"] == "floating":
            require(after["reader"]["top"] >= after["canvas"]["top"] - 0.5, f"Scrolled floating reader rose above canvas: {after}")
            require(after["toolbarOverlap"] < 0.5, f"Scrolled floating reader obscures toolbar: {after}")
        self.page.screenshot(self.output / "compact-low-canvas-scrolled.png")
        return {"positioned": positioned, "before": before, "opened": opened, "wheel": wheel, "afterScroll": after}

    def long_relationship_reader(self) -> dict:
        """Read full relationship context and follow identities with equal labels."""
        self.load("mixed-components", width=1440, height=1000)
        self.page.click("document.querySelector('[data-av-view=\"relationships\"]')")
        context = self.select_context(constellation=True)
        prepared = self.page.evaluate(
            """(()=>{const input=JSON.parse(document.getElementById('mixed-lineage').getAttribute('data-av-layout-input'));
              const index=input.edges.findIndex(e=>e.id==='alpha1-scope'),edge=input.edges[index];
              __ni.longKey='edge-'+index;__ni.longNote=edge.note;
              __ni.scopeKey='node-'+input.nodes.findIndex(n=>n.id===edge.to);
              __ni.secondEdgeKey='edge-'+input.edges.findIndex(e=>e.id==='alpha2-support');
              __ni.secondNodeKey='node-'+input.nodes.findIndex(n=>n.id==='alpha-record-2');
              return{key:__ni.longKey,noteChars:edge.note.length,from:edge.from,to:edge.to};})()"""
        )
        require(prepared["noteChars"] >= 1200, f"Long relationship fixture lost its full context: {prepared}")
        self.page.click("__ni.opener")
        self.page.click("__ni.reader.querySelector('[data-av-object].av-selected [data-av-inspect=\"'+__ni.longKey+'\"]')")
        require(self.state()["selectedKey"] == prepared["key"], "Relationship action selected a different occurrence")

        def read_to_end() -> dict:
            before = self.page.evaluate(
                """(()=>{const object=__ni.reader.querySelector('[data-av-object].av-selected'),body=object.querySelector('.av-object-body');
                  const note=[...body.querySelectorAll('.av-note')].find(p=>p.textContent===__ni.longNote),r=body.getBoundingClientRect(),x=r.left+r.width/2,y=r.top+r.height/2;
                  __ni.longBody=body;__ni.longNoteElement=note;
                  return{sourceExact:!!note,scrollHeight:body.scrollHeight,clientHeight:body.clientHeight,x,y,hit:body.contains(document.elementFromPoint(x,y))};})()"""
            )
            require(before["sourceExact"] and before["hit"], f"Long relationship source is missing or its reader is obstructed: {before}")
            require(before["scrollHeight"] > before["clientHeight"] + 100, f"Fixture does not exercise reader scrolling: {before}")
            self.page.call("Input.dispatchMouseEvent", type="mouseWheel", x=before["x"], y=before["y"], deltaX=0, deltaY=10000)
            self.page.settle()
            after = self.page.evaluate(
                """(()=>{const body=__ni.longBody,note=__ni.longNoteElement,marker='END OF RETAINED QUALIFICATION.',walker=document.createTreeWalker(note,NodeFilter.SHOW_TEXT);let node,rect=null;
                  while(node=walker.nextNode()){const index=node.textContent.indexOf(marker);if(index>=0){const range=document.createRange();range.setStart(node,index);range.setEnd(node,index+marker.length);rect=range.getBoundingClientRect();break;}}
                  const box=body.getBoundingClientRect();return{scrollTop:body.scrollTop,markerVisible:!!rect&&rect.top>=box.top-1&&rect.bottom<=box.bottom+1,
                    horizontalOverflow:body.scrollWidth-body.clientWidth,sourceExact:note.textContent===__ni.longNote,readerSame:__ni.reader===__ni.savedReader};})()"""
            )
            require(after["scrollTop"] > 0 and after["markerVisible"], f"Native wheel could not reach the end of the original relationship: {after}")
            require(after["horizontalOverflow"] <= 2 and after["sourceExact"] and after["readerSame"], f"Reading truncated or replaced relationship context: {after}")
            return {"before": before, "after": after}

        wide = read_to_end()
        self.page.screenshot(self.output / "mixed-long-relationship.png")
        transition = {"before": self.state(), "focusInReader": self.page.evaluate("__ni.reader.contains(document.activeElement)")}
        self.results["longReaderResizeTrace"] = transition
        self.page.viewport(390, 520)
        self.page.settle()
        transition["after"] = self.state()
        require(transition["after"]["layout"] == "drawer" and transition["after"]["readerSame"], f"Narrowing lost the focused long reader: {transition}")
        require(self.state()["selectedKey"] == prepared["key"], "Narrowing changed the relationship occurrence")
        narrow = read_to_end()
        self.page.screenshot(self.output / "mixed-long-relationship-narrow.png")
        # Follow the destination to a different relationship, then its origin.
        # The two origin labels are identical; their retained record IDs are not.
        self.page.click("__ni.reader.querySelector('[data-av-object].av-selected [data-av-inspect=\"'+__ni.scopeKey+'\"]')")
        self.page.click("__ni.reader.querySelector('[data-av-object].av-selected [data-av-inspect=\"'+__ni.secondEdgeKey+'\"]')")
        self.page.click("__ni.reader.querySelector('[data-av-object].av-selected [data-av-inspect=\"'+__ni.secondNodeKey+'\"]')")
        destination = self.page.evaluate(
            """(()=>{const object=__ni.reader.querySelector('[data-av-object].av-selected');return{key:object.getAttribute('data-av-object'),expected:__ni.secondNodeKey,
              exactIdentity:[...object.querySelectorAll('code')].some(e=>e.textContent==='alpha-record-2'),focused:object.contains(document.activeElement),
              mode:__ni.figure.getAttribute('data-av-selection-mode'),sourceSame:JSON.stringify(__ni.sourceSnapshot)===JSON.stringify(__ni.sourceNow())};})()"""
        )
        require(destination["key"] == destination["expected"] and destination["exactIdentity"], f"Repeated label resolved to the wrong record: {destination}")
        require(destination["focused"] and destination["sourceSame"] and destination["mode"] == "pan", f"Reading relationships changed source, focus or drawing mode: {destination}")
        self.page.screenshot(self.output / "mixed-repeated-label-identity.png")
        self.page.click("__ni.reader.querySelector('.av-panel-close')", scroll=False)
        return {"context": context, "prepared": prepared, "wide": wide, "narrow": narrow, "destination": destination}

    def short_window_reader(self) -> dict:
        """Keep the live evidence and a reachable return path in short windows."""
        self.load("compact", width=1440, height=1000)
        context = self.select_context()
        self.page.click("__ni.opener")
        self.page.click("__ni.reader.querySelector('[data-av-inspector-pin]')")
        pinned = self.state()
        require(pinned["layout"] == "side", f"Wide evidence did not pin: {pinned}")

        self.page.viewport(390, 360)
        self.page.settle()
        narrow = self.state()
        require(narrow["layout"] == "drawer" and narrow["readerSame"], f"Narrowing replaced or lost the reader: {narrow}")
        require(narrow["selectedKey"] == pinned["selectedKey"], "Narrowing changed the selected evidence")
        # A reader pinned in a wider window must still offer Unpin. Once unpinned,
        # the unavailable action disappears and focus moves to the visible Close.
        self.page.click("__ni.reader.querySelector('[data-av-inspector-pin]')", scroll=False)
        unpinned = self.page.evaluate(
            """(()=>{const r=__ni.reader,p=r.querySelector('[data-av-inspector-pin]'),c=r.querySelector('.av-panel-close'),b=r.querySelector('[data-av-object].av-selected .av-object-body');
              const box=r.getBoundingClientRect();return{pinHidden:p.hidden,pinPressed:p.getAttribute('aria-pressed'),closeFocused:document.activeElement===c,
                bodyHeight:b?.clientHeight||0,contained:box.left>=0&&box.top>=0&&box.right<=innerWidth+1&&box.bottom<=innerHeight+1,
                readerSame:r===__ni.savedReader,sourceSame:JSON.stringify(__ni.sourceSnapshot)===JSON.stringify(__ni.sourceNow())};})()"""
        )
        require(unpinned["pinHidden"] and unpinned["pinPressed"] == "false", f"Unavailable Pin remained in a narrow drawer: {unpinned}")
        require(unpinned["closeFocused"], f"Unpin left keyboard focus on a hidden control: {unpinned}")
        require(unpinned["contained"] and unpinned["bodyHeight"] >= 100, f"Short drawer has no useful evidence area: {unpinned}")
        require(unpinned["readerSame"] and unpinned["sourceSame"], "Narrow unpin replaced evidence or changed original sources")
        self.page.screenshot(self.output / "compact-short-drawer.png")
        self.page.click("__ni.reader.querySelector('.av-panel-close')", scroll=False)
        require(self.state()["layout"] == "closed", "Close did not return from the short drawer")

        self.page.viewport(1000, 320)
        self.page.settle()
        self.page.click("__ni.opener")
        landscape = self.state()
        require(landscape["layout"] == "drawer" and landscape["readerSame"], f"Short landscape reader lost its context: {landscape}")
        require(landscape["selectedKey"] == pinned["selectedKey"], "Landscape changed the selected evidence")
        self.page._point("__ni.reader.querySelector('.av-panel-close')", scroll=False)
        self.page.screenshot(self.output / "compact-short-landscape.png")
        self.page.click("__ni.reader.querySelector('.av-panel-close')", scroll=False)
        return {"context": context, "pinned": pinned, "narrow": narrow, "unpinned": unpinned, "landscape": landscape}

    def cleanup_and_reenhance(self) -> dict:
        self.load("compact", width=1440, height=1000)
        context = self.select_context()
        baseline = self.page.evaluate(
            """(()=>({openers:document.querySelectorAll('[data-av-inspector-open]').length,pins:document.querySelectorAll('[data-av-inspector-pin]').length,
              reviewUi:document.querySelectorAll('[data-av-review-ui]').length,sources:__ni.sourceNow(),
              readers:document.querySelectorAll('.av-inspector').length
            }))()"""
        )
        self.page.evaluate("__nativeInspectorCleanup()")
        self.page.evaluate("(async()=>{await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));})()")
        cleaned = self.page.evaluate(
            """(()=>({openers:document.querySelectorAll('[data-av-inspector-open]').length,pins:document.querySelectorAll('[data-av-inspector-pin]').length,
              sources:__ni.sourceNow(),readerView:__ni.reader.getAttribute('data-av-inspector-view'),layout:__ni.explorer.getAttribute('data-av-inspector-layout'),
              summaryHidden:__ni.reader.querySelector('summary')?.hidden??null
            }))()"""
        )
        require(cleaned["openers"] == 0 and cleaned["pins"] == 0, f"Cleanup left generated inspector controls: {cleaned}")
        require(cleaned["sources"] == baseline["sources"], "Cleanup mutated exact figure source attributes")
        self.page.evaluate(
            """(async()=>{const root=document.querySelector('.av-workspace');globalThis.__nativeInspectorCleanup=AgenticVisuals.enhanceVisuals(root);await __nativeInspectorCleanup.whenIdle();await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));})()"""
        )
        reenhanced = self.page.evaluate(
            """(()=>({openers:document.querySelectorAll('[data-av-inspector-open]').length,pins:document.querySelectorAll('[data-av-inspector-pin]').length,
              reviewUi:document.querySelectorAll('[data-av-review-ui]').length,sources:__ni.sourceNow(),
              readers:document.querySelectorAll('.av-inspector').length,
              openLayouts:[...document.querySelectorAll('[data-av-inspector-layout]')].filter(e=>e.getAttribute('data-av-inspector-layout')!=='closed').length
            }))()"""
        )
        require(reenhanced["openers"] == baseline["openers"] and reenhanced["pins"] == baseline["pins"], f"Re-enhance duplicated or lost inspector controls: baseline={baseline}, reenhanced={reenhanced}")
        require(reenhanced["readers"] == baseline["readers"], "Re-enhance changed authored reader count")
        require(reenhanced["sources"] == baseline["sources"], "Re-enhance mutated exact figure source attributes")
        require(reenhanced["openLayouts"] == 0, f"Re-enhance did not restore default-closed readers: {reenhanced}")
        self.page.screenshot(self.output / "compact-reenhanced.png")
        return {"context": context, "baseline": baseline, "cleaned": cleaned, "reenhanced": reenhanced}

    def run(self) -> dict:
        self.output.mkdir(parents=True, exist_ok=True)
        scenarios = self.results["scenarios"]
        assert isinstance(scenarios, dict)
        scenarios["wideReaderAndPan"] = self.wide_reader_and_pan()
        scenarios["lowerCanvasFloatGuard"] = self.lower_canvas_float_guard()
        scenarios["narrowAndExpand"] = self.narrow_and_expand()
        scenarios["relationshipsAndLinks"] = self.relationships_and_links()
        scenarios["longRelationshipReader"] = self.long_relationship_reader()
        scenarios["shortWindowReader"] = self.short_window_reader()
        scenarios["cleanupAndReenhance"] = self.cleanup_and_reenhance()
        errors = self.page.console_errors()
        self.results["consoleErrors"] = len(errors)
        require(not errors, f"Chrome recorded {len(errors)} console/runtime errors")
        return self.results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cdp", default=DEFAULT_CDP, help="Existing Chrome DevTools HTTP endpoint.")
    parser.add_argument("--reports", type=Path, default=DEFAULT_REPORTS, help="Directory containing assembled HTML reports.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Directory for screenshots and JSON results.")
    args = parser.parse_args()

    reports = args.reports.resolve()
    output = args.output.resolve()
    if not reports.is_dir():
        print(f"error: report directory does not exist: {reports}", file=sys.stderr)
        return 2
    output.mkdir(parents=True, exist_ok=True)

    page = NativePage(args.cdp)
    qualification = InspectorQualification(page, reports, output)
    try:
        results = qualification.run()
        (output / "results.json").write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        print(json.dumps({"status": "passed", "output": str(output), "scenarios": list(results["scenarios"])}, ensure_ascii=False))
        return 0
    except Exception as error:
        try:
            qualification.results["failure"] = {"type": type(error).__name__, "message": str(error)}
            qualification.results["consoleErrors"] = page.console_errors()
            page.screenshot(output / "failure.png")
            (output / "results.json").write_text(json.dumps(qualification.results, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8", newline="\n")
        except Exception:
            pass
        print(f"error: {type(error).__name__}: {error}", file=sys.stderr)
        print(f"evidence: {output}", file=sys.stderr)
        return 1
    finally:
        page.close()


if __name__ == "__main__":
    raise SystemExit(main())
