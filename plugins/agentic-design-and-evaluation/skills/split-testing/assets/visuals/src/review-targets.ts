import { exactJson } from './exact-json';
import { fingerprint } from './identity';
import { figureOf, figureTitle, visualAdapter, figureOrigin, figureContext } from './figures';
import { ReviewAnchor, ReviewTarget, ReviewItem } from "./review-types";
export type { ReviewAnchor, ReviewTarget, ReviewItem } from "./review-types";
export interface ResolvedAnchor { status: 'resolved' | 'missing' | 'changed' | 'ambiguous'; element?: HTMLElement; elements?: HTMLElement[]; range?: Range; message: string }
export interface TargetRegistry {
  targets: ReadonlyMap<string, { element: HTMLElement; target: ReviewTarget }>;
  anchor(element: HTMLElement): ReviewAnchor;
  selection(selection: Selection): ReviewAnchor | null;
  item(element: Element): ReviewAnchor | null;
  items(elements: readonly Element[]): ReviewAnchor | null;
  resolve(anchor: ReviewAnchor): ResolvedAnchor;
  /** A synchronous fresh snapshot; never reused across reader actions. */
  resolveAll?(anchors: readonly ReviewAnchor[]): ResolvedAnchor[];
  cleanup(): void;
}
const substitutes=new WeakMap<Node,Element>();
export function registerReviewPlaceholder(marker:Node,element:Element):()=>void{substitutes.set(marker,element);return()=>substitutes.delete(marker);}
// Presentation-only rearrangement must not change source order in anchors.
// Keep live nodes (not captured strings): missing content and real text edits
// remain observable. New authored nodes are included, never silently discarded.
const readingOrders = new WeakMap<Node, readonly Node[]>();
export function registerReviewOrder(parent: Element): () => void {
  const original = Array.from(parent.childNodes);
  readingOrders.set(parent, original);
  return () => { if (readingOrders.get(parent) === original) readingOrders.delete(parent); };
}
function reviewChildren(parent: Node): Node[] {
  const actual = Array.from(parent.childNodes), original = readingOrders.get(parent);
  if (!original) return actual;
  const available = new Set<Node>(actual), known = new Set(original);
  return [...original.filter(node => available.has(node)), ...actual.filter(node => !known.has(node))];
}
const excluded = '.av-frame-tools,.av-view-status,[data-av-controls],[data-av-review-ui],[data-av-notebook],script,style,.av-sr-only,.av-figure-actions';
function reviewNodes(element: Node): {node:Node;start:number;end:number}[] {
  const nodes:{node:Node;start:number;end:number}[]=[];let offset=0;
  const visit=(node:Node):void=>{const original=substitutes.get(node);if(original){visit(original);return;}if(node.nodeType===3){const start=offset;offset+=(node.textContent||'').length;nodes.push({node,start,end:offset});}else if((node.nodeType===1&&!(node as Element).matches(excluded+',.av-focus-dialog'))||node.nodeType===11)for(const child of reviewChildren(node))visit(child);};
  visit(element);return nodes;
}
export function reviewText(element: Element): string {return reviewNodes(element).map(item=>item.node.textContent||'').join('');}
/** Human-readable context; exact text offsets and target identities use reviewText. */
export function readableReviewText(element: Element): string {
  const parts:string[]=[];
  const visit=(node:Node):void=>{
    const original=substitutes.get(node);if(original){visit(original);return;}
    if(node.nodeType===3){parts.push(node.textContent||'');return;}
    if(node.nodeType!==1&&node.nodeType!==11)return;
    const current=node.nodeType===1?node as Element:null;
    if(current?.matches(excluded+',.av-focus-dialog'))return;
    if(current?.tagName.toLowerCase()==='br'){parts.push('\n');return;}
    const block=current?.matches('p,div,section,article,header,footer,h1,h2,h3,h4,h5,h6,blockquote,pre,li,dt,dd,tr');
    if(block)parts.push('\n');
    const badge=current?.matches('.av-badge');if(badge)parts.push(' ');
    if(current?.matches('td,th'))parts.push('\t');
    for(const child of reviewChildren(node))visit(child);
    if(badge)parts.push(' ');
    if(block)parts.push('\n');
  };
  visit(element);
  return parts.join('').replace(/[ \t]*\n[ \t]*/g,'\n').replace(/\n{3,}/g,'\n\n').trim();
}
function reviewOffset(root:Element,boundary:Node,at:number):number|null {
  let count=0,result:number|null=null;
  const visit=(node:Node):void=>{
    if(result!==null)return;const original=substitutes.get(node);if(original){visit(original);return;}
    if(node===boundary){result=count+(node.nodeType===3?at:Array.from(node.childNodes).slice(0,at).reduce((sum,child)=>sum+reviewNodes(child).reduce((n,part)=>n+part.end-part.start,0),0));return;}
    if(node.nodeType===3)count+=(node.textContent||'').length;
    else if((node.nodeType===1&&!(node as Element).matches(excluded+',.av-focus-dialog'))||node.nodeType===11)for(const child of reviewChildren(node))visit(child);
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
    for(const child of reviewChildren(node))visit(child);
  };visit(element);return exactJson(parts);
}
function grounds(element:HTMLElement):string{return (element.closest('[data-av-layout-input]')||(element.hasAttribute('data-av-figure')?figureOrigin(element).owner:null))?.getAttribute('data-av-layout-input')||contentIdentity(element);}
function sources(element:Element):{label:string;href:string}[]{const roots=[element,...(element.hasAttribute('data-av-figure')?figureContext(element as HTMLElement):[])],links=roots.flatMap(root=>Array.from(root.querySelectorAll('a[href]'))).filter(node=>!node.closest(excluded)).map(node=>({label:node.textContent||'',href:node.getAttribute('href')||''}));return [...new Map(links.map(link=>[exactJson(link),link])).values()];}
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
    const signature=fingerprint(exactJson([title,path,recipe]));
    if(!element.id){const base=(scope.id||'report')+'--target-'+signature.split(':')[1].slice(0,18);let id=base,index=1;while(entries.has(id)||scope.ownerDocument.getElementById(id))id=base+'-'+(++index);initialIds.set(element,null);element.id=id;}
    if(entries.has(element.id))throw new Error('Review targets need unique IDs.');
    entries.set(element.id,{element,target:{reportId:scope.id,revision,id:element.id,label:title,path,fingerprint:signature,excerpt:text,sources:sources(element)}});
  }
  } catch (error) { for (const element of initialIds.keys()) element.removeAttribute('id'); throw error; }
  const signatures=new Map<string,{element:HTMLElement;target:ReviewTarget}[]>();
  for(const entry of entries.values())if(initialIds.has(entry.element)){const group=signatures.get(entry.target.fingerprint)||[];group.push(entry);signatures.set(entry.target.fingerprint,group);}
  for(const group of signatures.values())if(group.length>1)for(const entry of group)entry.target.ambiguous=true;
  const signature=(entry:{element:HTMLElement;target:ReviewTarget}):string=>fingerprint(exactJson([label(entry.element),entry.target.path,grounds(entry.element)]));
  const owner=(element:Element):{element:HTMLElement;target:ReviewTarget}|undefined=>{
    for(let current:Element|null=element;current;current=current.parentElement){const entry=entries.get(current.id);if(entry?.element===current)return entry;}return undefined;
  };
  const fresh=(entry:{element:HTMLElement;target:ReviewTarget}):ReviewTarget=>({...entry.target,label:label(entry.element),fingerprint:signature(entry),excerpt:reviewText(entry.element),sources:sources(entry.element)});
  const anchor=(element:HTMLElement):ReviewAnchor=>{const entry=owner(element);if(!entry)throw new Error('This content has no review target.');return{kind:entry.element.hasAttribute('data-av-figure')?'figure':'section',target:fresh(entry)};};
  const markSelector = '[data-av-inspect],[data-av-observation],[data-av-mermaid-item]';
  const markKey = (node: Element): string | null => node.getAttribute('data-av-inspect') || node.getAttribute('data-av-observation') || node.getAttribute('data-av-mermaid-item');
  function evidenceIndex(figure: HTMLElement) {
    const marks = new Map<string, HTMLElement[]>(), details = new Map<string, HTMLElement[]>();
    for (const node of Array.from(figure.querySelectorAll<HTMLElement>(markSelector))) {
      const key = markKey(node); if (!key || node.closest('[data-av-review-ui]')) continue;
      const group = marks.get(key) || []; group.push(node); marks.set(key, group);
    }
    for (const node of Array.from(figureOrigin(figure).owner?.querySelectorAll<HTMLElement>('[data-av-object]') || [])) {
      const key = node.getAttribute('data-av-object')!; const group = details.get(key) || []; group.push(node); details.set(key, group);
    }
    const adapter = visualAdapter(figure), items = adapter?.items?.(figure);
    const supplied = new Map<string, typeof items>();
    for (const item of items || []) { const group = supplied.get(item.id) || []; supplied.set(item.id, [...group, item]); }
    return {marks, details, adapter, supplied, custom: !!items};
  }
  function captureItems(elements: readonly Element[]): ReviewAnchor | null {
    if (!elements.length) return null;
    const figure = figureOf(elements[0]); if (!figure || elements.some(node => figureOf(node) !== figure)) return null;
    const entry = owner(figure); if (!entry) return null;
    const index = evidenceIndex(figure), items: ReviewItem[] = [], seen = new Set<string>();
    for (const node of elements) {
      const customId = index.adapter?.identify?.(node, figure);
      let item: ReviewItem;
      if (customId) {
        const matches = index.supplied.get(customId);
        if (matches?.length !== 1) return null;
        const found = matches[0]; item = {itemId:customId,label:found.label,text:found.text || '',...(found.values ? {values:{...found.values}} : {})};
      } else {
        const mark = node.closest<HTMLElement>(markSelector), key = mark && markKey(mark);
        if (!mark || !figure.contains(mark) || !key || index.marks.get(key)?.length !== 1) return null;
        const details = index.details.get(key); if (details && details.length !== 1) return null;
        const text = details?.length ? reviewText(details[0]) : mark.getAttribute('aria-label') || mark.textContent || '';
        if (!text.trim()) return null;
        item = {itemId:key,label:mark.getAttribute('aria-label') || mark.querySelector('title')?.textContent || text.slice(0,160),text};
      }
      if (seen.has(item.itemId)) continue;
      seen.add(item.itemId); items.push(item);
    }
    const target = fresh(entry);
    return items.length === 1 ? {kind:'item',target,...items[0]} : {kind:'items',target,items};
  }
  function resolutionSnapshot() {
    const ids=new Map<string,number>();
    for(const node of Array.from(scope.ownerDocument.querySelectorAll('[id]')))ids.set(node.id,(ids.get(node.id)||0)+1);
    return {ids,signatures:new Map<HTMLElement,string>(),items:new Map<HTMLElement,ReturnType<typeof evidenceIndex>>()};
  }
  // Rendering a collection checks current identities once per figure/target.
  // No cache survives this synchronous batch: edits, removals and duplicate IDs
  // are revalidated before every later navigation or export.
  function resolve(value:ReviewAnchor,snapshot=resolutionSnapshot()):ResolvedAnchor {
      if(value.target.reportId!==scope.id||value.target.revision!==revision)return{status:'changed',message:'This annotation belongs to another report revision; its original context is retained.'};
      if(value.target.ambiguous)return{status:'ambiguous',message:'Identical targets lacked authored identities. The original context is retained; supply stable IDs to distinguish them.'};
      const entry=entries.get(value.target.id);if(!entry)return{status:'missing',message:'The original target is unavailable in this report.'};
      if(entry.target.ambiguous)return{status:'ambiguous',message:'Multiple current targets share the original content identity.'};
      if(!entry.element.isConnected||entry.element.id!==value.target.id)return{status:'missing',message:'The original target is no longer present.'};
      if(snapshot.ids.get(value.target.id)!==1)return{status:'ambiguous',message:'More than one target has this identity.'};
      if(!snapshot.signatures.has(entry.element))snapshot.signatures.set(entry.element,signature(entry));
      if(snapshot.signatures.get(entry.element)!==value.target.fingerprint)return{status:'changed',element:entry.element,message:'The target content differs from the annotated version.'};
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
      let resolvedElements: HTMLElement[] | undefined;
      if (value.kind === 'item' || value.kind === 'items') {
        let index = snapshot.items.get(entry.element); if(!index){index=evidenceIndex(entry.element);snapshot.items.set(entry.element,index);} const selected = value.kind === 'items' ? value.items : [value];
        resolvedElements = [];
        for (const wanted of selected) {
          if (index.custom) {
            const matches = index.supplied.get(wanted.itemId);
            if (matches?.length !== 1) return {status:matches?.length ? 'ambiguous' : 'missing', element:entry.element, message:`The selected item “${wanted.label}” is missing or ambiguous. The complete original selection is retained.`};
            const actual = matches[0];
            const sameValues = (a: Record<string,string|number|null> = {}, b: Record<string,string|number|null> = {}) => Object.keys(a).length === Object.keys(b).length && Object.keys(a).every(key => Object.prototype.hasOwnProperty.call(b,key) && Object.is(a[key], b[key]));
            if (actual.label !== wanted.label || (actual.text || '') !== wanted.text || !sameValues(actual.values,wanted.values)) return {status:'changed',element:entry.element,message:`The selected item “${wanted.label}” has different wording or values. The original selection is retained.`};
            const marks = index.marks.get(wanted.itemId); resolvedElements.push(marks?.length === 1 ? marks[0] : entry.element);
          } else {
            const marks = index.marks.get(wanted.itemId), details = index.details.get(wanted.itemId);
            if (marks?.length !== 1 || details && details.length !== 1) return {status:marks?.length || details?.length ? 'ambiguous' : 'missing', element:entry.element, message:`The selected item “${wanted.label}” is missing or ambiguous. The complete original selection is retained.`};
            const mark = marks[0], text = details?.length ? reviewText(details[0]) : mark.getAttribute('aria-label') || mark.textContent || '';
            if (text !== wanted.text) return {status:'changed',element:entry.element,message:`The selected item “${wanted.label}” has different wording or evidence. The original selection is retained.`};
            resolvedElements.push(mark);
          }
        }
        resolvedElement = resolvedElements[0] || entry.element;
      }
      return{status:'resolved',element:resolvedElement,...(resolvedElements?{elements:resolvedElements}:{}),...(resolvedRange?{range:resolvedRange}:{}),message:'Attached to the original target.'};
  }
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
    item: element => captureItems([element]),
    items: captureItems,
    resolve,
    resolveAll(values){if(!values.length)return[];const snapshot=resolutionSnapshot();return values.map(value=>resolve(value,snapshot));},
    cleanup(){for(const[element,id]of initialIds){if(id===null)element.removeAttribute('id');else element.id=id;}}
  };
}
