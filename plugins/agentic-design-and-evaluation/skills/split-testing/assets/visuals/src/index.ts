/** Public interface of the split-testing visual library. */
import { enhance, mount } from "./enhance";
import { trialReport } from "./compose";
import type { Narrative } from "./compose";
import type { ReportSpec } from "./model";
import type { TrialReport } from "./trial-model";
import { comparisonReport, fromTrial } from "./comparison-compose";
import type { ComparisonNarrative } from "./comparison-compose";
import type { Comparison } from "./comparison-model";

export { escapeText, wilson } from "./core";
export { ArmRegistry, createContext } from "./model";
export type { ArmSpec, BlockSpec, MetaItem, ReportSpec, SectionSpec, RenderContext } from "./model";
export type { TrialReport, TrialRun } from "./trial-model";
export { renderReport, renderBlock, registerBlock, blockTypes } from "./report";
export type { BlockRenderer } from "./report";
export { trialReport, SECTION_IDS } from "./compose";
export type { Narrative } from "./compose";
export { casePairs, pairedOrder, invalidReason, tally, trialAxes } from "./trial-model";
export type { CasePair } from "./trial-model";
export { enhance, mount, csvCell, runsCsv } from "./enhance";
export type { Enhancement } from "./enhance";
export { mermaidDiagram } from "./figures";
export { validateSpec, validateNarrative, validateComparison } from "./validate";
export { comparisonReport, fromTrial, COMPARISON_SECTION_IDS } from "./comparison-compose";
export type { ComparisonNarrative, Criterion } from "./comparison-compose";
export { summarize, difference, summarizeGroups, winMatrix, groupPath, groupComparison, metricOf, alternativeIds, judgmentMetric, observationStatus, ordinalLevels, invalidJudgments, superiority, bootstrap, tCdf, tQuantile, tInterval, welch, poolMoments } from "./comparison-stats";
export type { Comparison, Metric, MetricKind, Alternative, Case, Observation, Aggregate, Preference, Ranking, MetricSummary, MetricDifference, ComparisonFilter } from "./comparison-model";
export type { Problem } from "./validate";
export { failureCause } from "./failure";
export type { FailureCause } from "./failure";
export { newcombe } from "./stats";
export { lineDiff, diffRuns, diffStats, wordDiff } from "./diff";
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
 * specification in #av-spec, a comparison in #av-comparison, or trial data in
 * #av-trial, with an optional narrative in #av-narrative, into the element
 * marked data-av-mount. A specification borrows the trial or comparison beside it.
 * Trial data with #av-general set to true is drawn through the comparison views
 * (fromTrial), and its narrative is then a comparison narrative. */
export function autoMount(): boolean {
  if (typeof document === "undefined") return false;
  const target = document.querySelector<HTMLElement>("[data-av-mount]");
  if (!target || target.hasAttribute("data-av-mounted")) return false;
  const spec = embedded<ReportSpec>("av-spec");
  const trial = embedded<TrialReport>("av-trial");
  const comparison = embedded<Comparison>("av-comparison");
  if (!spec && !trial && !comparison) return false;
  target.setAttribute("data-av-mounted", "");
  try {
    if (spec) { if (trial && !spec.trial) spec.trial = trial; if (comparison && !spec.comparison) spec.comparison = comparison; mount(target, spec); }
    else if (comparison) mount(target, comparisonReport(comparison, embedded<ComparisonNarrative>("av-narrative") || {}));
    else if (embedded<boolean>("av-general") === true) mount(target, comparisonReport(fromTrial(trial!), embedded<ComparisonNarrative>("av-narrative") || {}));
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
