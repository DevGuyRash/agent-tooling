/** A collection: many reports (trials and comparisons, each with its narrative)
 * in one page with one copy of the library. This module reads a collection
 * into per-report summaries the collection views share, and composes the
 * collection page, each member's full report and the side-by-side view of two
 * members as ordinary specifications. Like the rest of the library it computes
 * only counts, pass rates with Wilson intervals and differences between rates
 * with Newcombe intervals; every decision shown is the one its narrative wrote. */
import { fmtNum, fmtPct, isNum, median } from "./core";
import { newcombe } from "./stats";
import { ArmRegistry } from "./model";
import type { ArmSpec, BlockSpec, ReportSpec, SectionSpec } from "./model";
import { armTally, costUsd, countsText, tally, TrialReport, TrialRun } from "./trial-model";
import type { Comparison, MetricKind } from "./comparison-model";
import { difference, judgmentMetric, observationStatus, ordinalLevels, summarize, welch, winMatrix } from "./comparison-stats";
import { fmtDates, trialReport } from "./compose";
import type { Narrative } from "./compose";
import { comparisonReport } from "./comparison-compose";
import type { ComparisonNarrative } from "./comparison-compose";
import { verdictWords } from "./blocks/trial";
import type { VerdictKind } from "./blocks/trial";
import type { Story } from "./reading";
import { composed, validateCollection } from "./validate";

export interface CollectionTheme { id: string; label?: string; summary?: string | string[] }
export interface CollectionMember {
  /** The member's key in links (#report/ID) and in the views' `members` fields. */
  id: string;
  theme?: string;
  /** Overrides the report's title in the collection views; `label` is a shorter name for compact views. */
  title?: string;
  label?: string;
  /** One line shown beside the decision on the member's card, such as what happened after it. */
  note?: string;
  /** When it ran (YYYY-MM-DD), when the data's own dates do not say it right. */
  date?: string;
  /** The id of an earlier member this one follows up. */
  follows?: string;
  /** Model names, when the data does not record them (comparisons, specifications). */
  models?: string[];
  /** Exactly one of trial, comparison or spec: the data a composition draws, or a finished specification of any blocks. */
  trial?: TrialReport;
  comparison?: Comparison;
  spec?: ReportSpec;
  narrative?: Narrative | ComparisonNarrative;
}
export interface CollectionPair { a: string; b: string; title?: string; note?: string }
export interface Collection {
  title?: string;
  kicker?: string;
  summary?: string | string[];
  footer?: string;
  /** What the whole collection set out to decide, for a reader new to it (see catalog.md#the-story). */
  story?: Story;
  /** What each section's views say, by section id. */
  readings?: Record<string, string | string[]>;
  themes?: CollectionTheme[];
  members: CollectionMember[];
  /** Comparisons worth making, each opened side by side. */
  pairs?: CollectionPair[];
}

/** One setup in a member: a trial arm or a comparison alternative, with its headline value on the member's measure. */
export interface MemberRow {
  id: string; label: string;
  /** The model it ran on (trial) or its group (comparison): setups are compared within a lane. */
  lane: string;
  /** Successes and valid trials, for measures that are rates (k is 0 otherwise); invalid observations. */
  k: number; n: number; invalid: number;
  /** The headline value in the measure's units (a share for rates), its 95% interval, and the value in words. */
  value: number | null; interval: [number, number] | null; text: string;
  /** numeric: mean, sd and n for differences between reports. */
  mean?: number | null; sd?: number | null;
  /** preference: the opponents it had decisive judgments against; rank: the company it was ranked in, one entry per
   * ranking's alternatives (each sorted, the list sorted). Its value is relative to these, so it is set against another
   * report's only where they agree. null when only supplied totals give its value, so they are not recorded. */
  contest?: string[] | null;
  /** Median recorded cost of a valid run, in US dollars. */
  cost: number | null;
  baseline: boolean;
  /** How many cases its value pools. Above one it has no interval, since runs on one case repeat that case
   * rather than sample new ones; `perCase` then holds each case's own value and interval. */
  cases: number;
  perCase?: CaseValue[];
}
/** One case's own value for a setup: k of n for rates, with its 95% interval. */
export interface CaseValue { id: string; label: string; k: number; n: number; value: number | null; interval: [number, number] | null; text: string }
/** A setup measured against the reference setup in its lane. */
export interface MemberGain {
  arm: string; label: string; lane: string; base: string;
  /** The setup minus its reference in the measure's units, its 95% interval and how it was found. */
  delta: number | null; interval: [number, number] | null; method: string;
  /** Whether the change is for the better by the measure's direction; null when it names none or nothing changed. */
  good: boolean | null;
  /** The trial's own per-case median difference in cost per run, as a share (−0.2 is 20% cheaper). */
  costChange: number | null;
  /** How many cases the change pools (no interval above one), and each case's own change with its interval. */
  cases: number;
  perCase?: Array<{ id: string; label: string; delta: number | null; interval: [number, number] | null }>;
}
/** What a member's headline values measure: trials measure the pass rate. */
export interface MemberMeasure {
  id: string; label: string; kind: MetricKind; better: "higher" | "lower" | "none"; unit: string;
  /** Rates and win shares sit on 0–100%; other measures on their own range. */
  percent: boolean; domain: [number, number];
  /** An ordinal measure's levels, lowest first: its scale. */
  levels?: string[];
  /** A rank measure's ranked set: the alternatives ranked (ids, sorted) and the most places a ranking gives (null when
   * only supplied totals say). A mean rank is on the scale of its set. */
  ranked?: string[]; places?: number | null;
  /** A preference measure's judged set (ids, sorted): a win share is a share against these. */
  judged?: string[];
}
export interface MemberSummary {
  id: string; index: number; kind: "trial" | "comparison" | "spec";
  theme: string; title: string; short: string; question: string;
  verdict: VerdictKind; stamp: string; headline: string; note: string;
  /** ISO date (YYYY-MM-DD) and, where the data record it and no `date` replaces it, the time the runs began. */
  date: string | null; time: number | null; dates: string | null;
  /** Trial runs, or a comparison's observations (valid as the comparison engine reads them). */
  runs: number; valid: number; invalid: number; noun: "runs" | "observations";
  /** Every kind of evidence the member holds, counted apart: runs, observations, judgments, rankings, supplied totals. */
  evidence: Array<{ n: number; noun: string; invalid?: number }>;
  models: string[]; judge: string | null;
  /** What the headline values measure, in words ("pass rate", or the comparison's primary metric). */
  metric: string;
  measure: MemberMeasure | null;
  rows: MemberRow[]; baseline: string | null; gains: MemberGain[];
  /** Total recorded cost of every run, in US dollars; null when no run records one. */
  cost: number | null;
  cases: Array<{ id: string; label: string }>;
  follows: string | null;
  arms: ArmRegistry;
}
export interface CollectionModel {
  data: Collection;
  members: MemberSummary[];
  byId: Map<string, MemberSummary>;
  themes: Array<{ id: string; label: string; summary?: string | string[]; members: MemberSummary[] }>;
  /** The author's pairs, then each follow-up with the member it follows. */
  pairs: Array<CollectionPair & { source: "pair" | "follows" }>;
  /** The member's full report as its standalone file composes it. */
  spec(id: string): ReportSpec | null;
  member(id: string): CollectionMember | null;
}

export const MEMBER_ID = /^[A-Za-z][\w.-]*$/;
const isObject = (v: unknown): v is Record<string, unknown> => !!v && typeof v === "object" && !Array.isArray(v);
const text = (v: unknown): string => typeof v === "string" ? v.trim() : isNum(v) ? String(v) : "";
const isTrial = (v: unknown): v is TrialReport => isObject(v) && Array.isArray(v.runs);
const isComparisonData = (v: unknown): v is Comparison => isObject(v) && Array.isArray(v.alternatives);
const isSpec = (v: unknown): v is ReportSpec => isObject(v) && typeof v.title === "string" && Array.isArray(v.sections);
/** The data a member's views read: its own trial or comparison, or the one its specification carries. */
function dataOf(m: CollectionMember): { trial?: TrialReport; comparison?: Comparison } {
  if (isSpec(m.spec)) return { trial: isTrial(m.spec.trial) ? m.spec.trial : undefined, comparison: !isTrial(m.spec.trial) && isComparisonData(m.spec.comparison) ? m.spec.comparison : undefined };
  return { trial: isTrial(m.trial) ? m.trial : undefined, comparison: isComparisonData(m.comparison) ? m.comparison : undefined };
}
/** Members the views can draw: an id links can carry, and exactly one trial, comparison or specification. */
export function usableMembers(data: Collection | undefined): CollectionMember[] {
  const seen = new Set<string>();
  return (isObject(data) && Array.isArray(data.members) ? data.members : []).filter((m): m is CollectionMember => {
    if (!isObject(m) || typeof m.id !== "string" || !MEMBER_ID.test(m.id) || seen.has(m.id)) return false;
    if ([isTrial(m.trial), isComparisonData(m.comparison), isSpec(m.spec)].filter(Boolean).length !== 1) return false;
    seen.add(m.id);
    return true;
  });
}

/** A calendar date written YYYY-MM-DD at the start of a value, or null (2026-02-30 is not one). */
export function calendarDay(v: unknown): string | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(text(v));
  if (!m) return null;
  const d = new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3])));
  return d.getUTCFullYear() === Number(m[1]) && d.getUTCMonth() === Number(m[2]) - 1 && d.getUTCDate() === Number(m[3]) ? m[0] : null;
}

const PASS_RATE: MemberMeasure = { id: "passed", label: "pass rate", kind: "binary", better: "higher", unit: "", percent: true, domain: [0, 1] };
const goodness = (d: number | null, better: MemberMeasure["better"]): boolean | null =>
  d === null || Math.abs(d) < 1e-12 || better === "none" ? null : (d > 0) === (better === "higher");

function trialRows(t: TrialReport, arms: string[], label: (id: string) => string, baseline: string | null, caseLabel: (id: string) => string): MemberRow[] {
  const cases = [...new Set(t.runs.map(r => r?.scenario).filter((x): x is string => typeof x === "string"))];
  return arms.map(id => {
    const runs = t.runs.filter(r => r && r.arm === id);
    const tl = armTally(t, id);
    const costs = runs.filter(r => r.passed === true || r.passed === false).map(costUsd).filter(isNum);
    const model = t.plan?.arms?.[id]?.model;
    const perCase = cases.flatMap(c => {
      const ct = tally(runs.filter(r => r.scenario === c));
      return ct.runs ? [{ id: c, label: caseLabel(c), k: ct.pass, n: ct.valid, value: ct.rate, interval: ct.interval, text: ct.valid ? `${ct.pass} of ${ct.valid}` : "no valid runs" }] : [];
    });
    return { id, label: label(id), lane: typeof model === "string" ? model : "", k: tl.pass, n: tl.valid, invalid: tl.invalid, value: tl.rate, interval: tl.interval,
      text: !tl.valid ? "no valid runs" : tl.cases > 1 ? countsText(tl) : `${tl.pass} of ${tl.valid} passed (${fmtPct(tl.rate)})`,
      cost: median(costs), baseline: id === baseline, cases: tl.cases, perCase };
  });
}

/** What each alternative's value is relative to, for the kinds whose values depend on who else took part: a preference
 * value on the opponents it had decisive judgments against, a rank on the alternatives each ranking placed it among
 * (observations ranked together share a case and unit). Undefined for other kinds. */
function contestsOf(c: Comparison, metric: { id: string; kind: string }): Map<string, Set<string>> | undefined {
  const out = new Map<string, Set<string>>();
  const add = (id: string, context: string) => { if (!out.has(id)) out.set(id, new Set()); out.get(id)!.add(context); };
  const sortedIds = (xs: unknown[]) => [...new Set(xs.filter((x): x is string => typeof x === "string"))].sort((x, y) => (x < y ? -1 : x > y ? 1 : 0));
  if (metric.kind === "preference") {
    const w = winMatrix(c, metric.id);
    w.ids.forEach((id, i) => w.ids.forEach((o, j) => { if (i !== j && (w.wins[i][j] || 0) + (w.wins[j][i] || 0) > 0) add(id, o); }));
    return out;
  }
  if (metric.kind !== "rank") return undefined;
  const mine = (named: unknown) => typeof named === "string" && named ? named === metric.id : judgmentMetric(c, "rank") === metric.id;
  for (const rk of Array.isArray(c.rankings) ? c.rankings : []) {
    if (!isObject(rk) || !Array.isArray(rk.order) || !mine(rk.metric)) continue;
    const ids = sortedIds(rk.order);
    for (const id of ids) add(id, ids.join(", "));
  }
  const groups = new Map<string, string[]>();
  for (const o of Array.isArray(c.observations) ? c.observations : []) {
    if (!isObject(o) || o.metric !== metric.id || typeof o.alternative !== "string" || !isNum(o.value) || o.value < 1 || o.valid === false) continue;
    const key = `${o.case ?? ""}\u0000${o.unit ?? ""}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key)!.push(o.alternative);
  }
  for (const members of groups.values()) { const ids = sortedIds(members); for (const id of ids) add(id, ids.join(", ")); }
  return out;
}

/** Each alternative's headline value on the comparison's primary metric, whatever its kind, as the comparison views summarize it. */
function comparisonRows(c: Comparison, ids: string[], label: (id: string) => string, baseline: string | null): { rows: MemberRow[]; measure: MemberMeasure | null } {
  const metrics = Array.isArray(c.metrics) ? c.metrics.filter(m => isObject(m) && typeof m.id === "string") : [];
  const primary = metrics.find(m => m.primary) || metrics[0];
  if (!primary) return { rows: [], measure: null };
  const summaries = summarize(c, primary.id);
  const contests = contestsOf(c, primary);
  const unit = text(primary.unit);
  const levels = primary.kind === "ordinal" ? ordinalLevels(c, primary) : [];
  const groupOf = (id: string) => { const a = c.alternatives.find(x => isObject(x) && x.id === id); const g = a?.group; return Array.isArray(g) ? g.map(text).filter(Boolean).join(" · ") : text(g); };
  const caseIds = (Array.isArray(c.cases) ? c.cases : []).filter(x => isObject(x) && typeof x.id === "string").map(x => ({ id: String(x.id), label: text(x.label) || String(x.id) }));
  const rate = primary.kind === "binary" || primary.kind === "count";
  const rows: MemberRow[] = ids.map(id => {
    const s = summaries.find(x => x.alternative === id);
    const n = s?.n ?? 0, invalid = s?.invalid ?? 0;
    // Observations on one case repeat it rather than sample new cases: pooled over several, the value has no interval.
    const perCase: CaseValue[] = caseIds.flatMap(cs => {
      const one = summarize(c, primary.id, { cases: [cs.id], alternatives: [id] }).find(x => x.alternative === id);
      if (!one || !one.n) return [];
      const v = rate ? one.rate ?? null : isNum(one.mean) ? one.mean : isNum(one.median) ? one.median : null;
      return [{ id: cs.id, label: cs.label, k: one.k ?? 0, n: one.n, value: v, interval: rate || isNum(one.mean) ? one.interval ?? null : null, text: rate ? `${one.k ?? 0} of ${one.n}` : v === null ? "no value" : `${fmtNum(v)}${unit ? ` ${unit}` : ""} (n = ${one.n})` }];
    });
    // The comparison engine decides when values pool repeats over several cases; such a value has no interval.
    const spread = s?.cases ?? 1, pooled = spread > 1;
    const across = pooled ? `, across ${spread} cases` : "";
    const row = { id, label: label(id), lane: groupOf(id), k: 0, n, invalid, value: null as number | null, interval: null as [number, number] | null, text: "no valid observations", cost: null, baseline: id === baseline, cases: spread, ...(perCase.length ? { perCase } : {}),
      ...(contests ? { contest: contests.has(id) ? [...contests.get(id)!].sort() : null } : {}) };
    if (!s || !n) return row;
    switch (primary.kind) {
      case "binary": case "count":
        return { ...row, k: s.k ?? 0, value: s.rate ?? null, interval: pooled ? null : s.interval ?? null, text: pooled ? `${s.k ?? 0} of ${n} across ${spread} cases` : `${s.k ?? 0} of ${n} (${fmtPct(s.rate)})` };
      case "preference": {
        const decisive = (s.wins ?? 0) + (s.losses ?? 0);
        return { ...row, k: s.wins ?? 0, n: decisive, value: decisive ? (s.wins ?? 0) / decisive : null, interval: s.interval ?? null, text: decisive ? `won ${s.wins ?? 0} of ${decisive} decisive judgments (${fmtPct((s.wins ?? 0) / decisive)})` : "no decisive judgments" };
      }
      case "numeric": {
        const v = isNum(s.mean) ? s.mean : isNum(s.median) ? s.median : null;
        return { ...row, value: v, interval: isNum(s.mean) && !pooled ? s.interval ?? null : null, mean: s.mean ?? null, sd: s.sd ?? null, text: v === null ? "no value" : `${isNum(s.mean) ? "mean" : "median"} ${fmtNum(v)}${unit ? ` ${unit}` : ""} (n = ${n}${across})` };
      }
      case "ordinal": {
        const at = s.medianLevel ? levels.indexOf(s.medianLevel) : -1;
        return { ...row, value: at >= 0 ? at : null, text: at >= 0 ? `median level “${s.medianLevel}” (n = ${n})` : "no level" };
      }
      case "rank":
        return { ...row, value: s.meanRank ?? null, interval: pooled ? null : s.interval ?? null, text: isNum(s.meanRank) ? `mean rank ${fmtNum(s.meanRank)} (n = ${n}${across})` : "no ranking" };
      default:
        return row;
    }
  });
  const percent = ["binary", "count", "preference"].includes(primary.kind);
  const spread = rows.flatMap(r => [r.value, ...(r.interval || [])]).filter(isNum);
  let domain: [number, number] = [0, 1];
  if (primary.kind === "ordinal") domain = [0, Math.max(1, levels.length - 1)];
  else if (primary.kind === "rank") domain = [1, Math.max(2, ids.length, ...spread)];
  else if (!percent && spread.length) {
    const lo = Math.min(...spread), hi = Math.max(...spread);
    const from = lo >= 0 && lo < hi / 2 ? 0 : lo - (hi - lo) * 0.08, to = hi + (hi - lo || Math.abs(hi) || 1) * 0.08;
    domain = [from, to > from ? to : from + 1];
  }
  const better = primary.better === "higher" || primary.better === "lower" ? primary.better : "none";
  // What a value's scale depends on beyond its kind: an ordinal's levels, a rank's ranked set, a preference's judged set.
  const sorted = (xs: string[]) => [...new Set(xs)].sort((x, y) => (x < y ? -1 : x > y ? 1 : 0));
  const scale = primary.kind === "ordinal" ? { levels }
    : primary.kind === "rank" ? { ranked: sorted(summaries.filter(s => s.n > 0).map(s => s.alternative)), places: summaries.some(s => s.values?.length) ? summaries.reduce((top, s) => (s.values || []).reduce((t, v) => v > t ? v : t, top), 0) : null }
    : primary.kind === "preference" ? { judged: sorted(summaries.filter(s => (s.wins ?? 0) + (s.losses ?? 0) + (s.ties ?? 0) > 0).map(s => s.alternative)) }
    : {};
  return { rows, measure: { id: primary.id, label: text(primary.label) || primary.id, kind: primary.kind, better, unit, percent, domain, ...scale } };
}

/** Each case both setups ran, with the setup's change on it and that change's own interval. */
function caseChanges(r: MemberRow, base: MemberRow, diff: (cs: string) => { delta: number | null; interval: [number, number] | null }): MemberGain["perCase"] {
  return (r.perCase || []).filter(x => (base.perCase || []).some(y => y.id === x.id)).map(x => ({ id: x.id, label: x.label, ...diff(x.id) }));
}

function trialGains(rows: MemberRow[], baseline: string | null, change: (id: string) => number | null): MemberGain[] {
  const base = rows.find(r => r.id === baseline);
  if (!base) return [];
  return rows.filter(r => r !== base && r.lane === base.lane).map(r => {
    const delta = r.value !== null && base.value !== null ? r.value - base.value : null;
    const cases = Math.max(r.cases, base.cases), pooled = cases > 1;
    const perCase = caseChanges(r, base, cs => {
      const x = r.perCase!.find(v => v.id === cs)!, y = base.perCase!.find(v => v.id === cs)!;
      return { delta: x.n && y.n ? x.k / x.n - y.k / y.n : null, interval: x.n && y.n ? newcombe(x.k, x.n, y.k, y.n) : null };
    });
    return { arm: r.id, label: r.label, lane: r.lane, base: base.id, delta, interval: !pooled && r.n && base.n ? newcombe(r.k, r.n, base.k, base.n) : null,
      method: pooled ? `pooled counts across ${cases} cases, with no interval (runs on one case repeat it); each case's own change has a 95% Newcombe interval` : "difference of pass rates with a 95% Newcombe interval",
      good: goodness(delta, "higher"), costChange: change(r.id), cases, ...(pooled ? { perCase } : {}) };
  });
}

/** A comparison's setups against the reference in their lane, with the comparison engine's own difference for the metric's kind. */
function comparisonGains(c: Comparison, measure: MemberMeasure | null, rows: MemberRow[], baseline: string | null): MemberGain[] {
  const base = rows.find(r => r.id === baseline);
  if (!base || !measure) return [];
  return rows.filter(r => r !== base && r.lane === base.lane).map(r => {
    const d = difference(c, measure.id, r.id, base.id);
    const cases = Math.max(r.cases, base.cases), pooled = cases > 1;
    const perCase = caseChanges(r, base, cs => { const e = difference(c, measure.id, r.id, base.id, { cases: [cs] }); return { delta: e.estimate, interval: e.interval }; });
    return { arm: r.id, label: r.label, lane: r.lane, base: base.id, delta: d.estimate, interval: pooled ? null : d.interval,
      method: pooled ? `pooled over ${cases} cases, with no interval (observations on one case repeat it); each case's own change has its interval` : d.method,
      good: goodness(d.estimate, measure.better), costChange: null, cases, ...(pooled ? { perCase } : {}) };
  });
}

/** A specification member's decision: its first verdict block. */
function specDecision(spec: ReportSpec): Record<string, unknown> | null {
  for (const section of spec.sections || []) for (const block of isObject(section) && Array.isArray(section.blocks) ? section.blocks : []) if (isObject(block) && block.type === "verdict") return block;
  return null;
}

function summarizeMember(m: CollectionMember, index: number, spec: ReportSpec): MemberSummary {
  const narrative = (isObject(m.narrative) ? m.narrative : {}) as Narrative & ComparisonNarrative;
  const custom = isSpec(m.spec);
  const decision = custom ? specDecision(m.spec!) : isObject(narrative.decision) ? narrative.decision : null;
  const asked = text(decision?.verdict).toLowerCase();
  const verdict: VerdictKind = decision && asked in verdictWords ? asked as VerdictKind : "none";
  const armSpecs: ArmSpec[] = (spec.arms || []).filter(a => isObject(a) && typeof a.id === "string");
  const arms = new ArmRegistry(armSpecs);
  const label = (id: string) => arms.label(id);
  const named = custom ? text(spec.title) : text(narrative.title) || text(narrative.question);
  const own = (fallback: string) => ({ title: text(m.title) || named || fallback || m.id, short: text(m.label) || text(m.title) || named || fallback || m.id });
  const base = { id: m.id, index, theme: text(m.theme), verdict, stamp: text(decision?.label) || verdictWords[verdict], headline: text(decision?.headline), note: text(m.note), follows: text(m.follows) || null, arms };
  const listed = Array.isArray(m.models) && m.models.length ? m.models.map(text).filter(Boolean) : null;
  const { trial: t, comparison: c } = dataOf(m);
  const kind = custom ? "spec" as const : t ? "trial" as const : "comparison" as const;
  if (t) {
    const ran = new Set(t.runs.map(r => r?.arm));
    const order = [...new Set([...armSpecs.map(a => a.id), ...t.runs.map(r => r?.arm)])].filter((id): id is string => typeof id === "string" && ran.has(id));
    const wanted = custom ? text(t.baseline) : text(narrative.baseline) || text(t.baseline);
    const baseline = order.includes(wanted) ? wanted : null;
    const caseText = isObject(custom ? spec.cases : narrative.cases) ? (custom ? spec.cases : narrative.cases) as Record<string, unknown> : {};
    const rows = trialRows(t, order, label, baseline, id => text(caseText[id]) || id);
    const all = tally(t.runs.filter((r): r is TrialRun => isObject(r)));
    const costs = t.runs.map(r => isObject(r) ? costUsd(r) : null).filter(isNum);
    const pct = (id: string) => { const v = t.pct_vs_baseline?.[id]?.cost_usd?.median ?? t.pct_vs_baseline?.[id]?.total_cost_usd?.median; return isNum(v) && t.baseline === baseline ? v : null; };
    const first = text(t.ran?.first) || text(t.generated_at);
    const cases = [...new Set(t.runs.map(r => r?.scenario).filter((s): s is string => typeof s === "string"))];
    const caseLabels = isObject(custom ? spec.cases : narrative.cases) ? (custom ? spec.cases : narrative.cases) as Record<string, unknown> : {};
    const time = Date.parse(first), set = calendarDay(m.date);
    return {
      ...base, ...own(text(t.name)), kind, question: custom ? "" : text(narrative.question),
      date: set || calendarDay(first), time: set || Number.isNaN(time) ? null : time,
      dates: set ? fmtDates(set) : fmtDates(t.ran?.first || t.generated_at, t.ran?.last),
      runs: all.runs, valid: all.valid, invalid: all.invalid, noun: "runs", evidence: [{ n: all.runs, noun: "run", invalid: all.invalid }],
      models: listed || [...new Set(rows.map(r => r.lane).filter(Boolean))], judge: text(t.plan?.judge?.model) || null,
      metric: "pass rate", measure: PASS_RATE, rows, baseline, gains: trialGains(rows, baseline, pct),
      cost: costs.length ? costs.reduce((a, b) => a + b, 0) : null,
      cases: cases.map(id => ({ id, label: text(caseLabels[id]) || id })),
    };
  }
  const set = calendarDay(m.date);
  const common = { date: set, time: null, dates: set ? fmtDates(set) : null, models: listed || [], judge: null, cost: null };
  if (!c) {
    return { ...base, ...own(""), ...common, kind, question: "", runs: 0, valid: 0, invalid: 0, noun: "observations", evidence: [], metric: "", measure: null, rows: [], baseline: null, gains: [], cases: [] };
  }
  const ids = armSpecs.length ? armSpecs.map(a => a.id).filter(id => c.alternatives.some(x => isObject(x) && x.id === id)) : c.alternatives.filter(isObject).map(x => x.id);
  const wanted = custom ? text(c.baseline) : text(narrative.baseline) || text(c.baseline);
  const baseline = ids.includes(wanted) ? wanted : null;
  const { rows, measure } = comparisonRows(c, ids, label, baseline);
  const cases = (Array.isArray(c.cases) ? c.cases : []).filter(x => isObject(x) && typeof x.id === "string").map(x => ({ id: x.id, label: text(x.label) || x.id }));
  // Validity as the comparison engine reads it: a missing or malformed value is invalid too.
  const status = observationStatus(c);
  const invalid = status.filter(s => s !== null).length;
  const count = (v: unknown) => Array.isArray(v) ? v.length : 0;
  const evidence = [
    { n: status.length, noun: "observation", invalid }, { n: count(c.preferences), noun: "judgment" }, { n: count(c.rankings), noun: "ranking" }, { n: count(c.aggregates), noun: "supplied total" },
  ].filter(e => e.n > 0);
  return {
    ...base, ...own(text(c.title) || text(c.question)), ...common, kind, question: custom ? "" : text(narrative.question) || text(c.question),
    runs: status.length, valid: status.length - invalid, invalid, noun: "observations", evidence,
    metric: measure?.label || "", measure, rows, baseline, gains: comparisonGains(c, measure, rows, baseline), cases,
  };
}

/** The member's full report: its specification, or the trial or comparison composition of its data and narrative. */
function composeMember(m: CollectionMember): ReportSpec {
  if (isSpec(m.spec)) return m.spec;
  return isTrial(m.trial) ? trialReport(m.trial, (m.narrative || {}) as Narrative) : comparisonReport(m.comparison as Comparison, (m.narrative || {}) as ComparisonNarrative);
}

const models = new WeakMap<object, CollectionModel>();
/** Summaries of every usable member, grouped by theme in the collection's order. */
export function collectionModel(data: Collection): CollectionModel {
  const cached = isObject(data) ? models.get(data) : undefined;
  if (cached) return cached;
  const usable = usableMembers(data);
  const specs = new Map<string, ReportSpec>();
  const spec = (id: string): ReportSpec | null => {
    const m = usable.find(x => x.id === id);
    if (!m) return null;
    if (!specs.has(id)) specs.set(id, composeMember(m));
    return specs.get(id)!;
  };
  const members = usable.map((m, i) => summarizeMember(m, i, spec(m.id)!));
  const byId = new Map(members.map(s => [s.id, s]));
  const declared = (Array.isArray(data?.themes) ? data.themes : []).filter((t): t is CollectionTheme => isObject(t) && typeof t.id === "string" && !!t.id);
  const themes: CollectionModel["themes"] = [];
  for (const t of declared) if (!themes.some(x => x.id === t.id)) themes.push({ id: t.id, label: text(t.label) || t.id, summary: t.summary, members: members.filter(s => s.theme === t.id) });
  const loose = members.filter(s => !themes.some(t => t.id === s.theme));
  if (loose.length) themes.push({ id: "", label: themes.length ? "Other reports" : "Reports", members: loose });
  const pairs: CollectionModel["pairs"] = [];
  const add = (a: string, b: string, extra: Partial<CollectionPair>, source: "pair" | "follows") => {
    if (a === b || !byId.has(a) || !byId.has(b) || pairs.some(p => (p.a === a && p.b === b) || (p.a === b && p.b === a))) return;
    pairs.push({ a, b, ...extra, source });
  };
  for (const p of Array.isArray(data?.pairs) ? data.pairs : []) if (isObject(p)) add(text(p.a), text(p.b), { title: text(p.title) || undefined, note: text(p.note) || undefined }, "pair");
  for (const s of members) if (s.follows) add(s.follows, s.id, {}, "follows");
  const model: CollectionModel = { data, members, byId, themes: themes.filter(t => t.members.length), pairs, spec, member: id => usable.find(x => x.id === id) || null };
  if (isObject(data)) models.set(data, model);
  return model;
}

/** Members a view draws: those named by `members`, in that order, else those in the named `themes`, else all, in collection order. */
export function selectMembers(model: CollectionModel, input: { members?: unknown; themes?: unknown }): MemberSummary[] {
  const names = Array.isArray(input.members) ? input.members.filter((x): x is string => typeof x === "string") : null;
  if (names) return [...new Set(names)].map(id => model.byId.get(id)).filter((s): s is MemberSummary => !!s);
  const themes = Array.isArray(input.themes) ? input.themes.filter((x): x is string => typeof x === "string") : null;
  return themes ? model.members.filter(s => themes.includes(s.theme)) : model.members;
}

/** The selected members grouped by theme: an explicit `members` list keeps its order, themes following their first member;
 * otherwise the collection's themes in its order. */
export function selectGroups(model: CollectionModel, input: { members?: unknown; themes?: unknown }): CollectionModel["themes"] {
  const chosen = selectMembers(model, input);
  if (!Array.isArray(input.members)) { const ids = new Set(chosen.map(s => s.id)); return model.themes.map(t => ({ ...t, members: t.members.filter(s => ids.has(s.id)) })).filter(t => t.members.length); }
  // An explicit list keeps its sequence: consecutive members of one theme share a group, and a theme met again later opens another.
  const groups: CollectionModel["themes"] = [];
  for (const s of chosen) {
    const theme = model.themes.find(t => t.members.includes(s))!;
    const last = groups[groups.length - 1];
    if (last && last.id === theme.id) last.members.push(s); else groups.push({ ...theme, members: [s] });
  }
  return groups;
}

// ------------------------------------------------------------------ comparing two members

/** A measure's scale as one string: the metric, its kind, unit and direction, and what its values are relative to (an
 * ordinal's levels, a rank's ranked set, a preference's judged set). Two members' values may be set side by side, on
 * one scale, differenced or ordered against each other, only when their keys agree. */
export function measureKey(m: MemberMeasure | null): string {
  return m ? JSON.stringify([m.id, m.kind, m.unit, m.better, m.levels ?? null, m.ranked ?? null, m.places ?? null, m.judged ?? null]) : "";
}
/** Whether two members' headline values measure the same thing on the same scale, so they may share one scale and be differenced. */
export function sameMeasure(a: MemberSummary, b: MemberSummary): boolean {
  return !!a.measure && !!b.measure && measureKey(a.measure) === measureKey(b.measure);
}
/** Why two members' headline values cannot share a scale, in words; null when they can. */
export function measuresApart(a: MemberSummary, b: MemberSummary): string | null {
  const x = a.measure, y = b.measure;
  if (!x || !y) return "at least one report has no headline value to set against the other's";
  if (measureKey(x) === measureKey(y)) return null;
  if (x.id !== y.id) return `A measures ${x.label} and B measures ${y.label}`;
  const levels = (m: MemberMeasure) => (m.levels || []).join(", ");
  const rankSet = (m: MemberMeasure) => `${(m.ranked || []).join(", ") || "none"}${isNum(m.places) ? ` in ${m.places} places` : " ranked"}`;
  const judgedSet = (m: MemberMeasure) => (m.judged || []).join(", ") || "none";
  const why = x.kind !== y.kind ? `as ${x.kind} and ${y.kind} values`
    : x.kind === "ordinal" && levels(x) !== levels(y) ? `on different ordered levels (A: ${levels(x) || "none"}; B: ${levels(y) || "none"})`
    : x.kind === "rank" && rankSet(x) !== rankSet(y) ? `on different ranked sets (A: ${rankSet(x)}; B: ${rankSet(y)})`
    : x.kind === "preference" && judgedSet(x) !== judgedSet(y) ? `against different sets of alternatives (A: ${judgedSet(x)}; B: ${judgedSet(y)})`
    : x.unit !== y.unit ? `in different units (A: ${x.unit || "none"}; B: ${y.unit || "none"})`
    : x.better !== y.better ? `in different directions (A: ${x.better === "none" ? "none named" : `${x.better} is better`}; B: ${y.better === "none" ? "none named" : `${y.better} is better`})`
    : null;
  return `A and B both measure ${x.label}, but ${why || "on different scales"}`;
}

/** Why two matched setups' values cannot be set against each other although their reports share a measure, in words;
 * null when they can. A preference or rank value is relative to who else took part, so the setup must have faced the
 * same opponents, or been ranked among the same alternatives, in both reports. */
export function rowsApart(m: MemberMeasure, a: MemberRow, b: MemberRow): string | null {
  if (m.kind !== "preference" && m.kind !== "rank") return null;
  const x = a.contest, y = b.contest, name = a.label === b.label ? a.label : `${a.label} and ${b.label}`;
  if (x && y && x.join("\u0000") === y.join("\u0000")) return null;
  const tail = "so its values are not set against each other";
  if (!x || !y) return `${m.kind === "preference" ? `the opponents ${name} faced are` : `the rankings ${name} was placed in are`} not recorded in ${!x && !y ? "either report" : !x ? "A" : "B"} (only supplied totals give its value), ${tail}`;
  // Opponents are one list; a rank's company is one list per ranking.
  const list = (v: string[]) => v.length ? v.join(m.kind === "preference" ? ", " : "; ") : "none";
  return m.kind === "preference" ? `${name} faced different opponents (A: ${list(x)}; B: ${list(y)}), ${tail}` : `${name} was ranked among different alternatives (A: ${list(x)}; B: ${list(y)}), ${tail}`;
}

/** B minus A for two matched setups on the same measure: Newcombe for rates, Welch for means; null where the kind has no
 * such difference. `why` says, when there is no interval, why not. */
export function crossDifference(m: MemberMeasure, a: MemberRow, b: MemberRow): { estimate: number; interval: [number, number] | null; method: string; why: string | null } | null {
  // Values pooled over several cases have no interval, and neither does their difference.
  const pooled = Math.max(a.cases, b.cases) > 1, pooledWhy = "pooled over cases, no interval";
  if ((m.kind === "binary" || m.kind === "count") && a.n && b.n) {
    if (pooled) return { estimate: b.k / b.n - a.k / a.n, interval: null, method: "difference of pooled counts, with no interval (runs on one case repeat it)", why: pooledWhy };
    const iv = newcombe(b.k, b.n, a.k, a.n);
    return { estimate: b.k / b.n - a.k / a.n, interval: iv, method: "difference of rates with a 95% Newcombe interval", why: iv ? null : "no interval: the counts do not allow one" };
  }
  if (m.kind === "numeric" && isNum(a.mean) && isNum(b.mean)) {
    if (pooled) return { estimate: b.mean - a.mean, interval: null, method: "difference of means pooled over cases, with no interval", why: pooledWhy };
    const w = isNum(a.sd) && isNum(b.sd) && a.n > 1 && b.n > 1 ? welch(b.mean, b.sd, b.n, a.mean, a.sd, a.n) : null;
    return { estimate: b.mean - a.mean, interval: w?.interval ?? null, method: w ? "difference of means with a 95% Welch interval" : "difference of means (no interval: a spread is missing)", why: w?.interval ? null : "no interval: a spread is missing" };
  }
  return null;
}

/** Setups of two members matched for comparison: by label, then by id, then reference with reference. */
export function matchRows(a: MemberSummary, b: MemberSummary): Array<{ a: MemberRow | null; b: MemberRow | null; how: string }> {
  const left = [...a.rows], right = [...b.rows], out: Array<{ a: MemberRow | null; b: MemberRow | null; how: string }> = [];
  const take = (pred: (x: MemberRow, y: MemberRow) => boolean, how: string) => {
    for (const x of [...left]) {
      const y = right.find(r => pred(x, r));
      if (y) { out.push({ a: x, b: y, how }); left.splice(left.indexOf(x), 1); right.splice(right.indexOf(y), 1); }
    }
  };
  take((x, y) => x.label.toLowerCase() === y.label.toLowerCase(), "same label");
  take((x, y) => x.id === y.id, "same id");
  // Ids that differ only by an ending every id on its side shares, such as -gpt and -cl.
  const ending = (ids: string[]) => {
    if (ids.length < 2) return "";
    const tails = ids.map(id => /[-_:.][^-_:.]+$/.exec(id)?.[0] || "");
    return tails[0] && tails.every(t => t === tails[0]) ? tails[0] : "";
  };
  const ea = ending(a.rows.map(r => r.id)), eb = ending(b.rows.map(r => r.id));
  if (ea && eb && ea !== eb) take((x, y) => x.id.slice(0, -ea.length) === y.id.slice(0, -eb.length), `same id apart from ${ea} and ${eb}`);
  take((x, y) => x.baseline && y.baseline, "both references");
  return [...out, ...left.map(x => ({ a: x, b: null, how: "" })), ...right.map(y => ({ a: null, b: y, how: "" }))];
}

/** Passed and valid counts of one setup on one case. */
export function caseCell(collection: CollectionModel, s: MemberSummary, arm: string, scenario: string): { k: number; n: number } | null {
  const m = collection.member(s.id);
  if (!m) return null;
  const { trial, comparison } = dataOf(m);
  if (trial) {
    const runs = trial.runs.filter(r => r && r.arm === arm && r.scenario === scenario);
    if (!runs.length) return null;
    const tl = tally(runs);
    return { k: tl.pass, n: tl.valid };
  }
  const c = comparison;
  const metric = c ? (c.metrics || []).find(x => x?.primary) || c.metrics?.[0] : undefined;
  if (!c || !metric || (metric.kind !== "binary" && metric.kind !== "count")) return null;
  const got = summarize(c, metric.id, { cases: [scenario], alternatives: [arm] }).find(x => x.alternative === arm);
  return got && (got.n || got.invalid) ? { k: got.k ?? 0, n: got.n } : null;
}

// ------------------------------------------------------------------ compositions

/** The section ids of the collection composition, in order. */
export const COLLECTION_SECTION_IDS = ["glance", "reports", "shifts", "cost-gain", "timeline", "matchups"] as const;

/** The collection page: the whole collection at a glance, every report by theme, then the cross-report views
 * that have something to show. Each section is ordinary; a caller can drop, reorder or extend them. */
export function collectionReport(data: Collection): ReportSpec {
  if (!isObject(data) || !Array.isArray(data.members)) throw new TypeError("collectionReport needs a collection: an object with a members list (see catalog.md).");
  const model = collectionModel(data);
  const ms = model.members;
  const count = (v: VerdictKind) => ms.filter(s => s.verdict === v).length;
  const runs = ms.filter(s => s.noun === "runs"), others = ms.filter(s => s.noun !== "runs");
  // Evidence other than trial runs, counted by kind: observations, judgments, rankings, supplied totals.
  const extra = new Map<string, number>();
  for (const s of others) for (const e of s.evidence) extra.set(e.noun, (extra.get(e.noun) || 0) + e.n);
  const extraWords = [...extra].map(([noun, n]) => `${n} ${noun}${n === 1 ? "" : "s"}`);
  const sum = (xs: number[]) => xs.reduce((a, b) => a + b, 0);
  const named = (n: number, word: string) => n ? `${n} ${word}${n === 1 ? "" : "s"}` : "";
  const allModels = [...new Set(ms.flatMap(s => s.models))];
  const costs = ms.map(s => s.cost).filter(isNum);
  const times = ms.map(s => s.date).filter((d): d is string => !!d).sort();
  const shared = (f: (s: MemberSummary) => boolean) => ms.some(f);
  const sections: SectionSpec[] = [
    {
      id: "glance", title: "At a glance", label: "Glance",
      lead: "What each report decided, grouped by theme. Select a decision to open its report.",
      blocks: [
        { type: "figures", items: [
          { value: ms.length, label: ms.length === 1 ? "report" : "reports", note: [named(ms.filter(s => s.kind === "trial").length, "trial"), named(ms.filter(s => s.kind === "comparison").length, "comparison"), named(ms.filter(s => s.kind === "spec").length, "specification")].filter(Boolean).join(", ") },
          ...(runs.length ? [{ value: sum(runs.map(s => s.runs)), label: "trial runs", note: `${sum(runs.map(s => s.valid))} valid, ${sum(runs.map(s => s.invalid))} invalid${extraWords.length ? `; the other reports hold ${extraWords.join(", ")}` : ""}` }]
            : extraWords.length ? [{ value: extraWords[0], label: "evidence", note: extraWords.slice(1).join(", ") || undefined }] : []),
          { value: count("adopt"), label: "adopted", tone: "pass" as const },
          { value: count("reject"), label: "not adopted", tone: "fail" as const },
          ...(count("mixed") + count("inconclusive") + count("none") ? [{ value: count("mixed") + count("inconclusive") + count("none"), label: "mixed or open", tone: "warn" as const }] : []),
          ...(allModels.length ? [{ value: allModels.length, label: allModels.length === 1 ? "model" : "models", note: allModels.join(", ") }] : []),
          ...(costs.length ? [{ value: `$${sum(costs).toFixed(2)}`, label: "recorded cost", note: costs.length < ms.length ? `${costs.length} of ${ms.length} reports record cost` : undefined }] : []),
          ...(times.length ? [{ value: fmtDates(times[0], times[times.length - 1]) || times[0], label: "ran" }] : []),
        ] },
        { type: "decisions" },
      ],
    },
    { id: "reports", title: "Every report", label: "Reports", lead: "Each card is one report: its decision in a sentence, how each setup did, and the exact counts on demand. Open one to read it in full, or pick two to compare.", blocks: [{ type: "reports" }] },
  ];
  // Pass rates only when every report drawn is a trial; any other measure sits on its own scale.
  const passRates = ms.filter(s => s.rows.length > 0).every(s => s.kind === "trial");
  if (shared(s => s.rows.length > 0)) sections.push(passRates
    ? { id: "shifts", title: "How the pass rates moved", label: "Shifts", lead: "Every setup each report tried, on one 0–100% scale per model. A ring marks the setup the others were measured against; the line from it shows how far each change moved the pass rate.", blocks: [{ type: "shifts" }] }
    : { id: "shifts", title: "How each report's result moved", label: "Shifts", lead: "Every setup each report tried, each report on its own measure's scale: a rate on 0–100%, any other measure on its own range, shown at the ends of its track. A ring marks the setup the others were measured against; the line from it shows how far each change moved the result.", blocks: [{ type: "shifts" }] });
  if (shared(s => s.gains.some(g => g.delta !== null && g.costChange !== null))) sections.push({ id: "cost-gain", title: "Cost against gain", label: "Cost", lead: "Each point is one change measured against its reference on the same model: up means more runs passed, right means each run cost more.", blocks: [{ type: "cost-gain" }] });
  if (ms.filter(s => s.date).length > 1 || shared(s => !!s.follows)) sections.push({ id: "timeline", title: "How the work unfolded", label: "Timeline", lead: "The reports in the order they ran, with each follow-up linked to the report it followed.", blocks: [{ type: "timeline" }] });
  if (model.pairs.length) sections.push({ id: "matchups", title: "Side by side", label: "Compare", lead: "Pairs worth reading together: the same question on another model, or a follow-up and the report it followed.", blocks: [{ type: "matchups" }] });
  const readings = isObject(data.readings) ? data.readings : {};
  for (const s of sections) if (typeof s.id === "string" && Object.prototype.hasOwnProperty.call(readings, s.id)) s.reading = readings[s.id] as string | string[];
  const spec: ReportSpec = {
    title: text(data.title) || "Report collection",
    kicker: text(data.kicker) || "Collection",
    summary: data.summary,
    sections,
    footer: text(data.footer) || `${ms.length} reports in one file: every view is drawn from the data embedded here, and every report opens in full.`,
    collection: data,
    ...(isObject(data.story) ? { story: data.story as Story } : {}),
  };
  // The collection's own checks, with each member's; the page lists them once.
  const problems = validateCollection(data);
  return composed({ ...spec, problems }, problems);
}

/** The member's full report, as its standalone file would compose it, for reading inside the collection. */
export function memberReport(data: Collection, id: string): ReportSpec | null {
  return collectionModel(data).spec(id);
}

/** Two members side by side: their decisions, setups, cases and cost, and each decision as its report states it. */
export function compareReport(data: Collection, a: string, b: string): ReportSpec {
  const model = collectionModel(data);
  const sa = model.byId.get(a), sb = model.byId.get(b);
  const name = (s: MemberSummary | undefined, id: string) => s ? s.short : id;
  const block: BlockSpec = { type: "report-compare", a, b };
  // The page tells its own story: what each report is about, in its own words, and why the two are read together.
  const opening = (s: MemberSummary | undefined, id: string, letter: string): string => {
    if (!s) return `**${letter}:** \`${id}\` is not a report in this collection.`;
    const story = model.spec(s.id)?.story, bg = story ? (Array.isArray(story.background) ? story.background : [story.background]).find(x => typeof x === "string" && x.trim()) : "";
    return `**${letter}: ${s.title}${/[.?!]$/.test(s.title) ? "" : "."}** ${bg || s.question || "Its report states no background."}`;
  };
  const decided = (s: MemberSummary | undefined, letter: string) => s ? `${letter} (${s.short}): ${s.stamp}${s.headline ? `. ${s.headline}` : ""}` : `${letter}: no such report`;
  const pair = model.pairs.find(p => (p.a === a && p.b === b) || (p.a === b && p.b === a));
  const same = !!sa && !!sb && sameMeasure(sa, sb);
  const story: Story = {
    background: [opening(sa, a, "A"), opening(sb, b, "B")],
    intent: pair ? `The collection reads these two together: ${pair.title || (pair.source === "follows" ? "a follow-up and the report it followed" : "a pair worth comparing")}.` : "Two reports of this collection, chosen to be read side by side.",
    questions: ["Did the decision change from A to B, and on what evidence?", same ? `Where both measure ${sa!.metric}, how far apart are the setups they share?` : "What does each report measure, given that their values cannot share one scale?"],
    covers: "Each report's decision as it states it, the models and evidence behind it, and each setup's result, on one scale where both measure the same thing.",
    notCovered: "Anything either report leaves out. Each opens in full from here, with its own story and every run.",
  };
  const apart = sa && sb ? measuresApart(sa, sb) : null;
  // Setups whose values are relative to different contests (opponents faced, company ranked in) stay apart even on one measure.
  const contested = same ? matchRows(sa!, sb!).filter(x => x.a && x.b && rowsApart(sa!.measure!, x.a, x.b)).map(x => x.a!.label) : [];
  const except = contested.length ? `, except ${contested.length === 1 ? contested[0] : `${contested.slice(0, -1).join(", ")} and ${contested[contested.length - 1]}`}, which ${sa!.measure!.kind === "preference" ? `faced different opponents in the two reports` : `were ranked among different alternatives in the two reports`} and ${contested.length === 1 ? "is" : "are"} shown apart` : "";
  const reading = `${decided(sa, "A")} ${decided(sb, "B")} ${same ? `Both measure ${sa!.metric}, so their setups sit on one scale${except}.` : `${apart ? `${apart.charAt(0).toUpperCase()}${apart.slice(1)}, so each` : "Each"} is shown on its own scale and never subtracted.`}`;
  return {
    title: `${name(sa, a)} and ${name(sb, b)}`,
    kicker: `${text(data.kicker) || "Collection"} · side by side`,
    sections: [{ id: "compare", title: "Side by side", label: "Compare", reading, blocks: [block] }],
    footer: "Both reports open in full from here; every number is drawn from the data embedded in this file.",
    collection: data,
    story,
  };
}
