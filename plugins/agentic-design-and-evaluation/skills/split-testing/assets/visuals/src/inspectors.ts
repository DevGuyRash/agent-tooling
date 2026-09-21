import { figureOf, figureOrigin } from './figures';
import { registerReviewPlaceholder } from './review-targets';
import { commandIcon, focusCommand } from './command-bar';
import { visibleViewport } from './overlay-layout';

interface Inspector {
  explorer: HTMLElement; reader: HTMLElement; plot: HTMLElement; opener: HTMLButtonElement;
  dialog: HTMLDialogElement; home: Comment; releasePosition: () => void; syncPosition: () => void; mode: 'side' | 'drawer';
  trigger: HTMLElement | null; undo: (() => void)[];
}
export interface InspectorController { refresh(): void; open(target: Element, trigger?: HTMLElement): boolean; cleanup(): void }
/** One live evidence reader. On small containers it becomes a closable reading
 * drawer, not a second copy of the evidence below an already long drawing. */
export function attachInspectors(root: HTMLElement): InspectorController {
  const document = root.ownerDocument, view = document.defaultView, records: Inspector[] = [];
  let stopped = false, scheduled: number | null = null;
  function close(record: Inspector, restore = true): void {
    if (record.dialog.open) record.dialog.close();
    record.opener.setAttribute('aria-expanded','false');
    if (restore && record.trigger?.isConnected) focusCommand(record.trigger);
    record.trigger = null;
  }
  function place(record: Inspector): void {
    const width = record.explorer.clientWidth; if (!width || stopped) return;
    const rootFont = parseFloat(view?.getComputedStyle?.(document.documentElement).fontSize || '16') || 16;
    const mode = width >= 55 * rootFont ? 'side' : 'drawer';
    if (mode !== record.mode) {
      if (mode === 'side') {
        close(record); record.home.parentNode?.insertBefore(record.reader,record.home.nextSibling);
      } else record.dialog.appendChild(record.reader);
      record.mode = mode; record.syncPosition();
    }
    record.explorer.setAttribute('data-av-inspector-layout',mode);
    record.opener.hidden = mode === 'side';
    const selected = record.reader.querySelector<HTMLElement>('[data-av-object].av-selected') || record.reader.querySelector<HTMLElement>('[data-av-object][open]');
    const label = selected?.querySelector('summary')?.textContent?.trim();
    const text = record.opener.querySelector('span'); if (text) text.textContent = label ? 'Read evidence: ' + label : 'Read evidence';
    const bounds = visibleViewport(view,12);
    record.dialog.style.setProperty('max-height', Math.max(0,bounds.bottom-bounds.top) + 'px');
    if (mode === 'side') {
      const drawing = record.plot.querySelector<HTMLElement>('.av-plot-scroll') || record.plot;
      const plotBox = record.plot.getBoundingClientRect(), box = drawing.getBoundingClientRect();
      const barHeight = record.explorer.closest('.av-workspace')?.querySelector('.av-workspace-bar')?.getBoundingClientRect().height || 0;
      const available = Math.max(180,bounds.bottom-bounds.top-barHeight-32);
      const height = Math.min(available,Math.max(200,box.height));
      record.reader.style.setProperty('--av-inspector-height', height + 'px');
      record.reader.style.setProperty('--av-inspector-offset', Math.max(0,box.top-plotBox.top) + 'px');
    }
  }
  function refresh(): void { for (const record of records) place(record); }
  function schedule(): void {
    if (stopped || scheduled !== null) return;
    if (!view?.requestAnimationFrame) { refresh(); return; }
    scheduled = view.requestAnimationFrame(() => { scheduled = null; refresh(); });
  }
  for (const reader of Array.from(root.querySelectorAll<HTMLElement>('.av-inspector'))) {
    const explorer = reader.parentElement; if (!explorer || !explorer.closest('[data-av-explorer]')) continue;
    const plot = Array.from(explorer.children).find(node => node.matches('.av-plot-shell,.av-scatter-scenes')) as HTMLElement | undefined;
    if (!reader || !plot) continue;
    const dialog = document.createElement('dialog'); if (typeof dialog.showModal !== 'function') continue;
    dialog.className = 'av-focus-dialog av-inspector-dialog'; dialog.setAttribute('aria-label','Evidence reader');
    const header = document.createElement('header'); header.className = 'av-inspector-header'; header.setAttribute('data-av-review-ui','');
    const title = document.createElement('strong'); title.textContent = 'Evidence'; header.appendChild(title);
    const dismiss = document.createElement('button'); dismiss.type = 'button'; dismiss.className = 'av-button'; dismiss.textContent = 'Close'; dismiss.setAttribute('aria-label','Close evidence reader'); header.appendChild(dismiss); dialog.appendChild(header);
    const home = document.createComment('av-evidence-reader'); reader.parentNode!.insertBefore(home,reader);
    // A docked reader is already in the source tree. Substitute the placeholder
    // only while it is moved into a transient dialog.
    let release: () => void = () => {};
    const opener = document.createElement('button'); opener.type = 'button'; opener.className = 'av-button av-inspector-opener'; opener.setAttribute('aria-haspopup','dialog'); opener.setAttribute('aria-expanded','false'); opener.hidden = true; opener.setAttribute('data-av-review-ui','');
    opener.appendChild(commandIcon(document,'M4 3h16v18H4zM8 7h8M8 11h8M8 15h6'));
    const label = document.createElement('span'); label.textContent = 'Read evidence'; opener.appendChild(label);
    const toolbar = Array.from(plot.children).find(child => child.matches('.av-plot-toolbar'));
    plot.insertBefore(opener,toolbar?.nextSibling || plot.firstChild); explorer.appendChild(dialog);
    const oldLayout = explorer.getAttribute('data-av-inspector-layout'), oldStyle = reader.getAttribute('style');
    const record: Inspector = {explorer,reader,plot,opener,dialog,home,releasePosition:()=>release(),syncPosition:()=>{},mode:'side',trigger:null,undo:[]};
    const open = () => { record.trigger = opener; reader.setAttribute('open',''); if (!dialog.open) dialog.showModal(); opener.setAttribute('aria-expanded','true'); dismiss.focus({preventScroll:true}); };
    const closeClick = (event: Event) => { event.preventDefault(); event.stopPropagation(); close(record); };
    opener.addEventListener('click',open); dismiss.addEventListener('click',closeClick); dialog.addEventListener('cancel',closeClick);
    // Keep the placeholder active only while the live reader is in the dialog.
    const updateIdentity = () => { release(); release = reader.parentNode === dialog ? registerReviewPlaceholder(home,reader) : () => {}; };
    record.syncPosition = updateIdentity;
    record.undo.push(() => { opener.removeEventListener('click',open); dismiss.removeEventListener('click',closeClick); dialog.removeEventListener('cancel',closeClick); if(oldLayout===null)explorer.removeAttribute('data-av-inspector-layout');else explorer.setAttribute('data-av-inspector-layout',oldLayout); if(oldStyle===null)reader.removeAttribute('style');else reader.setAttribute('style',oldStyle); });
    if (view?.ResizeObserver) { const observer = new view.ResizeObserver(schedule); observer.observe(explorer); observer.observe(plot); record.undo.push(() => observer.disconnect()); }
    records.push(record);

  }
  // Polling is unnecessary: layout invalidation and viewport changes cover moves.
  root.addEventListener('av-layout-invalidated',schedule,true);
  view?.addEventListener('resize',schedule); view?.visualViewport?.addEventListener('resize',schedule);
  refresh();
  return {
    refresh,
    open(target,trigger) {
      const explorer = target.closest('[data-av-explorer]') || (figureOf(target) ? figureOrigin(figureOf(target)!).explorer : null);
      const record = records.find(record => record.explorer === explorer || record.explorer.closest('[data-av-explorer]') === explorer); if (!record) return false;
      place(record); record.reader.setAttribute('open','');
      if (record.mode === 'side') { record.reader.querySelector<HTMLElement>('summary')?.focus({preventScroll:true}); return true; }
      record.trigger = trigger || record.opener; if (!record.dialog.open) record.dialog.showModal(); record.opener.setAttribute('aria-expanded','true');
      record.dialog.querySelector<HTMLElement>('button')?.focus({preventScroll:true}); return true;
    },
    cleanup() {
      if(stopped)return; stopped=true;
      if(scheduled!==null)view?.cancelAnimationFrame(scheduled);
      root.removeEventListener('av-layout-invalidated',schedule,true); view?.removeEventListener('resize',schedule); view?.visualViewport?.removeEventListener('resize',schedule);
      for(const record of records){ close(record,false); record.releasePosition(); record.home.parentNode?.insertBefore(record.reader,record.home.nextSibling);record.home.remove();record.opener.remove();record.dialog.remove();for(const restore of record.undo.reverse())restore();}
    }
  };
}
