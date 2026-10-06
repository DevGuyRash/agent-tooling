/** Metric-aware views of any comparison: one metric drawn by its kind
 * (metric), alternatives by metrics (scorecard), alternatives minus a baseline
 * or each other (difference), and nested groups with pooled rows and the
 * differences between groups (hierarchy). Each reads ctx.comparison unless the
 * block carries its own `data`. Every statistic comes from comparison-stats;
 * these views only draw what it returns, so nothing here invents a score. */
import { attrs, axisTicks, count, esc, fmtInt, fmtNum, inline, isNum, niceTicks, num, outcomeMark } from "../core";
import type { RenderContext } from "../model";
import type { Alternative, Comparison, ComparisonFilter, Metric, MetricDifference, MetricKind, MetricSummary } from "../comparison-model";
import { difference as differenceOf, groupComparison, groupPath, observationStatus, summarize, summarizeGroups } from "../comparison-stats";
import { placement, Placement } from "../stats";
import { empty, frame, FrameInput, pos } from "./frame";

const KINDS: MetricKind[] = ["binary", "numeric", "ordinal", "count", "rank", "preference"];
/** Kinds whose headline is a share in 0–1. */
const SHARE = new Set<MetricKind>(["binary", "count", "preference"]);
type Center = "mean" | "median";
type Threshold = number | { value: number; label?: string } | null;

/** Fields every view accepts. `cases`, `groups` (an alternative group path
 * prefix, outermost first) and `caseGroups` (the same for cases) narrow what the
 * statistics read; the block names them so the scope stays visible. */
export interface CompareInput extends FrameInput {
  /** The comparison to draw; the report's own comparison when omitted. */
  data?: Comparison;
  /** A metric id; the primary metric, else the first, when omitted. */
  metric?: string;
  /** Alternatives to show, in this order; every alternative when omitted. */
  alternatives?: string[];
  cases?: string[];
  groups?: string[];
  caseGroups?: string[];
  /** The alternative others are read against; the comparison's baseline when omitted. */
  baseline?: string;
}

// ------------------------------------------------------------------ inputs

const strings = (v: unknown): string[] | undefined => Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : typeof v === "string" ? [v] : undefined;
/** Largest and smallest without spreading a long list into arguments. */
const maxOf = (v: number[], start = -Infinity) => { let x = start; for (const y of v) if (isNum(y) && y > x) x = y; return x; };
const minOf = (v: number[], start = Infinity) => { let x = start; for (const y of v) if (isNum(y) && y < x) x = y; return x; };
const iv = (v: unknown): [number, number] | null => Array.isArray(v) && v.length === 2 && isNum(v[0]) && isNum(v[1]) && v[0] <= v[1] ? [v[0], v[1]] : null;
const metricName = (m: Metric) => typeof m.label === "string" && m.label ? m.label : m.id;
const unitOf = (m: Metric) => typeof m.unit === "string" && m.unit ? m.unit : "";
const directed = (m: Metric): "higher" | "lower" | null => m.better === "higher" || m.better === "lower" ? m.better : null;

function listed(names: string[]): string {
  if (!names.length) return "none";
  return names.length > 12 ? `${names.slice(0, 12).join(", ")} and ${names.length - 12} more` : names.join(", ");
}
function problemList(problems: string[]): string {
  return problems.length ? `<ul class="av-cmp-problems" role="note">${[...new Set(problems)].map(p => `<li>${esc(p)}</li>`).join("")}</ul>` : "";
}

interface Source { data: Comparison; metrics: Metric[]; metric: Metric | null; alts: string[]; info: Map<string, Alternative>; filter: ComparisonFilter; baseline?: string; problems: string[] }

/** Every case id the comparison mentions, declared cases first. */
function caseIds(data: Comparison): string[] {
  const out = new Set<string>();
  for (const c of Array.isArray(data.cases) ? data.cases : []) if (c && typeof c.id === "string") out.add(c.id);
  for (const list of [data.observations, data.aggregates, data.preferences, data.rankings])
    for (const x of Array.isArray(list) ? list : []) if (x && typeof (x as { case?: unknown }).case === "string") out.add((x as { case: string }).case);
  return [...out];
}

function resolve(kind: string, input: CompareInput, ctx: RenderContext, needMetric = true): Source | string {
  const own = !!input.data && typeof input.data === "object";
  const raw = own ? input.data : ctx.comparison;
  if (!raw || typeof raw !== "object" || !Array.isArray(raw.alternatives) || !Array.isArray(raw.metrics))
    return frame(kind, input, empty("No comparison to show: give this block “data”, or compose the report from a comparison."));
  const problems: string[] = [];
  const info = new Map<string, Alternative>();
  for (const a of raw.alternatives) if (a && typeof a.id === "string" && !info.has(a.id)) {
    info.set(a.id, a);
    if (own) ctx.arms.add(a.id, { label: typeof a.label === "string" ? a.label : undefined, note: typeof a.note === "string" ? a.note : undefined });
  }
  const known = [...info.keys()];
  const metrics = raw.metrics.filter((m): m is Metric => !!m && typeof m === "object" && typeof m.id === "string");
  for (const m of metrics) if (!KINDS.includes(m.kind)) problems.push(`Metric “${m.id}” has kind “${String(m.kind)}”, which these views cannot draw. Kinds: ${KINDS.join(", ")}.`);
  const usable = metrics.filter(m => KINDS.includes(m.kind));
  let metric: Metric | null = null;
  if (needMetric) {
    const wanted = typeof input.metric === "string" ? input.metric : undefined;
    metric = (wanted ? usable.find(m => m.id === wanted) : usable.find(m => m.primary === true) || usable[0]) || null;
    if (!metric) return frame(kind, input, `${problemList([...problems, wanted ? `No metric “${wanted}” to draw. Metrics: ${listed(usable.map(m => m.id))}.` : "This comparison has no metric these views can draw."])}${empty("Nothing to draw.")}`);
  }
  const pick = strings(input.alternatives);
  if (pick) { const bad = pick.filter(id => !info.has(id)); if (bad.length) problems.push(`Not among the alternatives: ${listed(bad)}. Alternatives: ${listed(known)}.`); }
  const cases = strings(input.cases), groups = strings(input.groups), caseGroups = strings(input.caseGroups);
  const inside = (id: string) => !groups || !groups.length || groups.every((g, i) => groupPath(info.get(id)?.group)[i] === g);
  const alts = (pick ? [...new Set(pick.filter(id => info.has(id)))] : known).filter(inside);
  if (!alts.length) return frame(kind, input, `${problemList(problems)}${empty(groups?.length ? `No alternative sits inside the group ${groups.join(" › ")}.` : "No alternatives to show.")}`);
  if (cases) { const all = caseIds(raw), bad = cases.filter(c => !all.includes(c)); if (bad.length) problems.push(`No observations name these cases: ${listed(bad)}. Cases: ${listed(all)}.`); }
  const filter: ComparisonFilter = {};
  if (cases) filter.cases = cases;
  if (groups && groups.length) filter.groups = groups;
  if (caseGroups && caseGroups.length) filter.caseGroups = caseGroups;
  let baseline = typeof input.baseline === "string" ? input.baseline : typeof raw.baseline === "string" ? raw.baseline : undefined;
  if (baseline && !alts.includes(baseline)) { problems.push(`The baseline “${baseline}” is not among the alternatives shown, so nothing is read against it.`); baseline = undefined; }
  return { data: raw, metrics: usable, metric, alts, info, filter, baseline, problems };
}

function caseName(data: Comparison, ctx: RenderContext, id: string): string {
  const c = (Array.isArray(data.cases) ? data.cases : []).find(x => x && x.id === id);
  return typeof c?.label === "string" && c.label ? c.label : ctx.caseLabels[id] || id;
}

function scopeLine(src: Source, ctx: RenderContext): string {
  const parts: string[] = [];
  if (src.filter.cases) parts.push(`${src.filter.cases.length === 1 ? "case" : "cases"} ${src.filter.cases.map(c => caseName(src.data, ctx, c)).join(", ")}`);
  if (src.filter.groups) parts.push(`alternatives in ${src.filter.groups.join(" › ")}`);
  if (src.filter.caseGroups) parts.push(`cases in ${src.filter.caseGroups.join(" › ")}`);
  return parts.length ? `<p class="av-cmp-scope"><span class="av-eyebrow">Only</span>${esc(parts.join("; "))}</p>` : "";
}

/** Cases each alternative has valid data for on these metrics, when they differ: a pooled
 * value then mixes different cases, so a gap between two alternatives can come from the
 * case mix rather than the alternatives. Only data that names a case is read. */
function coverageLine(src: Source, ctx: RenderContext, metrics: Metric[]): string {
  const caseInfo = new Map<string, string[]>();
  for (const c of Array.isArray(src.data.cases) ? src.data.cases : []) if (c && typeof c.id === "string" && !caseInfo.has(c.id)) caseInfo.set(c.id, groupPath(c.group));
  const okCase = (id: string) => (!src.filter.cases || src.filter.cases.includes(id)) && (!src.filter.caseGroups || src.filter.caseGroups.every((g, i) => (caseInfo.get(id) || [])[i] === g));
  const status = observationStatus(src.data), byGap = new Map<string, string[]>();
  for (const m of metrics) {
    if (m.kind === "preference") continue;
    const seen = new Map<string, Set<string>>();
    const note = (alt: unknown, cs: unknown) => { if (typeof alt !== "string" || typeof cs !== "string" || !src.alts.includes(alt) || !okCase(cs)) return; if (!seen.has(alt)) seen.set(alt, new Set()); seen.get(alt)!.add(cs); };
    (Array.isArray(src.data.observations) ? src.data.observations : []).forEach((o, i) => { if (o && o.metric === m.id && status[i] === null) note(o.alternative, o.case); });
    for (const a of Array.isArray(src.data.aggregates) ? src.data.aggregates : []) if (a && a.metric === m.id) note(a.alternative, a.case);
    if (m.kind === "rank") for (const r of Array.isArray(src.data.rankings) ? src.data.rankings : []) if (r && (r.metric === m.id || r.metric === undefined) && Array.isArray(r.order)) for (const alt of r.order) note(alt, r.case);
    if (seen.size < 2) continue;
    const all = new Set<string>(); for (const set of seen.values()) for (const c of set) all.add(c);
    const gaps = src.alts.filter(a => seen.has(a)).map(a => [a, [...all].filter(c => !seen.get(a)!.has(c))] as const).filter(([, miss]) => miss.length);
    if (!gaps.length) continue;
    const who = gaps.map(([a, miss]) => `${ctx.arms.label(a)} has no data for ${miss.map(c => caseName(src.data, ctx, c)).join(", ")}`).join("; ");
    if (!byGap.has(who)) byGap.set(who, []);
    byGap.get(who)!.push(metricName(m));
  }
  if (!byGap.size) return "";
  const shown = metrics.filter(m => m.kind !== "preference").length;
  const text = [...byGap].map(([who, names]) => `${shown > 1 && names.length < shown ? `On ${names.join(", ")}: ` : ""}${who}.`).join(" ");
  return `<p class="av-cmp-scope av-cmp-coverage"><span class="av-eyebrow">Unequal cases</span><span>${esc(text)} Pooled values then cover different cases, so a gap can come from the case mix; set “cases” to the shared ones to compare like with like.</span></p>`;
}

function thresholdOf(raw: Threshold | undefined, m: Metric): { value: number; label: string } | null {
  if (raw === null) return null;
  if (isNum(raw)) return { value: raw, label: "" };
  if (raw && typeof raw === "object" && isNum(raw.value)) return { value: raw.value, label: typeof raw.label === "string" ? raw.label : "" };
  return isNum(m.threshold) ? { value: m.threshold, label: "" } : null;
}

const bySummary = (list: MetricSummary[]) => {
  const out = new Map<string, MetricSummary>();
  for (const s of Array.isArray(list) ? list : []) if (s && typeof s.alternative === "string" && !out.has(s.alternative)) out.set(s.alternative, s);
  return out;
};

// ------------------------------------------------------------------ numbers in words

/** A share as a percentage with the digits its size needs: 75%, 2.4%, 0.38%. */
export function fmtShare(p: number | null | undefined, round = false): string {
  if (!isNum(p)) return "—";
  const a = Math.abs(p) * 100;
  const text = a === 0 ? "0" : a < 1 ? a.toFixed(2) : a < 10 ? a.toFixed(1) : a.toFixed(0);
  if (round) return `${p < 0 ? "−" : ""}${text.replace(/\.0+$/, "").replace(/(\.\d*?)0+$/, "$1")}%`;
  return `${p < 0 ? "−" : ""}${text}%`;
}
const ordinalWord = (n: number) => { const r = n % 100; return `${fmtInt(n)}${r >= 11 && r <= 13 ? "th" : ["th", "st", "nd", "rd"][n % 10] || "th"}`; };
const sign = (v: number) => v > 1e-12 ? "+" : v < -1e-12 ? "−" : "±";

function fmtValue(m: Metric, v: number | null, unit = true): string {
  if (!isNum(v)) return "—";
  if (SHARE.has(m.kind)) return fmtShare(v);
  return `${fmtNum(v)}${unit && unitOf(m) && m.kind === "numeric" ? ` ${unitOf(m)}` : ""}`;
}
function fmtRange(m: Metric, ci: [number, number]): string {
  return SHARE.has(m.kind) ? `${fmtShare(ci[0])}–${fmtShare(ci[1])}` : `${fmtNum(ci[0])} to ${fmtNum(ci[1])}`;
}
/** A difference in the metric's own terms: rate points, units, positions, or a probability excess. */
function fmtDiff(m: Metric, v: number | null, unit = true): string {
  if (!isNum(v)) return "—";
  const a = Math.abs(v);
  if (a < 1e-12) return unit && SHARE.has(m.kind) ? "0 pts" : "0";
  if (SHARE.has(m.kind)) { const p = a * 100; return `${sign(v)}${p < 1 ? p.toFixed(2) : p < 10 && Math.abs(p - Math.round(p)) > 1e-9 ? p.toFixed(1) : p.toFixed(0)}${unit ? " pts" : ""}`; }
  if (m.kind === "ordinal") return `${sign(v)}${a.toFixed(2)}`;
  return `${sign(v)}${fmtNum(a)}${unit && m.kind === "numeric" && unitOf(m) ? ` ${unitOf(m)}` : unit && m.kind === "rank" ? ` ${a === 1 ? "position" : "positions"}` : ""}`;
}
function diffCaption(m: Metric): string {
  if (SHARE.has(m.kind)) return "difference, points";
  if (m.kind === "ordinal") return "P(higher) − ½";
  if (m.kind === "rank") return "difference, positions";
  return `difference${unitOf(m) ? `, ${unitOf(m)}` : ""}`;
}
function headCaption(m: Metric, center: Center): string {
  return { binary: "share", count: "rate", preference: "win rate", numeric: center, ordinal: "median level", rank: "mean position" }[m.kind];
}

// ------------------------------------------------------------------ headline values

interface Head { v: number | null; ci: [number, number] | null; text: string; ciText: string; detail: string; n: number; invalid: number; level: number | null; ok: boolean }

function levelsOf(m: Metric, s?: MetricSummary): string[] {
  const named = (Array.isArray(s?.levels) ? s!.levels! : Array.isArray(m.levels) ? m.levels : []).map(l => String(l));
  const n = Math.max(named.length, Array.isArray(s?.counts) ? s!.counts!.length : 0);
  return Array.from({ length: n }, (_, i) => named[i] ?? `level ${i + 1}`);
}
function countsOf(m: Metric, s?: MetricSummary): number[] {
  const c = Array.isArray(s?.counts) ? s!.counts!.map(count) : [];
  return levelsOf(m, s).map((_, i) => c[i] || 0);
}
/** The median level, or the two levels it falls between, as indices. */
function medianLevel(c: number[]): [number, number] | null {
  const total = c.reduce((a, b) => a + b, 0);
  if (!total) return null;
  let cum = 0;
  for (let i = 0; i < c.length; i++) {
    cum += c[i];
    if (cum * 2 > total) return [i, i];
    if (cum * 2 === total) { const j = c.findIndex((x, k) => k > i && x > 0); return [i, j < 0 ? i : j]; }
  }
  return null;
}

function head(m: Metric, s: MetricSummary | undefined, center: Center = "mean"): Head {
  const out: Head = { v: null, ci: null, text: "—", ciText: "", detail: "", n: count(s?.n), invalid: count(s?.invalid), level: null, ok: false };
  if (!s) return out;
  const ci = iv(s.interval);
  if (m.kind === "binary" || m.kind === "count") {
    const k = count(s.k), rate = num(s.rate) ?? (out.n && k <= out.n ? k / out.n : null);
    Object.assign(out, { v: rate, ci, detail: `${fmtInt(k)}/${fmtInt(out.n)}` });
  } else if (m.kind === "preference") {
    const w = count(s.wins), l = count(s.losses), t = count(s.ties), rate = num(s.rate) ?? (w + l ? w / (w + l) : null);
    Object.assign(out, { v: rate, ci, detail: `${fmtInt(w)} won · ${fmtInt(l)} lost${t ? ` · ${fmtInt(t)} tied` : ""}` });
  } else if (m.kind === "numeric") {
    const mean = num(s.mean), med = num(s.median);
    Object.assign(out, center === "median"
      ? { v: med, ci: null, detail: `n = ${fmtInt(out.n)}${mean !== null ? ` · mean ${fmtNum(mean)}` : ""}` }
      : { v: mean, ci, detail: `n = ${fmtInt(out.n)}${med !== null ? ` · median ${fmtNum(med)}` : ""}` });
  } else if (m.kind === "rank") {
    const first = num(s.firstShare);
    Object.assign(out, { v: num(s.meanRank), ci, detail: `n = ${fmtInt(out.n)}${first !== null ? ` · 1st in ${fmtShare(first)}` : ""}` });
  } else if (m.kind === "ordinal") {
    const c = countsOf(m, s), levels = levelsOf(m, s), total = c.reduce((a, b) => a + b, 0);
    const given = typeof s.medianLevel === "string" ? levels.indexOf(s.medianLevel) : -1;
    const mid: [number, number] | null = given >= 0 ? [given, given] : medianLevel(c);
    out.n = Math.max(out.n, total);
    out.level = mid ? (mid[0] + mid[1]) / 2 : null;
    out.text = mid ? (mid[0] === mid[1] ? levels[mid[0]] : `${levels[mid[0]]}–${levels[mid[1]]}`) : "—";
    out.detail = `n = ${fmtInt(out.n)}`;
    out.ok = !!mid;
    return out;
  }
  out.text = fmtValue(m, out.v);
  out.ciText = out.ci ? fmtRange(m, out.ci) : "";
  out.ok = out.v !== null;
  return out;
}

/** Sort key for "sort": "value": best first when the metric has a direction, otherwise largest first (ranks: first place first). */
function sortKey(m: Metric, h: Head, s?: MetricSummary): number | null {
  if (m.kind === "ordinal") {
    if (h.level === null) return null;
    const c = countsOf(m, s), total = c.reduce((a, b) => a + b, 0) || 1, upper = c.reduce((a, x, i) => a + (i > (c.length - 1) / 2 ? x : 0), 0) / total;
    return h.level + upper / 10;
  }
  return h.v;
}
function sortRows(m: Metric, ids: string[], heads: Map<string, Head>, sums: Map<string, MetricSummary>): string[] {
  const asc = m.better === "lower" || (m.kind === "rank" && m.better !== "higher");
  return ids.slice().sort((a, b) => {
    const x = sortKey(m, heads.get(a)!, sums.get(a)), y = sortKey(m, heads.get(b)!, sums.get(b));
    if (x === null || y === null) return x === null ? (y === null ? 0 : 1) : -1;
    return asc ? x - y : y - x;
  });
}

// ------------------------------------------------------------------ scales and tracks

interface Scale { min: number; max: number; ticks: number[]; at(v: number): string; label(v: number): string }

function scaleFor(m: Metric, values: number[], places: number): Scale | null {
  const v = values.filter(isNum);
  let min: number, max: number, ticks: number[], label: (x: number) => string;
  if (SHARE.has(m.kind)) {
    const hi = maxOf(v, 0);
    const cap = m.kind === "preference" ? 1 : [0.01, 0.02, 0.05, 0.1, 0.2, 0.25, 0.5, 1].find(c => c >= hi - 1e-9) ?? Math.max(1, hi);
    min = 0; max = cap; ticks = axisTicks(0, cap, 4); label = x => fmtShare(x, true);
  } else if (m.kind === "rank") {
    // Positions run from first to the last any ordering used; an interval past them is clipped, not given room.
    max = Math.max(2, places || Math.ceil(maxOf(v, 1)));
    min = 1;
    ticks = max <= 10 ? Array.from({ length: max }, (_, i) => i + 1) : [1, ...niceTicks(1, max, 4).filter(t => t > 1 && t < max && Number.isInteger(t)), max];
    label = ordinalWord;
  } else if (m.kind === "numeric") {
    if (!v.length) return null;
    ticks = axisTicks(minOf(v), maxOf(v), 4);
    if (ticks.length < 2) return null;
    min = ticks[0]; max = ticks[ticks.length - 1]; label = fmtNum;
  } else return null;
  const span = max - min || 1;
  return { min, max, ticks, at: x => pos((x - min) / span), label };
}

function axis(sc: Scale | null, m: Metric, caption: string, cls = "av-cmp-axis"): string {
  const better = directed(m);
  const hint = better ? `<span class="av-cmp-better">${better} is better</span>` : "";
  const ticks = m.kind === "ordinal"
    ? `<span style="--x:0%">← lower levels</span><span style="--x:50%">|</span><span style="--x:100%">higher levels →</span>`
    : sc ? sc.ticks.map(t => `<span style="--x:${sc.at(t)}">${esc(sc.label(t))}</span>`).join("") : "";
  return `<div class="${cls}" role="row" aria-hidden="true"><span class="av-cmp-axis-cap">${esc(caption)}</span><div class="av-cmp-ticks">${ticks}</div><span class="av-cmp-axis-end">${hint}</span></div>`;
}

interface Ref { value: number; kind: "rule" | "base" | "parent" | "even" }

function refLines(refs: Ref[], sc: Scale): string {
  return refs.filter(r => isNum(r.value) && r.value >= sc.min - 1e-9 && r.value <= sc.max + 1e-9).map(r => `<span class="av-cmp-ref av-cmp-ref--${r.kind}" style="--x:${sc.at(r.value)}"></span>`).join("");
}

/** Up to `max` values spread evenly over the sorted list, so a long series still draws its shape. */
function thin(values: number[], max = 240): number[] {
  const v = values.filter(isNum).sort((a, b) => a - b);
  if (v.length <= max) return v;
  return Array.from({ length: max }, (_, i) => v[Math.round(i * (v.length - 1) / (max - 1))]);
}

/** Positions a rank axis needs: every alternative, and any position an ordering used. */
function rankPlaces(m: Metric, alts: string[], sums: Map<string, MetricSummary>): number {
  if (m.kind !== "rank") return alts.length;
  return Math.max(alts.length, Math.ceil(maxOf(alts.flatMap(id => Array.isArray(sums.get(id)?.values) ? sums.get(id)!.values! : []), 0)));
}
function rankCounts(s: MetricSummary | undefined, places: number): number[] {
  const out = Array.from({ length: places }, () => 0);
  for (const x of Array.isArray(s?.values) ? s!.values! : []) if (isNum(x) && Number.isInteger(x) && x >= 1 && x <= places) out[x - 1]++;
  return out;
}

function trackAria(m: Metric, who: string, h: Head, center: Center = "mean"): string {
  if (!h.ok) return `${who}: ${h.n ? "no value" : "no valid observations"}${h.invalid ? `, ${h.invalid} invalid` : ""}`;
  return `${who}: ${headCaption(m, center)} ${h.text}${h.ciText ? `, 95% interval ${h.ciText}` : ""}${h.detail ? `, ${h.detail}` : ""}${h.invalid ? `, ${h.invalid} invalid` : ""}`;
}

interface TrackOpts { color: string; refs: Ref[]; aria: string; mini?: boolean; dots?: boolean; places?: number; center?: Center }

function track(m: Metric, s: MetricSummary | undefined, h: Head, sc: Scale | null, o: TrackOpts): string {
  if (m.kind === "ordinal") return likert(m, s, o.aria, !!o.mini);
  const cls = `av-cmp-track${o.mini ? " av-cmp-track--mini" : ""}`;
  if (!sc || !h.ok) return `<div class="${cls} av-cmp-track--empty" role="img" aria-label="${esc(o.aria)}"><span class="av-cmp-none">${h.n || h.invalid ? (o.mini ? "invalid" : "no valid value") : (o.mini ? "none" : "no observations")}</span></div>`;
  const style = `--c:${o.color};--p:${sc.at(h.v!)};${h.ci ? `--lo:${sc.at(h.ci[0])};--hi:${sc.at(h.ci[1])};` : ""}`;
  let marks = "";
  if (m.kind === "numeric" && o.dots !== false && s) {
    const vals = thin(Array.isArray(s.values) ? s.values : []);
    marks += vals.map((x, i) => `<span class="av-cmp-dot" style="--x:${sc.at(x)};--y:${(18 + ((i * 0.6180339887) % 1) * 64).toFixed(1)}%"></span>`).join("");
    const med = num(s.median);
    if (med !== null && o.center !== "median") marks += `<span class="av-cmp-med" style="--x:${sc.at(med)}"></span>`;
    else if (o.center === "median" && num(s.mean) !== null) marks += `<span class="av-cmp-med av-cmp-med--mean" style="--x:${sc.at(num(s.mean)!)}"></span>`;
  }
  if (m.kind === "rank" && s && o.places) {
    const c = rankCounts(s, o.places), total = c.reduce((a, b) => a + b, 0);
    if (total) marks += c.map((k, i) => k ? `<span class="av-cmp-bub" style="--x:${sc.at(i + 1)};--s:${(k / total).toFixed(3)}" title="${esc(`${ordinalWord(i + 1)} in ${k} of ${total}`)}"></span>` : "").join("");
  }
  return `<div class="${cls}" role="img" aria-label="${esc(o.aria)}" style="${style}">${refLines(o.refs, sc)}${marks}${h.ci ? '<span class="av-ci"></span>' : ""}<span class="av-pt"></span></div>`;
}

/** Ordinal levels as one diverging bar: lower levels left of the centre line,
 * higher levels right, an odd middle level split across it. Tones carry a
 * direction only when the metric has one. */
function likert(m: Metric, s: MetricSummary | undefined, aria: string, mini: boolean): string {
  const c = countsOf(m, s), levels = levelsOf(m, s), total = c.reduce((a, b) => a + b, 0);
  const cls = `av-cmp-lk${mini ? " av-cmp-lk--mini" : ""}`;
  if (!total) return `<div class="${cls} av-cmp-track--empty" role="img" aria-label="${esc(aria)}"><span class="av-cmp-none">no observations</span></div>`;
  const L = c.length, mid = (L - 1) / 2, better = directed(m);
  const lowTone = better === "higher" ? "var(--av-fail)" : better === "lower" ? "var(--av-pass)" : "var(--av-ink-3)";
  const highTone = better === "higher" ? "var(--av-pass)" : better === "lower" ? "var(--av-fail)" : "var(--av-accent)";
  const left = c.reduce((a, x, i) => a + (i < mid ? x : i === mid ? x / 2 : 0), 0) / total;
  const segs = c.map((k, i) => {
    const share = k / total, d = L > 1 ? Math.abs(i - mid) / mid : 0;
    const tone = i === mid ? "var(--av-line-strong)" : `color-mix(in srgb, ${i < mid ? lowTone : highTone} ${Math.round(28 + 62 * d)}%, var(--av-surface))`;
    return share > 0 ? `<span class="av-cmp-lk-seg${d > 0.6 ? " av-cmp-lk-seg--deep" : ""}" style="--w:${pos(share / 2)};--lc:${tone}" title="${esc(`${levels[i]}: ${k} (${fmtShare(share)})`)}">${!mini && share >= 0.16 ? fmtInt(k) : ""}</span>` : "";
  }).join("");
  const label = `${aria}. ${levels.map((l, i) => `${l} ${c[i]}`).join(", ")}`;
  return `<div class="${cls}" role="img" aria-label="${esc(label)}"><span class="av-cmp-lk-mid"></span><span class="av-cmp-lk-bar"><span class="av-cmp-lk-gap" style="--w:${pos(0.5 - left / 2)}"></span>${segs}</span></div>`;
}

function likertLegend(m: Metric, levels: string[]): string {
  const L = levels.length;
  if (!L) return "";
  const mid = (L - 1) / 2, better = directed(m);
  const lowTone = better === "higher" ? "var(--av-fail)" : better === "lower" ? "var(--av-pass)" : "var(--av-ink-3)";
  const highTone = better === "higher" ? "var(--av-pass)" : better === "lower" ? "var(--av-fail)" : "var(--av-accent)";
  return levels.map((l, i) => {
    const d = L > 1 ? Math.abs(i - mid) / mid : 0;
    const tone = i === mid ? "var(--av-line-strong)" : `color-mix(in srgb, ${i < mid ? lowTone : highTone} ${Math.round(28 + 62 * d)}%, var(--av-surface))`;
    return `<span><span class="av-cmp-lk-key" style="--lc:${tone}"></span>${esc(l)}</span>`;
  }).join("");
}

// ------------------------------------------------------------------ row parts

function chips(h: Head, s: MetricSummary | undefined, extra = ""): string {
  const out = [
    h.invalid ? `<span class="av-chip av-chip--invalid" title="Observations without a valid value are left out and counted here, never as failures">${outcomeMark("invalid")}${fmtInt(h.invalid)} invalid</span>` : "",
    s?.fromAggregate ? '<span class="av-chip" title="Drawn from supplied totals rather than individual observations">reported totals</span>' : "",
    extra,
  ].join("");
  return out ? `<span class="av-cmp-chips">${out}</span>` : "";
}

/** Fewer than five observations: the n is marked, not repeated in a chip. */
const few = (h: Head) => h.ok && h.n > 0 && h.n < 5;
const FEW = ' title="Fewer than five observations: a very rough value"';
function numbers(h: Head, s: MetricSummary | undefined, extra = ""): string {
  return `<div class="av-cmp-num" role="cell"><span class="av-cmp-v${h.ok ? "" : " av-cmp-v--none"}">${esc(h.text)}</span>${h.ciText ? `<span class="av-ci-text">${esc(h.ciText)}</span>` : ""}${h.detail ? `<span class="av-cmp-n${few(h) ? " av-cmp-few" : ""}"${few(h) ? FEW : ""}>${esc(h.detail)}</span>` : ""}${chips(h, s, extra)}</div>`;
}

/** Better or worse than the baseline: only for a metric with a direction, and
 * only when the interval for the difference excludes zero. */
interface Tone { tone: "better" | "worse"; up: boolean; text: string }
function toneAgainst(src: Source, m: Metric, id: string): Tone | null {
  const better = directed(m);
  if (!better || !src.baseline || id === src.baseline) return null;
  const d = differenceOf(src.data, m.id, id, src.baseline, src.filter), ci = iv(d?.interval), est = num(d?.estimate);
  if (!ci || est === null) return null;
  const place = placement(ci, 0);
  if (place === "spans") return null;
  const up = place === "above", good = up === (better === "higher");
  return { tone: good ? "better" : "worse", up, text: `${fmtDiff(m, est)} against the baseline, 95% interval ${fmtDiff(m, ci[0])} to ${fmtDiff(m, ci[1])}${typeof d.method === "string" && d.method ? ` (${d.method})` : ""}` };
}
const toneChip = (t: Tone | null) => t ? `<span class="av-chip av-cmp-tone av-cmp-tone--${t.tone}" title="${esc(t.text)}"><span aria-hidden="true">${t.up ? "▲" : "▼"}</span> ${t.tone} than baseline</span>` : "";

function row(label: string, cell: string, nums: string, attr: Record<string, string | number | undefined>, cls = ""): string {
  return `<div class="av-cmp-row${cls}" role="row"${attrs(attr)}><div class="av-cmp-label" role="rowheader">${label}</div><div class="av-cmp-cell" role="cell">${cell}</div>${nums}</div>`;
}

function legendFor(m: Metric, opts: { threshold?: { value: number; label: string } | null; baseline?: boolean; parent?: boolean; center?: Center; levels?: string[] }): string {
  const items: string[] = [];
  if (m.kind === "ordinal") items.push(likertLegend(m, opts.levels || levelsOf(m)));
  else {
    items.push(`<span><span class="av-legend-pt"></span>${esc({ binary: "share of yes", count: "rate: successes over trials", preference: "win rate over decisive judgments", numeric: opts.center === "median" ? "median" : "mean", rank: "mean position (1 is first)" }[m.kind] || "")}</span>`);
    if (!(m.kind === "numeric" && opts.center === "median")) items.push(`<span><span class="av-legend-ci"></span>95% interval</span>`);
    if (m.kind === "numeric") items.push(`<span><span class="av-cmp-key-dot"></span>each observation</span><span><span class="av-legend-median"></span>${opts.center === "median" ? "mean" : "median"}</span>`);
    if (m.kind === "rank") items.push(`<span><span class="av-cmp-key-bub"></span>share placed at each position</span>`);
    if (m.kind === "preference") items.push(`<span><span class="av-cmp-key-ref av-cmp-key-ref--even"></span>50%: even</span>`);
  }
  if (opts.baseline) items.push(`<span><span class="av-cmp-key-ref av-cmp-key-ref--base"></span>baseline</span>`);
  if (opts.parent) items.push(`<span><span class="av-cmp-key-ref av-cmp-key-ref--parent"></span>the group's pooled value</span>`);
  if (opts.threshold && m.kind !== "ordinal") items.push(`<span><span class="av-cmp-key-ref av-cmp-key-ref--rule"></span>${esc(opts.threshold.label || `threshold ${fmtValue(m, opts.threshold.value)}`)}</span>`);
  return `<p class="av-legend av-cmp-legend">${items.join("")}</p>`;
}

const KIND_METHOD: Record<MetricKind, string> = {
  binary: "Each value is the share of valid observations that were yes.",
  count: "Each value is successes over trials, pooled over the observations shown.",
  numeric: "Dots are the individual valid observations; the large point is their mean with its interval, and the tick is the median.",
  ordinal: "Each bar splits the valid observations by level: lower levels extend left of the centre line, higher levels right, and a middle level straddles it. The median level is named beside it; no level is turned into a score.",
  rank: "Each point is the mean position (1 is first) with its interval; circles show how often the alternative was placed at each position.",
  preference: "Each value is wins over decisive head-to-head judgments, counting every pair inside a ranking; ties and unreached judgments are counted, not scored.",
};

/** The interval methods the statistics reported, in their own words. */
const methodsOf = (list: Array<MetricSummary | undefined>) => [...new Set(list.map(s => s?.intervalMethod).filter((x): x is string => typeof x === "string" && !!x))];
const methodList = (methods: string[]) => methods.length ? `<p>Intervals: ${methods.length === 1 ? esc(methods[0]) : ""}</p>${methods.length > 1 ? `<ul>${methods.map(x => `<li>${esc(x)}</li>`).join("")}</ul>` : ""}` : "";

function methodNote(m: Metric, methods: string[], extra = ""): string {
  return `<details class="av-cmp-method"><summary>How these values are computed</summary><p>${esc(KIND_METHOD[m.kind])} Observations without a valid value are left out and counted beside each row, never treated as failures.${extra ? ` ${esc(extra)}` : ""}</p>${methodList(methods)}</details>`;
}

function metricMeta(m: Metric, level = true): string {
  const parts = [m.kind === "count" ? "rate" : m.kind, unitOf(m) && m.kind === "numeric" ? unitOf(m) : "", directed(m) ? `${directed(m)} is better` : "", level && isNum(m.threshold) && m.kind !== "ordinal" ? `threshold ${fmtValue(m, m.threshold)}` : ""].filter(Boolean);
  return parts.join(" · ");
}

// ------------------------------------------------------------------ metric

export interface MetricInput extends CompareInput {
  /** "case" adds one small panel per case under the pooled rows; "group" nests the rows under their groups, each with its pooled row. */
  by?: "alternative" | "case" | "group";
  /** With by "group": group levels to nest (default 1, the outermost). */
  depth?: number;
  sort?: "identity" | "value";
  /** A line drawn across every row, in the metric's units (a share for binary and count); null hides the metric's own. */
  threshold?: Threshold;
  /** For numeric metrics: the headline is the mean (default, with its interval) or the median. */
  center?: Center;
  method?: boolean;
}

function metricHeading(m: Metric, aside = "", level = true): string {
  const meta = metricMeta(m, level);
  const desc = typeof m.description === "string" && m.description ? `<p class="av-cmp-mdesc">${inline(m.description)}</p>` : "";
  return `<p class="av-cmp-mhead"><strong>${esc(metricName(m))}</strong>${meta || aside ? `<span class="av-cmp-mmeta">${esc([meta, aside].filter(Boolean).join(" · "))}</span>` : ""}</p>${desc}`;
}

export function metric(input: MetricInput, ctx: RenderContext): string {
  const src = resolve("metric", input, ctx);
  if (typeof src === "string") return src;
  const m = src.metric!, center: Center = input.center === "median" ? "median" : "mean";
  const thr = m.kind === "ordinal" ? null : thresholdOf(input.threshold, m);
  if (input.by === "group") {
    const depth = isNum(input.depth) && input.depth >= 1 ? Math.floor(input.depth) : 1;
    const view = groupedView(src, m, ctx, { maxDepth: depth, between: false, center, thr, title: input.title });
    return frame("metric", input, `${problemList(src.problems)}${metricHeading(m)}${view.legend}${scopeLine(src, ctx)}${coverageLine(src, ctx, [m])}${view.flat}${view.grid}${input.method === false ? "" : methodNote(m, view.methods, "A group's row pools every observation of its members as one, so members with more observations weigh more.")}`, { "data-kind": m.kind, "data-by": "group" });
  }
  const sums = bySummary(summarize(src.data, m.id, src.filter));
  const heads = new Map(src.alts.map(id => [id, head(m, sums.get(id), center)]));
  const order = input.sort === "value" ? sortRows(m, src.alts, heads, sums) : src.alts;
  const places = rankPlaces(m, src.alts, sums);
  const all = [...heads.values()].flatMap(h => [h.v, ...(h.ci || [])]).filter(isNum);
  const extra = [...(thr ? [thr.value] : []), ...(m.kind === "numeric" ? src.alts.flatMap(id => (sums.get(id)?.values || []).filter(isNum)) : [])];

  // By case: the same scale holds every panel and the pooled rows.
  const byCase = input.by === "case";
  // Data that names no case counts in the pooled rows and in no case panel; say so,
  // and draw no panels when none of this metric's data names a case.
  const own = m.kind === "rank" || m.kind === "preference" ? [] : [...(Array.isArray(src.data.observations) ? src.data.observations : []), ...(Array.isArray(src.data.aggregates) ? src.data.aggregates : [])]
    .filter(x => x && x.metric === m.id && typeof x.alternative === "string" && src.alts.includes(x.alternative));
  const caseless = own.filter(x => typeof x.case !== "string" || !x.case).length;
  // When none of it names a case, the empty-view notice below says so.
  const caseNote = byCase && caseless && caseless < own.length ? `<p class="av-cmp-scope"><span class="av-eyebrow">No case</span>${esc(`${fmtInt(caseless)} of ${fmtInt(own.length)} entries for ${metricName(m)} name no case; they count in the rows above and in no panel below.`)}</p>` : "";
  const cases = byCase && !(caseless && caseless === own.length) ? (src.filter.cases || caseIds(src.data)) : [];
  const panels = cases.map(c => {
    const ss = bySummary(summarize(src.data, m.id, { ...src.filter, cases: [c] }));
    return { c, ss, hs: new Map(src.alts.map(id => [id, head(m, ss.get(id), center)])) };
  });
  for (const p of panels) for (const h of p.hs.values()) all.push(...[h.v, ...(h.ci || [])].filter(isNum));
  const sc = scaleFor(m, [...all, ...extra], places);

  const base = src.baseline ? heads.get(src.baseline) : undefined;
  const refs: Ref[] = [
    ...(thr ? [{ value: thr.value, kind: "rule" as const }] : []),
    ...(base?.ok && base.v !== null && m.kind !== "ordinal" ? [{ value: base.v, kind: "base" as const }] : []),
    ...(m.kind === "preference" ? [{ value: 0.5, kind: "even" as const }] : []),
  ];
  const rows = order.map(id => {
    const s = sums.get(id), h = heads.get(id)!, who = ctx.arms.label(id), isBase = id === src.baseline, note = ctx.arms.note(id);
    const label = `${ctx.arms.tag(id)}${note ? `<span class="av-cmp-note">${esc(note)}</span>` : ""}${isBase ? '<span class="av-chip av-chip--base">baseline</span>' : ""}`;
    return row(label, track(m, s, h, sc, { color: ctx.arms.color(id), refs, aria: trackAria(m, who, h, center), places, center }), numbers(h, s, toneChip(toneAgainst(src, m, id))), { "data-arm": id }, isBase ? " av-cmp-row--base" : "");
  }).join("");

  const multiples = panels.length ? `<div class="av-cmp-multiples-head"><span class="av-eyebrow">By case</span><span>${esc(`${metricName(m)} in each case, on the same scale`)}</span></div><div class="av-cmp-multiples" role="list">${panels.map(p => {
    const c = (Array.isArray(src.data.cases) ? src.data.cases : []).find(x => x && x.id === p.c);
    const path = groupPath(c?.group), name = caseName(src.data, ctx, p.c);
    const lines = order.map(id => {
      const h = p.hs.get(id)!, s = p.ss.get(id), who = ctx.arms.label(id);
      return `<div class="av-cmp-mini" data-arm="${esc(id)}">${ctx.arms.glyph(id)}<span class="av-cmp-mini-name" title="${esc(who)}">${esc(who)}</span>${track(m, s, h, sc, { color: ctx.arms.color(id), refs: refs.filter(r => r.kind !== "base"), aria: `${name}, ${trackAria(m, who, h, center)}`, mini: true, places, center, dots: false })}<span class="av-cmp-mini-v${h.ok ? "" : " av-cmp-v--none"}">${esc(h.text)}${h.invalid ? `<span class="av-cmp-mini-inv" title="${esc(`${h.invalid} invalid, left out`)}">${outcomeMark("invalid")}</span>` : ""}</span></div>`;
    }).join("");
    return `<figure class="av-cmp-panel" role="listitem"><figcaption>${path.length ? `<span class="av-cmp-panel-group">${esc(path.join(" › "))}</span>` : ""}<span class="av-cmp-panel-name">${esc(name)}</span></figcaption>${lines}</figure>`;
  }).join("")}</div>` : byCase ? empty("No observation names a case, so there is nothing to show by case.") : "";

  const levels = m.kind === "ordinal" ? levelsOf(m, [...sums.values()][0]) : undefined;
  const grid = `<div class="av-cmp-grid" role="table" aria-label="${esc(input.title || metricName(m))}">${axis(sc, m, headCaption(m, center))}${rows}</div>`;
  const methods = methodsOf([...sums.values()]);
  return frame("metric", input, `${problemList(src.problems)}${metricHeading(m)}${legendFor(m, { threshold: thr, baseline: refs.some(r => r.kind === "base"), center, levels })}${scopeLine(src, ctx)}${coverageLine(src, ctx, [m])}${grid}${caseNote}${multiples}${input.method === false ? "" : methodNote(m, methods, directed(m) && src.baseline ? "“Better” or “worse than baseline” appears only where the 95% interval for the difference from the baseline excludes zero." : "")}`, { "data-kind": m.kind });
}

// ------------------------------------------------------------------ scorecard

export interface ScorecardInput extends CompareInput {
  /** Metric ids to show, in order; every metric (the primary first) when omitted. */
  metrics?: string[];
  /** "columns" puts alternatives across the top; "rows" down the side. Columns up to eight alternatives by default. */
  orient?: "columns" | "rows";
  center?: Center;
}

interface TreeNode { path: string[]; items: Array<{ alt: string } | { node: TreeNode }>; members: string[] }

/** Alternatives nested by their group paths, in first-appearance order. */
function treeOf(alts: string[], info: Map<string, Alternative>, maxDepth = Infinity): TreeNode {
  const root: TreeNode = { path: [], items: [], members: [] };
  const index = new Map<string, TreeNode>([["[]", root]]);
  for (const id of alts) {
    const p = groupPath(info.get(id)?.group).slice(0, maxDepth);
    let node = root;
    root.members.push(id);
    for (let d = 0; d < p.length; d++) {
      const path = p.slice(0, d + 1), key = JSON.stringify(path);
      let child = index.get(key);
      if (!child) { child = { path, items: [], members: [] }; index.set(key, child); node.items.push({ node: child }); }
      child.members.push(id);
      node = child;
    }
    node.items.push({ alt: id });
  }
  return root;
}
const flatten = (n: TreeNode): string[] => n.items.flatMap(it => "alt" in it ? [it.alt] : flatten(it.node));
const groupName = (s: string) => s === "" ? "(unnamed group)" : s;

export function scorecard(input: ScorecardInput, ctx: RenderContext): string {
  const src = resolve("scorecard", input, ctx, false);
  if (typeof src === "string") return src;
  const center: Center = input.center === "median" ? "median" : "mean";
  const pick = strings(input.metrics);
  if (pick) { const bad = pick.filter(id => !src.metrics.some(m => m.id === id)); if (bad.length) src.problems.push(`No metric named ${listed(bad)}. Metrics: ${listed(src.metrics.map(m => m.id))}.`); }
  const metrics = pick ? [...new Set(pick)].map(id => src.metrics.find(m => m.id === id)).filter((m): m is Metric => !!m) : [...src.metrics.filter(m => m.primary === true), ...src.metrics.filter(m => m.primary !== true)];
  if (!metrics.length) return frame("scorecard", input, `${problemList(src.problems)}${empty("No metric to show.")}`);
  const tree = treeOf(src.alts, src.info), alts = flatten(tree);
  const paths = new Map(alts.map(id => [id, groupPath(src.info.get(id)?.group)]));
  const depth = Math.max(0, ...[...paths.values()].map(p => p.length));
  const cols = input.orient === "rows" || input.orient === "columns" ? input.orient : alts.length > 8 ? "rows" : "columns";
  const grid = metrics.map(m => {
    const sums = bySummary(summarize(src.data, m.id, src.filter));
    return { m, cells: new Map(alts.map(id => [id, { s: sums.get(id), h: head(m, sums.get(id), center), t: toneAgainst(src, m, id) }])) };
  });
  let toned = false;

  const metricHead = (m: Metric, scope: "row" | "col") => {
    const meta = metricMeta(m);
    return `<th scope="${scope}" class="av-sc-metric"${attrs({ title: typeof m.description === "string" ? m.description : undefined })}><span class="av-sc-mname">${esc(metricName(m))}</span>${m.primary === true ? '<span class="av-chip av-chip--req">primary</span>' : ""}<span class="av-sc-mmeta">${esc(`${headCaption(m, center)}${meta ? ` · ${meta}` : ""}`)}</span></th>`;
  };
  const altHead = (id: string, scope: "row" | "col") => `<th scope="${scope}" class="av-sc-alt${id === src.baseline ? " av-sc-alt--base" : ""}" data-arm="${esc(id)}">${ctx.arms.tag(id)}${id === src.baseline ? '<span class="av-chip av-chip--base">baseline</span>' : ""}</th>`;
  const cell = (m: Metric, id: string, c: { s?: MetricSummary; h: Head; t: Tone | null }) => {
    const base = id === src.baseline ? " av-sc-cell--base" : "";
    if (!c.s || (!c.h.ok && !c.h.n && !c.h.invalid)) return `<td class="av-sc-cell av-sc-cell--missing${base}"><span class="av-missing">missing</span></td>`;
    if (!c.h.ok) return `<td class="av-sc-cell av-sc-cell--missing${base}"><span class="av-missing">no valid value</span>${chips(c.h, c.s)}</td>`;
    if (c.t) toned = true;
    const tone = c.t ? `<span class="av-sc-tone" title="${esc(c.t.text)}"><span aria-hidden="true">${c.t.up ? "▲" : "▼"}</span><span class="av-sr">${esc(`${c.t.tone} than the baseline`)}</span></span>` : "";
    const mini = m.kind === "ordinal" ? likert(m, c.s, `${ctx.arms.label(id)}, ${metricName(m)}`, true) : "";
    return `<td class="av-sc-cell${base}"${c.t ? ` data-tone="${c.t.tone}"` : ""}><span class="av-sc-v">${esc(c.h.text)}${tone}</span>${c.h.ciText ? `<span class="av-sc-ci">${esc(c.h.ciText)}</span>` : ""}${mini}<span class="av-sc-n${few(c.h) ? " av-cmp-few" : ""}"${few(c.h) ? FEW : ""}>${esc(c.h.detail)}</span>${chips(c.h, c.s)}</td>`;
  };

  let table: string;
  if (cols === "columns") {
    const groupRows = Array.from({ length: depth }, (_, L) => {
      const runs: Array<{ key: string; label: string | null; span: number }> = [];
      for (const id of alts) {
        const p = paths.get(id)!, key = p.length > L ? JSON.stringify(p.slice(0, L + 1)) : "";
        const last = runs[runs.length - 1];
        if (last && last.key === key) last.span++;
        else runs.push({ key, label: p.length > L ? p[L] : null, span: 1 });
      }
      return `<tr class="av-sc-grouprow"><td class="av-sc-corner"></td>${runs.map(r => r.label !== null ? `<th scope="colgroup" colspan="${r.span}" class="av-sc-group" style="--depth:${L}">${esc(groupName(r.label))}</th>` : `<td colspan="${r.span}"></td>`).join("")}</tr>`;
    }).join("");
    table = `<thead>${groupRows}<tr><td class="av-sc-corner"><span class="av-eyebrow">Metric</span></td>${alts.map(id => altHead(id, "col")).join("")}</tr></thead><tbody>${grid.map(g => `<tr>${metricHead(g.m, "row")}${alts.map(id => cell(g.m, id, g.cells.get(id)!)).join("")}</tr>`).join("")}</tbody>`;
  } else {
    let last = "";
    const body = alts.map(id => {
      const p = paths.get(id)!, key = JSON.stringify(p);
      const group = key !== last && p.length ? `<tr class="av-sc-grouprow"><th scope="rowgroup" colspan="${metrics.length + 1}" class="av-sc-group">${esc(p.map(groupName).join(" › "))}</th></tr>` : "";
      last = key;
      return `${group}<tr>${altHead(id, "row")}${grid.map(g => cell(g.m, id, g.cells.get(id)!)).join("")}</tr>`;
    }).join("");
    table = `<thead><tr><td class="av-sc-corner"><span class="av-eyebrow">Alternative</span></td>${metrics.map(m => metricHead(m, "col")).join("")}</tr></thead><tbody>${body}</tbody>`;
  }
  const legend = `<p class="av-legend av-cmp-legend"><span><span class="av-sc-key">75%</span>headline value</span><span><span class="av-sc-key av-sc-key--ci">60–85%</span>95% interval</span><span><span class="av-sc-key av-sc-key--n">n</span>observations behind it</span>${src.baseline ? '<span><span class="av-chip av-chip--base">baseline</span>what tints are read against</span>' : ""}${toned ? '<span><span class="av-sc-key av-sc-key--better">▲</span><span class="av-sc-key av-sc-key--worse">▼</span>better or worse than the baseline: the 95% interval for the difference excludes zero, on a metric with a direction</span>' : ""}<span><span class="av-missing">missing</span>no observations</span></p>`;
  return frame("scorecard", input, `${problemList(src.problems)}${legend}${scopeLine(src, ctx)}${coverageLine(src, ctx, metrics)}<div class="av-scroll-x av-sc-wrap" tabindex="0" role="region" aria-label="${esc(input.title || "Scorecard")}"><table class="av-sc av-sc--${cols}">${table}</table></div>`, { "data-orient": cols });
}

// ------------------------------------------------------------------ difference

export interface DifferenceInput extends CompareInput {
  /** Several metrics, one panel each; the single `metric` (or the primary) when omitted. */
  metrics?: string[];
  /** "baseline": each alternative minus the baseline (default when there is one); "all": every pair, later minus earlier; or explicit [a, b] pairs, a minus b. */
  pairs?: "baseline" | "all" | string[][];
  /** A difference worth acting on, in the difference's units (a share for rates: 0.05 is 5 points). Used when one metric is shown. */
  threshold?: Threshold;
  /** Alternatives given identical material; the comparison's own when omitted, false to hide. */
  identical?: string[][] | false;
  sort?: "identity" | "difference";
  /** For numeric metrics: compare means (default) or medians. */
  center?: Center;
  method?: boolean;
}

interface DRow { a: string; b: string; method: string; est: number | null; ci: [number, number] | null; noise: boolean }

function phrase(m: Metric, up: boolean, center: Center): string {
  const name = metricName(m);
  if (m.kind === "ordinal") return `${up ? "higher" : "lower"} levels of ${name}`;
  if (m.kind === "rank") return `${up ? "a later" : "an earlier"} average position on ${name}`;
  if (m.kind === "numeric" && center === "median") return `${up ? "a higher" : "a lower"} median ${name}`;
  return `${up ? "a higher" : "a lower"} ${name}`;
}

function diffScale(values: number[]): { M: number; at(v: number): string; ticks: number[] } {
  const extent = maxOf(values.map(Math.abs), 0);
  const t = axisTicks(0, extent > 0 ? extent * 1.04 : 1, 2);
  const M = t.length > 1 ? t[t.length - 1] : extent || 1;
  return { M, at: v => pos((v + M) / (2 * M)), ticks: [-M, -M / 2, 0, M / 2, M] };
}

function differencePanel(src: Source, m: Metric, input: DifferenceInput, ctx: RenderContext, single: boolean): string {
  const center: Center = input.center === "median" && m.kind === "numeric" ? "median" : "mean";
  const sums = bySummary(summarize(src.data, m.id, src.filter));
  const raw = input.identical === false ? [] : Array.isArray(input.identical) ? input.identical : Array.isArray(src.data.identical) ? src.data.identical : [];
  const groups = raw.map(g => (strings(g) || []).filter(id => src.alts.includes(id))).filter(g => g.length > 1);
  const same = (x: string, y: string) => groups.some(g => g.includes(x) && g.includes(y));
  const explicit = Array.isArray(input.pairs) ? input.pairs : null;
  const mode = explicit ? "pairs" : input.pairs === "all" || !src.baseline ? "all" : "baseline";
  const make = (a: string, b: string, noise: boolean): DRow => {
    const d = differenceOf(src.data, m.id, a, b, src.filter);
    const part = center === "median" && d?.median ? d.median : d;
    return { a, b, method: typeof part?.method === "string" ? part.method : "", est: num(part?.estimate), ci: iv(part?.interval), noise };
  };
  const rows: DRow[] = [];
  if (explicit) {
    for (const p of explicit) {
      const pair = strings(p) || [];
      if (pair.length !== 2 || !src.alts.includes(pair[0]) || !src.alts.includes(pair[1]) || pair[0] === pair[1]) { src.problems.push(`A pair names two different alternatives shown, first minus second; this one does not: ${JSON.stringify(p)}.`); continue; }
      rows.push(make(pair[0], pair[1], false));
    }
  } else if (mode === "baseline") { for (const id of src.alts) if (id !== src.baseline && !same(id, src.baseline!)) rows.push(make(id, src.baseline!, false)); }
  else for (let i = 0; i < src.alts.length; i++) for (let j = i + 1; j < src.alts.length; j++) if (!same(src.alts[i], src.alts[j])) rows.push(make(src.alts[j], src.alts[i], false));
  const noise: DRow[] = groups.flatMap(g => g.flatMap((x, i) => g.slice(i + 1).map(y => make(y, x, true))));
  if (input.sort === "difference") rows.sort((x, y) => (y.est ?? -Infinity) - (x.est ?? -Infinity));
  if (!rows.length && !noise.length) return `<div class="av-cmp-dpanel">${metricHeading(m)}${empty("Nothing to compare on this metric.")}</div>`;

  const thr = single ? thresholdOf(input.threshold ?? null, { ...m, threshold: undefined }) : null;
  const gaps = noise.map(r => r.est).filter(isNum).map(Math.abs);
  const band = gaps.length ? Math.max(...gaps) : null;
  const sc = diffScale([...[...rows, ...noise].flatMap(r => [r.est, ...(r.ci || [])]), ...(thr ? [thr.value] : []), ...(band !== null ? [band] : [])].filter(isNum));
  const better = directed(m), name = metricName(m);

  const side = (id: string) => {
    const s = sums.get(id), h = head(m, s, center);
    return `<span class="av-cmp-side">${ctx.arms.tag(id, { id: false })}<span class="av-cmp-side-v">${esc(h.ok ? `${h.text}${h.detail && SHARE.has(m.kind) ? ` · ${h.detail}` : ""}` : "no value")}</span>${h.invalid ? `<span class="av-chip av-chip--invalid" title="${esc(`${ctx.arms.label(id)}: invalid observations are left out, never counted as failures`)}">${outcomeMark("invalid")}${fmtInt(h.invalid)} invalid</span>` : ""}</span>`;
  };
  const reading = (r: DRow): string => {
    const A = esc(ctx.arms.label(r.a)), B = esc(ctx.arms.label(r.b));
    if (!r.ci || r.est === null) return `<strong>No interval.</strong> ${esc(r.method || "The observations do not allow one.")}`;
    if (r.noise) return Math.abs(r.est) < 1e-9 ? "<strong>Identical material.</strong> These copies came out the same this time." : `<strong>Identical material,</strong> so this gap of ${esc(fmtDiff(m, Math.abs(r.est)).replace(/^\+/, ""))} is chance alone.`;
    const place: Placement = placement(r.ci, 0);
    let out = place === "spans" ? `<strong>The 95% interval includes zero:</strong> these observations cannot tell ${A} and ${B} apart on ${esc(name)}.`
      : `<strong>The 95% interval lies ${place} zero:</strong> these observations fit only ${esc(phrase(m, place === "above", center))} for ${A} than for ${B}.`;
    if (better && place !== "spans") out += (place === "above") === (better === "higher") ? " That is the better direction for this metric." : " That is the worse direction for this metric.";
    if (thr) {
      const t = placement(r.ci, thr.value), what = esc(thr.label || `the ${fmtDiff(m, thr.value)} threshold`);
      out += " " + (t === "above" ? `All of it is above ${what}.` : t === "below" ? `All of it is below ${what}.` : `The interval reaches across ${what}.`);
    }
    return out;
  };
  const rowHtml = (r: DRow): string => {
    const place = r.ci ? placement(r.ci, 0) : null;
    const style = `--c:${r.noise ? "var(--av-warn)" : ctx.arms.color(r.a)};--z:${sc.at(0)};${r.est !== null && r.ci ? `--p:${sc.at(r.est)};--lo:${sc.at(r.ci[0])};--hi:${sc.at(r.ci[1])};` : ""}${thr && !r.noise ? `--t:${sc.at(thr.value)};` : ""}${band !== null && !r.noise ? `--b0:${sc.at(-band)};--b1:${sc.at(band)};` : ""}`;
    const aria = `${ctx.arms.label(r.a)} minus ${ctx.arms.label(r.b)}: ${r.ci && r.est !== null ? `${fmtDiff(m, r.est)}, 95% interval ${fmtDiff(m, r.ci[0])} to ${fmtDiff(m, r.ci[1])}` : "no interval"}`;
    const trackHtml = `<div class="av-cmp-dtrack${r.ci ? "" : " av-cmp-track--empty"}" role="img" aria-label="${esc(aria)}" style="${style}">${band !== null && !r.noise && r.ci ? '<span class="av-cmp-band"></span>' : ""}<span class="av-cmp-zero"></span>${thr && !r.noise ? '<span class="av-cmp-thr"></span>' : ""}${r.ci && r.est !== null ? '<span class="av-ci"></span><span class="av-pt"></span>' : '<span class="av-cmp-none">no interval</span>'}</div>`;
    const nums = `<div class="av-cmp-num">${r.ci && r.est !== null ? `<span class="av-cmp-v">${esc(fmtDiff(m, r.est))}</span><span class="av-ci-text">${esc(`${fmtDiff(m, r.ci[0], false)} to ${fmtDiff(m, r.ci[1], false)}`)}</span>${place ? `<span class="av-cmp-place av-cmp-place--${place}">${place === "spans" ? "includes 0" : "excludes 0"}</span>` : ""}` : '<span class="av-cmp-v av-cmp-v--none">—</span>'}</div>`;
    return `<li class="av-cmp-drow${r.noise ? " av-cmp-drow--noise" : ""}"${attrs({ "data-place": place || undefined, "data-a": r.a, "data-b": r.b })}><div class="av-cmp-dlabel">${side(r.a)}<span class="av-cmp-minus" aria-hidden="true">minus</span>${side(r.b)}</div><div class="av-cmp-cell">${trackHtml}</div>${nums}<p class="av-cmp-reading">${reading(r)}</p></li>`;
  };
  const ticks = sc.ticks.map(t => `<span style="--x:${sc.at(t)}">${esc(fmtDiff(m, t, false))}</span>`).join("");
  const first = mode === "baseline" ? "the alternative" : "the first";
  const second = mode === "baseline" ? ctx.arms.label(src.baseline!) : "the second";
  const axisHtml = `<div class="av-cmp-daxis" aria-hidden="true"><span class="av-cmp-axis-cap">${esc(diffCaption(m))}</span><div class="av-cmp-ticks">${ticks}</div><span></span></div><div class="av-cmp-ddir" aria-hidden="true"><span></span><div class="av-cmp-ddir-track"><span>← ${esc(second)} higher${better === "lower" ? " (better)" : ""}</span><span>${esc(first)} higher${better === "higher" ? " (better)" : ""} →</span></div><span></span></div>`;
  const methods = [...new Set([...rows, ...noise].map(r => r.method).filter(Boolean))];
  const legend = `<p class="av-legend av-cmp-legend"><span><span class="av-legend-pt"></span>${esc(center === "median" ? "difference in medians: first minus second" : "difference: first minus second")}</span><span><span class="av-legend-ci"></span>95% interval</span><span><span class="av-cmp-key-zero"></span>zero: no difference</span>${thr ? `<span><span class="av-cmp-key-ref av-cmp-key-ref--rule"></span>${esc(thr.label || `threshold ${fmtDiff(m, thr.value)}`)}</span>` : ""}${band !== null ? `<span><span class="av-legend-noise"></span>${esc(`gap between identical alternatives (${fmtDiff(m, band).replace(/^\+/, "")}), either way`)}</span>` : ""}</p>`;
  const main = rows.length ? `<ul class="av-cmp-dlist" aria-label="${esc(`Differences in ${name}`)}">${rows.map(rowHtml).join("")}</ul>` : "";
  const noiseHtml = noise.length ? `<div class="av-cmp-noise" role="group" aria-label="Chance alone"><p class="av-cmp-noise-label"><span class="av-eyebrow">Chance alone</span><span>Alternatives that received identical material. Their gap is what chance produces between copies of the same thing.</span></p><ul class="av-cmp-dlist">${noise.map(rowHtml).join("")}</ul></div>` : "";
  const method = input.method === false ? "" : `<details class="av-cmp-method"><summary>How these differences are computed</summary><p>${esc(`Each row is the first alternative minus the second on ${name}, in ${diffCaption(m).replace(/^difference, /, "")}. Observations without a valid value are left out of both sides and counted beside them, never as failures. The interval covers variation between the observations shown, not cases or people the comparison did not include.`)}</p>${methods.length ? `<ul>${methods.map(x => `<li>${esc(x)}</li>`).join("")}</ul>` : ""}</details>`;
  const aside = mode === "baseline" ? `each alternative minus ${ctx.arms.label(src.baseline!)}` : mode === "all" ? "every pair, later minus earlier" : "the pairs named, first minus second";
  return `<div class="av-cmp-dpanel" data-kind="${m.kind}">${metricHeading(m, aside, false)}${legend}<div class="av-cmp-dgrid">${axisHtml}${main}${noiseHtml}</div>${method}</div>`;
}

export function difference(input: DifferenceInput, ctx: RenderContext): string {
  const src = resolve("difference", input, ctx, false);
  if (typeof src === "string") return src;
  const pick = strings(input.metrics);
  if (pick) { const bad = pick.filter(id => !src.metrics.some(m => m.id === id)); if (bad.length) src.problems.push(`No metric named ${listed(bad)}. Metrics: ${listed(src.metrics.map(m => m.id))}.`); }
  const wanted = typeof input.metric === "string" ? input.metric : undefined;
  if (wanted && !src.metrics.some(m => m.id === wanted)) src.problems.push(`No metric “${wanted}” to draw. Metrics: ${listed(src.metrics.map(m => m.id))}.`);
  const metrics = pick ? [...new Set(pick)].map(id => src.metrics.find(m => m.id === id)).filter((m): m is Metric => !!m)
    : [(wanted ? src.metrics.find(m => m.id === wanted) : src.metrics.find(m => m.primary === true) || src.metrics[0])].filter((m): m is Metric => !!m);
  if (!metrics.length) return frame("difference", input, `${problemList(src.problems)}${empty("No metric to compare on.")}`);
  if (src.alts.length < 2) return frame("difference", input, `${problemList(src.problems)}${empty("A difference needs two alternatives.")}`);
  if (metrics.length > 1 && input.threshold !== undefined && input.threshold !== null) src.problems.push("A threshold is in one metric's units, so it is drawn only when the block shows one metric.");
  const panels = metrics.map(m => differencePanel(src, m, input, ctx, metrics.length === 1)).join("");
  return frame("difference", input, `${problemList(src.problems)}${scopeLine(src, ctx)}${coverageLine(src, ctx, metrics)}${panels}`, metrics.length === 1 ? { "data-kind": metrics[0].kind } : {});
}

// ------------------------------------------------------------------ hierarchy

export interface HierarchyInput extends CompareInput {
  /** Group levels to show; deeper groups fold into their ancestor at this depth. */
  depth?: number;
  /** Differences between sibling groups at each level (default true). */
  between?: boolean;
  center?: Center;
  method?: boolean;
}

interface Gap { a: string; b: string; est: number | null; ci: [number, number] | null; method: string }

/** Alternatives nested under their groups, each group a pooled row from
 * summarizeGroups, and (with `between`) sibling groups differenced through
 * groupComparison, so groups read exactly as alternatives do. */
function groupedView(src: Source, m: Metric, ctx: RenderContext, o: { maxDepth: number; between: boolean; center: Center; thr: { value: number; label: string } | null; title?: string }): { grid: string; legend: string; flat: string; methods: string[] } {
  const { center, thr } = o;
  const tree = treeOf(src.alts, src.info, o.maxDepth);
  const D = Math.max(0, ...src.alts.map(id => Math.min(o.maxDepth, groupPath(src.info.get(id)?.group).length)));
  // Only the alternatives shown are pooled, so a group's row holds exactly the members drawn under it.
  const scope: ComparisonFilter = src.alts.length < src.info.size ? { ...src.filter, alternatives: src.alts } : src.filter;
  const caseScope: ComparisonFilter = { ...(src.filter.cases ? { cases: src.filter.cases } : {}), ...(src.filter.caseGroups ? { caseGroups: src.filter.caseGroups } : {}) };
  const sums = bySummary(summarize(src.data, m.id, src.filter));
  const heads = new Map(src.alts.map(id => [id, head(m, sums.get(id), center)]));
  const pooled = new Map<string, { s: MetricSummary; h: Head }>();
  for (let d = 0; d < D; d++) for (const g of summarizeGroups(src.data, m.id, d, scope) || []) {
    const path = strings(g?.path) || (() => { const first = (strings(g?.members) || []).find(id => src.info.has(id)); return first ? groupPath(src.info.get(first)!.group).slice(0, d + 1) : null; })();
    if (path && !pooled.has(JSON.stringify(path))) pooled.set(JSON.stringify(path), { s: g, h: head(m, g, center) });
  }
  const pooledOf = (n: TreeNode) => pooled.get(JSON.stringify(n.path));

  const gapsOf = new Map<TreeNode, Gap[]>();
  const byDepth = new Map<number, Comparison>();
  const visit = (n: TreeNode) => {
    const kids = n.items.filter((it): it is { node: TreeNode } => "node" in it).map(it => it.node);
    if (o.between && kids.length >= 2) {
      const d = n.path.length;
      if (!byDepth.has(d)) byDepth.set(d, groupComparison(src.data, d, scope));
      const gc = byDepth.get(d)!;
      const pairs: Array<[TreeNode, TreeNode]> = kids.length <= 4 ? kids.flatMap((x, i) => kids.slice(i + 1).map((y): [TreeNode, TreeNode] => [x, y])) : kids.slice(1).map((y): [TreeNode, TreeNode] => [kids[0], y]);
      gapsOf.set(n, pairs.map(([x, y]) => {
        const r = differenceOf(gc, m.id, x.path.join(" › "), y.path.join(" › "), caseScope);
        const part = center === "median" && r?.median ? r.median : r;
        return { a: groupName(x.path[d]), b: groupName(y.path[d]), est: num(part?.estimate), ci: iv(part?.interval), method: typeof part?.method === "string" ? part.method : "" };
      }));
    }
    kids.forEach(visit);
  };
  visit(tree);
  const allGaps = [...gapsOf.values()].flat();
  const ds = diffScale(allGaps.flatMap(g => [g.est, ...(g.ci || [])]).filter(isNum));

  const values = [...heads.values(), ...[...pooled.values()].map(p => p.h)].flatMap(h => [h.v, ...(h.ci || [])]).filter(isNum);
  const extra = m.kind === "numeric" ? src.alts.flatMap(id => (sums.get(id)?.values || []).filter(isNum)) : [];
  const places = rankPlaces(m, src.alts, sums);
  const sc = scaleFor(m, [...values, ...extra, ...(thr ? [thr.value] : [])], places);
  const baseRefs: Ref[] = [...(thr ? [{ value: thr.value, kind: "rule" as const }] : []), ...(m.kind === "preference" ? [{ value: 0.5, kind: "even" as const }] : [])];
  const better = directed(m);

  const gapRow = (g: Gap, depth: number, scopeName: string) => {
    const place = g.ci ? placement(g.ci, 0) : null;
    const tone = place && place !== "spans" && better ? ((place === "above") === (better === "higher") ? "better" : "worse") : "";
    const style = `--c:var(--av-ink-2);--z:${ds.at(0)};${g.ci && g.est !== null ? `--p:${ds.at(g.est)};--lo:${ds.at(g.ci[0])};--hi:${ds.at(g.ci[1])};` : ""}`;
    const aria = `${g.a} minus ${g.b}, ${metricName(m)}: ${g.ci && g.est !== null ? `${fmtDiff(m, g.est)}, 95% interval ${fmtDiff(m, g.ci[0])} to ${fmtDiff(m, g.ci[1])}` : `no interval${g.method ? ` (${g.method})` : ""}`}`;
    const cell = `<div class="av-cmp-dtrack av-cmp-dtrack--mini${g.ci ? "" : " av-cmp-track--empty"}" role="img" aria-label="${esc(aria)}" style="${style}"><span class="av-cmp-zero"></span>${g.ci && g.est !== null ? '<span class="av-ci"></span><span class="av-pt"></span>' : '<span class="av-cmp-none">no interval</span>'}<span class="av-cmp-dend av-cmp-dend--l">${esc(fmtDiff(m, -ds.M, false))}</span><span class="av-cmp-dend av-cmp-dend--r">${esc(fmtDiff(m, ds.M, false))}</span></div>`;
    const nums = `<div class="av-cmp-num" role="cell">${g.ci && g.est !== null ? `<span class="av-cmp-v">${esc(fmtDiff(m, g.est))}</span><span class="av-ci-text">${esc(`${fmtDiff(m, g.ci[0], false)} to ${fmtDiff(m, g.ci[1], false)}`)}</span>` : `<span class="av-cmp-v av-cmp-v--none" title="${esc(g.method)}">—</span>`}${place ? `<span class="av-cmp-place av-cmp-place--${place}${tone ? ` av-cmp-place--${tone}` : ""}">${place === "spans" ? "includes 0" : `excludes 0${tone ? ` · ${tone}` : ""}`}</span>` : ""}</div>`;
    const label = `<span class="av-eyebrow">${esc(`Between ${scopeName}`)}</span><span class="av-cmp-gap-name">${esc(g.a)} <span class="av-cmp-minus">minus</span> ${esc(g.b)}</span>`;
    return row(label, cell, nums, { style: `--depth:${depth}` }, ` av-cmp-row--gap${place ? ` av-cmp-row--${place}` : ""}`);
  };
  const render = (n: TreeNode, depth: number): string => {
    let out = (gapsOf.get(n) || []).map(g => gapRow(g, depth, n.path.length ? groupName(n.path[n.path.length - 1]) : "top-level groups")).join("");
    const parent = n.path.length ? pooledOf(n) : undefined;
    for (const it of n.items) {
      if ("alt" in it) {
        const id = it.alt, s = sums.get(id), h = heads.get(id)!;
        const refs = [...baseRefs, ...(parent?.h.ok && parent.h.v !== null && m.kind !== "ordinal" ? [{ value: parent.h.v, kind: "parent" as const }] : [])];
        out += row(ctx.arms.tag(id), track(m, s, h, sc, { color: ctx.arms.color(id), refs, aria: trackAria(m, ctx.arms.label(id), h, center), places, center }), numbers(h, s), { "data-arm": id, style: `--depth:${depth}` }, " av-cmp-row--alt");
      } else {
        const g = it.node, p = pooledOf(g), h = p?.h || head(m, undefined), name = groupName(g.path[g.path.length - 1]);
        const subgroups = g.items.filter(x => "node" in x).length;
        const label = `<span class="av-cmp-gname">${esc(name)}</span><span class="av-cmp-gmeta">${esc(`${g.members.length} ${g.members.length === 1 ? "alternative" : "alternatives"}${subgroups ? ` in ${subgroups} ${subgroups === 1 ? "group" : "groups"}` : ""}, pooled`)}</span>`;
        out += `${row(label, track(m, p?.s, h, sc, { color: "var(--av-ink-2)", refs: baseRefs, aria: trackAria(m, `${name} (pooled)`, h, center), places, center, dots: false }), numbers(h, p?.s), { "data-group": JSON.stringify(g.path), style: `--depth:${depth}` }, " av-cmp-row--group")}${render(g, depth + 1)}`;
      }
    }
    return out;
  };
  const flat = D === 0 ? `<p class="av-cmp-scope"><span class="av-eyebrow">No groups</span>No alternative names a group, so every alternative sits at one level. Give alternatives a “group” path, outermost first, to nest them.</p>` : "";
  const levels = m.kind === "ordinal" ? levelsOf(m, [...sums.values()][0]) : undefined;
  const legend = `${legendFor(m, { threshold: thr, parent: D > 0 && m.kind !== "ordinal", center, levels })}${D > 0 ? `<p class="av-legend av-cmp-legend av-cmp-legend--rows"><span><span class="av-cmp-key-group"></span>a group, pooled over its members</span>${allGaps.length ? `<span><span class="av-cmp-key-zero"></span>“Between” rows: one group minus another, on their own scale centred on zero</span>` : ""}</p>` : ""}`;
  const methods = [...methodsOf([...sums.values(), ...[...pooled.values()].map(p => p.s)]), ...new Set(allGaps.map(g => g.method).filter(Boolean))];
  const grid = `<div class="av-cmp-grid av-cmp-grid--tree" role="table" aria-label="${esc(o.title || `${metricName(m)} by group`)}">${axis(sc, m, headCaption(m, center))}${render(tree, 0)}</div>`;
  return { grid, legend, flat, methods };
}

export function hierarchy(input: HierarchyInput, ctx: RenderContext): string {
  const src = resolve("hierarchy", input, ctx);
  if (typeof src === "string") return src;
  const m = src.metric!, center: Center = input.center === "median" ? "median" : "mean";
  const maxDepth = isNum(input.depth) && input.depth >= 1 ? Math.floor(input.depth) : Infinity;
  const view = groupedView(src, m, ctx, { maxDepth, between: input.between !== false, center, thr: m.kind === "ordinal" ? null : thresholdOf(undefined, m), title: input.title });
  const note = `A group's row pools every observation of its members as one, so members with more observations weigh more. A row that starts “Between” is one group minus another: each group's observations are pooled and compared as two alternatives${m.kind === "preference" || m.kind === "rank" ? ", and judgments between two members of the same group are set aside" : ""}.`;
  return frame("hierarchy", input, `${problemList(src.problems)}${metricHeading(m)}${view.legend}${scopeLine(src, ctx)}${coverageLine(src, ctx, [m])}${view.flat}${view.grid}${input.method === false ? "" : methodNote(m, view.methods, note)}`, { "data-kind": m.kind });
}
