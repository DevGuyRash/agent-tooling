import { figureOf } from './figures';
import { fingerprint } from './identity';
interface MermaidRuntime {
  initialize(config: Record<string, unknown>): void;
  render(id: string, source: string, container?: Element): Promise<{ svg: string; bindFunctions?: (element: Element) => void }>;
  getRegisteredDiagramsMetadata(): { id: string }[];
}
let renderQueue: Promise<void> = Promise.resolve();
let sequence = 0;
export interface DiagramController { refresh(): Promise<void>; whenIdle(): Promise<void>; cleanup(): void }
/** Scope renderer-owned IDs without changing exact source or relying on a family whitelist. */
export function scopeDiagram(svg: SVGElement, prefix: string): void {
  const nodes = [svg, ...Array.from(svg.querySelectorAll<Element>('*'))];
  const groupsById = new Map<string, Element[]>(), assigned = new Map<Element, string>();
  for (const node of nodes) if (node.id) {
    const group = groupsById.get(node.id) || [];
    group.push(node); groupsById.set(node.id, group);
    assigned.set(node, prefix + '-' + assigned.size);
  }
  // Some renderer families repeat an ID on a node and its background shape,
  // or emit the same paint definition twice. Keep every element and its styles,
  // giving each a unique DOM ID. This is not an analytical item identity.
  const equivalent = (a: Node, b: Node): boolean => {
    if (a.nodeType !== b.nodeType || a.nodeName !== b.nodeName) return false;
    if (a.nodeType === 3) return a.textContent === b.textContent;
    if (a.nodeType === 1) {
      const first = a as Element, second = b as Element;
      if (first.attributes.length !== second.attributes.length || Array.from(first.attributes).some(attribute => second.getAttribute(attribute.name) !== attribute.value)) return false;
    }
    return a.childNodes.length === b.childNodes.length && Array.from(a.childNodes).every((child, index) => equivalent(child, b.childNodes[index]));
  };
  // Compute before rewriting IDs. A fragment with differing duplicate definitions
  // cannot be repaired by selecting a winner: retain the source and report it.
  const ambiguous = new Set([...groupsById].filter(([, group]) => group.length > 1 && group.some(node => !equivalent(group[0], node))).map(([id]) => id));
  const reference = (id: string): string => {
    if (ambiguous.has(id)) throw new Error('The diagram has an ambiguous reference to duplicate renderer IDs. Inspect its original source.');
    const group = groupsById.get(id); return group ? assigned.get(group[0])! : id;
  };
  const paint = (value: string): string => value.replace(/url\(["']?#([^"')]+)["']?\)/g, (_match, id: string) => 'url(#' + reference(id) + ')');
  for (const node of nodes) {
    if (node.id) node.id = assigned.get(node)!;
    for (const attribute of Array.from(node.attributes)) {
      if (attribute.name === 'id') continue;
      if (['aria-labelledby', 'aria-describedby'].includes(attribute.name)) node.setAttribute(attribute.name, attribute.value.split(/\s+/).map(reference).join(' '));
      else if (['href', 'xlink:href'].includes(attribute.name) && attribute.value.startsWith('#')) node.setAttribute(attribute.name, '#' + reference(attribute.value.slice(1)));
      else if (attribute.value.includes('url(')) node.setAttribute(attribute.name, paint(attribute.value));
    }
    if (node.tagName.toLowerCase() === 'style') node.textContent = (node.textContent || '').replace(/([^{}]+)\{([^{}]*)\}/g, (_rule, selector: string, declarations: string) => selector.replace(/#([a-zA-Z_][\w-]*)/g, (match, id: string) => {
      const group = groupsById.get(id);
      // :is keeps the original ID specificity while selecting every former match.
      return !group ? match : group.length === 1 ? '#' + assigned.get(group[0]) : ':is(' + group.map(node => '#' + assigned.get(node)).join(',') + ')';
    }) + '{' + paint(declarations) + '}');
  }
  const groups = new Map<string, Element[]>();
  const candidates = nodes.filter(node => {
    if (node.closest('defs,marker,clipPath,mask,pattern,symbol')) return false;
    if (!node.textContent?.trim()) return false;
    if (node.tagName.toLowerCase() === 'text') return true;
    if (node.tagName.toLowerCase() !== 'g') return false;
    return node.hasAttribute('data-id') || node.classList.contains('node') || !!assigned.get(node) && !node.querySelector('g[id],g.node,g[data-id]');
  });
  // Prefer a complete node to an individually selectable label within it. Other
  // families can expose text items without a diagram-family-specific adapter.
  const candidateSet = new Set(candidates);
  const outer = candidates.filter(node => { for (let parent = node.parentElement; parent; parent = parent.parentElement) if (candidateSet.has(parent)) return false; return true; });
  for (const node of outer) {
    const text = node.textContent!.trim();
    const key = node.getAttribute('data-id') ? 'id:' + node.getAttribute('data-id') : 'text:' + fingerprint(text);
    const matches = groups.get(key) || []; matches.push(node); groups.set(key, matches);
  }
  for (const [key, matches] of groups) if (matches.length === 1) {
    const node = matches[0]; node.setAttribute('data-av-mermaid-item', key);
    node.setAttribute('tabindex', '0'); node.setAttribute('role', 'button');
    node.setAttribute('aria-label', node.textContent?.trim() || key);
  }
}
/** Measure in diagram coordinates at intrinsic size. A valid vendor viewBox is
 * retained, but cannot clip actual glyphs, strokes or overflowing HTML labels.
 * Browser text metrics refine geometry; no source wording or value is changed.
 */
export function diagramBounds(svg: SVGElement, document: Document): number[] {
  let bounds = (svg.getAttribute('viewBox') || '').split(/[ ,]+/).map(Number);
  const pixels = (value: string | null) => value && /^\d+(?:\.\d+)?(?:px)?$/.test(value.trim()) ? parseFloat(value) : 0;
  if (bounds.length !== 4 || !bounds.every(Number.isFinite) || bounds[2] <= 0 || bounds[3] <= 0) {
    const width = pixels(svg.getAttribute('width')) || pixels(svg.style.getPropertyValue('max-width'));
    const height = pixels(svg.getAttribute('height'));
    bounds = [0, 0, width, height];
  }
  const staging = document.createElement('div'); staging.setAttribute('data-av-mermaid-staging', '');
  staging.setAttribute('aria-hidden', 'true');
  staging.style.cssText = 'position:absolute;left:-100000px;top:0;visibility:hidden;pointer-events:none;';
  document.body.appendChild(staging); staging.appendChild(svg);
  const originalStyle = svg.getAttribute('style');
  try {
    if (bounds[2] > 0 && bounds[3] > 0) {
      svg.style.setProperty('width', bounds[2] + 'px'); svg.style.setProperty('height', bounds[3] + 'px');
      svg.style.setProperty('max-width', 'none'); svg.style.setProperty('display', 'block');
    }
    const graphics = svg as SVGGraphicsElement;
    const union=(x:number,y:number,width:number,height:number,padding=8):void=>{
      if(![x,y,width,height].every(Number.isFinite)||width<0||height<0)return;
      const left=Math.min(bounds[0],x-padding),top=Math.min(bounds[1],y-padding);
      bounds=[left,top,Math.max(bounds[0]+bounds[2],x+width+padding)-left,Math.max(bounds[1]+bounds[3],y+height+padding)-top];
    };
    if (typeof graphics.getBBox === 'function') {
      // Options are ignored by older engines, where the padded geometric box
      // remains the fallback. Never shrink a valid vendor-provided viewBox.
      const box=(graphics.getBBox as (options?:unknown)=>DOMRect)({fill:true,stroke:true,markers:true,clipped:false});
      if(box.width>0&&box.height>0)union(box.x,box.y,box.width,box.height);
    }
    // SVG getBBox does not include overflowing HTML glyphs inside foreignObject.
    // Read their native text ranges at intrinsic size, then transform viewport
    // rectangles back to this SVG's coordinates (not the reader's zoom/pan).
    const matrix=graphics.getScreenCTM?.();
    if(matrix&&document.createRange){
      const inverse=matrix.inverse();
      const transform=(x:number,y:number)=>({x:inverse.a*x+inverse.c*y+inverse.e,y:inverse.b*x+inverse.d*y+inverse.f});
      const include=(rect:DOMRect):void=>{
        if(!rect.width&&!rect.height)return;
        const corners=[transform(rect.left,rect.top),transform(rect.right,rect.top),transform(rect.left,rect.bottom),transform(rect.right,rect.bottom)];
        const xs=corners.map(p=>p.x),ys=corners.map(p=>p.y),x=Math.min(...xs),y=Math.min(...ys);union(x,y,Math.max(...xs)-x,Math.max(...ys)-y);
      };
      for(const object of Array.from(svg.querySelectorAll('foreignObject'))){
        const visit=(node:Node):void=>{
          if(node.nodeType===3&&node.textContent?.trim()){
            const range=document.createRange();range.selectNodeContents(node);
            for(const rect of Array.from(range.getClientRects()))include(rect);
          }else if(node.nodeType===1){
            if(['script','style'].includes((node as Element).tagName.toLowerCase()))return;
            for(const child of Array.from(node.childNodes))visit(child);
          }
        };visit(object);
      }
    }
  } finally {
    if (originalStyle === null) svg.removeAttribute('style'); else svg.setAttribute('style', originalStyle);
    svg.remove(); staging.remove();
  }
  if (!bounds.every(Number.isFinite) || bounds[2] <= 0 || bounds[3] <= 0) throw new Error('The diagram has no measurable bounds. Its source remains available.');
  svg.setAttribute('viewBox', bounds.join(' ')); return bounds;
}

export function attachMermaid(root: HTMLElement, ready: (figure: HTMLElement) => void): DiagramController {
  const document = root.ownerDocument, view = document.defaultView;
  const diagrams = [...(root.matches('[data-av-mermaid]') ? [root] : []), ...Array.from(root.querySelectorAll<HTMLElement>('[data-av-mermaid]'))];
  const namespaces = new WeakMap<HTMLElement, string>(), keys = new WeakMap<HTMLElement, string>(), generations = new WeakMap<HTMLElement, number>();
  const original = diagrams.map(element => ({ element, output: element.querySelector<HTMLElement>('[data-av-mermaid-output]')!, children: Array.from(element.querySelector('[data-av-mermaid-output]')?.childNodes || []), status: element.querySelector<HTMLElement>('[data-av-mermaid-status]')!, text: element.querySelector('[data-av-mermaid-status]')?.textContent || '', state: element.getAttribute('data-av-mermaid-state'), busy: element.getAttribute('aria-busy'), hidden: element.querySelector('[data-av-mermaid-output]')?.getAttribute('hidden'), svg: element.querySelector<SVGElement>('[data-av-zoom-target]'), attributes: Array.from(element.querySelector<SVGElement>('[data-av-zoom-target]')?.attributes || []).map(attribute=>[attribute.name,attribute.value]), svgChildren: Array.from(element.querySelector('[data-av-zoom-target]')?.childNodes || []) }));
  let stopped = false;
  const jobsInFlight = new Set<Promise<void>>(), requested = new Map<HTMLElement, {key: string; job: Promise<void>}>(), semanticKeys = new Map<HTMLElement, string>();
  async function refresh(): Promise<void> {
    const jobs = diagrams.map(element => {
      const figure = figureOf(element), output = element.querySelector<HTMLElement>('[data-av-mermaid-output]'), status = element.querySelector<HTMLElement>('[data-av-mermaid-status]');
      if (!figure || !output || !status || stopped) return Promise.resolve();
      const runtime = (view as unknown as { mermaid?: MermaidRuntime })?.mermaid || (globalThis as unknown as { mermaid?: MermaidRuntime }).mermaid;
      if (!runtime) { element.setAttribute('data-av-mermaid-state','error'); element.removeAttribute('aria-busy'); status.textContent = 'Mermaid is not embedded. Reassemble with --feature mermaid. The original source remains available.'; return Promise.resolve(); }
      const source = element.getAttribute('data-av-mermaid-source') || '';
      const css = view?.getComputedStyle?.(figure);
      const roles={background:['--av-plot','#ffffff'],primaryColor:['--av-sheet','#f4f5fa'],primaryTextColor:['--av-ink','#172032'],primaryBorderColor:['--av-line-strong','#66758a'],lineColor:['--av-axis','#66758a'],secondaryColor:['--av-subtle','#ecf1f5'],tertiaryColor:['--av-inspector-surface','#f4edf6']};
      const probes=document.createElement('span');probes.setAttribute('data-av-review-ui','');probes.hidden=true;
      const colorNodes=Object.entries(roles).map(([name,[token,fallback]])=>{const node=document.createElement('span');node.style.setProperty('color',`var(${token})`);probes.appendChild(node);return {name,node,fallback};});
      figure.appendChild(probes);
      const palette:Record<string,string>={fontFamily:css?.fontFamily||'sans-serif'};
      try{for(const {name,node,fallback}of colorNodes){const resolved=view?.getComputedStyle?.(node).color;palette[name]=resolved&&!resolved.includes('var(')?resolved:fallback;}}finally{probes.remove();}
      const key = JSON.stringify([source, palette, element.getAttribute('data-av-mermaid-config')]);
      if (requested.get(element)?.key === key) return requested.get(element)!.job;
      if (keys.get(element) === key) {
        generations.set(element, (generations.get(element) || 0) + 1);
        requested.delete(element); element.setAttribute('data-av-mermaid-state', 'ready');
        element.removeAttribute('aria-busy'); output.hidden = false; status.textContent = ''; return Promise.resolve();
      }
      const semanticKey = JSON.stringify([source, element.getAttribute('data-av-mermaid-config')]);
      const generation = (generations.get(element) || 0) + 1; generations.set(element, generation);
      element.setAttribute('data-av-mermaid-state','pending'); element.setAttribute('aria-busy','true');
      const retainScene = semanticKeys.get(element) === semanticKey;
      output.hidden = !retainScene; status.textContent = retainScene ? '' : 'Preparing diagram…';
      const job = renderQueue.then(async () => {
        if (stopped || generations.get(element) !== generation) return;
        if (document.fonts?.ready) await document.fonts.ready;
        if (stopped || generations.get(element) !== generation) return;
        const supplied = JSON.parse(element.getAttribute('data-av-mermaid-config') || '{}');
        if (!supplied || Array.isArray(supplied) || typeof supplied !== 'object') throw new Error('Mermaid configuration must be an object.');
        runtime.initialize({ ...supplied, theme: supplied.theme || 'base', themeVariables: { ...palette, ...supplied.themeVariables }, startOnLoad: false, securityLevel: 'strict', suppressErrorRendering: true, deterministicIds: true, deterministicIDSeed: fingerprint(source + (figure.id || 'diagram')), secure: ['securityLevel', 'startOnLoad', 'secure'] });
        let id = 'av-mermaid-' + (++sequence); while(document.getElementById(id)||document.getElementById('d'+id))id='av-mermaid-'+(++sequence);
        const staging=document.createElement('div');staging.setAttribute('data-av-mermaid-staging','');staging.setAttribute('aria-hidden','true');staging.style.cssText='position:absolute;left:-100000px;top:0;visibility:hidden;pointer-events:none;';document.body.appendChild(staging);
        let result: {svg:string}; try { result = await runtime.render(id, source, staging); } finally { staging.remove(); }
        if (stopped || generations.get(element) !== generation) return;
        // Strict Mermaid output is the renderer's SVG. No evidence is evaluated as code.
        const template = document.createElement('template'); template.innerHTML = result.svg;
        const incoming = template.content.querySelector<SVGElement>('svg');
        if (!incoming || incoming.querySelector('script')) throw new Error('Mermaid did not return a safe SVG scene.');
        let namespace=namespaces.get(element);if(!namespace){do{namespace='av-diagram-'+(++sequence);}while(document.getElementById(namespace+'-0'));namespaces.set(element,namespace);}
        scopeDiagram(incoming,namespace); incoming.setAttribute('data-av-mermaid-scene', '');
        const plot = output.querySelector<HTMLElement>('[data-av-plot]'), live = plot?.querySelector<SVGElement>('[data-av-zoom-target]');
        if (!plot || !live) throw new Error('The diagram viewport is unavailable.');
        const bounds = diagramBounds(incoming, document);
        // Preserve the viewport node and its handlers when a theme rerenders the diagram.
        for (const name of ['id', 'class', 'viewBox', 'role', 'aria-label', 'aria-describedby', 'aria-labelledby', 'data-av-mermaid-scene']) { const value = incoming.getAttribute(name); if (value !== null) live.setAttribute(name, value); else live.removeAttribute(name); }
        for(const name of ['background','color','font-family','font-size']){const value=incoming.style.getPropertyValue(name);if(value)live.style.setProperty(name,value);else live.style.removeProperty(name);}
        const selectedItems = new Set(Array.from(live.querySelectorAll('[data-av-mermaid-item][data-av-item-selected],[data-av-mermaid-item][aria-pressed="true"]')).map(node => node.getAttribute('data-av-mermaid-item')));
        const focusedItem = document.activeElement?.getAttribute('data-av-mermaid-item');
        live.setAttribute('width', String(bounds[2])); live.setAttribute('height', String(bounds[3])); live.replaceChildren(...Array.from(incoming.childNodes));
        for (const node of Array.from(live.querySelectorAll<SVGElement>('[data-av-mermaid-item]'))) { if(selectedItems.has(node.getAttribute('data-av-mermaid-item'))){node.setAttribute('data-av-item-selected','');node.setAttribute('aria-pressed','true');} if (focusedItem && node.getAttribute('data-av-mermaid-item') === focusedItem) node.focus({preventScroll:true}); }
        keys.set(element, key); semanticKeys.set(element, semanticKey); element.removeAttribute('aria-busy'); element.setAttribute('data-av-mermaid-state','ready'); output.hidden=false; status.textContent = ''; ready(figure);
      }).catch(error => { if (!stopped && generations.get(element) === generation) { element.removeAttribute('aria-busy'); element.setAttribute('data-av-mermaid-state','error'); status.textContent = 'Diagram could not render: ' + (error instanceof Error ? error.message : String(error)) + ' Original source remains available below.'; } });
      renderQueue = job; requested.set(element, {key, job}); jobsInFlight.add(job);
      void job.then(() => { jobsInFlight.delete(job); if (requested.get(element)?.job === job) requested.delete(element); });
      return job;
    });
    await Promise.all(jobs);
  }
  return { refresh, async whenIdle() { while (jobsInFlight.size) await Promise.all([...jobsInFlight]); }, cleanup() { stopped = true; requested.clear(); semanticKeys.clear(); for (const state of original) { state.output.replaceChildren(...state.children); state.status.textContent = state.text; if(state.busy===null)state.element.removeAttribute('aria-busy');else state.element.setAttribute('aria-busy',state.busy); if(state.state===null)state.element.removeAttribute('data-av-mermaid-state');else state.element.setAttribute('data-av-mermaid-state',state.state);if(state.hidden===null||state.hidden===undefined)state.output.removeAttribute('hidden');else state.output.setAttribute('hidden',state.hidden);if(state.svg){for(const attribute of Array.from(state.svg.attributes))state.svg.removeAttribute(attribute.name);for(const[name,value]of state.attributes)state.svg.setAttribute(name,value);state.svg.replaceChildren(...state.svgChildren);} } } };
}
