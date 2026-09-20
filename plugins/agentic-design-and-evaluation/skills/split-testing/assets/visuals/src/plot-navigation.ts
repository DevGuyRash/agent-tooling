/** Viewport mechanics only. Source-owned coordinates, evidence and selection are retained. */
export interface PlotSnapshot { entries: { element: HTMLElement; mode: Mode; zoom: number; left: number; top: number }[] }
export interface PlotController {
  snapshot(target: Element): PlotSnapshot;
  fit(target: Element): void;
  restore(snapshot: PlotSnapshot): void;
  click(target: Element): boolean;
  /** Call after moving a frame or refining its source-owned plot geometry. */
  refresh(target?: Element): void;
  cleanup(): void;
}
export interface PlotLayoutRequest {
  width: number;
  mode: "fit" | "actual" | "custom";
  /** Row layouts include their measured label track, excluding native scroll gutters. */
  availableWidth?: number;
}
type Mode = "fit" | "actual" | "custom";
interface Dimensions { x: number; y: number; width: number; height: number; naturalWidth: number; naturalHeight: number }
interface Metrics { dimensions: Dimensions; width: number; height: number; viewportWidth: number; viewportHeight: number }
type PlotMedia = SVGElement | HTMLElement;
interface Plot {
  element: HTMLElement; viewport: HTMLElement; svg: PlotMedia; controls: HTMLElement[]; output: HTMLElement;
  mode: Mode; zoom: number; fitScale: number; metrics: Metrics | null;
  left: number; top: number; refreshing: boolean; layers: Map<SVGElement, "x" | "rows">;
}
interface Drag { plot: Plot; pointer: number; x: number; y: number; left: number; top: number; moved: boolean }
const PLOT = "[data-av-plot],.av-plot-shell";
const CONTROL = "[data-av-fit-width],[data-av-actual-size],[data-av-zoom-in],[data-av-zoom-out],[data-av-zoom-reset]";
const MIN_ZOOM = 1, MAX_ZOOM = 4, ZOOM_STEP = .25;
const finite = (value: number, fallback = 0): number => Number.isFinite(value) ? value : fallback;
const positive = (value: number, fallback: number): number => Number.isFinite(value) && value > 0 ? value : fallback;
function length(value: string | null): number {
  return value !== null && /^\s*(?:\d+(?:\.\d*)?|\.\d+)(?:px)?\s*$/.test(value) ? Number.parseFloat(value) : 0;
}
function priority(style: CSSStyleDeclaration, name: string): string {
  return typeof style.getPropertyPriority === "function" ? style.getPropertyPriority(name) : "";
}
function dimensions(svg: Element): Dimensions {
  const values = (svg.getAttribute("viewBox") || svg.getAttribute("viewbox") || "").trim().split(/[\s,]+/).map(Number);
  const valid = values.length === 4 && values.every(Number.isFinite) && values[2] > 0 && values[3] > 0;
  const naturalWidth = positive(length(svg.getAttribute("width")), (svg as HTMLImageElement).naturalWidth || (valid ? values[2] : 900));
  const naturalHeight = positive(length(svg.getAttribute("height")), (svg as HTMLImageElement).naturalHeight || (valid ? values[3] : 400));
  return { x: valid ? values[0] : 0, y: valid ? values[1] : 0, width: valid ? values[2] : naturalWidth, height: valid ? values[3] : naturalHeight, naturalWidth, naturalHeight };
}

export function attachPlots(root: HTMLElement): PlotController {
  const document = root.ownerDocument, window = document.defaultView;
  const undo: (() => void)[] = [], plots = new Map<Element, Plot>(), controlOwners = new Map<Element, Plot>();
  const saved = new WeakMap<Element, Set<string>>(), savedStyles = new WeakMap<Element, Set<string>>();
  const suppressed = new WeakSet<Element>();
  let drag: Drag | null = null, cleaned = false;
  const all = <T extends Element = HTMLElement>(selector: string): T[] => [...(root.matches(selector) ? [root as unknown as T] : []), ...Array.from(root.querySelectorAll<T>(selector))];
  function listen(target: EventTarget, type: string, listener: EventListener, capture = false): void {
    target.addEventListener(type, listener, capture); undo.push(() => target.removeEventListener(type, listener, capture));
  }
  function attribute(element: Element, name: string, value: string | null): void {
    const names = saved.get(element) || new Set<string>();
    if (!names.has(name)) {
      names.add(name); saved.set(element, names); const original = element.getAttribute(name);
      undo.push(() => original === null ? element.removeAttribute(name) : element.setAttribute(name, original));
    }
    if (value === null) { if (element.hasAttribute(name)) element.removeAttribute(name); }
    else if (element.getAttribute(name) !== value) element.setAttribute(name, value);
  }
  // Restore only owned declarations: theme/refinement code may own other styles.
  function style(element: HTMLElement | SVGElement, name: string, value: string | null, importance = ""): void {
    let names = savedStyles.get(element);
    if (!names) {
      names = new Set(); savedStyles.set(element, names);
      const absent = element.getAttribute("style") === null;
      undo.push(() => { if (absent && !(element.getAttribute("style") || "").trim()) element.removeAttribute("style"); });
    }
    if (!names.has(name)) {
      names.add(name); const previous = element.style.getPropertyValue(name), previousPriority = priority(element.style, name);
      undo.push(() => { if (previous) element.style.setProperty(name, previous, previousPriority); else element.style.removeProperty(name); });
    }
    if (value === null || value === "") { if (element.style.getPropertyValue(name)) element.style.removeProperty(name); }
    else if (element.style.getPropertyValue(name) !== value || priority(element.style, name) !== importance) element.style.setProperty(name, value, importance);
  }
  function scoped<T extends Element = HTMLElement>(element: Element, selector: string): T[] {
    return Array.from(element.querySelectorAll<T>(selector)).filter(item => item.closest(PLOT) === element);
  }
  function limits(plot: Plot): [number, number] {
    return [Math.max(0, finite(plot.viewport.scrollWidth) - finite(plot.viewport.clientWidth)), Math.max(0, finite(plot.viewport.scrollHeight) - finite(plot.viewport.clientHeight))];
  }
  function overflow(plot: Plot): boolean { return limits(plot).some(value => value > 1); }
  function measure(plot: Plot, box = dimensions(plot.svg)): Metrics {
    const rectangle = plot.svg.getBoundingClientRect(), width = positive(rectangle.width, box.naturalWidth);
    const height = positive(rectangle.height, width * box.naturalHeight / box.naturalWidth);
    return { dimensions: box, width, height, viewportWidth: Math.max(0, finite(plot.viewport.clientWidth)), viewportHeight: Math.max(0, finite(plot.viewport.clientHeight)) };
  }
  function position(plot: Plot, left: number, top: number): void {
    const [maxLeft, maxTop] = limits(plot);
    plot.viewport.scrollLeft = Math.max(0, Math.min(maxLeft, finite(left)));
    plot.viewport.scrollTop = Math.max(0, Math.min(maxTop, finite(top)));
    plot.left = plot.viewport.scrollLeft; plot.top = plot.viewport.scrollTop;
  }
  function collectLayers(plot: Plot): void {
    for (const layer of scoped<SVGElement>(plot.element, "svg[data-av-axis-layer]")) {
      const kind = layer.getAttribute("data-av-axis-layer");
      if (kind === "x" || kind === "rows") plot.layers.set(layer, kind);
    }
  }
  function layers(plot: Plot): void {
    collectLayers(plot);
    const metrics = plot.metrics;
    if (!metrics) return;
    const scaleX = metrics.width / metrics.dimensions.width, scaleY = metrics.height / metrics.dimensions.height;
    style(plot.element, "--av-plot-scale", String(scaleX));
    style(plot.element, "--av-pan-x", `${plot.left}px`); style(plot.element, "--av-pan-y", `${plot.top}px`);
    style(plot.element, "--av-plot-rendered-width", `${metrics.width}px`); style(plot.element, "--av-plot-rendered-height", `${metrics.height}px`);
    let rowWidth = 0, axisHeight = 0;
    for (const [layer, kind] of plot.layers) {
      if (!plot.element.contains(layer)) continue;
      const box = dimensions(layer);
      // Row identities keep their fitted width and readable type while their
      // centers follow the zoomed observations. The label column never pans sideways.
      const width = kind === "rows" ? box.naturalWidth * plot.fitScale : box.width * scaleX;
      const height = kind === "rows" ? box.naturalHeight * scaleY : box.height * scaleY;
      if (kind === "rows") {
        const stretch = scaleY / plot.fitScale;
        attribute(layer, "preserveAspectRatio", "none");
        for (const row of Array.from(layer.querySelectorAll<SVGGElement>("[data-av-row-center]"))) {
          const center = Number(row.getAttribute("data-av-row-center"));
          if (Number.isFinite(center)) attribute(row, "transform", `translate(0 ${center}) scale(1 ${1 / stretch}) translate(0 ${-center})`);
        }
      }
      style(layer, "width", `${width}px`); style(layer, "height", `${height}px`);
      style(layer, "min-width", "0"); style(layer, "max-width", "none");
      style(layer, "transform", kind === "x" ? `translateX(${-plot.left}px)` : `translateY(${-plot.top}px)`);
      style(layer, "transform-origin", "0 0");
      if (kind === "rows") rowWidth = Math.max(rowWidth, width); else axisHeight = Math.max(axisHeight, height);
    }
    style(plot.element, "--av-axis-row-width", `${rowWidth}px`); style(plot.element, "--av-axis-x-height", `${axisHeight}px`);
  }
  function update(plot: Plot, announce = false): void {
    const mode=plot.element.closest('[data-av-selection-mode]')?.getAttribute('data-av-selection-mode')||'pan';
    attribute(plot.viewport, "data-av-pan", overflow(plot)&&mode==='pan' ? "ready" : null);
    attribute(plot.element, "data-av-zoom", String(plot.zoom)); attribute(plot.element, "data-av-viewport-mode", plot.mode);
    for (const control of plot.controls) {
      const disabled = control.hasAttribute("data-av-zoom-in") ? plot.zoom >= MAX_ZOOM
        : control.hasAttribute("data-av-zoom-out") ? plot.zoom <= MIN_ZOOM
        : control.hasAttribute("data-av-zoom-reset") ? plot.mode === "fit" && plot.zoom === 1 && plot.left === 0 && plot.top === 0 : false;
      attribute(control, "disabled", disabled ? "" : null);
      if (control.hasAttribute("data-av-fit-width")) attribute(control, "aria-pressed", String(plot.mode === "fit"));
      if (control.hasAttribute("data-av-actual-size")) attribute(control, "aria-pressed", String(plot.mode === "actual"));
    }
    layers(plot);
    if (announce) {
      const percent = Math.round(plot.zoom * 1000) / 10;
      const text = `${percent}% zoom.${plot.element.closest('[data-av-selection-mode="text"]') ? " Text selection mode." : mode==='select' ? ' Select an item to inspect it.' : overflow(plot) ? " Drag to pan, or focus the plot and use the arrow keys." : " The chart fits the available width."}`;
      if (plot.output.textContent !== text) plot.output.textContent = text;
    }
  }
  function finish(): void {
    const previous = drag; drag = null;
    if (!previous) return;
    attribute(previous.plot.viewport, "data-av-dragging", null);
    if (previous.moved) suppressed.add(previous.plot.viewport);
    try { previous.plot.viewport.releasePointerCapture?.(previous.pointer); } catch { /* Native capture may already be lost. */ }
  }
  function markPoint(plot: Plot, item: SVGGraphicsElement): { x: number; y: number } {
    const box = item.getBBox(); let x = box.x + box.width / 2, y = box.y + box.height / 2;
    const owner = plot.svg as SVGGraphicsElement;
    if (typeof item.getScreenCTM === "function" && typeof owner.getScreenCTM === "function") {
      const matrix = item.getScreenCTM(), rootMatrix = owner.getScreenCTM();
      if (matrix && rootMatrix) {
        const determinant = rootMatrix.a * rootMatrix.d - rootMatrix.b * rootMatrix.c;
        if (Number.isFinite(determinant) && determinant !== 0) {
          const screenX = matrix.a * x + matrix.c * y + matrix.e - rootMatrix.e;
          const screenY = matrix.b * x + matrix.d * y + matrix.f - rootMatrix.f;
          x = (rootMatrix.d * screenX - rootMatrix.c * screenY) / determinant;
          y = (-rootMatrix.b * screenX + rootMatrix.a * screenY) / determinant;
        }
      }
    }
    return { x, y };
  }
  function selected(plot: Plot, metrics: Metrics): SVGGraphicsElement | null {
    for (const item of scoped<SVGGraphicsElement>(plot.element, "[data-av-inspect]")) {
      if (!plot.svg.contains(item) || item.getAttribute("aria-pressed") !== "true" || typeof item.getBBox !== "function") continue;
      try {
        const point = markPoint(plot, item), x = (point.x - metrics.dimensions.x) * metrics.width / metrics.dimensions.width - plot.left;
        const y = (point.y - metrics.dimensions.y) * metrics.height / metrics.dimensions.height - plot.top;
        if (x >= 0 && x <= metrics.viewportWidth && y >= 0 && y <= metrics.viewportHeight) return item;
      } catch { /* Unmeasurable or hidden marks do not change the viewport anchor. */ }
    }
    return null;
  }
  function keepVisible(plot: Plot, item: SVGGraphicsElement | null): void {
    if (!item || !plot.svg.contains(item) || !plot.metrics) return;
    try {
      const point = markPoint(plot, item), metrics = plot.metrics;
      const x = (point.x - metrics.dimensions.x) * metrics.width / metrics.dimensions.width;
      const y = (point.y - metrics.dimensions.y) * metrics.height / metrics.dimensions.height;
      const marginX = Math.min(16, metrics.viewportWidth / 4), marginY = Math.min(16, metrics.viewportHeight / 4);
      const left = x < plot.left + marginX ? x - marginX : x > plot.left + metrics.viewportWidth - marginX ? x - metrics.viewportWidth + marginX : plot.left;
      const top = y < plot.top + marginY ? y - marginY : y > plot.top + metrics.viewportHeight - marginY ? y - metrics.viewportHeight + marginY : plot.top;
      position(plot, left, top);
    } catch { /* Exact evidence remains available when a mark has no native box. */ }
  }
  function fitSize(plot: Plot, box: Dimensions): { width: number; availableWidth?: number } {
    const expanded = plot.element.closest<HTMLElement>('[data-av-expanded-figure]');
    const declaredWidth = Number(expanded?.getAttribute('data-av-fit-width'));
    const viewportWidth = declaredWidth > 0 ? declaredWidth : Math.max(0, finite(plot.viewport.clientWidth));
    if (!plot.element.classList.contains("av-row-plot")) return { width: viewportWidth };
    const row = [...plot.layers].find(([element, kind]) => kind === "rows" && plot.element.contains(element))?.[0];
    const layout = row?.closest<HTMLElement>(".av-row-plot-layout");
    if (!row || !layout || !row.parentElement) return { width: viewportWidth };
    const rowWidth = dimensions(row).width;
    const measured = viewportWidth + Math.max(0, finite(row.parentElement.clientWidth));
    const availableWidth = declaredWidth > 0 ? declaredWidth : Math.min(measured, Math.max(0, finite(layout.clientWidth, measured)));
    return { width: availableWidth * box.width / (box.width + rowWidth), availableWidth };
  }
  function requestLayout(plot: Plot, width: number, availableWidth?: number): void {
    const EventType = window?.CustomEvent;
    const detail: PlotLayoutRequest = { width, mode: plot.mode === "actual" ? "actual" : "fit", ...(availableWidth === undefined ? {} : { availableWidth }) };
    if (typeof EventType === "function") plot.element.dispatchEvent(new EventType("av-layout-request", { bubbles: true, detail }));
  }
  function refreshPlot(plot: Plot, requested?: { mode: Mode; zoom?: number; reset?: boolean }, forceLayout = false): void {
    if (cleaned || plot.refreshing) return;
    collectLayers(plot);
    const observed = measure(plot), previous = plot.metrics, initialFit = fitSize(plot, observed.dimensions);
    if (observed.viewportWidth <= 0 && !(initialFit.availableWidth && initialFit.availableWidth > 0)) return; // A measurable row layout can bootstrap a cramped data lane; genuinely hidden frames retain their anchor.
    plot.refreshing = true;
    try {
      const sameSize = previous && previous.viewportWidth === observed.viewportWidth && previous.viewportHeight === observed.viewportHeight && Math.abs(previous.width - observed.width) < .01 && Math.abs(previous.height - observed.height) < .01;
      if (sameSize) { plot.left = finite(plot.viewport.scrollLeft); plot.top = finite(plot.viewport.scrollTop); }
      const anchorX = previous ? previous.dimensions.x + (plot.left + previous.viewportWidth / 2) * previous.dimensions.width / previous.width : 0;
      const anchorY = previous ? previous.dimensions.y + (plot.top + previous.viewportHeight / 2) * previous.dimensions.height / previous.height : 0;
      const mark = previous ? selected(plot, previous) : null;
      const originX = plot.left === 0, originY = plot.top === 0;
      if (requested) { finish(); plot.mode = requested.mode; if (requested.zoom !== undefined) plot.zoom = requested.zoom; }
      const box = dimensions(plot.svg);
      const desired = plot.mode === "actual" ? box.naturalWidth : initialFit.width;
      const resized = !previous || previous.viewportWidth !== observed.viewportWidth || previous.viewportHeight !== observed.viewportHeight;
      if (requested || resized || forceLayout) requestLayout(plot, positive(desired, box.naturalWidth), initialFit.availableWidth);
      const refined = dimensions(plot.svg);
      let fittedWidth = positive(fitSize(plot, refined).width, refined.naturalWidth);
      const expanded = plot.element.closest<HTMLElement>('[data-av-expanded-figure]'), availableHeight = Number(expanded?.getAttribute('data-av-fit-height'));
      if (availableHeight > 0) {
        const axisHeight = Math.max(0, ...[...plot.layers].filter(([, kind]) => kind === 'x').map(([layer]) => dimensions(layer).naturalHeight));
        fittedWidth = Math.min(fittedWidth, refined.naturalWidth * availableHeight / (refined.naturalHeight + axisHeight));
      }
      plot.fitScale = fittedWidth / refined.naturalWidth;
      if (plot.mode === "fit") plot.zoom = 1;
      if (plot.mode === "actual") plot.zoom = refined.naturalWidth / fittedWidth;
      const width = fittedWidth * plot.zoom;
      style(plot.svg, "width", `${width}px`); style(plot.svg, "height", plot.svg.hasAttribute('data-av-custom-media') ? `${refined.naturalHeight*width/refined.naturalWidth}px` : "auto");
      if(plot.svg.hasAttribute('data-av-custom-media')){style(plot.svg,'--av-custom-width',`${refined.naturalWidth}px`);style(plot.svg,'--av-custom-height',`${refined.naturalHeight}px`);style(plot.svg,'--av-custom-scale',String(width/refined.naturalWidth));}
      style(plot.svg, "min-width", "0"); style(plot.svg, "max-width", "none");
      // Default/reset shows the complete scene. Zoom adds pan space without
      // growing the entire report or giving the row identities another scrollbar.
      style(plot.element, "--av-plot-fit-height", `${Math.ceil(refined.naturalHeight * plot.fitScale)}px`);
      plot.metrics = measure(plot, refined);
      layers(plot); // The synchronized row track can change the available body width.
      plot.metrics = measure(plot, refined);
      if (requested?.reset) position(plot, 0, 0);
      else if (previous) {
        const x = (anchorX - refined.x) * plot.metrics.width / refined.width - plot.metrics.viewportWidth / 2;
        const y = (anchorY - refined.y) * plot.metrics.height / refined.height - plot.metrics.viewportHeight / 2;
        position(plot, !requested && originX ? 0 : x, !requested && originY ? 0 : y); keepVisible(plot, mark);
      } else position(plot, plot.left, plot.top);
      update(plot, true);
      if (drag?.plot === plot && (!overflow(plot) || resized)) finish();
    } finally { plot.refreshing = false; }
  }

  for (const element of all<HTMLElement>(PLOT)) {
    const svg = scoped<PlotMedia>(element, "[data-av-zoom-target]")[0] || scoped<PlotMedia>(element, "svg,canvas,img").find(item => !item.hasAttribute("data-av-axis-layer"));
    const viewport = scoped<HTMLElement>(element, ".av-plot-scroll")[0];
    if (!svg || !viewport) continue;
    let output = scoped<HTMLElement>(element, "[data-av-zoom-status]")[0];
    if (!output) {
      output = document.createElement("output"); output.className = "av-zoom-value av-sr-only"; output.setAttribute("data-av-zoom-status", "");
      const toolbar = scoped<HTMLElement>(element, "[data-av-controls]")[0] || element; toolbar.appendChild(output);
      const generated = output; undo.push(() => generated.remove());
    }
    const content = Array.from(output.childNodes), originalLeft = viewport.scrollLeft, originalTop = viewport.scrollTop;
    undo.push(() => { output!.textContent = ""; for (const node of content) output!.appendChild(node); viewport.scrollLeft = originalLeft; viewport.scrollTop = originalTop; });
    attribute(output, "role", "status"); attribute(output, "aria-live", "polite"); attribute(output, "aria-atomic", "true");
    const plot: Plot = { element, viewport, svg, output, controls: [], mode: "fit", zoom: 1, fitScale: 1, metrics: null, left: finite(originalLeft), top: finite(originalTop), refreshing: false, layers: new Map() };
    plots.set(element, plot);
    listen(element, "av-layout-invalidated", (() => {if(plot.element.closest('[data-av-selection-mode]')?.getAttribute('data-av-selection-mode')!=='pan'){finish();suppressed.delete(plot.viewport);}refreshPlot(plot, undefined, true);}) as EventListener);
    if (!viewport.hasAttribute("tabindex")) attribute(viewport, "tabindex", "0");
    if (!viewport.hasAttribute("role")) attribute(viewport, "role", "region");
    if (!viewport.hasAttribute("aria-label")) attribute(viewport, "aria-label", svg.querySelector("title")?.textContent || svg.getAttribute("aria-label") || "Plot viewport");
    listen(viewport, "scroll", (() => {
      if (plot.refreshing || cleaned) return;
      const now = measure(plot), old = plot.metrics;
      if (old && (old.viewportWidth !== now.viewportWidth || old.viewportHeight !== now.viewportHeight || Math.abs(old.width - now.width) > .01 || Math.abs(old.height - now.height) > .01)) refreshPlot(plot);
      else { plot.left = finite(viewport.scrollLeft); plot.top = finite(viewport.scrollTop); update(plot); }
    }) as EventListener);
    listen(viewport, "pointerdown", ((event: PointerEvent) => {
      if (event.button !== 0 || event.isPrimary === false || (plot.element.closest('[data-av-selection-mode]')?.getAttribute('data-av-selection-mode')||'pan')!=='pan') return;
      suppressed.delete(viewport);
      if (event.pointerType === "touch") return;
      refreshPlot(plot);
      const target = event.target as Element | null;
      if (!overflow(plot) || target?.closest("a[href],button,input,select,textarea,[contenteditable]")) return;
      finish(); drag = { plot, pointer: event.pointerId, x: event.clientX, y: event.clientY, left: viewport.scrollLeft, top: viewport.scrollTop, moved: false };
    }) as EventListener);
    listen(viewport, "lostpointercapture", ((event: PointerEvent) => { if (drag?.plot === plot && drag.pointer === event.pointerId) finish(); }) as EventListener);
    listen(viewport, "click", ((event: MouseEvent) => {
      if (!suppressed.has(viewport)) return;
      suppressed.delete(viewport);
      if (event.detail === 0 && !(event as PointerEvent).pointerType) return;
      event.preventDefault(); event.stopPropagation();
    }) as EventListener, true);
  }

  // Resolve once, before the host moves toolbar nodes into the shared frame bar.
  for (const control of all<HTMLElement>(CONTROL)) {
    let plot = plots.get(control.closest(PLOT)!);
    if (!plot) {
      const reference = control.closest("[data-av-plot-for]")?.getAttribute("data-av-plot-for"), frame = control.closest(".av-card");
      const candidates = [...plots.values()].filter(item => reference !== undefined && reference !== null
        ? item.element.getAttribute("data-av-plot-key") === reference && (!frame || item.element.closest(".av-card") === frame)
        : frame ? item.element.closest(".av-card") === frame : plots.size === 1);
      if (candidates.length === 1) plot = candidates[0];
    }
    if (!plot) continue;
    controlOwners.set(control, plot); plot.controls.push(control);
    if (!control.hasAttribute("aria-label")) {
      const title = plot.svg.querySelector("title")?.textContent || "plot";
      const action = control.hasAttribute("data-av-fit-width") ? "Fit width for" : control.hasAttribute("data-av-actual-size") ? "Show actual size for" : control.hasAttribute("data-av-zoom-reset") ? "Reset zoom and fit" : control.hasAttribute("data-av-zoom-in") ? "Zoom in" : "Zoom out";
      attribute(control, "aria-label", `${action} ${title}`);
    }
  }
  for (const plot of plots.values()) refreshPlot(plot);
  const Observer = window?.ResizeObserver;
  if (Observer) for (const plot of plots.values()) {
    const observer = new Observer(() => refreshPlot(plot)); observer.observe(plot.viewport); observer.observe(plot.svg); undo.push(() => observer.disconnect());
  }
  if (window) {
    listen(window, "resize", (() => { for (const plot of plots.values()) refreshPlot(plot); }) as EventListener);
    listen(window, "blur", finish as EventListener);
  }
  listen(document, "pointermove", ((event: PointerEvent) => {
    if (!drag || drag.pointer !== event.pointerId) return;
    if (event.buttons === 0) { finish(); return; }
    const dx = event.clientX - drag.x, dy = event.clientY - drag.y;
    if (!drag.moved && Math.hypot(dx, dy) < 4) return;
    if (!drag.moved) { drag.moved = true; try { drag.plot.viewport.setPointerCapture?.(drag.pointer); } catch { /* Document listeners cover movement while inside this document. */ } }
    attribute(drag.plot.viewport, "data-av-dragging", ""); event.preventDefault();
    position(drag.plot, drag.left - dx, drag.top - dy); update(drag.plot);
  }) as EventListener);
  for (const type of ["pointerup", "pointercancel"]) listen(document, type, ((event: PointerEvent) => { if (drag?.pointer === event.pointerId) finish(); }) as EventListener);

  return {
    snapshot(target) { return { entries: [...plots.values()].filter(plot => target === plot.element || target.contains(plot.element)).map(plot => ({ element: plot.element, mode: plot.mode, zoom: plot.zoom, left: plot.viewport.scrollLeft, top: plot.viewport.scrollTop })) }; },
    fit(target) { for (const plot of plots.values()) if (target === plot.element || target.contains(plot.element)) refreshPlot(plot, {mode:'fit',zoom:1,reset:true}); },
    restore(snapshot) { for (const entry of snapshot.entries) { const plot=plots.get(entry.element); if(plot){plot.mode=entry.mode;plot.zoom=entry.zoom;plot.left=entry.left;plot.top=entry.top;plot.metrics=null;refreshPlot(plot);} } },
    click(target) {
      const control = target.closest(CONTROL), plot = control ? controlOwners.get(control) : undefined;
      if (!control || !plot || cleaned) return false;
      if (control.hasAttribute("disabled")) return true;
      if (control.hasAttribute("data-av-fit-width")) refreshPlot(plot, { mode: "fit", zoom: 1, reset: true });
      else if (control.hasAttribute("data-av-actual-size")) refreshPlot(plot, { mode: "actual", zoom: 1 });
      else if (control.hasAttribute("data-av-zoom-reset")) refreshPlot(plot, { mode: "fit", zoom: 1, reset: true });
      else refreshPlot(plot, { mode: "custom", zoom: control.hasAttribute("data-av-zoom-in") ? Math.min(MAX_ZOOM, plot.zoom + ZOOM_STEP) : Math.max(MIN_ZOOM, plot.zoom - ZOOM_STEP) });
      return true;
    },
    refresh(target) { if (!cleaned) for (const plot of plots.values()) if (!target || target === plot.element || target.contains(plot.element) || plot.element.contains(target)) refreshPlot(plot); },
    cleanup() { if (cleaned) return; finish(); cleaned = true; for (const restore of undo.reverse()) restore(); controlOwners.clear(); plots.clear(); },
  };
}
