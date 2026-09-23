#!/usr/bin/env python3
"""Native Ishikawa regression for wrapped-label spacing and source fidelity."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from native_inspector import NativePage


HERE = Path(__file__).resolve().parent
RICH_SOURCE = (HERE / "mermaid-fixtures/ishikawa.mmd").read_text(encoding="utf-8")

SHALLOW_SOURCE = """ishikawa-beta
  Delayed fulfillment during a synchronized promotion window
  Process
    Reconciliation backlog accumulates while downstream acknowledgements arrive out of order
    Retry coordination repeats work after transient dependency timeouts during peak traffic
    Inventory reservations remain pending while asynchronous payment callbacks are reconciled
    Shipment batching waits for every regional carrier cutoff to finish before releasing work
    Promotion validation rechecks unchanged campaign rules for each individual order request
    Audit enrichment performs repeated lookups before completed orders can leave the workflow
  People
    Regional escalation ownership changes during handoff windows and delays acknowledgement
    Incident notes omit the request correlation value needed to join duplicate support reports
    Operations reviewers alternate between queues while unresolved orders keep accumulating
    Manual exception routing depends on a single specialist reviewing every ambiguous outcome
    Weekend coverage spans multiple time zones without a shared view of pending fulfillment
    Customer callbacks arrive before support staff can see the latest reconciliation status
"""

NESTED_SOURCE = """ishikawa-beta
  Inconsistent settlement completion after coordinated releases
  Platform
    Database connection acquisition waits behind synchronized retry bursts from checkout workers
      Pool refill tasks compete with long-running history queries during regional traffic spikes
      Connection validation repeats across replicas while failover health checks are still active
      Query cancellation cleanup holds sessions until every transaction observer has acknowledged
    Cache invalidation processing falls behind when many deployment generations become active
      Cross-region fanout batches wait for slow acknowledgements before publishing newer versions
      Expiration workers revisit unchanged keys while recovery traffic continues to refill entries
      Metadata refresh jobs share the same queue as user-facing cache misses during warm-up
  Operations
    Deployment handoff documentation omits the owning team for delayed settlement reconciliation
      Escalation paging rotates between responders before the original diagnostic context is copied
      Release validation notes arrive after the next environment promotion has already started
    Recovery playbooks require manual correlation of identifiers from several independent systems
      Support staff transcribe settlement references before operators can compare duplicate events
      Follow-up ownership changes whenever the incident crosses a regional support boundary
"""

CASES = {
    "rich": RICH_SOURCE,
    "shallow": SHALLOW_SOURCE,
    "nested": NESTED_SOURCE,
}


def source_meta(source: str) -> dict[str, object]:
    lines = [line for line in source.splitlines()[1:] if line.strip()]
    indents = [len(line) - len(line.lstrip(" ")) for line in lines]
    top_indent = min(indents)
    labels = [line.strip() for line in lines]
    top_level = max(0, sum(indent == top_indent for indent in indents) - 1)
    return {
        "labels": labels,
        "labelCount": len(labels),
        "topLevelCount": top_level,
        "subBranchCount": len(labels) - top_level - 1,
    }


def file_record(path: Path) -> dict[str, object]:
    payload = path.read_bytes()
    return {"path": str(path), "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cdp", required=True, help="Existing Chrome DevTools HTTP endpoint")
    parser.add_argument("--report", required=True, type=Path, help="assembled offline report exposing AgenticVisuals")
    parser.add_argument("--vendor", type=Path, help="local Mermaid candidate evaluated after the report starts")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--expect-collisions", action="store_true", help="qualify a known failing bundled baseline")
    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)
    result: dict[str, object] = {
        "status": "failed",
        "report": file_record(args.report),
        "candidateVendor": file_record(args.vendor) if args.vendor else None,
        "expectCollisions": args.expect_collisions,
        "cases": {},
    }
    page = NativePage(args.cdp)
    try:
        page.viewport(1600, 1300)
        page.navigate(args.report)
        page.wait(
            "typeof AgenticVisuals==='object' && typeof mermaid==='object' && "
            "!!document.querySelector('.av-workspace[data-av-ready]') && "
            "!document.documentElement.hasAttribute('data-av-starting')",
            timeout=90,
        )
        if args.vendor:
            loaded = page.evaluate(args.vendor.read_text(encoding="utf-8") + "\n;typeof globalThis.mermaid")
            require(loaded == "object", f"candidate did not replace the Mermaid runtime: {loaded!r}")
        page.events.clear()

        collision_total = 0
        for theme, width in (("light", 1600), ("dark", 980)):
            for case_name, source in CASES.items():
                page.viewport(width, 1300)
                meta = source_meta(source)
                payload = page.evaluate(
                    """(async()=>{
                      globalThis.__ishikawaCleanup?.();
                      const V=AgenticVisuals,source=SOURCE,meta=META,theme=THEME,name=NAME;
                      const wrapper=document.createElement('div');
                      wrapper.innerHTML=V.reportSurface({
                        id:'ishikawa-label-regression-'+theme+'-'+name,theme,palette:'graphite',canvas:'plain',spacing:'comfortable',sections:'solo',
                        body:V.reportSection({id:'ishikawa-section-'+theme+'-'+name,title:'Ishikawa wrapped labels · '+name,
                          body:V.mermaidDiagram({id:'ishikawa-'+theme+'-'+name,title:'Ishikawa '+name,source})})
                      });
                      const root=wrapper.firstElementChild;if(!root)throw Error('reportSurface returned no root');
                      document.body.replaceChildren(root);
                      globalThis.__ishikawaCleanup=V.enhanceVisuals(root);
                      await __ishikawaCleanup.whenIdle();
                      await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
                      await __ishikawaCleanup.whenIdle();
                      const diagram=root.querySelector('[data-av-mermaid]'),svg=diagram?.querySelector('svg[data-av-mermaid-scene]');
                      if(!svg)throw Error('Ishikawa scene did not render: '+(diagram?.getAttribute('data-av-mermaid-state')||'missing'));
                      const compact=value=>(value||'').replace(/\\s+/g,'');
                      const textNodes=[...svg.querySelectorAll('.ishikawa text')];
                      const labels=textNodes.map((node,index)=>{const r=node.getBoundingClientRect();return{index,text:node.textContent||'',compact:compact(node.textContent),left:r.left,top:r.top,right:r.right,bottom:r.bottom,width:r.width,height:r.height};});
                      const pairs=[...svg.querySelectorAll('.ishikawa-pair')],pairIndex=node=>pairs.indexOf(node.closest('.ishikawa-pair'));
                      const collisionBoxes=[];
                      for(const [index,group] of [...svg.querySelectorAll('.ishikawa-label-group')].entries()){
                        const node=group.querySelector('.ishikawa-label-box')||group.querySelector('text'),r=node.getBoundingClientRect();
                        collisionBoxes.push({kind:'cause-box',index,pair:pairIndex(group),text:group.querySelector('text')?.textContent||'',left:r.left,top:r.top,right:r.right,bottom:r.bottom,width:r.width,height:r.height});
                      }
                      for(const [index,node] of [...svg.querySelectorAll('.ishikawa-sub-group text')].entries()){
                        const r=node.getBoundingClientRect();
                        collisionBoxes.push({kind:'descendant-text',index,pair:pairIndex(node),text:node.textContent||'',left:r.left,top:r.top,right:r.right,bottom:r.bottom,width:r.width,height:r.height});
                      }
                      const collisions=[];
                      for(let i=0;i<collisionBoxes.length;i++)for(let j=i+1;j<collisionBoxes.length;j++){
                        const a=collisionBoxes[i],b=collisionBoxes[j],x=Math.min(a.right,b.right)-Math.max(a.left,b.left),y=Math.min(a.bottom,b.bottom)-Math.max(a.top,b.top);
                        if(x>0.5&&y>0.5)collisions.push({a:i,b:j,aKind:a.kind,bKind:b.kind,aPair:a.pair,bPair:b.pair,aText:a.text,bText:b.text,overlapWidth:x,overlapHeight:y});
                      }
                      const actual=labels.map(item=>item.compact).sort(),expected=meta.labels.map(compact).sort();
                      const branches=svg.querySelectorAll('.ishikawa-branch').length,subBranches=svg.querySelectorAll('.ishikawa-sub-branch').length;
                      const arrows=svg.querySelectorAll('.ishikawa-branch[marker-start],.ishikawa-sub-branch[marker-start]').length;
                      const viewBox=svg.getAttribute('viewBox'),vb=svg.viewBox.baseVal,content=svg.querySelector('.ishikawa')?.getBBox();
                      const contentInsideViewBox=!!content&&content.x>=vb.x-1&&content.y>=vb.y-1&&content.x+content.width<=vb.x+vb.width+1&&content.y+content.height<=vb.y+vb.height+1;
                      return{
                        theme,name,state:diagram.getAttribute('data-av-mermaid-state'),viewBox,
                        contentBBox:content?{x:content.x,y:content.y,width:content.width,height:content.height}:null,contentInsideViewBox,
                        sourceExact:diagram.getAttribute('data-av-mermaid-source')===source,
                        disclosedSourceExact:diagram.querySelector('.av-diagram-source code')?.textContent===source,
                        labelCount:labels.length,expectedLabelCount:meta.labelCount,labelsExact:JSON.stringify(actual)===JSON.stringify(expected),
                        branches,expectedBranches:meta.topLevelCount,subBranches,expectedSubBranches:meta.subBranchCount,
                        arrows,expectedArrows:meta.topLevelCount+meta.subBranchCount,collisions,labels,collisionBoxes
                      };
                    })()"""
                    .replace("SOURCE", json.dumps(source, ensure_ascii=False))
                    .replace("META", json.dumps(meta, ensure_ascii=False))
                    .replace("THEME", json.dumps(theme))
                    .replace("NAME", json.dumps(case_name))
                )
                require(payload["state"] == "ready", f"{theme}/{case_name} did not render: {payload}")
                require(payload["sourceExact"] and payload["disclosedSourceExact"], f"{theme}/{case_name} source changed")
                require(payload["labelCount"] == payload["expectedLabelCount"] and payload["labelsExact"], f"{theme}/{case_name} labels changed")
                require(payload["contentInsideViewBox"], f"{theme}/{case_name} content extends outside final SVG viewBox")
                require(payload["branches"] == payload["expectedBranches"], f"{theme}/{case_name} top-level cause count changed")
                require(payload["subBranches"] == payload["expectedSubBranches"], f"{theme}/{case_name} descendant relation count changed")
                require(payload["arrows"] == payload["expectedArrows"], f"{theme}/{case_name} arrow count changed")
                collision_total += len(payload["collisions"])
                document_height = page.evaluate(
                    "Math.ceil(Math.max(document.documentElement.scrollHeight,document.body.scrollHeight))"
                )
                screenshot_height = min(5000, max(900, int(document_height) + 20))
                page.viewport(width, screenshot_height)
                page.settle()
                payload["documentHeight"] = document_height
                payload["screenshotHeight"] = screenshot_height
                page.screenshot(args.output / f"{theme}-{case_name}.png")
                cases = result["cases"]
                assert isinstance(cases, dict)
                cases[f"{theme}-{case_name}"] = payload

        result["collisionTotal"] = collision_total
        if args.expect_collisions:
            require(collision_total > 0, "baseline unexpectedly has no wrapped-label collisions")
            result["status"] = "observed"
        else:
            require(collision_total == 0, f"candidate still has {collision_total} wrapped-label collisions")
            result["status"] = "passed"
        errors = page.console_errors()
        require(not errors, f"Chrome recorded {len(errors)} console/runtime errors during Ishikawa qualification")
    except Exception as error:
        result["status"] = "failed"
        result["error"] = f"{type(error).__name__}: {error}"
    finally:
        page.close()
        (args.output / "results.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(json.dumps({"status": result["status"], "collisionTotal": result.get("collisionTotal"), "error": result.get("error"), "output": str(args.output)}))
    return 0 if result["status"] in {"passed", "observed"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
