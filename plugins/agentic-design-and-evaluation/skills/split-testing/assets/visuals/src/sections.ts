/** Section names a narrative may use, and the one resolution of a record keyed by them (a narrative's readings), shared
 * by both compositions and the checks, so what the checks assess is what the page shows. */
import { entriesOf } from "./core";

/** Earlier ids that still name a trial report's default sections. */
export const TRIAL_SECTION_ALIASES: Record<string, string> = { plan: "setup" };
/** Other names a comparison report's sections answer to. */
export const COMPARISON_SECTION_ALIASES: Record<string, string> = { setup: "compared", alternatives: "compared", metrics: "results", hierarchy: "groups", preferences: "judgments", pairwise: "judgments", matrix: "decision", ledger: "observations", runs: "observations" };
const via = (aliases: Record<string, string>) => (id: unknown): string => { const k = String(id); return Object.prototype.hasOwnProperty.call(aliases, k) ? aliases[k] : k; };
/** The trial section a name stands for. */
export const trialSection = via(TRIAL_SECTION_ALIASES);
/** The comparison section a name stands for. */
export const comparisonSection = via(COMPARISON_SECTION_ALIASES);

/** A record keyed by section names, resolved: each section's value is that of the first key naming it, in the record's
 * own order (entriesOf: a "$" key is a note), and each later key naming the same section is a clash, kept with both
 * keys. Both compositions show exactly `values`; the checks assess exactly `values` and refuse every clash. */
export function resolveSections(record: unknown, section: (id: string) => string): { values: Map<string, unknown>; keys: Map<string, string>; clashes: Array<{ section: string; first: string; again: string }> } {
  const values = new Map<string, unknown>(), keys = new Map<string, string>(), clashes: Array<{ section: string; first: string; again: string }> = [];
  for (const [k, v] of entriesOf(record)) {
    const s = section(k);
    if (keys.has(s)) clashes.push({ section: s, first: keys.get(s)!, again: k });
    else { keys.set(s, k); values.set(s, v); }
  }
  return { values, keys, clashes };
}
