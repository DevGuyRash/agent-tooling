import { documentId, escapeText as e, svg } from './core';
export interface FigureBounds { width: number; height: number }
export interface FigureSource { language: string; text: string; filename?: string }
export interface FigureItem { id: string; label: string; text?: string; values?: Record<string, string | number | null> }
export interface VisualFigureInput {
  id?: string; title: string; caption?: string;
  /** Natural fit shrinks to the available space without enlarging the drawing. */
  fit?: 'natural' | 'width';
  /** Trusted author composition. Evidence strings belong in escaped renderer fields. */
  body: string; adapter?: string; source?: FigureSource;
}
export interface VisualAdapter {
  bounds(element: HTMLElement): FigureBounds;
  /** A self-contained full-scope SVG, independent of viewport zoom/pan. */
  svg?(element: HTMLElement): string | Promise<string>;
  png?(element: HTMLElement): Blob | Promise<Blob>;
  source?(element: HTMLElement): FigureSource | undefined;
  items?(element: HTMLElement): readonly FigureItem[];
  /** Return the stable item ID for a clicked native item, if it is identifiable. */
  identify?(target: Element, element: HTMLElement): string | undefined;
}
const adapters = new Map<string, VisualAdapter>();
export function registerVisualAdapter(name: string, adapter: VisualAdapter): () => void {
  documentId(name, 'An adapter name');
  if (adapters.has(name)) throw new TypeError(`Visual adapter ${name} is already registered.`);
  if (typeof adapter.bounds !== 'function') throw new TypeError('A visual adapter needs bounds.');
  adapters.set(name, adapter); return () => { if (adapters.get(name) === adapter) adapters.delete(name); };
}
export function visualAdapter(element: HTMLElement): VisualAdapter | undefined { return adapters.get(element.getAttribute('data-av-adapter') || ''); }
export function visualFigure(input: VisualFigureInput): string {
  if (typeof input.title !== 'string' || !input.title.trim() || typeof input.body !== 'string') throw new TypeError('A figure needs a title and trusted body markup.');
  if (input.adapter) documentId(input.adapter, 'An adapter name');
  if (input.fit !== undefined && input.fit !== 'natural' && input.fit !== 'width') throw new TypeError('Figure fit must be natural or width.');
  if (input.source && (typeof input.source.text !== 'string' || typeof input.source.language !== 'string')) throw new TypeError('Figure source needs a language and its original text.');
  return `<figure class="av-visual-figure" data-av-figure data-av-figure-title="${e(input.title)}"${input.id ? ` id="${e(documentId(input.id))}"` : ''}${input.fit ? ` data-av-fit-policy="${input.fit}"` : ''}${input.adapter ? ` data-av-adapter="${e(input.adapter)}"` : ''}${input.source ? ` data-av-source="${e(JSON.stringify(input.source))}"` : ''}><figcaption class="av-figure-caption">${e(input.title)}${input.caption ? `<span>${e(input.caption)}</span>` : ''}</figcaption><div class="av-figure-body" data-av-figure-body>${input.body}</div></figure>`;
}
export interface MermaidDiagramInput { id?: string; title: string; source: string; caption?: string; fit?: 'natural' | 'width'; config?: Record<string, unknown> }
export function mermaidDiagram(input: MermaidDiagramInput): string {
  if (typeof input.source !== 'string' || !input.source.trim()) throw new TypeError('A Mermaid diagram needs its original source.');
  // HTML normalizes literal carriage returns and discards a leading newline in
  // <pre>. Character references and the code child keep the supplied source intact.
  const sourceMarkup = e(input.source).replace(/\r/g, '&#13;');
  const body = `<div class="av-mermaid" data-av-mermaid data-av-requires="mermaid" data-av-mermaid-source="${sourceMarkup}"${input.config ? ` data-av-mermaid-config="${e(JSON.stringify(input.config))}"` : ''}><p class="av-note" data-av-mermaid-status role="status">Diagram source is available below.</p><div data-av-mermaid-output>${svg(input.title, 400, '', 900)}</div><details class="av-diagram-source"><summary>Diagram source</summary><pre tabindex="0" role="region" aria-label="${e(`Original Mermaid source: ${input.title}`)}"><code>${sourceMarkup}</code></pre></details></div>`;
  return visualFigure({ ...input, fit: input.fit ?? 'natural', source: { language: 'mermaid', text: input.source, filename: 'diagram.mmd' }, body });
}
export function figureOf(element: Element): HTMLElement | null {
  const nearest = element.closest<HTMLElement>('[data-av-figure]');
  return nearest?.parentElement?.closest<HTMLElement>('.av-visual-figure') || nearest;
}
export function figureTitle(element: HTMLElement): string {
  return element.getAttribute('data-av-figure-title') || element.querySelector('figcaption,svg title')?.textContent?.trim() || figureOrigin(element).owner?.querySelector('.av-card-title')?.textContent || 'Visualization';
}
export function figureSource(element: HTMLElement): FigureSource | undefined {
  const supplied = visualAdapter(element)?.source?.(element);
  const checked=(value:unknown):FigureSource=>{
    if(!value||typeof value!=='object'||Array.isArray(value))throw new Error('Figure source must contain its original text and language.');
    const source=value as FigureSource;
    if(typeof source.text!=='string'||typeof source.language!=='string'||source.filename!==undefined&&typeof source.filename!=='string')throw new Error('Figure source must contain its original text and language.');
    return source;
  };
  if (supplied !== undefined && supplied !== null) return checked(supplied);
  const raw = element.getAttribute('data-av-source');
  if (raw) return checked(JSON.parse(raw));
  const recipe = (element.closest('[data-av-layout-input]') || figureOrigin(element).owner)?.getAttribute('data-av-layout-input');
  return recipe ? { language: 'json', text: recipe, filename: 'figure-data.json' } : undefined;
}

interface FigureOrigin { owner: HTMLElement | null; explorer: HTMLElement | null; scope: HTMLElement | null }
const origins = new WeakMap<HTMLElement, FigureOrigin>();
export function retainFigureOrigin(figure: HTMLElement): void { if(!origins.has(figure))origins.set(figure,{owner:figure.closest<HTMLElement>('.av-card'),explorer:figure.closest<HTMLElement>('[data-av-explorer]'),scope:figure.closest<HTMLElement>('[data-av-coordinate-scope]')}); }
export function figureOrigin(figure: HTMLElement): FigureOrigin { return origins.get(figure)||{owner:figure.closest<HTMLElement>('.av-card'),explorer:figure.closest<HTMLElement>('[data-av-explorer]'),scope:figure.closest<HTMLElement>('[data-av-coordinate-scope]')}; }

export function figureContext(figure:HTMLElement):HTMLElement[] {
  const origin=figureOrigin(figure),nodes:HTMLElement[]=[];
  const caption=figure.querySelector('figcaption')?.querySelector<HTMLElement>('span');if(caption)nodes.push(caption);
  if(origin.scope){const note=Array.from(origin.scope.children).find(element=>element.matches('.av-note'));if(note)nodes.push(note as HTMLElement);}
  for(const element of Array.from(origin.owner?.querySelectorAll<HTMLElement>('.av-frame-description,.av-legend,.av-frame-footer')||[]))if(element.closest('.av-card')===origin.owner)nodes.push(element);
  return nodes;
}
