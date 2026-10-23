/** Checks a report specification or a narrative against what the library
 * understands, so a misspelled block type, field, arm or case is named instead
 * of being silently ignored or drawn as a fact about the trial. An error is
 * input that would break a view or make it misread; a warning is input the
 * report does not use as written. report.py --check applies the same rules
 * without a browser; tests/test_validate.py keeps the two in agreement. */
import { esc, entriesOf, keysIn } from "./core";
import type { ReportSpec } from "./model";
import { blockTypes } from "./report";
import { casePairs, trialArms, wellFormedPair } from "./trial-model";
import { caseKey, NO_CASE } from "./stats";
import type { TrialReport } from "./trial-model";

export interface Problem { level: "error" | "warning"; where: string; message: string; hint?: string }

/** What a field accepts. A string names a scalar kind; objects build lists,
 * keyed records, objects with named fields, enumerations and alternatives.
 * The tables stay plain JSON so report.py can hold the same ones. */
type Field = string | Enum | { list: Field } | { record: Field; keys?: string } | { oneOf: Field[] } | Shape;
interface Enum { enum: string[]; warn?: boolean; fold?: boolean }
/** kn: [passed, valid] field pairs whose first cannot exceed the second. */
interface Shape { fields: Record<string, Field>; required?: string[]; kn?: string[][]; empty?: Record<string, string> }
/** trial: "always" needs trial data; "without-rows" or "without-settings" needs it unless the block carries that field.
 * comparison: "without-data" needs comparison data unless the block carries its own "data". */
interface BlockSchema extends Shape { trial?: "always" | "without-rows" | "without-settings"; comparison?: "without-data"; collection?: "always" }

/** How to read a view: what it shows and how to read it (the library has its own words for each view) and what this data says. */
const READ: Field = { fields: { shows: "prose", how: "prose", says: "prose" } };
const FRAME: Record<string, Field> = { title: "text", description: "prose", note: "text", id: "text", read: READ };
const NUMBER_OR_NULL: Field = { oneOf: ["number", "null"] };
const TONES = ["neutral", "pass", "fail", "invalid", "warn", "accent"];
const TONE: Field = { enum: TONES, warn: true };
const GROUP: Field = { fields: { label: "text", cases: { list: "case" }, note: "text" }, required: ["label", "cases"] };
const CELL_VALUE: Field = { oneOf: ["text", "boolean", "null"] };
const CASE_PAIR: Field = { fields: { base: "case", variant: "case", label: "text", note: "text" }, required: ["base", "variant"] };
const PAIR_LIST: Field = { list: { oneOf: [{ list: "case" }, { fields: { base: "case", variant: "case" }, required: ["base", "variant"] }] } };
const PAIR_SPECS: Field = { list: { oneOf: [{ list: "case" }, { fields: { base: "case", variant: "case", variants: { oneOf: [{ list: "case" }, { record: "text", keys: "case" }] }, label: "text", baseLabel: "text", suffix: "text" } }] } };
const AUTO_OFF: Field = { enum: ["auto", "off"], warn: true };
const CONTRAST_SIDE: Field = { fields: { label: "text", arms: { list: "arm" }, arm: "arm", cases: { list: "case" }, case: "case" } };
const CELL: Field = { oneOf: ["text", "boolean", "null", { fields: { value: CELL_VALUE, status: { enum: TONES }, note: "text", mono: "boolean" } }] };
const VERDICT: Record<string, Field> = {
  verdict: { enum: ["adopt", "reject", "inconclusive", "mixed", "none"], fold: true },
  label: "text", headline: "text", detail: "prose",
  checks: { list: { fields: { label: "text", observed: "text", threshold: "text", met: { oneOf: ["boolean", "null"] }, group: "text" }, required: ["label", "observed"] } },
  conditions: { list: "text" }, limits: { list: "text" }, changes: { list: "text" },
  mentions: { list: "text" }, pairs: { list: CASE_PAIR }, alert: { fields: { text: "text", href: "text", link: "text" }, required: ["text"] },
};

const ALTERNATIVES: Field = { list: "alternative" };
/** What every comparison view reads: its own data or the report's, a metric, and what to narrow to
 * (alternatives, cases, and group-path prefixes for alternatives and cases, outermost first). */
const COMPARE: Record<string, Field> = { ...FRAME, data: "any", metric: "metric", alternatives: ALTERNATIVES, cases: { list: "comparison-case" }, groups: { list: "text" }, caseGroups: { list: "text" }, baseline: "alternative" };
const THRESHOLD: Field = { oneOf: ["number", "null", { fields: { value: "number", label: "text" }, required: ["value"] }] };
const CENTER: Field = { enum: ["mean", "median"], warn: true };
const CRITERION_FIELDS: Record<string, Field> = { id: "text", label: "text", weight: "number", better: { enum: ["higher", "lower", "none"] }, description: "text", note: "text", metric: "metric", scores: { record: { oneOf: ["text", "boolean", "null"] }, keys: "alternative-ref" } };
const DECISION_CELL: Field = { fields: { criterion: "text", alternative: "alternative-ref", rating: { oneOf: ["text", "null"] }, text: "text", evidence: "prose" }, required: ["criterion", "alternative"] };
const DECISION_SCALE: Field = { fields: { min: "number", max: "number", levels: { list: "text" }, labels: { record: "text" }, note: "text" } };

/** Fields each built-in block reads. A type registered without a schema is
 * accepted as written. */
/** Collection views: a subset of members by id or by theme, and pairs of members. */
const SUBSET: Record<string, Field> = { ...FRAME, members: { list: "member" }, themes: { list: "theme" } };
const PAIR: Field = { fields: { a: "member", b: "member", title: "text", note: "text" }, required: ["a", "b"] };
const BLOCKS: Record<string, BlockSchema> = {
  verdict: { fields: { ...FRAME, ...VERDICT, rule: "prose" }, required: ["headline"] },
  figures: { fields: { ...FRAME, items: { list: { fields: { value: { oneOf: ["text", "null"] }, label: "text", note: "text", tone: { enum: ["neutral", "pass", "fail", "warn", "invalid"], warn: true } }, required: ["label"] } } }, required: ["items"] },
  ladder: {
    trial: "without-rows",
    fields: {
      ...FRAME, rows: { list: { fields: { arm: "arm-ref", case: "case-ref", k: "count", n: "count", invalid: "count", note: "text", cases: "count" }, required: ["k", "n"], kn: [["k", "n"]] } }, independent: "boolean",
      by: { enum: ["arm", "case"] }, case: "case", cases: { list: "case" }, arms: { list: "arm" }, identical: { list: { list: "arm" } }, baseline: "text",
      sort: { enum: ["identity", "rate"], warn: true }, references: { list: { fields: { value: "rate", label: "text" }, required: ["value", "label"] } }, pairs: { list: CASE_PAIR },
    },
  },
  tapestry: { trial: "always", fields: { ...FRAME, arms: { list: "arm" }, cases: { list: "case" }, transpose: "boolean", groups: { list: GROUP }, pairs: { list: CASE_PAIR } } },
  checks: { trial: "always", fields: { ...FRAME, arms: { list: "arm" }, checks: { list: "check" }, cases: { list: "case" }, by: { enum: ["case", "check"], warn: true }, pairs: { list: CASE_PAIR }, required: "boolean" } },
  pairwise: { trial: "always", fields: { ...FRAME, pair: "pair" } },
  cost: { trial: "always", fields: { ...FRAME, measures: { list: "measure" }, arms: { list: "arm" } } },
  invalid: { trial: "always", fields: { ...FRAME } },
  ledger: { trial: "always", fields: { ...FRAME } },
  plan: { trial: "always", fields: { ...FRAME } },
  setup: {
    trial: "without-settings",
    fields: { ...FRAME, arms: { list: "arm" }, baseline: "arm", identical: { list: { list: "arm" } }, hide: { list: "text" }, settings: { record: "any", keys: "arm-ref" }, judge: "any", pairs: { oneOf: [AUTO_OFF, PAIR_LIST] } },
  },
  cases: { trial: "always", fields: { ...FRAME, cases: { list: "case" }, arms: { list: "arm" }, groups: { list: GROUP }, pairs: { oneOf: [AUTO_OFF, PAIR_SPECS] }, index: "boolean", descriptions: { record: "prose", keys: "case-ref" } } },
  failures: { trial: "always", fields: { ...FRAME, cases: { list: "case" }, arms: { list: "arm" }, by: { enum: ["cause", "case"], warn: true }, reasons: "count" } },
  contrast: {
    trial: "without-rows",
    fields: {
      ...FRAME,
      rows: { list: { fields: { label: "text", arm: "arm-ref", vs: "arm-ref", note: "text", k1: "count", n1: "count", k2: "count", n2: "count", invalid1: "count", invalid2: "count", identical: "boolean", cases: "count" }, required: ["k1", "n1", "k2", "n2"], kn: [["k1", "n1"], ["k2", "n2"]] } }, independent: "boolean",
      baseline: { oneOf: ["arm", { list: "arm" }] }, arms: { list: "arm" }, cases: { list: "case" }, a: CONTRAST_SIDE, b: CONTRAST_SIDE,
      pair: { oneOf: ["text", { fields: { suffix: "text" }, required: ["suffix"] }] }, by: { enum: ["arm", "case", "none"], warn: true }, identical: { list: { list: "arm" } },
      threshold: { oneOf: ["number", { fields: { value: "number", label: "text" }, required: ["value"] }] }, sort: { enum: ["identity", "difference"], warn: true }, method: "boolean",
    },
  },
  text: { fields: { ...FRAME, text: "prose" }, required: ["text"] },
  callout: { fields: { title: "text", id: "text", tone: { enum: [...TONES, "note", "limit"], warn: true }, label: "text", text: "prose" }, required: ["text"] },
  list: { fields: { ...FRAME, items: { list: { oneOf: ["text", { fields: { text: "text", tone: TONE, detail: "text" }, required: ["text"] }] } }, ordered: "boolean" }, required: ["items"] },
  facts: { fields: { ...FRAME, items: { list: { fields: { label: "text", value: CELL_VALUE, mono: "boolean" }, required: ["label"] } } }, required: ["items"] },
  table: { fields: { ...FRAME, columns: { list: "text" }, rows: { list: { list: CELL } }, numeric: { list: "count" }, rowHeader: "boolean" }, required: ["columns", "rows"] },
  matrix: {
    fields: {
      ...FRAME, columns: { list: { fields: { id: "text", label: "text", arm: "boolean" }, required: ["id"] } },
      rows: { list: { fields: { id: "text", label: "text", detail: "text" }, required: ["id", "label"] } },
      cells: { list: { fields: { row: "text", column: "text", status: { enum: [...TONES, "missing"] }, text: "text", note: "text" }, required: ["row", "column"] } },
    },
    required: ["columns", "rows", "cells"],
  },
  intervals: {
    fields: {
      ...FRAME, rows: { list: { fields: { label: "text", arm: "arm-ref", k: "count", n: "count", cases: "count", value: NUMBER_OR_NULL, lo: NUMBER_OR_NULL, hi: NUMBER_OR_NULL, note: "text" }, kn: [["k", "n"]] } }, independent: "boolean",
      domain: { list: "number" }, unit: "text", percent: "boolean", reference: { fields: { value: "number", label: "text" }, required: ["value", "label"] },
    },
    required: ["rows"],
  },
  bars: {
    fields: {
      ...FRAME, segments: { list: { fields: { id: "text", label: "text", tone: TONE }, required: ["id", "label"] } },
      rows: { list: { fields: { label: "text", arm: "arm-ref", values: { record: NUMBER_OR_NULL }, note: "text" }, required: ["values"] } },
    },
    required: ["segments", "rows"],
  },
  trend: {
    fields: {
      ...FRAME, stages: { list: "text" },
      series: { list: { fields: { label: "text", arm: "arm-ref", points: { list: { fields: { stage: "text", k: "count", n: "count", cases: "count", value: NUMBER_OR_NULL, lo: NUMBER_OR_NULL, hi: NUMBER_OR_NULL }, required: ["stage"], kn: [["k", "n"]] } } }, required: ["label", "points"] } },
      percent: "boolean", unit: "text", independent: "boolean",
    },
    required: ["stages", "series"],
  },
  excerpts: { fields: { ...FRAME, items: { list: { fields: { text: "text", source: "text", arm: "arm-ref", outcome: { enum: ["pass", "fail", "invalid"] }, note: "text" }, required: ["text"] } } }, required: ["items"] },
  diagram: { fields: { ...FRAME, source: "text", caption: "text", config: "any" }, required: ["source"] },
  scorecard: { comparison: "without-data", fields: { ...COMPARE, metrics: { list: "metric" }, orient: { enum: ["columns", "rows"], warn: true }, center: CENTER } },
  metric: { comparison: "without-data", fields: { ...COMPARE, by: { enum: ["alternative", "case", "group"], warn: true }, depth: "count", sort: { enum: ["identity", "value"], warn: true }, threshold: THRESHOLD, center: CENTER, method: "boolean" } },
  difference: {
    comparison: "without-data",
    fields: { ...COMPARE, metrics: { list: "metric" }, pairs: { oneOf: [{ enum: ["baseline", "all"], warn: true }, { list: ALTERNATIVES }] }, threshold: THRESHOLD, identical: { oneOf: [{ list: ALTERNATIVES }, "boolean"] }, sort: { enum: ["identity", "difference"], warn: true }, center: CENTER, method: "boolean" },
  },
  hierarchy: { comparison: "without-data", fields: { ...COMPARE, depth: "count", between: "boolean", center: CENTER, method: "boolean" } },
  alternatives: { comparison: "without-data", fields: { ...FRAME, data: "any", alternatives: ALTERNATIVES, baseline: "alternative", hide: { list: "text" }, identical: { list: { list: "alternative-ref" } } } },
  preferences: { comparison: "without-data", fields: { ...FRAME, data: "any", metric: "metric", alternatives: ALTERNATIVES, cases: { list: "comparison-case" }, groups: { list: "text" } } },
  "decision-matrix": {
    fields: { ...FRAME, data: "any", criteria: { list: { fields: CRITERION_FIELDS, required: ["id"] } }, cells: { list: DECISION_CELL }, alternatives: { list: { oneOf: ["alternative-ref", { fields: { id: "alternative-ref", label: "text" }, required: ["id"] }] } }, scale: DECISION_SCALE },
    required: ["criteria"],
  },
  observations: { comparison: "without-data", fields: { ...FRAME, data: "any", alternatives: ALTERNATIVES, cases: { list: "comparison-case" }, metrics: { list: "metric" }, metric: "metric", groups: { list: "text" } } },
  decisions: { collection: "always", fields: SUBSET },
  reports: { collection: "always", fields: { ...SUBSET, layouts: { list: { enum: ["cards", "list", "table", "matrix"], warn: true } } } },
  shifts: { collection: "always", fields: SUBSET },
  "cost-gain": { collection: "always", fields: SUBSET },
  timeline: { collection: "always", fields: SUBSET },
  matchups: { collection: "always", fields: { ...SUBSET, pairs: { list: PAIR } } },
  "report-compare": { collection: "always", fields: { ...FRAME, a: "member", b: "member" }, required: ["a", "b"] },
};

const SECTION: Record<string, Field> = { id: "section-id", title: "text", label: "text", lead: "prose", reading: "prose", blocks: { list: "block" } };
const SPEC: Shape = {
  fields: {
    title: "string", kicker: "text", summary: "prose",
    meta: { list: { fields: { label: "text", value: "text" }, required: ["label", "value"] } },
    arms: { list: { fields: { id: "arm-ref", label: "text", note: "text" }, required: ["id"] } },
    sections: { list: { fields: SECTION, required: ["title", "blocks"] } },
    footer: "text", trial: "any", cases: { record: "text", keys: "case-ref" }, problems: "any", comparison: "any", collection: "any", story: "any",
  },
  required: ["title", "sections"],
};
/** A collection of reports (collection.ts). */
const MEMBER: Shape = { fields: { id: "member-id", theme: "theme", title: "text", label: "text", note: "text", date: "text", follows: "member", models: { list: "text" }, trial: "any", comparison: "any", spec: "any", narrative: "any" }, required: ["id"] };
const COLLECTION: Shape = {
  fields: { title: "text", kicker: "text", summary: "prose", footer: "text", story: "any", readings: { record: "prose" }, themes: { list: { fields: { id: "theme-id", label: "text", summary: "prose" }, required: ["id"] } }, members: { list: MEMBER }, pairs: { list: PAIR } },
  required: ["members"],
};
/** Section ids of the trial composition (compose.ts SECTION_IDS), and earlier
 * ids it still accepts, for include, exclude, after and append. */
const DEFAULT_SECTIONS = ["verdict", "setup", "arms", "cases", "grid", "failures", "checks", "pairwise", "cost", "invalid", "runs"];
/** Sections composed only when include names them. */
const OPT_IN_SECTIONS = ["grid"];
const SECTION_ALIASES: Record<string, string> = { plan: "setup" };
const SECTION_NAMES = [...DEFAULT_SECTIONS, ...Object.keys(SECTION_ALIASES)];
const sectionKey = (id: string) => Object.prototype.hasOwnProperty.call(SECTION_ALIASES, id) ? SECTION_ALIASES[id] : id;
const NARRATIVE: Shape = {
  fields: {
    title: "text", question: "text", summary: "prose", kicker: "text",
    decision: { fields: { ...FRAME, ...VERDICT, rule: "any" }, required: ["headline"], empty: { headline: 'write the decision in one sentence, or delete "decision" to report the results without one' } },
    arms: { oneOf: [{ list: { fields: { id: "arm-label", label: "text", note: "text" }, required: ["id"] } }, { record: { fields: { label: "text", note: "text" } }, keys: "arm-label" }] },
    cases: { record: "text", keys: "case-ref" },
    identical: { list: { list: "arm" } },
    groups: { list: GROUP },
    pairs: { list: { oneOf: [{ list: "case" }, { fields: { base: "case", variant: "case", label: "text" }, required: ["base", "variant"] }] } },
    baseline: "arm",
    threshold: { oneOf: ["number", { fields: { value: "number", label: "text" }, required: ["value"] }] },
    include: { list: "text" }, exclude: { list: "text" },
    sections: { list: { fields: { ...SECTION, after: "text" }, required: ["title", "blocks"] } },
    append: { record: { list: "block" } },
    footer: "text", story: "any", readings: { record: "prose" },
  },
};
const MEASURES = ["output_tokens", "input_tokens", "seconds", "commands", "total_cost_usd"];

/** A comparison of any alternatives (comparison-model.ts), as validateComparison reads it. */
const METRIC_KINDS = ["binary", "numeric", "ordinal", "count", "rank", "preference"];
const GROUP_PATH: Field = { oneOf: ["text", { list: "text" }] };
const COMPARISON: Shape = {
  fields: {
    title: "text", question: "text", summary: "prose",
    alternatives: { list: { fields: { id: "string", label: "text", description: "text", group: GROUP_PATH, attributes: { record: { oneOf: ["text", "boolean", "null"] } }, content: "text", note: "text" }, required: ["id"] } },
    cases: { list: { fields: { id: "string", label: "text", description: "text", group: GROUP_PATH }, required: ["id"] } },
    metrics: { list: { fields: { id: "string", label: "text", kind: { enum: METRIC_KINDS }, better: { enum: ["higher", "lower", "none"] }, unit: "text", levels: { list: "text" }, primary: "boolean", description: "text", threshold: "number" }, required: ["id", "kind"] } },
    observations: { list: { fields: { alternative: "alternative", metric: "metric", case: "comparison-case", value: { oneOf: ["boolean", "text", "null"] }, n: "count", unit: "text", valid: "boolean", invalid_reason: "text", note: "text", excerpt: "text", source: "text", id: "text" }, required: ["alternative", "metric"] } },
    aggregates: { list: { fields: { alternative: "alternative", metric: "metric", case: "comparison-case", k: "count", n: "count", mean: "number", sd: "number", median: "number", lo: "number", hi: "number", counts: { record: "count" }, source: "text", note: "text" }, required: ["alternative", "metric"] } },
    preferences: { list: { fields: { a: "alternative", b: "alternative", winner: { oneOf: ["text", "null"] }, case: "comparison-case", metric: "metric", judge: "text", note: "text" }, required: ["a", "b"] } },
    rankings: { list: { fields: { order: ALTERNATIVES, case: "comparison-case", metric: "metric", judge: "text" }, required: ["order"] } },
    baseline: "alternative",
    identical: { list: ALTERNATIVES },
    decision_rule: "prose",
    sources: { list: { fields: { label: "text", href: "text", note: "text" }, required: ["label"] } },
  },
  required: ["alternatives", "metrics"],
};
/** Section ids of the comparison composition (comparison-compose.ts), and other names it accepts. */
const COMPARISON_SECTIONS = ["verdict", "compared", "results", "differences", "groups", "cases", "judgments", "decision", "observations", "sources"];
const COMPARISON_ALIASES: Record<string, string> = { setup: "compared", alternatives: "compared", metrics: "results", hierarchy: "groups", preferences: "judgments", pairwise: "judgments", matrix: "decision", ledger: "observations", runs: "observations" };
const COMPARISON_NAMES = [...COMPARISON_SECTIONS, ...Object.keys(COMPARISON_ALIASES)];
const comparisonKey = (id: string) => Object.prototype.hasOwnProperty.call(COMPARISON_ALIASES, id) ? COMPARISON_ALIASES[id] : id;
const COMPARISON_NARRATIVE: Shape = {
  fields: {
    title: "text", question: "text", summary: "prose", kicker: "text",
    decision: NARRATIVE.fields.decision,
    alternatives: { oneOf: [{ list: { fields: { id: "alternative-ref", label: "text", note: "text" }, required: ["id"] } }, { record: { fields: { label: "text", note: "text" } }, keys: "alternative-ref" }] },
    baseline: "alternative",
    identical: { list: ALTERNATIVES },
    criteria: { list: { fields: CRITERION_FIELDS } },
    cells: { list: DECISION_CELL },
    scale: DECISION_SCALE,
    include: { list: "text" }, exclude: { list: "text" },
    sections: { list: { fields: { ...SECTION, after: "text" }, required: ["title", "blocks"] } },
    append: { record: { list: "block" } },
    footer: "text", story: "any", readings: { record: "prose" },
  },
};
const NUMERIC_TEXT = /^\s*-?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?\s*$/;

// ------------------------------------------------------------------ helpers

type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => v !== null && typeof v === "object" && !Array.isArray(v);
const isNumber = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);
const isText = (v: unknown) => typeof v === "string" || isNumber(v);
/** A map's keys as entriesOf lists them ("$" keys are notes), sorted so both checkers list problems in one order. */
const keysOf = (v: Obj) => keysIn(v).sort((a, b) => (a < b ? -1 : a > b ? 1 : 0));

/** A supplied value as it reads in a message: text in quotes, cut to 60 characters. */
function clip(value: string, max = 60): string {
  const chars = Array.from(value);
  return chars.length > max ? `${chars.slice(0, max - 1).join("")}…` : value;
}
function found(v: unknown): string {
  if (v === null) return "null";
  if (Array.isArray(v)) return "a list";
  if (typeof v === "object") return "an object";
  if (typeof v === "string") return `text "${clip(v)}"`;
  if (typeof v === "number") return `the number ${v}`;
  if (typeof v === "boolean") return String(v);
  return "a value JSON cannot hold";
}
function listOf(items: string[], max = 12): string {
  const shown = items.slice(0, max).map(x => clip(x, 40)).join(", ");
  return items.length > max ? `${shown}, and ${items.length - max} more` : shown;
}
function plural(n: number, word: string): string { return `${n} ${word}${n === 1 ? "" : "s"}`; }

/** Edit distance with adjacent transpositions (optimal string alignment). */
function distance(a: string, b: string): number {
  const rows: number[][] = [];
  for (let i = 0; i <= a.length; i++) { rows.push([i]); for (let j = 1; j <= b.length; j++) rows[i].push(i ? 0 : j); }
  for (let i = 1; i <= a.length; i++) for (let j = 1; j <= b.length; j++) {
    const cost = a[i - 1] === b[j - 1] ? 0 : 1;
    rows[i][j] = Math.min(rows[i - 1][j] + 1, rows[i][j - 1] + 1, rows[i - 1][j - 1] + cost);
    if (i > 1 && j > 1 && a[i - 1] === b[j - 2] && a[i - 2] === b[j - 1]) rows[i][j] = Math.min(rows[i][j], rows[i - 2][j - 2] + 1);
  }
  return rows[a.length][b.length];
}
/** The option a misspelling most likely meant: a case-insensitive match, else
 * the closest within one edit per three characters (at most two). */
function suggest(value: string, options: string[]): string | null {
  const lower = value.toLowerCase();
  const folded = options.find(o => o.toLowerCase() === lower);
  if (folded !== undefined) return folded;
  let best: string | null = null, bestDistance = Infinity;
  for (const option of options) {
    const d = distance(lower, option.toLowerCase()), limit = Math.min(2, Math.max(1, Math.floor(option.length / 3)));
    if (d <= limit && d < bestDistance) { best = option; bestDistance = d; }
  }
  return best;
}

function describe(f: Field): string {
  if (typeof f === "string") return ({
    text: "text", string: "text", prose: "text or a list of paragraphs", number: "a number", count: "a whole number of 0 or more",
    rate: "a number from 0 to 1", boolean: "true or false", null: "null", any: "any value", block: "a block object",
    arm: "an arm id", "arm-ref": "an arm id", "arm-label": "an arm id", case: "a case id", "case-ref": "a case id", check: "a check name", pair: "a pairwise key",
    measure: "a measure id", "section-id": "a section id", alternative: "an alternative id", "alternative-ref": "an alternative id", metric: "a metric id", "comparison-case": "a case id",
    member: "a report id", "member-id": "a report id", theme: "a theme id", "theme-id": "a theme id",
  } as Record<string, string>)[f] || f;
  if ("enum" in f) return `one of ${f.enum.join(", ")}`;
  if ("list" in f) return "a list";
  if ("oneOf" in f) return [...new Set(f.oneOf.map(describe))].join(" or ");
  return "an object";
}
/** Whether a value has the outer shape a field takes, to choose among alternatives. */
function fits(v: unknown, f: Field): boolean {
  if (typeof f === "string") {
    if (f === "any") return true;
    if (f === "null") return v === null;
    if (f === "boolean") return typeof v === "boolean";
    if (f === "number" || f === "count" || f === "rate") return isNumber(v);
    if (f === "text") return isText(v);
    if (f === "prose") return isText(v) || Array.isArray(v);
    if (f === "block") return isObj(v);
    return typeof v === "string";
  }
  if ("enum" in f) return typeof v === "string";
  if ("list" in f) return Array.isArray(v);
  if ("oneOf" in f) return f.oneOf.some(a => fits(v, a));
  return isObj(v);
}
function typeHint(v: unknown, f: Field): string {
  const numeric = typeof f === "string" && ["number", "count", "rate"].includes(f);
  if (numeric && typeof v === "string" && /^\s*-?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?\s*$/.test(v)) return "write the number without quotes";
  if (f === "boolean" && (v === "true" || v === "false")) return "write true or false without quotes";
  if (typeof f === "object" && "list" in f && !Array.isArray(v)) return "write a list in square brackets, even for one item";
  if (f === "count" && isNumber(v)) return "counts are whole numbers of 0 or more";
  if (f === "rate" && isNumber(v)) return "rates are fractions: write 0.75 for 75%";
  return `write ${describe(f)}`;
}

/** A value as canonical text (keys sorted), so recorded settings compare by content. */
function canon(v: unknown): string {
  if (Array.isArray(v)) return `[${v.map(canon).join(",")}]`;
  if (isObj(v)) return `{${Object.keys(v).sort((a, b) => (a < b ? -1 : a > b ? 1 : 0)).map(k => `${JSON.stringify(k)}:${canon(v[k])}`).join(",")}}`;
  return v === undefined ? "" : JSON.stringify(v) ?? "";
}
/** Plan fields that carry an arm's material text; the digests beside them are what is compared. */
const MATERIAL_TEXT = ["instructions_text", "instructions_truncated", "artifact_text", "artifact_truncated"];

interface Known { trial: boolean; arms: string[]; cases: string[]; checks: string[]; pairs: string[]; settings: Record<string, Obj>; comparison: boolean; alternatives: string[]; metrics: string[]; ccases: string[]; collection: boolean; members: string[]; themes: string[]; ranArms: string[]; ranCases: string[] }
const isComparison = (v: unknown): v is Obj => isObj(v) && Array.isArray(v.alternatives);
const isCollection = (v: unknown): v is Obj => isObj(v) && Array.isArray(v.members);
/** The collection composition's section ids (collection.ts COLLECTION_SECTION_IDS). */
const COLLECTION_SECTIONS = ["glance", "reports", "shifts", "cost-gain", "timeline", "matchups"];
/** Sections the collection composition plainly shows: the glance and index always, shifts when a member has trial data,
 * pairs when the collection names pairs or follow-ups, the timeline when a member follows another. */
function collectionSectionsShown(collection: Obj): string[] {
  const members = (Array.isArray(collection.members) ? collection.members : []).filter(isObj);
  const shown = ["glance", "reports"];
  // A member's data, its own or its specification's, as the composition reads it.
  const measured = (c: unknown) => isObj(c) && Array.isArray(c.metrics) && c.metrics.length > 0;
  if (members.some(m => isObj(m.trial) || (isObj(m.spec) && (isObj(m.spec.trial) || measured(m.spec.comparison))) || measured(m.comparison))) shown.push("shifts");
  if (members.some(m => isObj(m.trial) || isObj(m.spec)) && members.some(costShown)) shown.push("cost-gain");
  if (members.filter(dated).length > 1 || members.some(m => typeof m.follows === "string")) shown.push("timeline");
  if ((Array.isArray(collection.pairs) && collection.pairs.length) || members.some(m => typeof m.follows === "string")) shown.push("matchups");
  return COLLECTION_SECTIONS.filter(s => shown.includes(s));
}
/** A member's trial data, its own or its specification's. */
const memberTrial = (m: Obj): Obj | null => isObj(m.spec) ? (isObj(m.spec.trial) && Array.isArray(m.spec.trial.runs) ? m.spec.trial : null) : isObj(m.trial) && Array.isArray(m.trial.runs) ? m.trial : null;
const trimmed = (v: unknown) => typeof v === "string" ? v.trim() : isNumber(v) ? String(v) : "";
/** A member the timeline places by day: its own date, or the day its trial's runs began. */
function dated(m: Obj): boolean {
  if (typeof m.date === "string" && isCalendarDate(m.date.slice(0, 10)) && /^\d{4}-\d{2}-\d{2}/.test(m.date)) return true;
  const t = memberTrial(m), ran = t && isObj(t.ran) ? t.ran : {};
  const first = t ? trimmed(ran.first) || trimmed(t.generated_at) : "";
  return /^\d{4}-\d{2}-\d{2}/.test(first) && isCalendarDate(first.slice(0, 10));
}
/** Whether a member draws a point on the cost-against-gain view: a setup measured against its reference on the same
 * model, both with valid runs, and the trial's own cost difference against that reference. */
function costShown(m: Obj): boolean {
  const t = memberTrial(m);
  if (!t) return false;
  const runs = (t.runs as unknown[]).filter(isObj);
  const ran = new Set(runs.map(r => r.arm).filter(a => typeof a === "string"));
  const narrative = !isObj(m.spec) && isObj(m.narrative) ? m.narrative : {};
  const wanted = isObj(m.spec) ? trimmed(t.baseline) : trimmed(narrative.baseline) || trimmed(t.baseline);
  if (!ran.has(wanted) || t.baseline !== wanted) return false;
  const arms = isObj(t.plan) && isObj(t.plan.arms) ? t.plan.arms : {};
  const lane = (id: string) => isObj(arms[id]) && typeof arms[id].model === "string" ? arms[id].model : "";
  const valid = (id: string) => runs.some(r => r.arm === id && (r.passed === true || r.passed === false));
  const pct = isObj(t.pct_vs_baseline) ? t.pct_vs_baseline : {};
  const change = (id: string) => { const e = isObj(pct[id]) ? pct[id] : {}; const v = isObj(e.cost_usd) && e.cost_usd.median !== undefined && e.cost_usd.median !== null ? e.cost_usd.median : isObj(e.total_cost_usd) ? e.total_cost_usd.median : undefined; return isNumber(v); };
  return valid(wanted) && [...ran].some(id => id !== wanted && lane(id) === lane(wanted) && valid(id) && change(id));
}
/** A real calendar day written YYYY-MM-DD: 2026-02-30 and 2026-99-99 are not. */
function isCalendarDate(v: string): boolean {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(v);
  if (!m) return false;
  const d = new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3])));
  return d.getUTCFullYear() === Number(m[1]) && d.getUTCMonth() === Number(m[2]) - 1 && d.getUTCDate() === Number(m[3]);
}
function knownFrom(trial: unknown, comparison?: unknown, collection?: unknown): Known {
  // settings has no prototype, so an arm named like an Object member is an ordinary key.
  const known: Known = { trial: false, arms: [], cases: [], checks: [], pairs: [], settings: Object.create(null), comparison: false, alternatives: [], metrics: [], ccases: [], collection: false, members: [], themes: [], ranArms: [], ranCases: [] };
  if (isCollection(collection)) {
    known.collection = true;
    for (const [list, into] of [[collection.members, known.members], [collection.themes, known.themes]] as const) if (Array.isArray(list)) for (const x of list) if (isObj(x) && typeof x.id === "string" && !into.includes(x.id)) into.push(x.id);
  }
  if (isComparison(comparison)) {
    known.comparison = true;
    const ids = (list: unknown, into: string[]) => { if (Array.isArray(list)) for (const x of list) if (isObj(x) && typeof x.id === "string" && !into.includes(x.id)) into.push(x.id); };
    ids(comparison.alternatives, known.alternatives); ids(comparison.metrics, known.metrics); ids(comparison.cases, known.ccases);
  }
  if (!isObj(trial) || !Array.isArray(trial.runs)) return known;
  known.trial = true;
  const add = (list: string[], v: unknown) => { if (typeof v === "string" && !list.includes(v)) list.push(v); };
  const plan = isObj(trial.plan) ? trial.plan : {};
  if (isObj(plan.arms)) for (const [a, entry] of entriesOf(plan.arms)) { add(known.arms, a); if (isObj(entry)) known.settings[a] = entry; }
  if (Array.isArray(plan.scenarios)) for (const s of plan.scenarios) if (isObj(s)) add(known.cases, s.name);
  for (const r of trial.runs) {
    if (!isObj(r)) continue;
    add(known.arms, r.arm);
    add(known.cases, r.scenario);
    add(known.ranArms, r.arm);
    add(known.ranCases, r.scenario);
    if ((r.passed === true || r.passed === false) && isObj(r.checks)) for (const [k, v] of entriesOf(r.checks)) if (typeof v === "boolean") add(known.checks, k);
  }
  if (isObj(trial.pairwise)) for (const k of keysIn(trial.pairwise)) add(known.pairs, k);
  return known;
}

const IDS: Record<string, { list: "arms" | "cases" | "checks" | "pairs" | "alternatives" | "metrics" | "ccases" | "members" | "themes" | null; noun: string; plural: string; level: Problem["level"]; tail: string }> = {
  arm: { list: "arms", noun: "an arm in this trial", plural: "arms in this trial", level: "error", tail: "" },
  "arm-ref": { list: "arms", noun: "an arm in this trial", plural: "arms in this trial", level: "warning", tail: "; it gets an identity color of its own" },
  "arm-label": { list: "arms", noun: "an arm in this trial", plural: "arms in this trial", level: "warning", tail: ", so this entry is not used" },
  case: { list: "cases", noun: "a case in this trial", plural: "cases in this trial", level: "error", tail: "" },
  "case-ref": { list: "cases", noun: "a case in this trial", plural: "cases in this trial", level: "warning", tail: ", so this label is not used" },
  check: { list: "checks", noun: "a recorded pass/fail check in this trial", plural: "checks in this trial", level: "error", tail: "" },
  pair: { list: "pairs", noun: "a pairwise comparison in this trial", plural: "pairwise comparisons in this trial", level: "error", tail: "" },
  measure: { list: null, noun: "a cost measure", plural: "measures", level: "error", tail: "" },
  alternative: { list: "alternatives", noun: "an alternative in this comparison", plural: "alternatives in this comparison", level: "error", tail: "" },
  "alternative-ref": { list: "alternatives", noun: "an alternative in this comparison", plural: "alternatives in this comparison", level: "warning", tail: ", so this entry is not used" },
  metric: { list: "metrics", noun: "a metric in this comparison", plural: "metrics in this comparison", level: "error", tail: "" },
  "comparison-case": { list: "ccases", noun: "a case defined in this comparison", plural: "cases in this comparison", level: "warning", tail: "; it is shown by its id" },
  member: { list: "members", noun: "a report in this collection", plural: "reports in this collection", level: "error", tail: "" },
  theme: { list: "themes", noun: "a theme in this collection", plural: "themes in this collection", level: "warning", tail: "" },
};
const FROM_COLLECTION = ["members", "themes"];
const FROM_COMPARISON = ["alternatives", "metrics", "ccases"];

// ------------------------------------------------------------------ checker

type Hook = (value: unknown, where: string) => void;

class Checker {
  readonly problems: Problem[] = [];
  constructor(readonly known: Known, readonly types: string[], readonly root: string) {}

  add(level: Problem["level"], where: string, message: string, hint?: string): void {
    this.problems.push(hint ? { level, where: where || this.root, message, hint } : { level, where: where || this.root, message });
  }
  join(where: string, key: string | number): string {
    if (typeof key === "number") return `${where}[${key}]`;
    if (!/^[A-Za-z_][A-Za-z0-9_-]*$/.test(key)) return `${where}[${JSON.stringify(key)}]`;
    return where ? `${where}.${key}` : key;
  }
  type(v: unknown, f: Field, where: string): void {
    this.add("error", where, `expected ${describe(f)}, found ${found(v)}`, typeHint(v, f));
  }

  check(v: unknown, f: Field, where: string): void {
    if (typeof f === "string") return this.scalar(v, f, where);
    if ("enum" in f) return this.choice(v, f, where);
    if ("list" in f) {
      if (!Array.isArray(v)) return this.type(v, f, where);
      v.forEach((x, i) => this.check(x, f.list, this.join(where, i)));
      return;
    }
    if ("record" in f) {
      if (!isObj(v)) return this.type(v, f, where);
      for (const k of keysOf(v)) {
        const at = this.join(where, k);
        if (f.keys) this.id(k, f.keys, at);
        if (v[k] !== null && v[k] !== undefined) this.check(v[k], f.record, at);
      }
      return;
    }
    if ("oneOf" in f) {
      const alternative = f.oneOf.find(a => fits(v, a));
      return alternative === undefined ? this.type(v, f, where) : this.check(v, alternative, where);
    }
    this.shape(v, f, where);
  }

  scalar(v: unknown, kind: string, where: string): void {
    if (kind === "any") return;
    if (kind === "block") return this.block(v, where);
    if (!fits(v, kind)) return this.type(v, kind, where);
    if (kind === "count" && (!Number.isInteger(v) || (v as number) < 0)) return this.type(v, kind, where);
    if (kind === "rate" && ((v as number) < 0 || (v as number) > 1)) return this.type(v, kind, where);
    if (kind === "prose" && Array.isArray(v)) v.forEach((x, i) => { if (!isText(x)) this.type(x, "text", this.join(where, i)); });
    if (kind === "member-id" && !/^[A-Za-z][\w.-]*$/.test(v as string))
      this.add("error", where, `"${clip(v as string)}" cannot be a report id, since links name reports by id`, "start with a letter and use only letters, digits, _ . or -");
    if (kind === "theme-id" && !(v as string).trim()) this.add("error", where, "a theme id cannot be blank, since reports join their theme by its id", "name the theme");
    if (kind === "section-id" && !/^[A-Za-z][\w:.-]*$/.test(v as string))
      this.add("warning", where, `"${clip(v as string)}" cannot be used as a section id, so the section gets a generated one`, "start with a letter and use only letters, digits, _ : . or -");
    if (kind in IDS) this.id(v as string, kind, where);
  }

  choice(v: unknown, f: Enum, where: string): void {
    if (typeof v === "string" && (f.enum.includes(v) || (f.fold && f.enum.includes(v.toLowerCase())))) return;
    if (typeof v !== "string") return this.type(v, f, where);
    const s = suggest(v, f.enum);
    this.add(f.warn ? "warning" : "error", where, `"${clip(v)}" is not one of the allowed values`, `${s ? `did you mean "${s}"? Allowed` : "allowed"} values: ${f.enum.join(", ")}`);
  }

  id(value: string, kind: string, where: string): void {
    const spec = IDS[kind];
    if (!spec) return;
    // A blank case names no case: every view reads that evidence as evidence naming no case (caseKey).
    if (kind === "comparison-case" && caseKey(value) === NO_CASE) {
      if (this.known.comparison) this.add("warning", where, "an empty or blank case names no case: it stands for the evidence naming no case", 'name a case, or leave "case" out where the evidence names none');
      return;
    }
    const ofComparison = spec.list !== null && FROM_COMPARISON.includes(spec.list), ofCollection = spec.list !== null && FROM_COLLECTION.includes(spec.list);
    if (spec.list && !(ofCollection ? this.known.collection : ofComparison ? this.known.comparison && (spec.list !== "ccases" || this.known.ccases.length > 0) : this.known.trial)) return;
    const options = spec.list ? this.known[spec.list] : MEASURES;
    if (options.includes(value)) return;
    const s = suggest(value, options);
    this.add(spec.level, where, `"${clip(value)}" is not ${spec.noun}${spec.tail}`,
      s ? `did you mean "${s}"?` : options.length ? `${spec.plural}: ${listOf(options)}` : `this ${ofCollection ? "collection" : ofComparison ? "comparison" : "trial"} has no ${spec.plural.replace(/ in this (trial|comparison|collection)$/, "")}`);
  }

  shape(v: unknown, f: Shape, where: string, hooks: Record<string, Hook> = {}, skip: string[] = []): void {
    if (!isObj(v)) return this.type(v, f, where);
    for (const name of f.required || []) {
      const x = v[name];
      if (x === undefined || x === null) this.add("error", where, `missing required field "${name}"`, `required here: ${(f.required || []).join(", ")}`);
      else if (typeof x === "string" && !x.trim() && ["text", "string", "prose"].includes(f.fields[name] as string))
        this.add("error", this.join(where, name), `"${name}" is empty`, f.empty?.[name] || "write the text the report should show, or remove the entry");
    }
    for (const [name, field] of Object.entries(f.fields)) {
      const x = v[name];
      if (x === undefined || x === null) continue;
      const at = this.join(where, name);
      this.check(x, field, at);
      hooks[name]?.(x, at);
    }
    const names = Object.keys(f.fields).filter(n => !skip.includes(n));
    for (const k of keysOf(v)) {
      if (Object.prototype.hasOwnProperty.call(f.fields, k) || skip.includes(k)) continue;
      const s = suggest(k, names);
      this.add("warning", this.join(where, k), `unknown field "${clip(k)}" is not used`, s ? `did you mean "${s}"?` : `fields here: ${listOf(names, 30)}`);
    }
    for (const [k, n] of f.kn || []) {
      const passed = v[k], valid = v[n];
      if (isNumber(passed) && isNumber(valid) && passed > valid)
        this.add("error", where, `${k} (${passed}) is larger than ${n} (${valid})`, `${k} counts passed runs and ${n} counts valid runs, so ${k} cannot be larger than ${n}`);
    }
  }

  block(v: unknown, where: string): void {
    if (!isObj(v)) return this.add("error", where, `expected a block object, found ${found(v)}`, 'a block is an object with a "type", such as {"type": "text", "text": "…"}');
    const type = v.type;
    if (typeof type !== "string" || !type) return this.add("error", where, 'the block has no "type"', `block types: ${listOf(this.types, 40)}`);
    if (!this.types.includes(type)) {
      const s = suggest(type, this.types);
      return this.add("error", where, `unknown block type "${clip(type)}"`, s ? `did you mean "${s}"?` : `block types: ${listOf(this.types, 40)}`);
    }
    const schema = Object.prototype.hasOwnProperty.call(BLOCKS, type) ? BLOCKS[type] : undefined;
    if (!schema) return;
    const at = `${where} (${type})`;
    // A block that carries its own comparison is checked against it.
    if (isComparison(v.data)) {
      const own = knownFrom(undefined, v.data);
      const inner = new Checker({ ...this.known, comparison: true, alternatives: own.alternatives, metrics: own.metrics, ccases: own.ccases }, this.types, this.root);
      inner.blockBody(type, schema, v, at);
      this.problems.push(...inner.problems);
      return;
    }
    this.blockBody(type, schema, v, at);
  }

  blockBody(type: string, schema: BlockSchema, v: Obj, at: string): void {
    const own = schema.trial && schema.trial.startsWith("without-") ? schema.trial.slice("without-".length) : null;
    if (!this.known.trial && (schema.trial === "always" || (own !== null && (v[own] === undefined || v[own] === null))))
      this.add("error", at, `the ${type} block needs trial data${own !== null ? ` or its own "${own}"` : ""}`, 'pass --trial to report.py, or set the specification\'s "trial" field');
    if (schema.collection && !this.known.collection)
      this.add("error", at, `the ${type} block needs a collection`, 'pass --collection to report.py, or set the specification\'s "collection" field');
    if (schema.comparison && !this.known.comparison && (v.data === undefined || v.data === null))
      this.add("error", at, `the ${type} block needs comparison data or its own "data"`, 'pass --data or --csv to report.py, or set the specification\'s "comparison" field');
    // A view's own data is checked once, as comparison data, by checkComparison (viewData).
    this.shape(v, schema, at, {}, ["type"]);
    this.blockRules(type, v, at);
  }

  /** Cross-field rules a field table cannot state. */
  blockRules(type: string, v: Obj, at: string): void {
    const strings = (list: unknown, key: string) => Array.isArray(list) ? list.filter(isObj).map(x => x[key]).filter((x): x is string => typeof x === "string") : [];
    const refer = (value: unknown, options: string[], where: string, noun: string, tail: string) => {
      if (typeof value !== "string" || options.includes(value)) return;
      const s = suggest(value, options);
      this.add("warning", where, `"${clip(value)}" is not ${noun}, so ${tail}`, s ? `did you mean "${s}"?` : options.length ? `ids here: ${listOf(options)}` : "this block defines none");
    };
    if (type === "ladder" && Array.isArray(v.rows)) {
      const key = v.by === "case" ? "case" : "arm";
      v.rows.forEach((row, i) => {
        if (isObj(row) && (row[key] === undefined || row[key] === null)) this.add("error", `${at}.rows[${i}]`, `missing required field "${key}"`, `rows by ${key} name the ${key} each count belongs to`);
      });
    }
    if (type === "ladder" && typeof v.baseline === "string" && v.by !== "case") {
      const rows = Array.isArray(v.rows) ? strings(v.rows, "arm") : null;
      const options = rows || (this.known.trial ? this.known.arms : null);
      if (options && !options.includes(v.baseline)) {
        const s = suggest(v.baseline, options);
        this.add("error", `${at}.baseline`, `"${clip(v.baseline)}" is not ${rows ? "an arm in this block's rows" : "an arm in this trial"}`, s ? `did you mean "${s}"?` : `${rows ? "arms in the rows" : "arms in this trial"}: ${listOf(options)}`);
      }
    }
    if (type === "table" && Array.isArray(v.columns) && Array.isArray(v.rows))
      v.rows.forEach((row, i) => {
        if (Array.isArray(row) && row.length > (v.columns as unknown[]).length)
          this.add("warning", `${at}.rows[${i}]`, `${plural(row.length, "cell")} for ${plural((v.columns as unknown[]).length, "column")}; the extra cells are not shown`, "add a column or remove the extra cells");
      });
    if (type === "matrix" && Array.isArray(v.cells)) {
      const rows = strings(v.rows, "id"), columns = strings(v.columns, "id");
      v.cells.forEach((cell, i) => {
        if (!isObj(cell)) return;
        refer(cell.row, rows, `${at}.cells[${i}].row`, "a row id of this matrix", "the cell is not shown");
        refer(cell.column, columns, `${at}.cells[${i}].column`, "a column id of this matrix", "the cell is not shown");
      });
    }
    if (type === "bars" && Array.isArray(v.rows)) {
      const segments = strings(v.segments, "id");
      v.rows.forEach((row, i) => {
        if (isObj(row) && isObj(row.values)) for (const k of keysOf(row.values)) refer(k, segments, this.join(`${at}.rows[${i}].values`, k), "a segment id", "this value is not drawn");
      });
    }
    if (type === "trend" && Array.isArray(v.series)) {
      const stages = Array.isArray(v.stages) ? v.stages.filter((s): s is string => typeof s === "string") : [];
      v.series.forEach((series, i) => {
        if (isObj(series) && Array.isArray(series.points)) series.points.forEach((p, j) => { if (isObj(p)) refer(p.stage, stages, `${at}.series[${i}].points[${j}].stage`, "one of the stages", "this point is not drawn"); });
      });
    }
    if (type === "intervals" && Array.isArray(v.domain) && !(v.domain.length === 2 && isNumber(v.domain[0]) && isNumber(v.domain[1]) && v.domain[0] < v.domain[1]))
      this.add("error", `${at}.domain`, "the domain is not two increasing numbers", "write [low, high], such as [0, 1]");
  }

  section(v: unknown, where: string, extra: Record<string, Field> = {}): void {
    this.shape(v, { fields: { ...SECTION, ...extra }, required: ["title", "blocks"] }, where);
  }
}

function order(problems: Problem[]): Problem[] {
  const seen = new Set<string>(), unique: Problem[] = [];
  for (const p of problems) {
    const key = JSON.stringify([p.level, p.where, p.message]);
    if (!seen.has(key)) { seen.add(key); unique.push(p); }
  }
  return [...unique.filter(p => p.level === "error"), ...unique.filter(p => p.level !== "error")];
}

/** A problem from elsewhere (the composition), kept only when well formed. */
function carried(p: unknown): Problem | null {
  if (!isObj(p) || typeof p.where !== "string" || typeof p.message !== "string") return null;
  const level = p.level === "error" ? "error" : "warning";
  return typeof p.hint === "string" && p.hint ? { level, where: p.where, message: p.message, hint: p.hint } : { level, where: p.where, message: p.message };
}

function registered(): string[] {
  try { return blockTypes(); } catch { return Object.keys(BLOCKS).sort(); }
}

// ------------------------------------------------------------------ the story a newcomer needs

/** What a reader who has never heard of the work needs before the results: every report kind carries it. */
const STORY: Shape = {
  fields: {
    background: "prose", intent: "prose", questions: { list: "text" }, rule: "prose", covers: "prose", notCovered: "prose",
    alternatives: { record: "prose" }, cases: { record: "prose" },
    glossary: { list: { fields: { term: "text", meaning: "prose" }, required: ["term", "meaning"] } },
  },
  required: ["background", "intent", "questions", "covers", "notCovered"],
};
const STORY_HINT = 'add "story": background, intent, questions, rule, covers and notCovered, with every alternative and case described in plain words; see catalog.md#the-story';
/** A sentence that sends the reader to a file for what the report should say itself: a referral ("see", "refer to",
 * "per", "according to", "consult", "as described in", "set out in", "details are in", or a sentence opening "Read",
 * "Open" or "Check") followed by a path (../README.md, runs/x/notes.txt, /home/me/plan.md) or a document's file name.
 * Naming a file as the subject of the work, with or without a path, or saying a text is in a file ("a typo in
 * README.md"), is not one. */
export const FILE_REF = /(?:\b(?:see(?:\s+also)?|refer(?:red)?\s+to|per|according\s+to|consult|as\s+(?:[a-z]+\s+)?in|(?:described|listed|documented|defined|explained|given|written|set\s+out|spelled\s+out|recorded|kept|stated|specified|detailed|available|covered)\s+in|details?\s+(?:are\s+|is\s+)?in)|(?:^|[.!?;:]\s+|\(\s*)(?:read|open|check))\s+(?:the\s+)?[`"'“‘]?((?:\.{1,2}\/|~\/|\/)?(?:[\w.-]+\/)+[\w.-]*\w\.[A-Za-z][A-Za-z0-9]{0,4}|(?:\.{1,2}\/|~\/|\/)[\w.-]*\w\.[A-Za-z][A-Za-z0-9]{0,4}|[\w-][\w.-]*\.(?:md|markdown|txt|rst|adoc|pdf|docx?|html?|json|jsonl|ya?ml|toml|csv|tsv|ipynb|xlsx?|log))(?![\w\/])/i;
/** The file a text points the reader at, or null. */
export function filePointer(text: string): string | null {
  const m = FILE_REF.exec(text);
  return m ? m[1] : null;
}
/** Views that are prose or the decision itself; every other block is a view whose data needs a reading. */
const PROSE_BLOCKS = ["text", "callout", "list", "facts", "verdict"];
const said = (v: unknown) => (typeof v === "string" && v.trim() !== "") || (Array.isArray(v) && v.some(x => typeof x === "string" && x.trim() !== ""));
const textsOf = (v: unknown): string[] => typeof v === "string" ? [v] : Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : [];

function fileRefs(c: Checker, value: unknown, where: string): void {
  for (const t of textsOf(value)) {
    const m = filePointer(t);
    if (m) { c.add("error", where, `points the reader at "${clip(m)}", which this report does not include`, "say here, in plain words, what the reader needs from it"); return; }
  }
}

/** What a story must describe: each alternative with its noun ("arm" for a trial's, "alternative" otherwise), and each case. */
interface StoryNeeds { rule: boolean; alternatives: Map<string, "arm" | "alternative"> | null; cases: string[] | null }
/** The story's parts, every alternative and case described, and no pointer to a file the reader cannot see. */
function storyChecks(c: Checker, owner: Obj, at: string, needs: StoryNeeds): void {
  const story = owner.story, where = c.join(at, "story");
  if (story === undefined || story === null) { c.add("error", at, 'missing "story", which tells a reader new to this work what it is about', STORY_HINT); return; }
  c.shape(story, STORY, where);
  if (!isObj(story)) return;
  if (needs.rule && !said(story.rule)) c.add("error", where, 'missing "rule": how the decision was to be made, in plain words', "say what result would decide it, so the reader can hold the views below against it");
  if (Array.isArray(story.questions) && !story.questions.length) c.add("error", c.join(where, "questions"), "lists no question", "write each question or theory the work set out to test, in plain words");
  // A part given but saying nothing (empty, blank, or not words at all, such as a number) tells the reader as little as one left out.
  // A rule the report does not require is checked the same way when given; a required one is checked above.
  for (const k of ["background", "intent", "questions", "covers", "notCovered", ...(needs.rule ? [] : ["rule"])]) {
    const v = story[k];
    // A missing or blank required part is already reported by the shape check.
    if (v === undefined || v === null || (k !== "rule" && typeof v === "string" && !v.trim())) continue;
    if (k === "questions") { if (Array.isArray(v)) v.forEach((q, i) => { if (typeof q !== "string" || !q.trim()) c.add("error", c.join(c.join(where, k), i), "is blank", "write the question in plain words, or remove it"); }); }
    else if (!said(v)) c.add("error", c.join(where, k), "says nothing", "write it in plain words for a reader new to this work");
  }
  const described = (key: "alternatives" | "cases", needed: Map<string, string> | null) => {
    if (!needed) return;
    const ids = [...needed.keys()], given = isObj(story[key]) ? story[key] as Obj : {};
    for (const [id, noun] of needed) if (!said(given[id])) c.add("error", c.join(where, key), `does not describe ${noun} "${clip(id)}"`, key === "alternatives" ? "say in plain words what each one is and how it differs from the others" : "say in plain words why each case exists and what it checks for");
    const article = key === "cases" ? "a case" : [...needed.values()].every(n => n === "arm") && ids.length ? "an arm" : "an alternative";
    for (const k of keysOf(given)) if (!ids.includes(k)) {
      const s = suggest(k, ids);
      c.add("warning", c.join(c.join(where, key), k), `"${clip(k)}" is not ${article} in this report, so this description is not used`, s ? `did you mean "${s}"?` : ids.length ? `ids here: ${listOf(ids)}` : "this report has none");
    }
  };
  described("alternatives", needs.alternatives);
  described("cases", needs.cases ? new Map(needs.cases.map(id => [id, "case"])) : null);
  for (const k of ["background", "intent", "questions", "rule", "covers", "notCovered"]) fileRefs(c, story[k], c.join(where, k));
  for (const key of ["alternatives", "cases"]) if (isObj(story[key])) for (const k of keysOf(story[key] as Obj)) fileRefs(c, (story[key] as Obj)[k], c.join(c.join(where, key), k));
  if (Array.isArray(story.glossary)) story.glossary.forEach((g, i) => { if (isObj(g)) fileRefs(c, g.meaning, c.join(c.join(c.join(where, "glossary"), i), "meaning")); });
}

/** A recorded decision rule that only points at a file cannot be shown: the narrative states the rule, and the verdict shows that. */
function pointedRule(c: Checker, narrative: Obj, recorded: unknown, whose: string): void {
  const file = typeof recorded === "string" ? filePointer(recorded) : null;
  if (!file || !isObj(narrative.story) || said(narrative.story.rule)) return;
  c.add("error", "narrative.story.rule", `${whose} decision rule points the reader at "${clip(file)}", which this report does not include, so the narrative states the rule`, "write the rule in story.rule, in plain words; the verdict shows it in place of the recorded pointer");
}

/** A reading, for each section the composition will show, of what its views say for this data. */
function readingsChecks(c: Checker, owner: Obj, at: string, required: string[], names: string[], key: (id: string) => string): void {
  const where = c.join(at, "readings");
  const given = isObj(owner.readings) ? owner.readings as Obj : {};
  const covered = keysOf(given).filter(k => said(given[k])).map(key);
  for (const id of required) if (!covered.includes(id)) c.add("error", where, `no reading for the "${id}" section`, `add readings.${id}: what a newcomer should take from that section's views for this data, in plain words, with the numbers that matter`);
  for (const k of keysOf(given)) {
    if (!names.includes(k)) {
      const s = suggest(k, names);
      c.add("warning", c.join(where, k), `"${clip(k)}" is not a section of this report, so this reading is not used`, s ? `did you mean "${s}"?` : `sections: ${listOf(names, 20)}`);
    }
    fileRefs(c, given[k], c.join(where, k));
  }
}

/** Sections the trial composition always or plainly shows, by the same tests the composition applies. */
function trialSectionsShown(trial: unknown, narrative: Obj, kept: string[]): string[] {
  const shown = ["setup", "cases", "runs"];
  if (isObj(trial) && Array.isArray(trial.runs)) {
    const runs = trial.runs.filter(isObj);
    const valid = runs.filter(r => r.passed === true || r.passed === false);
    // The arms section holds the arm views, or with one arm the variants against their base cases.
    if (valid.length && (new Set(runs.map(r => r.arm).filter(a => typeof a === "string")).size > 1 || variantPairs(trial, runs, narrative))) shown.push("arms");
    if (valid.some(r => r.passed === false)) shown.push("failures");
    if (isObj(trial.pairwise) && keysIn(trial.pairwise).length) shown.push("pairwise");
    const positive = (v: unknown) => isNumber(v) && v > 0;
    if (valid.some(r => positive(r.seconds) || positive(r.commands) || (isObj(r.usage) && ["output_tokens", "input_tokens", "cost_usd", "total_cost_usd"].some(k => positive((r.usage as Obj)[k]))))) shown.push("cost");
    if (runs.some(r => r.passed !== true && r.passed !== false)) shown.push("invalid");
    if (valid.length) shown.push("grid");
    if (valid.length && checksShown(trial as Obj, runs)) shown.push("checks");
  }
  return DEFAULT_SECTIONS.filter(s => shown.includes(s) && kept.includes(s));
}
/** Whether the composition pairs any case with a variant of it: the narrative's own pairs where it lists them (as the
 * composition keeps them), else those the plan's scenarios form. */
function variantPairs(trial: Obj, runs: Obj[], narrative: Obj): boolean {
  const ran = new Set(runs.map(r => r.scenario).filter(x => typeof x === "string"));
  if (Array.isArray(narrative.pairs))
    return narrative.pairs.some(p => {
      const [base, variant] = Array.isArray(p) ? p : isObj(p) ? [p.base, p.variant] : [];
      return typeof base === "string" && typeof variant === "string" && base !== variant && ran.has(base) && ran.has(variant);
    });
  const scenarios = isObj(trial.plan) && Array.isArray(trial.plan.scenarios) ? trial.plan.scenarios.filter(isObj) : [];
  return casePairs({ plan: { scenarios }, runs } as unknown as TrialReport).length > 0;
}
/** Whether the composition draws its checks section: with several arms, a check every recorded run gives as true or
 * false, or a judge's verdict; with one arm, a case whose runs record a measure besides its required checks. */
function checksShown(trial: Obj, runs: Obj[]): boolean {
  const arms = new Set(runs.map(r => r.arm));
  const recorded = runs.filter(r => r.passed !== null);
  const checksOf = (r: Obj): Obj => isObj(r.checks) ? r.checks : {};
  if (arms.size > 1) {
    const names = new Map<string, boolean>();
    for (const r of recorded) for (const [k, v] of entriesOf(checksOf(r))) names.set(k, typeof v === "boolean" ? names.get(k) ?? true : false);
    return [...names.values()].some(Boolean) || runs.some(r => isObj(r.judge) && (r.judge.verdict === "pass" || r.judge.verdict === "fail"));
  }
  const scenarios = isObj(trial.plan) && Array.isArray(trial.plan.scenarios) ? trial.plan.scenarios.filter(isObj) : [];
  return [...new Set(runs.map(r => r.scenario))].some(cs => {
    const plan = scenarios.find(s => s.name === cs);
    const required = plan && Array.isArray(plan.required) ? plan.required.filter(x => typeof x === "string") : [];
    const kinds = new Map<string, string>();
    for (const r of recorded.filter(x => x.scenario === cs)) for (const [k, v] of entriesOf(checksOf(r))) {
      if (required.includes(k)) continue;
      const t = typeof v === "boolean" ? "boolean" : isNumber(v) ? "number" : "other";
      kinds.set(k, kinds.get(k) === undefined || kinds.get(k) === t ? t : "other");
    }
    return [...kinds.values()].some(t => t !== "other");
  });
}

/** Sections the comparison composition plainly shows for this data and narrative. */
function comparisonSectionsShown(data: Obj, narrative: Obj, kept: string[]): string[] {
  // The same conditions the comparison composition draws each section under (comparison-compose.ts).
  const objects = (v: unknown) => Array.isArray(v) ? v.filter(isObj) : [];
  const ids = [...new Set(objects(data.alternatives).map(a => a.id).filter((id): id is string => typeof id === "string"))];
  const metrics = objects(data.metrics).filter(m => typeof m.id === "string" && METRIC_KINDS.includes(m.kind as string));
  const baseline = [narrative.baseline, data.baseline].some(b => typeof b === "string" && ids.includes(b));
  const identical = (Array.isArray(narrative.identical) ? narrative.identical : Array.isArray(data.identical) ? data.identical : [])
    .some(g => new Set((Array.isArray(g) ? g : []).filter(a => typeof a === "string" && ids.includes(a))).size > 1);
  const shown: string[] = [];
  if (ids.length) shown.push("compared");
  if (metrics.length) shown.push("results");
  if (metrics.length && ids.length > 1 && (baseline || identical || ids.length === 2)) shown.push("differences");
  if (objects(data.alternatives).some(a => typeof a.id === "string" && (Array.isArray(a.group) ? a.group.length > 0 : typeof a.group === "string" && a.group !== ""))) shown.push("groups");
  if (comparisonCases(data).length > 1 && metrics.length) shown.push("cases");
  if (objects(data.preferences).length || objects(data.rankings).some(r => Array.isArray(r.order))) shown.push("judgments");
  if (objects(narrative.criteria).length) shown.push("decision");
  if (objects(data.observations).length || objects(data.aggregates).length) shown.push("observations");
  return COMPARISON_SECTIONS.filter(s => shown.includes(s) && kept.includes(s));
}

/** Each section of a specification that holds a view says what its views show for this data. */
function sectionReadings(c: Checker, sections: unknown, at0: string, composedSections?: Set<string>): void {
  if (!Array.isArray(sections)) return;
  sections.forEach((s, i) => {
    if (!isObj(s) || !Array.isArray(s.blocks)) return;
    // A section the library composed, unchanged, is read as its composition reads it (one reading for its views).
    if (composedSections?.has(printed(s))) return;
    const at = `${c.join(at0, "sections")}[${i}]`;
    fileRefs(c, s.reading, `${at}.reading`);
    s.blocks.forEach((b, j) => {
      if (!isObj(b)) return;
      if (isObj(b.read)) for (const k of ["shows", "how", "says"]) fileRefs(c, b.read[k], `${at}.blocks[${j}].read.${k}`);
      if (b.type === "verdict") for (const k of ["headline", "detail", "rule", "conditions", "limits", "changes"]) fileRefs(c, b[k], `${at}.blocks[${j}].${k}`);
    });
    const views = s.blocks.map((b, j) => [b, j] as const).filter(([b]) => isObj(b) && typeof b.type === "string" && !PROSE_BLOCKS.includes(b.type)) as Array<readonly [Obj, number]>;
    const says = (b: Obj) => isObj(b.read) && said(b.read.says);
    if (views.length === 1) {
      if (!said(s.reading) && !says(views[0][0])) c.add("error", at, "says nothing about what its views show for this data", 'add "reading" to the section, or "read": {"says": …} to the view: what a newcomer should take from it, with the numbers that matter');
      return;
    }
    // With several views, a reading belongs to its view: one paragraph for the section cannot stand for views it does not describe.
    for (const [b, j] of views) if (!says(b)) c.add("error", `${at}.blocks[${j}]`, "says nothing about what this view shows for this data", 'in a section of several views, give each one its own "read": {"says": …}: what a newcomer should take from it, with the numbers that matter');
  });
}
/** Views a narrative appends to the composed sections: each says what it shows, since the section's reading speaks for the composition's own views. */
function appendReadings(c: Checker, append: unknown, at: string): void {
  if (!isObj(append)) return;
  for (const k of keysOf(append)) {
    const blocks = append[k];
    if (!Array.isArray(blocks)) continue;
    blocks.forEach((b, j) => {
      if (!isObj(b) || typeof b.type !== "string") return;
      const where = `${c.join(c.join(at, "append"), k)}[${j}]`;
      if (isObj(b.read)) for (const f of ["shows", "how", "says"]) fileRefs(c, b.read[f], `${where}.read.${f}`);
      if (!PROSE_BLOCKS.includes(b.type) && !(isObj(b.read) && said(b.read.says))) c.add("error", where, "says nothing about what this view shows for this data", 'add "read": {"says": …}: what a newcomer should take from it, with the numbers that matter');
    });
  }
}
const hasVerdict = (spec: Obj) => Array.isArray(spec.sections) && spec.sections.some(s => isObj(s) && Array.isArray(s.blocks) && s.blocks.some(b => isObj(b) && b.type === "verdict"));
/** The arms a trial ran, or a comparison's alternatives, and its cases, for the story's descriptions. */
/** The ids a value names where its field labels an arm or a case of its own (rows, series and items written by hand),
 * and an object flagged as an arm (a matrix column with arm: true) by its id. */
// Only ids a block brings itself: a filter ("arm", "case") selects among the trial's own, which are already required.
const ARM_FIELDS = ["arm-ref"], CASE_FIELDS = ["case-ref"];
function namedIds(value: unknown, field: Field | undefined, out: { arms: string[]; cases: string[] }): void {
  if (field === undefined || value === undefined || value === null) return;
  const take = (list: string[], v: unknown) => { if (typeof v === "string" && v && !list.includes(v)) list.push(v); };
  if (typeof field === "string") { if (ARM_FIELDS.includes(field)) take(out.arms, value); else if (CASE_FIELDS.includes(field)) take(out.cases, value); return; }
  if ("list" in field) { if (Array.isArray(value)) for (const v of value) namedIds(v, field.list, out); return; }
  if ("record" in field) {
    if (!isObj(value)) return;
    for (const k of keysOf(value)) { if (field.keys && ARM_FIELDS.includes(field.keys)) take(out.arms, k); else if (field.keys && CASE_FIELDS.includes(field.keys)) take(out.cases, k); namedIds(value[k], field.record, out); }
    return;
  }
  if ("oneOf" in field) { for (const f of field.oneOf) namedIds(value, f, out); return; }
  if ("fields" in field) {
    if (!isObj(value)) return;
    if (field.fields.arm === "boolean" && value.arm === true) take(out.arms, value.id);
    for (const [k, f] of Object.entries(field.fields)) namedIds(value[k], f, out);
  }
}
/** A comparison's cases as the composition finds them: those it declares, then every case its observations, totals,
 * judgments and rankings name. */
function comparisonCases(data: Obj): string[] {
  const out: string[] = [];
  // Evidence naming no case (a case missing, null, empty or only spaces) names none, as every view reads it.
  const take = (v: unknown) => { if (typeof v === "string" && caseKey(v) !== NO_CASE && !out.includes(v)) out.push(v); };
  for (const x of Array.isArray(data.cases) ? data.cases : []) if (isObj(x)) take(x.id);
  for (const key of ["observations", "aggregates", "preferences", "rankings"]) for (const x of Array.isArray(data[key]) ? data[key] as unknown[] : []) if (isObj(x)) take(x.case);
  return out;
}
/** Every alternative and case a report draws, from every source of data it uses: the trial (its arms and cases that
 * ran), the comparison (its alternatives and every case its data name), each block's own comparison data, the ids that
 * rows, series and items written by hand name, and a specification's own arms and cases. The one place a story's
 * descriptions are required from. */
function storyObligations(known: Known, trial: unknown, comparison: unknown, blocks: unknown[], own: { arms?: unknown; cases?: unknown }, rule: boolean): StoryNeeds {
  const alternatives = new Map<string, "arm" | "alternative">(), cases: string[] = [];
  const alt = (id: unknown, noun: "arm" | "alternative") => { if (typeof id === "string" && id && !alternatives.has(id)) alternatives.set(id, noun); };
  const kase = (id: unknown) => { if (typeof id === "string" && id && !cases.includes(id)) cases.push(id); };
  let any = false;
  if (known.trial) {
    any = true; known.ranArms.forEach(a => alt(a, "arm")); known.ranCases.forEach(kase);
    // The pairwise view reads its own arms and cases, whatever the runs name.
    const pairwise = isObj(trial) && isObj(trial.pairwise) ? trial.pairwise : {};
    for (const k of keysIn(pairwise)) {
      const p = pairwise[k];
      if (!isObj(p)) continue;
      if (Array.isArray(p.arms)) p.arms.slice(0, 2).forEach(a => alt(a, "arm"));
      if (isObj(p.scenarios)) keysIn(p.scenarios).forEach(kase);
    }
  }
  const fromComparison = (data: Obj) => { any = true; for (const a of data.alternatives as unknown[]) if (isObj(a)) alt(a.id, "alternative"); comparisonCases(data).forEach(kase); };
  if (isComparison(comparison)) fromComparison(comparison);
  for (const a of Array.isArray(own.arms) ? own.arms : []) if (isObj(a)) { any = true; alt(a.id, "alternative"); }
  for (const k of isObj(own.cases) ? keysOf(own.cases) : []) { any = true; kase(k); }
  for (const b of blocks) {
    if (!isObj(b) || typeof b.type !== "string") continue;
    if (isComparison(b.data)) fromComparison(b.data);
    const schema = Object.prototype.hasOwnProperty.call(BLOCKS, b.type) ? BLOCKS[b.type] : undefined;
    const named = { arms: [] as string[], cases: [] as string[] };
    if (schema) namedIds(b, schema, named);
    if (named.arms.length || named.cases.length) any = true;
    named.arms.forEach(a => alt(a, isObj(trial) && known.ranArms.includes(a) ? "arm" : "alternative"));
    named.cases.forEach(kase);
    // A decision matrix draws its own alternatives: those it lists, else its comparison's, else those its cells name.
    if (b.type === "decision-matrix") {
      const source = b.data !== undefined && b.data !== null ? b.data : comparison;
      const ids = (list: unknown, key: string) => (Array.isArray(list) ? list : []).map(x => isObj(x) ? x[key] : key === "id" ? x : undefined).filter((x): x is string => typeof x === "string" && x !== "");
      let drawn = Array.isArray(b.alternatives) ? ids(b.alternatives, "id") : isComparison(source) ? ids(source.alternatives, "id") : [];
      if (!drawn.length) drawn = ids(b.cells, "alternative");
      if (drawn.length) any = true;
      drawn.forEach(a => alt(a, isObj(trial) && known.ranArms.includes(a) ? "arm" : "alternative"));
    }
  }
  if (!any) return { rule, alternatives: null, cases: null };
  return { rule, alternatives, cases: known.trial || cases.length ? cases : null };
}
/** What a specification's story must describe, from every source of data it uses, read as validateSpec reads them. */
function specNeeds(spec: Obj, known: Known, trial: unknown, comparison: unknown): StoryNeeds {
  return storyObligations(known, trial, comparison, blocksOf(spec), spec, hasVerdict(spec));
}
/** The cases a report covers: every case its story must describe, from every source of data it uses (its trial's runs
 * and pairwise scenarios, its comparison's declared cases and every case any of its evidence names, its views' own data,
 * the cases its rows and labels name). The story check and a collection's "Cases" statement both read this one list. */
export function reportCases(spec: ReportSpec | unknown, options: { trial?: unknown; comparison?: unknown } = {}): string[] {
  if (!isObj(spec)) return [];
  const trial = wellFormedTrial(spec.trial ? spec.trial : options.trial), comparison = spec.comparison ? spec.comparison : options.comparison;
  return specNeeds(spec, knownFrom(trial, comparison), trial, comparison).cases || [];
}
/** An identifier the views group or label by: text with something in it. */
const isId = (v: unknown): v is string => typeof v === "string" && !!v.trim();
const ID_HINT = "write the trial with trial.py report RUN_DIR --out FILE, which names each as text";
/** The one check of trial data, however it enters: a specification's own `trial`, a trial supplied beside a
 * specification, a narrative's trial (so every composed trial report), and a collection member's. It must be trial report
 * data, and every identifier the views group or label by must be text: each run's arm and scenario (and its job, when
 * given), each plan scenario's name, and the two arms of each pairwise judgment. trial.py writes them all, so a value
 * left out, null, empty, only spaces or not text is malformed input, refused at its place; every later check reads the
 * trial through wellFormedTrial, so none descends into such a record. False when it is not trial data. Where two
 * entries check one trial, each problem is listed once (order removes the repeat). */
function checkTrial(c: Checker, trial: unknown, where: string): boolean {
  if (!isObj(trial) || !Array.isArray(trial.runs)) { c.add("error", where, "is not trial report data", "write it with trial.py report RUN_DIR --out FILE"); return false; }
  trial.runs.forEach((r, i) => {
    if (!isObj(r)) return;
    if (!isId(r.arm)) c.add("error", `${where}.runs[${i}].arm`, "a trial run must name its arm", ID_HINT);
    if (!isId(r.scenario)) c.add("error", `${where}.runs[${i}].scenario`, "a trial run must name its scenario", ID_HINT);
    if (r.job !== undefined && r.job !== null && !isId(r.job)) c.add("error", `${where}.runs[${i}].job`, "a trial run's job, when given, must name its record", ID_HINT);
    if (!isVerdict(r.passed)) c.add("error", `${where}.runs[${i}].passed`, "a trial run must say whether it passed: true, false, or null for no verdict", ID_HINT.replace("names each as text", "writes each run's verdict"));
  });
  if (isObj(trial.plan) && Array.isArray(trial.plan.scenarios))
    trial.plan.scenarios.forEach((sc, i) => { if (isObj(sc) && !isId(sc.name)) c.add("error", `${where}.plan.scenarios[${i}].name`, "a plan scenario must have a name", ID_HINT); });
  // A pairwise judgment names exactly two different arms this trial knows, with its overall counts and its counts by case.
  if (isObj(trial.pairwise)) {
    const known = trialArms(trial);
    for (const k of keysOf(trial.pairwise)) {
      const p = trial.pairwise[k], at = c.join(c.join(where, "pairwise"), k);
      if (!isObj(p)) { c.add("error", at, "a pairwise judgment must be an object with its arms and counts", ID_HINT); continue; }
      if (!Array.isArray(p.arms) || p.arms.length !== 2) c.add("error", c.join(at, "arms"), "a pairwise judgment must name its two arms", ID_HINT);
      else {
        p.arms.forEach((a, i) => {
          if (!isId(a)) c.add("error", `${c.join(at, "arms")}[${i}]`, "a pairwise judgment must name its arms", ID_HINT);
          else if (!known.includes(a)) c.add("error", `${c.join(at, "arms")}[${i}]`, `"${clip(a)}" is not an arm of this trial`, known.length ? `arms of this trial: ${listOf(known)}` : "this trial has no arms");
        });
        if (isId(p.arms[0]) && p.arms[0] === p.arms[1]) c.add("error", c.join(at, "arms"), "a pairwise judgment must name two different arms", ID_HINT);
      }
      if (!isObj(p.overall)) c.add("error", c.join(at, "overall"), "a pairwise judgment needs its overall counts", ID_HINT.replace("names each as text", "writes them"));
      if (!isObj(p.scenarios)) c.add("error", c.join(at, "scenarios"), "a pairwise judgment needs its counts by case", ID_HINT.replace("names each as text", "writes them"));
    }
  }
  return true;
}
/** A run's verdict: passed, failed, or null for none (an invalid run). */
const isVerdict = (v: unknown) => v === true || v === false || v === null;
/** The trial every check after checkTrial reads: only the runs, plan scenarios and pairwise judgments whose identifiers
 * are well formed, so no check descends into a record whose identifiers are malformed. */
function wellFormedTrial(trial: unknown): unknown {
  if (!isObj(trial) || !Array.isArray(trial.runs)) return trial;
  const runs = trial.runs.filter(r => !isObj(r) || (isId(r.arm) && isId(r.scenario) && (r.job === undefined || r.job === null || isId(r.job)) && isVerdict(r.passed)));
  const plan = isObj(trial.plan) && Array.isArray(trial.plan.scenarios) ? { ...trial.plan, scenarios: trial.plan.scenarios.filter(sc => !isObj(sc) || isId(sc.name)) } : trial.plan;
  const known = trialArms(trial);
  const pairwise = isObj(trial.pairwise) ? Object.fromEntries(entriesOf(trial.pairwise).filter(([, p]) => wellFormedPair(p, known))) : trial.pairwise;
  return { ...trial, runs, ...(plan !== undefined ? { plan } : {}), ...(pairwise !== undefined ? { pairwise } : {}) };
}
/** A check's problems, moved from the place it names its input (`from`, such as "comparison") to where the input
 * entered (`at`, such as "sections[0].blocks[1].data"). */
function placed(problems: Problem[], from: string, at: string): Problem[] {
  return problems.map(p => ({ ...p, where: p.where === from ? at : p.where.startsWith(`${from}.`) || p.where.startsWith(`${from}[`) ? `${at}${p.where.slice(from.length)}` : `${at}.${p.where}` }));
}
/** The one check of comparison data, however it enters: a specification's own `comparison`, one supplied beside it, a
 * view's own `data` (in a specification or a narrative), and a collection member's. False when it is not comparison data. */
function checkComparison(c: Checker, data: unknown, where: string): boolean {
  if (!isComparison(data)) { c.add("error", where, "is not comparison data", 'a comparison is {"alternatives": [ … ], "metrics": [ … ]}; see catalog.md'); return false; }
  c.problems.push(...placed(validateComparison(data), "comparison", where));
  return true;
}
/** The one check of a collection, however it enters: a specification's own `collection`, or one supplied beside it. */
function checkCollection(c: Checker, data: unknown, where: string): void {
  c.problems.push(...placed(validateCollection(data), "collection", where));
}
/** Comparison data each view of a specification or a narrative carries as its own (`data`), checked where it sits. */
function viewData(c: Checker, owner: Obj, at: string): void {
  const each = (b: unknown, where: string) => {
    if (!isObj(b) || typeof b.type !== "string" || b.data === undefined || b.data === null) return;
    const schema = Object.prototype.hasOwnProperty.call(BLOCKS, b.type) ? BLOCKS[b.type] : undefined;
    // Placed as every problem of a view is, under the view's place and type.
    if (schema && Object.prototype.hasOwnProperty.call(schema.fields, "data")) checkComparison(c, b.data, c.join(`${where} (${b.type})`, "data"));
  };
  (Array.isArray(owner.sections) ? owner.sections : []).forEach((s, i) => { if (isObj(s) && Array.isArray(s.blocks)) s.blocks.forEach((b, j) => each(b, `${c.join(c.join(at, "sections"), i)}.blocks[${j}]`)); });
  if (isObj(owner.append)) for (const k of keysOf(owner.append)) if (Array.isArray(owner.append[k])) (owner.append[k] as unknown[]).forEach((b, j) => each(b, c.join(c.join(c.join(at, "append"), k), j)));
}
/** Every block of a specification's or a narrative's own sections, and of its appended blocks. */
function blocksOf(owner: Obj): unknown[] {
  const out: unknown[] = [];
  for (const s of Array.isArray(owner.sections) ? owner.sections : []) if (isObj(s) && Array.isArray(s.blocks)) out.push(...s.blocks);
  if (isObj(owner.append)) for (const k of keysOf(owner.append)) if (Array.isArray(owner.append[k])) out.push(...(owner.append[k] as unknown[]));
  return out;
}


// ------------------------------------------------------------------ public

/** Specifications this library composed in memory: the problems their inputs had, and the sections it built. */
interface Composition { problems: Problem[]; sections: Set<string> }
const COMPOSED = new WeakMap<object, Composition>();
const printed = (v: unknown): string => { try { return JSON.stringify(v) ?? ""; } catch { return ""; } };
/** Records a specification the library composed (from a trial, a comparison or a collection) with the problems
 * found in its inputs (its narrative's among them), which only it can know, and the sections it built, each as
 * written: a section still as built reads as its composition reads it, one reading for its views. Every check of
 * the specification checks what it says now, data and story included, edited or not. Only an object composed in
 * memory can be recorded: a "problems" field in a specification read from JSON proves nothing, and its sections
 * are checked as any author's are. */
export function composed<T extends object>(spec: T, problems: Problem[]): T {
  const o = spec as unknown as Obj;
  COMPOSED.set(spec, { problems, sections: new Set((Array.isArray(o.sections) ? o.sections : []).map(printed)) });
  return spec;
}

/** Problems in a report specification, checked as it is written now: every check, whatever it says of itself,
 * with, for one this library composed, the problems its inputs had. */
export function validateSpec(spec: ReportSpec | unknown, options: { trial?: unknown; comparison?: unknown; collection?: unknown } = {}): Problem[] {
  if (!isObj(spec)) return [{ level: "error", where: "spec", message: `expected an object with "title" and "sections", found ${found(spec)}`, hint: 'a specification is {"title": "…", "sections": [ … ]}' }];
  const own = COMPOSED.get(spec as object);
  const inputs = own ? own.problems.map(carried).filter((p): p is Problem => p !== null) : [];
  // As in the browser: a specification without trial data of its own borrows the trial supplied beside it.
  // Every check after the trial's own reads only its well-formed records.
  const trial = wellFormedTrial((spec as Obj).trial ? (spec as Obj).trial : options.trial);
  const comparison = (spec as Obj).comparison ? (spec as Obj).comparison : options.comparison;
  const collection = (spec as Obj).collection ? (spec as Obj).collection : options.collection;
  const c = new Checker(knownFrom(trial, comparison, collection), registered(), "spec");
  c.shape(spec, SPEC, "", {
    trial: (value, where) => { checkTrial(c, value, where); },
    comparison: (value, where) => { checkComparison(c, value, where); },
    collection: (value, where) => { checkCollection(c, value, where); },
    sections: value => {
      if (!Array.isArray(value)) return;
      const ids: string[] = [];
      value.forEach((s, i) => {
        if (!isObj(s) || typeof s.id !== "string" || !/^[A-Za-z][\w:.-]*$/.test(s.id)) return;
        if (ids.includes(s.id)) c.add("warning", `sections[${i}].id`, `section id "${clip(s.id)}" is already used by an earlier section`, "give each section its own id, so links reach the section meant");
        ids.push(s.id);
      });
    },
  });
  // Data supplied beside the specification is what its views read: checked as its own would be, by the same check.
  if (!(spec as Obj).trial && options.trial !== undefined && options.trial !== null) checkTrial(c, options.trial, "trial");
  if (!(spec as Obj).comparison && options.comparison !== undefined && options.comparison !== null) checkComparison(c, options.comparison, "comparison");
  if (!(spec as Obj).collection && options.collection !== undefined && options.collection !== null) checkCollection(c, options.collection, "collection");
  viewData(c, spec as Obj, "");
  storyChecks(c, spec as Obj, "", specNeeds(spec as Obj, c.known, trial, comparison));
  sectionReadings(c, (spec as Obj).sections, "", own?.sections);
  // A composition copies its inputs into the specification (a narrative's story, its verdict), so the check can find an
  // input's mistake again: at the specification's root, in its story, or in a section still as built, a problem with
  // the same level and message as an input's is that one, listed once at the input's place, where it is corrected.
  const sections = Array.isArray((spec as Obj).sections) ? (spec as Obj).sections as unknown[] : [];
  const copied = (where: string) => {
    if (where === "spec" || where === "story" || where.startsWith("story.")) return true;
    const i = /^sections\[(\d+)\]/.exec(where);
    return !!i && !!own?.sections.has(printed(sections[Number(i[1])]));
  };
  const again = (p: Problem) => !!own && copied(p.where) && inputs.some(q => q.level === p.level && q.message === p.message);
  return order([...inputs, ...c.problems.filter(p => !again(p))]);
}


/** Problems in a narrative for the trial composition, checked against the
 * trial's arms and cases when the trial data is given. */
export function validateNarrative(narrative: unknown, given?: unknown): Problem[] {
  // Every check after the trial's own reads only its well-formed records.
  const trial = wellFormedTrial(given);
  const c = new Checker(knownFrom(trial), registered(), "narrative");
  if (!isObj(narrative)) return [{ level: "error", where: "narrative", message: `expected an object, found ${found(narrative)}`, hint: 'a narrative is an object such as {"title": "…", "decision": { … }}' }];
  // The trial the narrative is told against: a narrative needs trial data to be read against.
  if (given !== undefined && given !== null && !checkTrial(c, given, "trial")) return order(c.problems);
  const strings = (v: unknown) => Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : null;
  const include = strings(narrative.include)?.map(sectionKey) || null, exclude = (strings(narrative.exclude) || []).map(sectionKey);
  const kept = DEFAULT_SECTIONS.filter(s => (include ? include.includes(s) : !OPT_IN_SECTIONS.includes(s)) && !exclude.includes(s));
  const leftOut = (id: string) => OPT_IN_SECTIONS.includes(sectionKey(id)) && !exclude.includes(sectionKey(id)) ? `is drawn only when include names it` : "is left out by include or exclude";
  const sectionIds = (value: unknown, where: string) => (Array.isArray(value) ? value : []).forEach((id, i) => {
    if (typeof id !== "string" || SECTION_NAMES.includes(id)) return;
    const s = suggest(id, DEFAULT_SECTIONS);
    c.add("error", c.join(where, i), `"${clip(id)}" is not a section of the trial report`, s ? `did you mean "${s}"?` : `sections: ${DEFAULT_SECTIONS.join(", ")}`);
  });
  c.shape(narrative, NARRATIVE, "narrative", {
    decision: (value, where) => { if (isObj(value) && value.rule !== undefined) c.add("warning", c.join(where, "rule"), "the decision rule comes from the trial's plan, so this value is not shown", "remove it; the verdict quotes the plan's rule word for word"); },
    arms: (value, where) => {
      if (!Array.isArray(value)) return;
      const seen: string[] = [];
      value.forEach((a, i) => {
        if (!isObj(a) || typeof a.id !== "string") return;
        if (seen.includes(a.id)) c.add("warning", c.join(c.join(where, i), "id"), `arm "${clip(a.id)}" is listed more than once; the first entry is used`, "keep one entry per arm");
        seen.push(a.id);
      });
    },
    identical: (value, where) => {
      if (!Array.isArray(value)) return;
      const placed: string[] = [];
      value.forEach((group, i) => {
        const members = strings(group);
        if (!members) return;
        if (new Set(members).size < 2) c.add("warning", c.join(where, i), "an identical group needs at least two different arms; this one shows no spread", "list every arm that received the same material in one group");
        members.forEach(arm => {
          if (placed.includes(arm)) c.add("warning", c.join(where, i), `arm "${clip(arm)}" is already in an earlier identical group`, "each arm belongs to at most one group");
        });
        for (const arm of new Set(members)) placed.push(arm);
        // Copies differ only by chance; arms whose recorded settings differ do not.
        const first = members.find(a => Object.prototype.hasOwnProperty.call(c.known.settings, a));
        if (first === undefined) return;
        const base = c.known.settings[first];
        (group as unknown[]).forEach((arm, j) => {
          const other = typeof arm === "string" && Object.prototype.hasOwnProperty.call(c.known.settings, arm) ? c.known.settings[arm] : undefined;
          if (typeof arm !== "string" || arm === first || !other) return;
          const differ = [...new Set([...Object.keys(base), ...Object.keys(other)])].filter(k => !MATERIAL_TEXT.includes(k) && canon(base[k]) !== canon(other[k])).sort((a, b) => (a < b ? -1 : a > b ? 1 : 0));
          if (differ.length) c.add("error", c.join(c.join(where, i), j), `"${clip(arm)}" differs from "${clip(first)}" in ${listOf(differ)}, so the gap between them is not chance alone`, "identical is for copies whose every recorded setting matches; leave these arms out of it");
        });
      });
    },
    pairs: (value, where) => {
      if (!Array.isArray(value)) return;
      value.forEach((pair, i) => {
        const at = c.join(where, i);
        if (Array.isArray(pair) && pair.length !== 2) c.add("error", at, `a pair names a base case and its variant, found ${plural(pair.length, "item")}`, 'write ["base-case", "variant-case"], or {"base": "…", "variant": "…"}');
        const [base, variant] = Array.isArray(pair) ? pair : isObj(pair) ? [pair.base, pair.variant] : [];
        if (typeof base === "string" && base === variant) c.add("warning", at, `"${clip(base)}" cannot be a variant of itself, so this pair is not used`, "name two different cases");
      });
    },
    threshold: (value, where) => {
      const v = isNumber(value) ? value : isObj(value) && isNumber(value.value) ? value.value : null;
      if (v !== null && Math.abs(v) > 1) c.add("error", isNumber(value) ? where : c.join(where, "value"), `the threshold ${v} is outside −1 to 1, so it is not drawn`, "write the difference as a share: 0.15 for +15 points");
    },
    include: sectionIds,
    exclude: sectionIds,
    sections: (value, where) => {
      if (!Array.isArray(value)) return;
      const before: string[] = [...kept];
      value.forEach((s, i) => {
        if (!isObj(s)) return;
        const after = s.after;
        if (typeof after === "string" && !before.includes(sectionKey(after))) {
          const at = c.join(c.join(where, i), "after");
          if (SECTION_NAMES.includes(after)) c.add("warning", at, `section "${after}" ${leftOut(after)}, so this section goes at the end`, "keep that section, or name another one to follow");
          else {
            const options = [...new Set([...DEFAULT_SECTIONS, ...before])];
            const hint = suggest(after, options);
            c.add("error", at, `no section "${clip(after)}" comes before this one, so this section goes at the end`, hint ? `did you mean "${hint}"?` : `sections: ${listOf(options)}`);
          }
        }
        const key = typeof s.id === "string" && s.id ? s.id : s.title;
        if (typeof key === "string") before.push(key);
      });
    },
    append: (value, where) => {
      if (!isObj(value)) return;
      for (const k of keysOf(value)) {
        const at = c.join(where, k);
        if (!SECTION_NAMES.includes(k)) {
          const s = suggest(k, DEFAULT_SECTIONS);
          c.add("error", at, `"${clip(k)}" is not a section of the trial report, so these blocks do not appear`, s ? `did you mean "${s}"?` : `sections: ${DEFAULT_SECTIONS.join(", ")}`);
        } else if (!kept.includes(sectionKey(k))) c.add("warning", at, `section "${k}" ${leftOut(k)}, so these blocks do not appear`, "keep that section, or append the blocks to another one");
      }
    },
  });
  viewData(c, narrative, "narrative");
  storyChecks(c, narrative, "narrative", storyObligations(c.known, trial, undefined, blocksOf(narrative), {}, true));
  pointedRule(c, narrative, isObj(trial) && isObj(trial.plan) ? trial.plan.decision_rule : undefined, "the plan's");
  readingsChecks(c, narrative, "narrative", trialSectionsShown(trial, narrative, kept), SECTION_NAMES, sectionKey);
  sectionReadings(c, narrative.sections, "narrative");
  appendReadings(c, narrative.append, "narrative");
  if (isObj(narrative.decision)) for (const k of ["headline", "detail", "conditions", "limits", "changes"]) fileRefs(c, narrative.decision[k], `narrative.decision.${k}`);
  return order(c.problems);
}

/** The level an ordinal value names: its name, or, when the metric lists its levels, a 0-based index. */
function levelOf(levels: string[], value: unknown, explicit: boolean): number {
  if ((typeof value === "string" || isNumber(value)) && levels.includes(String(value))) return levels.indexOf(String(value));
  if (!explicit && typeof value === "string" && NUMERIC_TEXT.test(value) && levels.includes(String(Number(value)))) return levels.indexOf(String(Number(value)));
  return explicit && isNumber(value) && Number.isInteger(value) && value >= 0 && value < levels.length ? value : -1;
}

/** Problems in a comparison of any alternatives, and in a narrative for its
 * composition when one is given: references to alternatives, metrics and cases
 * that do not exist, values that do not fit their metric's kind, judgments that
 * name neither alternative, and narrative sections or criteria the composition
 * cannot use. Invalid observations are not problems; they are counted. */
export function validateComparison(data: unknown, narrative?: unknown): Problem[] {
  if (!isObj(data)) return [{ level: "error", where: "comparison", message: `expected an object with "alternatives" and "metrics", found ${found(data)}`, hint: 'a comparison is {"alternatives": [ … ], "metrics": [ … ]}; see catalog.md' }];
  const c = new Checker(knownFrom(undefined, isComparison(data) ? data : { alternatives: [] }), registered(), "comparison");
  c.shape(data, COMPARISON, "comparison");
  const list = (key: string): unknown[] => Array.isArray(data[key]) ? data[key] as unknown[] : [];
  for (const key of ["alternatives", "cases", "metrics"]) {
    const seen: string[] = [];
    list(key).forEach((x, i) => {
      if (!isObj(x) || typeof x.id !== "string") return;
      if (seen.includes(x.id)) c.add("error", `comparison.${key}[${i}].id`, `id "${clip(x.id)}" is already used by an earlier entry`, "give each entry its own id; the views read the first");
      seen.push(x.id);
    });
  }
  const metrics = new Map<string, Obj>();
  for (const m of list("metrics")) if (isObj(m) && typeof m.id === "string" && !metrics.has(m.id)) metrics.set(m.id, m);
  const levels = (m: Obj): string[] => Array.isArray(m.levels) ? m.levels.filter(isText).map(String) : [];
  const primaries = list("metrics").filter(m => isObj(m) && m.primary === true).length;
  if (primaries > 1) c.add("warning", "comparison.metrics", `${primaries} metrics are marked primary`, "mark one; the views read the first as primary");
  const owner = (kind: string): string | undefined => {
    const of = [...metrics.values()].filter(m => m.kind === kind);
    return of.length === 1 ? of[0].id as string : of.find(m => m.primary === true)?.id as string | undefined;
  };
  const unnamed = (x: unknown) => isObj(x) && !(typeof x.metric === "string" && x.metric);
  list("metrics").forEach((m, i) => {
    if (!isObj(m) || typeof m.id !== "string") return;
    const at = `comparison.metrics[${i}]`, id = m.id;
    if (Array.isArray(m.levels) && m.kind !== "ordinal") c.add("warning", `${at}.levels`, "levels are read only for ordinal metrics", 'remove them, or set "kind": "ordinal"');
    if (new Set(levels(m)).size < levels(m).length) c.add("error", `${at}.levels`, "a level is listed more than once, so the order is ambiguous", "list each level once, lowest first");
    if ((m.kind === "binary" || m.kind === "count") && isNumber(m.threshold) && (m.threshold < 0 || m.threshold > 1)) c.add("error", `${at}.threshold`, `the threshold ${m.threshold} is outside 0 to 1`, "write a rate as a share: 0.15 for 15%");
    if (m.kind === "ordinal" && !levels(m).length && (list("observations").some(o => isObj(o) && o.metric === id && o.valid !== false && typeof o.value === "string" && o.value !== "" && !NUMERIC_TEXT.test(o.value))
      || list("aggregates").some(a => isObj(a) && a.metric === id && isObj(a.counts) && keysOf(a.counts).some(k => !NUMERIC_TEXT.test(k)))))
      c.add("error", at, `ordinal metric "${clip(id)}" names no levels, so its text values have no order`, '"levels" lists them lowest first, such as ["poor", "fair", "good"]');
    const judged = m.kind === "preference" || m.kind === "rank";
    const hasData = list("observations").some(o => isObj(o) && o.metric === id) || list("aggregates").some(a => isObj(a) && a.metric === id)
      || (judged && ([...(m.kind === "preference" ? list("preferences") : []), ...list("rankings")].some(j => isObj(j) && (j.metric === id || (unnamed(j) && owner(m.kind as string) === id)))));
    if (!hasData && METRIC_KINDS.includes(m.kind as string)) c.add("warning", at, `metric "${clip(id)}" has no ${judged ? "observations, aggregates or judgments" : "observations or aggregates"}, so its views show nothing`, "add its data, or remove the metric");
  });
  list("observations").forEach((o, i) => {
    if (!isObj(o)) return;
    const at = `comparison.observations[${i}]`, m = typeof o.metric === "string" ? metrics.get(o.metric) : undefined;
    if (!m) return;
    const kind = m.kind, v = o.value, name = clip(String(m.id));
    if (o.n !== undefined && o.n !== null && kind !== "count") c.add("warning", `${at}.n`, '"n" is read only for count metrics', "remove it, or make the metric a count");
    if (kind === "preference") return c.add("warning", at, 'preference metrics read "preferences" and "rankings", so this observation is counted invalid', "record head-to-head judgments in preferences, or use a rank or numeric metric");
    if (o.valid === false || v === null || v === undefined || v === "") return;
    const wrong = (what: string, hint: string) => c.add("error", `${at}.value`, `expected ${what} for ${kind} metric "${name}", found ${found(v)}`, hint);
    const unread = 'mark an observation without a result "valid": false';
    if (kind === "binary" && !(typeof v === "boolean" || v === 0 || v === 1)) wrong("true or false", `write true or false (or 1 and 0); ${unread}`);
    if (kind === "numeric" && !isNumber(v)) wrong("a number", typeof v === "string" && NUMERIC_TEXT.test(v) ? "write the number without quotes" : `write a number; ${unread}`);
    if (kind === "rank" && !(isNumber(v) && v >= 1)) wrong("a position of 1 or more", "1 is first place");
    if (kind === "count") {
      if (!(isNumber(v) && Number.isInteger(v) && v >= 0)) wrong("a whole number of successes", 'write the successes as a number, with "n" for the trials');
      else if (!isNumber(o.n)) c.add("error", at, 'a count needs "n", the trials behind it', 'add "n", such as {"value": 12, "n": 400}');
      else if (v > o.n) c.add("error", `${at}.value`, `${v} successes is more than n (${o.n}) trials`, "successes cannot exceed trials");
    }
    if (kind === "ordinal" && levels(m).length && levelOf(levels(m), v, true) < 0)
      c.add("error", `${at}.value`, `${found(v)} is not a level of ordinal metric "${name}"`, `levels: ${listOf(levels(m))}`);
  });
  list("aggregates").forEach((a, i) => {
    if (!isObj(a)) return;
    const at = `comparison.aggregates[${i}]`, m = typeof a.metric === "string" ? metrics.get(a.metric) : undefined;
    if (isNumber(a.k) && isNumber(a.n) && a.k > a.n) c.add("error", at, `k (${a.k}) is larger than n (${a.n})`, "k counts successes (or wins) out of n trials (or decisive judgments)");
    if (isNumber(a.lo) && isNumber(a.hi) && a.lo > a.hi) c.add("error", at, `lo (${a.lo}) is above hi (${a.hi})`, "write the interval with lo at or below hi");
    if (!m) return;
    const kind = m.kind;
    if ((kind === "binary" || kind === "count" || kind === "preference") && !(isNumber(a.k) && isNumber(a.n))) c.add("error", at, `a ${kind} aggregate needs "k" and "n"`, "k successes (or wins) out of n trials (or decisive judgments)");
    if ((kind === "numeric" || kind === "rank") && !isNumber(a.mean)) c.add("error", at, `a ${kind} aggregate needs "mean"`, 'add "mean", with "sd" and "n" for an interval');
    if (kind === "ordinal" && !isObj(a.counts)) c.add("error", at, 'an ordinal aggregate needs "counts"', 'counts per level, such as {"good": 12, "fair": 5}');
    if (kind === "ordinal" && isObj(a.counts) && levels(m).length)
      for (const k of keysOf(a.counts)) if (!levels(m).includes(k)) c.add("error", c.join(`${at}.counts`, k), `"${clip(k)}" is not a level of ordinal metric "${clip(String(m.id))}"`, `levels: ${listOf(levels(m))}`);
  });
  const judgedBy = (j: Obj, where: string) => {
    const m = typeof j.metric === "string" ? metrics.get(j.metric) : undefined;
    if (m && typeof m.kind === "string" && m.kind !== "preference" && m.kind !== "rank") c.add("warning", where, `metric "${clip(String(m.id))}" is a ${m.kind} metric, so this judgment does not count toward it`, "name a preference or rank metric, or leave metric out for the overall preference");
  };
  list("preferences").forEach((p, i) => {
    if (!isObj(p)) return;
    const at = `comparison.preferences[${i}]`;
    if (typeof p.a === "string" && p.a === p.b) c.add("error", at, `"${clip(p.a)}" is judged against itself`, "name two different alternatives");
    else if (p.winner !== undefined && p.winner !== null && p.winner !== "tie" && p.winner !== p.a && p.winner !== p.b)
      c.add("error", `${at}.winner`, `${found(p.winner)} names neither alternative of this judgment`, `write ${typeof p.a === "string" ? `"${clip(p.a)}"` : "a"}, ${typeof p.b === "string" ? `"${clip(p.b)}"` : "b"}, "tie", or null when no judgment was reached`);
    judgedBy(p, `${at}.metric`);
  });
  list("rankings").forEach((r, i) => {
    if (!isObj(r) || !Array.isArray(r.order)) return;
    const at = `comparison.rankings[${i}]`, seen: string[] = [];
    r.order.forEach((id, j) => {
      if (typeof id !== "string") return;
      if (seen.includes(id)) c.add("error", `${at}.order[${j}]`, `"${clip(id)}" is placed twice in one ranking`, "list each alternative once, first place first");
      seen.push(id);
    });
    if (r.order.length < 2) c.add("warning", `${at}.order`, "a ranking of fewer than two alternatives compares nothing", "list at least two alternatives, first place first");
    judgedBy(r, `${at}.metric`);
  });
  list("identical").forEach((g, i) => {
    if (Array.isArray(g) && new Set(g.filter(x => typeof x === "string")).size < 2) c.add("warning", `comparison.identical[${i}]`, "an identical group needs at least two different alternatives; this one shows no spread", "list every alternative that received the same material in one group");
  });
  const prefs = [...metrics.values()].filter(m => m.kind === "preference");
  const loose = list("preferences").filter(unnamed).length;
  if (loose && prefs.length > 1 && !prefs.some(m => m.primary === true))
    c.add("warning", "comparison.preferences", `${plural(loose, "judgment")} name no metric, and ${prefs.length} preference metrics could own them`, 'name the metric on each judgment, or mark one preference metric "primary"; until then they count only toward the overall preference');
  if (narrative !== undefined) c.problems.push(...comparisonNarrative(narrative, c.known, data));
  return order(c.problems);
}

/** Problems in a narrative for the comparison composition. */
function comparisonNarrative(narrative: unknown, known: Known, data: Obj): Problem[] {
  if (!isObj(narrative)) return [{ level: "error", where: "narrative", message: `expected an object, found ${found(narrative)}`, hint: 'a narrative is an object such as {"title": "…", "decision": { … }}' }];
  const c = new Checker(known, registered(), "narrative");
  const strings = (v: unknown) => Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : null;
  const include = strings(narrative.include)?.map(comparisonKey) || null, exclude = (strings(narrative.exclude) || []).map(comparisonKey);
  const kept = COMPARISON_SECTIONS.filter(s => (!include || include.includes(s)) && !exclude.includes(s));
  const sectionIds = (value: unknown, where: string) => (Array.isArray(value) ? value : []).forEach((id, i) => {
    if (typeof id !== "string" || COMPARISON_NAMES.includes(id)) return;
    const s = suggest(id, COMPARISON_SECTIONS);
    c.add("error", c.join(where, i), `"${clip(id)}" is not a section of the comparison report`, s ? `did you mean "${s}"?` : `sections: ${COMPARISON_SECTIONS.join(", ")}`);
  });
  c.shape(narrative, COMPARISON_NARRATIVE, "narrative", {
    decision: (value, where) => { if (isObj(value) && value.rule !== undefined) c.add("warning", c.join(where, "rule"), "the decision rule comes from the comparison's decision_rule, so this value is not shown", "remove it; the verdict quotes the comparison's rule word for word"); },
    alternatives: (value, where) => {
      if (!Array.isArray(value)) return;
      const seen: string[] = [];
      value.forEach((a, i) => {
        if (!isObj(a) || typeof a.id !== "string") return;
        if (seen.includes(a.id)) c.add("warning", c.join(c.join(where, i), "id"), `alternative "${clip(a.id)}" is listed more than once; the first entry is used`, "keep one entry per alternative");
        seen.push(a.id);
      });
    },
    identical: (value, where) => (Array.isArray(value) ? value : []).forEach((g, i) => {
      if (Array.isArray(g) && new Set(g.filter(x => typeof x === "string")).size < 2) c.add("warning", c.join(where, i), "an identical group needs at least two different alternatives; this one shows no spread", "list every alternative that received the same material in one group");
    }),
    criteria: (value, where) => {
      if (!Array.isArray(value)) return;
      const rows = value.filter(isObj).filter(r => r.better !== "none"), weighted = rows.filter(r => isNumber(r.weight)).length;
      const rated = (Array.isArray(narrative.cells) ? narrative.cells : []).filter(isObj).map(x => x.criterion);
      value.forEach((r, i) => {
        if (!isObj(r)) return;
        if (r.metric === undefined && r.scores === undefined && !(r.id !== undefined && rated.includes(r.id))) c.add("error", c.join(where, i), 'a criterion needs "metric", "scores" or cells that rate it', "name the metric that measures it, give each alternative a score, or rate it in cells by its id");
        if (isNumber(r.weight) && r.weight < 0) c.add("error", c.join(c.join(where, i), "weight"), "a weight cannot be negative", "write how much the criterion counts, 0 or more");
      });
      if (weighted && weighted < rows.length) c.add("warning", where, `${weighted} of ${rows.length} criteria carry a weight, so the weighted total leaves out the other ${rows.length - weighted}`, "weight every criterion that should count toward the total");
    },
    include: sectionIds,
    exclude: sectionIds,
    sections: (value, where) => {
      if (!Array.isArray(value)) return;
      const before: string[] = [...kept];
      value.forEach((s, i) => {
        if (!isObj(s)) return;
        const after = s.after;
        if (typeof after === "string" && !before.includes(comparisonKey(after))) {
          const at = c.join(c.join(where, i), "after");
          if (COMPARISON_NAMES.includes(after)) c.add("warning", at, `section "${after}" is left out by include or exclude, so this section goes at the end`, "keep that section, or name another one to follow");
          else {
            const options = [...new Set([...COMPARISON_SECTIONS, ...before])];
            const hint = suggest(after, options);
            c.add("error", at, `no section "${clip(after)}" comes before this one, so this section goes at the end`, hint ? `did you mean "${hint}"?` : `sections: ${listOf(options)}`);
          }
        }
        const key = typeof s.id === "string" && s.id ? s.id : s.title;
        if (typeof key === "string") before.push(key);
      });
    },
    append: (value, where) => {
      if (!isObj(value)) return;
      for (const k of keysOf(value)) {
        const at = c.join(where, k);
        if (!COMPARISON_NAMES.includes(k)) {
          const s = suggest(k, COMPARISON_SECTIONS);
          c.add("error", at, `"${clip(k)}" is not a section of the comparison report, so these blocks do not appear`, s ? `did you mean "${s}"?` : `sections: ${COMPARISON_SECTIONS.join(", ")}`);
        } else if (!kept.includes(comparisonKey(k))) c.add("warning", at, `section "${k}" is left out by include or exclude, so these blocks do not appear`, "keep that section, or append the blocks to another one");
      }
    },
  });
  viewData(c, narrative, "narrative");
  storyChecks(c, narrative, "narrative", storyObligations(known, undefined, data, blocksOf(narrative), {}, true));
  pointedRule(c, narrative, data.decision_rule, "the comparison's");
  readingsChecks(c, narrative, "narrative", comparisonSectionsShown(data, narrative, kept), COMPARISON_NAMES, comparisonKey);
  sectionReadings(c, narrative.sections, "narrative");
  appendReadings(c, narrative.append, "narrative");
  if (isObj(narrative.decision)) for (const k of ["headline", "detail", "conditions", "limits", "changes"]) fileRefs(c, narrative.decision[k], `narrative.decision.${k}`);
  return c.problems;
}

/** A compact panel at the top of a report listing the problems in its input;
 * empty when there are none. Errors open the list; warnings alone leave it
 * folded under a one-line summary that stays visible. */
/** Problems in a collection of reports: its shape, each member's data, and
 * each member's narrative checked against that data as its standalone report
 * would check it. */
export function validateCollection(collection: unknown): Problem[] {
  if (!isCollection(collection)) return [{ level: "error", where: "collection", message: `expected an object with a "members" list, found ${found(collection)}`, hint: 'a collection is {"members": [{"id": "…", "trial": { … }, "narrative": { … }}, …]}; see catalog.md' }];
  const c = new Checker(knownFrom(undefined, undefined, collection), registered(), "collection");
  c.shape(collection, COLLECTION, "collection");
  const themes: string[] = [];
  (Array.isArray(collection.themes) ? collection.themes : []).forEach((t, i) => {
    if (!isObj(t) || typeof t.id !== "string") return;
    if (themes.includes(t.id)) c.add("warning", `collection.themes[${i}].id`, `theme id "${clip(t.id)}" is already used by an earlier theme`, "give each theme its own id; reports join the first");
    themes.push(t.id);
    if (!said(t.summary)) c.add("error", `collection.themes[${i}]`, `theme "${clip(t.id)}" has no summary`, "say what its reports set out to decide and how they relate to one another");
    else fileRefs(c, t.summary, `collection.themes[${i}].summary`);
  });
  storyChecks(c, collection, "collection", { rule: false, alternatives: null, cases: null });
  readingsChecks(c, collection, "collection", collectionSectionsShown(collection), COLLECTION_SECTIONS, id => id);
  const ids: string[] = [];
  (collection.members as unknown[]).forEach((m, i) => {
    if (!isObj(m)) return;
    const at = `collection.members[${i}]`;
    if (typeof m.id === "string") {
      if (ids.includes(m.id)) c.add("error", `${at}.id`, `report id "${clip(m.id)}" is already used by an earlier report`, "give each report its own id; links and pairs name reports by id");
      ids.push(m.id);
      if (m.follows === m.id) c.add("error", `${at}.follows`, "a report cannot follow itself", "name the earlier report this one follows up, or remove the field");
    }
    const given = (k: string) => m[k] !== undefined && m[k] !== null;
    const hasTrial = given("trial"), hasComparison = given("comparison"), hasSpec = given("spec");
    const sources = [hasTrial, hasComparison, hasSpec].filter(Boolean).length;
    if (sources > 1) c.add("error", at, 'has more than one of "trial", "comparison" and "spec"', "a report draws one trial, one comparison or one specification; make them separate reports");
    else if (!sources) c.add("error", at, 'missing "trial", "comparison" or "spec"', "give the report its trial data (trial.py report), its comparison data, or a specification of its own");
    if (typeof m.date === "string" && !isCalendarDate(m.date)) c.add("warning", `${at}.date`, `"${clip(m.date)}" is not a calendar date written YYYY-MM-DD, so it is not used`, "write the day the runs began, such as 2026-10-15");
    const under = (problems: Problem[]) => { for (const p of problems) c.problems.push({ ...p, where: `${at}.${p.where}` }); };
    const narrated = m.narrative !== undefined && m.narrative !== null;
    if (hasSpec && sources === 1) {
      if (!isObj(m.spec) || typeof m.spec.title !== "string" || !Array.isArray(m.spec.sections)) c.add("error", `${at}.spec`, "is not a report specification", 'a specification is {"title": "…", "sections": [ … ]}; see catalog.md');
      else for (const p of validateSpec(m.spec)) c.problems.push({ ...p, where: p.where === "spec" ? `${at}.spec` : `${at}.spec.${p.where}` });
      if (narrated) c.add("warning", `${at}.narrative`, "a specification replaces the composition a narrative shapes, so this narrative is not used", "put the decision and labels in the specification itself, or remove the narrative");
    }
    if (hasTrial && sources === 1) {
      // Without a narrative the member's report is composed from none, and checked as such.
      if (checkTrial(c, m.trial, `${at}.trial`)) under(validateNarrative(narrated ? m.narrative : {}, m.trial));
    }
    if (hasComparison && sources === 1) {
      if (checkComparison(c, m.comparison, `${at}.comparison`)) under(validateComparison(m.comparison, narrated ? m.narrative : {}));
    }
  });
  (Array.isArray(collection.pairs) ? collection.pairs : []).forEach((p, i) => {
    if (isObj(p) && typeof p.a === "string" && p.a === p.b) c.add("error", `collection.pairs[${i}]`, "pairs a report with itself", "name two different reports");
  });
  return order(c.problems);
}

export function renderProblems(problems: Problem[]): string {
  const list = order((Array.isArray(problems) ? problems : []).map(carried).filter((p): p is Problem => p !== null));
  if (!list.length) return "";
  const errors = list.filter(p => p.level === "error").length, warnings = list.length - errors;
  const counts = [errors ? plural(errors, "error") : "", warnings ? plural(warnings, "warning") : ""].filter(Boolean).join(" and ");
  const lead = errors
    ? "Some views below may be missing, or may not show what the author meant. Each item names the place in the input and how to correct it."
    : "These do not change what any view shows, but some of what the author supplied was not used as written.";
  // Sentences start with a capital on the page; a quoted value or a one-letter name such as k keeps its case.
  const sentence = (text: string) => /^[a-z][a-z]/.test(text) ? text[0].toUpperCase() + text.slice(1) : text;
  const item = (p: Problem) => `<li class="av-problem av-problem--${p.level}"><span class="av-problem-level">${p.level === "error" ? "Error" : "Warning"}</span><div class="av-problem-body"><p class="av-problem-msg">${esc(sentence(p.message))}</p><code class="av-problem-where">${esc(p.where)}</code>${p.hint ? `<p class="av-problem-hint">${esc(sentence(p.hint))}</p>` : ""}</div></li>`;
  const SHOWN = 8;
  const more = list.length > SHOWN
    ? `<details class="av-problems-more"><summary>Show ${plural(list.length - SHOWN, "more problem")}</summary><ol class="av-problems-list" start="${SHOWN + 1}">${list.slice(SHOWN).map(item).join("")}</ol></details>`
    : "";
  return `<aside class="av-problems av-problems--${errors ? "error" : "warning"}" aria-labelledby="av-problems-title" data-av-problems="${list.length}">
<div class="av-problems-head"><span class="av-problems-icon" aria-hidden="true">!</span><div class="av-problems-text"><p class="av-eyebrow">Input check</p><h2 class="av-problems-title" id="av-problems-title">This report's input has ${esc(counts)}</h2><p class="av-problems-lead">${esc(lead)}</p></div></div>
<details class="av-problems-details"${errors ? " open" : ""}><summary><span class="av-problems-show">Show the list</span><span class="av-problems-hide">Hide the list</span></summary><ol class="av-problems-list">${list.slice(0, SHOWN).map(item).join("")}</ol>${more}</details>
</aside>`;
}
