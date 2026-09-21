import { anchoredPanel, visibleViewport } from "./overlay-layout";
/** Keep report utilities in their owning DOM/theme, but outside scroll clipping.
 * No duplicate settings or notebook controls are created. Native details remain
 * the fallback when popovers are unavailable. */
export function attachUtilityPanels(root: HTMLElement): () => void {
  const document = root.ownerDocument, view = document.defaultView;
  const restore: (() => void)[] = [];
  let stopped = false, scheduled: number | null = null;
  const entries: { details: HTMLDetailsElement; panel: HTMLElement; place: () => void; close: () => void }[] = [];
  function listen(target: EventTarget, type: string, fn: EventListener, capture = false): void {
    target.addEventListener(type, fn, capture);
    restore.push(() => target.removeEventListener(type, fn, capture));
  }
  const menus = [...(root.matches('[data-av-settings],[data-av-notebook]') ? [root] : []), ...Array.from(root.querySelectorAll<HTMLElement>('[data-av-settings],[data-av-notebook]'))];
  for (const element of menus) {
    const details = element as HTMLDetailsElement;
    const panel = details.querySelector<HTMLElement>('.av-settings-panel,.av-notebook-popover');
    const summary = details.querySelector<HTMLElement>('summary');
    if (!panel || !summary || typeof panel.showPopover !== 'function' || typeof panel.hidePopover !== 'function') continue;
    const saved = ['popover', 'style', 'data-av-utility-layer'].map(name => [name, panel.getAttribute(name)] as const);
    const expanded = summary.getAttribute('aria-expanded');
    let visible = false;
    panel.setAttribute('popover', 'manual'); panel.setAttribute('data-av-utility-layer', '');
    function hide(): void {
      if (visible) { try { panel!.hidePopover(); } catch { /* Already closed by its native context. */ } }
      visible = false;
      summary!.setAttribute('aria-expanded', 'false');
    }
    function place(): void {
      if (stopped) return;
      if (!details.open || !details.isConnected || details.closest('[hidden]')) { hide(); return; }
      if (!visible) {
        try { panel!.showPopover(); visible = true; }
        catch { return; }
      }
      summary!.setAttribute('aria-expanded', 'true');
      const bounds = visibleViewport(view);
      const anchor = summary!.getBoundingClientRect();
      if(details.hasAttribute('data-av-notebook')) {
        const width=Math.min(620,Math.max(0,bounds.right-bounds.left)),height=Math.max(0,bounds.bottom-bounds.top);
        panel!.style.setProperty('width',width+'px');panel!.style.setProperty('height',Math.min(800,height)+'px');panel!.style.setProperty('max-height',height+'px');
        panel!.style.setProperty('left',Math.max(bounds.left,bounds.right-width)+'px');panel!.style.setProperty('top',bounds.top+'px');return;
      }

      panel!.style.setProperty('max-width', Math.max(0, bounds.right - bounds.left) + 'px');
      const box = panel!.getBoundingClientRect();
      const placed = anchoredPanel(anchor, bounds, box.width, Math.max(box.height, panel!.scrollHeight));
      panel!.style.setProperty('max-height', placed.maxHeight + 'px');
      panel!.style.setProperty('left', placed.left + 'px');
      // Measure after the height constraint: a scrollbar or text reflow can
      // change a panel's final size, especially immediately after orientation.
      const actualHeight = panel!.getBoundingClientRect().height;
      panel!.style.setProperty('top', anchoredPanel(anchor, bounds, box.width, actualHeight).top + 'px');
    }
    entries.push({ details, panel, place, close: hide });
    listen(details, 'toggle', ((event: Event) => { if (event.target === details) place(); }) as EventListener);
    listen(details, 'focusout', ((event: FocusEvent) => {
      if (details.open && event.relatedTarget && !details.contains(event.relatedTarget as Node)) { details.open = false; hide(); }
    }) as EventListener);
    listen(panel, 'toggle', ((event: Event) => {
      if (event.target === panel && visible && (event as ToggleEvent).newState === 'closed' && !panel.matches(':popover-open')) { visible = false; details.open = false; summary.setAttribute('aria-expanded', 'false'); }
    }) as EventListener);
    // Escape closes this panel, not an expanded figure or another report.
    listen(details, 'keydown', ((event: KeyboardEvent) => {
      if (event.key !== 'Escape' || !details.open || event.defaultPrevented) return;
      event.preventDefault(); event.stopPropagation(); details.open = false; hide(); summary.focus({ preventScroll: true });
    }) as EventListener);
    if (view?.ResizeObserver) {
      const observer = new view.ResizeObserver(() => { if (details.open) schedule(); });
      observer.observe(panel); restore.push(() => observer.disconnect());
    }
    restore.push(() => {
      hide();
      for (const [name, value] of saved) { if (value === null) panel.removeAttribute(name); else panel.setAttribute(name, value); }
      if (expanded === null) summary.removeAttribute('aria-expanded'); else summary.setAttribute('aria-expanded', expanded);
    });
    place();
  }
  function schedule(): void {
    if (stopped || scheduled !== null || !entries.some(entry => entry.details.open)) return;
    if (!view?.requestAnimationFrame) { for (const entry of entries) entry.place(); return; }
    scheduled = view.requestAnimationFrame(() => { scheduled = null; for (const entry of entries) entry.place(); });
  }
  if (entries.length) {
    listen(document, 'scroll', schedule, true);
    listen(document, 'pointerdown', ((event: Event) => {
      const target = event.target as Node | null;
      for (const entry of entries) if (entry.details.open && target && !entry.details.contains(target)) { entry.details.open = false; entry.close(); }
    }) as EventListener, true);
    if (view) listen(view, 'resize', schedule);
    if (view?.visualViewport) { listen(view.visualViewport, 'resize', schedule); listen(view.visualViewport, 'scroll', schedule); }
  }
  return () => {
    if (stopped) return;
    stopped = true;
    if (scheduled !== null) view?.cancelAnimationFrame(scheduled);
    for (const undo of restore.reverse()) undo();
    entries.length = 0;
  };
}
