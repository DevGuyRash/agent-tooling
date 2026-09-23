import { figureOf, figureOrigin } from './figures';
import { registerReviewPlaceholder } from './review-targets';
import { CommandOptions, commandIcon, focusCommand } from './command-bar';
import { clampOverlayPosition, visibleViewport } from './overlay-layout';

type ReaderLayout = 'closed' | 'floating' | 'side' | 'drawer';
let nextInspector = 0;
interface Inspector {
  owner: HTMLElement; explorer: HTMLElement; reader: HTMLElement; plot: HTMLElement;
  summary: HTMLElement; pin: HTMLButtonElement; closeButton: HTMLButtonElement;
  dialog: HTMLDialogElement; home: Comment; figures: HTMLElement[];
  openers: Map<HTMLElement, HTMLButtonElement>; activeFigure: HTMLElement | null;
  trigger: HTMLElement | null; canvas: HTMLElement | null;
  open: boolean; pinned: boolean; raised: boolean; layout: ReaderLayout;
  occlusion: number;
  occlusionFigure: HTMLElement | null;
  viewportSize: string | null;
  releasePosition: () => void; undo: (() => void)[];
}
export interface InspectorHooks {
  command?(figure: HTMLElement, control: HTMLButtonElement, options: CommandOptions): void;
  layout?(figure: HTMLElement): void;
  contextChanged?(): void;
  /** A floating reader may cover a mark; the viewport owns any pan correction. */
  reveal?(item: Element, occlusion: DOMRect | null): void;
}
export interface InspectorController {
  refresh(): void;
  open(target: Element, trigger?: HTMLElement, takeFocus?: boolean): boolean;
  /** Selection previews never launch a modal or steal focus from the drawing. */
  preview(target: Element): void;
  dismissOutside(target: Element, keepContained?: boolean): void;
  /** Suspend a figure-local reader while that figure occupies another view. */
  suspend(target: Element): () => boolean;
  cleanup(): void;
}

/** One live evidence reader per explorer. The drawing starts at full width;
 * readers can open a non-modal peek, explicitly pin it, or use the narrow drawer.
 * The evidence itself always stays under its original report/explorer owner. */
export function attachInspectors(root: HTMLElement, hooks: InspectorHooks = {}): InspectorController {
  const document = root.ownerDocument, view = document.defaultView, records: Inspector[] = [];
  let stopped = false, scheduled: number | null = null, placing = false, watching = false;
  const icon = 'M4 3h16v18H4zM8 7h8M8 11h8M8 15h6';
  const property = (element: HTMLElement, name: string, value: string | null) => {
    if (value === null) element.style.removeProperty(name);
    else if (element.style.getPropertyValue(name) !== value) element.style.setProperty(name, value);
  };
  function visible(element: HTMLElement): boolean {
    return !element.closest('[hidden]') && element.getBoundingClientRect().width > 0;
  }
  function viewport(record: Inspector): HTMLElement | null {
    const active = record.activeFigure;
    if (active && visible(active)) return active.querySelector<HTMLElement>('.av-plot-scroll');
    return Array.from(record.plot.querySelectorAll<HTMLElement>('.av-plot-scroll')).find(visible) || null;
  }
  function selected(record: Inspector): HTMLElement | null {
    return record.reader.querySelector<HTMLElement>('[data-av-object].av-selected')
      || record.reader.querySelector<HTMLElement>('[data-av-object][open]');
  }
  function selectedMark(record: Inspector): HTMLElement | null {
    const key = selected(record)?.getAttribute('data-av-object');
    const candidates = record.activeFigure ? [record.activeFigure, ...record.figures] : record.figures;
    for (const figure of candidates) {
      if (!visible(figure)) continue;
      const mark = Array.from(figure.querySelectorAll<HTMLElement>('[data-av-inspect]')).find(item => item.getAttribute('data-av-inspect') === key);
      if (mark) return mark;
    }
    return null;
  }
  function lower(record: Inspector): void {
    if (record.raised) {
      record.raised = false;
      try { record.reader.hidePopover(); } catch { /* The browser can close an ancestor first. */ }
    }
    record.reader.removeAttribute('popover');
  }
  function home(record: Inspector): void {
    if (record.reader.parentNode !== record.home.parentNode) record.home.parentNode?.insertBefore(record.reader, record.home.nextSibling);
    record.releasePosition(); record.releasePosition = () => {};
  }
  function reserve(record: Inspector, canvas: HTMLElement | null): void {
    if (record.canvas === canvas) return;
    const previous = record.canvas;
    record.canvas?.removeAttribute('data-av-inspector-canvas');
    record.canvas = canvas;
    canvas?.setAttribute('data-av-inspector-canvas', '');
    const figure = canvas && figureOf(canvas) || previous && figureOf(previous);
    if (figure) hooks.layout?.(figure);
  }
  function opener(record: Inspector): HTMLElement | null {
    return record.activeFigure && record.openers.get(record.activeFigure) || record.openers.values().next().value || null;
  }
  function watch(): void {
    const needed = records.some(record => record.open);
    if (watching === needed) return;
    watching = needed;
    const method = needed ? 'addEventListener' : 'removeEventListener';
    document[method]('scroll', schedule, true);
    document[method]('keydown', escape as EventListener, true);
    document[method]('pointerdown', outside as EventListener, true);
  }
  function close(record: Inspector, restore = true): void {
    if (!record.open && record.layout === 'closed') return;
    const trigger = record.trigger;
    record.open = false;
    lower(record);
    if (record.dialog.open) record.dialog.close();
    home(record); reserve(record, null);
    record.layout = 'closed'; record.reader.hidden = true;
    record.reader.setAttribute('data-av-inspector-view', 'closed');
    record.explorer.setAttribute('data-av-inspector-layout', 'closed');
    for (const control of record.openers.values()) control.setAttribute('aria-expanded', 'false');
    hooks.reveal?.(selectedMark(record) || record.plot, null);
    if (restore) focusCommand(trigger?.isConnected && visible(trigger) ? trigger : opener(record));
    record.trigger = null; watch(); hooks.contextChanged?.();
  }
  function place(record: Inspector, explicit = false, allowDrawer = true): void {
    const drawing = viewport(record), canvas = drawing?.closest<HTMLElement>('.av-row-plot-layout') || drawing;
    if (!record.open) { reserve(record, null); return; }
    if (!drawing || !canvas) { close(record, false); return; }
    const drawnFigure = figureOf(drawing); if (drawnFigure && record.figures.includes(drawnFigure)) record.activeFigure = drawnFigure;
    const expandedFigure = !!drawing.closest('[data-av-expanded-figure]');
    if (expandedFigure && !explicit && record.layout !== 'drawer') { close(record, false); return; }
    const available = visibleViewport(view, 12);
    const viewportSize = `${available.right - available.left}:${available.bottom - available.top}`;
    const keepReading = record.viewportSize !== null && record.viewportSize !== viewportSize && record.reader.contains(document.activeElement);
    record.viewportSize = viewportSize;
    let box = canvas.getBoundingClientRect();
    const font = parseFloat(view?.getComputedStyle?.(document.documentElement).fontSize || '16') || 16;
    const bar = record.owner.closest('.av-workspace')?.querySelector('.av-workspace-bar')?.getBoundingClientRect();
    const topLimit = Math.max(available.top, bar && bar.bottom > 0 && bar.top < available.bottom ? bar.bottom + 12 : available.top);
    const floatingTop = Math.max(topLimit, box.top + 12), floatingRoom = available.bottom - floatingTop;
    // Resizing can push a later figure below the viewport as preceding text wraps.
    // Keep a focused reader for the drawer transition; incidental scrolling still
    // closes an out-of-room peek instead of opening a modal.
    if (!explicit && !keepReading && record.layout === 'floating' && (box.bottom <= topLimit || floatingRoom < 220)) {
      close(record, record.reader.contains(document.activeElement)); return;
    }
    const fullWidth = record.canvas === canvas ? record.explorer.clientWidth : box.width;
    const canFloat = !expandedFigure && fullWidth >= 46 * font && available.right - available.left >= 48 * font
      && floatingRoom >= 220 && box.bottom > topLimit;
    const canPin = !expandedFigure && record.explorer.clientWidth >= 58 * font;
    const layout: ReaderLayout = record.pinned && canPin ? 'side' : canFloat ? 'floating' : 'drawer';
    const previousLayout = record.layout, focus = record.reader.contains(document.activeElement) ? document.activeElement as HTMLElement : null;
    if (layout === 'drawer' && (!allowDrawer || !explicit && previousLayout !== 'drawer' && !focus)) { close(record, false); return; }
    record.pin.disabled = !canPin && !record.pinned;
    record.pin.hidden = record.pin.disabled;
    record.pin.setAttribute('aria-pressed', String(record.pinned));
    record.pin.title = record.pinned ? 'Unpin evidence' : 'Keep evidence beside the drawing';
    record.pin.querySelector('span')!.textContent = record.pinned ? 'Pinned' : 'Pin';
    if (layout !== previousLayout) {
      lower(record);
      if (record.dialog.open) record.dialog.close();
      home(record);
      record.layout = layout;
      record.explorer.setAttribute('data-av-inspector-layout', layout);
      record.reader.setAttribute('data-av-inspector-view', layout);
      record.reader.hidden = false;
      if (layout === 'drawer') {
        record.dialog.appendChild(record.reader);
        record.releasePosition = registerReviewPlaceholder(record.home, record.reader);
        record.dialog.showModal();
      } else if (layout === 'floating' && typeof record.reader.showPopover === 'function') {
        record.reader.setAttribute('popover', 'manual');
        try { record.reader.showPopover(); record.raised = true; }
        catch { record.reader.removeAttribute('popover'); }
      }
    }
    if (layout === 'floating' && record.reader.hasAttribute('popover') && !record.reader.matches(':popover-open')) {
      try { record.reader.showPopover(); record.raised = true; } catch { lower(record); }
    }
    reserve(record, layout === 'side' ? canvas : null);
    // Pinning changes the drawing's width synchronously. Positioning from the
    // pre-pin box would briefly cover the wrong region and over-pan the mark.
    box = canvas.getBoundingClientRect();
    const height = Math.max(120, Math.min(36 * font, available.bottom - topLimit, Math.max(280, box.height)));
    if (layout === 'side') {
      const readerHeight = Math.min(height, Math.max(240, box.height));
      const top = Math.max(box.top, Math.min(topLimit, box.bottom - readerHeight));
      property(record.reader, '--av-inspector-offset', Math.max(0, top - record.explorer.getBoundingClientRect().top) + 'px');
      property(record.reader, '--av-inspector-height', readerHeight + 'px');
      for (const key of ['left','top','width','height','max-height','max-width']) property(record.reader, key, null);
    } else if (layout === 'floating') {
      const width = Math.min(27 * font, box.width * .44, available.right - available.left);
      const top = Math.max(topLimit, box.top + 12), floatingHeight = Math.min(height, available.bottom - top);
      const left = Math.max(available.left, Math.min(box.right - width - 12, available.right - width));
      property(record.reader, 'left', left + 'px'); property(record.reader, 'top', top + 'px');
      property(record.reader, 'width', width + 'px'); property(record.reader, 'height', floatingHeight + 'px');
      property(record.reader, 'max-width', (available.right - available.left) + 'px');
      property(record.reader, 'max-height', Math.max(120, available.bottom - top) + 'px');
      const measured = record.reader.getBoundingClientRect();
      const position = clampOverlayPosition(available, measured.width, measured.height, left, top);
      property(record.reader, 'left', position.left + 'px'); property(record.reader, 'top', position.top + 'px');
    } else {
      for (const key of ['left','top','width','height','max-height','max-width']) property(record.reader, key, null);
      property(record.dialog, 'max-height', Math.max(120, available.bottom - available.top) + 'px');
    }
    for (const control of record.openers.values()) control.setAttribute('aria-expanded', 'true');
    const occlusion = layout === 'floating' ? Math.ceil(record.reader.getBoundingClientRect().width) : 0;
    if (occlusion !== record.occlusion || record.activeFigure !== record.occlusionFigure) {
      record.occlusion = occlusion; record.occlusionFigure = record.activeFigure;
      hooks.reveal?.(selectedMark(record) || record.plot, occlusion ? record.reader.getBoundingClientRect() : null);
    }
    // Movement between native top layers can discard focus. Retain the same
    // evidence node; do not refocus on ordinary scrolling or item updates.
    if (layout !== previousLayout && focus?.isConnected) focusCommand(focus);
  }
  function refresh(): void {
    if (stopped || placing) return;
    placing = true;
    try { for (const record of records) place(record); } finally { placing = false; }
  }
  function schedule(): void {
    if (stopped || scheduled !== null) return;
    if (!view?.requestAnimationFrame) { refresh(); return; }
    scheduled = view.requestAnimationFrame(() => { scheduled = null; refresh(); });
  }
  function escape(event: KeyboardEvent): void {
    if (event.key !== 'Escape' || event.defaultPrevented || event.isComposing) return;
    const target = event.target as Element | null;
    // A source dialog or menu above this reader owns Escape first.
    const record = [...records].reverse().find(item => item.open && (item.reader.contains(target) || item.layout === 'floating' && item.owner.contains(target)));
    if (!record || record.layout === 'drawer') return;
    if (target?.closest('.av-floating-panel,.av-command-menu,.av-source-dialog,.av-context-review')) return;
    event.preventDefault(); event.stopPropagation(); close(record);
  }
  function outside(event: PointerEvent): void {
    const target = event.target as Element | null;
    for (const record of records) if (record.open && record.layout === 'floating' && target && !record.reader.contains(target)
      && !record.owner.contains(target) && !record.activeFigure?.contains(target)) close(record, false);
  }
  function recordFor(target: Element): Inspector | undefined {
    const figure = figureOf(target), owner = target.closest('[data-av-explorer]') || (figure ? figureOrigin(figure).explorer : null);
    return records.find(record => record.owner === owner || record.reader.contains(target) || figure && record.figures.includes(figure));
  }
  function open(target: Element, trigger?: HTMLElement, takeFocus = true): boolean {
    const record = recordFor(target); if (!record || stopped) return false;
    const figure = figureOf(target);
    if (figure && record.figures.includes(figure)) record.activeFigure = figure;
    else {
      const mark = selectedMark(record);
      record.activeFigure = mark && figureOf(mark) || record.figures.find(visible) || null;
    }
    for (const other of records) if (other !== record && other.open && !other.pinned) close(other, false);
    record.trigger = trigger || opener(record); record.open = true;
    const allowDrawer = takeFocus || record.layout === 'drawer' || record.reader.contains(document.activeElement);
    record.reader.setAttribute('open', ''); place(record, true, allowDrawer); watch(); hooks.contextChanged?.();
    if (record.open && (takeFocus || record.layout === 'drawer')) focusCommand(selected(record)?.querySelector<HTMLElement>('summary') || record.reader);
    const mark = selectedMark(record);
    if (mark) hooks.reveal?.(mark, record.layout === 'floating' ? record.reader.getBoundingClientRect() : null);
    return true;
  }

  for (const reader of Array.from(root.querySelectorAll<HTMLElement>('.av-inspector'))) {
    const explorer = reader.parentElement, owner = explorer?.closest<HTMLElement>('[data-av-explorer]');
    const plot = explorer && Array.from(explorer.children).find(node => node.matches('.av-plot-shell,.av-scatter-scenes')) as HTMLElement | undefined;
    const summary = reader.querySelector<HTMLElement>('summary');
    if (!explorer || !owner || !plot || !summary) continue;
    const dialog = document.createElement('dialog'); if (typeof dialog.showModal !== 'function') continue;
    dialog.className = 'av-focus-dialog av-inspector-dialog'; dialog.setAttribute('aria-label', 'Evidence reader');
    const homeMarker = document.createComment('av-evidence-reader'); explorer.insertBefore(homeMarker, reader);
    const attributes = ['id','tabindex','hidden','open','style','role','aria-label','popover','data-av-inspector-view'].map(name => [name, reader.getAttribute(name)] as const);
    const oldLayout = explorer.getAttribute('data-av-inspector-layout');
    const header = document.createElement('header'); header.className = 'av-inspector-header'; header.setAttribute('data-av-review-ui', '');
    const heading = document.createElement('strong'); heading.textContent = 'Evidence'; header.appendChild(heading);
    const summaryHidden = summary.getAttribute('hidden'); summary.hidden = true;
    reader.insertBefore(header, summary.nextSibling);
    if (!reader.id) { let id: string; do { id = 'av-evidence-reader-' + (++nextInspector); } while (document.getElementById(id)); reader.id = id; }
    reader.setAttribute('tabindex','-1');
    const controls = document.createElement('span'); controls.className = 'av-inspector-actions'; controls.setAttribute('data-av-review-ui', '');
    const pin = document.createElement('button'); pin.type = 'button'; pin.className = 'av-button av-button-quiet'; pin.setAttribute('data-av-inspector-pin', ''); pin.setAttribute('aria-label','Pin evidence beside drawing');
    pin.appendChild(commandIcon(document, 'm8 3 8 0-1 6 4 4v2H5v-2l4-4zM12 15v6'));
    const caption = document.createElement('span'); caption.textContent = 'Pin'; pin.appendChild(caption);
    const dismiss = document.createElement('button'); dismiss.type = 'button'; dismiss.className = 'av-button av-panel-close'; dismiss.setAttribute('aria-label', 'Close evidence reader'); dismiss.textContent = '×';
    controls.append(pin, dismiss); header.appendChild(controls);
    const figures = [...(plot.hasAttribute('data-av-figure') ? [plot] : []), ...Array.from(plot.querySelectorAll<HTMLElement>('[data-av-figure]'))].filter(figure => figureOf(figure) === figure);
    const record: Inspector = {owner, explorer, reader, plot, summary, pin, closeButton: dismiss, dialog, home: homeMarker, figures,
      openers: new Map(), activeFigure: null, trigger: null, canvas: null, open: false, pinned: false, raised: false, layout: 'closed', occlusion: 0, occlusionFigure: null, viewportSize: null, releasePosition: () => {}, undo: []};
    reader.hidden = true; reader.setAttribute('open', ''); reader.setAttribute('role', 'region'); reader.setAttribute('aria-label', 'Evidence reader');
    reader.setAttribute('data-av-inspector-view', 'closed'); explorer.setAttribute('data-av-inspector-layout', 'closed');
    explorer.appendChild(dialog);
    for (const figure of figures) {
      const control = document.createElement('button'); control.type = 'button'; control.className = 'av-button av-inspector-opener';
      control.setAttribute('data-av-inspector-open', ''); control.setAttribute('data-av-review-ui', ''); control.setAttribute('aria-expanded','false');
      control.setAttribute('aria-label', 'Read evidence'); control.appendChild(commandIcon(document, icon));
      control.setAttribute('aria-controls', reader.id); control.setAttribute('aria-haspopup','dialog');
      const label = document.createElement('span'); label.textContent = 'Evidence'; control.appendChild(label);
      const host = figure.querySelector('.av-plot-toolbar') || figure;
      // The command bar restores a moved control to this marker's parent on
      // cleanup. Keep that parent disposable so a later bar cleanup cannot
      // resurrect the inspector's already-removed generated control.
      const holder = document.createElement('span'); holder.setAttribute('data-av-review-ui', ''); holder.style.display = 'contents';
      host.appendChild(holder); holder.appendChild(control);
      const toggle = (event: Event) => { event.preventDefault(); event.stopPropagation(); if (record.open && record.activeFigure === figure) close(record); else open(figure, control); };
      control.addEventListener('click', toggle);
      hooks.command?.(figure, control, {label:'Evidence',labelled:true,priority:12,group:'inspection',icon});
      record.openers.set(figure, control);
      record.undo.push(() => { control.removeEventListener('click', toggle); control.remove(); holder.remove(); });
    }
    const pinClick = (event: Event) => { event.preventDefault(); event.stopPropagation(); record.pinned = !record.pinned; place(record); focusCommand(pin.hidden ? dismiss : pin); };
    const dismissClick = (event: Event) => { event.preventDefault(); event.stopPropagation(); close(record); };
    const summaryClick = (event: Event) => { if (!(event.target as Element)?.closest('button,a,input')) event.preventDefault(); };
    pin.addEventListener('click', pinClick); dismiss.addEventListener('click', dismissClick);
    summary.addEventListener('click', summaryClick); dialog.addEventListener('cancel', dismissClick);
    record.undo.push(() => {
      pin.removeEventListener('click', pinClick); dismiss.removeEventListener('click', dismissClick); summary.removeEventListener('click', summaryClick); dialog.removeEventListener('cancel', dismissClick);
      header.remove(); if (summaryHidden === null) summary.removeAttribute('hidden'); else summary.setAttribute('hidden', summaryHidden);
      for (const [name,value] of attributes) if (value === null) reader.removeAttribute(name); else reader.setAttribute(name,value);
      if (oldLayout === null) explorer.removeAttribute('data-av-inspector-layout'); else explorer.setAttribute('data-av-inspector-layout',oldLayout);
    });
    if (view?.ResizeObserver) {
      const observer = new view.ResizeObserver(schedule); observer.observe(explorer); observer.observe(plot);
      for (const canvas of Array.from(plot.querySelectorAll('.av-plot-scroll,.av-row-plot-layout'))) observer.observe(canvas);
      record.undo.push(() => observer.disconnect());
    }
    records.push(record);
  }
  root.addEventListener('av-layout-invalidated', schedule, true);
  view?.addEventListener('resize', schedule); view?.visualViewport?.addEventListener('resize', schedule);
  return {
    refresh, open,
    dismissOutside(target, keepContained = false) { for (const record of records) if (record.open && !record.reader.contains(target) && !(keepContained && target.contains(record.reader))) close(record, false); },
    suspend(target) {
      const saved = records.filter(record => record.figures.some(figure => target === figure || target.contains(figure)))
        .map(record => ({record, wasOpen: record.open, figure: record.activeFigure, trigger: record.trigger}));
      for (const entry of saved) close(entry.record, false);
      return () => {
        if (stopped) return false;
        let restored = false;
        for (const entry of saved) {
          close(entry.record, false);
          if (!entry.wasOpen || !entry.figure?.isConnected || !visible(entry.figure)) continue;
          const width = entry.figure.querySelector<HTMLElement>('.av-plot-scroll')?.clientWidth || 0;
          const font = parseFloat(view?.getComputedStyle?.(document.documentElement).fontSize || '16') || 16;
          // Returning to a now-narrow report keeps the opener available rather
          // than starting a new modal above the view's restored keyboard focus.
          if (width < 46 * font) continue;
          restored = open(entry.figure, entry.trigger || undefined, false) || restored;
        }
        return restored;
      };
    },
    preview(target) {
      const record = recordFor(target); if (!record || stopped) return;
      const figure = figureOf(target), drawing = figure?.querySelector<HTMLElement>('.av-plot-scroll');
      const font = parseFloat(view?.getComputedStyle?.(document.documentElement).fontSize || '16') || 16;
      if (record.open || drawing && !figure?.hasAttribute('data-av-expanded-figure') && drawing.clientWidth >= 46 * font) open(target, target as HTMLElement, false);
    },
    cleanup() {
      if (stopped) return;
      for (const record of records) close(record, false);
      stopped = true; if (scheduled !== null) view?.cancelAnimationFrame(scheduled);
      root.removeEventListener('av-layout-invalidated', schedule, true); view?.removeEventListener('resize', schedule); view?.visualViewport?.removeEventListener('resize', schedule);
      for (const record of records) { lower(record); home(record); record.home.remove(); record.dialog.remove(); for (const restore of record.undo.reverse()) restore(); }
    },
  };
}
