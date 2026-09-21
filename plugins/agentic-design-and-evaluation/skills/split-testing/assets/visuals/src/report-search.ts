import { anchoredPanel, visibleViewport } from './overlay-layout';
import { figureOf, figureOrigin, figureTitle } from './figures';
import { selectableItems } from './item-selection';
export type SearchKind = 'sections' | 'figures' | 'items' | 'text' | 'notes' | 'bookmarks';
export interface SearchEntry { kind: SearchKind; label: string; text: string; context: string; target?: HTMLElement; activate?(from: HTMLElement): void }
export interface ReportSearch { update(query: string): void; refresh(): void; whenIdle(): Promise<void>; cleanup(): void }
const kinds: SearchKind[] = ['sections','figures','items','text','notes','bookmarks'];
const labels: Record<SearchKind,string> = {sections:'Sections',figures:'Figures',items:'Items & nodes',text:'Text & sources',notes:'Notes',bookmarks:'Bookmarks'};
const ignored = '[data-av-controls],[data-av-review-ui],[data-av-notebook],.av-workspace-bar,.av-workspace-nav,script,style,button,select,textarea,input,.av-sr-only,[data-av-view-question],[role="status"]';
/** Reading separators belong to search excerpts, never stored fingerprints. */
export function searchText(node: Element): string {
  const parts: string[] = [];
  const visit = (node: Node): void => {
    if (node.nodeType === 3) { parts.push(node.textContent || ''); return; }
    if (node.nodeType !== 1 || (node as Element).matches(ignored)) return;
    const block = (node as Element).matches('p,div,section,article,header,footer,summary,li,td,th,dt,dd,pre,blockquote,br,h1,h2,h3,h4,.av-status,.av-id');
    if (block) parts.push(' ');
    for (const child of Array.from(node.childNodes)) visit(child);
    if (block) parts.push(' ');
  };
  visit(node); return parts.join('').replace(/\s+/g, ' ').trim();
}
/** Index the current evidence, including hidden sections. Blocks inside an item
 * are represented once by that item rather than repeated as paragraph hits. */
export function reportEntries(root: HTMLElement): SearchEntry[] {
  const entries: SearchEntry[] = [], seen = new Set<Element>(), objectKeys = new Map<Element, Set<string>>();
  const context = (node: Element): string => { const figure=figureOf(node),owner=figure?figureOrigin(figure).owner:null;const section=node.closest('[data-av-panel]')||owner?.closest('[data-av-panel]');return section?.querySelector('h1,h2,h3')?.textContent?.trim()||''; };
  const own = (node: Element): boolean => node.closest('.av-workspace')===root && !node.closest(ignored);
  const add = (kind:SearchKind,node:HTMLElement,label:string,text:string) => { if(!seen.has(node)&&label.trim()){seen.add(node);entries.push({kind,target:node,label:label.trim(),text,context:context(node)});} };
  for(const node of Array.from(root.querySelectorAll<HTMLElement>('[data-av-panel],.av-card,.av-report-brief,.av-workspace-heading'))){if(!own(node))continue;const heading=Array.from(node.querySelectorAll('h1,h2,h3,h4')).find(h=>h.closest('[data-av-panel],.av-card,.av-report-brief,.av-workspace-heading')===node);if(heading)add('sections',node,heading.textContent||'',node.querySelector(':scope > .av-frame-content > .av-frame-description')?.textContent||'');}
  for(const figure of Array.from(root.querySelectorAll<HTMLElement>('[data-av-figure]'))){if(figureOf(figure)!==figure||!own(figure))continue;add('figures',figure,figureTitle(figure),figure.querySelector('figcaption > span')?.textContent||'');}
  for(const node of Array.from(root.querySelectorAll<HTMLElement>('[data-av-object]'))){if(!own(node))continue;const owner=node.closest('.av-card');if(owner){const keys=objectKeys.get(owner)||new Set<string>();keys.add(node.getAttribute('data-av-object')!);objectKeys.set(owner,keys);}add('items',node,node.querySelector('summary')?.textContent||'Item',searchText(node));}
  for(const node of Array.from(root.querySelectorAll<HTMLElement>(selectableItems))){if(!own(node))continue;const figure=figureOf(node);const key=node.getAttribute('data-av-inspect')||node.getAttribute('data-av-observation');const owner=figure&&figureOrigin(figure).owner;
    if(key&&owner&&objectKeys.get(owner)?.has(key))continue;
    const title=node.getAttribute('aria-label')||node.querySelector('title')?.textContent||node.textContent||'';add('items',node,title,searchText(node));
  }
  // Stop at useful reading blocks; don't index every ancestor's entire subtree.
  function visit(node:Element):void{
    if(node!==root&&(node.matches(ignored)||node.matches('[data-av-object]')||node.matches(selectableItems)||node.matches('[data-av-panel],.av-card,.av-report-brief,.av-workspace-heading')&&node.closest('.av-workspace')!==root))return;
    if(node.matches('img[alt]')){const text=node.getAttribute('alt')||'';if(text)add('text',node as HTMLElement,text,text);return;}
    if(node.matches('p,pre,blockquote,td,th,li,figcaption,text,desc')){const text=searchText(node).trim();if(text)add('text',node as HTMLElement,text.length>100?text.slice(0,100)+'…':text,text);return;}
    for(const child of Array.from(node.children))visit(child);
  }
  visit(root);return entries;
}
/** Worker body contains no imports, network requests, evaluation or user code.
 * The browser's regular-expression engine is isolated and can be terminated. */
function regexWorker():void {
  self.onmessage=(event:MessageEvent<{pattern:string;flags:string;texts:string[]}>)=>{
    try{const re=new RegExp(event.data.pattern,event.data.flags);const hits:(null|[number,number])[]=event.data.texts.map(text=>{const hit=re.exec(text);return hit?[hit.index,hit[0].length]:null;});self.postMessage({hits});}
    catch(error){self.postMessage({error:error instanceof Error?error.message:'Invalid regular expression.'});}
  };
}
export function regexSpec(query:string):{pattern:string;flags:string}{
  let pattern=query,flags='iu';const literal=/^\/([\s\S]*)\/([a-z]*)$/.exec(query);if(literal){pattern=literal[1];flags=literal[2]||'u';}
  if(!/^[imsu]*$/.test(flags)||new Set(flags).size!==flags.length)throw new Error('Use only i, m, s or u regular-expression flags.');
  if(pattern.length>2000)throw new Error('This expression is too long. Use a shorter expression or literal text.');
  return{pattern,flags};
}
export function attachReportSearch(
  root: HTMLElement, input: HTMLInputElement, results: HTMLElement,
  hooks: { notes(): SearchEntry[]; reveal(target: HTMLElement): void; close(): void },
): ReportSearch {
  const document = root.ownerDocument, view = document.defaultView;
  const undo: (() => void)[] = [], limits = new Map<string, number>();
  type Match = { entry: SearchEntry; at: number; length: number };
  let query = '', lastQuery: string | null = null, regex = false;
  let active: SearchKind | 'all' = 'all', matches: Match[] = [];
  let stopped = false, generation = 0, finish: (() => void) | null = null;
  let pending = Promise.resolve(), layer = false, repositioning = false;
  const initial = ['style', 'popover', 'data-av-search-layer', 'data-av-review-ui'].map(name => [name, results.getAttribute(name)] as const);
  const inputInitial = ['aria-controls', 'aria-expanded'].map(name => [name, input.getAttribute(name)] as const);
  const originalId = results.id;
  if (!results.id) {
    const base = (input.id || root.id || 'report') + '--results'; let id = base, n = 1;
    while (document.getElementById(id)) id = base + '-' + (++n);
    results.id = id;
  }
  results.setAttribute('data-av-review-ui', '');
  input.setAttribute('aria-controls', results.id); input.setAttribute('aria-expanded', 'false');
  const nativeLayer = typeof results.showPopover === 'function' && typeof results.hidePopover === 'function';
  if (nativeLayer) { results.setAttribute('popover', 'manual'); results.setAttribute('data-av-search-layer', ''); }
  const toggle = document.createElement('button');
  toggle.type = 'button'; toggle.className = 'av-search-regex'; toggle.textContent = '.*';
  toggle.title = 'Regular expression'; toggle.setAttribute('aria-label', 'Use regular expression');
  toggle.setAttribute('aria-pressed', 'false'); input.parentNode?.appendChild(toggle);

  function listen(target: EventTarget, type: string, fn: EventListener, capture = false): void {
    target.addEventListener(type, fn, capture); undo.push(() => target.removeEventListener(type, fn, capture));
  }
  function create<K extends keyof HTMLElementTagNameMap>(parent: HTMLElement, tag: K, text?: string, cls = ''): HTMLElementTagNameMap[K] {
    const node = document.createElement(tag); node.className = cls;
    if (text !== undefined) node.textContent = text;
    parent.appendChild(node); return node;
  }
  function button(parent: HTMLElement, label: string, fn: () => void, cls = 'av-button av-button-quiet'): HTMLButtonElement {
    const node = create(parent, 'button', label, cls); node.type = 'button';
    node.addEventListener('click', event => { event.preventDefault(); event.stopPropagation(); fn(); }); return node;
  }
  function place(): void {
    if (stopped || results.hidden || !layer || repositioning) return;
    repositioning = true;
    try {
      const bounds = visibleViewport(view), box = input.parentElement!.getBoundingClientRect();
      const available = Math.max(0, bounds.right - bounds.left);
      const width = Math.min(680, available);
      // A fixed top-layer panel remains inside a narrow embed's browser viewport.
      // Its content scrolls, not the header or result-type controls.
      const fit = anchoredPanel(box, bounds, width, 560, 6);
      results.style.setProperty('left', Math.max(bounds.left, Math.min(box.left, bounds.right - width)) + 'px');
      results.style.setProperty('top', fit.top + 'px'); results.style.setProperty('width', width + 'px');
      results.style.setProperty('max-height', fit.maxHeight + 'px');
    } finally { repositioning = false; }
  }
  function show(): void {
    results.hidden = false; input.setAttribute('aria-expanded', 'true');
    if (nativeLayer && !layer) {
      try { results.showPopover(); layer = true; }
      catch { results.removeAttribute('popover'); results.removeAttribute('data-av-search-layer'); }
    }
    place();
  }
  function dismiss(): void {
    if (layer) { try { results.hidePopover(); } catch { /* Already closed. */ } layer = false; }
    results.hidden = true; input.setAttribute('aria-expanded', 'false');
  }
  function cancel(): void { const end = finish; finish = null; end?.(); }
  function close(): void { hooks.close(); update(''); input.focus({ preventScroll: true }); }
  function header(message: string): void {
    results.textContent = '';
    const chrome = create(results, 'header', undefined, 'av-search-header');
    const count = create(chrome, 'strong', message); count.setAttribute('role', 'status');
    button(chrome, 'Close', close).setAttribute('aria-label', 'Close search results');
  }
  function paint(focusKind?: SearchKind | 'all'): void {
    const oldTop = results.querySelector<HTMLElement>('.av-search-body')?.scrollTop || 0;
    header(matches.length ? `${matches.length} ${matches.length === 1 ? 'result' : 'results'}` : 'No matches. Try another search.');
    const indexes = new Map(matches.map((match,index)=>[match,index]));
    const grouped = new Map(kinds.map(kind => [kind, matches.filter(match => match.entry.kind === kind)]));
    const tabs = create(results, 'div', undefined, 'av-search-tabs');
    tabs.setAttribute('role', 'group'); tabs.setAttribute('aria-label', 'Search result types');
    for (const kind of ['all', ...kinds] as const) {
      const count = kind === 'all' ? matches.length : grouped.get(kind)!.length;
      if (kind !== 'all' && !count && active !== kind) continue;
      const choice = button(tabs, `${kind === 'all' ? 'All' : labels[kind]} (${count})`, () => { active = kind; paint(kind); });
      choice.setAttribute('data-av-search-kind', kind); choice.setAttribute('aria-pressed', String(kind === active));
    }
    const body = create(results, 'div', undefined, 'av-search-body');
    for (const kind of kinds) {
      if (active !== 'all' && active !== kind) continue;
      const group = grouped.get(kind)!; if (!group.length) continue;
      const section = create(body, 'section', undefined, 'av-search-group');
      create(section, 'h3', `${labels[kind]} · ${group.length}`);
      const list = create(section, 'ul'), key = active + ':' + kind;
      const base = active === 'all' ? 3 : 20, limit = limits.get(key) || base;
      for (const match of group.slice(0, limit)) {
        const item = create(list, 'li');
        const choice = button(item, '', () => {
          hooks.close(); update('');
          if (match.entry.activate) match.entry.activate(input);
          else if (match.entry.target?.isConnected) hooks.reveal(match.entry.target);
        }, 'av-search-result');
        choice.setAttribute('data-av-search-result', '');choice.setAttribute('data-av-search-hit', String(indexes.get(match)));
        create(choice, 'span', match.entry.label, 'av-search-result-label');
        if (match.entry.context) create(choice, 'span', match.entry.context, 'av-search-result-context');
        const text = match.entry.text;
        const at = Math.max(0, Math.min(text.length, match.at - match.entry.label.length - 1));
        const from = Math.max(0, at - 50), to = Math.min(text.length, Math.max(at + match.length + 100, 160));
        if (text && text !== match.entry.label) create(choice, 'span', (from ? '…' : '') + text.slice(from, to) + (to < text.length ? '…' : ''), 'av-search-result-excerpt');
      }
      const controls = create(section, 'div', undefined, 'av-search-group-actions');
      const redraw = (value: number) => {
        limits.set(key, value); paint();
        // Keep keyboard readers at the same group's controls after replacement.
        const groups = Array.from(results.querySelectorAll<HTMLElement>('.av-search-group'));
        const current = groups.find(node => node.getAttribute('data-av-search-group') === kind);
        current?.querySelector<HTMLElement>('.av-search-group-actions button')?.focus({ preventScroll: true });
      };
      section.setAttribute('data-av-search-group', kind);
      if (group.length > limit) button(controls, `Show ${Math.min(20, group.length - limit)} more…`, () => redraw(limit + 20));
      if (active === 'all' && group.length > base) button(controls, `Only ${labels[kind].toLowerCase()}`, () => { active = kind; paint(kind); });
      if (limit > base) button(controls, 'Show fewer', () => redraw(base));
    }
    body.scrollTop = focusKind ? 0 : oldTop;
    if (focusKind) Array.from(tabs.querySelectorAll<HTMLElement>('button')).find(node => node.getAttribute('data-av-search-kind') === focusKind)?.focus({ preventScroll: true });
    place();
  }
  function run(token: number): Promise<void> {
    const entries = [...reportEntries(root), ...hooks.notes()];
    const texts = entries.map(entry => entry.label + '\n' + entry.text + '\n' + entry.context);
    const accept = (hits: (null | [number, number])[]) => {
      if (stopped || token !== generation) return;
      matches = [];
      hits.forEach((hit, index) => { if (hit && entries[index]) matches.push({ entry: entries[index], at: hit[0], length: hit[1] }); });
      paint();
    };
    if (!regex) {
      const needle = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      const re = new RegExp(needle, 'iu');
      accept(texts.map(text => { const hit = re.exec(text); return hit ? [hit.index, hit[0].length] : null; }));
      return Promise.resolve();
    }
    let worker: Worker | null = null, url: string | null = null;
    try {
      const spec = regexSpec(query);
      if (!view?.Worker || !view.URL?.createObjectURL) throw new Error('Regular-expression search requires a browser worker. Literal text search is still available.');
      url = view.URL.createObjectURL(new Blob(['(' + regexWorker.toString() + ')()'], { type: 'text/javascript' }));
      worker = new view.Worker(url);
      return new Promise<void>(resolve => {
        let done = false;
        const end = () => {
          if (done) return; done = true; clearTimeout(timer); worker?.terminate();
          if (url) view.URL.revokeObjectURL(url);
          if (finish === end) finish = null;
          resolve();
        };
        const timer = setTimeout(() => {
          if (!stopped && token === generation) { header('This expression took too long. Simplify it or use literal text search.'); place(); }
          end();
        }, 1000);
        finish = end;
        worker!.onmessage = event => {
          if (!done && !stopped && token === generation) {
            if (event.data.error) { header('Invalid expression: ' + event.data.error); place(); }
            else accept(event.data.hits);
          }
          end();
        };
        worker!.onerror = () => {
          if (!done && !stopped && token === generation) { header('Regular-expression search could not start. Use literal text search.'); place(); }
          end();
        };
        try { worker!.postMessage({ ...spec, texts }); }
        catch { header('This report could not be searched with that expression. Use literal text search.'); end(); }
      });
    } catch (error) {
      worker?.terminate(); if (url) view?.URL.revokeObjectURL(url);
      if (!stopped && token === generation) { header(error instanceof Error ? error.message : 'Search failed.'); place(); }
      return Promise.resolve();
    }
  }
  function update(value: string): void {
    if (stopped) return;
    query = value.trim(); const key = (regex ? 'regex:' : 'literal:') + query;
    if (key === lastQuery) { if (query && results.hidden) show(); return; }
    lastQuery = key; generation++; cancel();
    if (!query) { dismiss(); results.textContent = ''; matches = []; pending = Promise.resolve(); return; }
    limits.clear(); active = 'all'; header('Searching…'); show();
    // Literal queries remain synchronous and bounded in rendered results. Regex
    // never runs on the main thread, including syntax checking and empty matches.
    pending = run(generation);
  }
  listen(toggle, 'click', event => {
    event.preventDefault(); event.stopPropagation(); regex = !regex;
    toggle.setAttribute('aria-pressed', String(regex)); lastQuery = null; update(input.value); input.focus({ preventScroll: true });
  });
  const onKey = ((event: KeyboardEvent) => {
    if (results.hidden || event.isComposing) return;
    const target = event.target as HTMLElement;
    if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); close(); return; }
    if (!['ArrowDown', 'ArrowUp'].includes(event.key) || event.altKey || event.ctrlKey || event.metaKey) return;
    const items = Array.from(results.querySelectorAll<HTMLElement>('[data-av-search-result]'));
    const index = items.indexOf(target); if (target !== input && index < 0) return;
    event.preventDefault(); event.stopPropagation(); const next = index + (event.key === 'ArrowDown' ? 1 : -1);
    if (next < 0) input.focus(); else items[Math.min(items.length - 1, next)]?.focus();
  }) as EventListener;
  listen(input, 'keydown', onKey); listen(results, 'keydown', onKey);
  listen(document, 'pointerdown', event => {
    if (!results.hidden && !results.contains(event.target as Node) && !input.parentElement?.contains(event.target as Node)) dismiss();
  }, true);
  listen(input, 'focus', () => { if (input.value.trim() && results.hidden) { lastQuery = null; update(input.value); } });
  const leave = ((event: FocusEvent) => {
    if (event.relatedTarget && !results.contains(event.relatedTarget as Node) && !input.parentElement?.contains(event.relatedTarget as Node)) dismiss();
  }) as EventListener;
  listen(input.parentElement!, 'focusout', leave); listen(results, 'focusout', leave);
  if (view) { listen(view, 'resize', place); if (view.visualViewport) listen(view.visualViewport, 'resize', place); }
  listen(document, 'scroll', place, true);
  return {
    update, refresh() { if (query && !results.hidden) { lastQuery = null; update(input.value); } },
    async whenIdle() { for (;;) { const job = pending; await job; if (pending === job) return; } },
    cleanup() {
      if (stopped) return; stopped = true; generation++; cancel(); dismiss();
      for (const fn of undo.reverse()) fn(); toggle.remove(); results.textContent = '';
      for (const [name, value] of initial) { if (value === null) results.removeAttribute(name); else results.setAttribute(name, value); }
      for (const [name, value] of inputInitial) { if (value === null) input.removeAttribute(name); else input.setAttribute(name, value); }
      if (originalId) results.id = originalId; else results.removeAttribute('id');
    },
  };
}
