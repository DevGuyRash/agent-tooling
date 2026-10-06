/** Compose a report specification from any comparison, and turn trial data into one (stubs; being implemented). */
import type { Comparison } from "./comparison-model";
import type { ReportSpec, SectionSpec, BlockSpec, ArmSpec } from "./model";
import type { TrialReport } from "./trial-model";

export interface ComparisonNarrative {
  title?: string; question?: string; summary?: string | string[]; kicker?: string;
  decision?: { verdict?: "adopt" | "reject" | "inconclusive" | "mixed" | "none"; label?: string; headline: string; detail?: string | string[]; checks?: Array<{ label: string; observed: string; threshold?: string; met?: boolean | null; group?: string }>; conditions?: string[]; limits?: string[]; changes?: string[] };
  alternatives?: ArmSpec[] | Record<string, { label?: string; note?: string }>;
  include?: string[]; exclude?: string[];
  sections?: Array<SectionSpec & { after?: string }>;
  append?: Record<string, BlockSpec[]>;
  footer?: string;
}

export function comparisonReport(data: Comparison, narrative: ComparisonNarrative = {}): ReportSpec {
  void narrative;
  return { title: data.title || data.question || "Comparison", sections: [], comparison: data };
}

export function fromTrial(trial: TrialReport): Comparison {
  void trial; return { alternatives: [], metrics: [] };
}
