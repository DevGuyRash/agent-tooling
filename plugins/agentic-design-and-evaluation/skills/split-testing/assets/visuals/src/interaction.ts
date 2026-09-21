import { attachComparisonReader, ComparisonReader } from './comparison-reader';
import { notifyReportReady, notifyReportInitializing } from './startup';
import { attachReportSearch, ReportSearch } from './report-search';
import { attachInspectors, InspectorController } from './inspectors';
import { attachItemSelection, ItemSelectionController, selectedFigureItems } from './item-selection';
import { attachUtilityPanels } from "./utility-panels";
import { attachNotifications, NotificationController } from './notifications';
import { attachCommandBar, CommandBar } from './command-bar';
import { registerReviewPlaceholder } from './review-targets';
import { browserTextMeasure, estimateTextWidth } from './text-layout';
/** Optional, presentation-only browser interactions. Renderer HTML remains the fallback. */

import { attachLayoutRefinement } from "./layout-refinement";
import { attachFigureTools, FigureTools } from "./figure-tools";
import { attachMermaid, DiagramController } from "./mermaid";
import { figureOf, figureTitle, figureOrigin, figureContext } from "./figures";
import { attachPlots, PlotSnapshot } from "./plot-navigation";
import { attachPreferences } from "./preferences";
import { attachNotebooks, NotebookController, ReaderPlace } from "./notebook";

export interface EnhancementCleanup { (): void; whenReady(): Promise<void>; whenIdle(): Promise<void> }
const enhancedRoots = new WeakMap<HTMLElement, EnhancementCleanup>();

interface WorkspaceState {
  element: HTMLElement;
  panels: HTMLElement[];
  navigation: HTMLElement[];
  search: HTMLInputElement | null;
  status: HTMLElement;
  reset: HTMLButtonElement | null;
  showAll: HTMLElement[];
  showSingle: HTMLElement[];
  mode: "single" | "all";
  selected: string | null;
  journey: string | null;
  journeys: Map<string, { element: HTMLElement; steps: string[] }>;
  query: string;
  results: HTMLElement;
  finder?: ReportSearch;
}

interface FocusState {
  kind: "section" | "figure";
  owner: HTMLElement;
  plotSnapshot: PlotSnapshot;
  suspension: { element: HTMLElement; hidden: string | null }[];
  card: HTMLElement;
  marker: HTMLElement;
  releaseReviewPosition: () => void;
  scroll: { element: HTMLElement; top: number; left: number }[];
  viewport: { x: number; y: number };
  trigger: HTMLElement;
  previouslyFocused: boolean;
  previousAttribute: string | null;
  expansionControls: { element: HTMLElement; hidden: string | null }[];
  toolMoves: { element: HTMLElement; marker: Comment }[];
  initiallyClosed: boolean;
  previousTemporaryAttribute: string | null;
}

/**
 * Enhance a report, one workspace, or a frame with native browser controls.
 * Repeated calls for the same root return the same idempotent cleanup function.
 * Cleanup restores managed visibility and removes generated controls/listeners;
 * no supplied evidence is cloned, rewritten, or discarded.
 */
export function enhanceVisuals(root: HTMLElement): EnhancementCleanup {
  const shells = [...(root.matches(".av-workspace") ? [root] : []), ...Array.from(root.querySelectorAll<HTMLElement>(".av-workspace"))];
  if (shells.some(shell => shell.parentElement?.closest(".av-workspace"))) throw new TypeError("A report has one workspace shell. Compose nested charts, sections, lanes or reportSurface fragments inside it; embed independent reports as siblings.");
  const existing = enhancedRoots.get(root);
  if (existing) return existing;

  for (let ancestor = root.parentElement; ancestor; ancestor = ancestor.parentElement) {
    if (enhancedRoots.has(ancestor)) throw new TypeError("This content already belongs to an enhanced report. Use its existing controller, or clean it up before enhancing a different root.");
  }
  for (const descendant of Array.from(root.querySelectorAll<HTMLElement>("[data-av-enhanced]"))) {
    if (enhancedRoots.has(descendant)) throw new TypeError("This root contains an independently enhanced report. Enhance sibling reports separately, or clean them up first.");
  }
  if (shells.length) notifyReportInitializing(root.ownerDocument);
  const refinementCleanup = attachLayoutRefinement(root);
  let diagrams: DiagramController | null = null;
  let appearanceReady = false;
  let itemSelection: ItemSelectionController | null = null, inspectors: InspectorController | null = null;
  let notifications:NotificationController|null=null;
  const preferences = attachPreferences(root, () => { if (appearanceReady) void diagrams?.refresh(); notifications?.refresh(); });
  const document = root.ownerDocument;
  notifications=attachNotifications(root,(target,source)=>preferences.snapshot(target,source));
  const sectionBars:CommandBar[]=[];
  const sectionBarHosts = new WeakMap<CommandBar, HTMLElement>();
  const window = document.defaultView;
  const undo: Array<() => void> = [];
  const savedAttributes = new WeakMap<Element, Set<string>>();
  const savedClasses = new WeakMap<Element, Set<string>>();
  const savedText = new WeakSet<Element>();
  const workspaces: WorkspaceState[] = [];
  let notebooks: NotebookController | null = null;
  const frameLocations = new WeakMap<Element, { state: WorkspaceState; panel: HTMLElement }>();
  let figures: FigureTools;
  try { figures = attachFigureTools(root, (figure, trigger) => inspectFrame(figure, trigger, "figure"), message => notifications?.show(message), () => notifications?.refresh()); }
  catch (error) { notifications.cleanup(); preferences.cleanup(); refinementCleanup(); throw error; }
  const plots = attachPlots(root);
  figures.dock();
  diagrams = attachMermaid(root, figure => { plots.refresh(figure); itemSelection?.refresh(figure); inspectors?.refresh(); });
  const readers=new Map<HTMLElement,ComparisonReader>();
  const collections=new Map<HTMLElement,HTMLElement[]>();
  const collectionOwners=new WeakMap<HTMLElement,HTMLElement>();
  const comparisonSlots = new Map<HTMLElement, Array<Array<{ object: HTMLElement; marker: Comment }>>>();
  const animations = new Set<Animation>();
  const currentAnimation = new WeakMap<Element, Animation>();
  const reducedMotion = window?.matchMedia?.("(prefers-reduced-motion: reduce)");
  let cleaned = false;
  let dialog: HTMLDialogElement | null = null;
  let dialogBody: HTMLElement | null = null;
  let dialogTitle: HTMLElement | null = null;
  let dialogContext: HTMLElement | null = null;
  let dialogTools: HTMLElement | null = null;
  let dialogClose: HTMLButtonElement | null = null;
  let focused: FocusState | null = null;
  const focusStack: FocusState[] = [];

  function attribute(element: Element, name: string, value: string | null): void {
    let saved = savedAttributes.get(element);
    if (!saved) { saved = new Set(); savedAttributes.set(element, saved); }
    if (!saved.has(name)) {
      saved.add(name);
      const original = element.getAttribute(name);
      undo.push(() => original === null ? element.removeAttribute(name) : element.setAttribute(name, original));
    }
    if (value === null) element.removeAttribute(name);
    else element.setAttribute(name, value);
  }

  function stateClass(element: Element, name: string, enabled: boolean): void {
    let saved = savedClasses.get(element);
    if (!saved) { saved = new Set(); savedClasses.set(element, saved); }
    if (!saved.has(name)) {
      saved.add(name);
      const original = element.classList.contains(name);
      undo.push(() => element.classList.toggle(name, original));
    }
    element.classList.toggle(name, enabled);
  }

  function hidden(element: Element, value: boolean): void { attribute(element, "hidden", value ? "" : null); }
  function message(element: HTMLElement, value: string): void {
    if (!savedText.has(element)) {
      savedText.add(element);
      const original = Array.from(element.childNodes);
      undo.push(() => { element.textContent = ""; for (const child of original) element.appendChild(child); });
    }
    element.textContent = value;
  }
  function listen(target: EventTarget, type: string, handler: EventListener, capture = false): void {
    target.addEventListener(type, handler, capture);
    undo.push(() => target.removeEventListener(type, handler, capture));
  }
  function generated<T extends HTMLElement>(element: T, parent: Element): T {
    parent.appendChild(element);
    undo.push(() => element.remove());
    return element;
  }
  function button(label: string): HTMLButtonElement {
    const element = document.createElement("button");
    element.type = "button";
    element.className = "av-button";
    element.textContent = label;
    return element;
  }
  function output(parent: Element, className: string): HTMLElement {
    const element = document.createElement("p");
    element.className = className;
    element.setAttribute("role", "status");
    element.setAttribute("aria-live", "polite");
    return generated(element, parent);
  }
  function elements<T extends Element = HTMLElement>(within: Element, selector: string): T[] {
    return Array.from(within.querySelectorAll<T>(selector));
  }
  function inclusive<T extends Element = HTMLElement>(selector: string): T[] {
    return [...(root.matches(selector) ? [root as unknown as T] : []), ...elements<T>(root, selector)];
  }
  function inScope<T extends Element = HTMLElement>(within: Element, selector: string, boundary: string): T[] {
    return elements<T>(within, selector).filter(element => element.closest(boundary) === within);
  }
  function targetOf(event: Event): Element | null {
    const target = event.target as Node | null;
    return target?.nodeType === 1 ? target as Element : target?.parentElement || null;
  }
  function contains(element: Element): boolean { return root === element || root.contains(element) || !!dialog?.contains(element) || !!focused?.card.contains(element) || !!focused?.toolMoves.some(move => move.element.contains(element)); }
  function focus(element: HTMLElement): void {
    if (!element.matches("a[href],button,input,select,textarea,summary,[tabindex]")) attribute(element, "tabindex", "-1");
    element.focus({ preventScroll: true });
  }
  function scroll(element: Element): void { element.scrollIntoView?.({ block: "nearest", inline: "nearest", behavior: "auto" }); }
  function motion(element: Element): void {
    if (!reducedMotion || reducedMotion.matches || typeof element.animate !== "function") return;
    currentAnimation.get(element)?.cancel();
    const animation = element.animate([{ opacity: 0.7, transform: "translateY(4px)" }, { opacity: 1, transform: "translateY(0)" }], { duration: 140, easing: "ease-out" });
    currentAnimation.set(element, animation);
    animations.add(animation);
    animation.finished.then(() => animations.delete(animation), () => animations.delete(animation));
  }
  function cancelMotion(): void { for (const animation of animations) animation.cancel(); animations.clear(); }
  if (reducedMotion) listen(reducedMotion, "change", (() => { if (reducedMotion.matches) cancelMotion(); }) as EventListener);

  function ownCardParts(card: Element, selector: string): HTMLElement[] {
    const parts = inScope(card, selector, ".av-card");
    const state = [focused, ...focusStack].find(state => state?.card === card);
    if (state) for (const move of state.toolMoves) {
      if (move.element.matches(selector)) parts.push(move.element);
      parts.push(...elements<HTMLElement>(move.element, selector));
    }
    return [...new Set(parts)];
  }
  function dataMode(card: HTMLElement, mode: "visual" | "data", announce = true): void {
    for (const part of ownCardParts(card, '[data-av-content-view="visual"]')) hidden(part, mode === "data");
    for (const part of ownCardParts(card, '[data-av-content-view="data"]')) {
      hidden(part, false);
      if (mode === "data" && part.tagName.toLowerCase() === "details") attribute(part, "open", "");
    }
    for (const control of ownCardParts(card, "[data-av-view-toggle]")) {
      if (control.hasAttribute("data-av-view-switch")) {
        attribute(control, "data-av-view-toggle", mode === "data" ? "visual" : "data");
        attribute(control, "aria-pressed", String(mode === "data"));
        attribute(control, "title", mode === "data" ? "Show chart and data" : "Show data only");
      } else attribute(control, "aria-pressed", String(control.getAttribute("data-av-view-toggle") === mode));
    }
    attribute(card, "data-av-display", mode);
    for (const controls of ownCardParts(card, ".av-plot-toolbar")) hidden(controls, mode === "data");
    const status = ownCardParts(card, "[data-av-view-status]")[0];
    if (announce && status) message(status, mode === "data" ? "Data only. Exact values, missing entries, annotations and evidence remain available." : "Visual and data views. Exact values, missing entries, annotations and evidence remain available.");
    plots.refresh(card);
    if (announce) motion(card);
  }

  function coordinateScope(explorer: HTMLElement, choice: string): void {
    for (const view of inScope(explorer, "[data-av-coordinate-scope]", "[data-av-explorer]")) hidden(view, view.getAttribute("data-av-coordinate-scope") !== choice);
    for (const control of inScope(explorer, "[data-av-scope-choice]", "[data-av-explorer]")) attribute(control, "aria-pressed", String(control.getAttribute("data-av-scope-choice") === choice));
    plots.refresh(explorer);
  }
  function openDisclosures(target: Element): void {
    for (let ancestor: Element | null = target; ancestor && contains(ancestor); ancestor = ancestor.parentElement) {
      if (ancestor.tagName.toLowerCase() === "details") attribute(ancestor, "open", "");
      if (ancestor.hasAttribute("data-av-coordinate-scope")) { const explorer = ancestor.closest<HTMLElement>("[data-av-explorer]"); if (explorer) coordinateScope(explorer, ancestor.getAttribute("data-av-coordinate-scope")!); }
      if (ancestor.matches('.av-card[data-av-display="data"]') && target.closest('[data-av-content-view="visual"]')) dataMode(ancestor as HTMLElement, "visual", false);
    }
    preferences.reveal(target);
  }

  function titleOf(element: Element): string {
    const heading = element.matches(".av-card") ? element.querySelector(".av-card-title,h1,h2,h3,h4") : null;
    return (heading?.textContent || element.querySelector("summary,h1,h2,h3,h4")?.textContent || element.getAttribute("aria-label") || "Evidence").trim();
  }

  function panelName(panel: Element): string { return (panel.querySelector("h1,h2,h3")?.textContent || panel.getAttribute("data-av-panel") || "View").trim(); }
  function renderSearch(state: WorkspaceState): void { state.finder?.update(state.query); }
  function placeOf(state: WorkspaceState): ReaderPlace { return { viewId: state.selected, mode: state.mode, journeyId: state.journey }; }
  function recordPlace(state: WorkspaceState): void { notebooks?.recordPlace(state.element, placeOf(state)); }
  function renderWorkspace(state: WorkspaceState, animate = false): void {
    attribute(state.element, "data-av-reader-mode", state.mode);
    for (const panel of state.panels) {
      const visible = state.mode === "all" || panel.getAttribute("data-av-panel") === state.selected;
      hidden(panel, !visible);
      if (visible && animate) motion(panel);
    }
    for (const context of inScope(state.element, "[data-av-view-question]", ".av-workspace")) hidden(context, state.mode === "all" || state.panels.length < 2 || state.selected === state.panels[0]?.getAttribute("data-av-panel"));
    for (const link of state.navigation) {
      const selected = state.mode === "single" && link.getAttribute("data-av-view") === state.selected;
      attribute(link, "aria-current", selected ? "page" : null); stateClass(link, "av-selected", selected);
    }
    for (const show of state.showAll) attribute(show, "aria-pressed", String(state.mode === "all"));
    for (const single of state.showSingle) attribute(single, "aria-pressed", String(state.mode === "single"));
    if (state.reset) hidden(state.reset, !state.query);
    const total = state.panels.length;
    if (state.mode === "all") message(state.status, `Full report. All ${total} sections are available.`);
    else {
      const selected = state.panels.find(panel => panel.getAttribute("data-av-panel") === state.selected);
      message(state.status, `Reading “${selected ? panelName(selected) : "Section"}”. ${total} sections are available in this report.`);
    }
    const count = inScope(state.element, "[data-av-view-count]", ".av-workspace")[0];
    if (count) message(count, state.mode === "all" ? `${total} sections` : `${Math.max(1, state.panels.findIndex(panel => panel.getAttribute("data-av-panel") === state.selected) + 1)} / ${total}`);
    for (const [id, route] of state.journeys) {
      hidden(route.element, state.journey !== id || state.mode === "all");
      const index = route.steps.indexOf(state.selected || "");
      const position = route.element.querySelector<HTMLElement>("[data-av-path-position]");
      if (position) message(position, `${index + 1} of ${route.steps.length}`);
      for (const control of elements(route.element, "[data-av-path-step]")) {
        const next = control.getAttribute("data-av-path-step") !== "-1";
        attribute(control, "disabled", (next ? index >= route.steps.length - 1 : index <= 0) ? "" : null);
      }
    }
    preferences.refresh(state.panels.find(panel => panel.getAttribute("data-av-panel") === state.selected));
    plots.refresh(state.element);
    renderSearch(state);
  }

  function changeReadingMode(state: WorkspaceState, mode: "single" | "all"): void {
    clearSearch(state);
    let panel = state.panels.find(panel => panel.getAttribute('data-av-panel') === state.selected) || state.panels[0];
    if (state.mode === 'all' && window) {
      const bar = state.element.querySelector('.av-workspace-bar')?.getBoundingClientRect();
      const line = Math.max(0, bar?.bottom || 0) + 24;
      // A full-report reader may have scrolled away from the last clicked view.
      const candidates = state.panels.map(panel => ({ panel, box: panel.getBoundingClientRect() }));
      panel = candidates.find(({ box }) => box.top <= line && box.bottom > line)?.panel
        || candidates.filter(({ box }) => box.bottom > line).sort((a, b) => a.box.top - b.box.top)[0]?.panel || panel;
    }
    const top = panel?.getBoundingClientRect().top;
    if (panel) state.selected = panel.getAttribute('data-av-panel');
    state.mode = mode; renderWorkspace(state); recordPlace(state);
    if (!panel || top === undefined || !Number.isFinite(top)) return;
    // Insert/remove preceding views without moving the passage being read.
    // Scrollable embeds receive the correction before the document viewport.
    for (let ancestor = panel.parentElement; ancestor && ancestor !== document.body; ancestor = ancestor.parentElement) {
      if (ancestor.scrollHeight > ancestor.clientHeight && /auto|scroll/.test(window?.getComputedStyle?.(ancestor).overflowY || '')) ancestor.scrollTop += panel.getBoundingClientRect().top - top;
    }
    const delta = panel.getBoundingClientRect().top - top;
    if (Number.isFinite(delta) && Math.abs(delta) > 1) window?.scrollTo?.(window.scrollX, window.scrollY + delta);
  }

  function clearSearch(state: WorkspaceState): void {
    state.query = "";
    if (state.search) state.search.value = "";
    state.finder?.update("");
  }
  function workspaceFor(element: Element): WorkspaceState | undefined {
    const frame = element.closest(".av-card");
    return (frame ? frameLocations.get(frame)?.state : undefined) || workspaces.find(state => state.element === element.closest(".av-workspace"));
  }
  function reveal(target: Element, takeFocus: boolean, selectView = true): void {
    // A fragment outside the active dialog must first restore its live frame.
    if (focused && !focused.card.contains(target)) closeAllFocus(false);
    const state = workspaceFor(target);
    const frame = target.closest(".av-card");
    const panel = target.closest<HTMLElement>("[data-av-panel]") || (frame ? frameLocations.get(frame)?.panel : undefined);
    if (state) clearSearch(state);
    if (state && panel && state.panels.includes(panel)) {
      state.selected = panel.getAttribute("data-av-panel");
      if (selectView) state.mode = "single";
      if (state.journey && !state.journeys.get(state.journey)?.steps.includes(state.selected || "")) state.journey = null;
      renderWorkspace(state);
      recordPlace(state);
    } else if (state) renderWorkspace(state);
    const collectionObject=target.closest<HTMLElement>("[data-av-object]");
    if(collectionObject&&collectionOwners.has(collectionObject)){const reader=readers.get(collectionOwners.get(collectionObject)!);if(reader)reader.reveal(collectionObject.getAttribute('data-av-object')!);else{const explorer=collectionObject.closest<HTMLElement>('[data-av-explorer]');if(explorer)endComparison(explorer);}}
    openDisclosures(target);
    const object = target.closest<HTMLElement>("[data-av-object]");
    const explorer = object?.closest<HTMLElement>("[data-av-explorer]");
    if (object && explorer) synchronizeObject(explorer, object.getAttribute("data-av-object") || "");
    if (takeFocus) {
      const focusTarget = target.tagName.toLowerCase() === "details" ? target.querySelector<HTMLElement>("summary") || target as HTMLElement : target as HTMLElement;
      focus(focusTarget);
      scroll(target);
    }
  }
  function fragment(href: string | null, localOnly = true): Element | null {
    if (!href || !href.startsWith("#") || href.length === 1) return null;
    let id: string;
    try { id = decodeURIComponent(href.slice(1)); } catch { return null; }
    const target = document.getElementById(id);
    return target && (!localOnly || contains(target)) ? target : null;
  }
  function hashChanged(): void {
    const target = fragment(window?.location.hash || "");
    if (target) reveal(target, true);
  }

  function restoreFocus(restoreKeyboardFocus: boolean): void {
    const previous = focused;
    focused = null;
    if (!previous) return;
    if (previous.kind === "figure") { previous.card.removeAttribute('data-av-expanded-figure'); previous.card.removeAttribute('data-av-fit-width'); previous.card.removeAttribute('data-av-fit-height'); }
    for (const move of previous.toolMoves) if (move.marker.parentNode) move.marker.parentNode.replaceChild(move.element, move.marker);
    if (previous.initiallyClosed) {
      previous.card.removeAttribute("open");
      if (previous.previousTemporaryAttribute === null) previous.card.removeAttribute("data-av-inspection-open");
      else previous.card.setAttribute("data-av-inspection-open", previous.previousTemporaryAttribute);
    }
    if (previous.marker.parentNode) previous.marker.parentNode.replaceChild(previous.card, previous.marker);
    else if (!root.contains(previous.card) && root !== previous.card) root.appendChild(previous.card);
    previous.releaseReviewPosition();
    plots.refresh(previous.card); plots.restore(previous.plotSnapshot);
    previous.card.classList.toggle("av-focused", previous.previouslyFocused);
    if (previous.previousAttribute === null) previous.card.removeAttribute("data-av-focused");
    else previous.card.setAttribute("data-av-focused", previous.previousAttribute);
    for (const control of previous.expansionControls) {
      if (control.hidden === null) control.element.removeAttribute("hidden"); else control.element.setAttribute("hidden", control.hidden);
    }
    preferences.refresh(previous.card);figures.refresh();for(const bar of sectionBars)bar.refresh();
    attribute(previous.trigger, "aria-expanded", "false");
    focused = focusStack.pop() || null;
    if (focused) {
      for (const state of focused.suspension) { if(state.hidden===null)state.element.removeAttribute('hidden');else state.element.setAttribute('hidden',state.hidden); }
      focused.suspension=[];
      if(dialogTitle){dialogTitle.textContent=focused.kind==='figure'?figureTitle(focused.card):titleOf(focused.card);dialog?.setAttribute('aria-label',`Expanded view: ${dialogTitle.textContent}`);}if(dialogClose){dialogClose.textContent=focusStack.length?'Back':'Close';dialogClose.setAttribute('aria-label',focusStack.length?'Back to previous expanded view':'Close expanded view');}
      showFigureContext(focused);
      dialog?.setAttribute('data-av-viewer-kind',focused.kind); preferences.mirror(dialog!,focused.owner); updateFigureBounds(); plots.refresh(focused.card);
    } else dialog?.removeAttribute('data-av-viewer-kind');
    if (restoreKeyboardFocus && previous.trigger.isConnected) {
      let destination = previous.trigger;
      for (let ancestor = previous.trigger.parentElement; ancestor; ancestor = ancestor.parentElement) {
        if (ancestor.tagName.toLowerCase() === "details" && !ancestor.hasAttribute("open")) destination = ancestor.querySelector<HTMLElement>("summary") || ancestor;
      }
      focus(destination);
      for (const saved of previous.scroll) if (saved.element.isConnected) { saved.element.scrollTop = saved.top; saved.element.scrollLeft = saved.left; }
      window?.scrollTo?.(previous.viewport.x, previous.viewport.y);
    }
  }
  function closeFocus(restoreKeyboardFocus = true): void {
    // Restore synchronously; the native close event can be delivered later.
    restoreFocus(restoreKeyboardFocus);
    if (!focused && dialog?.open) dialog.close();
    notifications?.refresh();
  }
  function closeAllFocus(restoreKeyboardFocus = true): void { while(focused) closeFocus(restoreKeyboardFocus); }
  function showFigureContext(state:FocusState|null):void {
    if(!dialogContext)return;dialogContext.replaceChildren();dialogContext.parentElement!.hidden=state?.kind!=='figure';if(state?.kind!=='figure')return;
    for(const source of figureContext(state.card)){const copy=source.cloneNode(true) as HTMLElement;copy.removeAttribute('id');for(const node of Array.from(copy.querySelectorAll('[id]')))node.removeAttribute('id');dialogContext.appendChild(copy);}
  }
  function updateFigureBounds(): void {
    if(focused?.kind!=='figure'||!dialogBody)return;
    const width=dialogBody.clientWidth,height=dialogBody.clientHeight;
    if(width>0)focused.card.setAttribute('data-av-fit-width',String(width));
    if(height>0)focused.card.setAttribute('data-av-fit-height',String(height));
  }
  function inspectFrame(card: HTMLElement, trigger: HTMLElement, kind: "section" | "figure" = "section"): void {
    if (focused?.card === card) { closeFocus(); return; }
    const nested = !!focused?.card.contains(card);
    if (!nested) closeAllFocus(false);
    if (!dialog) {
      const created = document.createElement("dialog");
      created.className = "av-focus-dialog av-enhanced";
      created.setAttribute("data-av-enhanced", "true");
      if (typeof created.showModal !== "function") { reveal(card, true); return; }
      dialog = generated(created, root.matches(".av-card,[data-av-figure]") ? document.body : root);
      const header = document.createElement("div");
      header.className = "av-dialog-header av-focus-dialog__toolbar";
      dialogTitle = document.createElement("p");
      dialogTitle.className = "av-dialog-title";
      header.appendChild(dialogTitle);
      dialogTools = document.createElement("div"); dialogTools.className = "av-dialog-actions"; header.appendChild(dialogTools);
      dialogClose = button("Close");
      dialogClose.setAttribute("aria-label", "Close expanded view");
      dialogClose.setAttribute("data-av-close-focus", "");
      header.appendChild(dialogClose);
      const contextDisclosure=document.createElement('details');contextDisclosure.className='av-dialog-context';const contextLabel=document.createElement('summary');contextLabel.textContent='Context and sources';contextDisclosure.appendChild(contextLabel);dialogContext=document.createElement('div');dialogContext.className='av-dialog-context-body';contextDisclosure.appendChild(dialogContext);header.appendChild(contextDisclosure);
      dialog.appendChild(header);
      dialogBody = document.createElement("div");
      dialogBody.className = "av-dialog-body";
      dialog.appendChild(dialogBody);
      if(window?.ResizeObserver){const observer=new window.ResizeObserver(()=>{updateFigureBounds();if(focused?.kind==='figure')plots.refresh(focused.card);});observer.observe(dialogBody);undo.push(()=>observer.disconnect());}
      listen(dialog, "close", (() => { if (!dialog?.open) closeAllFocus(true); }) as EventListener);
      listen(dialog, "cancel", ((event: Event) => { event.preventDefault(); closeFocus(); }) as EventListener);
      if (root.matches(".av-card,[data-av-figure]")) {
        // A focused child can leave the enhanced root. Forward its events while
        // avoiding a second dispatch when the root itself is inside the dialog.
        for (const [type, handler, capture] of [
          ["click", click, false], ["keydown", keydown, false],
          ["change", change, false], ["input", input, false], ["toggle", disclosureToggle, true],
        ] as const) listen(dialog, type, ((event: Event) => {
          const target = targetOf(event);
          if (target && !root.contains(target)) (handler as EventListener)(event);
        }) as EventListener, capture);
      }
    }
    if (!card.parentNode || !dialogBody || !dialogTitle || !dialogTools) return;
    const owner = (kind === 'figure' ? card.closest<HTMLElement>('.av-card') : card) || root;
    const location = frameLocations.get(owner);
    if (location) {
      location.state.selected = location.panel.getAttribute("data-av-panel");
      if (location.state.journey && !location.state.journeys.get(location.state.journey)?.steps.includes(location.state.selected || "")) location.state.journey = null;
      recordPlace(location.state);
    }
    notebooks?.recordInspection(card);
    const marker = document.createElement("div");
    marker.className = card.className + " av-focus-placeholder";
    marker.setAttribute("aria-hidden", "true");
    marker.style.height = `${Math.max(0, card.getBoundingClientRect().height || 0)}px`;
    marker.style.visibility = "hidden";
    const scrollState: FocusState["scroll"] = [];
    for (let parent = card.parentElement; parent; parent = parent.parentElement) scrollState.push({ element: parent, top: parent.scrollTop || 0, left: parent.scrollLeft || 0 });
    const viewport = { x: window?.scrollX || 0, y: window?.scrollY || 0 };
    card.parentNode.insertBefore(marker, card);
    const expansionControls = ownCardParts(card, "[data-av-focus]").map(element => ({ element, hidden: element.getAttribute("hidden") }));
    const savedPlotSnapshot = plots.snapshot(card);
    const releaseReviewPosition=registerReviewPlaceholder(marker,card);
    if(nested && focused){
      focused.suspension=[{element:focused.card,hidden:focused.card.getAttribute('hidden')},...focused.toolMoves.map(move=>({element:move.element,hidden:move.element.getAttribute('hidden')}))];
      for(const state of focused.suspension)state.element.hidden=true;
      focusStack.push(focused);
    }
    focused = { kind, owner, releaseReviewPosition, plotSnapshot: savedPlotSnapshot, suspension: [], card, marker, scroll: scrollState, viewport, trigger, previouslyFocused: card.classList.contains("av-focused"), previousAttribute: card.getAttribute("data-av-focused"), expansionControls, toolMoves: [], initiallyClosed: card.matches("details") && !card.hasAttribute("open"), previousTemporaryAttribute: card.getAttribute("data-av-inspection-open") };
    for (const tools of kind === 'figure' ? [figures.toolbar(card)].filter((element): element is HTMLElement => !!element) : ownCardParts(card, ".av-frame-tools")) {
      const place = document.createComment("av-frame-tools"); tools.parentNode?.insertBefore(place, tools);
      focused.toolMoves.push({ element: tools, marker: place }); dialogTools.appendChild(tools);
    }
    for (const control of expansionControls) hidden(control.element, true);
    if (focused.initiallyClosed) { attribute(card, "data-av-inspection-open", ""); card.setAttribute("open", ""); }
    dialogBody.appendChild(card);
    card.classList.add("av-focused");
    card.setAttribute("data-av-focused", "true");
    if(kind==='figure')card.setAttribute('data-av-expanded-figure','');
    dialog.setAttribute('data-av-viewer-kind',kind);
    const title = kind==='figure'?figureTitle(card):titleOf(card);
    dialogTitle.textContent = title;
    if (dialogClose) { dialogClose.textContent = focusStack.length ? "Back" : "Close"; dialogClose.setAttribute("aria-label", focusStack.length ? "Back to previous expanded view" : "Close expanded view"); }
    showFigureContext(focused);
    preferences.mirror(dialog, owner);
    dialog.setAttribute("aria-label", `Expanded view: ${title}`);
    attribute(trigger, "aria-expanded", "true");
    try { if(!dialog.open) dialog.showModal(); }
    catch { restoreFocus(false); reveal(card, true); return; }
    notifications?.refresh();
    dialogClose?.focus();
    updateFigureBounds();
    if(kind==='figure')plots.fit(card);else plots.refresh(card);
    figures.refresh();for(const bar of sectionBars)bar.refresh();
    motion(card);
  }

  function endComparison(explorer:HTMLElement):void {
    for(const reader of readers.values())if(reader.explorer===explorer)reader.reset();
    for(const checkbox of inScope<HTMLInputElement>(explorer,'[data-av-compare]','[data-av-explorer]'))checkbox.checked=false;
    stateClass(explorer,'av-comparing',false);
    for(const item of inScope(explorer,'[data-av-object]','[data-av-explorer]'))stateClass(item,'av-compared',false);
    for(const group of comparisonSlots.get(explorer)||[])for(const{object,marker}of group)marker.parentNode?.insertBefore(object,marker);
    const status=inScope<HTMLElement>(explorer,'[data-av-comparison-status]','[data-av-explorer]')[0];if(status)message(status,'Single record view.');
  }
  function renderCollections(explorer:HTMLElement,key?:string):void {
    const compared=new Set(inScope<HTMLInputElement>(explorer,'[data-av-compare]','[data-av-explorer]').filter(control=>control.checked).map(control=>control.getAttribute('data-av-compare')));
    for(const[parent,objects]of collections){
      if(parent.closest('[data-av-explorer]')!==explorer)continue;
      const reader=readers.get(parent);if(reader){reader.render(key);continue;}
      const current=objects.find(object=>object.getAttribute('data-av-object')===key)||(compared.size===1?objects.find(object=>compared.has(object.getAttribute('data-av-object'))):undefined)||objects.find(object=>object.classList.contains('av-selected'))||objects.find(object=>object.hasAttribute('open'))||objects[0];
      const selected=compared.size>1?objects.filter(object=>compared.has(object.getAttribute('data-av-object'))):current?[current]:[];
      parent.style.setProperty('--av-reader-columns',String(Math.max(1,selected.length)));
      for(const object of objects){const shown=selected.includes(object);hidden(object,!shown);attribute(object,'open',shown?'':null);}
    }
  }
  function updateSteps(explorer: HTMLElement, key: string): void {
    const objects = inScope(explorer, "[data-av-object]", "[data-av-explorer]");
    const index = objects.findIndex(object => object.getAttribute("data-av-object") === key);
    for (const step of inScope(explorer, "[data-av-step]", "[data-av-explorer]")) {
      const direction = step.getAttribute("data-av-step") === "-1" ? -1 : 1;
      attribute(step, "disabled", !objects.length || (direction < 0 ? index <= 0 : index >= objects.length - 1) ? "" : null);
    }
  }
  function synchronizeObject(explorer: HTMLElement, key?: string): void {
    const objects = inScope(explorer, "[data-av-object]", "[data-av-explorer]");
    const open = objects.filter(object => object.tagName.toLowerCase() !== "details" || object.hasAttribute("open"));
    const current = open.find(object => object.classList.contains("av-selected")) || open[0];
    const selected = key === undefined ? current?.getAttribute("data-av-object") || "" : key;
    for (const item of objects) stateClass(item, "av-selected", item.getAttribute("data-av-object") === selected);
    for (const item of inScope(explorer, "[data-av-inspect]", "[data-av-explorer]")) {
      const active = item.getAttribute("data-av-inspect") === selected;
      attribute(item, "data-av-inspected", active ? "" : null);
      // Older custom explorers without the plot tools keep their original single-selection semantics.
      if (!item.closest(".av-plot-scroll")) attribute(item, "aria-pressed", String(active));
    }
    for (const edge of inScope(explorer, "[data-av-from],[data-av-to]", "[data-av-explorer]")) stateClass(edge, "av-related", !!selected && (edge.getAttribute("data-av-from") === selected || edge.getAttribute("data-av-to") === selected));
    for (const select of inScope<HTMLSelectElement>(explorer, "[data-av-select]", "[data-av-explorer]")) if (Array.from(select.options).some(option => option.value === selected)) select.value = selected;
    updateSteps(explorer, selected);
    renderCollections(explorer,selected);
  }
  function inspectObject(control: Element, requestedKey?: string, takeFocus = true, selectView = false): void {
    const explorer = control.closest<HTMLElement>("[data-av-explorer]") || (figureOf(control) ? figureOrigin(figureOf(control)!).explorer : null);
    const key = requestedKey || control.getAttribute("data-av-inspect") || (control as HTMLSelectElement).value;
    if (!explorer || !key) return;
    const objects = inScope(explorer, "[data-av-object]", "[data-av-explorer]");
    const object = objects.find(item => item.getAttribute("data-av-object") === key);
    if (!object) return;
    if(collectionOwners.has(object)){endComparison(explorer);}
    for (const item of objects) if (item !== object && !explorer.classList.contains("av-comparing") && item.tagName.toLowerCase() === "details") attribute(item, "open", null);
    synchronizeObject(explorer, key);
    if(focused?.kind==='figure'&&focused.card.contains(control)){
      for(const mark of elements<HTMLElement>(focused.card,'[data-av-inspect]'))attribute(mark,'data-av-inspected',mark.getAttribute('data-av-inspect')===key?'':null);
      if(dialogContext){
        let detail=dialogContext.querySelector<HTMLElement>('[data-av-selected-context]');
        if(!detail){detail=document.createElement('section');detail.setAttribute('data-av-selected-context','');dialogContext.insertBefore(detail,dialogContext.firstChild);}
        detail.replaceChildren();
        const title=document.createElement('h3');title.textContent=titleOf(object);detail.appendChild(title);
        const content=object.querySelector('.av-object-body');
        if(content){const copy=content.cloneNode(true) as HTMLElement;copy.removeAttribute('id');for(const node of Array.from(copy.querySelectorAll('[id]')))node.removeAttribute('id');for(const node of Array.from(copy.querySelectorAll('[data-av-controls],[data-av-review-ui]')))node.remove();detail.appendChild(copy);}
        else {const text=document.createElement('p');text.textContent=object.textContent;detail.appendChild(text);}
        dialogContext.parentElement?.setAttribute('open','');dialogContext.scrollTop=0;
      }
      notebooks?.recordInspection(object);return;
    }
    reveal(object, takeFocus, selectView);
    let status = inScope(explorer, "[data-av-inspector-status]", "[data-av-explorer]")[0];
    if (!status) { status = output(explorer, "av-inspection-status av-sr-only"); status.setAttribute("data-av-inspector-status", ""); }
    message(status, `Inspecting “${titleOf(object)}”. Other objects and their evidence remain available.`);
    notebooks?.recordInspection(object);
    motion(object);
  }
  function stepObject(control: Element): void {
    const explorer = control.closest<HTMLElement>("[data-av-explorer]");
    if (!explorer) return;
    const objects = inScope(explorer, "[data-av-object]", "[data-av-explorer]");
    const selected = objects.findIndex(object => object.classList.contains("av-selected"));
    const current = selected;
    const direction = control.getAttribute("data-av-step") === "-1" ? -1 : 1;
    const next = objects[current + direction];
    if (next) inspectObject(control, next.getAttribute("data-av-object") || undefined);
  }
  function compareArtifacts(explorer: HTMLElement): void {
    const managed=[...readers.values()].filter(reader=>reader.explorer===explorer);if(managed.length){for(const reader of managed)reader.compare();return;}
    const selected = new Set(inScope<HTMLInputElement>(explorer, "[data-av-compare]", "[data-av-explorer]").filter(control => control.checked).map(control => control.getAttribute("data-av-compare")));
    for (const object of inScope(explorer, "[data-av-object]", "[data-av-explorer]")) {
      const compared = selected.has(object.getAttribute("data-av-object"));
      stateClass(object, "av-compared", compared);
      if (compared && object.tagName.toLowerCase() === "details") attribute(object, "open", "");
    }
    let groups = comparisonSlots.get(explorer);
    if (!groups) {
      const byParent = new Map<Element, Array<{ object: HTMLElement; marker: Comment }>>();
      for (const object of inScope(explorer, "[data-av-object]", "[data-av-explorer]")) {
        const parent = object.parentElement;
        if (!parent) continue;
        const marker = document.createComment("av-comparison-slot");
        parent.insertBefore(marker, object);
        const group = byParent.get(parent) || [];
        group.push({ object, marker });
        byParent.set(parent, group);
      }
      groups = [...byParent.values()];
      comparisonSlots.set(explorer, groups);
      const originalGroups = groups;
      undo.push(() => {
        for (const group of originalGroups) for (const { object, marker } of group) {
          if (marker.parentNode) marker.parentNode.replaceChild(object, marker);
        }
      });
    }
    // Reorder the original live nodes, so visual and keyboard reading order
    // agree. Saved slots restore supplied order when comparison ends or cleans up.
    for (const group of groups) {
      const ordered = selected.size > 1
        ? [...group.filter(({ object }) => selected.has(object.getAttribute("data-av-object"))), ...group.filter(({ object }) => !selected.has(object.getAttribute("data-av-object")))]
        : group;
      group.forEach(({ marker }, index) => marker.parentNode?.insertBefore(ordered[index].object, marker));
    }
    stateClass(explorer, "av-comparing", selected.size > 1);
    renderCollections(explorer);
    if (selected.size < 2) {
      const objects = inScope(explorer, "[data-av-object]", "[data-av-explorer]");
      const active = objects.find(object => selected.has(object.getAttribute("data-av-object"))) || objects.find(object => object.hasAttribute("open"));
      if (active) preferences.reveal(active);
    }
    let status = inScope(explorer, "[data-av-comparison-status]", "[data-av-explorer]")[0];
    if (!status) { status = output(explorer, "av-comparison-status av-sr-only"); status.setAttribute("data-av-comparison-status", ""); }
    message(status, selected.size ? `${selected.size} artifacts selected for comparison.${selected.size > 1 ? " Selected artifacts are grouped first in their supplied order." : ""} Unselected artifacts remain available.` : "No artifacts selected for comparison. All artifacts remain available.");
    motion(explorer);
  }

  function click(event: MouseEvent): void {
    if (event.defaultPrevented || event.button !== 0) return;
    const target = targetOf(event);
    if (!target) return;
    const close = target.closest("[data-av-close-focus]");
    if (close && dialog?.contains(close)) { closeFocus(); return; }
    if (!contains(target)) return;
    const collectionSummary=target.closest<HTMLElement>('summary');if(collectionSummary&&collectionOwners.has(collectionSummary.parentElement!)&&!target.closest('button,input,a,select,textarea')){event.preventDefault();return;}
    if (figures.click(target)) { event.preventDefault(); return; }
    if (itemSelection?.click(event,target)) { event.preventDefault(); return; }
    if(target.closest('.av-plot-scroll')&&figureOf(target)?.getAttribute('data-av-selection-mode')==='text')return;
    if (notebooks?.click(target)) { if(!target.closest('a[download]'))event.preventDefault(); return; }
    if (preferences.click(target)) return;
    const focusControl = target.closest<HTMLElement>("[data-av-focus]");
    if (focusControl) {
      event.preventDefault();
      const card = focusControl.closest<HTMLElement>(".av-card");
      if (card) inspectFrame(card, focusControl);
      return;
    }
    const dataControl = target.closest<HTMLElement>("[data-av-view-toggle]");
    if (dataControl) {
      event.preventDefault();
      const card = dataControl.closest<HTMLElement>(".av-card") || (focused?.toolMoves.some(move => move.element.contains(dataControl)) ? focused.card : null);
      if (card) dataMode(card, dataControl.getAttribute("data-av-view-toggle") === "data" ? "data" : "visual");
      return;
    }
    // Only registered controls own commands. Expanded figures also carry
    // data-av-fit-width as geometry metadata, not as a clickable Fit action.
    if (plots.click(target)) { event.preventDefault(); return; }
    const scopeChoice = target.closest("[data-av-scope-choice]");
    if (scopeChoice) { const explorer = scopeChoice.closest<HTMLElement>("[data-av-explorer]"); if (explorer) coordinateScope(explorer, scopeChoice.getAttribute("data-av-scope-choice")!); return; }
    const inspect = target.closest("[data-av-inspect]");
    if (inspect) { inspectObject(inspect, undefined, (event.detail || 0) === 0); return; }
    const step = target.closest("[data-av-step]");
    if (step) { stepObject(step); return; }
    const state = workspaceFor(target);
    if (state) {
      if (target.closest("[data-av-path-exit]")) { state.journey = null; renderWorkspace(state); recordPlace(state); return; }
      const pathStep = target.closest<HTMLElement>("[data-av-path-step]");
      if (pathStep && state.journey) {
        const route = state.journeys.get(state.journey);
        const index = route?.steps.indexOf(state.selected || "") ?? -1;
        const next = route?.steps[index + (pathStep.getAttribute("data-av-path-step") === "-1" ? -1 : 1)];
        const panel = state.panels.find(panel => panel.getAttribute("data-av-panel") === next);
        if (panel) {
          reveal(panel, true);
          try { window?.history?.replaceState(null, "", "#" + encodeURIComponent(panel.id)); } catch { /* Native links and notebook remain available. */ }
        }
        return;
      }
      if (target.closest("[data-av-show-all]")) { changeReadingMode(state, "all"); return; }
      if (target.closest("[data-av-show-single]")) { changeReadingMode(state, "single"); return; }
      if (target.closest("[data-av-search-reset]")) { clearSearch(state); renderWorkspace(state, true); state.search?.focus(); return; }
    }
    const anchor = target.closest<HTMLAnchorElement>("a[href]");
    if (anchor && !event.ctrlKey && !event.metaKey && !event.altKey && !event.shiftKey) {
      const destination = fragment(anchor.getAttribute("href"));
      if (destination) {
        const route = anchor.getAttribute("data-av-start-journey");
        const state = workspaceFor(anchor);
        if (route && state?.journeys.has(route)) state.journey = route;
        reveal(destination, true);
      }
    }
  }
  const itemReaders = new Map<HTMLElement, {dialog: HTMLDialogElement; body: HTMLElement; trigger: HTMLElement | null}>();
  function selectDiagramItem(target: Element, open = false, trigger?: HTMLElement): void {
    const item = target.closest<HTMLElement>('[data-av-mermaid-item],[data-av-observation]'), figure = item && figureOf(item);
    if (!item || !figure || !open && !itemReaders.get(figure)?.dialog.open) return;
    let reader = itemReaders.get(figure);
    if (!reader) {
      const panel = document.createElement('dialog'); panel.className = 'av-source-panel av-selected-items-dialog'; panel.setAttribute('data-av-review-ui',''); panel.setAttribute('aria-label','Selected diagram items');
      if (typeof panel.showModal !== 'function') return;
      const header = document.createElement('header'); header.className = 'av-source-header'; panel.appendChild(header);
      const heading = document.createElement('strong'); heading.textContent = 'Selected evidence'; header.appendChild(heading);
      const close = button('Close'); close.setAttribute('aria-label','Close selected evidence'); header.appendChild(close);
      const body = document.createElement('div'); body.className = 'av-selected-items-body'; panel.appendChild(body);
      const actions = document.createElement('div'); actions.className = 'av-button-group'; panel.appendChild(actions);
      const source = figure.querySelector<HTMLButtonElement>('[data-av-figure-action="source"]');
      if (source) { const go = button('View original source'); actions.appendChild(go); go.addEventListener('click',event=>{event.preventDefault();event.stopPropagation();source.click();}); }
      reader = {dialog:panel,body,trigger:null}; itemReaders.set(figure,reader); figure.appendChild(panel);
      const current = reader;
      const dismiss = (event:Event) => {event.preventDefault();event.stopPropagation();panel.close();if(current.trigger?.isConnected)current.trigger.focus({preventScroll:true});};
      close.addEventListener('click',dismiss);panel.addEventListener('cancel',dismiss);
      undo.push(()=>{if(panel.open)panel.close();panel.remove();itemReaders.delete(figure);});
    }
    reader.body.replaceChildren();
    const selected = selectedFigureItems(figure);
    for (const mark of selected.length ? selected : [item]) {
      const section = document.createElement('section'), heading = document.createElement('h3'); heading.textContent = mark.getAttribute('aria-label') || 'Selected item'; section.appendChild(heading);
      const text = document.createElement('pre'); text.textContent = mark.textContent || mark.getAttribute('aria-label') || ''; section.appendChild(text); reader.body.appendChild(section);
    }
    if (open) { reader.trigger=trigger||item; if(!reader.dialog.open)reader.dialog.showModal(); reader.dialog.querySelector<HTMLElement>('button')?.focus({preventScroll:true}); }
  }
  function keydown(event: KeyboardEvent): void {
    if (event.isComposing) return;
    const origin = targetOf(event);
    if (origin && itemSelection?.keydown(event,origin)) { event.preventDefault(); event.stopPropagation(); return; }
    const summary=origin?.closest<HTMLElement>('summary');
    if(summary&&collectionOwners.has(summary.parentElement!)&&!origin?.closest('button,input,a,select,textarea')&&['Enter',' '].includes(event.key)){event.preventDefault();return;}
    if (event.key === "Escape") {
      const notebook = origin?.closest<HTMLElement>("[data-av-notebook]");
      if (notebook?.hasAttribute("open")) { attribute(notebook, "open", null); notebook.querySelector<HTMLElement>("summary")?.focus(); event.preventDefault(); return; }
    }
    if (event.key === "Escape" && preferences.dismiss(targetOf(event), true)) { event.preventDefault(); return; }
    if (event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey || (event.key !== "Enter" && event.key !== " ")) return;
    const target = targetOf(event);
    if(target?.closest('.av-plot-scroll')&&figureOf(target)?.getAttribute('data-av-selection-mode')==='text')return;
    if(target?.closest('.av-plot-scroll'))return;
    const inspect = target?.closest("[data-av-inspect]");
    if (!inspect || !contains(inspect) || target?.closest("input,textarea,select,button,a[href],[contenteditable]")) return;
    event.preventDefault();
    inspectObject(inspect);
  }
  function change(event: Event): void {
    const target = targetOf(event);
    if (!target || !contains(target)) return;
    if (notebooks?.change(target)) return;
    if (preferences.change(target)) {
      for (const explorer of inclusive("[data-av-explorer]")) synchronizeObject(explorer);
      return;
    }
    if (target.matches("[data-av-select]")) { inspectObject(target, undefined, false); inspectors?.refresh(); inspectors?.open(target,target as HTMLElement); }
    else if (target.matches("[data-av-compare]")) {
      const explorer = target.closest<HTMLElement>("[data-av-explorer]");
      if (explorer) compareArtifacts(explorer);
    }
  }

  function input(event: Event): void {
    const target = targetOf(event);
    if (target && contains(target)) notebooks?.input(target);
  }
  function disclosureToggle(event: Event): void {
    const target = targetOf(event);
    // Reading panes are owned by their workbench. Reopening or hiding n records
    // must not fan out into n whole-explorer synchronization passes or move the
    // current record to whichever native toggle event happened to arrive last.
    if(target?.matches('[data-av-object]')&&readers.has(collectionOwners.get(target as HTMLElement)!)){
      if(!target.hasAttribute('hidden')&&!target.hasAttribute('open'))attribute(target,'open','');
      return;
    }
    if (target && contains(target)) {
      preferences.toggle(target);
      if (target.matches("details[open]")) plots.refresh(target);
      if (target.matches("details.av-card[open]")) { for (const bar of sectionBars) { const host = sectionBarHosts.get(bar); if (host && target.contains(host)) bar.refresh(); } figures.refresh(target); }
      if(collectionOwners.has(target as HTMLElement)&&!target.hasAttribute("hidden")&&!target.hasAttribute("open")){attribute(target,"open","");return;}
      if (target.matches("[data-av-object]")) {
        const explorer = target.closest<HTMLElement>("[data-av-explorer]");
        if (explorer) synchronizeObject(explorer, target.hasAttribute("open") ? target.getAttribute("data-av-object") || "" : undefined);
      }
      if (target.matches("details[open][data-av-notebook],details[open][data-av-settings]")) {
        const controls = target.closest(".av-workspace-utilities");
        if (controls) for (const other of elements(controls, "[data-av-notebook],[data-av-settings]")) if (other !== target) attribute(other, "open", null);
      }
      if (target.matches("details[open]")) {
        const panel = target.matches("[data-av-notebook],[data-av-settings]") ? target.querySelector(".av-notebook-popover,.av-settings-panel") : null;
        if (panel) motion(panel); else if (!target.matches("[data-av-notebook],[data-av-settings]")) motion(target);
      }
    }
  }

  attribute(root, "data-av-enhanced", "true");
  stateClass(root, "av-enhanced", true);
  for (const controls of inclusive("[data-av-controls],[data-av-script-only]")) if(!controls.matches(".av-floating-panel")) hidden(controls, false);

  for (const card of inclusive<HTMLElement>(".av-card")) {
    for (const control of ownCardParts(card, "[data-av-focus]")) { attribute(control, "aria-haspopup", "dialog"); attribute(control, "aria-expanded", "false"); }
    if (!ownCardParts(card, '[data-av-content-view="visual"]').length || !ownCardParts(card, '[data-av-content-view="data"]').length) continue;
    let toolbar = ownCardParts(card, "[data-av-controls]")[0];
    if (!toolbar) { toolbar = document.createElement("div"); toolbar.className = "av-frame-tools"; toolbar.setAttribute("data-av-controls", ""); generated(toolbar, card); }
    if (!ownCardParts(card, "[data-av-view-toggle]").length) {
      const control = button("Data");
      control.setAttribute("data-av-view-toggle", "data"); control.setAttribute("data-av-view-switch", "");
      generated(control, toolbar);
      const expand = ownCardParts(card, "[data-av-focus]")[0];
      if (expand?.parentElement === toolbar) toolbar.insertBefore(control, expand);
    }
    if (!ownCardParts(card, "[data-av-view-status]").length) { const status = output(card, "av-view-status av-sr-only"); status.setAttribute("data-av-view-status", ""); }
    dataMode(card, "visual", false);
  }

  for(const explorer of inclusive<HTMLElement>('[data-av-explorer]')){
    for(const inspector of inScope<HTMLElement>(explorer,'.av-inspector','[data-av-explorer]')){
      const direct=Array.from(inspector.children).filter(element=>element.hasAttribute('data-av-object')) as HTMLElement[];
      if(direct.length){const stage=document.createElement('div');stage.className='av-object-list';inspector.insertBefore(stage,direct[0]);const moves=direct.map(element=>{const marker=document.createComment('av-reader-object');element.parentNode!.insertBefore(marker,element);stage.appendChild(element);return{element,marker};});undo.push(()=>{for(const move of moves)move.marker.parentNode?.replaceChild(move.element,move.marker);stage.remove();});}
    }
    const groups=new Map<HTMLElement,HTMLElement[]>();
    for(const object of inScope<HTMLElement>(explorer,'[data-av-object]','[data-av-explorer]')){const parent=object.parentElement;if(!parent||!(parent.matches('.av-deck-grid,.av-scenario-grid')||parent.matches('.av-object-list')&&parent.closest('.av-inspector')))continue;const values=groups.get(parent)||[];values.push(object);groups.set(parent,values);}
    for(const[parent,objects]of groups){
      collections.set(parent,objects);stateClass(parent,'av-collection-stage',true);const oldColumns=parent.style.getPropertyValue('--av-reader-columns');undo.push(()=>{if(oldColumns)parent.style.setProperty('--av-reader-columns',oldColumns);else parent.style.removeProperty('--av-reader-columns');});
      for(const object of objects){collectionOwners.set(object,parent);const summary=object.querySelector('summary');if(summary){attribute(summary,'tabindex','-1');attribute(summary,'aria-disabled',null);}}
      if(parent.matches('.av-scenario-grid')&&objects.length>1&&!inScope(explorer,'[data-av-compare]','[data-av-explorer]').length){const choices=document.createElement('fieldset');choices.className='av-artifact-controls';choices.setAttribute('data-av-controls','');const legend=document.createElement('legend');legend.textContent='Compare scenarios';choices.appendChild(legend);for(const object of objects){const label=document.createElement('label');label.className='av-compare-choice';const checkbox=document.createElement('input');checkbox.type='checkbox';checkbox.setAttribute('data-av-compare',object.getAttribute('data-av-object')!);label.appendChild(checkbox);label.appendChild(document.createTextNode(titleOf(object)));choices.appendChild(label);}parent.parentNode!.insertBefore(choices,parent);undo.push(()=>choices.remove());}
    }
  }

  for (const explorer of inclusive("[data-av-explorer]")) {
    for (const select of inScope<HTMLSelectElement>(explorer, "[data-av-select]", "[data-av-explorer]")) {
      const original = select.value;
      undo.push(() => { select.value = original; });
    }
    for (const checkbox of inScope<HTMLInputElement>(explorer, "[data-av-compare]", "[data-av-explorer]")) {
      const original = checkbox.checked;
      undo.push(() => { checkbox.checked = original; });
    }
    for (const control of inScope(explorer, "[data-av-inspect]", "[data-av-explorer]")) {
      if (!control.matches("button,a[href],input")) { attribute(control, "tabindex", "0"); attribute(control, "role", "button"); }
      const svg = control.closest("svg");
      if (svg) attribute(svg, "role", "group");
      attribute(control, "aria-pressed", "false");
      if (!control.hasAttribute("aria-label")) {
        const object = inScope(explorer, "[data-av-object]", "[data-av-explorer]").find(item => item.getAttribute("data-av-object") === control.getAttribute("data-av-inspect"));
        attribute(control, "aria-label", `Inspect ${object ? titleOf(object) : (control.textContent || "evidence").trim()}`);
      }
    }
    synchronizeObject(explorer);
    const visibleScope = inScope(explorer, "[data-av-coordinate-scope]", "[data-av-explorer]").find(element => !element.hasAttribute("hidden"));
    if (visibleScope) coordinateScope(explorer, visibleScope.getAttribute("data-av-coordinate-scope")!);
  }

  for(const[parent,objects]of collections)if(parent.matches('.av-deck-grid,.av-scenario-grid')&&objects.length){const explorer=parent.closest<HTMLElement>('[data-av-explorer]')!;readers.set(parent,attachComparisonReader(explorer,parent,objects));}

  for (const workspace of inclusive<HTMLElement>(".av-workspace")) {
    const panels = inScope(workspace, "[data-av-panel]", ".av-workspace");
    if (!panels.length) continue;
    const navigation = inScope(workspace, "[data-av-view]", ".av-workspace");
    const search = inScope<HTMLInputElement>(workspace, "[data-av-search]", ".av-workspace")[0] || null;
    let status = inScope(workspace, "[data-av-search-status]", ".av-workspace")[0];
    if (!status) { status = output(workspace, "av-search-status av-muted"); status.setAttribute("data-av-search-status", ""); }
    const showAll = inScope(workspace, "[data-av-show-all]", ".av-workspace");
    const showSingle = inScope(workspace, "[data-av-show-single]", ".av-workspace");
    const controlsParent = search?.closest("label")?.parentElement || search?.parentElement || workspace;
    if (!showAll.length) { const control = button("Full report"); control.setAttribute("data-av-show-all", ""); showAll.push(generated(control, controlsParent)); }
    if (!showSingle.length) { const control = button("Section view"); control.setAttribute("data-av-show-single", ""); showSingle.push(generated(control, showAll[0]?.parentElement || controlsParent)); }
    let reset = inScope<HTMLButtonElement>(workspace, "[data-av-search-reset]", ".av-workspace")[0] || null;
    if (search && !reset) { reset = button("Clear search"); reset.setAttribute("data-av-search-reset", ""); generated(reset, controlsParent); }
    let results = inScope<HTMLElement>(workspace, "[data-av-search-results]", ".av-workspace")[0];
    if (!results) { results = document.createElement("div"); results.className = "av-search-results"; results.setAttribute("data-av-search-results", ""); results.setAttribute("role", "region"); results.setAttribute("aria-label", "Search results"); generated(results, controlsParent); }
    const originalResults = Array.from(results.childNodes);
    undo.push(() => { results.textContent = ""; for (const child of originalResults) results.appendChild(child); });
    const journeys = new Map<string, { element: HTMLElement; steps: string[] }>();
    for (const route of inScope<HTMLElement>(workspace, "[data-av-journey-id]", ".av-workspace")) {
      try {
        const id = route.getAttribute("data-av-journey-id"), steps: unknown = JSON.parse(route.getAttribute("data-av-journey-steps") || "");
        if (id && !journeys.has(id) && Array.isArray(steps) && steps.length && new Set(steps).size === steps.length && steps.every(step => typeof step === "string" && panels.some(panel => panel.getAttribute("data-av-panel") === step))) journeys.set(id, { element: route, steps });
      } catch { /* Authored malformed route hooks do not hide the underlying views. */ }
    }
    const selected = workspace.getAttribute("data-av-start-view") || navigation.find(link => link.getAttribute("aria-current") === "page")?.getAttribute("data-av-view");
    const state: WorkspaceState = { element: workspace, panels, navigation, search, status, reset, showAll, showSingle, mode: "single", selected: panels.some(panel => panel.getAttribute("data-av-panel") === selected) ? selected! : panels[0].getAttribute("data-av-panel"), query: search?.value || "", results, journey: null, journeys };
    workspaces.push(state);
    for (const card of elements<HTMLElement>(workspace, ".av-card")) {
      const panel = card.closest<HTMLElement>("[data-av-panel]");
      if (card.closest(".av-workspace") === workspace && panel && panels.includes(panel)) frameLocations.set(card, { state, panel });
    }
    if (search) listen(search, "input", (() => { state.query = search.value; if (state.reset) hidden(state.reset, !state.query); renderSearch(state); }) as EventListener);
    renderWorkspace(state);
  }

  notebooks = attachNotebooks(root, { notify: message=>notifications?.show(message), controls: element => element.hasAttribute('data-av-figure') ? figures.toolbar(element) : ownCardParts(element,'.av-frame-tools')[0] || null,
    reveal: target => reveal(target, true),
    restored: (scope, place) => {
      const state = workspaces.find(state => state.element === scope);
      if (!state || !state.panels.some(panel => panel.getAttribute('data-av-panel') === place.viewId)) return;
      state.selected = place.viewId; state.mode = place.mode; state.journey = place.journeyId;
      renderWorkspace(state); // Hydration is not a navigation action or a focus request.
    },
    navigate: (scope, place) => {
      const state = workspaces.find(state => state.element === scope);
      if (!state || !state.panels.some(panel => panel.getAttribute("data-av-panel") === place.viewId)) return;
      closeAllFocus(false); clearSearch(state);
      state.selected = place.viewId; state.mode = place.mode; state.journey = place.journeyId;
      renderWorkspace(state); recordPlace(state);
      const panel = state.panels.find(panel => panel.getAttribute("data-av-panel") === state.selected);
      if (panel) { focus(panel); scroll(panel); }
    },
  });
  for (const state of workspaces) if (state.search) {
    state.finder = attachReportSearch(state.element, state.search, state.results, {
      notes: () => notebooks?.searchEntries(state.element) || [],
      close: () => { clearSearch(state); if (state.reset) hidden(state.reset, true); },
      reveal: target => {
        if (target.hasAttribute('data-av-object')) {
          inspectObject(target, target.getAttribute('data-av-object') || undefined, false, false);
          inspectors?.refresh(); inspectors?.open(target, state.search!);
        } else if (target.matches('[data-av-inspect],[data-av-observation],[data-av-mermaid-item]')) {
          reveal(target, false, false);
          if (target.hasAttribute('data-av-inspect')) { inspectObject(target, undefined, false, false); inspectors?.refresh(); inspectors?.open(target, state.search!); }
          else selectDiagramItem(target, true);
        } else reveal(target, true, false);
      },
    });
    renderSearch(state);
  }
  const explicitTarget = fragment(window?.location.hash || "");
  figures.dock();
  for(const card of inclusive<HTMLElement>('.av-card')){
    const toolbar=ownCardParts(card,'.av-frame-tools')[0];if(!toolbar)continue;
    const controls=Array.from(toolbar.querySelectorAll<HTMLButtonElement>('button'));
    const bar=attachCommandBar(toolbar,'Section actions');sectionBars.push(bar);sectionBarHosts.set(bar,toolbar);
    for(const button of controls){const action=button.getAttribute('data-av-review-action'),label=action==='new-note'?'Note':action==='bookmark'?'Bookmark':button.hasAttribute('data-av-focus')?'Expand section':button.hasAttribute('data-av-view-toggle')?'Data':button.textContent||'Action';
      bar.add(button,{label,priority:button.hasAttribute('data-av-focus')?10:30,width:36,icon:action==='new-note'?'M4 3h16v14l-5 4H4zM8 8h8M8 12h6':action==='bookmark'?'M6 3h12v18l-6-4-6 4z':button.hasAttribute('data-av-view-toggle')?'M3 3h18v18H3zM3 9h18M3 15h18M9 3v18':undefined});}
  }
  for (const state of workspaces) {
    if (explicitTarget && workspaceFor(explicitTarget) === state) continue;
    const saved = notebooks.restore(state.element);
    if (saved?.viewId && state.panels.some(panel => panel.getAttribute("data-av-panel") === saved.viewId)) {
      state.selected = saved.viewId; state.mode = saved.mode; state.journey = saved.journeyId; renderWorkspace(state);
    }
  }
  inspectors = attachInspectors(root);
  itemSelection = attachItemSelection(root, figures.figures, {
    inspect: (item, open, trigger) => {
      if (item.hasAttribute('data-av-inspect')) {
        inspectObject(item,undefined,false); inspectors?.refresh();
        if (open && focused?.kind !== 'figure') inspectors?.open(item,trigger||item);
      } else selectDiagramItem(item,open,trigger);
    },
    command: (figure,control,options) => figures.command(figure,control,options),
    updateCommand: (figure,control,options) => figures.updateCommand(figure,control,options),
    canReview: figure => !!notebooks?.hasReview(figure),
    review: (figure,action,trigger) => notebooks?.reviewSelection(figure,action,trigger),
  });
  const utilityCleanup = attachUtilityPanels(root);
  // Reserve the real sticky bar height, including wrapped controls and reader zoom.
  for (const state of workspaces) {
    const bar = state.element.querySelector<HTMLElement>('.av-workspace-bar');
    if (!bar) continue;
    const original = state.element.style.getPropertyValue('--av-bar-height');
    const measure = () => { if (cleaned) return; const height = bar.getBoundingClientRect().height; if (height > 0) state.element.style.setProperty('--av-bar-height', Math.ceil(height) + 'px'); };
    measure();
    if (window?.ResizeObserver) { const observer = new window.ResizeObserver(measure); observer.observe(bar); undo.push(() => observer.disconnect()); }
    undo.push(() => { if (original) state.element.style.setProperty('--av-bar-height', original); else state.element.style.removeProperty('--av-bar-height'); });
  }
  listen(root, "input", input as EventListener);
  listen(root, "click", click as EventListener);
  listen(root, "keydown", keydown as EventListener);
  listen(root, "change", change as EventListener);
  // Another independently enhanced root may own the fragment destination. A
  // click still needs to reveal it when the hash already has the same value.
  listen(document, "click", ((event: MouseEvent) => {
    if (event.defaultPrevented || event.button !== 0 || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
    // A generated download is not a reader click outside the active panel.
    if (targetOf(event)?.closest('[data-av-internal-download]')) return;
    preferences.dismiss(targetOf(event));
    for (const notebook of inclusive<HTMLElement>("[data-av-notebook]")) if (notebook.hasAttribute("open") && !notebook.contains(targetOf(event))) attribute(notebook, "open", null);
    const anchor = targetOf(event)?.closest<HTMLAnchorElement>("a[href]");
    if (!anchor) return;
    const destination = fragment(anchor.getAttribute("href"), false);
    if (!destination) return;
    if (focused && !focused.card.contains(destination)) closeAllFocus(false);
    if (!contains(anchor) && contains(destination)) reveal(destination, true);
  }) as EventListener);
  listen(root, "toggle", disclosureToggle as EventListener, true);
  if (window) listen(window, "hashchange", hashChanged as EventListener);
  hashChanged();
  const initialAppearance = preferences.whenReady().then(() => {
    if (cleaned) return; appearanceReady = true; return diagrams?.refresh();
  });
  const ready = Promise.all([preferences.whenReady(), notebooks.whenReady()]).then(() => {
    if (cleaned) return;
    for (const state of workspaces) attribute(state.element, 'data-av-ready', '');
    notifyReportReady(document);
  });
  if(window)listen(window,'resize',(()=>{updateFigureBounds();if(focused?.kind==='figure')plots.refresh(focused.card);}) as EventListener);
  for(const select of inclusive<HTMLSelectElement>('select')){
    if(select.parentElement?.classList.contains('av-select-wrap'))continue;
    const marker=document.createComment('av-select'),wrap=document.createElement('span');wrap.className='av-select-wrap';select.parentNode?.insertBefore(marker,select);select.parentNode?.insertBefore(wrap,select);wrap.appendChild(select);
    const measure=()=>{if(cleaned)return;const font=window?.getComputedStyle?.(select).font||'14px sans-serif',width=browserTextMeasure(document,font)||estimateTextWidth;let widest=0;for(const option of Array.from(select.options))widest=Math.max(widest,width(option.textContent||''));wrap.style.setProperty('--av-select-content-width',Math.ceil(widest)+'px');};
    measure();void document.fonts?.ready.then(measure);if(window?.MutationObserver){const observer=new window.MutationObserver(measure);observer.observe(select,{childList:true,subtree:true,characterData:true});undo.push(()=>observer.disconnect());}
    undo.push(()=>{marker.parentNode?.replaceChild(select,marker);wrap.remove();});
  }

  const cleanup = Object.assign((): void => {
    if (cleaned) return;
    cleaned = true;
    closeAllFocus();
    cancelMotion();
    for (const state of workspaces) state.finder?.cleanup();
    for(const bar of sectionBars)bar.cleanup();
    itemSelection?.cleanup(); inspectors?.cleanup();
    for(const reader of readers.values())reader.cleanup();readers.clear();
    for (const restore of undo.reverse()) restore();
    utilityCleanup();
    notebooks?.cleanup();
    notifications?.cleanup();
    preferences.cleanup();
    diagrams?.cleanup();
    plots.cleanup(); figures.cleanup();
    refinementCleanup();
    enhancedRoots.delete(root);
  }, { whenReady: () => ready, whenIdle: async (): Promise<void> => { await Promise.all([ready, initialAppearance,preferences.whenIdle(), notebooks?.whenIdle(), diagrams?.whenIdle(), figures.whenIdle(), ...workspaces.map(state => state.finder?.whenIdle())]); } });
  enhancedRoots.set(root, cleanup);
  return cleanup;
}
