import { figureOf, figureTitle } from './figures';
import { fingerprint } from './identity';
import { repairElkLayout, ElkPostprocessor } from './elk-layout';
import { routeArchitectureConnection, ArchitectureRouter } from './architecture-layout';
interface MermaidRuntime {
  initialize(config: Record<string, unknown>): void;
  parse?(source: string): Promise<{ config?: Record<string, unknown> & { themeVariables?: Record<string, unknown> } } | false>;
  render(id: string, source: string, container?: Element): Promise<{ svg: string; bindFunctions?: (element: Element) => void }>;
  getRegisteredDiagramsMetadata(): { id: string }[];
  setElkLayoutPostprocessor?(postprocessor: ElkPostprocessor | null): ElkPostprocessor | null;
  setArchitectureRouter?(router: ArchitectureRouter | null): ArchitectureRouter | null;
}
let renderQueue: Promise<void> = Promise.resolve();
let sequence = 0;
const MIN_LAYOUT_WIDTH = 900;
export interface DiagramController { refresh(): Promise<void>; whenIdle(): Promise<void>; cleanup(): void }
type DiagramStyles = Readonly<Record<string, string>>;
/** Offscreen scenes have no report ancestor. Retain effective custom properties
 * and inherited typography so theme-dependent paint participates in measurement.
 * Do not copy display, visibility or layout from a potentially collapsed figure.
 */
function diagramStyles(computed?: CSSStyleDeclaration): DiagramStyles {
  const names = new Set(['font', 'color', 'color-scheme', 'letter-spacing', 'word-spacing', 'line-height', 'text-transform', 'direction', 'writing-mode']);
  for (const name of Array.from(computed || [])) if (name.startsWith('--') || name.startsWith('font-')) names.add(name);
  return Object.fromEntries([...names].sort().map(name => [name, computed?.getPropertyValue(name).trim() || '']).filter(([, value]) => value));
}
function diagramStaging(document: Document, styles: DiagramStyles, width?: number): HTMLElement {
  const staging = document.createElement('div');
  staging.setAttribute('data-av-mermaid-staging', ''); staging.setAttribute('aria-hidden', 'true');
  // Opacity suppresses paint without changing visibility or native geometry.
  staging.style.cssText = 'position:absolute;left:-100000px;top:0;opacity:0;pointer-events:none;max-width:none;';
  for (const [name, value] of Object.entries(styles)) staging.style.setProperty(name, value);
  if (width !== undefined) staging.style.setProperty('width', width + 'px');
  document.body.appendChild(staging);
  return staging;
}
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
/** Some renderer notes span actor centers even when their text is wider. Grow
 * only that note's own horizontal background; never reflow its text, move its
 * participants/connections, or change source and selection identity.
 */
function fitNoteBackgrounds(svg: SVGElement, document: Document): SVGGraphicsElement[] {
  const changed: SVGGraphicsElement[] = [];
  for (const group of Array.from(svg.querySelectorAll('g[data-et="note"]'))) {
    const children = Array.from(group.children), backgrounds = children.filter(child => child.matches('rect.note'));
    const labels = children.filter(child => child.matches('text.noteText')) as SVGGraphicsElement[];
    if (backgrounds.length !== 1 || !labels.length || children.some(child => !child.matches('rect.note,text.noteText,title,desc'))) continue;
    const background = backgrounds[0] as SVGGraphicsElement;
    // Boxes share their parent's coordinates only without individual transforms.
    // Unknown/custom geometry keeps the renderer's result rather than being guessed.
    const nodes = [background, ...labels];
    if (nodes.some(node => node.hasAttribute('transform') || (document.defaultView?.getComputedStyle(node).transform || 'none') !== 'none')) continue;
    if (['x','width'].some(name => background.style.getPropertyValue(name))) continue;
    try {
      const box = background.getBBox(), text = labels.map(label => label.getBBox());
      if ([box, ...text].some(value => ![value.x,value.y,value.width,value.height].every(Number.isFinite) || value.width <= 0 || value.height <= 0)) continue;
      const left = Math.min(...text.map(value => value.x)), right = Math.max(...text.map(value => value.x + value.width));
      if (left >= box.x - 0.5 && right <= box.x + box.width + 0.5) continue;
      const height = Math.max(...text.map(value => value.y + value.height)) - Math.min(...text.map(value => value.y));
      // Reuse the note's measured vertical breathing room, bounded so unusually
      // tall authored notes do not acquire a correspondingly enormous side margin.
      const padding = Math.max(4, Math.min(12, (box.height - height) / 2));
      const x = Math.min(box.x, left - padding), end = Math.max(box.x + box.width, right + padding);
      background.setAttribute('x', String(x)); background.setAttribute('width', String(end - x));
      changed.push(background);
    } catch { /* A renderer without native box measurement keeps its own geometry. */ }
  }
  return changed;
}

interface PaintedBounds { box: {x:number;y:number;width:number;height:number} | null; complete: boolean }
/** Measure actually painted leaf geometry in root SVG coordinates. Renderer
 * viewBoxes are useful as a locality hint, but several Mermaid families either
 * leave large empty margins or place a visible primitive just beyond an edge.
 * Far generated helpers (for example Gantt's off-range "today" line) are not
 * part of the visible scene and must not make the canvas hundreds of times wider.
 */
function paintedBounds(svg: SVGElement, document: Document, viewport: number[]): PaintedBounds {
  const matrix=(svg as SVGGraphicsElement).getScreenCTM?.(),view=document.defaultView;
  if(!matrix)return {box:null,complete:false};
  let inverse:DOMMatrix;
  try{inverse=matrix.inverse();}catch{return {box:null,complete:false};}
  const [vx,vy,vw,vh]=viewport,near={left:vx-vw,top:vy-vh,right:vx+vw*2,bottom:vy+vh*2};
  const intersect=(a:{x:number;y:number;width:number;height:number},b:{x:number;y:number;width:number;height:number})=>{
    const x=Math.max(a.x,b.x),y=Math.max(a.y,b.y),right=Math.min(a.x+a.width,b.x+b.width),bottom=Math.min(a.y+a.height,b.y+b.height);
    return right>=x&&bottom>=y?{x,y,width:right-x,height:bottom-y}:null;
  };
  const viewportBox={x:vx,y:vy,width:vw,height:vh};
  const boxes:{x:number;y:number;width:number;height:number}[]=[];
  let complete=true;
  const styleValue=(style:CSSStyleDeclaration|undefined,property:string):string=>style?.getPropertyValue?.(property)?.trim()||'';
  const opacityVisible=(value:string):boolean=>{const parsed=Number.parseFloat(value);return !Number.isFinite(parsed)||parsed>0;};
  const active=(value:string|null|undefined):boolean=>!!value&&value.trim()!==''&&value.trim()!=='none';
  const maxScale=(value:DOMMatrix):number=>{
    const aa=value.a*value.a+value.b*value.b,bb=value.c*value.c+value.d*value.d,cross=value.a*value.c+value.b*value.d;
    return Math.sqrt(Math.max(0,(aa+bb+Math.sqrt(Math.max(0,(aa-bb)*(aa-bb)+4*cross*cross)))/2));
  };
  const mapRect=(rect:{left:number;top:number;right:number;bottom:number},padding=0)=>{
    const points=[[rect.left-padding,rect.top-padding],[rect.right+padding,rect.top-padding],[rect.left-padding,rect.bottom+padding],[rect.right+padding,rect.bottom+padding]].map(([x,y])=>({x:inverse.a*x+inverse.c*y+inverse.e,y:inverse.b*x+inverse.d*y+inverse.f}));
    const xs=points.map(point=>point.x),ys=points.map(point=>point.y);
    return {x:Math.min(...xs),y:Math.min(...ys),width:Math.max(...xs)-Math.min(...xs),height:Math.max(...ys)-Math.min(...ys)};
  };
  const markerId=(value:string):string|null=>value.match(/#([^"')]+)["']?\)/)?.[1]||null;
  const markerPadding=(element:SVGGraphicsElement,style:CSSStyleDeclaration|undefined,strokeWidth:number):number|null=>{
    const references=[styleValue(style,'marker-start')||element.getAttribute('marker-start')||'',styleValue(style,'marker-mid')||element.getAttribute('marker-mid')||'',styleValue(style,'marker-end')||element.getAttribute('marker-end')||''].filter(active);
    if(!references.length)return 0;
    const screen=element.getScreenCTM?.();if(!screen)return null;
    const scale=maxScale(screen);if(!Number.isFinite(scale)||scale<=0)return null;
    let radius=0;
    for(const reference of references){
      const id=markerId(reference);if(!id)return null;
      const marker=Array.from(svg.querySelectorAll<SVGMarkerElement>('marker')).find(node=>node.id===id);if(!marker)return null;
      const markerStyle=view?.getComputedStyle?.(marker);
      if((styleValue(markerStyle,'overflow')||marker.getAttribute('overflow')||'hidden')!=='hidden')return null;
      // A marker viewBox can scale or translate its reference point independently
      // of the viewport. Keep the renderer viewport instead of guessing that math.
      if(marker.hasAttribute('viewBox'))return null;
      const read=(name:string,fallback:string):number=>Number.parseFloat(marker.getAttribute(name)||fallback);
      const width=read('markerWidth','3'),height=read('markerHeight','3'),refX=read('refX','0'),refY=read('refY','0');
      if(![width,height,refX,refY].every(Number.isFinite)||width<=0||height<=0)return null;
      const units=(marker.getAttribute('markerUnits')||'strokeWidth').trim();
      if(units!=='userSpaceOnUse'&&units!=='strokeWidth')return null;
      const unitScale=units==='strokeWidth'?strokeWidth:1;
      if(!Number.isFinite(unitScale)||unitScale<0)return null;
      const dx=Math.max(Math.abs(refX),Math.abs(width-refX)),dy=Math.max(Math.abs(refY),Math.abs(height-refY));
      radius=Math.max(radius,Math.hypot(dx,dy)*unitScale*scale);
    }
    return radius;
  };
  const selector='path,rect,circle,ellipse,line,polyline,polygon,text,foreignObject,use,image';
  for(const element of Array.from(svg.querySelectorAll<SVGGraphicsElement>(selector))){
    if(element.closest('defs,clipPath,mask,marker,pattern,symbol'))continue;
    let visible=true,clipped=false;
    for(let node:Element|null=element;node;node=node.parentElement){
      const style=view?.getComputedStyle?.(node);
      const display=styleValue(style,'display')||node.getAttribute('display')||'',visibility=styleValue(style,'visibility')||node.getAttribute('visibility')||'';
      const opacity=styleValue(style,'opacity')||node.getAttribute('opacity')||'';
      if(display==='none'||visibility==='hidden'||visibility==='collapse'||!opacityVisible(opacity)){visible=false;break;}
      const clip=styleValue(style,'clip-path')||node.getAttribute('clip-path');
      const mask=styleValue(style,'mask')||styleValue(style,'mask-image')||node.getAttribute('mask');
      if(active(clip)||active(mask)){clipped=true;complete=false;}
      const effect=styleValue(style,'filter')||node.getAttribute('filter');
      if(active(effect))complete=false;
      if(node===svg)break;
    }
    if(!visible)continue;
    const style=view?.getComputedStyle?.(element),tag=element.tagName.toLowerCase();
    const fillValue=styleValue(style,'fill')||element.getAttribute('fill')||'black',fillOpacity=styleValue(style,'fill-opacity')||element.getAttribute('fill-opacity')||'1';
    const strokeValue=styleValue(style,'stroke')||element.getAttribute('stroke')||'none',strokeOpacity=styleValue(style,'stroke-opacity')||element.getAttribute('stroke-opacity')||'1';
    const fill=fillValue!=='none'&&opacityVisible(fillOpacity),strokeWidth=Number.parseFloat(styleValue(style,'stroke-width')||element.getAttribute('stroke-width')||'1');
    const stroke=strokeValue!=='none'&&opacityVisible(strokeOpacity)&&Number.isFinite(strokeWidth)&&strokeWidth>0;
    const marker=[styleValue(style,'marker-start')||element.getAttribute('marker-start'),styleValue(style,'marker-mid')||element.getAttribute('marker-mid'),styleValue(style,'marker-end')||element.getAttribute('marker-end')].some(active);
    if(!['text','foreignobject','image','use'].includes(tag)&&!fill&&!stroke&&!marker)continue;
    if(tag==='foreignobject'||tag==='use'||active(styleValue(style,'text-shadow'))||active(styleValue(style,'box-shadow')))complete=false;
    let rect:DOMRect;
    try{rect=element.getBoundingClientRect();}catch{complete=false;continue;}
    if(![rect.left,rect.top,rect.right,rect.bottom].every(Number.isFinite)){complete=false;continue;}
    if(!rect.width&&!rect.height&&!marker)continue;
    let padding=0;
    if(stroke){
      const screen=element.getScreenCTM?.();
      if(!screen)complete=false;
      else{
        const vector=styleValue(style,'vector-effect')||element.getAttribute('vector-effect')||'',scale=vector==='non-scaling-stroke'?1:maxScale(screen);
        const join=(styleValue(style,'stroke-linejoin')||element.getAttribute('stroke-linejoin')||'miter').toLowerCase();
        const miter=join==='miter'?Number.parseFloat(styleValue(style,'stroke-miterlimit')||element.getAttribute('stroke-miterlimit')||'4'):1;
        if(!Number.isFinite(scale)||scale<=0||!Number.isFinite(miter)||miter<=0)complete=false;
        else padding=Math.max(padding,strokeWidth*scale*Math.max(1,miter)/2);
      }
    }
    if(marker){
      const markerExtent=markerPadding(element,style,stroke?strokeWidth:1);
      if(markerExtent===null)complete=false;else padding=Math.max(padding,markerExtent);
    }
    let box=mapRect(rect,padding);
    // A clipped leaf cannot legitimately enlarge the root canvas. Its exact
    // inner clip may be smaller, but clamping to the authored root viewport is
    // conservative and leaves the renderer viewport intact because complete=false.
    if(clipped){const bounded=intersect(box,viewportBox);if(!bounded)continue;box=bounded;}
    const far=box.x+box.width<near.left||box.x>near.right||box.y+box.height<near.top||box.y>near.bottom;
    // Mermaid Gantt emits a vertical current-date guide even when today's date
    // is hundreds of chart widths outside an authored historical range. This
    // generated guide is not part of that historical scene. Do not generalize
    // this to arbitrary far geometry: authored off-viewport evidence must remain.
    const generatedDateGuide=far&&tag==='line'&&!element.id&&element.classList.contains('today')
      &&element.hasAttribute('x1')&&element.hasAttribute('x2')&&element.getAttribute('x1')===element.getAttribute('x2');
    if(generatedDateGuide)continue;
    boxes.push(box);
  }
  if(!boxes.length)return {box:null,complete};
  const left=Math.min(...boxes.map(box=>box.x)),top=Math.min(...boxes.map(box=>box.y)),right=Math.max(...boxes.map(box=>box.x+box.width)),bottom=Math.max(...boxes.map(box=>box.y+box.height));
  return {box:{x:left,y:top,width:right-left,height:bottom-top},complete};
}

/** Measure in diagram coordinates at intrinsic size. A valid vendor viewBox is
 * retained, but cannot clip actual glyphs, strokes or overflowing HTML labels.
 * Browser text metrics refine geometry; no source wording or value is changed.
 */
export function diagramBounds(svg: SVGElement, document: Document, inheritedStyles: DiagramStyles = {}): number[] {
  let bounds = (svg.getAttribute('viewBox') || '').split(/[ ,]+/).map(Number);
  const vendorViewport = bounds.length === 4 && bounds.every(Number.isFinite) && bounds[2] > 0 && bounds[3] > 0;
  const pixels = (value: string | null) => value && /^\d+(?:\.\d+)?(?:px)?$/.test(value.trim()) ? parseFloat(value) : 0;
  if (!vendorViewport) {
    const width = pixels(svg.getAttribute('width')) || pixels(svg.style.getPropertyValue('max-width'));
    const height = pixels(svg.getAttribute('height'));
    bounds = [0, 0, width, height];
  }
  const staging = diagramStaging(document, inheritedStyles); staging.appendChild(svg);
  const originalStyle = svg.getAttribute('style');
  try {
    if (bounds[2] > 0 && bounds[3] > 0) {
      svg.style.setProperty('width', bounds[2] + 'px'); svg.style.setProperty('height', bounds[3] + 'px');
      svg.style.setProperty('max-width', 'none'); svg.style.setProperty('display', 'block');
    }
    fitNoteBackgrounds(svg, document);
    const graphics = svg as SVGGraphicsElement;
    const union=(x:number,y:number,width:number,height:number,padding=8):void=>{
      if(![x,y,width,height].every(Number.isFinite)||width<0||height<0)return;
      const left=Math.min(bounds[0],x-padding),top=Math.min(bounds[1],y-padding);
      bounds=[left,top,Math.max(bounds[0]+bounds[2],x+width+padding)-left,Math.max(bounds[1]+bounds[3],y+height+padding)-top];
    };
    const painted=paintedBounds(svg,document,[...bounds]);
    if(painted.box&&painted.complete){const box=painted.box;bounds=[box.x-8,box.y-8,box.width+16,box.height+16];}
    else if(painted.box){const box=painted.box;union(box.x,box.y,box.width,box.height);}
    if (!vendorViewport && !painted.box && typeof graphics.getBBox === 'function') {
      // A renderer without a usable viewport still needs a geometric fallback.
      // For a valid Mermaid viewBox, trust the renderer for non-text geometry:
      // getBBox is intentionally unaware of authored clipping in common engines
      // and can otherwise turn clipped/off-canvas shapes into blank page width.
      const box=(graphics.getBBox as (options?:unknown)=>DOMRect)({fill:true,stroke:true,markers:true,clipped:false});
      if(box.width>0&&box.height>0)union(box.x,box.y,box.width,box.height);
    }
    // paintedBounds already measures SVG text with the same visibility, clipping,
    // transform, stroke and marker rules as the rest of the scene. The remaining
    // text-specific gap is HTML inside foreignObject: its glyphs can legitimately
    // paint beyond the element's own box when overflow is visible. Measure only
    // those visible, unclipped ranges so text protection cannot resurrect geometry
    // that a renderer intentionally clipped, masked or made transparent.
    const matrix=graphics.getScreenCTM?.();
    if(matrix){
      let inverse: DOMMatrix | null=null;
      try { inverse=matrix.inverse(); } catch { /* Keep the renderer viewport when the staging transform is not invertible. */ }
      if(inverse){
        const transform=(x:number,y:number)=>({x:inverse.a*x+inverse.c*y+inverse.e,y:inverse.b*x+inverse.d*y+inverse.f});
        const include=(rect:DOMRect):void=>{
          if(!rect.width&&!rect.height)return;
          const corners=[transform(rect.left,rect.top),transform(rect.right,rect.top),transform(rect.left,rect.bottom),transform(rect.right,rect.bottom)];
          const xs=corners.map(p=>p.x),ys=corners.map(p=>p.y),x=Math.min(...xs),y=Math.min(...ys);union(x,y,Math.max(...xs)-x,Math.max(...ys)-y);
        };
        const rangeMayExpand=(node:Node):boolean=>{
          for(let current:Element|null=node.parentElement;current;current=current.parentElement){
            const style=document.defaultView?.getComputedStyle?.(current);
            const value=(property:string,attribute=property):string=>style?.getPropertyValue?.(property)?.trim()||current.getAttribute(attribute)?.trim()||'';
            const display=value('display'),visibility=value('visibility'),opacity=Number.parseFloat(value('opacity'));
            if(display==='none'||visibility==='hidden'||visibility==='collapse'||(Number.isFinite(opacity)&&opacity<=0))return false;
            const clip=value('clip-path'),mask=value('mask')||value('mask-image');
            if((clip&&clip!=='none')||(mask&&mask!=='none'))return false;
            const clippedOverflow=(property:string):boolean=>['hidden','clip','scroll','auto'].includes(value(property)||value('overflow'));
            // Inner HTML/foreignObject/nested-SVG overflow is an authored clip.
            // The scene SVG's own overflow is the viewport boundary this routine
            // is refining, so it must not suppress legitimate visible overhang.
            if(current!==svg&&(clippedOverflow('overflow-x')||clippedOverflow('overflow-y')))return false;
            if(current===svg)break;
          }
          return true;
        };
        for(const object of Array.from(svg.querySelectorAll('foreignObject'))){
          const visit=(node:Node):void=>{
            if(node.nodeType===3&&node.textContent?.trim()&&rangeMayExpand(node)){
              try { const range=document.createRange();range.selectNodeContents(node);for(const rect of Array.from(range.getClientRects()))include(rect); }
              catch { /* Keep the renderer viewport when this browser cannot range-measure SVG HTML. */ }
            }else if(node.nodeType===1){
              if(['script','style'].includes((node as Element).tagName.toLowerCase()))return;
              for(const child of Array.from(node.childNodes))visit(child);
            }
          };visit(object);
        }
      }
    }
  } finally {
    if (originalStyle === null) svg.removeAttribute('style'); else svg.setAttribute('style', originalStyle);
    svg.remove(); staging.remove();
  }
  if (!bounds.every(Number.isFinite) || bounds[2] <= 0 || bounds[3] <= 0) throw new Error('The diagram has no measurable bounds. Its source remains available.');
  svg.setAttribute('viewBox', bounds.join(' ')); return bounds;
}

/** An explicit diagram-specific font must not be replaced by our global default. */
function hasDiagramFont(config: Record<string, unknown>): boolean {
  const pending = Object.entries(config).filter(([key]) => key !== 'themeVariables').map(([, value]) => value);
  const seen = new Set<object>();
  while (pending.length) {
    const value = pending.pop();
    if (!value || typeof value !== 'object' || seen.has(value)) continue;
    seen.add(value);
    for (const [key, child] of Object.entries(value)) {
      if ((key === 'fontFamily' || key.endsWith('FontFamily')) && typeof child === 'string' && child.trim()) return true;
      if (child && typeof child === 'object') pending.push(child);
    }
  }
  return false;
}

/** Native themes derive related fills and text together. Mixing report colors
 * into an authored palette can leave white edge labels on a light background.
 * Font-only overrides still use the report palette.
 */
function hasAuthoredPalette(config: Record<string, unknown>): boolean {
  if (typeof config.theme === 'string' && config.theme.trim()) return true;
  const variables = config.themeVariables;
  return !!variables && typeof variables === 'object' && !Array.isArray(variables)
    && Object.keys(variables).some(name => name !== 'fontFamily' && name !== 'fontSize');
}

export function attachMermaid(root: HTMLElement, ready: (figure: HTMLElement) => void): DiagramController {
  const document = root.ownerDocument, view = document.defaultView;
  const diagrams = [...(root.matches('[data-av-mermaid]') ? [root] : []), ...Array.from(root.querySelectorAll<HTMLElement>('[data-av-mermaid]'))];
  const namespaces = new WeakMap<HTMLElement, string>(), keys = new WeakMap<HTMLElement, string>(), generations = new WeakMap<HTMLElement, number>();
  const sourceDefaults = new WeakMap<HTMLElement, { source: string; nested: boolean; family?: string; theme?: string; palette: boolean }>();
  const original = diagrams.map(element => ({ element, output: element.querySelector<HTMLElement>('[data-av-mermaid-output]')!, children: Array.from(element.querySelector('[data-av-mermaid-output]')?.childNodes || []), status: element.querySelector<HTMLElement>('[data-av-mermaid-status]')!, text: element.querySelector('[data-av-mermaid-status]')?.textContent || '', state: element.getAttribute('data-av-mermaid-state'), busy: element.getAttribute('aria-busy'), hidden: element.querySelector('[data-av-mermaid-output]')?.getAttribute('hidden'), svg: element.querySelector<SVGElement>('[data-av-zoom-target]'), attributes: Array.from(element.querySelector<SVGElement>('[data-av-zoom-target]')?.attributes || []).map(attribute=>[attribute.name,attribute.value]), svgChildren: Array.from(element.querySelector('[data-av-zoom-target]')?.childNodes || []) }));
  let stopped = false;
  let refreshStarted = false, resizeDirty = false, resizeJob: Promise<void> | null = null;
  const jobsInFlight = new Set<Promise<void>>(), requested = new Map<HTMLElement, {key: string; job: Promise<void>}>(), semanticKeys = new Map<HTMLElement, string>(), observedWidths = new WeakMap<HTMLElement, number>();
  const renderWidth=(element:HTMLElement,figure:HTMLElement,output:HTMLElement):number=>{
    const viewport=output.querySelector<HTMLElement>('.av-plot-scroll');
    const body=figure.querySelector<HTMLElement>('[data-av-figure-body]');
    for(const width of [body?.clientWidth,viewport?.clientWidth,figure.clientWidth])if(width&&Number.isFinite(width)&&width>0)return Math.max(MIN_LAYOUT_WIDTH,Math.round(width));
    return observedWidths.get(element) || MIN_LAYOUT_WIDTH;
  };
  const scheduleResize=():void=>{
    if(stopped)return;
    resizeDirty=true;
    if(resizeJob)return;
    resizeJob=Promise.resolve().then(async()=>{while(resizeDirty&&!stopped){resizeDirty=false;await refresh();}}).finally(()=>{resizeJob=null;if(resizeDirty&&!stopped)scheduleResize();});
  };
  async function refresh(): Promise<void> {
    refreshStarted = true;
    const jobs = diagrams.map(element => {
      const figure = figureOf(element), output = element.querySelector<HTMLElement>('[data-av-mermaid-output]'), status = element.querySelector<HTMLElement>('[data-av-mermaid-status]');
      if (!figure || !output || !status || stopped) return Promise.resolve();
      const runtime = (view as unknown as { mermaid?: MermaidRuntime })?.mermaid || (globalThis as unknown as { mermaid?: MermaidRuntime }).mermaid;
      if (!runtime) { element.setAttribute('data-av-mermaid-state','error'); element.removeAttribute('aria-busy'); status.textContent = 'Mermaid is not embedded. Reassemble with --feature mermaid. The original source remains available.'; return Promise.resolve(); }
      const source = element.getAttribute('data-av-mermaid-source') || '';
      const css = view?.getComputedStyle?.(figure);
      const inheritedStyles = diagramStyles(css);
      const roles={background:['--av-plot','#ffffff'],primaryColor:['--av-sheet','#f4f5fa'],primaryTextColor:['--av-ink','#172032'],primaryBorderColor:['--av-line-strong','#66758a'],lineColor:['--av-axis','#66758a'],secondaryColor:['--av-subtle','#ecf1f5'],tertiaryColor:['--av-inspector-surface','#f4edf6'],noteBkgColor:['--av-inspector-surface','#f4edf6'],noteTextColor:['--av-ink','#172032'],noteBorderColor:['--av-line-strong','#66758a']};
      const probes=document.createElement('span');probes.setAttribute('data-av-review-ui','');probes.hidden=true;
      const colorNodes=Object.entries(roles).map(([name,[token,fallback]])=>{const node=document.createElement('span');node.style.setProperty('color',`var(${token})`);probes.appendChild(node);return {name,node,fallback};});
      figure.appendChild(probes);
      const palette:Record<string,string>={fontFamily:css?.fontFamily||'sans-serif'};
      try{for(const {name,node,fallback}of colorNodes){const resolved=view?.getComputedStyle?.(node).color;palette[name]=resolved&&!resolved.includes('var(')?resolved:fallback;}}finally{probes.remove();}
      const width=renderWidth(element,figure,output);
      observedWidths.set(element,width);
      const key = JSON.stringify([source, palette, inheritedStyles, element.getAttribute('data-av-mermaid-config'), width]);
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
        let sourceFont = sourceDefaults.get(element);
        if (sourceFont?.source !== source) {
          // Let the bundled parser interpret frontmatter and directives. Keep
          // their font and palette choices, once per source; width/theme changes do
          // not parse again. Rendering still receives the exact original text.
          const parsed = runtime.parse ? await runtime.parse(source) : false;
          const config = parsed && parsed.config || {};
          sourceFont = { source, nested: hasDiagramFont(config), family: typeof config.fontFamily === 'string' ? config.fontFamily : undefined, theme: typeof config.themeVariables?.fontFamily === 'string' ? config.themeVariables.fontFamily : undefined, palette: hasAuthoredPalette(config) };
          sourceDefaults.set(element, sourceFont);
        }
        if (stopped || generations.get(element) !== generation) return;
        // Mermaid uses its top-level font for geometry and themeVariables for
        // painted labels. Supplying only the latter can make text wider than
        // its node or note background. Keep both defaults aligned while leaving
        // explicitly authored configuration and source directives authoritative.
        const themeFont = sourceFont.theme ?? (sourceFont.family || supplied.themeVariables?.fontFamily || supplied.fontFamily || palette.fontFamily);
        // Empty (not null) disables Mermaid's global override of an explicit
        // per-diagram font; null would restore the vendor's global default.
        const fontFamily = sourceFont.family ?? supplied.fontFamily ?? (sourceFont.nested || hasDiagramFont(supplied) ? '' : themeFont);
        const colorDefaults = sourceFont.palette || hasAuthoredPalette(supplied) ? {} : palette;
        runtime.initialize({ ...supplied, fontFamily, theme: supplied.theme || 'base', themeVariables: { ...colorDefaults, fontFamily: themeFont, ...supplied.themeVariables }, startOnLoad: false, securityLevel: 'strict', suppressErrorRendering: true, deterministicIds: true, deterministicIDSeed: fingerprint(source + (figure.id || 'diagram')), secure: ['securityLevel', 'startOnLoad', 'secure'] });
        let id = 'av-mermaid-' + (++sequence); while(document.getElementById(id)||document.getElementById('d'+id))id='av-mermaid-'+(++sequence);
        const staging = diagramStaging(document, inheritedStyles, width);
        let result: {svg:string}, previousPostprocessor: ElkPostprocessor | null = null, ownsPostprocessor = false;
        let previousArchitectureRouter: ArchitectureRouter | null = null, ownsArchitectureRouter = false;
        try {
          if (runtime.setElkLayoutPostprocessor) { previousPostprocessor = runtime.setElkLayoutPostprocessor(repairElkLayout); ownsPostprocessor = true; }
          if (runtime.setArchitectureRouter) { previousArchitectureRouter = runtime.setArchitectureRouter(routeArchitectureConnection); ownsArchitectureRouter = true; }
          result = await runtime.render(id, source, staging);
        } finally {
          staging.remove();
          if (ownsArchitectureRouter) runtime.setArchitectureRouter!(previousArchitectureRouter);
          if (ownsPostprocessor) runtime.setElkLayoutPostprocessor!(previousPostprocessor);
        }
        if (stopped || generations.get(element) !== generation) return;
        // Strict Mermaid output is the renderer's SVG. No evidence is evaluated as code.
        const template = document.createElement('template'); template.innerHTML = result.svg;
        const incoming = template.content.querySelector<SVGElement>('svg');
        if (!incoming || incoming.querySelector('script')) throw new Error('Mermaid did not return a safe SVG scene.');
        let namespace=namespaces.get(element);if(!namespace){do{namespace='av-diagram-'+(++sequence);}while(document.getElementById(namespace+'-0'));namespaces.set(element,namespace);}
        scopeDiagram(incoming,namespace); incoming.setAttribute('data-av-mermaid-scene', '');
        const plot = output.querySelector<HTMLElement>('[data-av-plot]'), live = plot?.querySelector<SVGElement>('[data-av-zoom-target]');
        if (!plot || !live) throw new Error('The diagram viewport is unavailable.');
        const bounds = diagramBounds(incoming, document, inheritedStyles);
        // Preserve the viewport node and its handlers when a theme rerenders the diagram.
        for (const name of ['id', 'class', 'viewBox', 'preserveAspectRatio', 'role', 'aria-label', 'aria-describedby', 'aria-labelledby', 'data-av-mermaid-scene']) { const value = incoming.getAttribute(name); if (value !== null) live.setAttribute(name, value); else live.removeAttribute(name); }
        // Authored accTitle/accDescr references survive scoping. An unlabeled
        // vendor scene still needs a useful name instead of all its SVG text.
        const nativeTitle = Array.from(incoming.children).some(child => child.localName === 'title' && child.textContent?.trim());
        if (!live.getAttribute('aria-label')?.trim() && !live.getAttribute('aria-labelledby')?.trim() && !nativeTitle) live.setAttribute('aria-label', figureTitle(figure));
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
  let resizeObserver: ResizeObserver | null=null;
  if(view?.ResizeObserver){
    const owners=new Map<Element,HTMLElement>();
    resizeObserver=new view.ResizeObserver(entries=>{let changed=false;for(const entry of entries){const element=owners.get(entry.target),figure=element&&figureOf(element),output=element?.querySelector<HTMLElement>('[data-av-mermaid-output]');if(!element||!figure||!output)continue;const width=renderWidth(element,figure,output),previous=observedWidths.get(element);if(width>0&&width!==previous){observedWidths.set(element,width);changed=true;}}if(changed&&refreshStarted)scheduleResize();});
    for(const element of diagrams){const figure=figureOf(element),output=element.querySelector<HTMLElement>('[data-av-mermaid-output]'),viewport=output?.querySelector<HTMLElement>('.av-plot-scroll'),body=figure?.querySelector<HTMLElement>('[data-av-figure-body]');for(const target of [viewport,body])if(target&&!owners.has(target)){owners.set(target,element);resizeObserver.observe(target);}}
  }
  return { refresh, async whenIdle() { while (resizeJob || jobsInFlight.size) await Promise.all([...jobsInFlight,...(resizeJob?[resizeJob]:[])]); }, cleanup() { stopped = true; resizeObserver?.disconnect(); resizeDirty=false; resizeJob=null; requested.clear(); semanticKeys.clear(); for (const state of original) { state.output.replaceChildren(...state.children); state.status.textContent = state.text; if(state.busy===null)state.element.removeAttribute('aria-busy');else state.element.setAttribute('aria-busy',state.busy); if(state.state===null)state.element.removeAttribute('data-av-mermaid-state');else state.element.setAttribute('data-av-mermaid-state',state.state);if(state.hidden===null||state.hidden===undefined)state.output.removeAttribute('hidden');else state.output.setAttribute('hidden',state.hidden);if(state.svg){for(const attribute of Array.from(state.svg.attributes))state.svg.removeAttribute(attribute.name);for(const[name,value]of state.attributes)state.svg.setAttribute(name,value);state.svg.replaceChildren(...state.svgChildren);} } } };
}
