#!/usr/bin/env python3
"""Qualify native Mermaid exports from one generated standalone gallery.

The script owns one page target in an already-running Chromium DevTools process.
It never launches a browser, changes fixture/runtime sources, or rewrites Mermaid
input. Every READY fixture is exported through the real figure download control.
Journey, C4, and Cynefin additionally prove that SVG bytes and decoded PNG pixels
are independent of reader zoom/pan state.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

from native_inspector import NativePage, require
from native_navigation import set_theme


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PROJECT = ROOT / "plugins/agentic-design-and-evaluation"
FIXTURES = HERE / "mermaid-fixtures"
PIXEL_FIXTURES = {"journey.mmd", "c4.mmd", "cynefin.mmd", "ishikawa.mmd", "venn.mmd"}
LABEL_FIXTURES = {"stateDiagram.mmd": "PresentationReview", "untrusted-label.mmd": "literal evidence"}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_record(path: Path) -> dict[str, object]:
    payload = path.read_bytes()
    return {"path": str(path), "bytes": len(payload), "sha256": sha256(payload)}


def safe_stem(filename: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", filename).removesuffix(".mmd") or "fixture"


def compact(value: str) -> str:
    return "".join(value.split())


def check_label_fit(page: NativePage, filename: str, needle: str) -> dict[str, object]:
    """Measure the real label after workspace insertion, without injecting CSS."""
    record = page.evaluate("""(()=>{
      const section=document.querySelector(SELECTOR),svg=section?.querySelector('svg[data-av-mermaid-scene]');
      const fo=[...(svg?.querySelectorAll('foreignObject')||[])].find(e=>e.textContent.includes(NEEDLE));
      if(!fo)return {missing:true};
      const label=fo.querySelector('p')||fo.querySelector('span')||fo.firstElementChild;
      const bounds=e=>{const r=e.getBoundingClientRect();return {left:r.left,top:r.top,right:r.right,bottom:r.bottom,width:r.width,height:r.height}};
      const range=document.createRange();range.selectNodeContents(label);
      const rects=[...range.getClientRects()].filter(r=>r.width>0&&r.height>0);
      if(!rects.length)return {missing:true};
      const glyph={left:Math.min(...rects.map(r=>r.left)),top:Math.min(...rects.map(r=>r.top)),right:Math.max(...rects.map(r=>r.right)),bottom:Math.max(...rects.map(r=>r.bottom))};
      glyph.width=glyph.right-glyph.left;glyph.height=glyph.bottom-glyph.top;
      const node=fo.closest('g.node'),background=node?.querySelector('rect,path,polygon,circle');
      const excess=box=>({left:Math.max(0,box.left-glyph.left),top:Math.max(0,box.top-glyph.top),right:Math.max(0,glyph.right-box.right),bottom:Math.max(0,glyph.bottom-box.bottom)});
      const fr=bounds(fo),br=background?bounds(background):null,style=getComputedStyle(label),matrix=fo.getScreenCTM();
      return {text:label.textContent,foreignObject:fr,glyph,background:br,glyphSpill:excess(fr),backgroundSpill:br?excess(br):null,overflowWrap:style.overflowWrap,fontFamily:style.fontFamily,fontSize:style.fontSize,lineHeight:style.lineHeight,scaleY:matrix?Math.hypot(matrix.c,matrix.d):1};
    })()""".replace("SELECTOR", json.dumps(f'[data-round2-fixture="{filename}"]')).replace("NEEDLE", json.dumps(needle)))
    require(not record.get("missing"), f"missing or unmaterialized label for {filename}")
    require(record["foreignObject"]["width"] > 0 and record["foreignObject"]["height"] > 0, f"empty label geometry for {filename}")
    require(record["overflowWrap"] == "normal", f"workspace wrapping leaks into the measured Mermaid label: {filename}")
    require(max(record["glyphSpill"].values()) <= 1, f"Mermaid label exceeds measured foreignObject for {filename}: {record}")
    require(record["backgroundSpill"] is not None and max(record["backgroundSpill"].values()) <= 1, f"Mermaid label exceeds its visible node background for {filename}: {record}")
    if filename == "untrusted-label.mmd":
        require(record["glyph"]["height"] > 1.5 * float(str(record["fontSize"]).removesuffix("px")) * record["scaleY"], "normal multiline label wrapping was lost")
    return record


def number(value: str | None) -> float | None:
    if value is None:
        return None
    match = re.fullmatch(r"\s*([0-9]+(?:\.[0-9]+)?)\s*(?:px)?\s*", value)
    return float(match.group(1)) if match else None


def view_box(value: str | None) -> tuple[float, float, float, float] | None:
    if not value:
        return None
    try:
        parts = tuple(float(part) for part in re.split(r"[\s,]+", value.strip()))
    except ValueError:
        return None
    return parts if len(parts) == 4 else None


def prepare_output(path: Path) -> None:
    if path.is_symlink() or path.exists() and not path.is_dir():
        raise ValueError(f"output must be a regular directory: {path}")
    if path.exists() and any(path.iterdir()):
        raise ValueError(f"output directory is not empty: {path}; use a new evidence directory")
    (path / "svg").mkdir(parents=True, exist_ok=True)
    (path / "png").mkdir(parents=True, exist_ok=True)


def install_blob_capture(page: NativePage) -> None:
    page.evaluate(
        """(()=>{
          if(globalThis.__mermaidExportCapture)return;
          const create=URL.createObjectURL.bind(URL),click=HTMLAnchorElement.prototype.click;
          globalThis.__mermaidExportCapture={blobs:[],downloads:[]};
          URL.createObjectURL=function(blob){__mermaidExportCapture.blobs.push(blob);return create(blob);};
          HTMLAnchorElement.prototype.click=function(){
            if(this.hasAttribute('data-av-internal-download')){
              __mermaidExportCapture.downloads.push({name:this.download,blobIndex:__mermaidExportCapture.blobs.length-1});
              return;
            }
            return click.call(this);
          };
        })()"""
    )


def section_expression(filename: str) -> str:
    selector = f'[data-round2-fixture="{filename}"]'
    return f"document.querySelector({json.dumps(selector)})"


def figure_expression(filename: str) -> str:
    return section_expression(filename) + ".querySelector('[data-av-figure]')"


def capture_download(page: NativePage, filename: str, action: str, destination: Path) -> tuple[bytes, dict[str, object]]:
    require(action in {"svg", "png"}, f"unsupported export action: {action}")
    install_blob_capture(page)
    figure = figure_expression(filename)
    before = page.evaluate("__mermaidExportCapture.downloads.length")
    # NativePage.click uses hit-tested pointer input and opens an overflow details
    # menu with native input when the menu-only export control is currently hidden.
    page.click(figure + f'.querySelector(\'[data-av-figure-action="{action}"]\')')
    page.wait(f"__mermaidExportCapture.downloads[{before}]||null", timeout=90)
    result = page.evaluate(
        f"""(async()=>{{
          const item=__mermaidExportCapture.downloads[{before}],blob=__mermaidExportCapture.blobs[item.blobIndex];
          const bytes=new Uint8Array(await blob.arrayBuffer());let binary='';
          for(let start=0;start<bytes.length;start+=8192)binary+=String.fromCharCode(...bytes.subarray(start,start+8192));
          let decoded=null;
          if(blob.type==='image/png'){{
            const bitmap=await createImageBitmap(blob),canvas=document.createElement('canvas');
            canvas.width=bitmap.width;canvas.height=bitmap.height;
            const context=canvas.getContext('2d',{{willReadFrequently:true}});if(!context)throw Error('PNG decode canvas unavailable');
            context.drawImage(bitmap,0,0);bitmap.close();
            const pixels=context.getImageData(0,0,canvas.width,canvas.height).data;
            let h1=2166136261>>>0,h2=2246822519>>>0,sum=0;
            for(let i=0;i<pixels.length;i++){{const v=pixels[i];h1=Math.imul(h1^v,16777619)>>>0;h2=Math.imul(h2^(v+(i&255)),3266489917)>>>0;sum=(sum+v)>>>0;}}
            decoded={{width:canvas.width,height:canvas.height,rgbaBytes:pixels.length,pixelHash:[h1.toString(16).padStart(8,'0'),h2.toString(16).padStart(8,'0'),sum.toString(16).padStart(8,'0')].join('-')}};
            canvas.width=canvas.height=0;
          }}
          return {{name:item.name,type:blob.type,size:blob.size,decoded,base64:btoa(binary)}};
        }})()"""
    )
    payload = base64.b64decode(result.pop("base64"))
    destination.write_bytes(payload)
    metadata = {
        "path": str(destination),
        "name": result["name"],
        "type": result["type"],
        "bytes": len(payload),
        "reportedBytes": result["size"],
        "sha256": sha256(payload),
        **({"decoded": result["decoded"]} if result.get("decoded") else {}),
    }
    return payload, metadata


def parsed_svg(payload: bytes) -> tuple[dict[str, object], str]:
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as error:
        raise AssertionError(f"downloaded SVG is not parseable XML: {error}") from error
    require(root.tag.rsplit("}", 1)[-1] == "svg", "downloaded artifact root is not SVG")
    scene = next(
        (
            node
            for node in root.iter()
            if node.tag.rsplit("}", 1)[-1] == "svg" and "data-av-mermaid-scene" in node.attrib
        ),
        None,
    )
    require(scene is not None, "exported SVG does not contain the complete Mermaid scene")
    outer = {
        "width": number(root.get("width")),
        "height": number(root.get("height")),
        "viewBox": view_box(root.get("viewBox")),
    }
    scene_geometry = {
        "width": number(scene.get("width")),
        "height": number(scene.get("height")),
        "viewBox": view_box(scene.get("viewBox")),
        "preserveAspectRatio": scene.get("preserveAspectRatio"),
    }
    require(
        outer["width"] is not None
        and outer["height"] is not None
        and outer["width"] > 0
        and outer["height"] > 0
        and outer["viewBox"] is not None,
        f"exported SVG has incomplete outer geometry: {outer}",
    )
    require(
        scene_geometry["width"] is not None
        and scene_geometry["height"] is not None
        and scene_geometry["width"] > 0
        and scene_geometry["height"] > 0
        and scene_geometry["viewBox"] is not None,
        f"exported Mermaid scene has incomplete geometry: {scene_geometry}",
    )
    return {"outer": outer, "scene": scene_geometry}, " ".join(root.itertext())


def live_records(page: NativePage) -> list[dict[str, object]]:
    return page.evaluate(
        """(()=>[...document.querySelectorAll('[data-round2-fixture]')].map(section=>{
          const diagram=section.querySelector('[data-av-mermaid]'),figure=diagram?.closest('[data-av-figure]'),scene=diagram?.querySelector('svg[data-av-mermaid-scene]');
          const sourceRecord=JSON.parse(figure?.getAttribute('data-av-source')||'null');
          const renderedLabels=[...new Set([...(scene?scene.querySelectorAll('text,foreignObject'):[])].map(node=>(node.textContent||'').replace(/\\s+/g,' ').trim()).filter(Boolean))];
          return {
            file:section.getAttribute('data-round2-fixture'),family:section.getAttribute('data-round2-family'),expected:section.getAttribute('data-round2-expected'),
            state:diagram?.getAttribute('data-av-mermaid-state')||'',status:diagram?.querySelector('[data-av-mermaid-status]')?.textContent||'',
            source:diagram?.getAttribute('data-av-mermaid-source')||'',inlineSource:diagram?.querySelector('.av-diagram-source pre')?.textContent||'',retainedSource:sourceRecord?.text||'',
            title:figure?.getAttribute('data-av-figure-title')||'',caption:figure?.querySelector('figcaption span')?.textContent||'',
            scene:{width:scene?.getAttribute('width')||'',height:scene?.getAttribute('height')||'',viewBox:scene?.getAttribute('viewBox')||'',preserveAspectRatio:scene?.getAttribute('preserveAspectRatio')},
            renderedLabels,visualLimitation:section.querySelector('[data-round2-visual-limitation]')?.textContent||''
          };
        }))()"""
    )


def viewport_state(page: NativePage, filename: str) -> dict[str, object]:
    figure = figure_expression(filename)
    return page.evaluate(
        f"""(()=>{{const f={figure},p=f?.querySelector('[data-av-plot]'),v=f?.querySelector('.av-plot-scroll');return{{
          zoom:Number(p?.getAttribute('data-av-zoom')||0),mode:p?.getAttribute('data-av-viewport-mode')||'',
          left:v?.scrollLeft||0,top:v?.scrollTop||0,scrollWidth:v?.scrollWidth||0,scrollHeight:v?.scrollHeight||0,clientWidth:v?.clientWidth||0,clientHeight:v?.clientHeight||0
        }}}})()"""
    )


def native_zoom_pan(page: NativePage, filename: str) -> tuple[dict[str, object], dict[str, object]]:
    figure = figure_expression(filename)
    before = viewport_state(page, filename)
    for _ in range(2):
        page.click(figure + ".querySelector('[data-av-zoom-in]')")
    page.settle()
    point = page.evaluate(
        f"""(()=>{{const v={figure}.querySelector('.av-plot-scroll'),r=v.getBoundingClientRect();return{{x:r.left+r.width/2,y:r.top+r.height/2}};}})()"""
    )
    for delta_x, delta_y in ((420, 0), (0, 320), (420, 240)):
        page.call("Input.dispatchMouseEvent", type="mouseWheel", x=point["x"], y=point["y"], deltaX=delta_x, deltaY=delta_y)
        page.settle()
        current = viewport_state(page, filename)
        if current["left"] > before["left"] + 1 or current["top"] > before["top"] + 1:
            break
    after = viewport_state(page, filename)
    require(after["zoom"] > max(1, before["zoom"]), f"native zoom did not change {filename}: before={before}, after={after}")
    require(
        after["left"] > before["left"] + 1 or after["top"] > before["top"] + 1,
        f"native wheel did not pan zoomed {filename}: before={before}, after={after}",
    )
    return before, after


def reset_view(page: NativePage, filename: str) -> dict[str, object]:
    figure = figure_expression(filename)
    disabled = page.evaluate(figure + ".querySelector('[data-av-zoom-reset]')?.disabled??true")
    if not disabled:
        page.click(figure + ".querySelector('[data-av-zoom-reset]')")
    state = viewport_state(page, filename)
    require(state["zoom"] == 1 and state["left"] <= 1 and state["top"] <= 1, f"reset did not restore {filename}: {state}")
    return state


def verify_export_context(
    filename: str,
    item: dict[str, object],
    live: dict[str, object],
    svg_payload: bytes,
) -> dict[str, object]:
    geometry, exported_text = parsed_svg(svg_payload)
    export_compact = compact(exported_text)
    title = str(live["title"])
    caption = str(live["caption"])
    require(title and compact(title) in export_compact, f"SVG export lost title for {filename}: {title!r}")
    require(caption and compact(caption) in export_compact, f"SVG export lost caption/context for {filename}")
    limitation = item.get("visualLimitation")
    if isinstance(limitation, str) and limitation:
        require(compact(limitation) in export_compact, f"SVG export lost visual limitation context for {filename}")
    critical = [label for label in item.get("expectedRenderedLabels", []) if isinstance(label, str)]
    missing_critical = [label for label in critical if compact(label) not in export_compact]
    require(not missing_critical, f"SVG export lost critical labels for {filename}: {missing_critical}")
    live_labels = [label for label in live.get("renderedLabels", []) if isinstance(label, str) and compact(label)]
    missing_live = [label for label in live_labels if compact(label) not in export_compact]
    require(not missing_live, f"SVG export lost rendered labels for {filename}: {missing_live[:8]}")

    source_scene = live["scene"]
    assert isinstance(source_scene, dict)
    source_width, source_height, source_box = number(str(source_scene.get("width", ""))), number(str(source_scene.get("height", ""))), view_box(str(source_scene.get("viewBox", "")))
    exported_scene = geometry["scene"]
    assert isinstance(exported_scene, dict)
    require(source_width == exported_scene["width"], f"SVG export changed Mermaid scene width for {filename}: {source_width} != {exported_scene['width']}")
    require(source_height == exported_scene["height"], f"SVG export changed Mermaid scene height for {filename}: {source_height} != {exported_scene['height']}")
    require(source_box == exported_scene["viewBox"], f"SVG export changed Mermaid scene viewBox for {filename}: {source_box} != {exported_scene['viewBox']}")
    require(source_scene.get("preserveAspectRatio") == exported_scene["preserveAspectRatio"], f"SVG export changed preserveAspectRatio for {filename}")
    return {
        "geometry": geometry,
        "title": title,
        "captionSha256": sha256(caption.encode("utf-8")),
        "renderedLabelCount": len(live_labels),
        "criticalLabels": critical,
        "contextSha256": sha256((title + "\n" + caption + "\n" + "\n".join(critical)).encode("utf-8")),
    }


def qualify(page: NativePage, gallery: Path, fixture_root: Path, output: Path, expected_gallery_hash: str, theme: str) -> dict[str, object]:
    index_path = fixture_root / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    require(isinstance(index, list) and index, "fixture index must be a non-empty list")
    by_name = {item["file"]: item for item in index if isinstance(item, dict) and isinstance(item.get("file"), str)}
    require(len(by_name) == len(index), "fixture index has missing or duplicate filenames")
    ready = [item for item in index if item.get("expectedState") == "ready"]
    require(PIXEL_FIXTURES.issubset({item["file"] for item in ready}), "Journey/C4/Cynefin must all be READY fixtures")

    gallery_record = file_record(gallery)
    require(gallery_record["sha256"] == expected_gallery_hash, f"gallery hash mismatch: expected {expected_gallery_hash}, got {gallery_record['sha256']}")
    fixture_records = {name: file_record(fixture_root / name) for name in sorted(by_name)}

    page.viewport(1180, 920)
    page.call("Network.emulateNetworkConditions", offline=True, latency=0, downloadThroughput=0, uploadThroughput=0)
    page.navigate(gallery)
    page.wait(
        f"""(()=>{{const sections=[...document.querySelectorAll('[data-round2-fixture]')];return sections.length==={len(index)}&&sections.every(s=>['ready','error'].includes(s.querySelector('[data-av-mermaid]')?.getAttribute('data-av-mermaid-state')))}})()""",
        timeout=240,
    )
    page.settle()
    show_all = page.evaluate("(()=>{const b=document.querySelector('[data-av-show-all]'),r=b?.getBoundingClientRect();return !!b&&!!r&&r.width>0&&r.height>0&&!b.disabled})()")
    if show_all:
        page.click("document.querySelector('[data-av-show-all]')")
    set_theme(page, theme)
    page.wait(
        """[...document.querySelectorAll('[data-av-mermaid]')].every(scene=>['ready','error'].includes(scene.getAttribute('data-av-mermaid-state')))""",
        timeout=240,
    )
    page.settle()
    live = live_records(page)
    live_by_name = {record["file"]: record for record in live}
    require(set(live_by_name) == set(by_name), "standalone gallery fixture set differs from current index")

    for filename, item in by_name.items():
        record = live_by_name[filename]
        source = (fixture_root / filename).read_bytes().decode("utf-8")
        require(record["source"] == record["inlineSource"] == record["retainedSource"] == source, f"standalone source bytes differ from current fixture: {filename}")
        require(record["state"] == item.get("expectedState"), f"standalone state differs from current fixture index for {filename}: {record['state']}")
        if item.get("visualLimitation"):
            require(str(item["visualLimitation"]) in str(record["visualLimitation"]), f"standalone lost visual limitation for {filename}")

    results: dict[str, object] = {}
    for position, item in enumerate(ready, start=1):
        filename = item["file"]
        print(f"exporting SVG {position}/{len(ready)} {filename}", flush=True)
        reset = reset_view(page, filename)
        label_fit = check_label_fit(page, filename, LABEL_FIXTURES[filename]) if filename in LABEL_FIXTURES else None
        svg_path = output / "svg" / f"{safe_stem(filename)}-reset.svg"
        svg_payload, svg_meta = capture_download(page, filename, "svg", svg_path)
        require(svg_meta["type"].startswith("image/svg+xml") and svg_meta["bytes"] > 100, f"invalid SVG download for {filename}: {svg_meta}")
        export_context = verify_export_context(filename, item, live_by_name[filename], svg_payload)
        record: dict[str, object] = {
            "labelFit": label_fit,
            "family": item.get("family"),
            "kind": item.get("kind"),
            "layout": item.get("layout"),
            "source": fixture_records[filename],
            "resetViewport": reset,
            "svgReset": svg_meta,
            "export": export_context,
        }
        if filename in PIXEL_FIXTURES:
            png_reset_path = output / "png" / f"{safe_stem(filename)}-reset.png"
            png_reset_payload, png_reset = capture_download(page, filename, "png", png_reset_path)
            require(png_reset["type"] == "image/png" and png_reset["bytes"] > 100 and png_reset.get("decoded"), f"invalid reset PNG for {filename}: {png_reset}")
            before, transformed = native_zoom_pan(page, filename)
            svg_pan_path = output / "svg" / f"{safe_stem(filename)}-pan.svg"
            svg_pan_payload, svg_pan = capture_download(page, filename, "svg", svg_pan_path)
            png_pan_path = output / "png" / f"{safe_stem(filename)}-pan.png"
            png_pan_payload, png_pan = capture_download(page, filename, "png", png_pan_path)
            require(svg_pan_payload == svg_payload, f"complete SVG export changed after zoom/pan for {filename}")
            require(png_pan["type"] == "image/png" and png_pan.get("decoded"), f"invalid panned PNG for {filename}: {png_pan}")
            require(png_pan["decoded"] == png_reset["decoded"], f"decoded PNG pixels changed after zoom/pan for {filename}: reset={png_reset['decoded']}, pan={png_pan['decoded']}")
            # PNG encoding itself may vary; decoded pixels are the required invariant.
            require(len(png_reset_payload) == png_reset["bytes"] and len(png_pan_payload) == png_pan["bytes"], "captured PNG byte accounting mismatch")
            record.update({
                "pngReset": png_reset,
                "transformedFrom": before,
                "transformedViewport": transformed,
                "svgPan": svg_pan,
                "pngPan": png_pan,
                "svgInvariant": svg_pan["sha256"] == svg_meta["sha256"],
                "decodedPngInvariant": png_pan["decoded"] == png_reset["decoded"],
            })
            reset_view(page, filename)
        results[filename] = record

    errors = page.console_errors()
    external = [
        event.get("params", {}).get("request", {}).get("url", "")
        for event in page.events
        if event.get("method") == "Network.requestWillBeSent"
        and str(event.get("params", {}).get("request", {}).get("url", "")).startswith(("http://", "https://"))
    ]
    require(not errors, f"Chrome recorded {len(errors)} console/runtime errors")
    require(not external, f"offline standalone attempted HTTP(S) requests: {external}")
    return {
        "gallery": gallery_record,
        "fixtureIndex": file_record(index_path),
        "fixtureCount": len(index),
        "readyCount": len(ready),
        "fixtureSources": fixture_records,
        "fixtures": results,
        "pixelFixtures": sorted(PIXEL_FIXTURES),
        "consoleErrors": len(errors),
        "externalRequests": external,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gallery", required=True, type=Path, help="Final generated standalone mermaid-gallery.html")
    parser.add_argument("--gallery-sha256", required=True, help="Expected SHA-256 for --gallery")
    parser.add_argument("--fixtures", type=Path, default=FIXTURES, help="Current external Mermaid fixture directory")
    parser.add_argument("--output", required=True, type=Path, help="New empty directory for retained SVG/PNG evidence and results.json")
    parser.add_argument("--cdp", required=True, help="Existing Chrome DevTools HTTP endpoint")
    parser.add_argument("--theme", choices=("light", "dark"), default="light", help="Reader theme for rendered/exported evidence")
    args = parser.parse_args()

    gallery, fixture_root, output = args.gallery.resolve(), args.fixtures.resolve(), args.output.resolve()
    if not SHA256_RE.fullmatch(args.gallery_sha256):
        print("error: --gallery-sha256 must be 64 lowercase hexadecimal characters", file=sys.stderr)
        return 2
    if not gallery.is_file():
        print(f"error: gallery does not exist: {gallery}", file=sys.stderr)
        return 2
    if not (fixture_root / "index.json").is_file():
        print(f"error: fixture index does not exist: {fixture_root / 'index.json'}", file=sys.stderr)
        return 2
    actual_gallery_hash = sha256(gallery.read_bytes())
    if actual_gallery_hash != args.gallery_sha256:
        print(
            f"error: gallery SHA-256 mismatch: expected {args.gallery_sha256}, got {actual_gallery_hash}",
            file=sys.stderr,
        )
        return 2
    try:
        prepare_output(output)
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    page: NativePage | None = None
    result: dict[str, object] = {
        "status": "running",
        "requestedGallery": str(gallery),
        "requestedGallerySha256": args.gallery_sha256,
        "theme": args.theme,
        "output": str(output),
    }
    try:
        page = NativePage(args.cdp)
        result["target"] = page.target_id
        result["qualification"] = qualify(page, gallery, fixture_root, output, args.gallery_sha256, args.theme)
        result["status"] = "passed"
        qualification = result["qualification"]
        assert isinstance(qualification, dict)
        print(json.dumps({
            "status": "passed",
            "target": page.target_id,
            "readyFixtures": qualification["readyCount"],
            "pixelFixtures": qualification["pixelFixtures"],
            "output": str(output),
        }, ensure_ascii=False))
        return_code = 0
    except Exception as error:
        result["status"] = "failed"
        result["failure"] = {"type": type(error).__name__, "message": str(error)}
        try:
            if page is not None:
                result["failureScreenshot"] = page.screenshot(output / "failure.png")
        except Exception:
            pass
        print(f"error: {type(error).__name__}: {error}", file=sys.stderr)
        print(f"evidence: {output}", file=sys.stderr)
        return_code = 1
    finally:
        if page is not None:
            page.close()
        (output / "results.json").write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8", newline="\n")
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
