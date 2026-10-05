/** Public interface of the split-testing visual library. */
import { enhance, mount } from "./enhance";
import { trialReport } from "./compose";
import type { Narrative } from "./compose";
import type { ReportSpec } from "./model";
import type { TrialReport } from "./trial-model";

export { escapeText, wilson } from "./core";
export { ArmRegistry, createContext } from "./model";
export type { ArmSpec, BlockSpec, MetaItem, ReportSpec, SectionSpec, RenderContext } from "./model";
export type { TrialReport, TrialRun } from "./trial-model";
export { renderReport, renderBlock, registerBlock, blockTypes } from "./report";
export type { BlockRenderer } from "./report";
export { trialReport } from "./compose";
export type { Narrative } from "./compose";
export { enhance, mount } from "./enhance";
export type { Enhancement } from "./enhance";
export { mermaidDiagram } from "./figures";
export { validateSpec, validateNarrative } from "./validate";
export type { Problem } from "./validate";
export { failureCause } from "./failure";
export type { FailureCause } from "./failure";
export { newcombe } from "./stats";
export { lineDiff } from "./diff";
export type { MermaidDiagramInput } from "./figures";
export { browserTextMeasure } from "./text-layout";
export * as blocks from "./blocks/index";

/** Read a JSON block the assembler embedded; null when absent or unreadable. */
function embedded<T>(id: string): T | null {
  const node = typeof document === "undefined" ? null : document.getElementById(id);
  if (!node || node.getAttribute("type") !== "application/json") return null;
  try { return JSON.parse(node.textContent || "null") as T; } catch { return null; }
}

/** Render the report the document carries, if it carries one: a full
 * specification in #av-spec, or trial data in #av-trial with an optional
 * narrative in #av-narrative, into the element marked data-av-mount. */
export function autoMount(): boolean {
  if (typeof document === "undefined") return false;
  const target = document.querySelector<HTMLElement>("[data-av-mount]");
  if (!target || target.hasAttribute("data-av-mounted")) return false;
  const spec = embedded<ReportSpec>("av-spec");
  const trial = embedded<TrialReport>("av-trial");
  if (!spec && !trial) return false;
  target.setAttribute("data-av-mounted", "");
  try {
    if (spec) { if (trial && !spec.trial) spec.trial = trial; mount(target, spec); }
    else mount(target, trialReport(trial!, embedded<Narrative>("av-narrative") || {}));
  } catch (error) {
    target.innerHTML = `<div class="av-block av-block-error" role="alert"><strong>This report could not render.</strong> ${String(error instanceof Error ? error.message : error).replace(/[&<>"']/g, c => `&#${c.charCodeAt(0)};`)}</div>`;
  }
  return true;
}

if (typeof document !== "undefined") {
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", () => { autoMount(); });
  else autoMount();
}
void enhance;
