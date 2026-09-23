#!/usr/bin/env python3
"""Qualify exact Mermaid source preservation in an existing standalone report.

This maintainer check attaches to one already-running Chrome process, loads a
standalone report that already contains the current visual-library bundle, and
adds one deterministic source fixture through that public browser API. It does
not build the library, launch a browser, or alter the supplied report.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

from native_inspector import NativePage, require


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PROJECT = ROOT / "plugins/agentic-design-and-evaluation"
DEFAULT_REPORT = PROJECT / ".local/visual-tests/reports/mixed-components.html"
DEFAULT_OUTPUT = PROJECT / ".local/source-review-native"
DEFAULT_CDP = "http://127.0.0.1:38255"

# Deliberately starts with LF while every subsequent line ends CRLF. The long
# qualifier, repeated labels and non-ASCII text make normalization visible.
SOURCE_TEXT = (
    "\nflowchart LR\r\n"
    "  start[\"α launch / ID source-review-001\"] --> repeatedA[\"Repeated label\"]\r\n"
    "  repeatedA --> repeatedB[\"Repeated label\"]\r\n"
    "  repeatedB --> unicode[\"Unicode: 東京 • naïve • Δ • 🙂\"]\r\n"
    "  unicode --> long[\"Long qualifier: "
    + "segment-0123456789-" * 22
    + " duration 17 ms / unit ms / qualifier retained\"]\r\n"
    "  long --> multiline[\"Line one<br/>Line two<br/>Line three\"]\r\n"
)
CAPTION = "Evidence ID source-review-001 · duration 17 ms · qualifier retained · Unicode / repeated labels"


def file_record(path: Path) -> dict[str, object]:
    payload = path.read_bytes()
    return {"path": str(path), "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}


def install_download_capture(page: NativePage) -> None:
    page.evaluate(
        """(()=>{
          if(globalThis.__sourceReviewCapture)return;
          const originalCreate=URL.createObjectURL.bind(URL),originalClick=HTMLAnchorElement.prototype.click;
          globalThis.__sourceReviewCapture={blobs:[],downloads:[]};
          URL.createObjectURL=function(blob){__sourceReviewCapture.blobs.push(blob);return originalCreate(blob);};
          HTMLAnchorElement.prototype.click=function(){
            if(this.hasAttribute('data-av-internal-download')){
              __sourceReviewCapture.downloads.push({name:this.download,blobIndex:__sourceReviewCapture.blobs.length-1});
              return;
            }
            return originalClick.call(this);
          };
        })()"""
    )


def capture_source_download(page: NativePage) -> dict[str, object]:
    install_download_capture(page)
    before = page.evaluate("__sourceReviewCapture.downloads.length")
    page.click("__sourceReviewPanel.querySelector('[data-av-figure-action=\"download-source\"]')")
    item = page.wait(f"__sourceReviewCapture.downloads[{before}]||null", timeout=20)
    encoded = page.evaluate(
        f"""(async()=>{{
          const item=__sourceReviewCapture.downloads[{before}],blob=__sourceReviewCapture.blobs[item.blobIndex];
          const bytes=new Uint8Array(await blob.arrayBuffer());let binary='';
          for(let start=0;start<bytes.length;start+=8192)binary+=String.fromCharCode(...bytes.subarray(start,start+8192));
          return {{name:item.name,type:blob.type,size:blob.size,text:await blob.text(),base64:btoa(binary)}};
        }})()"""
    )
    raw = base64.b64decode(encoded.pop("base64"))
    encoded["bytesValue"] = raw
    return encoded


def capture_figure_download(page: NativePage, action: str) -> dict[str, object]:
    require(action in {"svg", "png"}, f"unsupported figure export action: {action}")
    install_download_capture(page)
    before = page.evaluate("__sourceReviewCapture.downloads.length")
    click_figure_action(page, action)
    page.wait(f"__sourceReviewCapture.downloads[{before}]||null", timeout=60)
    encoded = page.evaluate(
        f"""(async()=>{{
          const item=__sourceReviewCapture.downloads[{before}],blob=__sourceReviewCapture.blobs[item.blobIndex];
          const bytes=new Uint8Array(await blob.arrayBuffer());let binary='';
          for(let start=0;start<bytes.length;start+=8192)binary+=String.fromCharCode(...bytes.subarray(start,start+8192));
          let text=null,decoded=null;
          if(blob.type.startsWith('image/svg+xml'))text=await blob.text();
          if(blob.type==='image/png'){{
            const bitmap=await createImageBitmap(blob),canvas=document.createElement('canvas');
            canvas.width=bitmap.width;canvas.height=bitmap.height;
            const context=canvas.getContext('2d');if(!context)throw Error('PNG decode canvas is unavailable.');
            context.drawImage(bitmap,0,0);bitmap.close();
            const pixels=context.getImageData(0,0,canvas.width,canvas.height).data;
            let h1=2166136261>>>0,h2=2246822519>>>0,sum=0;
            for(let i=0;i<pixels.length;i++){{const value=pixels[i];h1=Math.imul(h1^value,16777619)>>>0;h2=Math.imul(h2^(value+(i&255)),3266489917)>>>0;sum=(sum+value)>>>0;}}
            decoded={{width:canvas.width,height:canvas.height,rgbaBytes:pixels.length,pixelHash:[h1.toString(16).padStart(8,'0'),h2.toString(16).padStart(8,'0'),sum.toString(16).padStart(8,'0')].join('-')}};
            canvas.width=canvas.height=0;
          }}
          return {{name:item.name,type:blob.type,size:blob.size,text,decoded,base64:btoa(binary)}};
        }})()"""
    )
    raw = base64.b64decode(encoded.pop("base64"))
    encoded["bytesValue"] = raw
    return encoded


def inject_source_fixture(page: NativePage) -> dict[str, object]:
    source = json.dumps(SOURCE_TEXT, ensure_ascii=False)
    caption = json.dumps(CAPTION, ensure_ascii=False)
    return page.evaluate(
        f"""(async()=>{{
          if(typeof AgenticVisuals?.reportSurface!=='function'||typeof AgenticVisuals?.mermaidDiagram!=='function'||typeof AgenticVisuals?.enhanceVisuals!=='function')
            throw Error('The standalone does not expose the expected current visual-library browser API.');
          const wrapper=document.createElement('div');
          wrapper.innerHTML=AgenticVisuals.reportSurface({{
            id:'source-review-harness',theme:'light',palette:'graphite',canvas:'plain',spacing:'comfortable',sections:'solo',
            body:AgenticVisuals.reportSection({{
              id:'source-review-section',title:'Exact source qualification',
              body:'<p class="av-note">Scope: exact source bytes · ID source-review-001 · duration 17 ms · unit ms · qualifier retained.</p>'+AgenticVisuals.mermaidDiagram({{
                id:'source-review-figure',title:'Source fidelity diagram',caption:{caption},source:{source}
              }})
            }})
          }});
          const root=wrapper.firstElementChild;if(!root)throw Error('Source-review surface did not render.');
          document.body.appendChild(root);globalThis.__sourceReviewRoot=root;
          globalThis.__sourceReviewCleanup=AgenticVisuals.enhanceVisuals(root);
          await __sourceReviewCleanup.whenIdle();
          await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
          globalThis.__sourceReviewFigure=root.querySelector('#source-review-figure');
          globalThis.__sourceReviewMermaid=__sourceReviewFigure?.querySelector('[data-av-mermaid]');
          return {{root:root.tagName,figure:!!__sourceReviewFigure,state:__sourceReviewMermaid?.getAttribute('data-av-mermaid-state')||null}};
        }})()"""
    )


def click_figure_action(page: NativePage, action: str) -> None:
    button = f"__sourceReviewFigure.querySelector('[data-av-figure-action={json.dumps(action)}]')"
    location = page.evaluate(f"({button})?.getAttribute('data-av-command-location')||null")
    if location == "menu":
        page.click("__sourceReviewFigure.querySelector('.av-command-overflow > summary')")
        require(
            page.evaluate("__sourceReviewFigure.querySelector('.av-command-overflow')?.open===true"),
            f"figure command menu did not open for {action}",
        )
    page.click(button)


def click_figure_control(page: NativePage, selector: str) -> None:
    control = f"__sourceReviewFigure.querySelector({json.dumps(selector)})"
    location = page.evaluate(f"({control})?.getAttribute('data-av-command-location')||null")
    if location == "menu":
        page.click("__sourceReviewFigure.querySelector('.av-command-overflow > summary')")
        require(
            page.evaluate("__sourceReviewFigure.querySelector('.av-command-overflow')?.open===true"),
            f"figure command menu did not open for {selector}",
        )
    page.click(control)


def export_record(payload: dict[str, object], path: Path) -> dict[str, object]:
    raw = payload["bytesValue"]
    assert isinstance(raw, bytes)
    path.write_bytes(raw)
    result = {
        **file_record(path),
        "name": payload["name"],
        "type": payload["type"],
        "reportedBytes": payload["size"],
    }
    if payload.get("decoded"):
        result["decoded"] = payload["decoded"]
    return result


def svg_context(raw: bytes) -> dict[str, object]:
    root = ET.fromstring(raw.decode("utf-8"))
    text = "\n".join(part.strip() for part in root.itertext() if part.strip())
    markers = ["Source fidelity diagram", "source-review-001", "17 ms", "qualifier retained", "Repeated label", "東京", "naïve", "Δ", "🙂"]
    present = {marker: marker in text for marker in markers}
    return {
        "width": root.get("width"),
        "height": root.get("height"),
        "viewBox": root.get("viewBox"),
        "markers": present,
        "allMarkersPresent": all(present.values()),
    }


def qualify(page: NativePage, report: Path, output: Path) -> dict[str, object]:
    source_bytes = SOURCE_TEXT.encode("utf-8")
    textarea_text = SOURCE_TEXT.replace("\r\n", "\n").replace("\r", "\n")
    input_path = output / "source_review_input.mmd"
    input_path.write_bytes(source_bytes)

    page.viewport(1180, 900)
    page.call("Network.emulateNetworkConditions", offline=True, latency=0, downloadThroughput=0, uploadThroughput=0)
    page.navigate(report)
    page.wait("document.readyState==='complete'&&typeof globalThis.AgenticVisuals==='object'", timeout=30)
    injected = inject_source_fixture(page)
    require(injected["figure"], f"Source-review figure was not inserted: {injected}")
    page.wait("['ready','error'].includes(__sourceReviewMermaid?.getAttribute('data-av-mermaid-state'))", timeout=60)
    state = page.evaluate("__sourceReviewMermaid.getAttribute('data-av-mermaid-state')")
    require(state == "ready", f"Source-review Mermaid did not reach ready state: {state}")
    page.settle()

    exact = page.evaluate(
        """(()=>{
          const raw=__sourceReviewFigure.getAttribute('data-av-source');
          const attribute=__sourceReviewMermaid.getAttribute('data-av-mermaid-source');
          const displayed=__sourceReviewMermaid.querySelector('.av-diagram-source code')?.textContent||null;
          const jsonSource=raw?JSON.parse(raw).text:null;
          return {
            attribute,displayed,jsonSource,
            attributeLength:attribute?.length||0,
            carriage:(attribute?.match(/\\r/g)||[]).length,
            newline:(attribute?.match(/\\n/g)||[]).length,
            leading:Array.from(attribute?.slice(0,4)||'').map(value=>value.codePointAt(0))
          };
        })()"""
    )
    require(exact["attribute"] == SOURCE_TEXT, "data-av-mermaid-source differs from the supplied source")
    require(exact["displayed"] == SOURCE_TEXT, "displayed Diagram source differs from the supplied source")
    require(exact["jsonSource"] == SOURCE_TEXT, "data-av-source JSON differs from the supplied source")
    require(SOURCE_TEXT.startswith("\n") and exact["leading"] and exact["leading"][0] == 10, f"leading LF was not retained: {exact['leading']}")
    require(exact["carriage"] == SOURCE_TEXT.count("\r") and exact["carriage"] > 0, f"CR characters were normalized: {exact}")
    require(exact["newline"] == SOURCE_TEXT.count("\n"), f"LF characters were normalized: {exact}")

    click_figure_action(page, "source")
    reader = page.evaluate(
        """(()=>{
          const panel=__sourceReviewFigure.querySelector('[data-av-source-panel]'),text=panel?.querySelector('textarea'),wrap=panel?.querySelector('[data-av-source-wrap]');
          globalThis.__sourceReviewPanel=panel;globalThis.__sourceReviewTextarea=text;globalThis.__sourceReviewWrap=wrap;
          return {open:!!panel?.open||panel?.hasAttribute('open'),value:text?.value||null,wrap:text?.getAttribute('wrap')||null,scrollWidth:text?.scrollWidth||0,clientWidth:text?.clientWidth||0};
        })()"""
    )
    require(reader["open"] and reader["value"] == textarea_text and reader["wrap"] == "soft", f"source reader did not open with the browser's line-ending-normalized source: {reader}")

    page.click("__sourceReviewWrap")
    unwrapped = page.evaluate("({wrap:__sourceReviewTextarea.getAttribute('wrap'),scrollWidth:__sourceReviewTextarea.scrollWidth,clientWidth:__sourceReviewTextarea.clientWidth,value:__sourceReviewTextarea.value})")
    require(unwrapped["value"] == textarea_text, "turning wrapping off changed displayed source text")
    require(unwrapped["wrap"] == "off", f"source reader did not turn wrapping off: {unwrapped}")
    require(unwrapped["scrollWidth"] > unwrapped["clientWidth"] + 20, f"long unwrapped source is not horizontally scrollable: {unwrapped}")
    page.screenshot(output / "source_review_unwrapped.png")

    page.click("__sourceReviewWrap")
    rewrapped = page.evaluate("({wrap:__sourceReviewTextarea.getAttribute('wrap'),scrollWidth:__sourceReviewTextarea.scrollWidth,clientWidth:__sourceReviewTextarea.clientWidth,value:__sourceReviewTextarea.value})")
    require(rewrapped["value"] == textarea_text and rewrapped["wrap"] == "soft", f"rewrapping changed source reader text/state: {rewrapped}")

    downloaded = capture_source_download(page)
    downloaded_bytes = downloaded.pop("bytesValue")
    assert isinstance(downloaded_bytes, bytes)
    download_path = output / "source_review_downloaded.mmd"
    download_path.write_bytes(downloaded_bytes)
    require(downloaded_bytes == source_bytes, "downloaded source bytes differ from the original UTF-8 input")
    require(downloaded["text"] == SOURCE_TEXT, "downloaded Blob text differs from the original source")
    require(downloaded["name"].endswith(".mmd"), f"source download lost its Mermaid filename: {downloaded['name']}")

    page.click("__sourceReviewPanel.querySelector('[aria-label=\"Close source\"]')")
    source_after = page.evaluate("__sourceReviewMermaid.getAttribute('data-av-mermaid-source')")
    require(source_after == SOURCE_TEXT, "opening, wrapping and downloading mutated retained source")

    reset_state = page.evaluate(
        """(()=>{const plot=__sourceReviewFigure.querySelector('[data-av-plot]'),viewport=plot?.querySelector('.av-plot-scroll');return {zoom:plot?.getAttribute('data-av-zoom'),mode:plot?.getAttribute('data-av-viewport-mode'),left:viewport?.scrollLeft||0,top:viewport?.scrollTop||0,source:__sourceReviewMermaid.getAttribute('data-av-mermaid-source')}})()"""
    )
    require(reset_state["zoom"] == "1" and reset_state["source"] == SOURCE_TEXT, f"baseline figure is not reset with exact source: {reset_state}")
    svg_reset_payload = capture_figure_download(page, "svg")
    png_reset_payload = capture_figure_download(page, "png")
    svg_reset_bytes = svg_reset_payload["bytesValue"]
    assert isinstance(svg_reset_bytes, bytes)
    reset_context = svg_context(svg_reset_bytes)
    require(reset_context["allMarkersPresent"], f"reset SVG lost full figure context: {reset_context}")
    require(png_reset_payload.get("decoded"), "reset PNG could not be decoded in native Chrome")

    click_figure_control(page, "[data-av-zoom-in]")
    click_figure_control(page, "[data-av-zoom-in]")
    page.click("__sourceReviewFigure.querySelector('.av-plot-scroll')")
    for _ in range(3):
        page.key("ArrowRight", code="ArrowRight")
    panned_state = page.evaluate(
        """(()=>{const plot=__sourceReviewFigure.querySelector('[data-av-plot]'),viewport=plot?.querySelector('.av-plot-scroll');return {zoom:plot?.getAttribute('data-av-zoom'),mode:plot?.getAttribute('data-av-viewport-mode'),left:viewport?.scrollLeft||0,top:viewport?.scrollTop||0,scrollWidth:viewport?.scrollWidth||0,clientWidth:viewport?.clientWidth||0}})()"""
    )
    require(float(panned_state["zoom"] or 0) > 1 and panned_state["scrollWidth"] > panned_state["clientWidth"] and panned_state["left"] > 20, f"real zoom/pan controls did not create a shifted viewport: {panned_state}")

    click_figure_action(page, "source")
    source_while_panned = page.evaluate(
        """(()=>{const panel=__sourceReviewFigure.querySelector('[data-av-source-panel]'),text=panel?.querySelector('textarea'),plot=__sourceReviewFigure.querySelector('[data-av-plot]'),viewport=plot?.querySelector('.av-plot-scroll');return {open:!!panel?.open||panel?.hasAttribute('open'),reader:text?.value||null,raw:__sourceReviewMermaid.getAttribute('data-av-mermaid-source'),zoom:plot?.getAttribute('data-av-zoom'),left:viewport?.scrollLeft||0}})()"""
    )
    require(source_while_panned["open"] and source_while_panned["reader"] == textarea_text and source_while_panned["raw"] == SOURCE_TEXT, f"source became unavailable or changed while zoomed/panned: {source_while_panned}")
    require(float(source_while_panned["zoom"] or 0) > 1 and source_while_panned["left"] > 0, f"opening source unexpectedly reset pan/zoom: {source_while_panned}")
    page.click("__sourceReviewFigure.querySelector('[data-av-source-panel] [aria-label=\"Close source\"]')")

    svg_panned_payload = capture_figure_download(page, "svg")
    png_panned_payload = capture_figure_download(page, "png")
    svg_panned_bytes = svg_panned_payload["bytesValue"]
    assert isinstance(svg_panned_bytes, bytes)
    panned_context = svg_context(svg_panned_bytes)
    require(panned_context["allMarkersPresent"], f"panned SVG lost full figure context: {panned_context}")
    svg_reset_record = export_record(svg_reset_payload, output / "source_review_reset.svg")
    png_reset_record = export_record(png_reset_payload, output / "source_review_reset.png")
    svg_panned_record = export_record(svg_panned_payload, output / "source_review_panned.svg")
    png_panned_record = export_record(png_panned_payload, output / "source_review_panned.png")
    export_findings = {
        "resetState": reset_state,
        "pannedState": panned_state,
        "sourceWhilePanned": source_while_panned,
        "svgReset": {**svg_reset_record, "context": reset_context},
        "svgPanned": {**svg_panned_record, "context": panned_context},
        "pngReset": png_reset_record,
        "pngPanned": png_panned_record,
        "svgByteIdentical": svg_panned_bytes == svg_reset_bytes,
        "decodedPngIdentical": png_panned_payload.get("decoded") == png_reset_payload.get("decoded"),
    }
    (output / "source_review_export_findings.json").write_text(
        json.dumps(export_findings, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    require(svg_panned_bytes == svg_reset_bytes, "SVG export changed with reader pan/zoom state")
    require(png_panned_payload.get("decoded") == png_reset_payload.get("decoded"), f"decoded PNG changed with reader pan/zoom state: reset={png_reset_payload.get('decoded')} panned={png_panned_payload.get('decoded')}")
    require(page.evaluate("__sourceReviewMermaid.getAttribute('data-av-mermaid-source')") == SOURCE_TEXT, "figure exports mutated retained source")

    errors = page.console_errors()
    external = [
        event.get("params", {}).get("request", {}).get("url", "")
        for event in page.events
        if event.get("method") == "Network.requestWillBeSent"
        and str(event.get("params", {}).get("request", {}).get("url", "")).startswith(("http://", "https://"))
    ]
    require(not errors, f"Chrome recorded console/runtime errors: {len(errors)}")
    require(not external, f"offline standalone attempted external network requests: {external}")

    page.evaluate("__sourceReviewCleanup?.();__sourceReviewRoot?.remove()")
    return {
        "injected": injected,
        "source": {
            "input": file_record(input_path),
            "pythonCodepoints": len(SOURCE_TEXT),
            "utf8Bytes": len(source_bytes),
            "carriageReturns": SOURCE_TEXT.count("\r"),
            "lineFeeds": SOURCE_TEXT.count("\n"),
            "leadingCodePoint": ord(SOURCE_TEXT[0]),
            "exactDom": exact,
        },
        "reader": {
            "initial": reader,
            "unwrapped": unwrapped,
            "rewrapped": rewrapped,
            "lineEndingNormalization": {
                "observed": reader["value"] != SOURCE_TEXT,
                "rawCarriageReturns": SOURCE_TEXT.count("\r"),
                "displayedCarriageReturns": reader["value"].count("\r"),
                "displayedLineFeeds": reader["value"].count("\n"),
            },
        },
        "download": {
            **file_record(download_path),
            "name": downloaded["name"],
            "type": downloaded["type"],
            "reportedBytes": downloaded["size"],
        },
        "exports": export_findings,
        "consoleErrors": len(errors),
        "externalRequests": external,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT, help="Existing standalone HTML carrying the current embedded visual-library bundle.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Directory for source_review evidence files.")
    parser.add_argument("--cdp", default=DEFAULT_CDP, help="Existing Chrome DevTools HTTP endpoint.")
    args = parser.parse_args()

    report, output = args.report.resolve(), args.output.resolve()
    if not report.is_file():
        print(f"error: standalone report does not exist: {report}", file=sys.stderr)
        return 2
    output.mkdir(parents=True, exist_ok=True)
    result: dict[str, object] = {"report": file_record(report), "output": str(output)}
    page: NativePage | None = None
    try:
        page = NativePage(args.cdp)
        result["target"] = page.target_id
        result["qualification"] = qualify(page, report, output)
        result["status"] = "passed"
        (output / "source_review_results.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        print(json.dumps({"status": "passed", "target": page.target_id, "output": str(output)}, ensure_ascii=False))
        return 0
    except Exception as error:
        result["status"] = "failed"
        result["failure"] = {"type": type(error).__name__, "message": str(error)}
        try:
            if page is not None:
                page.screenshot(output / "source_review_failure.png")
        except Exception:
            pass
        (output / "source_review_results.json").write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8", newline="\n")
        print(f"error: {type(error).__name__}: {error}", file=sys.stderr)
        print(f"evidence: {output / 'source_review_results.json'}", file=sys.stderr)
        return 1
    finally:
        if page is not None:
            page.close()


if __name__ == "__main__":
    raise SystemExit(main())
