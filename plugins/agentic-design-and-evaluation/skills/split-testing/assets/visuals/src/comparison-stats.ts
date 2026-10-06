/** Summaries and differences for every metric kind (stub signatures; being implemented). */
import type { Comparison, ComparisonFilter, MetricDifference, MetricSummary } from "./comparison-model";

/** Each alternative's summary on one metric. */
export function summarize(data: Comparison, metric: string, filter: ComparisonFilter = {}): MetricSummary[] {
  void data; void metric; void filter; return [];
}
/** Alternative a minus alternative b on one metric, with a 95% interval suited to its kind. */
export function difference(data: Comparison, metric: string, a: string, b: string, filter: ComparisonFilter = {}): MetricDifference {
  void data; void filter; return { metric, a, b, estimate: null, interval: null, method: "not implemented" };
}
/** Summaries pooled by group path at one depth (0 = outermost). */
export function summarizeGroups(data: Comparison, metric: string, depth = 0, filter: ComparisonFilter = {}): Array<MetricSummary & { group: string; members: string[] }> {
  void data; void metric; void depth; void filter; return [];
}
/** Head-to-head wins between every pair of alternatives on a preference metric (or overall). */
export function winMatrix(data: Comparison, metric?: string, filter: ComparisonFilter = {}): { ids: string[]; wins: number[][]; ties: number[][] } {
  void data; void metric; void filter; return { ids: [], wins: [], ties: [] };
}
/** The group path of an alternative or case, normalized to an array. */
export function groupPath(group: string[] | string | undefined): string[] {
  return Array.isArray(group) ? group.map(String) : typeof group === "string" && group ? [group] : [];
}
