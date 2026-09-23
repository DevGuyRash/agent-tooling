#!/usr/bin/env python3
"""Verify C4 layout uses its rendering container, independent of screen width."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path

from native_inspector import NativePage


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cdp", required=True)
    parser.add_argument("--report", required=True, type=Path, help="assembled offline report with the public visual library")
    parser.add_argument("--source", type=Path, default=Path(__file__).parent / "mermaid-fixtures/c4.mmd")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--vendor", type=Path, help="explicit local candidate runtime for pre-integration qualification")
    parser.add_argument("--observe", action="store_true", help="record a known failing upstream baseline without requiring invariance")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    source = args.source.read_text(encoding="utf-8")
    result = {"reportSha256": hashlib.sha256(args.report.read_bytes()).hexdigest(),
              "sourceSha256": hashlib.sha256(args.source.read_bytes()).hexdigest(),
              "candidateVendorSha256": hashlib.sha256(args.vendor.read_bytes()).hexdigest() if args.vendor else None,
              "cases": [], "status": "failed"}
    page = NativePage(args.cdp)
    try:
        page.call("Network.enable")
        page.call("Network.emulateNetworkConditions", offline=True, latency=0, downloadThroughput=0, uploadThroughput=0)
        page.viewport(1280, 900)
        page.navigate(args.report)
        page.wait("typeof AgenticVisuals==='object' && typeof mermaid==='object'", timeout=30)
        if args.vendor:
            page.evaluate(args.vendor.read_text(encoding="utf-8") + "\n;typeof globalThis.mermaid")
        for screen_width in (390, 800, 1600):
            page.evaluate("globalThis.__c4ContainerCleanup?.()")
            page.call("Emulation.setDeviceMetricsOverride", width=1280, height=900, deviceScaleFactor=1,
                      mobile=False, screenWidth=screen_width, screenHeight=1000, positionX=0, positionY=0)
            record = page.evaluate("""(async()=>{
                const V=AgenticVisuals,host=document.createElement('div');
                host.innerHTML=V.reportSurface({id:'c4-width-regression',theme:'light',palette:'graphite',canvas:'plain',spacing:'comfortable',sections:'solo',body:V.mermaidDiagram({id:'c4-width',title:'C4 container-width qualification',source:SOURCE})});
                const root=host.firstElementChild;root.style.width='1100px';root.style.maxWidth='none';
                document.body.replaceChildren(root);
                globalThis.__c4ContainerCleanup=V.enhanceVisuals(root);
                await globalThis.__c4ContainerCleanup.whenIdle();
                await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));
                const scene=root.querySelector('svg[data-av-mermaid-scene]');
                const geometry=[...scene.querySelectorAll('rect,path,circle,ellipse,text,foreignObject')].filter(e=>!e.closest('defs,marker,clipPath,mask')).map(e=>({tag:e.localName,attributes:['x','y','width','height','d','r','cx','cy','rx','ry','transform'].map(name=>[name,e.getAttribute(name)]),text:e.localName==='text'?e.textContent:null}));
                return {screenWidth:screen.width,availableScreenWidth:screen.availWidth,viewportWidth:innerWidth,containerWidth:root.clientWidth,state:root.querySelector('[data-av-mermaid]').getAttribute('data-av-mermaid-state'),viewBox:scene.getAttribute('viewBox'),text:scene.textContent,geometry};
            })()""".replace("SOURCE", json.dumps(source)))
            if record["availableScreenWidth"] != screen_width:
                raise AssertionError(f"screen emulation did not apply: {record['availableScreenWidth']} != {screen_width}")
            if record["state"] != "ready":
                raise AssertionError(f"C4 did not render at screen width {screen_width}")
            record["geometrySha256"] = hashlib.sha256(json.dumps(record.pop("geometry"), sort_keys=True).encode()).hexdigest()
            screenshot = args.output / f"screen-{screen_width}.png"
            screenshot.write_bytes(base64.b64decode(page.call("Page.captureScreenshot", format="png")["data"]))
            record["screenshot"] = screenshot.name
            result["cases"].append(record)
        result["screenIndependent"] = len({(record["viewBox"], record["geometrySha256"]) for record in result["cases"]}) == 1
        if not result["screenIndependent"] and not args.observe:
            raise AssertionError("C4 geometry changed with physical screen width while the rendering container stayed fixed")
        result["status"] = "observed" if args.observe else "passed"
    except Exception as error:
        result["error"] = str(error)
    finally:
        page.close()
        (args.output / "results.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "screenIndependent": result.get("screenIndependent"), "error": result.get("error"), "output": str(args.output)}))
    return 0 if result["status"] in ("passed", "observed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
