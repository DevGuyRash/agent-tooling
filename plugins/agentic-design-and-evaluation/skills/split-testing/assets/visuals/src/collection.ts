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
import { caseKey, caseSplit, casesWords, difference, eachWeighted, evidenceAs, NO_CASE, NO_CASE_WORDS, observationStatus, ordinalLevels, pooledWords, summarize, welch } from "./comparison-stats";
import { fmtDates, trialReport } from "./compose";
import type { Narrative } from "./compose";
import { comparisonReport } from "./comparison-compose";
import type { ComparisonNarrative } from "./comparison-compose";
import { verdictWords } from "./blocks/trial";
import type { VerdictKind } from "./blocks/trial";
import type { Story } from "./reading";
import { composed, reportCases, validateCollection } from "./validate";

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
  /** The headline value in the measure's units (a share for rates), pooled as the report states it, its 95% interval,
   * and the value in words. */
  value: number | null; interval: [number, number] | null; text: string;
  /** The value case-balanced (balancedValue): what every view that sets setups or reports against each other plots,
   * sorts and differences, so no mix of cases or invalid run moves it. Equal to `value` for a value from one case. */
  balanced: number | null;
  /** numeric: mean, sd and n for differences between reports. */
  mean?: number | null; sd?: number | null;
  /** Median recorded cost of a valid run, in US dollars. */
  cost: number | null;
  baseline: boolean;
  /** How many cases its value pools. Above one it has no interval, since runs on one case repeat that case
   * rather than sample new ones; `perCase` then holds each case's own value and interval. */
  cases: number;
  /** What its value pools, in words (casesWords): evidence naming no case counted beside the cases, never as one. */
  over: string;
  perCase?: CaseValue[];
}
/** One case's own value for a setup: k of n for rates, with its 95% interval. */
export interface CaseValue {
  id: string; label: string; k: number; n: number; value: number | null; interval: [number, number] | null; text: string;
  /** numeric: the case's mean and sd; ordinal: its count at each level, lowest first. */
  mean?: number | null; sd?: number | null; counts?: number[];
}
/** A setup measured against the reference setup in its lane. */
export interface MemberGain {
  arm: string; label: string; lane: string; base: string;
  /** The setup minus its reference in the measure's units, its 95% interval and how it was found. */
  delta: number | null; interval: [number, number] | null; method: string;
  /** The reference's and the setup's values the change is taken between (over the cases both ran): where a track draws
   * the change's line. Null when there is no change to draw. */
  from: number | null; to: number | null;
  /** Whether the change is for the better by the measure's direction; null when it names none or nothing changed. */
  good: boolean | null;
  /** The trial's own per-case median difference in cost per run, as a share (−0.2 is 20% cheaper). */
  costChange: number | null;
  /** How many cases the change pools (no interval above one), what it is taken over in words (casesWords), and each
   * case's own change with its interval. */
  cases: number;
  over: string;
  perCase?: Array<{ id: string; label: string; delta: number | null; interval: [number, number] | null }>;
}
/** What a member's headline values measure: trials measure the pass rate. */
export interface MemberMeasure {
  id: string; label: string; kind: MetricKind; better: "higher" | "lower" | "none"; unit: string;
  /** Rates and win shares sit on 0–100%; other measures on their own range. */
  percent: boolean; domain: [number, number];
  /** An ordinal measure's levels, lowest first: its scale. */
  levels?: string[];
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
  /** Whether any of its evidence names no case: said beside its cases, as a group of its own, never counted as one. */
  noCase: boolean;
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
/** An id as written: the checks hold every id to the identifier rule (isId), so ids are compared exactly, never trimmed. */
const idOf = (v: unknown): string => typeof v === "string" ? v : "";
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
  const cases = [...new Set(t.runs.filter(r => r).map(r => caseKey(r.scenario)))];
  return arms.map(id => {
    const runs = t.runs.filter(r => r && r.arm === id);
    const tl = armTally(t, id);
    const costs = runs.filter(r => r.passed === true || r.passed === false).map(costUsd).filter(isNum);
    const model = t.plan?.arms?.[id]?.model;
    const perCase = cases.flatMap(c => {
      const ct = tally(runs.filter(r => caseKey(r.scenario) === c));
      return ct.runs ? [{ id: c, label: c === NO_CASE ? NO_CASE_WORDS : caseLabel(c), k: ct.pass, n: ct.valid, value: ct.rate, interval: ct.interval, text: ct.valid ? `${ct.pass} of ${ct.valid}` : "no valid runs" }] : [];
    });
    return { id, label: label(id), lane: typeof model === "string" ? model : "", k: tl.pass, n: tl.valid, invalid: tl.invalid, value: tl.rate, interval: tl.interval,
      text: !tl.valid ? "no valid runs" : tl.cases > 1 ? countsText(tl) : `${tl.pass} of ${tl.valid} passed (${fmtPct(tl.rate)})`,
      cost: median(costs), baseline: id === baseline, cases: tl.cases, over: casesWords(tl.cases, false), perCase, balanced: null as number | null };
  }).map(r => ({ ...r, balanced: balancedValue(PASS_RATE, r) }));
}


/** Each alternative's headline value on the comparison's primary metric, whatever its kind, as the comparison views summarize it. */
/** The axis a measure's values are drawn on: rates and win shares on 0–100%, levels from the lowest to the highest, ranks
 * from first, and any other measure from 0 (or just below its lowest value) to just past its highest. */
export function measureDomain(m: MemberMeasure, values: number[], alternatives = 2): [number, number] {
  if (m.percent) return [0, 1];
  if (m.kind === "ordinal") return [0, Math.max(1, (m.levels || []).length - 1)];
  if (m.kind === "rank") return [1, Math.max(2, alternatives, ...values)];
  if (!values.length) return [0, 1];
  const lo = Math.min(...values), hi = Math.max(...values);
  const from = lo >= 0 && lo < hi / 2 ? 0 : lo - (hi - lo) * 0.08, to = hi + (hi - lo || Math.abs(hi) || 1) * 0.08;
  return [from, to > from ? to : from + 1];
}

function comparisonRows(c: Comparison, ids: string[], label: (id: string) => string, baseline: string | null): { rows: MemberRow[]; measure: MemberMeasure | null; source: Comparison } {
  const metrics = Array.isArray(c.metrics) ? c.metrics.filter(m => isObject(m) && typeof m.id === "string") : [];
  const primary = metrics.find(m => m.primary) || metrics[0];
  if (!primary) return { rows: [], measure: null, source: c };
  // The evidence every value of a setup is taken from, chosen once by the comparison engine (evidenceAs: an alternative's
  // supplied totals only where its summary reads them, so no case filter can bring in a total the value left out), with
  // what names no case as one case of its own. The value, its words, its per-case values, its cases and every change are
  // read from this; each summary's own case weights say which cases its value rests on.
  const relative = primary.kind === "preference" || primary.kind === "rank";
  const list = (v: unknown) => Array.isArray(v) ? v : [];
  const ev = evidenceAs(c);
  const cc = ev;
  const summaries = summarize(cc, primary.id);
  // The cases the report ran: every case its evidence names, whether or not it gave a value (invalid observations, ties,
  // judgments never reached), as each summary lists them. Values, weights and counts read the summaries' case weights.
  const rested = new Set(summaries.flatMap(x => x.casesRun || []));
  const unit = text(primary.unit);
  // The levels the summaries' counts follow: inferred, as theirs are, from the evidence read.
  const levels = primary.kind === "ordinal" ? ordinalLevels(cc, primary) : [];
  const groupOf = (id: string) => { const a = c.alternatives.find(x => isObject(x) && x.id === id); const g = a?.group; return Array.isArray(g) ? g.map(text).filter(Boolean).join(" · ") : text(g); };
  const declared = (Array.isArray(c.cases) ? c.cases : []).filter(x => isObject(x) && typeof x.id === "string").map(x => ({ id: String(x.id), label: text(x.label) || String(x.id) }));
  // The cases the headline values are taken over: those the headline metric's evidence names, declared ones in their order,
  // then the others in the order the data name them. (The report's cases, on every metric, are its story's: see reportCases.)
  const inData = [...new Set([...list(cc.observations), ...list(cc.aggregates), ...list(cc.preferences), ...list(cc.rankings)].map(x => isObject(x) ? caseKey(x.case) : NO_CASE).filter(x => rested.has(x)))];
  const caseIds = [...declared.filter(d => rested.has(d.id)), ...inData.filter(id => !declared.some(d => d.id === id)).map(id => ({ id, label: id === NO_CASE ? NO_CASE_WORDS : id }))];
  const rate = primary.kind === "binary" || primary.kind === "count";
  const rows: MemberRow[] = ids.map(id => {
    const s = summaries.find(x => x.alternative === id);
    const n = s?.n ?? 0, invalid = s?.invalid ?? 0;
    // Observations on one case repeat it rather than sample new cases: pooled over several, the value has no interval.
    const perCase: CaseValue[] = caseIds.flatMap((cs): CaseValue[] => {
      if (relative) {
        // A win share or mean rank depends on who else took part, so a case holds no value of its own here: only the
        // decisive judgments (a ranking's pairs among them) or rankings it gave this alternative, as its summary counts
        // them, a supplied total as the number it stands for.
        const takes = (s?.caseWeights || []).find(e => e[0] === cs.id)?.[1] || 0;
        const noun = primary.kind === "preference" ? (takes === 1 ? "decisive judgment" : "decisive judgments") : (takes === 1 ? "ranking" : "rankings");
        if (takes) return [{ id: cs.id, label: cs.label, k: 0, n: takes, value: null, interval: null, text: `${takes} ${noun}${s?.fromAggregate ? ", as a supplied total" : ""}` }];
        if (!s?.casesRun?.includes(cs.id)) return [];
        // A case it ran with nothing decisive or valid there: what happened, as that case's own summary counts it.
        const there = summarize(cc, primary.id, { cases: [cs.id] }).find(x => x.alternative === id);
        const what = [there?.ties ? `${there.ties} ${there.ties === 1 ? "tie" : "ties"}` : "", ...Object.entries(there?.invalidReasons || {}).map(([why, k]) => `${k} invalid: ${why}`)].filter(Boolean).join("; ");
        return [{ id: cs.id, label: cs.label, k: 0, n: 0, value: null, interval: null, text: `${primary.kind === "preference" ? "no decisive judgments" : "no valid rankings"}${what ? ` (${what})` : ""}` }];
      }
      const one = summarize(cc, primary.id, { cases: [cs.id], alternatives: [id] }).find(x => x.alternative === id);
      if (!one || !one.n && !one.invalid) return [];
      // A case with only invalid observations ran, but gives no value.
      if (!one.n) return [{ id: cs.id, label: cs.label, k: 0, n: 0, value: null, interval: null, text: "no valid observations" }];
      if (primary.kind === "ordinal") {
        const at = one.medianLevel ? levels.indexOf(one.medianLevel) : -1;
        return [{ id: cs.id, label: cs.label, k: 0, n: one.n, value: at >= 0 ? at : null, interval: null, counts: one.counts || [], text: at >= 0 ? `median level “${one.medianLevel}” (n = ${one.n})` : "no level" }];
      }
      const v = rate ? one.rate ?? null : isNum(one.mean) ? one.mean : isNum(one.median) ? one.median : null;
      return [{ id: cs.id, label: cs.label, k: one.k ?? 0, n: one.n, value: v, interval: rate || isNum(one.mean) ? one.interval ?? null : null, mean: one.mean ?? null, sd: one.sd ?? null, text: rate ? `${one.k ?? 0} of ${one.n}` : v === null ? "no value" : `${fmtNum(v)}${unit ? ` ${unit}` : ""} (n = ${one.n})` }];
    });
    // The comparison engine decides when values pool repeats over several cases; such a value has no interval.
    const spread = s?.cases ?? 1, pooled = spread > 1, over = s ? pooledWords(s) : casesWords(0, false);
    const across = pooled ? `, across ${over}` : "";
    const row = { id, label: label(id), lane: groupOf(id), k: 0, n, invalid, value: null as number | null, interval: null as [number, number] | null, text: "no valid observations", cost: null, baseline: id === baseline, cases: spread, over, balanced: null as number | null, ...(perCase.length ? { perCase } : {}) };
    if (!s || !n) return row;
    switch (primary.kind) {
      case "binary": case "count":
        return { ...row, k: s.k ?? 0, value: s.rate ?? null, interval: pooled ? null : s.interval ?? null, text: pooled ? `${s.k ?? 0} of ${n} across ${over}` : `${s.k ?? 0} of ${n} (${fmtPct(s.rate)})` };
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
        return { ...row, value: at >= 0 ? at : null, text: at >= 0 ? `median level “${s.medianLevel}” (n = ${n}${across})` : "no level" };
      }
      case "rank":
        return { ...row, value: s.meanRank ?? null, interval: pooled ? null : s.interval ?? null, text: isNum(s.meanRank) ? `mean rank ${fmtNum(s.meanRank)} (n = ${n}${across})` : "no ranking" };
      default:
        return row;
    }
  });
  const percent = ["binary", "count", "preference"].includes(primary.kind);
  const better = primary.better === "higher" || primary.better === "lower" ? primary.better : "none";
  const shape: MemberMeasure = { id: primary.id, label: text(primary.label) || primary.id, kind: primary.kind, better, unit, percent, domain: [0, 1], ...(primary.kind === "ordinal" ? { levels } : {}) };
  // Every value plotted is the case-balanced one, and the axis is drawn to hold it.
  const balancedRows = rows.map(r => ({ ...r, balanced: balancedValue(shape, r) }));
  const measure: MemberMeasure = { ...shape, domain: measureDomain(shape, balancedRows.flatMap(r => [r.balanced, ...(r.interval || [])]).filter(isNum), ids.length) };
  return { rows: balancedRows, measure, source: cc };
}

/** A setup's change from its reference, case-balanced as every comparison of setups is: its delta, interval and method,
 * and how many cases it is taken over. */
function balancedGain(m: MemberMeasure, base: MemberRow, r: MemberRow): { delta: number | null; interval: [number, number] | null; method: string; cases: number; over: string; from: number | null; to: number | null } {
  const g = caseBalanced(m, base, r, [base.label, r.label]);
  if ("apart" in g) return { delta: null, interval: null, method: g.apart, cases: 0, over: casesWords(0, false), from: null, to: null };
  // Its hover text names the cases it is taken over, and what either side ran beyond them.
  const named = g.cases.length > 1 ? `; over ${g.cases.slice(0, -1).join(", ")} and ${g.cases[g.cases.length - 1]}, ${eachWeighted(g.noCase)}` : `; on ${g.cases[0]}`;
  return { delta: g.estimate, interval: g.interval, method: `${g.method}${named}${g.coverage ? `; ${g.coverage}` : ""}`, cases: g.shared, over: g.over, from: g.a, to: g.b };
}

/** Each case both setups ran, with the setup's change on it and that change's own interval. */
function caseChanges(r: MemberRow, base: MemberRow, diff: (cs: string) => { delta: number | null; interval: [number, number] | null }): MemberGain["perCase"] {
  return (r.perCase || []).filter(x => (base.perCase || []).some(y => y.id === x.id)).map(x => ({ id: x.id, label: x.label, ...diff(x.id) }));
}

function trialGains(rows: MemberRow[], baseline: string | null, change: (id: string) => number | null): MemberGain[] {
  const base = rows.find(r => r.id === baseline);
  if (!base) return [];
  return rows.filter(r => r !== base && r.lane === base.lane).map(r => {
    // The setup against its reference over the cases both have a valid result on, each weighted equally.
    const g = balancedGain(PASS_RATE, base, r);
    const perCase = caseChanges(r, base, cs => {
      const x = r.perCase!.find(v => v.id === cs)!, y = base.perCase!.find(v => v.id === cs)!;
      return { delta: x.n && y.n ? x.k / x.n - y.k / y.n : null, interval: x.n && y.n ? newcombe(x.k, x.n, y.k, y.n) : null };
    });
    return { arm: r.id, label: r.label, lane: r.lane, base: base.id, ...g, good: goodness(g.delta, "higher"), costChange: change(r.id), ...(g.cases > 1 ? { perCase } : {}) };
  });
}

/** A comparison's setups against the reference in their lane, case-balanced. A preference or rank value depends on who
 * else took part, so it gets no change: its value is shown with its own counts, nothing more. */
function comparisonGains(c: Comparison, measure: MemberMeasure | null, rows: MemberRow[], baseline: string | null): MemberGain[] {
  const base = rows.find(r => r.id === baseline);
  if (!base || !measure || relativeMeasure(measure)) return [];
  return rows.filter(r => r !== base && r.lane === base.lane).map(r => {
    const perCase = caseChanges(r, base, cs => { const e = difference(c, measure.id, r.id, base.id, { cases: [cs] }); return { delta: e.estimate, interval: e.interval }; });
    const g = balancedGain(measure, base, r);
    return { arm: r.id, label: r.label, lane: r.lane, base: base.id, ...g, good: goodness(g.delta, measure.better), costChange: null, ...(g.cases > 1 ? { perCase } : {}) };
  });
}

/** A specification member's decision: its first verdict block. */
function specDecision(spec: ReportSpec): Record<string, unknown> | null {
  for (const section of spec.sections || []) for (const block of isObject(section) && Array.isArray(section.blocks) ? section.blocks : []) if (isObject(block) && block.type === "verdict") return block;
  return null;
}

/** A report's cases, as its story check reads them, each with the label its report gives it: its own case labels, else
 * the label a comparison it draws declares. */
function caseList(spec: ReportSpec): Array<{ id: string; label: string }> {
  const own = isObject(spec.cases) ? spec.cases as Record<string, unknown> : {};
  const declared = new Map<string, string>();
  const take = (c: unknown) => { if (isComparisonData(c)) for (const x of Array.isArray(c.cases) ? c.cases : []) if (isObject(x) && typeof x.id === "string" && text(x.label) && !declared.has(x.id)) declared.set(x.id, text(x.label)); };
  take(spec.comparison);
  for (const s of Array.isArray(spec.sections) ? spec.sections : []) for (const b of isObject(s) && Array.isArray(s.blocks) ? s.blocks : []) if (isObject(b)) take(b.data);
  return reportCases(spec).map(id => ({ id, label: text(own[id]) || declared.get(id) || id }));
}

/** Whether any evidence of a comparison the report draws, its own or a view's, names no case. */
function namesNoCase(spec: ReportSpec): boolean {
  const unnamed = (c: unknown) => isComparisonData(c) && ["observations", "aggregates", "preferences", "rankings"].some(k => {
    const list = (c as unknown as Record<string, unknown>)[k];
    return Array.isArray(list) && list.some(x => isObject(x) && caseKey(x.case) === NO_CASE);
  });
  return unnamed(spec.comparison) || (Array.isArray(spec.sections) ? spec.sections : []).some(s => isObject(s) && Array.isArray(s.blocks) && s.blocks.some(b => isObject(b) && unnamed(b.data)));
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
  const base = { id: m.id, index, theme: idOf(m.theme), verdict, stamp: text(decision?.label) || verdictWords[verdict], headline: text(decision?.headline), note: text(m.note), follows: idOf(m.follows) || null, arms };
  const listed = Array.isArray(m.models) && m.models.length ? m.models.map(text).filter(Boolean) : null;
  // The cases the member's report ran: exactly those its story must describe, from every source of data it uses.
  const cases = caseList(spec), noCase = namesNoCase(spec);
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
    const time = Date.parse(first), set = calendarDay(m.date);
    return {
      ...base, ...own(text(t.name)), kind, question: custom ? "" : text(narrative.question),
      date: set || calendarDay(first), time: set || Number.isNaN(time) ? null : time,
      dates: set ? fmtDates(set) : fmtDates(t.ran?.first || t.generated_at, t.ran?.last),
      runs: all.runs, valid: all.valid, invalid: all.invalid, noun: "runs", evidence: [{ n: all.runs, noun: "run", invalid: all.invalid }],
      models: listed || [...new Set(rows.map(r => r.lane).filter(Boolean))], judge: text(t.plan?.judge?.model) || null,
      metric: "pass rate", measure: PASS_RATE, rows, baseline, gains: trialGains(rows, baseline, pct),
      cost: costs.length ? costs.reduce((a, b) => a + b, 0) : null, cases, noCase,
    };
  }
  const set = calendarDay(m.date);
  const common = { date: set, time: null, dates: set ? fmtDates(set) : null, models: listed || [], judge: null, cost: null };
  if (!c) {
    return { ...base, ...own(""), ...common, kind, question: "", runs: 0, valid: 0, invalid: 0, noun: "observations", evidence: [], metric: "", measure: null, rows: [], baseline: null, gains: [], cases, noCase };
  }
  const ids = armSpecs.length ? armSpecs.map(a => a.id).filter(id => c.alternatives.some(x => isObject(x) && x.id === id)) : c.alternatives.filter(isObject).map(x => x.id);
  const wanted = custom ? text(c.baseline) : text(narrative.baseline) || text(c.baseline);
  const baseline = ids.includes(wanted) ? wanted : null;
  const { rows, measure, source } = comparisonRows(c, ids, label, baseline);
  const gains = comparisonGains(source, measure, rows, baseline);
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
    metric: measure?.label || "", measure: held(measure, rows, gains), rows, baseline, gains, cases, noCase,
  };
}
/** A measure whose track holds everything drawn on it: each value, its interval, and both ends of every change's line. */
function held(m: MemberMeasure | null, rows: MemberRow[], gains: MemberGain[]): MemberMeasure | null {
  if (!m) return m;
  const drawn = [...rows.flatMap(r => [r.balanced, ...(r.interval || [])]), ...gains.flatMap(g => [g.from, g.to])].filter(isNum);
  return { ...m, domain: measureDomain(m, drawn, rows.length) };
}

/** The member's full report: its specification, or the trial or comparison composition of its data and narrative. */
function composeMember(m: CollectionMember): ReportSpec {
  if (isSpec(m.spec)) return m.spec;
  return isTrial(m.trial) ? trialReport(m.trial, (m.narrative || {}) as Narrative) : comparisonReport(m.comparison as Comparison, (m.narrative || {}) as ComparisonNarrative);
}

/** Each collection's model with the data it was read from, as printed then: a model is reused only while its collection,
 * printed again, is the same, so an edit made in place is always read. Printing the 24-report collection takes about 6 ms;
 * reading it takes about 55, and a page reads it once for its composition and once for each of its views. */
const models = new WeakMap<object, { print: string; model: CollectionModel }>();
const printOf = (v: unknown): string => { try { return JSON.stringify(v) ?? ""; } catch { return ""; } };
/** Summaries of every usable member, grouped by theme in the collection's order. */
export function collectionModel(data: Collection): CollectionModel {
  const print = isObject(data) ? printOf(data) : "";
  const cached = print ? models.get(data) : undefined;
  if (cached && cached.print === print) return cached.model;
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
  for (const p of Array.isArray(data?.pairs) ? data.pairs : []) if (isObject(p)) add(idOf(p.a), idOf(p.b), { title: text(p.title) || undefined, note: text(p.note) || undefined }, "pair");
  for (const s of members) if (s.follows) add(s.follows, s.id, {}, "follows");
  const model: CollectionModel = { data, members, byId, themes: themes.filter(t => t.members.length), pairs, spec, member: id => usable.find(x => x.id === id) || null };
  if (print) models.set(data, { print, model });
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

/** A measure's scale as one string: the metric, its kind, unit and direction, and an ordinal's levels. Two members'
 * values may share one scale, be differenced or be ordered against each other only when their keys agree. */
export function measureKey(m: MemberMeasure | null): string {
  return m ? JSON.stringify([m.id, m.kind, m.unit, m.better, m.levels ?? null]) : "";
}
/** Whether a measure's values depend on who else took part: a win share on who was judged and how often, a mean rank on
 * who was ranked. Such values are never set against another report's. */
export const relativeMeasure = (m: MemberMeasure | null): boolean => !!m && (m.kind === "preference" || m.kind === "rank");
/** Whether two members' headline values measure the same thing on the same scale, so they may share one scale and be differenced. */
export function sameMeasure(a: MemberSummary, b: MemberSummary): boolean {
  return !!a.measure && !!b.measure && !relativeMeasure(a.measure) && measureKey(a.measure) === measureKey(b.measure);
}
/** Why two members' headline values cannot share a scale, in words; null when they can. */
export function measuresApart(a: MemberSummary, b: MemberSummary): string | null {
  const x = a.measure, y = b.measure;
  if (!x || !y) return "at least one report has no headline value to set against the other's";
  if (x.id !== y.id) return `A measures ${x.label} and B measures ${y.label}`;
  const levels = (m: MemberMeasure) => (m.levels || []).join(", ");
  if (x.kind === y.kind && relativeMeasure(x)) return `A and B both measure ${x.label}, ${x.kind === "preference" ? "a share of decisive judgments that depends on who else was judged and how often" : "a mean rank that depends on who else was ranked and how often"}`;
  if (measureKey(x) === measureKey(y)) return null;
  const why = x.kind !== y.kind ? `as ${x.kind} and ${y.kind} values`
    : x.kind === "ordinal" && levels(x) !== levels(y) ? `on different ordered levels (A: ${levels(x) || "none"}; B: ${levels(y) || "none"})`
    : x.unit !== y.unit ? `in different units (A: ${x.unit || "none"}; B: ${y.unit || "none"})`
    : x.better !== y.better ? `in different directions (A: ${x.better === "none" ? "none named" : `${x.better} is better`}; B: ${y.better === "none" ? "none named" : `${y.better} is better`})`
    : null;
  return `A and B both measure ${x.label}, but ${why || "on different scales"}`;
}

/** A setup's case-balanced value (direct standardization): its value on each of the given cases (by default every case
 * it has a valid result on) with every case weighted equally. Rates and means are averaged; an ordinal measure takes
 * the median level of its level shares averaged over the cases, never a mean of positions. With one case it is that
 * case's own value. The one place a value is balanced: every view, sort and tooltip that sets setups or reports against
 * each other takes its values from here. A preference or rank value depends on who else took part and is not balanced. */
export function balancedValue(m: MemberMeasure, r: MemberRow, ids?: string[]): number | null {
  if (relativeMeasure(m)) return r.value;
  const cs = (r.perCase || []).filter(c => c.n > 0 && c.value !== null && (!ids || ids.includes(c.id)));
  if (!cs.length) return r.perCase?.length || ids ? null : r.value;
  if (m.kind !== "ordinal") return cs.reduce((t, c) => t + c.value!, 0) / cs.length;
  const width = Math.max(...cs.map(c => (c.counts || []).length));
  const share = Array.from({ length: width }, (_, i) => cs.reduce((t, c) => { const k = c.counts || [], n = k.reduce((u, v) => u + v, 0); return t + (n ? (k[i] || 0) / n : 0); }, 0) / cs.length);
  let cum = 0;
  for (let i = 0; i < share.length; i++) { cum += share[i]; if (cum >= 0.5 - 1e-12) return i; }
  return share.length ? share.length - 1 : null;
}

/** One matched setup's change between two reports, or a setup against its reference within one, case-balanced: each
 * side's balancedValue over the cases both have a valid result on, so neither side's mix of cases or an invalid run
 * moves it. With one shared case it is that case's own comparison, with a 95% interval (Newcombe for rates, Welch for
 * means); balanced over several there is none, since the average pools cases. `label` says what the line covers when it
 * is not simply both values; `coverage` when either side ran cases the other did not, or has no valid result on some.
 * With no case in common, `apart` says so and nothing is compared. */
export type CaseBalanced =
  | { apart: string; ranTogether: boolean }
  | { a: number; b: number; estimate: number | null; interval: [number, number] | null; method: string; why: string | null; label: string | null; coverage: string | null; shared: number; cases: string[]; over: string; noCase: boolean };
export function caseBalanced(m: MemberMeasure, ra: MemberRow, rb: MemberRow, names: [string, string] = ["A", "B"]): CaseBalanced {
  const [A, B] = names;
  const ran = (r: MemberRow) => r.perCase || [];
  const valid = (r: MemberRow) => ran(r).filter(c => c.n > 0 && c.value !== null);
  const ea = ran(ra), eb = ran(rb), va = valid(ra), vb = valid(rb);
  const shared = va.flatMap(x => { const y = vb.find(c => c.id === x.id); return y ? [[x, y] as const] : []; });
  const name = ra.label === rb.label ? ra.label : `${ra.label} and ${rb.label}`;
  const list = (cs: CaseValue[]) => cs.map(c => c.label).join(", ") || "none";
  if (!shared.length) {
    const together = ea.some(x => eb.some(y => y.id === x.id));
    return { ranTogether: together, apart: together
      ? `${name} has no case with a valid result in both (${A}: ${list(va)}; ${B}: ${list(vb)}), so the two values are not set against each other`
      : `${name} ran no case in common in the two reports (${A}: ${list(ea)}; ${B}: ${list(eb)}), so the two values are not set against each other` };
  }
  // Cases run are told apart from cases with a valid result, so an invalid run is never read as a case not run. Each count
  // is worded by casesWords, so evidence naming no case is counted beside the cases, never as one.
  const allValid = va.length === ea.length && vb.length === eb.length, n = shared.length;
  const where = allValid ? "both ran" : `both have a valid result on`;
  const split = (cs: readonly CaseValue[]) => caseSplit(cs.map(c => c.id));
  const [sharedNamed, noCase] = split(shared.map(p => p[0]));
  const coverage = n < ea.length || n < eb.length
    ? `${A} ran ${casesWords(...split(ea))}${va.length < ea.length ? `, ${casesWords(...split(va), "with a valid result", true)},` : ""} and ${B} ${casesWords(...split(eb), "", true)}${vb.length < eb.length ? `, ${casesWords(...split(vb), "with a valid result", true)}` : ""}; the line covers only the ${casesWords(sharedNamed, noCase, where, allValid)}`
    : null;
  const rate = m.kind === "binary" || m.kind === "count", ordinal = m.kind === "ordinal";
  const caseNames = shared.map(p => p[0].label);
  const over = casesWords(sharedNamed, noCase, where);
  if (n === 1) {
    // That case's own comparison: its repeats are the samples, so it keeps an interval where the counts or spreads allow one.
    const [x, y] = shared[0];
    const label = coverage ? (noCase ? `on the ${NO_CASE_WORDS} alone` : `on the one case ${where}, ${x.label}`) : null;
    if (rate) {
      const iv = newcombe(y.k, y.n, x.k, x.n);
      return { a: x.value!, b: y.value!, estimate: y.value! - x.value!, interval: iv, method: iv ? "difference of rates with a 95% Newcombe interval" : "difference of rates (no interval: the counts do not allow one)", why: iv ? null : "no interval: the counts do not allow one", label, coverage, shared: n, cases: caseNames, over, noCase };
    }
    if (m.kind === "numeric" && isNum(x.mean) && isNum(y.mean)) {
      const spread = isNum(x.sd) && isNum(y.sd) && x.n > 1 && y.n > 1;
      const iv = spread ? welch(y.mean, y.sd!, y.n, x.mean, x.sd!, x.n)?.interval ?? null : null;
      const why = iv ? null : !spread ? "no interval: a spread is missing" : x.sd === 0 && y.sd === 0 ? `no interval: neither ${A === "A" && B === "B" ? "report's" : "setup's"} values vary` : "no interval: the spreads do not allow one";
      return { a: x.mean, b: y.mean, estimate: y.mean - x.mean, interval: iv, method: iv ? "difference of means with a 95% Welch interval" : `difference of means (${why})`, why, label, coverage, shared: n, cases: caseNames, over, noCase };
    }
    return { a: x.value!, b: y.value!, estimate: null, interval: null, method: "each side's median level on that case; no difference is computed for levels", why: null, label, coverage, shared: n, cases: caseNames, over, noCase };
  }
  const ids = shared.map(p => p[0].id);
  const a = balancedValue(m, ra, ids)!, b = balancedValue(m, rb, ids)!;
  const label = `${ordinal ? "balanced" : "averaged"} over the ${over}, ${eachWeighted(noCase)}`;
  return ordinal
    ? { a, b, estimate: null, interval: null, method: `each side's median level of its level shares averaged over the ${over}, ${eachWeighted(noCase)}; no difference is computed for levels`, why: null, label, coverage, shared: n, cases: caseNames, over, noCase }
    : { a, b, estimate: b - a, interval: null, method: `difference of case-balanced ${rate ? "rates" : "means"} over the ${over}, ${eachWeighted(noCase)}; no interval, since the average pools cases`, why: "averaged over cases, no interval", label, coverage, shared: n, cases: caseNames, over, noCase };
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
  // The same per-case values every comparison is taken from.
  const c = s.rows.find(r => r.id === arm)?.perCase?.find(x => x.id === scenario);
  return c ? { k: c.k, n: c.n } : null;
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
  // Composed for each call, so a reader's change to one report never reaches the next.
  const m = usableMembers(data).find(x => x.id === id);
  return m ? composeMember(m) : null;
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
  // Each change is taken over the cases both reports ran, each weighted equally; a setup with no case in common stays apart.
  // Each refusal keeps its reason: a case never run in common is not a case run in both with no valid result.
  const balanced = same ? matchRows(sa!, sb!).flatMap(x => x.a && x.b ? [{ name: x.a.label, r: caseBalanced(sa!.measure!, x.a, x.b) }] : []) : [];
  const refused = balanced.flatMap(({ name, r }) => "apart" in r ? [{ name, ranTogether: r.ranTogether }] : []);
  // Evidence naming no case, where a change averages it, is said beside the cases as every other statement says it.
  const noCase = balanced.some(({ r }) => !("apart" in r) && r.noCase);
  const listed = (names: string[]) => names.length === 1 ? names[0] : `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
  const parts = [
    ...(refused.some(r => !r.ranTogether) ? [`${listed(refused.filter(r => !r.ranTogether).map(r => r.name))}, which ran no case in common in the two reports`] : []),
    ...(refused.some(r => r.ranTogether) ? [`${listed(refused.filter(r => r.ranTogether).map(r => r.name))}, which ${refused.filter(r => r.ranTogether).length === 1 ? "has" : "have"} no case with a valid result in both`] : []),
  ];
  const except = parts.length ? `, except ${parts.join("; and ")}, shown apart` : "";
  const reading = `${decided(sa, "A")} ${decided(sb, "B")} ${same ? `Both measure ${sa!.metric}, so their setups sit on one scale, each change taken over the cases both reports ran${noCase ? `, plus ${NO_CASE_WORDS}` : ""}, ${eachWeighted(noCase)}${except}.` : `${apart ? `${apart.charAt(0).toUpperCase()}${apart.slice(1)}, so each` : "Each"} is shown on its own scale and never subtracted.`}`;
  return {
    title: `${name(sa, a)} and ${name(sb, b)}`,
    kicker: `${text(data.kicker) || "Collection"} · side by side`,
    sections: [{ id: "compare", title: "Side by side", label: "Compare", reading, blocks: [block] }],
    footer: "Both reports open in full from here; every number is drawn from the data embedded in this file.",
    collection: data,
    story,
  };
}
