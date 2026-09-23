#!/usr/bin/env python3
"""Native Venn regression for label/note separation and source fidelity."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from native_inspector import NativePage

HERE = Path(__file__).resolve().parent
RICH = (HERE / "mermaid-fixtures/venn.mmd").read_text(encoding="utf-8")
MULTI = """venn-beta
  title Multiple notes remain distinct
  set Alpha["Alpha evidence"]:40
    text AlphaOne["First retained observation"]
    text AlphaTwo["Second retained observation"]
    text AlphaThree["Third retained observation"]
  set Beta["Beta context"]:25
  union Alpha,Beta["Shared evidence"]:4
"""
UNICODE = """venn-beta
  title Unicode note fidelity
  set East["International evidence"]:34
    text EastUnicode["日本語の長い注記 / é café / 👩🏽‍🚀 retained across repeated validation"]
  set West["Independent context"]:22
  union East,West["Shared context"]:3
"""
SINGLE = """venn-beta
  title Ordinary labels only
  set Left["Left evidence"]:22
  set Right["Right evidence"]:18
  union Left,Right["Shared evidence"]:4
"""
CASES = {
    "rich": {
        "source": RICH,
        "notes": {
            "Accepted by the pinned renderer": ["Supported"],
            "Explains the observed behavior": ["Relevant"],
            "Stable across repeated validation": ["Reproducible"],
            "日本語 / é / 👩🏽‍🚀 retained": ["Relevant", "Reproducible", "Supported"],
        },
    },
    "multi": {
        "source": MULTI,
        "notes": {
            "First retained observation": ["Alpha"],
            "Second retained observation": ["Alpha"],
            "Third retained observation": ["Alpha"],
        },
    },
    "unicode": {
        "source": UNICODE,
        "notes": {
            "日本語の長い注記 / é café / 👩🏽‍🚀 retained across repeated validation": ["East"],
        },
    },
    "single": {"source": SINGLE, "notes": {}},
}


def record(path: Path) -> dict[str, object]:
    payload = path.read_bytes()
    return {"path": str(path), "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cdp", required=True)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--vendor", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--expect-collisions", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    result: dict[str, object] = {
        "status": "failed",
        "report": record(args.report),
        "vendor": record(args.vendor),
        "expectCollisions": args.expect_collisions,
        "cases": {},
    }
    page = NativePage(args.cdp)
    try:
        page.viewport(1440, 1000)
        page.navigate(args.report)
        page.wait(
            "typeof AgenticVisuals==='object' && typeof mermaid==='object' && "
            "!!document.querySelector('.av-workspace[data-av-ready]')",
            timeout=60,
        )
        loaded = page.evaluate(args.vendor.read_text(encoding="utf-8") + "\n;typeof globalThis.mermaid")
        require(loaded == "object", f"vendor did not install: {loaded!r}")
        page.events.clear()
        collision_total = 0
        semantic_violations = 0
        for theme, width in (("light", 1440), ("dark", 760)):
            for name, spec in CASES.items():
                source = str(spec["source"])
                notes = dict(spec["notes"])
                page.viewport(width, 1000)
                payload = page.evaluate(
                    """(async()=>{
                      globalThis.__vennCleanup?.();
                      const V=AgenticVisuals,source=SOURCE,theme=THEME,name=NAME,noteMap=NOTES;
                      const holder=document.createElement('div');
                      holder.innerHTML=V.reportSurface({
                        id:'venn-regression-'+theme+'-'+name,theme,palette:'graphite',canvas:'plain',
                        spacing:'comfortable',sections:'solo',
                        body:V.reportSection({id:'venn-section',title:'Venn '+name,
                          body:V.mermaidDiagram({id:'venn-'+theme+'-'+name,title:'Venn '+name,source})})
                      });
                      const root=holder.firstElementChild;
                      if(!root)throw Error('reportSurface returned no root');
                      document.body.replaceChildren(root);
                      globalThis.__vennCleanup=V.enhanceVisuals(root);
                      await __vennCleanup.whenIdle();
                      await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
                      await __vennCleanup.whenIdle();
                      const diagram=root.querySelector('[data-av-mermaid]');
                      const svg=diagram?.querySelector('svg[data-av-mermaid-scene]');
                      if(!svg)throw Error('Venn scene missing: '+(diagram?.getAttribute('data-av-mermaid-state')||'unknown'));
                      const compact=s=>(s||'').replace(/\\s+/g,' ').trim();
                      const rect=r=>({left:r.left,top:r.top,right:r.right,bottom:r.bottom,width:r.width,height:r.height});
                      const ranges=node=>{
                        const q=document.createRange();q.selectNodeContents(node);
                        return [...q.getClientRects()].filter(r=>r.width>0&&r.height>0).map(rect);
                      };
                      const overlap=(a,b)=>{
                        const x=Math.min(a.right,b.right)-Math.max(a.left,b.left);
                        const y=Math.min(a.bottom,b.bottom)-Math.max(a.top,b.top);
                        return x>0.5&&y>0.5?{width:x,height:y,area:x*y}:null;
                      };
                      const circles=new Map([...svg.querySelectorAll('.venn-circle')].map(group=>{
                        const key=group.__data__?.sets?.[0]||group.getAttribute('data-venn-sets');
                        const path=group.querySelector('path'),box=path?.getBBox();
                        return [key,{group,path,box,cx:box?box.x+box.width/2:0,cy:box?box.y+box.height/2:0,r:box?box.width/2:0}];
                      }));
                      const areaFor=sets=>[...svg.querySelectorAll('.venn-area')].find(group=>
                        group.getAttribute('data-venn-sets')===[...sets].sort().join('_')
                      );
                      const pointInside=(circle,x,y)=>{
                        const inv=circle.path.getScreenCTM().inverse();
                        const p=new DOMPoint(x,y).matrixTransform(inv);
                        return circle.path.isPointInFill(p);
                      };
                      const regionCheck=(sets,rects)=>{
                        const wanted=new Set(sets),ignored=new Set();
                        for(const member of sets){
                          const a=circles.get(member);if(!a)continue;
                          for(const [other,b] of circles){
                            if(wanted.has(other))continue;
                            const d=Math.hypot(a.cx-b.cx,a.cy-b.cy);
                            if(d+a.r<=b.r+1e-6)ignored.add(other);
                          }
                        }
                        const violations=[];
                        for(const r of rects){
                          const pts=[
                            [r.left+1,r.top+1],[r.right-1,r.top+1],
                            [r.left+1,r.bottom-1],[r.right-1,r.bottom-1],
                            [(r.left+r.right)/2,(r.top+r.bottom)/2],
                          ];
                          for(const [x,y] of pts){
                            for(const member of sets){
                              const c=circles.get(member);
                              if(c&&!pointInside(c,x,y))violations.push({kind:'outside-member',set:member,x,y});
                            }
                            for(const [other,c] of circles){
                              if(!wanted.has(other)&&!ignored.has(other)&&pointInside(c,x,y)){
                                violations.push({kind:'inside-exterior',set:other,x,y});
                              }
                            }
                          }
                        }
                        return violations;
                      };
                      const noteNodes=[...svg.querySelectorAll('.venn-text-node')];
                      const records=[],collisions=[],semantic=[];
                      for(const [noteText,sets] of Object.entries(noteMap)){
                        const note=noteNodes.find(n=>compact(n.textContent)===compact(noteText));
                        const area=areaFor(sets),label=area?.querySelector('text');
                        if(!note||!label){records.push({noteText,sets,missing:true});continue}
                        const nr=ranges(note),lr=ranges(label),hits=[];
                        for(const a of nr)for(const b of lr){const hit=overlap(a,b);if(hit)hits.push(hit)}
                        const noteSemantic=regionCheck(sets,nr),labelSemantic=regionCheck(sets,lr);
                        collisions.push(...hits.map(hit=>({noteText,sets,hit})));
                        semantic.push(
                          ...noteSemantic.map(v=>({target:'note',noteText,sets,...v})),
                          ...labelSemantic.map(v=>({target:'label',noteText,sets,...v}))
                        );
                        records.push({
                          noteText,sets,noteId:note.closest('.venn-text-node-fo')?.getAttribute('data-venn-note')||null,noteRects:nr,labelText:label.textContent,labelRects:lr,
                          noteFont:getComputedStyle(note).fontSize,labelFont:getComputedStyle(label).fontSize,
                          labelTransform:label.getAttribute('transform'),overlaps:hits,
                          semantic:{note:noteSemantic,label:labelSemantic}
                        });
                      }
                      const circlePaths=Object.fromEntries([...circles].map(([key,c])=>[key,c.path?.getAttribute('d')||'']));
                      const labels=[...svg.querySelectorAll('.venn-area text')].map(n=>compact(n.textContent));
                      const renderedNotes=noteNodes.map(n=>compact(n.textContent));
                      return {
                        theme,name,state:diagram.getAttribute('data-av-mermaid-state'),
                        viewBox:svg.getAttribute('viewBox'),
                        sourceExact:diagram.getAttribute('data-av-mermaid-source')===source,
                        disclosedExact:diagram.querySelector('.av-diagram-source code')?.textContent===source,
                        labels,renderedNotes,circlePaths,records,collisions,semantic
                      };
                    })()"""
                    .replace("SOURCE", json.dumps(source, ensure_ascii=False))
                    .replace("THEME", json.dumps(theme))
                    .replace("NAME", json.dumps(name))
                    .replace("NOTES", json.dumps(notes, ensure_ascii=False))
                )
                require(payload["state"] == "ready", f"{theme}/{name} failed to render")
                require(payload["sourceExact"] and payload["disclosedExact"], f"{theme}/{name} source changed")
                require(all(not r.get("missing") for r in payload["records"]), f"{theme}/{name} lost note/label")
                collision_total += len(payload["collisions"])
                semantic_violations += len(payload["semantic"])
                height = int(page.evaluate("Math.ceil(Math.max(document.body.scrollHeight,document.documentElement.scrollHeight))"))
                page.viewport(width, min(2200, max(900, height + 20)))
                page.settle()
                page.screenshot(args.output / f"{theme}-{name}.png")
                result["cases"][f"{theme}-{name}"] = payload

        result["collisionTotal"] = collision_total
        result["semanticViolationTotal"] = semantic_violations
        if args.expect_collisions:
            require(collision_total > 0, "baseline unexpectedly has no name/note collisions")
            result["status"] = "observed"
        else:
            require(collision_total == 0, f"candidate still has {collision_total} name/note collisions")
            require(semantic_violations == 0, f"candidate has {semantic_violations} semantic-region violations")
            result["status"] = "passed"
        errors=page.console_errors()
        require(not errors,f"Chrome recorded {len(errors)} runtime/console errors")
    except Exception as error:
        result["status"]="failed"
        result["error"]=f"{type(error).__name__}: {error}"
    finally:
        page.close()
        (args.output / "results.json").write_text(
            json.dumps(result,indent=2,ensure_ascii=False)+"\n",encoding="utf-8"
        )
    print(json.dumps({
        "status":result["status"],
        "collisionTotal":result.get("collisionTotal"),
        "semanticViolationTotal":result.get("semanticViolationTotal"),
        "error":result.get("error"),
        "output":str(args.output),
    }))
    return 0 if result["status"] in {"passed","observed"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
