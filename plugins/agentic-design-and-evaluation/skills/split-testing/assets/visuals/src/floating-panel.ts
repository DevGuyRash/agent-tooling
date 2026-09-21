import { anchoredPanel, visibleViewport } from './overlay-layout';
import { focusCommand } from './command-bar';

export interface FloatingPanel {
  readonly element: HTMLElement;
  readonly body: HTMLElement;
  readonly isOpen: boolean;
  open(focus?: boolean): void;
  close(returnFocus?: boolean): void;
  toggle(): void;
  refresh(): void;
  cleanup(): void;
}
const panels = new WeakMap<Document, Set<FloatingPanel>>();
let nextPanel = 0;
/** A non-modal, viewport-bounded reader panel. The original controls stay in
 * their owner subtree, including inside an expanded figure. Only open panels
 * attach document listeners. Native popover is optional, never a dependency. */
export function attachFloatingPanel(trigger: HTMLElement, host: HTMLElement, title: string): FloatingPanel {
  const document = host.ownerDocument, view = document.defaultView;
  const panel = document.createElement('div');
  panel.className = 'av-floating-panel'; panel.hidden = true;
  panel.setAttribute('data-av-controls', ''); panel.setAttribute('data-av-review-ui', '');
  panel.setAttribute('role', 'dialog'); panel.setAttribute('aria-label', title);
  do { panel.id = `av-reader-panel-${++nextPanel}`; } while (document.getElementById(panel.id));
  const originals = ['aria-haspopup', 'aria-expanded', 'aria-controls'].map(name => [name, trigger.getAttribute(name)] as const);
  trigger.setAttribute('aria-haspopup', 'dialog'); trigger.setAttribute('aria-expanded', 'false'); trigger.setAttribute('aria-controls', panel.id);
  const header = document.createElement('header'); header.className = 'av-floating-header';
  const heading = document.createElement('strong'); heading.textContent = title; header.appendChild(heading);
  const dismiss = document.createElement('button'); dismiss.type = 'button'; dismiss.className = 'av-button av-panel-close'; dismiss.textContent = '×'; dismiss.setAttribute('aria-label', `Close ${title.toLowerCase()}`); header.appendChild(dismiss);
  const body = document.createElement('div'); body.className = 'av-floating-body'; panel.appendChild(header); panel.appendChild(body); host.appendChild(panel);
  let active = false, stopped = false, raised = false, scheduled: number | null = null;
  let native = typeof panel.showPopover === 'function' && typeof panel.hidePopover === 'function';
  if (native) panel.setAttribute('popover', 'manual');
  const pool = panels.get(document) || new Set<FloatingPanel>(); panels.set(document, pool);
  function place(): void {
    scheduled = null;
    if (!active || stopped) return;
    if (!trigger.isConnected || trigger.closest('[hidden]')) { close(false); return; }
    const bounds = visibleViewport(view, 10);
    panel.style.setProperty('max-width', Math.max(0, bounds.right - bounds.left) + 'px');
    // Clamp total panel height before measuring so wrapping is reflected in placement.
    panel.style.setProperty('max-height', Math.max(0, bounds.bottom - bounds.top) + 'px');
    let anchorControl = trigger;
    // A command can move into closed overflow during a resize. Anchor and
    // return to its reachable disclosure rather than an invisible button.
    for (let owner=trigger.parentElement;owner;owner=owner.parentElement)
      if (owner.tagName.toLowerCase()==='details'&&!owner.hasAttribute('open')) anchorControl=owner.querySelector<HTMLElement>('summary')||owner;
    const anchor = anchorControl.getBoundingClientRect(), box = panel.getBoundingClientRect();
    const placed = anchoredPanel(anchor, bounds, box.width || 352, box.height || 320, 6);
    // A trigger near the middle of a short viewport can leave neither half
    // useful. Prefer an overlaid reading panel, never a zero-height sliver.
    const height = placed.maxHeight < 160 ? Math.max(0, bounds.bottom - bounds.top) : placed.maxHeight;
    panel.style.setProperty('max-height', height + 'px');
    panel.style.setProperty('left', Math.max(bounds.left, Math.min(anchor.left, bounds.right - placed.width)) + 'px');
    panel.style.setProperty('top', (placed.maxHeight < 160 ? bounds.top : anchoredPanel(anchor, bounds, placed.width, panel.getBoundingClientRect().height || box.height, 6).top) + 'px');
  }
  function schedule(): void {
    if (!active || stopped || scheduled !== null) return;
    if (view?.requestAnimationFrame) scheduled = view.requestAnimationFrame(place); else place();
  }
  function outside(event: Event): void { const node = event.target as Node; if (!panel.contains(node) && !trigger.contains(node)) close(false); }
  function keydown(event: KeyboardEvent): void {
    if (event.key === 'Escape' && active) { event.preventDefault(); event.stopPropagation(); close(true); }
  }
  function watch(enable: boolean): void {
    const change = enable ? 'addEventListener' : 'removeEventListener';
    document[change]('pointerdown', outside, true); document[change]('focusin', outside, true);
    document[change]('keydown', keydown as EventListener, true); document[change]('scroll', schedule, true);
    view?.[change]('resize', schedule); view?.visualViewport?.[change]('resize', schedule); view?.visualViewport?.[change]('scroll', schedule);
  }
  function open(focus = true): void {
    if (stopped) return;
    for (const other of pool) if (other !== controller) other.close(false);
    if (!active) {
      active = true; panel.hidden = false; panel.setAttribute('data-av-open', '');
      if (native) try { panel.showPopover(); raised = true; } catch { native = false; panel.removeAttribute('popover'); }
      trigger.setAttribute('aria-expanded', 'true'); watch(true);
    }
    place();
    if (focus) (body.querySelector<HTMLElement>('input:not([disabled]),button:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex="0"]') || dismiss).focus({preventScroll: true});
  }
  function close(returnFocus = false): void {
    const wasOpen = active; active = false; watch(false);
    if (scheduled !== null) view?.cancelAnimationFrame(scheduled); scheduled = null;
    if (raised) { raised = false; try { panel.hidePopover(); } catch { /* An ancestor may have closed first. */ } }
    panel.hidden = true; panel.removeAttribute('data-av-open'); trigger.setAttribute('aria-expanded', 'false');
    if (wasOpen && returnFocus && trigger.isConnected) focusCommand(trigger);
  }
  const click = (event: Event) => { event.preventDefault(); event.stopPropagation(); if (active) close(true); else open(); };
  const closeClick = (event: Event) => { event.preventDefault(); event.stopPropagation(); close(true); };
  const toggle = (event: Event) => { if (event.target === panel && (event as ToggleEvent).newState === 'closed' && raised && !panel.matches(':popover-open')) { raised = false; close(false); } };
  trigger.addEventListener('click', click); dismiss.addEventListener('click', closeClick); panel.addEventListener('toggle', toggle);
  // Observer scheduling (not direct writes in its callback) avoids feedback loops.
  const observer = view?.ResizeObserver ? new view.ResizeObserver(schedule) : null; observer?.observe(panel);
  const controller: FloatingPanel = {element: panel, body, get isOpen() {return active;}, open, close, toggle: () => active ? close(true) : open(), refresh: schedule,
    cleanup() { if (stopped) return; close(false); stopped = true; observer?.disconnect(); trigger.removeEventListener('click', click); dismiss.removeEventListener('click', closeClick); panel.removeEventListener('toggle', toggle); panel.remove(); pool.delete(controller); if (!pool.size) panels.delete(document); for (const [name,value] of originals) if (value === null) trigger.removeAttribute(name); else trigger.setAttribute(name,value); }
  };
  pool.add(controller); return controller;
}
