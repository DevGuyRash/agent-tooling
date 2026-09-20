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
  const groups=new Map<string,Element[]>();
  for(const node of nodes){
    if(node.tagName.toLowerCase()!=='g'||!node.id)continue;
    const text=node.textContent?.trim();if(!text||node.querySelector('g[id]'))continue;
    const key=node.getAttribute('data-id')?'id:'+node.getAttribute('data-id'):'text:'+fingerprint(text);
    const matches=groups.get(key)||[];matches.push(node);groups.set(key,matches);
  }
  for(const[key,matches]of groups)if(matches.length===1){matches[0].setAttribute('data-av-mermaid-item',key);matches[0].setAttribute('tabindex','0');matches[0].setAttribute('role','button');matches[0].setAttribute('aria-label',matches[0].textContent?.trim()||key);}
}
export function attachMermaid(root: HTMLElement, ready: (figure: HTMLElement) => void): DiagramController {
  const document = root.ownerDocument, view = document.defaultView;
  const diagrams = [...(root.matches('[data-av-mermaid]') ? [root] : []), ...Array.from(root.querySelectorAll<HTMLElement>('[data-av-mermaid]'))];
  const namespaces = new WeakMap<HTMLElement, string>(), keys = new WeakMap<HTMLElement, string>(), generations = new WeakMap<HTMLElement, number>();
  const original = diagrams.map(element => ({ element, output: element.querySelector<HTMLElement>('[data-av-mermaid-output]')!, children: Array.from(element.querySelector('[data-av-mermaid-output]')?.childNodes || []), status: element.querySelector<HTMLElement>('[data-av-mermaid-status]')!, text: element.querySelector('[data-av-mermaid-status]')?.textContent || '', state: element.getAttribute('data-av-mermaid-state'), hidden: element.querySelector('[data-av-mermaid-output]')?.getAttribute('hidden'), svg: element.querySelector<SVGElement>('[data-av-zoom-target]'), attributes: Array.from(element.querySelector<SVGElement>('[data-av-zoom-target]')?.attributes || []).map(attribute=>[attribute.name,attribute.value]), svgChildren: Array.from(element.querySelector('[data-av-zoom-target]')?.childNodes || []) }));
  let stopped = false, pending = Promise.resolve();
  async function refresh(): Promise<void> {
    const jobs = diagrams.map(element => {
      const figure = figureOf(element), output = element.querySelector<HTMLElement>('[data-av-mermaid-output]'), status = element.querySelector<HTMLElement>('[data-av-mermaid-status]');
      if (!figure || !output || !status || stopped) return Promise.resolve();
      const runtime = (view as unknown as { mermaid?: MermaidRuntime })?.mermaid || (globalThis as unknown as { mermaid?: MermaidRuntime }).mermaid;
      if (!runtime) { status.textContent = 'Mermaid is not embedded. Reassemble with --feature mermaid. The original source remains available.'; return Promise.resolve(); }
      const source = element.getAttribute('data-av-mermaid-source') || '';
      const css = view?.getComputedStyle?.(figure);
      const color = (name: string, fallback: string) => {
        const probe = document.createElement('span'); probe.style.setProperty('color', `var(${name})`); probe.setAttribute('aria-hidden', 'true'); probe.style.setProperty('display', 'none'); figure.appendChild(probe);
        const resolved = view?.getComputedStyle?.(probe).color; probe.remove(); return resolved && !resolved.includes('var(') ? resolved : fallback;
      };
      const palette = { background: color('--av-plot', '#ffffff'), primaryColor: color('--av-sheet', '#f4f5fa'), primaryTextColor: color('--av-ink', '#172032'), primaryBorderColor: color('--av-line-strong', '#66758a'), lineColor: color('--av-axis', '#66758a'), secondaryColor: color('--av-subtle', '#ecf1f5'), tertiaryColor: color('--av-inspector-surface', '#f4edf6'), fontFamily: css?.fontFamily || 'sans-serif' };
      const key = JSON.stringify([source, palette, element.getAttribute('data-av-mermaid-config')]);
      if (keys.get(element) === key) return Promise.resolve();
      const generation = (generations.get(element) || 0) + 1; generations.set(element, generation); element.setAttribute('data-av-mermaid-state','pending'); output.hidden=true; status.textContent = 'Rendering diagram…';
      const job = renderQueue.then(async () => {
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
        scopeDiagram(incoming,namespace);
        const plot = output.querySelector<HTMLElement>('[data-av-plot]'), live = plot?.querySelector<SVGElement>('[data-av-zoom-target]');
        if (!plot || !live) throw new Error('The diagram viewport is unavailable.');
        let bounds = (incoming.getAttribute('viewBox') || '').split(/[ ,]+/).map(Number);
        if (bounds.length !== 4 || !bounds.every(Number.isFinite) || bounds[2] <= 0 || bounds[3] <= 0) {
          const pixels=(value:string|null)=>value&&/^\d+(?:\.\d+)?(?:px)?$/.test(value.trim())?Number.parseFloat(value):0;
          const width=pixels(incoming.getAttribute('width'))||pixels(incoming.style.getPropertyValue('max-width'))||pixels(incoming.style.getPropertyValue('width'));
          let height=pixels(incoming.getAttribute('height'))||pixels(incoming.style.getPropertyValue('height'));
          let measured:{x:number;y:number;width:number;height:number}|null=null;
          if(!(width>0&&height>0)&&typeof (incoming as SVGGraphicsElement).getBBox==='function'){
            const measuring=document.createElement('div');measuring.setAttribute('data-av-mermaid-staging','');measuring.style.cssText='position:absolute;left:-100000px;top:0;visibility:hidden;pointer-events:none;';document.body.appendChild(measuring);measuring.appendChild(incoming);
            try{const box=(incoming as SVGGraphicsElement).getBBox();if([box.x,box.y,box.width,box.height].every(Number.isFinite)&&box.width>0&&box.height>0)measured=box;}finally{incoming.remove();measuring.remove();}
          }
          if(measured){const x=Math.min(0,measured.x-8),y=Math.min(0,measured.y-8);bounds=[x,y,Math.max(width,measured.x+measured.width+8)-x,Math.max(height,measured.y+measured.height+8)-y];}
          else {if(!(width>0&&height>0))throw new Error('The diagram has no measurable bounds. Its source remains available.');bounds=[0,0,width,height];}
          incoming.setAttribute('viewBox',bounds.join(' '));
        }
        // Preserve the viewport node and its handlers when a theme rerenders the diagram.
        for (const name of ['id', 'class', 'viewBox', 'role', 'aria-label', 'aria-describedby', 'aria-labelledby']) { const value = incoming.getAttribute(name); if (value !== null) live.setAttribute(name, value); else live.removeAttribute(name); }
        for(const name of ['background','color','font-family','font-size']){const value=incoming.style.getPropertyValue(name);if(value)live.style.setProperty(name,value);else live.style.removeProperty(name);}
        const selectedItem=live.querySelector('[data-av-mermaid-item][aria-pressed="true"]')?.getAttribute('data-av-mermaid-item');
        live.setAttribute('width', String(bounds[2])); live.setAttribute('height', String(bounds[3])); live.replaceChildren(...Array.from(incoming.childNodes));
        if(selectedItem)for(const node of Array.from(live.querySelectorAll('[data-av-mermaid-item]')))if(node.getAttribute('data-av-mermaid-item')===selectedItem){node.setAttribute('aria-pressed','true');node.classList.add('av-selected');}
        keys.set(element, key); element.setAttribute('data-av-mermaid-state','ready'); output.hidden=false; status.textContent = ''; ready(figure);
      }).catch(error => { if (!stopped && generations.get(element) === generation) { element.setAttribute('data-av-mermaid-state','error'); status.textContent = 'Diagram could not render: ' + (error instanceof Error ? error.message : String(error)) + ' Original source remains available below.'; } });
      renderQueue = job; return job;
    });
    await Promise.all(jobs);
  }
  return { refresh() { pending = refresh(); return pending; }, whenIdle: () => pending, cleanup() { stopped = true; for (const state of original) { state.output.replaceChildren(...state.children); state.status.textContent = state.text; if(state.state===null)state.element.removeAttribute('data-av-mermaid-state');else state.element.setAttribute('data-av-mermaid-state',state.state);if(state.hidden===null||state.hidden===undefined)state.output.removeAttribute('hidden');else state.output.setAttribute('hidden',state.hidden);if(state.svg){for(const attribute of Array.from(state.svg.attributes))state.svg.removeAttribute(attribute.name);for(const[name,value]of state.attributes)state.svg.setAttribute(name,value);state.svg.replaceChildren(...state.svgChildren);} } } };
}
