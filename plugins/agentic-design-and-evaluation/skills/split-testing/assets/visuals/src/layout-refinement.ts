import { pairedComparison, intervalPlot, distribution, trajectory, scatterPlot } from "./quantitative";
import { evidenceFreshness } from "./landscape";
import { evidenceLineage } from "./qualitative";
import { browserTextMeasure } from "./text-layout";

/** Recompute geometry from retained original inputs; no evidence or reader records change. */
export function attachLayoutRefinement(root: HTMLElement): () => void {
  const document = root.ownerDocument, window = document.defaultView;
  const cache = new WeakMap<HTMLElement, string>();
  const frames = new Set<HTMLElement>([...(root.matches(".av-card[data-av-layout-kind]") ? [root] : []), ...Array.from(root.querySelectorAll<HTMLElement>(".av-card[data-av-layout-kind]"))]);
  // The retained occurrence identifies a plot within its original recipe even
  // when inspection or author composition moves the live frame or its contents.
  const plotOwners = new Map<HTMLElement, { frame: HTMLElement; index: number; count: number }>();
  for (const frame of frames) {
    const plots = framePlots(frame);
    plots.forEach((plot, index) => plotOwners.set(plot, { frame, index, count: plots.length }));
  }
  let stopped = false, fontEpoch = 0;
  const restorations = new Map<SVGElement, { attributes: Map<string, string | null>; children: Node[] }>();
  const statuses: HTMLElement[] = [];
  function render(kind: string, value: unknown): string {
    // These explicit library constructors validate their own data; no function name is evaluated.
    switch (kind) {
      case "paired": return pairedComparison(value as Parameters<typeof pairedComparison>[0]);
      case "interval": return intervalPlot(value as Parameters<typeof intervalPlot>[0]);
      case "distribution": return distribution(value as Parameters<typeof distribution>[0]);
      case "trajectory": return trajectory(value as Parameters<typeof trajectory>[0]);
      case "scatter": return scatterPlot(value as Parameters<typeof scatterPlot>[0]);
      case "freshness": return evidenceFreshness(value as Parameters<typeof evidenceFreshness>[0]);
      case "lineage": return evidenceLineage(value as Parameters<typeof evidenceLineage>[0]);
      default: throw new Error("Unknown chart layout recipe.");
    }
  }
  function framePlots(frame: Element): HTMLElement[] {
    return Array.from(frame.querySelectorAll<HTMLElement>("[data-av-plot]")).filter(plot => plot.closest(".av-card") === frame);
  }
  function scenes(plot: HTMLElement): SVGElement[] {
    return Array.from(plot.querySelectorAll<SVGElement>("svg[data-av-zoom-target],svg[data-av-axis-layer]")).filter(svg => svg.closest("[data-av-plot]") === plot);
  }
  function patch(target: SVGElement, source: SVGElement): void {
    const active = document.activeElement;
    const focused = active && target.contains(active) ? active as SVGElement : null;
    if (!restorations.has(target)) restorations.set(target, { attributes: new Map(["width", "height", "viewBox"].map(name => [name, target.getAttribute(name)])), children: Array.from(target.childNodes).map(node => node.cloneNode(true)) });
    const prior = new Map(Array.from(target.querySelectorAll<SVGElement>("[data-av-inspect]")).map(element => [element.getAttribute("data-av-inspect")!, element]));
    for (const incoming of Array.from(source.querySelectorAll<SVGElement>("[data-av-inspect]"))) {
      const old = prior.get(incoming.getAttribute("data-av-inspect")!);
      if (!old || old.tagName !== incoming.tagName) continue;
      const selected = old.classList.contains("av-selected"), related = old.classList.contains("av-related");
      for (const name of ["class", "d", "points", "x", "y", "width", "height", "cx", "cy", "r", "fill", "stroke"]) {
        const next = incoming.getAttribute(name); if (next === null) old.removeAttribute(name); else old.setAttribute(name, next);
      }
      old.classList.toggle("av-selected", selected); old.classList.toggle("av-related", related);
      old.replaceChildren(...Array.from(incoming.childNodes)); incoming.replaceWith(old);
    }
    for (const name of ["width", "height", "viewBox"]) { const value = source.getAttribute(name); if (value !== null) target.setAttribute(name, value); }
    target.replaceChildren(...Array.from(source.childNodes));
    if (focused?.isConnected && document.activeElement !== focused) focused.focus?.({ preventScroll: true });
  }
  function refine(event: Event): void {
    if (stopped) return;
    const target = event.target as HTMLElement | null;
    const plot = target?.closest<HTMLElement>("[data-av-plot]");
    const owner = plot && plotOwners.get(plot);
    if (!plot || !owner) return;
    const { frame, index, count } = owner;
    const source = frame.getAttribute("data-av-layout-input"), kind = frame.getAttribute("data-av-layout-kind");
    if (!source || !kind || !window?.getComputedStyle) return;
    const detail = (event as CustomEvent<{ width: number; mode: string; availableWidth?: number }>).detail;
    const sample = plot.querySelector("svg text") || plot;
    const computed = window.getComputedStyle(sample), font = `500 14px ${computed.fontFamily || "sans-serif"}`;
    const measure = browserTextMeasure(document, font);
    if (!measure) return;
    try {
      const input = JSON.parse(source);
      if (!input || typeof input !== "object" || Array.isArray(input)) throw new Error("Invalid chart layout input.");
      const axis = plot.querySelector<SVGElement>('[data-av-axis-layer="rows"]');
      const rowWidth = axis ? Number(axis.getAttribute("width")) || 0 : 0;
      const width = detail?.mode === "fit" && Number.isFinite(detail.width) && detail.width > 0 ? Math.max(240, detail.availableWidth || detail.width + rowWidth) : input.context?.width ?? 900;
      const key = JSON.stringify([width, font, fontEpoch]);
      if (cache.get(plot) === key) return;
      const template = document.createElement("template");
      if (!template.content) return;
      template.innerHTML = render(kind, { ...input, context: { ...input.context, width, measureText: measure } });
      const fresh = template.content.querySelector<HTMLElement>(".av-card");
      if (!fresh) throw new Error("The chart layout could not be reconstructed.");
      const freshPlots = framePlots(fresh);
      if (freshPlots.length !== count) throw new Error("The chart layout changed its retained plot set.");
      const oldScenes = scenes(plot), newScenes = scenes(freshPlots[index]);
      if (oldScenes.length !== newScenes.length || oldScenes.some((scene, position) => scene.getAttribute("data-av-axis-layer") !== newScenes[position].getAttribute("data-av-axis-layer"))) throw new Error("The chart layout changed its retained scene set.");
      for (let position = 0; position < oldScenes.length; position++) patch(oldScenes[position], newScenes[position]);
      cache.set(plot, key);
    } catch {
      if (!frame.querySelector("[data-av-layout-status]")) {
        const status = document.createElement("p"); status.className = "av-note"; status.setAttribute("data-av-layout-status", ""); status.setAttribute("role", "status");
        status.textContent = "The chart keeps its static layout. Exact values and annotations remain available in Data.";
        frame.appendChild(status); statuses.push(status);
      }
    }
  }
  root.addEventListener("av-layout-request", refine);
  // A moved frame remains in the same enhancement root, except when the frame itself was enhanced.
  document.addEventListener("av-layout-request", refine);
  const ready = document.fonts?.ready;
  ready?.then(() => {
    if (stopped) return;
    fontEpoch++;
    const EventConstructor = window?.CustomEvent;
    if (!EventConstructor) return;
    // The viewport owns its mode and anchor. Ask it to reflow the retained frames,
    // including frames currently moved into inspection outside the original root.
    for (const plot of plotOwners.keys()) plot.dispatchEvent(new EventConstructor("av-layout-invalidated"));
  }).catch(() => undefined);
  return () => {
    if (stopped) return; stopped = true;
    root.removeEventListener("av-layout-request", refine); document.removeEventListener("av-layout-request", refine);
    for (const status of statuses) status.remove();
    // Restore geometry but retain original live interactive nodes wherever present.
    for (const [target, original] of restorations) {
      const temporary = target.cloneNode(false) as SVGElement;
      temporary.replaceChildren(...original.children.map(node => node.cloneNode(true)));
      for (const [name, value] of original.attributes) if (value !== null) temporary.setAttribute(name, value);
      patch(target, temporary);
      for (const [name, value] of original.attributes) if (value === null) target.removeAttribute(name); else target.setAttribute(name, value);
    }
    restorations.clear();
  };
}
