/** A collection: many reports (trials and comparisons, each with its narrative)
 * in one page with one copy of the library. This module reads a collection
 * into per-report summaries the collection views share, and composes the
 * collection page, each member's full report and the side-by-side view of two
 * members as ordinary specifications. Like the rest of the library it computes
 * only counts, pass rates with Wilson intervals and differences between rates
 * with Newcombe intervals; every decision shown is the one its narrative wrote. */
import { isNum, median } from "./core";
import { newcombe } from "./stats";
import { ArmRegistry } from "./model";
import type { ArmSpec, BlockSpec, ReportSpec, SectionSpec } from "./model";
import { costUsd, tally, TrialReport, TrialRun } from "./trial-model";
import type { Comparison } from "./comparison-model";
import { metricOf, summarize } from "./comparison-stats";
import { fmtDates, trialReport } from "./compose";
import type { Narrative } from "./compose";
import { comparisonReport } from "./comparison-compose";
import type { ComparisonNarrative } from "./comparison-compose";
import { verdictWords } from "./blocks/trial";
import type { VerdictKind } from "./blocks/trial";

export interface CollectionTheme { id: string; label?: string; summary?: string | string[] }
export interface CollectionMember {
  /** The member's key in links (#report/ID) and in the views' `members` fields. */
  id: string;
  theme?: string;
  /** Overrides the narrative's title in the collection views; `label` is a shorter name for compact views. */
  title?: string;
  label?: string;
  /** One line shown beside the decision on the member's card, such as what happened after it. */
  note?: string;
  /** When it ran (YYYY-MM-DD), when the data's own dates do not say it right. */
  date?: string;
  /** The id of an earlier member this one follows up. */
  follows?: string;
  /** Model names, when the data does not record them (comparisons). */
  models?: string[];
  trial?: TrialReport;
  comparison?: Comparison;
  narrative?: Narrative | ComparisonNarrative;
}
export interface CollectionPair { a: string; b: string; title?: string; note?: string }
export interface Collection {
  title?: string;
  kicker?: string;
  summary?: string | string[];
  footer?: string;
  themes?: CollectionTheme[];
  members: CollectionMember[];
  /** Comparisons worth making, each opened side by side. */
  pairs?: CollectionPair[];
}

/** One setup in a member: a trial arm or a comparison alternative, with its pass rate (or rate on the primary metric). */
export interface MemberRow {
  id: string; label: string;
  /** The model it ran on (trial) or its group (comparison): setups are compared within a lane. */
  lane: string;
  k: number; n: number; invalid: number;
  rate: number | null; interval: [number, number] | null;
  /** Median recorded cost of a valid run, in US dollars. */
  cost: number | null;
  baseline: boolean;
}
/** A setup measured against the reference setup in its lane. */
export interface MemberGain {
  arm: string; label: string; lane: string; base: string;
  delta: number | null; interval: [number, number] | null;
  /** The trial's own per-case median difference in cost per run, as a share (−0.2 is 20% cheaper). */
  costChange: number | null;
}
export interface MemberSummary {
  id: string; index: number; kind: "trial" | "comparison";
  theme: string; title: string; short: string; question: string;
  verdict: VerdictKind; stamp: string; headline: string; note: string;
  /** ISO date (YYYY-MM-DD) and, where the data record it and no `date` replaces it, the time the runs began. */
  date: string | null; time: number | null; dates: string | null;
  runs: number; valid: number; invalid: number; noun: "runs" | "observations";
  models: string[]; judge: string | null;
  /** What the rates measure: "pass rate", or the comparison's primary metric. */
  metric: string;
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
/** Members the views can draw: an id links can carry, and one trial or one comparison. */
export function usableMembers(data: Collection | undefined): CollectionMember[] {
  const seen = new Set<string>();
  return (isObject(data) && Array.isArray(data.members) ? data.members : []).filter((m): m is CollectionMember => {
    if (!isObject(m) || typeof m.id !== "string" || !MEMBER_ID.test(m.id) || seen.has(m.id)) return false;
    if (isTrial(m.trial) === isComparisonData(m.comparison)) return false;
    seen.add(m.id);
    return true;
  });
}

function day(v: unknown): string | null {
  const s = text(v);
  return /^\d{4}-\d{2}-\d{2}/.test(s) ? s.slice(0, 10) : null;
}

function trialRows(t: TrialReport, arms: string[], label: (id: string) => string, baseline: string | null): MemberRow[] {
  return arms.map(id => {
    const runs = t.runs.filter(r => r && r.arm === id);
    const tl = tally(runs);
    const costs = runs.filter(r => r.passed === true || r.passed === false).map(costUsd).filter(isNum);
    const model = t.plan?.arms?.[id]?.model;
    return { id, label: label(id), lane: typeof model === "string" ? model : "", k: tl.pass, n: tl.valid, invalid: tl.invalid, rate: tl.rate, interval: tl.interval, cost: median(costs), baseline: id === baseline };
  });
}

function comparisonRows(c: Comparison, ids: string[], label: (id: string) => string, baseline: string | null): { rows: MemberRow[]; metric: string } {
  const metrics = Array.isArray(c.metrics) ? c.metrics.filter(m => isObject(m) && typeof m.id === "string") : [];
  const primary = metrics.find(m => m.primary) || metrics[0];
  if (!primary || (primary.kind !== "binary" && primary.kind !== "count")) return { rows: [], metric: primary ? text(primary.label) || primary.id : "" };
  const summaries = summarize(c, primary.id);
  const groupOf = (id: string) => { const a = c.alternatives.find(x => isObject(x) && x.id === id); const g = a?.group; return Array.isArray(g) ? g.map(text).filter(Boolean).join(" · ") : text(g); };
  const rows = ids.map(id => {
    const s = summaries.find(x => x.alternative === id);
    return { id, label: label(id), lane: groupOf(id), k: s?.k ?? 0, n: s?.n ?? 0, invalid: s?.invalid ?? 0, rate: s?.rate ?? null, interval: s?.interval ?? null, cost: null, baseline: id === baseline };
  });
  return { rows, metric: text(metricOf(c, primary.id)?.label) || primary.id };
}

function gainsOf(rows: MemberRow[], baseline: string | null, change: (id: string) => number | null): MemberGain[] {
  const base = rows.find(r => r.id === baseline);
  if (!base) return [];
  return rows.filter(r => r !== base && r.lane === base.lane).map(r => ({
    arm: r.id, label: r.label, lane: r.lane, base: base.id,
    delta: r.rate !== null && base.rate !== null ? r.rate - base.rate : null,
    interval: r.n && base.n ? newcombe(r.k, r.n, base.k, base.n) : null,
    costChange: change(r.id),
  }));
}

function summarizeMember(m: CollectionMember, index: number, spec: ReportSpec): MemberSummary {
  const narrative = (isObject(m.narrative) ? m.narrative : {}) as Narrative & ComparisonNarrative;
  const decision = isObject(narrative.decision) ? narrative.decision : null;
  const asked = text(decision?.verdict).toLowerCase();
  const verdict: VerdictKind = decision && asked in verdictWords ? asked as VerdictKind : "none";
  const armSpecs: ArmSpec[] = (spec.arms || []).filter(a => isObject(a) && typeof a.id === "string");
  const arms = new ArmRegistry(armSpecs);
  const label = (id: string) => arms.label(id);
  const base = { id: m.id, index, theme: text(m.theme), verdict, stamp: text(decision?.label) || verdictWords[verdict], headline: text(decision?.headline), note: text(m.note), follows: text(m.follows) || null, arms };
  if (isTrial(m.trial)) {
    const t = m.trial;
    const ran = new Set(t.runs.map(r => r?.arm));
    const order = armSpecs.map(a => a.id).filter(id => ran.has(id));
    const wanted = text(narrative.baseline) || text(t.baseline);
    const baseline = order.includes(wanted) ? wanted : null;
    const rows = trialRows(t, order, label, baseline);
    const all = tally(t.runs.filter((r): r is TrialRun => isObject(r)));
    const costs = t.runs.map(r => isObject(r) ? costUsd(r) : null).filter(isNum);
    const pct = (id: string) => { const v = t.pct_vs_baseline?.[id]?.cost_usd?.median ?? t.pct_vs_baseline?.[id]?.total_cost_usd?.median; return isNum(v) && t.baseline === baseline ? v : null; };
    const models = Array.isArray(m.models) && m.models.length ? m.models.map(text).filter(Boolean) : [...new Set(rows.map(r => r.lane).filter(Boolean))];
    const judge = text(t.plan?.judge?.model) || null;
    const first = text(t.ran?.first) || text(t.generated_at);
    const cases = [...new Set(t.runs.map(r => r?.scenario).filter((s): s is string => typeof s === "string"))];
    const caseLabels = isObject(narrative.cases) ? narrative.cases as Record<string, unknown> : {};
    const time = Date.parse(first);
    return {
      ...base, kind: "trial",
      title: text(m.title) || text(narrative.title) || text(narrative.question) || text(t.name) || m.id,
      short: text(m.label) || text(m.title) || text(narrative.title) || text(narrative.question) || text(t.name) || m.id,
      question: text(narrative.question),
      date: day(m.date) || day(first), time: day(m.date) || Number.isNaN(time) ? null : time,
      dates: day(m.date) ? fmtDates(day(m.date)) : fmtDates(t.ran?.first || t.generated_at, t.ran?.last),
      runs: all.runs, valid: all.valid, invalid: all.invalid, noun: "runs",
      models, judge, metric: "pass rate", rows, baseline, gains: gainsOf(rows, baseline, pct),
      cost: costs.length ? costs.reduce((a, b) => a + b, 0) : null,
      cases: cases.map(id => ({ id, label: text(caseLabels[id]) || id })),
    };
  }
  const c = m.comparison as Comparison;
  const ids = armSpecs.map(a => a.id);
  const wanted = text(narrative.baseline) || text(c.baseline);
  const baseline = ids.includes(wanted) ? wanted : null;
  const { rows, metric } = comparisonRows(c, ids, label, baseline);
  const cases = (Array.isArray(c.cases) ? c.cases : []).filter(x => isObject(x) && typeof x.id === "string").map(x => ({ id: x.id, label: text(x.label) || x.id }));
  const metrics = (Array.isArray(c.metrics) ? c.metrics : []).filter(x => isObject(x) && typeof x.id === "string");
  const primary = metrics.find(x => x.primary) || metrics[0];
  // Observations of the primary metric: one per run or unit observed, as the rates count them.
  const observed = (Array.isArray(c.observations) ? c.observations : []).filter(o => isObject(o) && (!primary || o.metric === primary.id));
  const invalid = observed.filter(o => o.valid === false).length;
  return {
    ...base, kind: "comparison",
    title: text(m.title) || text(narrative.title) || text(narrative.question) || text(c.title) || text(c.question) || m.id,
    short: text(m.label) || text(m.title) || text(narrative.title) || text(c.title) || m.id,
    question: text(narrative.question) || text(c.question),
    date: day(m.date), time: null, dates: day(m.date) ? fmtDates(day(m.date)) : null,
    runs: observed.length, valid: observed.length - invalid, invalid, noun: "observations",
    models: Array.isArray(m.models) ? m.models.map(text).filter(Boolean) : [], judge: null,
    metric, rows, baseline, gains: gainsOf(rows, baseline, () => null), cost: null, cases,
  };
}

/** The member's full report: the trial or comparison composition of its data and narrative. */
function composeMember(m: CollectionMember): ReportSpec {
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

/** Members a view draws: those named by `members`, else those in the named `themes`, else all, in collection order. */
export function selectMembers(model: CollectionModel, input: { members?: unknown; themes?: unknown }): MemberSummary[] {
  const names = Array.isArray(input.members) ? input.members.filter((x): x is string => typeof x === "string") : null;
  if (names) return names.map(id => model.byId.get(id)).filter((s): s is MemberSummary => !!s);
  const themes = Array.isArray(input.themes) ? input.themes.filter((x): x is string => typeof x === "string") : null;
  return themes ? model.members.filter(s => themes.includes(s.theme)) : model.members;
}

// ------------------------------------------------------------------ comparing two members

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
  if (isTrial(m.trial)) {
    const runs = m.trial.runs.filter(r => r && r.arm === arm && r.scenario === scenario);
    if (!runs.length) return null;
    const tl = tally(runs);
    return { k: tl.pass, n: tl.valid };
  }
  const c = m.comparison as Comparison;
  const metric = (c.metrics || []).find(x => x?.primary) || c.metrics?.[0];
  if (!metric) return null;
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
  const runs = ms.filter(s => s.noun === "runs"), observed = ms.filter(s => s.noun === "observations");
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
          { value: ms.length, label: ms.length === 1 ? "report" : "reports", note: [named(runs.length, "trial"), named(observed.length, "comparison")].filter(Boolean).join(", ") },
          ...(runs.length ? [{ value: sum(runs.map(s => s.runs)), label: "trial runs", note: `${sum(runs.map(s => s.valid))} valid, ${sum(runs.map(s => s.invalid))} invalid${observed.length ? `; the ${named(observed.length, "comparison")} add ${sum(observed.map(s => s.runs))} observations` : ""}` }] : []),
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
  if (shared(s => s.rows.length > 0)) sections.push({ id: "shifts", title: "How the pass rates moved", label: "Shifts", lead: "Every setup each report tried, on one 0–100% scale per model. A ring marks the setup the others were measured against; the line from it shows how far each change moved the pass rate.", blocks: [{ type: "shifts" }] });
  if (shared(s => s.gains.some(g => g.delta !== null && g.costChange !== null))) sections.push({ id: "cost-gain", title: "Cost against gain", label: "Cost", lead: "Each point is one change measured against its reference on the same model: up means more runs passed, right means each run cost more.", blocks: [{ type: "cost-gain" }] });
  if (ms.filter(s => s.date).length > 1 || shared(s => !!s.follows)) sections.push({ id: "timeline", title: "How the work unfolded", label: "Timeline", lead: "The reports in the order they ran, with each follow-up linked to the report it followed.", blocks: [{ type: "timeline" }] });
  if (model.pairs.length) sections.push({ id: "matchups", title: "Side by side", label: "Compare", lead: "Pairs worth reading together: the same question on another model, or a follow-up and the report it followed.", blocks: [{ type: "matchups" }] });
  return {
    title: text(data.title) || "Report collection",
    kicker: text(data.kicker) || "Collection",
    summary: data.summary,
    sections,
    footer: text(data.footer) || `${ms.length} reports in one file: every view is drawn from the data embedded here, and every report opens in full.`,
    collection: data,
  };
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
  return {
    title: `${name(sa, a)} and ${name(sb, b)}`,
    kicker: `${text(data.kicker) || "Collection"} · side by side`,
    sections: [{ id: "compare", title: "Side by side", label: "Compare", blocks: [block] }],
    footer: "Both reports open in full from here; every number is drawn from the data embedded in this file.",
    collection: data,
  };
}
