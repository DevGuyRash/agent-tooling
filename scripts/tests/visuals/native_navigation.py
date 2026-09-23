#!/usr/bin/env python3
"""Qualify plot navigation in one assembled report using an existing Chrome process.

This runner attaches through CDP, opens one owned page target, and exercises real
mouse, wheel, keyboard, pointer-capture, and expanded-view behavior. It does not
launch a browser or depend on project-specific scratch helpers.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from native_inspector import DEFAULT_CDP, NativePage, file_record


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PROJECT = ROOT / "plugins/agentic-design-and-evaluation"
DEFAULT_REPORTS = PROJECT / ".local/visual-tests/reports"
DEFAULT_OUTPUT = PROJECT / ".local/visual-tests/native-navigation"


def state(page: NativePage) -> dict:
    return page.evaluate(
        """(()=>{const f=__nav.figure,p=__nav.plot,v=__nav.viewport,r=v.getBoundingClientRect(),s=p.querySelector('[data-av-zoom-target]')?.getBoundingClientRect();return{
          sameFigure:f===__nav.savedFigure,connected:f.isConnected,title:f.getAttribute('data-av-figure-title')||f.getAttribute('aria-label')||null,
          mode:f.getAttribute('data-av-selection-mode')||null,zoom:p.getAttribute('data-av-zoom')||null,viewportMode:p.getAttribute('data-av-viewport-mode')||null,
          pan:v.getAttribute('data-av-pan')||null,space:v.hasAttribute('data-av-space-pan'),dragging:v.hasAttribute('data-av-dragging'),
          left:v.scrollLeft,top:v.scrollTop,cw:v.clientWidth,ch:v.clientHeight,sw:v.scrollWidth,sh:v.scrollHeight,
          viewport:{left:r.left,top:r.top,width:r.width,height:r.height},scene:s?{width:s.width,height:s.height}:null,
          expanded:f.hasAttribute('data-av-expanded-figure'),dialog:!!document.querySelector('.av-focus-dialog[open]'),
          pageY:window.scrollY,pageHeight:document.documentElement.scrollHeight,windowHeight:innerHeight,
          theme:(f.closest('[data-av-theme]')||document.querySelector('[data-av-theme]'))?.getAttribute('data-av-theme')||null
        }})()"""
    )


def point(page: NativePage) -> dict:
    value = page.evaluate(
        """(()=>{const v=__nav.viewport;v.scrollIntoView({block:'center',inline:'center'});const r=v.getBoundingClientRect();
          for(const [fx,fy] of [[.52,.63],[.35,.72],[.72,.72],[.50,.38]]){const x=r.left+r.width*fx,y=r.top+r.height*fy,e=document.elementFromPoint(x,y);if(e&&v.contains(e)&&!e.closest('a[href],button,input,select,textarea,[contenteditable]'))return{x,y,tag:e.tagName,cls:e.getAttribute('class')||''};}return null;})()"""
    )
    if not value:
        raise RuntimeError("no non-interactive hit-tested point was available inside the chosen plot")
    return value


def drag(page: NativePage, dx: float, dy: float) -> dict:
    hit = point(page)
    before = state(page)
    page.call("Input.dispatchMouseEvent", type="mousePressed", button="left", buttons=1, clickCount=1, x=hit["x"], y=hit["y"])
    page.call("Input.dispatchMouseEvent", type="mouseMoved", button="left", buttons=1, x=hit["x"] + dx, y=hit["y"] + dy)
    page.call("Input.dispatchMouseEvent", type="mouseReleased", button="left", buttons=0, clickCount=1, x=hit["x"] + dx, y=hit["y"] + dy)
    page.settle()
    return {"hit": hit, "before": before, "after": state(page)}


def click(page: NativePage, expression: str) -> None:
    page.click(expression)


def choose_mode(page: NativePage, action: str) -> dict:
    available = page.evaluate(
        """(()=>{const panel=document.getElementById(__nav.modeTrigger.getAttribute('aria-controls')||'');
          return panel?[...panel.querySelectorAll('[data-av-figure-action]')].map(e=>e.getAttribute('data-av-figure-action')):[];})()"""
    )
    if action not in available:
        raise RuntimeError(f"chosen plot has no {action!r} mode; available={available!r}")
    click(page, "__nav.modeTrigger")
    click(page, f"document.getElementById(__nav.modeTrigger.getAttribute('aria-controls')||'')?.querySelector('[data-av-figure-action={json.dumps(action)}]')")
    return state(page)


def space_drag(page: NativePage) -> dict:
    page.evaluate("__nav.viewport.focus({preventScroll:true})")
    page.call("Input.dispatchKeyEvent", type="keyDown", key=" ", code="Space", windowsVirtualKeyCode=32, nativeVirtualKeyCode=32)
    held = state(page)
    moved = drag(page, -110, -75)
    page.call("Input.dispatchKeyEvent", type="keyUp", key=" ", code="Space", windowsVirtualKeyCode=32, nativeVirtualKeyCode=32)
    page.settle()
    return {"held": held, "drag": moved, "after": state(page)}


def select_plot(page: NativePage) -> dict | None:
    return page.evaluate(
        """(()=>{const owner=p=>{const direct=p.querySelector(':scope > .av-plot-toolbar [data-av-mode-menu]');
            const trigger=direct||p.querySelector('[data-av-mode-menu]');if(!trigger)return null;
            const panel=document.getElementById(trigger.getAttribute('aria-controls')||'');
            const figure=panel?.parentElement?.closest('[data-av-figure]')||trigger.closest('[data-av-figure]');return figure?{figure,trigger}:null;};
          const plots=[...document.querySelectorAll('[data-av-plot]')].map(plot=>({plot,owned:owner(plot)})).filter(x=>{const v=x.plot.querySelector('.av-plot-scroll');if(!v||!x.owned)return false;const r=v.getBoundingClientRect();return r.width>200&&r.height>100&&getComputedStyle(v).visibility!=='hidden';});
          const chosen=plots.find(x=>{const v=x.plot.querySelector('.av-plot-scroll');return v.scrollWidth<=v.clientWidth+1&&v.scrollHeight<=v.clientHeight+1;})||plots[0];if(!chosen)return null;
          const {plot,owned}=chosen,viewport=plot.querySelector('.av-plot-scroll');globalThis.__nav={plot,figure:owned.figure,modeTrigger:owned.trigger,viewport,savedFigure:owned.figure};
          return{count:plots.length,title:owned.figure.getAttribute('data-av-figure-title')||owned.figure.getAttribute('aria-label'),mode:owned.figure.getAttribute('data-av-selection-mode'),cw:viewport.clientWidth,ch:viewport.clientHeight,sw:viewport.scrollWidth,sh:viewport.scrollHeight};})()"""
    )


def set_theme(page: NativePage, theme: str) -> str:
    current = page.evaluate("(document.querySelector('[data-av-theme]')?.getAttribute('data-av-theme')||null)")
    if current == theme:
        return current
    changed = page.evaluate(
        f"""(()=>{{const input=document.querySelector('input[data-av-setting="theme"][value={json.dumps(theme)}]');if(!input)return false;
          input.checked=true;input.dispatchEvent(new Event('change',{{bubbles:true}}));return true;}})()"""
    )
    if not changed:
        raise RuntimeError(f"report does not expose a theme selector for {theme!r}; current theme is {current!r}")
    page.wait(f"document.querySelector('[data-av-theme]')?.getAttribute('data-av-theme')==={json.dumps(theme)}")
    page.settle()
    return theme


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports", type=Path, default=DEFAULT_REPORTS, help="directory containing assembled HTML reports")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="directory for JSON evidence and screenshots")
    parser.add_argument("--cdp", default=DEFAULT_CDP, help="existing Chrome DevTools HTTP endpoint")
    parser.add_argument("--report", default="compact", help="report stem or filename under --reports (default: compact)")
    parser.add_argument("--theme", choices=("light", "dark", "system"), default="light", help="reader theme to qualify")
    args = parser.parse_args()

    report_name = args.report if args.report.endswith(".html") else args.report + ".html"
    report = (args.reports / report_name).resolve()
    if not report.is_file():
        parser.error(f"missing report: {report}")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    results_path = output / "results.json"
    result: dict[str, object] = {
        "testFile": file_record(Path(__file__).resolve()),
        "report": file_record(report),
        "context": {"endpoint": args.cdp, "report": args.report, "theme": args.theme, "viewport": {"width": 820, "height": 900, "deviceScaleFactor": 1}},
        "checks": [],
        "scenarios": {},
    }
    checks: list[dict[str, object]] = result["checks"]  # type: ignore[assignment]

    def check(name: str, condition: bool, detail: object) -> None:
        checks.append({"name": name, "pass": bool(condition), "detail": detail})

    page = NativePage(args.cdp)
    fatal: str | None = None
    try:
        page.viewport(820, 900)
        page.navigate(report)
        # Workspaces publish data-av-ready; standalone snippets publish an
        # enhanced av-surface instead. Both are valid startup completion paths.
        page.wait(
            """document.readyState==='complete' && !!globalThis.AgenticVisuals
              && !!document.querySelector('.av-workspace[data-av-ready],.av-surface[data-av-enhanced]')
              && !document.documentElement.hasAttribute('data-av-starting')""",
            timeout=35,
        )
        page.settle()
        set_theme(page, args.theme)
        chosen = select_plot(page)
        if not chosen:
            raise RuntimeError("report has no visible plot with drawing interaction controls")
        result["chosen"] = chosen

        initial = state(page)
        no_overflow_drag = drag(page, -100, -70)
        wheel_before = state(page)
        wheel_delta = -180 if wheel_before["pageY"] > 1 else 180
        wheel_hit = point(page)
        page.call("Input.dispatchMouseEvent", type="mouseWheel", x=wheel_hit["x"], y=wheel_hit["y"], deltaX=0, deltaY=wheel_delta)
        page.settle()
        wheel_after = state(page)
        no_overflow_wheel = {"hit": wheel_hit, "deltaY": wheel_delta, "before": wheel_before, "after": wheel_after}
        result["scenarios"]["noOverflow"] = {"initial": initial, "drag": no_overflow_drag, "wheel": no_overflow_wheel}  # type: ignore[index]
        check("fit starts without a false pan affordance", initial["sw"] <= initial["cw"] + 1 and initial["sh"] <= initial["ch"] + 1 and initial["pan"] is None, initial)
        check("drag does not move a fitted drawing", no_overflow_drag["after"]["left"] == no_overflow_drag["before"]["left"] and no_overflow_drag["after"]["top"] == no_overflow_drag["before"]["top"], no_overflow_drag)
        page_can_scroll = wheel_before["pageHeight"] > wheel_before["windowHeight"] + 1
        page_moved = wheel_after["pageY"] != wheel_before["pageY"]
        check("wheel stays out of a fitted drawing and chains to the page", wheel_after["top"] == wheel_before["top"] and (page_moved if page_can_scroll else True), no_overflow_wheel)

        plus = "__nav.plot.querySelector('[data-av-zoom-in]')"
        for _ in range(6):
            click(page, plus)
        zoomed = state(page)
        result["scenarios"]["zoomed"] = zoomed  # type: ignore[index]
        check("zoom creates a real native pan range", zoomed["sw"] > zoomed["cw"] or zoomed["sh"] > zoomed["ch"], zoomed)

        page.evaluate("globalThis.__navCapture=[];__nav.viewport.addEventListener('gotpointercapture',e=>__navCapture.push({type:'got',id:e.pointerId}));__nav.viewport.addEventListener('lostpointercapture',e=>__navCapture.push({type:'lost',id:e.pointerId}))")
        tiny = drag(page, -2, -2)
        tiny_capture = page.evaluate("globalThis.__navCapture.slice()")
        result["scenarios"]["threshold"] = {"drag": tiny, "capture": tiny_capture}  # type: ignore[index]
        check("sub-threshold pointer motion stays click-sized", tiny["after"]["left"] == tiny["before"]["left"] and tiny["after"]["top"] == tiny["before"]["top"] and not tiny_capture, {"drag": tiny, "capture": tiny_capture})

        page.evaluate("globalThis.__navCapture=[]")
        moved = drag(page, -130, -90)
        capture = page.evaluate("globalThis.__navCapture.slice()")
        result["scenarios"]["drag"] = {"drag": moved, "capture": capture}  # type: ignore[index]
        check("native mouse drag pans and completes pointer capture", (moved["after"]["left"] != moved["before"]["left"] or moved["after"]["top"] != moved["before"]["top"]) and any(e["type"] == "got" for e in capture) and any(e["type"] == "lost" for e in capture), {"drag": moved, "capture": capture})

        maximum = drag(page, -10000, -10000)
        max_left, max_top = maximum["after"]["sw"] - maximum["after"]["cw"], maximum["after"]["sh"] - maximum["after"]["ch"]
        minimum = drag(page, 10000, 10000)
        result["scenarios"]["bounds"] = {"maximum": maximum, "minimum": minimum}  # type: ignore[index]
        check("pan clamps to the native maximum range", abs(maximum["after"]["left"] - max_left) <= 1 and abs(maximum["after"]["top"] - max_top) <= 1, {"drag": maximum, "maxLeft": max_left, "maxTop": max_top})
        check("pan clamps back to the native origin", minimum["after"]["left"] == 0 and minimum["after"]["top"] == 0, minimum)

        hit = point(page)
        wheel_before = state(page)
        page.call("Input.dispatchMouseEvent", type="mouseWheel", x=hit["x"], y=hit["y"], deltaX=0, deltaY=170)
        page.settle()
        wheel_after = state(page)
        result["scenarios"]["wheel"] = {"hit": hit, "before": wheel_before, "after": wheel_after}  # type: ignore[index]
        check("native wheel pans an overflowing drawing", wheel_after["top"] > wheel_before["top"], {"before": wheel_before, "after": wheel_after})

        page.evaluate("globalThis.__navCapture=[]")
        hit = point(page)
        page.call("Input.dispatchMouseEvent", type="mousePressed", button="left", buttons=1, clickCount=1, x=hit["x"], y=hit["y"])
        page.call("Input.dispatchMouseEvent", type="mouseMoved", button="left", buttons=1, x=hit["x"] - 70, y=hit["y"] - 55)
        captured = page.evaluate("(()=>{const e=__navCapture.find(x=>x.type==='got');return e?{id:e.id,held:__nav.viewport.hasPointerCapture(e.id)}:null})()")
        released = page.evaluate("(()=>{const e=__navCapture.find(x=>x.type==='got');if(!e)return false;__nav.viewport.releasePointerCapture(e.id);return true})()")
        before_lost = state(page)
        page.call("Input.dispatchMouseEvent", type="mouseMoved", button="left", buttons=1, x=hit["x"] - 170, y=hit["y"] - 135)
        page.settle()
        after_lost = state(page)
        page.call("Input.dispatchMouseEvent", type="mouseReleased", button="left", buttons=0, clickCount=1, x=hit["x"] - 170, y=hit["y"] - 135)
        lost_events = page.evaluate("globalThis.__navCapture.slice()")
        lost = {"captured": captured, "released": released, "before": before_lost, "after": after_lost, "events": lost_events}
        result["scenarios"]["lostCapture"] = lost  # type: ignore[index]
        check("lost pointer capture terminates the drag", bool(captured and captured["held"] and released) and any(e["type"] == "lost" for e in lost_events) and not after_lost["dragging"] and before_lost["left"] == after_lost["left"] and before_lost["top"] == after_lost["top"], lost)

        select = choose_mode(page, "select-items")
        select_drag = drag(page, -100, -70)
        select_space = space_drag(page)
        text = choose_mode(page, "select-text")
        text_drag = drag(page, -100, -70)
        text_space = space_drag(page)
        result["scenarios"]["modes"] = {"select": {"state": select, "drag": select_drag, "space": select_space}, "text": {"state": text, "drag": text_drag, "space": text_space}}  # type: ignore[index]
        check("Select mode blocks ordinary drag pan", select["mode"] == "select" and select_drag["after"]["left"] == select_drag["before"]["left"] and select_drag["after"]["top"] == select_drag["before"]["top"], select_drag)
        check("Space pans without leaving Select mode", select_space["held"]["space"] and (select_space["drag"]["after"]["left"] != select_space["drag"]["before"]["left"] or select_space["drag"]["after"]["top"] != select_space["drag"]["before"]["top"]) and not select_space["after"]["space"] and select_space["after"]["mode"] == "select", select_space)
        check("Text mode blocks ordinary drag pan", text["mode"] == "text" and text_drag["after"]["left"] == text_drag["before"]["left"] and text_drag["after"]["top"] == text_drag["before"]["top"], text_drag)
        check("Space pans without leaving Text mode", text_space["held"]["space"] and (text_space["drag"]["after"]["left"] != text_space["drag"]["before"]["left"] or text_space["drag"]["after"]["top"] != text_space["drag"]["before"]["top"]) and not text_space["after"]["space"] and text_space["after"]["mode"] == "text", text_space)

        choose_mode(page, "pan")
        click(page, "__nav.plot.querySelector('[data-av-zoom-reset]')")
        reset = state(page)
        result["scenarios"]["reset"] = reset  # type: ignore[index]
        check("Reset returns the complete drawing to fit", reset["zoom"] == "1" and reset["viewportMode"] == "fit" and reset["left"] == 0 and reset["top"] == 0 and reset["pan"] is None, reset)

        for _ in range(2):
            click(page, plus)
        drag(page, -75, -55)
        before_expand = state(page)
        click(page, "__nav.figure.querySelector('[data-av-figure-action=\"expand\"]')")
        expanded = state(page)
        page.screenshot(output / "expanded.png")
        click(page, "document.querySelector('.av-focus-dialog[open] [data-av-close-focus]')")
        returned = state(page)
        result["scenarios"]["expandReturn"] = {"before": before_expand, "expanded": expanded, "returned": returned}  # type: ignore[index]
        check("Expand keeps the same live figure", expanded["sameFigure"] and expanded["connected"] and expanded["expanded"] and expanded["dialog"], expanded)
        check("Return restores zoom and scroll state", returned["sameFigure"] and returned["connected"] and not returned["expanded"] and not returned["dialog"] and returned["zoom"] == before_expand["zoom"] and returned["left"] == before_expand["left"] and returned["top"] == before_expand["top"], {"before": before_expand, "returned": returned})

        result["consoleErrors"] = page.console_errors()
        check("native run has no browser console errors", not result["consoleErrors"], result["consoleErrors"])
        page.screenshot(output / "final.png")
    except Exception as error:
        fatal = f"{type(error).__name__}: {error}"
        result["fatal"] = fatal
    finally:
        page.close()

    results_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    failed = [item for item in checks if not item["pass"]]
    summary = {"output": str(results_path), "checks": len(checks), "failed": [item["name"] for item in failed], "fatal": fatal, "chosen": result.get("chosen")}
    print(json.dumps(summary, indent=2))
    return 1 if fatal or failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
