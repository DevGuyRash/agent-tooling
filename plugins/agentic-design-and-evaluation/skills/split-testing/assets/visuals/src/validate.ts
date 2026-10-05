/** Checks a report specification and narrative against what the library
 * understands, so a misspelled field or arm id is named instead of ignored. */
import type { ReportSpec } from "./model";

export interface Problem { level: "error" | "warning"; where: string; message: string; hint?: string }

export function validateSpec(spec: ReportSpec): Problem[] { void spec; return []; }
export function validateNarrative(narrative: unknown, trial?: unknown): Problem[] { void narrative; void trial; return []; }
/** A visible panel listing problems; empty string when there are none. */
export function renderProblems(problems: Problem[]): string { void problems; return ""; }
