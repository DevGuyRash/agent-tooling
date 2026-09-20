import { fingerprint } from './identity';
import { figureOf, figureTitle, visualAdapter, figureOrigin, figureContext } from './figures';
import { ReviewAnchor, ReviewTarget } from "./review-types";
export type { ReviewAnchor, ReviewTarget } from "./review-types";
export interface ResolvedAnchor { status: 'resolved' | 'missing' | 'changed' | 'ambiguous'; element?: HTMLElement; range?: Range; message: string }
export interface TargetRegistry {
  targets: ReadonlyMap<string, { element: HTMLElement; target: ReviewTarget }>;
  anchor(element: HTMLElement): ReviewAnchor;
  selection(selection: Selection): ReviewAnchor | null;
  item(element: Element): ReviewAnchor | null;
  resolve(anchor: ReviewAnchor): ResolvedAnchor;
  cleanup(): void;
}
const substitutes=new WeakMap<Node,Element>();
export function registerReviewPlaceholder(marker:Node,element:Element):()=>void{substitutes.set(marker,element);return()=>substitutes.delete(marker);}
const excluded = '.av-frame-tools,.av-view-status,[data-av-controls],[data-av-review-ui],[data-av-notebook],script,style,.av-sr-only,.av-figure-actions';
function reviewNodes(element: Node): {node:Node;start:number;end:number}[] {
  const nodes:{node:Node;start:number;end:number}[]=[];let offset=0;
  const visit=(node:Node):void=>{const original=substitutes.get(node);if(original){visit(original);return;}if(node.nodeType===3){const start=offset;offset+=(node.textContent||'').length;nodes.push({node,start,end:offset});}else if((node.nodeType===1&&!(node as Element).matches(excluded+',.av-focus-dialog'))||node.nodeType===11)for(const child of Array.from(node.childNodes))visit(child);};
  visit(element);return nodes;
}
export function reviewText(element: Element): string {return reviewNodes(element).map(item=>item.node.textContent||'').join('');}
function reviewOffset(root:Element,boundary:Node,at:number):number|null {
  let count=0,result:number|null=null;
  const visit=(node:Node):void=>{
    if(result!==null)return;const original=substitutes.get(node);if(original){visit(original);return;}
    if(node===boundary){result=count+(node.nodeType===3?at:Array.from(node.childNodes).slice(0,at).reduce((sum,child)=>sum+reviewNodes(child).reduce((n,part)=>n+part.end-part.start,0),0));return;}
    if(node.nodeType===3)count+=(node.textContent||'').length;
    else if((node.nodeType===1&&!(node as Element).matches(excluded+',.av-focus-dialog'))||node.nodeType===11)for(const child of Array.from(node.childNodes))visit(child);
  };visit(root);return result;
}
function contentIdentity(element:Element):string {
  const parts:unknown[]=[];
  const visit=(node:Node):void=>{
    const original=substitutes.get(node);if(original){visit(original);return;}
    if(node.nodeType===3){parts.push(node.textContent||'');return;}
    if(node.nodeType!==1)return;const current=node as Element;if(current.matches(excluded+',.av-focus-dialog'))return;
    const recipe=current.getAttribute('data-av-layout-input');if(recipe){parts.push(['layout',current.getAttribute('data-av-layout-kind'),recipe]);return;}
    const diagram=current.getAttribute('data-av-mermaid-source');if(diagram!==null){parts.push(['mermaid',diagram,current.getAttribute('data-av-mermaid-config')]);return;}
    if(current.hasAttribute('data-av-source')){parts.push(['source',current.getAttribute('data-av-source')]);return;}
    if(current.hasAttribute('data-av-adapter')){const items=visualAdapter(current as HTMLElement)?.items?.(current as HTMLElement);if(items)parts.push(['items',items]);}
    if(current.tagName.toLowerCase()==='img')parts.push(['image',current.getAttribute('src'),current.getAttribute('alt')]);
    if(current.tagName.toLowerCase()==='a')parts.push(['link',current.getAttribute('href')]);
    for(const child of Array.from(node.childNodes))visit(child);
  };visit(element);return JSON.stringify(parts);
}
function grounds(element:HTMLElement):string{return (element.closest('[data-av-layout-input]')||(element.hasAttribute('data-av-figure')?figureOrigin(element).owner:null))?.getAttribute('data-av-layout-input')||contentIdentity(element);}
function sources(element:Element):{label:string;href:string}[]{const roots=[element,...(element.hasAttribute('data-av-figure')?figureContext(element as HTMLElement):[])],links=roots.flatMap(root=>Array.from(root.querySelectorAll('a[href]'))).filter(node=>!node.closest(excluded)).map(node=>({label:node.textContent||'',href:node.getAttribute('href')||''}));return [...new Map(links.map(link=>[JSON.stringify(link),link])).values()];}
function label(element: HTMLElement): string {
  if (element.hasAttribute('data-av-figure')) return figureTitle(element);
  // A report or view must not borrow the first nested figure's title. Besides
  // confusing the notebook and Resume button, that misstates annotation context.
  const owned = (heading: Element): boolean => {
    if (heading.closest(excluded)) return false;
    for (let parent = heading.parentElement; parent && parent !== element; parent = parent.parentElement)
      if (parent.matches('.av-card,[data-av-panel],[data-av-figure],[data-av-object],[data-av-notebook]')) return false;
    return true;
  };
  const heading = Array.from(element.querySelectorAll('.av-card-title,h1,h2,h3')).find(owned)
    || Array.from(element.querySelectorAll('summary')).find(owned);
  return (heading ? reviewText(heading).trim() : '') || element.getAttribute('aria-label') || 'Report section';
}

export function createTargetRegistry(scope: HTMLElement, revision: string, excludedScopes: readonly HTMLElement[] = []): TargetRegistry {
  const entries=new Map<string,{element:HTMLElement;target:ReviewTarget}>(),initialIds=new Map<HTMLElement,string|null>();
  const candidates=[scope,...Array.from(scope.querySelectorAll<HTMLElement>('.av-card,[data-av-panel],[data-av-figure],[data-av-object]')).filter(element=>!element.matches('.av-focus-placeholder')&&!element.parentElement?.closest('[data-av-notebook]')&&!excludedScopes.some(other=>other!==scope&&other.contains(element)))];
  // Validate authored identities before assigning any generated IDs. A failed
  // enhancement must not leave partially adopted evidence behind.
  const counts = new Map<string, number>();
  for (const node of Array.from(scope.ownerDocument.querySelectorAll('[id]'))) counts.set(node.id, (counts.get(node.id) || 0) + 1);
  for (const element of candidates) if (element.id && (counts.get(element.id) || 0) > 1) throw new Error('Review targets need unique IDs.');
  try { for(const element of candidates){
    if(element.hasAttribute('data-av-figure') && figureOf(element)!==element)continue;
    const title=label(element),path:string[]=[];
    for(let parent=element.parentElement;parent&&parent!==scope;parent=parent.parentElement)if(parent.matches('.av-card,[data-av-panel],[data-av-object]'))path.unshift(label(parent));
    const text=reviewText(element),recipe=grounds(element);
    const signature=fingerprint(JSON.stringify([title,path,recipe]));
    if(!element.id){const base=(scope.id||'report')+'--target-'+signature.split(':')[1].slice(0,18);let id=base,index=1;while(entries.has(id)||scope.ownerDocument.getElementById(id))id=base+'-'+(++index);initialIds.set(element,null);element.id=id;}
    if(entries.has(element.id))throw new Error('Review targets need unique IDs.');
    entries.set(element.id,{element,target:{reportId:scope.id,revision,id:element.id,label:title,path,fingerprint:signature,excerpt:text,sources:sources(element)}});
  }
  } catch (error) { for (const element of initialIds.keys()) element.removeAttribute('id'); throw error; }
  const signatures=new Map<string,{element:HTMLElement;target:ReviewTarget}[]>();
  for(const entry of entries.values())if(initialIds.has(entry.element)){const group=signatures.get(entry.target.fingerprint)||[];group.push(entry);signatures.set(entry.target.fingerprint,group);}
  for(const group of signatures.values())if(group.length>1)for(const entry of group)entry.target.ambiguous=true;
  const signature=(entry:{element:HTMLElement;target:ReviewTarget}):string=>fingerprint(JSON.stringify([label(entry.element),entry.target.path,grounds(entry.element)]));
  const owner=(element:Element):{element:HTMLElement;target:ReviewTarget}|undefined=>{
    for(let current:Element|null=element;current;current=current.parentElement){const entry=entries.get(current.id);if(entry?.element===current)return entry;}return undefined;
  };
  const fresh=(entry:{element:HTMLElement;target:ReviewTarget}):ReviewTarget=>({...entry.target,label:label(entry.element),fingerprint:signature(entry),excerpt:reviewText(entry.element),sources:sources(entry.element)});
  const anchor=(element:HTMLElement):ReviewAnchor=>{const entry=owner(element);if(!entry)throw new Error('This content has no review target.');return{kind:entry.element.hasAttribute('data-av-figure')?'figure':'section',target:fresh(entry)};};
  return {
    targets:entries,anchor,
    selection(selection){
      if(selection.isCollapsed||!selection.rangeCount)return null;const range=selection.getRangeAt(0),start=range.startContainer.nodeType===1?range.startContainer as Element:range.startContainer.parentElement;
      const end=range.endContainer.nodeType===1?range.endContainer as Element:range.endContainer.parentElement;if(!start||!end||start.closest(excluded)||end.closest(excluded))return null;
      const entry=owner(start);if(!entry||!entry.element.contains(end))return null;
      const quote=range.toString();if(!quote)return null;const text=reviewText(entry.element);
      // Exact surrounding context disambiguates repeated text; offsets orient recovery.
      const actual=reviewOffset(entry.element,range.startContainer,range.startOffset);if(actual===null)return null;
      if(text.slice(actual,actual+quote.length)!==quote)return null;
      return{kind:'text',target:fresh(entry),quote,start:actual,end:actual+quote.length,prefix:text.slice(Math.max(0,actual-80),actual),suffix:text.slice(actual+quote.length,actual+quote.length+80)};
    },
    item(element){
      const figure=figureOf(element);if(!figure)return null;const entry=owner(figure);if(!entry)return null;const adapter=visualAdapter(figure),id=adapter?.identify?.(element,figure);
      if(id){const found=adapter?.items?.(figure).find(item=>item.id===id);if(found)return{kind:'item',target:fresh(entry),itemId:id,label:found.label,text:found.text||'',...(found.values?{values:found.values}:{})};}
      const mark=element.closest<HTMLElement>('[data-av-inspect],[data-av-observation],[data-av-mermaid-item]');if(!mark||!figure.contains(mark))return null;
      const key=mark.getAttribute('data-av-inspect')||mark.getAttribute('data-av-observation')||mark.getAttribute('data-av-mermaid-item');
      const root=figureOrigin(figure).owner,detail=key?Array.from(root?.querySelectorAll<HTMLElement>('[data-av-object]')||[]).find(item=>item.getAttribute('data-av-object')===key):null;
      const text=detail?reviewText(detail):mark.getAttribute('aria-label')||mark.textContent||'';
      if(!key||!text.trim())return null;
      if(Array.from(figure.querySelectorAll('[data-av-inspect],[data-av-observation],[data-av-mermaid-item]')).filter(node=>[node.getAttribute('data-av-inspect'),node.getAttribute('data-av-observation'),node.getAttribute('data-av-mermaid-item')].includes(key)).length!==1)return null;return{kind:'item',target:fresh(entry),itemId:key,label:mark.getAttribute('aria-label')||mark.querySelector('title')?.textContent||text.slice(0,160),text};
    },
    resolve(value){
      if(value.target.reportId!==scope.id||value.target.revision!==revision)return{status:'changed',message:'This annotation belongs to another report revision; its original context is retained.'};
      if(value.target.ambiguous)return{status:'ambiguous',message:'Identical targets lacked authored identities. The original context is retained; supply stable IDs to distinguish them.'};
      const entry=entries.get(value.target.id);if(!entry)return{status:'missing',message:'The original target is unavailable in this report.'};
      if(entry.target.ambiguous)return{status:'ambiguous',message:'Multiple current targets share the original content identity.'};
      if(!entry.element.isConnected||entry.element.id!==value.target.id)return{status:'missing',message:'The original target is no longer present.'};
      if(Array.from(scope.ownerDocument.querySelectorAll('[id]')).filter(node=>node.id===value.target.id).length!==1)return{status:'ambiguous',message:'More than one target has this identity.'};
      if(signature(entry)!==value.target.fingerprint)return{status:'changed',element:entry.element,message:'The target content differs from the annotated version.'};
      let resolvedRange:Range|undefined;let resolvedElement=entry.element;
      if(value.kind==='text'){
        const text=reviewText(entry.element),hits:number[]=[];let at=-1;while((at=text.indexOf(value.quote,at+1))>=0){if(text.slice(Math.max(0,at-value.prefix.length),at)===value.prefix&&text.slice(at+value.quote.length,at+value.quote.length+value.suffix.length)===value.suffix)hits.push(at);}
        if(hits.length!==1)return{status:hits.length?'ambiguous':'changed',element:entry.element,message:hits.length?'The quoted text has more than one matching location.':'The original quotation no longer matches.'};
        if(scope.ownerDocument.createRange){
          const nodes=reviewNodes(entry.element);
          const start=nodes.find(node=>node.end>hits[0]),end=nodes.find(node=>node.end>=hits[0]+value.quote.length);
          if(start&&end){resolvedRange=scope.ownerDocument.createRange();resolvedRange.setStart(start.node,hits[0]-start.start);resolvedRange.setEnd(end.node,hits[0]+value.quote.length-end.start);resolvedElement=(start.node.parentElement||entry.element) as HTMLElement;if(resolvedRange.toString!==Object.prototype.toString&&resolvedRange.toString()!==value.quote)resolvedRange=undefined;}
        }
      }
      if(value.kind==='item'){
        const adapter=visualAdapter(entry.element),items=adapter?.items?.(entry.element);
        if(items){
          const matches=items.filter(item=>item.id===value.itemId);
          if(matches.length!==1)return{status:matches.length?'ambiguous':'missing',element:entry.element,message:'The item identity is missing or ambiguous.'};
          const item=matches[0],stable=(values:Record<string,string|number|null>|undefined)=>JSON.stringify(Object.entries(values||{}).sort(([a],[b])=>a.localeCompare(b)));
          if(item.label!==value.label||(item.text||'')!==value.text||stable(item.values)!==stable(value.values))return{status:'changed',element:entry.element,message:'The identified item’s wording or values changed.'};
        }else{
          const marks=Array.from(entry.element.querySelectorAll<HTMLElement>('[data-av-inspect],[data-av-observation],[data-av-mermaid-item]')).filter(item=>[item.getAttribute('data-av-inspect'),item.getAttribute('data-av-observation'),item.getAttribute('data-av-mermaid-item')].includes(value.itemId));
          if(marks.length!==1)return{status:marks.length?'ambiguous':'missing',element:entry.element,message:'The original diagram item is missing or ambiguous.'};
          const mark=marks[0],root=figureOrigin(entry.element).owner,detail=Array.from(root?.querySelectorAll<HTMLElement>('[data-av-object]')||[]).find(item=>item.getAttribute('data-av-object')===value.itemId);
          const text=detail?reviewText(detail):mark.getAttribute('aria-label')||mark.textContent||'';
          if(text!==value.text)return{status:'changed',element:entry.element,message:'The identified item’s wording or evidence changed.'};
          resolvedElement=mark;
        }
      }
      return{status:'resolved',element:resolvedElement,...(resolvedRange?{range:resolvedRange}:{}),message:'Attached to the original target.'};
    },
    cleanup(){for(const[element,id]of initialIds){if(id===null)element.removeAttribute('id');else element.id=id;}}
  };
}
