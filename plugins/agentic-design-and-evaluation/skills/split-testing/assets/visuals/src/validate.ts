/** Checks a report specification or a narrative against what the library
 * understands, so a misspelled block type, field, arm or case is named instead
 * of being silently ignored or drawn as a fact about the trial. An error is
 * input that would break a view or make it misread; a warning is input the
 * report does not use as written. report.py --check applies the same rules
 * without a browser; tests/test_validate.py keeps the two in agreement. */
import { esc } from "./core";
import type { ReportSpec } from "./model";
import { blockTypes } from "./report";

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
interface BlockSchema extends Shape { trial?: "always" | "without-rows" | "without-settings"; comparison?: "without-data" }

const FRAME: Record<string, Field> = { title: "text", description: "prose", note: "text", id: "text" };
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
const BLOCKS: Record<string, BlockSchema> = {
  verdict: { fields: { ...FRAME, ...VERDICT, rule: "prose" }, required: ["headline"] },
  figures: { fields: { ...FRAME, items: { list: { fields: { value: { oneOf: ["text", "null"] }, label: "text", note: "text", tone: { enum: ["neutral", "pass", "fail", "warn", "invalid"], warn: true } }, required: ["label"] } } }, required: ["items"] },
  ladder: {
    trial: "without-rows",
    fields: {
      ...FRAME, rows: { list: { fields: { arm: "arm-ref", case: "case-ref", k: "count", n: "count", invalid: "count", note: "text" }, required: ["k", "n"], kn: [["k", "n"]] } },
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
  cases: { trial: "always", fields: { ...FRAME, cases: { list: "case" }, arms: { list: "arm" }, groups: { list: GROUP }, pairs: { oneOf: [AUTO_OFF, PAIR_SPECS] }, index: "boolean" } },
  failures: { trial: "always", fields: { ...FRAME, cases: { list: "case" }, arms: { list: "arm" }, by: { enum: ["cause", "case"], warn: true }, reasons: "count" } },
  contrast: {
    trial: "without-rows",
    fields: {
      ...FRAME,
      rows: { list: { fields: { label: "text", arm: "arm-ref", vs: "arm-ref", note: "text", k1: "count", n1: "count", k2: "count", n2: "count", invalid1: "count", invalid2: "count", identical: "boolean" }, required: ["k1", "n1", "k2", "n2"], kn: [["k1", "n1"], ["k2", "n2"]] } },
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
      ...FRAME, rows: { list: { fields: { label: "text", arm: "arm-ref", k: "count", n: "count", value: NUMBER_OR_NULL, lo: NUMBER_OR_NULL, hi: NUMBER_OR_NULL, note: "text" }, kn: [["k", "n"]] } },
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
      series: { list: { fields: { label: "text", arm: "arm-ref", points: { list: { fields: { stage: "text", k: "count", n: "count", value: NUMBER_OR_NULL, lo: NUMBER_OR_NULL, hi: NUMBER_OR_NULL }, required: ["stage"], kn: [["k", "n"]] } } }, required: ["label", "points"] } },
      percent: "boolean", unit: "text",
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
};

const SECTION: Record<string, Field> = { id: "section-id", title: "text", label: "text", lead: "prose", blocks: { list: "block" } };
const SPEC: Shape = {
  fields: {
    title: "string", kicker: "text", summary: "prose",
    meta: { list: { fields: { label: "text", value: "text" }, required: ["label", "value"] } },
    arms: { list: { fields: { id: "arm-ref", label: "text", note: "text" }, required: ["id"] } },
    sections: { list: { fields: SECTION, required: ["title", "blocks"] } },
    footer: "text", trial: "any", cases: { record: "text", keys: "case-ref" }, problems: "any", comparison: "any",
  },
  required: ["title", "sections"],
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
    footer: "text",
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
    footer: "text",
  },
};
const NUMERIC_TEXT = /^\s*-?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?\s*$/;

// ------------------------------------------------------------------ helpers

type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => v !== null && typeof v === "object" && !Array.isArray(v);
const isNumber = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);
const isText = (v: unknown) => typeof v === "string" || isNumber(v);
const keysOf = (v: Obj) => Object.keys(v).filter(k => !k.startsWith("$")).sort((a, b) => (a < b ? -1 : a > b ? 1 : 0));

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

interface Known { trial: boolean; arms: string[]; cases: string[]; checks: string[]; pairs: string[]; settings: Record<string, Obj>; comparison: boolean; alternatives: string[]; metrics: string[]; ccases: string[] }
const isComparison = (v: unknown): v is Obj => isObj(v) && Array.isArray(v.alternatives);
function knownFrom(trial: unknown, comparison?: unknown): Known {
  // settings has no prototype, so an arm named like an Object member is an ordinary key.
  const known: Known = { trial: false, arms: [], cases: [], checks: [], pairs: [], settings: Object.create(null), comparison: false, alternatives: [], metrics: [], ccases: [] };
  if (isComparison(comparison)) {
    known.comparison = true;
    const ids = (list: unknown, into: string[]) => { if (Array.isArray(list)) for (const x of list) if (isObj(x) && typeof x.id === "string" && !into.includes(x.id)) into.push(x.id); };
    ids(comparison.alternatives, known.alternatives); ids(comparison.metrics, known.metrics); ids(comparison.cases, known.ccases);
  }
  if (!isObj(trial) || !Array.isArray(trial.runs)) return known;
  known.trial = true;
  const add = (list: string[], v: unknown) => { if (typeof v === "string" && !list.includes(v)) list.push(v); };
  const plan = isObj(trial.plan) ? trial.plan : {};
  if (isObj(plan.arms)) for (const [a, entry] of Object.entries(plan.arms)) { add(known.arms, a); if (isObj(entry)) known.settings[a] = entry; }
  if (Array.isArray(plan.scenarios)) for (const s of plan.scenarios) if (isObj(s)) add(known.cases, s.name);
  for (const r of trial.runs) {
    if (!isObj(r)) continue;
    add(known.arms, r.arm);
    add(known.cases, r.scenario);
    if ((r.passed === true || r.passed === false) && isObj(r.checks)) for (const [k, v] of Object.entries(r.checks)) if (typeof v === "boolean") add(known.checks, k);
  }
  if (isObj(trial.pairwise)) for (const k of Object.keys(trial.pairwise)) add(known.pairs, k);
  return known;
}

const IDS: Record<string, { list: "arms" | "cases" | "checks" | "pairs" | "alternatives" | "metrics" | "ccases" | null; noun: string; plural: string; level: Problem["level"]; tail: string }> = {
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
};
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
    const ofComparison = spec.list !== null && FROM_COMPARISON.includes(spec.list);
    if (spec.list && !(ofComparison ? this.known.comparison && (spec.list !== "ccases" || this.known.ccases.length > 0) : this.known.trial)) return;
    const options = spec.list ? this.known[spec.list] : MEASURES;
    if (options.includes(value)) return;
    const s = suggest(value, options);
    this.add(spec.level, where, `"${clip(value)}" is not ${spec.noun}${spec.tail}`,
      s ? `did you mean "${s}"?` : options.length ? `${spec.plural}: ${listOf(options)}` : `this ${ofComparison ? "comparison" : "trial"} has no ${spec.plural.replace(/ in this (trial|comparison)$/, "")}`);
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
    if (schema.comparison && !this.known.comparison && (v.data === undefined || v.data === null))
      this.add("error", at, `the ${type} block needs comparison data or its own "data"`, 'pass --data or --csv to report.py, or set the specification\'s "comparison" field');
    this.shape(v, schema, at, { data: (value, where) => { if (!isComparison(value)) this.add("error", where, "is not comparison data", 'a comparison is {"alternatives": [ … ], "metrics": [ … ]}; see catalog.md'); } }, ["type"]);
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

// ------------------------------------------------------------------ public

/** Problems in a report specification. A specification the trial composition
 * built carries its narrative's problems in `problems`; those are returned as
 * they are, since the composition's own sections need no second check. */
export function validateSpec(spec: ReportSpec | unknown, options: { trial?: unknown; comparison?: unknown } = {}): Problem[] {
  if (!isObj(spec)) return [{ level: "error", where: "spec", message: `expected an object with "title" and "sections", found ${found(spec)}`, hint: 'a specification is {"title": "…", "sections": [ … ]}' }];
  const own = (spec as Obj).problems;
  if (Array.isArray(own)) return order(own.map(carried).filter((p): p is Problem => p !== null));
  // As in the browser: a specification without trial data of its own borrows the trial supplied beside it.
  const trial = (spec as Obj).trial ? (spec as Obj).trial : options.trial;
  const comparison = (spec as Obj).comparison ? (spec as Obj).comparison : options.comparison;
  const c = new Checker(knownFrom(trial, comparison), registered(), "spec");
  c.shape(spec, SPEC, "", {
    trial: (value, where) => { if (!isObj(value) || !Array.isArray(value.runs)) c.add("error", where, "is not trial report data", "write it with trial.py report RUN_DIR --out FILE"); },
    comparison: (value, where) => {
      if (!isComparison(value)) c.add("error", where, "is not comparison data", 'a comparison is {"alternatives": [ … ], "metrics": [ … ]}; see catalog.md');
      else c.problems.push(...validateComparison(value));
    },
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
  return order(c.problems);
}

/** Problems in a narrative for the trial composition, checked against the
 * trial's arms and cases when the trial data is given. */
export function validateNarrative(narrative: unknown, trial?: unknown): Problem[] {
  const c = new Checker(knownFrom(trial), registered(), "narrative");
  if (!isObj(narrative)) return [{ level: "error", where: "narrative", message: `expected an object, found ${found(narrative)}`, hint: 'a narrative is an object such as {"title": "…", "decision": { … }}' }];
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
  if (narrative !== undefined) c.problems.push(...comparisonNarrative(narrative, c.known));
  return order(c.problems);
}

/** Problems in a narrative for the comparison composition. */
function comparisonNarrative(narrative: unknown, known: Known): Problem[] {
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
  return c.problems;
}

/** A compact panel at the top of a report listing the problems in its input;
 * empty when there are none. Errors open the list; warnings alone leave it
 * folded under a one-line summary that stays visible. */
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
