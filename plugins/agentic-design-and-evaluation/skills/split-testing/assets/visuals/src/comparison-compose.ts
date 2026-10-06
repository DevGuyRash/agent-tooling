/** Compose a report specification from any comparison, and turn trial data into one.
 *
 * The composition follows the reader who asked the question: the verdict and
 * the rule fixed before results, what was compared, every metric (the primary
 * one first), differences from the baseline, the groups, case by case, the
 * head-to-head judgments, the author's decision matrix, every observation and
 * the sources. A section appears only when the comparison holds data for it, so
 * a two-alternative taste test and a study of research directions with many
 * concepts each get the same reader-first page at their own size. A narrative
 * can include, exclude, reorder (after) and append, as with the trial report. */
import { fmtInt } from "./core";
import type { Alternative, Case, Comparison, Metric, Observation, Preference } from "./comparison-model";
import { alternativeIds, groupPath, invalidJudgments, judgmentMetric, observationStatus, winMatrix } from "./comparison-stats";
import type { ReportSpec, SectionSpec, BlockSpec, ArmSpec } from "./model";
import { costMeasures, displayPath, trialAxes } from "./trial-model";
import type { TrialReport } from "./trial-model";
import { validateComparison } from "./validate";
import type { Problem } from "./validate";

/** One row of a decision matrix: a metric that measures it, the author's own scores per alternative, or cells that rate it. */
export interface Criterion {
  /** Derived from the metric or the label when omitted. */
  id?: string; label?: string;
  /** Alternatives with no cell show this metric's measured value. */
  metric?: string;
  /** Ratings keyed by alternative id: a level or number as text, yes/no as a boolean, null for none. */
  scores?: Record<string, number | string | boolean | null>;
  /** A weighted total appears only when the author gives weights; it sums the weighted criteria and names any left out. */
  weight?: number;
  better?: "higher" | "lower" | "none";
  description?: string; note?: string;
}

export interface ComparisonNarrative {
  title?: string; question?: string; summary?: string | string[]; kicker?: string;
  decision?: { verdict?: "adopt" | "reject" | "inconclusive" | "mixed" | "none"; label?: string; headline: string; detail?: string | string[]; checks?: Array<{ label: string; observed: string; threshold?: string; met?: boolean | null; group?: string }>; conditions?: string[]; limits?: string[]; changes?: string[] };
  /** Labels and identity order for alternatives. */
  alternatives?: ArmSpec[] | Record<string, { label?: string; note?: string }>;
  /** The reference alternative, and groups of copies, when the data does not name them. */
  baseline?: string;
  identical?: string[][];
  /** The decision matrix: criteria, optional cells ({criterion, alternative, rating, text, evidence}) and a rating scale ({min, max, levels, labels, note}). */
  criteria?: Criterion[];
  cells?: Array<{ criterion: string; alternative: string; rating?: number | string | null; text?: string; evidence?: string | string[] }>;
  scale?: { min?: number; max?: number; levels?: string[]; labels?: Record<string, string>; note?: string };
  include?: string[]; exclude?: string[];
  sections?: Array<SectionSpec & { after?: string }>;
  append?: Record<string, BlockSpec[]>;
  footer?: string;
}

/** The default sections' ids, in reading order; each appears only when the comparison holds its data. */
export const COMPARISON_SECTION_IDS = ["verdict", "compared", "results", "differences", "groups", "cases", "judgments", "decision", "observations", "sources"] as const;
/** Other names readers reach for, mapped to a default section. */
export const COMPARISON_SECTION_ALIASES: Record<string, string> = { setup: "compared", alternatives: "compared", metrics: "results", hierarchy: "groups", preferences: "judgments", pairwise: "judgments", matrix: "decision", ledger: "observations", runs: "observations" };
const alias = (id: unknown) => { const k = String(id); return Object.prototype.hasOwnProperty.call(COMPARISON_SECTION_ALIASES, k) ? COMPARISON_SECTION_ALIASES[k] : k; };

const isObject = (v: unknown): v is Record<string, unknown> => !!v && typeof v === "object" && !Array.isArray(v);
const strings = (v: unknown): string[] => Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : [];
const objects = <T>(v: unknown): T[] => Array.isArray(v) ? v.filter(isObject) as unknown as T[] : [];
const KINDS = ["binary", "numeric", "ordinal", "count", "rank", "preference"];
const plural = (n: number, one: string, many = `${one}s`) => `${fmtInt(n)} ${n === 1 ? one : many}`;
const listed = (names: string[]) => names.length <= 1 ? names.join("") : `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;

export function comparisonReport(dataIn: Comparison, narrativeIn: ComparisonNarrative = {}): ReportSpec {
  if (!isObject(dataIn) || !Array.isArray(dataIn.alternatives)) throw new TypeError("comparisonReport needs a comparison: an object with an alternatives list and a metrics list (see catalog.md).");
  const narrative: ComparisonNarrative = isObject(narrativeIn) ? narrativeIn : {};
  let problems: Problem[] = [];
  try { problems = (validateComparison(dataIn, narrative) || []).filter(p => isObject(p)); }
  catch (error) { problems = [{ level: "warning", where: "comparison", message: `The comparison could not be checked: ${error instanceof Error ? error.message : String(error)}` }]; }

  // Narrative labels win over the data's; narrative order leads, but only for alternatives that exist.
  const ids = alternativeIds(dataIn);
  const rawLabels: unknown[] = Array.isArray(narrative.alternatives) ? narrative.alternatives : isObject(narrative.alternatives) ? Object.entries(narrative.alternatives).map(([id, v]) => Object.assign({ id }, isObject(v) ? v : {}, { id })) : [];
  const labels = rawLabels.filter((a): a is ArmSpec => isObject(a) && typeof a.id === "string");
  const order = [...new Set([...labels.map(a => a.id).filter(id => ids.includes(id)), ...ids])];
  const given = (id: string) => labels.find(a => a.id === id);
  const alternatives = objects<Alternative>(dataIn.alternatives).filter(a => typeof a.id === "string").map(a => {
    const g = given(a.id);
    return g ? { ...a, ...(typeof g.label === "string" && g.label ? { label: g.label } : {}), ...(typeof g.note === "string" && g.note ? { note: g.note } : {}) } : a;
  });
  const label = (id: string) => alternatives.find(a => a.id === id)?.label || id;
  const metrics = objects<Metric>(dataIn.metrics).filter(m => typeof m.id === "string" && KINDS.includes(m.kind));
  const ordered = [...metrics.filter(m => m.primary === true), ...metrics.filter(m => m.primary !== true)];
  const primary = metrics.find(m => m.primary === true);
  const baseline = [narrative.baseline, dataIn.baseline].find((b): b is string => typeof b === "string" && ids.includes(b));
  const identical = (Array.isArray(narrative.identical) ? narrative.identical : Array.isArray(dataIn.identical) ? dataIn.identical : [])
    .map(g => [...new Set(strings(g).filter(a => ids.includes(a)))]).filter(g => g.length > 1);
  const data: Comparison = { ...dataIn, alternatives, metrics, ...(baseline ? { baseline } : {}), identical };

  const observations = objects<Observation>(dataIn.observations);
  const preferences = objects<Preference>(dataIn.preferences);
  const rankings = objects<{ order: unknown }>(dataIn.rankings).filter(r => Array.isArray(r.order));
  const caseIds = [...new Set([...objects<Case>(dataIn.cases).map(c => c.id), ...[...observations, ...objects<{ case?: unknown }>(dataIn.aggregates), ...preferences, ...objects<{ case?: unknown }>(dataIn.rankings)].map(x => (x as { case?: unknown }).case)].filter((c): c is string => typeof c === "string"))];
  const grouped = alternatives.filter(a => groupPath(a.group).length > 0);
  const topGroups = new Set(grouped.map(a => groupPath(a.group)[0]));
  // Validity comes from the same reading the summaries use, so the verdict and the views agree.
  const status = observationStatus(data);
  const recorded = status.length, invalid = status.filter(x => x !== null).length, valid = recorded - invalid;
  const judgments = preferences.length + rankings.length;
  const unreached = invalidJudgments(data) + metrics.filter(m => m.kind === "preference").reduce((a, m) => a + invalidJudgments(data, m.id), 0);
  const rule = typeof dataIn.decision_rule === "string" && dataIn.decision_rule.trim() ? dataIn.decision_rule : undefined;
  const alert = recorded && !valid
    ? { text: `All ${plural(recorded, "observation")} are invalid, so no value can be given. Invalid observations are not failures.`, href: "#observations", link: "What was recorded" }
    : invalid && invalid / recorded >= 0.2
      ? { text: `${fmtInt(invalid)} of ${plural(recorded, "observation")} produced no valid value. They are counted apart from every summary and never treated as failures.`, href: "#observations", link: "Every observation" }
      : undefined;

  const appended = new Map<string, BlockSpec[]>();
  for (const [k, blocks] of Object.entries(isObject(narrative.append) ? narrative.append : {})) if (Array.isArray(blocks)) appended.set(alias(k), [...(appended.get(alias(k)) || []), ...blocks]);
  const sections: Array<{ key: string; section: SectionSpec }> = [];
  const add = (key: string, s: SectionSpec) => sections.push({ key, section: { ...s, id: key, blocks: [...s.blocks, ...(appended.get(key) || [])] } });

  // ---------------------------------------------------------------- verdict
  const decision = isObject(narrative.decision) ? narrative.decision : null;
  add("verdict", {
    title: "Verdict", label: "Verdict",
    blocks: [
      decision ? { type: "verdict", ...decision, rule, ...(alert ? { alert } : {}) } : {
        type: "verdict", verdict: "none",
        headline: recorded && !valid ? "Nothing valid was recorded, and no decision was written." : "No decision was recorded with these results.",
        detail: rule ? "The rule below was fixed before the results; the sections below hold the evidence it reads." : "No decision rule was given; the sections below show what was observed.",
        rule, ...(alert ? { alert } : {}),
      },
      {
        type: "figures", items: [
          { value: order.length, label: order.length === 1 ? "Alternative" : "Alternatives", note: topGroups.size ? plural(topGroups.size, "group") : undefined },
          { value: metrics.length, label: metrics.length === 1 ? "Metric" : "Metrics", note: primary ? `primary: ${primary.label || primary.id}` : undefined },
          ...(caseIds.length ? [{ value: caseIds.length, label: caseIds.length === 1 ? "Case" : "Cases" }] : []),
          ...(recorded ? [{ value: valid, label: "Valid observations", tone: valid ? "pass" : "warn" }, { value: invalid, label: "Invalid", note: invalid ? "counted apart, not failures" : "none", tone: invalid ? "warn" : "neutral" }] : []),
          ...(judgments ? [{ value: judgments, label: judgments === 1 ? "Judgment" : "Judgments", note: unreached ? `${fmtInt(unreached)} unreached` : rankings.length ? `${plural(rankings.length, "ranking")}` : undefined }] : []),
        ],
      },
    ],
  });

  // ---------------------------------------------------------------- what was compared
  if (order.length)
    add("compared", {
      title: "What was compared", label: "Compared",
      blocks: [{ type: "alternatives", alternatives: order, ...(baseline ? { baseline } : {}) }],
    });

  // ---------------------------------------------------------------- results
  if (ordered.length)
    add("results", {
      title: "Results", label: "Results",
      lead: `${ordered.length > 1 ? `Every metric, ${primary ? "the primary one first" : "in the order given"}. ` : ""}Intervals are 95%; invalid observations are counted beside each value and never as failures. A value marked as reported comes from a supplied summary rather than individual observations.`,
      blocks: [
        ...(ordered.length > 1 ? [{ type: "scorecard", metrics: ordered.map(m => m.id), ...(baseline ? { baseline } : {}) }] : []),
        ...ordered.map(m => ({ type: "metric", metric: m.id, ...(baseline ? { baseline } : {}) })),
      ],
    });

  // ---------------------------------------------------------------- differences
  if (ordered.length && order.length > 1 && (baseline || identical.length || order.length === 2)) {
    const pair = !baseline && !identical.length ? [order[0], order[1]] : null;
    add("differences", {
      title: baseline ? `Difference from ${label(baseline)}` : identical.length ? "Difference between identical alternatives" : `${label(order[0])} against ${label(order[1])}`,
      label: "Differences",
      lead: `${baseline ? `Each alternative minus ${label(baseline)}` : pair ? `${label(pair[0])} minus ${label(pair[1])}` : "Each copy against the others"}, metric by metric. Rates use Newcombe's interval, means Welch's (with a bootstrap interval for medians), ordinal levels the probability of superiority, ranks the difference in mean rank, and preferences the net head-to-head share.${identical.length ? " Identical alternatives received the same material: the distance between them is what chance alone produces." : ""}`,
      blocks: [{ type: "difference", metrics: ordered.map(m => m.id), ...(baseline ? { baseline } : {}), ...(identical.length ? { identical } : {}), ...(pair ? { pairs: [pair] } : {}) }],
    });
  }

  // ---------------------------------------------------------------- groups
  if (grouped.length)
    add("groups", {
      title: "Groups", label: "Groups",
      lead: `Alternatives inside their groups, pooled at every level, so ${topGroups.size > 1 ? "the groups can be compared with each other and the alternatives within each" : "each level can be read against the one above it"}.${grouped.length < alternatives.length ? ` ${plural(alternatives.length - grouped.length, "alternative")} belong${alternatives.length - grouped.length === 1 ? "s" : ""} to no group and appear${alternatives.length - grouped.length === 1 ? "s" : ""} only ungrouped.` : ""}`,
      blocks: [{ type: "hierarchy", ...(primary || ordered[0] ? { metric: (primary || ordered[0]).id } : {}) }],
    });

  // ---------------------------------------------------------------- cases
  if (caseIds.length > 1 && ordered.length)
    add("cases", {
      title: "Case by case", label: "Cases",
      lead: "Each metric in each case. A difference that lives in one case reads differently from one spread across all of them.",
      blocks: ordered.map(m => ({ type: "metric", metric: m.id, by: "case" })),
    });

  // ---------------------------------------------------------------- judgments
  if (judgments) {
    const has = (metric?: string) => { const w = winMatrix(data, metric); return w.wins.some(r => r.some(x => x > 0)) || w.ties.some(r => r.some(x => x > 0)) || invalidJudgments(data, metric) > 0; };
    const judged = metrics.filter(m => m.kind === "preference" && has(m.id));
    const overall = has(undefined) && !judgmentMetric(data, "preference");
    add("judgments", {
      title: "Head-to-head judgments", label: "Judgments",
      lead: "Each judgment between two alternatives, and every pair of places inside each ranking. Win rates count wins over decisive judgments; ties are shown beside them, and unreached judgments are counted apart.",
      blocks: [
        ...judged.map(m => ({ type: "preferences", metric: m.id, ...(judged.length > 1 || overall ? { title: m.label || m.id } : {}) })),
        ...(overall || !judged.length ? [{ type: "preferences", ...(judged.length ? { title: "Overall preference" } : {}) }] : []),
      ],
    });
  }

  // ---------------------------------------------------------------- decision matrix
  // Each criterion needs an id the matrix can key cells by: its own, else its metric's, else one from its label.
  const used = new Set<string>();
  const criteria = objects<Criterion>(narrative.criteria).map((c, i) => {
    const base = [c.id, c.metric, typeof c.label === "string" ? c.label.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "") : ""].find((x): x is string => typeof x === "string" && !!x) || `criterion-${i + 1}`;
    let id = base, n = 1;
    while (used.has(id)) id = `${base}-${++n}`;
    used.add(id);
    return { ...c, id };
  });
  if (criteria.length)
    add("decision", {
      title: "Decision matrix", label: "Decision",
      lead: "How each alternative meets the criteria the author set. A weighted total appears only when the author gave weights; it sums the weighted criteria, names any criterion left out, and shows its computation.",
      blocks: [{ type: "decision-matrix", criteria, ...(Array.isArray(narrative.cells) ? { cells: narrative.cells } : {}), ...(isObject(narrative.scale) ? { scale: narrative.scale } : {}), alternatives: order }],
    });

  // ---------------------------------------------------------------- observations and sources
  const aggregates = objects(dataIn.aggregates);
  if (observations.length || aggregates.length)
    add("observations", { title: observations.length ? "Every observation" : "Every supplied total", label: observations.length ? "Observations" : "Totals", lead: observations.length ? `Every recorded observation${aggregates.length ? " and supplied total" : ""}, filterable. An invalid one says why it has no value.` : "The totals the comparison was given, as supplied; every value above is computed from these.", blocks: [{ type: "observations" }] });
  const sources = objects<{ label: unknown; href?: unknown; note?: unknown }>(dataIn.sources).filter(s => typeof s.label === "string" && s.label);
  if (sources.length)
    add("sources", {
      title: "Sources", label: "Sources",
      blocks: [{ type: "list", items: sources.map(s => ({ text: typeof s.href === "string" && s.href ? `${s.label} — ${s.href}` : String(s.label), ...(typeof s.note === "string" && s.note ? { detail: s.note } : {}) })) }],
    });

  const include = Array.isArray(narrative.include) ? narrative.include.map(alias) : null;
  const exclude = (Array.isArray(narrative.exclude) ? narrative.exclude : []).map(alias);
  const kept: Array<{ key: string; section: unknown }> = sections.filter(s => (!include || include.includes(s.key)) && !exclude.includes(s.key));
  for (const extra of Array.isArray(narrative.sections) ? narrative.sections : []) {
    if (!isObject(extra)) { kept.push({ key: "", section: extra }); continue; }
    const { after, ...section } = extra as SectionSpec & { after?: string };
    const at = after !== undefined ? kept.findIndex(s => s.key && s.key === alias(after)) : -1;
    const entry = { key: String(section.id || section.title || ""), section };
    if (at >= 0) kept.splice(at + 1, 0, entry); else kept.push(entry);
  }
  if (alert && !kept.some(s => s.key === "observations")) delete (alert as { href?: string }).href;

  const altText = order.length === 1 ? `One alternative (${label(order[0])})` : order.length <= 4 ? `${order.length} alternatives (${listed(order.map(label))})` : plural(order.length, "alternative");
  const groupText = topGroups.size ? ` in ${plural(topGroups.size, "group")}` : "";
  const metricText = metrics.length ? ` on ${metrics.length <= 3 ? listed(metrics.map(m => m.label || m.id)) : plural(metrics.length, "metric")}` : "";
  const shape = order.length ? `${altText}${groupText}${metricText}${caseIds.length > 1 ? ` across ${plural(caseIds.length, "case")}` : ""}${recorded ? `: ${plural(recorded, "observation")}${invalid ? ` (${fmtInt(invalid)} invalid)` : ""}` : ""}${judgments ? `${recorded ? " and" : ":"} ${plural(judgments, "judgment")}` : ""}.` : undefined;
  const question = [narrative.question, dataIn.question].find((q): q is string => typeof q === "string" && !!q.trim());
  const title = [narrative.title, narrative.question, dataIn.title, dataIn.question].find((t): t is string => typeof t === "string" && !!t.trim()) || "Comparison";
  return {
    title,
    kicker: typeof narrative.kicker === "string" && narrative.kicker ? narrative.kicker : "Comparison",
    summary: narrative.summary ?? dataIn.summary ?? shape,
    meta: [
      ...(question && question !== title ? [{ label: "Question", value: question }] : []),
      ...(baseline ? [{ label: "Baseline", value: label(baseline) }] : []),
    ],
    arms: order.map(id => ({ id, label: label(id), ...(alternatives.find(a => a.id === id)?.note ? { note: alternatives.find(a => a.id === id)!.note } : {}) })),
    comparison: data,
    footer: narrative.footer || "A self-contained report: every view is drawn from the comparison embedded in this file.",
    problems,
    sections: kept.map(s => s.section as SectionSpec),
  };
}

// ------------------------------------------------------------------ trial data as a comparison

const MATERIAL = new Set(["instructions_text", "instructions_truncated", "artifact_text", "artifact_truncated"]);
const scalar = (v: unknown): string | number | boolean | null => v === null || typeof v === "string" || typeof v === "boolean" || (typeof v === "number" && Number.isFinite(v)) ? v as string | number | boolean | null : JSON.stringify(v) ?? null;

/** Trial report data (trial.py report) as a comparison: arms become alternatives
 * with their recorded settings and instructions, scenarios become cases, each run
 * observes a binary "passed" metric (an invalid run stays invalid, never a
 * failure), usage and timing become numeric metrics, boolean and numeric check
 * values become metrics, the judge's verdict a binary one, and pairwise
 * summaries become head-to-head judgments. */
export function fromTrial(trial: TrialReport): Comparison {
  if (!isObject(trial) || !Array.isArray(trial.runs)) throw new TypeError("fromTrial needs the JSON that `trial.py report RUN_DIR` writes.");
  const axes = trialAxes(trial);
  const plan = isObject(trial.plan) ? trial.plan : {};
  const planned = isObject(plan.arms) ? plan.arms : {};
  const runs = trial.runs.filter(isObject).filter(r => typeof r.arm === "string" && typeof r.scenario === "string");
  const valid = runs.filter(r => r.passed === true || r.passed === false);
  const alternatives: Alternative[] = axes.arms.map(id => {
    const entry = isObject(planned[id]) ? planned[id] as Record<string, unknown> : {};
    const attributes = Object.fromEntries(Object.entries(entry).filter(([k]) => !MATERIAL.has(k)).map(([k, v]) => [k, scalar(v)]));
    const text = typeof entry.instructions_text === "string" ? entry.instructions_text : undefined;
    return { id, ...(Object.keys(attributes).length ? { attributes } : {}), ...(text ? { content: text } : {}), ...(entry.instructions_truncated === true ? { note: "instructions shortened to the report's text bound" } : {}) };
  });
  const scenarios = objects<{ name?: unknown; description?: unknown; prompt?: unknown }>(plan.scenarios);
  const cases: Case[] = axes.cases.map(id => {
    const s = scenarios.find(x => x.name === id);
    const text = typeof s?.description === "string" && s.description ? s.description : typeof s?.prompt === "string" && s.prompt ? (s.prompt.length > 400 ? `${s.prompt.slice(0, 399)}…` : s.prompt) : undefined;
    return { id, ...(text ? { description: text } : {}) };
  });
  const required = new Map<string, string[]>();
  for (const s of objects<{ name?: unknown; required?: unknown }>(plan.scenarios)) for (const c of strings(s.required)) required.set(c, [...(required.get(c) || []), String(s.name)]);

  const metrics: Metric[] = [{ id: "passed", label: "Passed", kind: "binary", better: "higher", primary: true, description: "A run passes when every required check holds and the judge, when there is one, says pass. Invalid runs have no result and are counted apart." }];
  const observations: Observation[] = [];
  const at = (r: typeof runs[number]) => ({ alternative: r.arm, case: r.scenario, ...(typeof r.repeat === "number" ? { unit: r.repeat } : {}), ...(typeof r.job === "string" ? { id: r.job, source: r.job } : {}) });
  for (const r of runs) {
    const ok = r.passed === true || r.passed === false;
    observations.push({
      ...at(r), metric: "passed", value: ok ? r.passed : null,
      ...(ok ? {} : { valid: false, invalid_reason: String(r.invalid_reason || r.status || "invalid") }),
      ...(typeof r.judge?.reason === "string" && r.judge.reason ? { note: r.judge.reason } : {}),
      ...(typeof r.final_message_excerpt === "string" && r.final_message_excerpt ? { excerpt: r.final_message_excerpt } : {}),
    });
  }
  // Usage and timing over valid runs, as the trial's cost view reads them.
  const units: Record<string, string> = { tokens: "tokens", seconds: "seconds", usd: "USD", count: "" };
  for (const m of costMeasures(trial)) {
    metrics.push({ id: m.id, label: m.label, kind: "numeric", better: "lower", ...(units[m.unit] ? { unit: units[m.unit] } : {}), ...(m.note ? { description: m.note } : {}) });
    for (const r of valid) { const v = m.get(r); if (typeof v === "number" && Number.isFinite(v)) observations.push({ ...at(r), metric: m.id, value: v }); }
  }
  // Check values: all-boolean checks are binary, all-numeric ones numeric; other values stay in the trial views.
  const checkTypes = new Map<string, Set<string>>();
  for (const r of valid) for (const [k, v] of Object.entries(isObject(r.checks) ? r.checks : {})) (checkTypes.get(k) || checkTypes.set(k, new Set()).get(k)!).add(typeof v === "boolean" ? "boolean" : typeof v === "number" && Number.isFinite(v) ? "number" : "other");
  for (const [name, types] of [...checkTypes].sort((a, b) => a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0)) {
    if (types.size !== 1 || types.has("other")) continue;
    const boolean = types.has("boolean"), id = `check:${name}`, req = required.get(name);
    metrics.push({ id, label: name, kind: boolean ? "binary" : "numeric", better: boolean && req ? "higher" : "none", description: req ? `A required check in ${listed(req)}; elsewhere a recorded measure.` : "A recorded check value; no case requires it." });
    for (const r of valid) { const v = isObject(r.checks) ? r.checks[name] : undefined; if (typeof v === (boolean ? "boolean" : "number")) observations.push({ ...at(r), metric: id, value: v as boolean | number }); }
  }
  if (runs.some(r => r.judge?.verdict === "pass" || r.judge?.verdict === "fail")) {
    metrics.push({ id: "judge", label: "Judge says pass", kind: "binary", better: "higher" });
    for (const r of runs) if (r.judge?.verdict === "pass" || r.judge?.verdict === "fail") observations.push({ ...at(r), metric: "judge", value: r.judge.verdict === "pass" });
  }
  // Pairwise summaries: one judgment per counted pair, with inconsistent and invalid pairs as unreached judgments.
  const preferences: Preference[] = [];
  const pairs = Object.entries(isObject(trial.pairwise) ? trial.pairwise : {}).filter(([, s]) => isObject(s) && Array.isArray(s.arms) && s.arms.length === 2);
  for (const [key, summary] of pairs) {
    const [a, b] = summary.arms.map(String), id = pairs.length === 1 ? "pairwise" : `pairwise:${key}`;
    const judge = isObject(summary.judge) && typeof summary.judge.model === "string" ? summary.judge.model : undefined;
    metrics.push({ id, label: pairs.length === 1 ? "Pairwise preference" : `Pairwise: ${a} vs ${b}`, kind: "preference", better: "higher", description: "A judge saw matched runs side by side in both orders; only pairs decided the same way in both orders count as decided." });
    const scenarios = isObject(summary.scenarios) && Object.keys(summary.scenarios).length ? Object.entries(summary.scenarios) : [[undefined, summary.overall] as const];
    for (const [scenario, st] of scenarios) {
      if (!isObject(st)) continue;
      const n = (v: unknown) => typeof v === "number" && Number.isInteger(v) && v > 0 ? v : 0;
      const push = (count: number, winner: string | null, note?: string) => { for (let i = 0; i < count; i++) preferences.push({ a, b, winner, metric: id, ...(scenario ? { case: scenario } : {}), ...(judge ? { judge } : {}), ...(note ? { note } : {}) }); };
      push(n(st.a_wins), a); push(n(st.b_wins), b); push(n(st.tie), "tie");
      push(n(st.inconsistent), null, "decided differently in the two orders"); push(n(st.invalid), null, "no valid judgment");
    }
  }
  const name = typeof trial.name === "string" && trial.name ? trial.name : undefined;
  return {
    ...(name ? { title: name } : {}),
    alternatives, cases, metrics, observations, ...(preferences.length ? { preferences } : {}),
    ...(typeof trial.baseline === "string" && axes.arms.includes(trial.baseline) ? { baseline: trial.baseline } : {}),
    ...(typeof plan.decision_rule === "string" && plan.decision_rule.trim() ? { decision_rule: plan.decision_rule } : {}),
    ...(typeof trial.run_directory === "string" && trial.run_directory ? { sources: [{ label: "trial.py report", note: `run directory ${displayPath(trial.run_directory)}` }] } : {}),
  };
}
