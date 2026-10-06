/** Summaries and differences for every metric kind, for any comparison.
 *
 * Methods, each checked against a published worked example in tests/engine.cjs:
 * - binary and count: the rate k/n with a 95% Wilson score interval (Wilson 1927;
 *   Newcombe 1998a), and differences with Newcombe's hybrid score interval
 *   (Newcombe 1998b, method 10; src/stats.ts).
 * - numeric: mean, median and sample standard deviation, a 95% Student t interval
 *   for the mean, the mean difference with Welch's interval and the
 *   Welch–Satterthwaite degrees of freedom (Welch 1947), and the median
 *   difference with a seeded percentile bootstrap (Efron & Tibshirani 1993).
 * - ordinal: counts per level and the median level; the difference is
 *   P(a > b) + ½P(tie) − ½, Vargha and Delaney's A (2000) centred on zero (half
 *   of Cliff's delta), with a seeded percentile bootstrap. Level indices are
 *   never averaged.
 * - rank: mean rank, median rank and first-place share; differences in mean rank
 *   pair the two alternatives within each ranking or case when they can
 *   (paired t), and use Welch's interval otherwise.
 * - preference: wins, losses and ties from head-to-head judgments and from every
 *   pair inside a ranking, with a Wilson interval on wins over decisive
 *   judgments; a difference is the net head-to-head share (a's wins − b's wins)
 *   ÷ decisive judgments between them, 2p − 1 of a's Wilson interval.
 * Invalid observations and unreached judgments are counted apart, by reason, and
 * never enter a rate as failures. Summaries come from observations when an
 * alternative has any on that metric, and from supplied aggregates otherwise. */
import type { Aggregate, Comparison, ComparisonFilter, Metric, MetricDifference, MetricKind, MetricSummary, Observation, Preference, Ranking } from "./comparison-model";
import { isNum, quantile, wilson } from "./core";
import { newcombe, validCount, Z95 } from "./stats";

type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => !!v && typeof v === "object" && !Array.isArray(v);
const KINDS: MetricKind[] = ["binary", "numeric", "ordinal", "count", "rank", "preference"];
const BOOT = 2000;
/** Numeric text, as both checkers read it: an optional minus, digits with an optional point, an optional exponent. */
const NUMERIC_TEXT = /^\s*-?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?\s*$/;

/** The group path of an alternative or case, normalized to an array. */
export function groupPath(group: string[] | string | undefined): string[] {
  return Array.isArray(group) ? group.map(String) : typeof group === "string" && group ? [group] : [];
}

function items<T>(v: unknown): T[] { return Array.isArray(v) ? v.filter(isObj) as unknown as T[] : []; }
const startsWith = (path: string[], prefix: string[]) => prefix.every((p, i) => path[i] === p);

/** The metric with this id, when the comparison defines it. */
export function metricOf(data: Comparison, id: string): Metric | undefined {
  return items<Metric>(data?.metrics).find(m => m.id === id);
}
const kindOf = (m: Metric | undefined): MetricKind | undefined => m && KINDS.includes(m.kind) ? m.kind : undefined;

/** Alternative ids in the comparison's order. */
export function alternativeIds(data: Comparison): string[] {
  return [...new Set(items<{ id: unknown }>(data?.alternatives).map(a => a.id).filter((id): id is string => typeof id === "string"))];
}

function altFilter(data: Comparison, filter: ComparisonFilter): (id: unknown) => id is string {
  const only = Array.isArray(filter.alternatives) ? new Set(filter.alternatives.map(String)) : null;
  const prefix = Array.isArray(filter.groups) && filter.groups.length ? filter.groups.map(String) : null;
  const paths = new Map(items<{ id: unknown; group?: string[] | string }>(data?.alternatives).filter(a => typeof a.id === "string").map(a => [a.id as string, groupPath(a.group)]));
  return (id: unknown): id is string => typeof id === "string" && (!only || only.has(id)) && (!prefix || startsWith(paths.get(id) || [], prefix));
}
function caseFilter(data: Comparison, filter: ComparisonFilter): (c: unknown) => boolean {
  const only = Array.isArray(filter.cases) ? new Set(filter.cases.map(String)) : null;
  const prefix = Array.isArray(filter.caseGroups) && filter.caseGroups.length ? filter.caseGroups.map(String) : null;
  const inGroup = prefix ? new Set(items<{ id: unknown; group?: string[] | string }>(data?.cases).filter(c => typeof c.id === "string" && startsWith(groupPath(c.group), prefix)).map(c => c.id as string)) : null;
  if (!only && !inGroup) return () => true;
  return c => typeof c === "string" && (!only || only.has(c)) && (!inGroup || inGroup.has(c));
}

/** The preference or rank metric that judgments naming no metric belong to:
 * the only metric of that kind, else the primary one of that kind. */
export function judgmentMetric(data: Comparison, kind: "preference" | "rank"): string | undefined {
  const of = items<Metric>(data?.metrics).filter(m => m.kind === kind && typeof m.id === "string");
  return of.length === 1 ? of[0].id : of.find(m => m.primary === true)?.id;
}
function belongs(data: Comparison, named: unknown, metric: string | undefined): boolean {
  const own = typeof named === "string" && named ? named : undefined;
  if (metric === undefined) return own === undefined;
  if (own !== undefined) return own === metric;
  const kind = kindOf(metricOf(data, metric));
  return (kind === "preference" || kind === "rank") && judgmentMetric(data, kind) === metric;
}

// ------------------------------------------------------------------ distributions

/** ln Γ(x) for x > 0 (Lanczos, g = 7, nine coefficients). */
function lnGamma(x: number): number {
  const c = [0.99999999999980993, 676.5203681218851, -1259.1392167224028, 771.32342877765313, -176.61502916214059, 12.507343278686905, -0.13857109526572012, 9.9843695780195716e-6, 1.5056327351493116e-7];
  if (x < 0.5) return Math.log(Math.PI / Math.sin(Math.PI * x)) - lnGamma(1 - x);
  x -= 1;
  let a = c[0];
  const t = x + 7.5;
  for (let i = 1; i < 9; i++) a += c[i] / (x + i);
  return 0.5 * Math.log(2 * Math.PI) + (x + 0.5) * Math.log(t) - t + Math.log(a);
}
/** The continued fraction for the incomplete beta function (modified Lentz). */
function betaFraction(a: number, b: number, x: number): number {
  const tiny = 1e-300;
  let c = 1, d = 1 - (a + b) * x / (a + 1);
  if (Math.abs(d) < tiny) d = tiny;
  d = 1 / d;
  let h = d;
  for (let m = 1; m <= 300; m++) {
    const m2 = 2 * m;
    let aa = m * (b - m) * x / ((a + m2 - 1) * (a + m2));
    d = 1 + aa * d; if (Math.abs(d) < tiny) d = tiny; c = 1 + aa / c; if (Math.abs(c) < tiny) c = tiny; d = 1 / d; h *= d * c;
    aa = -(a + m) * (a + b + m) * x / ((a + m2) * (a + m2 + 1));
    d = 1 + aa * d; if (Math.abs(d) < tiny) d = tiny; c = 1 + aa / c; if (Math.abs(c) < tiny) c = tiny; d = 1 / d;
    const del = d * c; h *= del;
    if (Math.abs(del - 1) < 1e-15) break;
  }
  return h;
}
/** The regularized incomplete beta function I_x(a, b). */
function incompleteBeta(x: number, a: number, b: number): number {
  if (x <= 0) return 0;
  if (x >= 1) return 1;
  const front = Math.exp(lnGamma(a + b) - lnGamma(a) - lnGamma(b) + a * Math.log(x) + b * Math.log(1 - x));
  return x < (a + 1) / (a + b + 2) ? front * betaFraction(a, b, x) / a : 1 - front * betaFraction(b, a, 1 - x) / b;
}
/** Student's t distribution function with df degrees of freedom (df may be fractional). */
export function tCdf(t: number, df: number): number {
  const tail = 0.5 * incompleteBeta(df / (df + t * t), df / 2, 0.5);
  return t >= 0 ? 1 - tail : tail;
}
/** The p quantile of Student's t (p above one half), by bisection; the normal quantile beyond 10⁵ df. */
export function tQuantile(p: number, df: number): number | null {
  if (!isNum(p) || !isNum(df) || df <= 0 || p <= 0.5 || p >= 1) return null;
  if (df > 1e5 && Math.abs(p - 0.975) < 1e-12) return Z95;
  let lo = 0, hi = 2;
  while (tCdf(hi, df) < p && hi < 1e12) hi *= 2;
  for (let i = 0; i < 200 && hi - lo > 1e-13 * Math.max(1, hi); i++) { const mid = (lo + hi) / 2; if (tCdf(mid, df) < p) lo = mid; else hi = mid; }
  return (lo + hi) / 2;
}

/** A 95% Student t interval for a mean from its sample size and standard deviation. */
export function tInterval(mean: number, sd: number, n: number): [number, number] | null {
  if (!isNum(mean) || !isNum(sd) || !isNum(n) || n < 2 || sd < 0) return null;
  const t = tQuantile(0.975, n - 1);
  if (t === null) return null;
  const half = t * sd / Math.sqrt(n);
  return [mean - half, mean + half];
}
/** Welch's 95% interval for m1 − m2 with Welch–Satterthwaite degrees of freedom; null without spread or with n < 2. */
export function welch(m1: number, s1: number, n1: number, m2: number, s2: number, n2: number): { estimate: number; interval: [number, number] | null; df: number | null } {
  const estimate = m1 - m2;
  if (![s1, s2, n1, n2].every(isNum) || n1 < 2 || n2 < 2) return { estimate, interval: null, df: null };
  const v1 = s1 * s1 / n1, v2 = s2 * s2 / n2, se = Math.sqrt(v1 + v2);
  if (!(se > 0)) return { estimate, interval: null, df: null };
  const df = (v1 + v2) ** 2 / (v1 * v1 / (n1 - 1) + v2 * v2 / (n2 - 1));
  const t = tQuantile(0.975, df);
  return { estimate, interval: t === null ? null : [estimate - t * se, estimate + t * se], df };
}

function meanOf(v: number[]): number | null { return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null; }
function sdOf(v: number[]): number | null {
  if (v.length < 2) return null;
  const m = meanOf(v)!;
  return Math.sqrt(v.reduce((a, x) => a + (x - m) ** 2, 0) / (v.length - 1));
}
function medianOf(v: number[]): number | null { return quantile(v.slice().sort((a, b) => a - b), 0.5); }

/** P(x > y) + ½P(x = y) − ½ over every pair: Vargha–Delaney A centred on zero, in [−½, ½]. */
export function superiority(xs: number[], ys: number[]): number | null {
  if (!xs.length || !ys.length) return null;
  const sorted = ys.slice().sort((a, b) => a - b);
  const below = (v: number) => { let lo = 0, hi = sorted.length; while (lo < hi) { const m = (lo + hi) >> 1; if (sorted[m] < v) lo = m + 1; else hi = m; } return lo; };
  const atOrBelow = (v: number) => { let lo = 0, hi = sorted.length; while (lo < hi) { const m = (lo + hi) >> 1; if (sorted[m] <= v) lo = m + 1; else hi = m; } return lo; };
  let score = 0;
  for (const x of xs) { const lt = below(x), le = atOrBelow(x); score += lt + 0.5 * (le - lt); }
  return score / (xs.length * ys.length) - 0.5;
}

/** A 32-bit FNV-1a digest, the seed of a bootstrap. */
function seedOf(text: string): number {
  let h = 0x811c9dc5;
  for (let i = 0; i < text.length; i++) { h ^= text.charCodeAt(i); h = Math.imul(h, 0x01000193) >>> 0; }
  return h;
}
/** mulberry32: a small, fast, deterministic generator in [0, 1). */
function generator(seed: number): () => number {
  let s = seed >>> 0;
  return () => {
    s = (s + 0x6d2b79f5) >>> 0;
    let t = s;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
/** A 95% percentile bootstrap interval for stat(x, y), resampling each side with
 * replacement B times from a seed, so the same data always give the same interval. */
export function bootstrap(xs: number[], ys: number[], stat: (x: number[], y: number[]) => number | null, seed: string, B = BOOT): [number, number] | null {
  if (!xs.length || !ys.length) return null;
  const random = generator(seedOf(seed));
  const draw = (v: number[]) => { const out = new Array<number>(v.length); for (let i = 0; i < v.length; i++) out[i] = v[Math.floor(random() * v.length)]; return out; };
  const stats: number[] = [];
  for (let b = 0; b < B; b++) { const s = stat(draw(xs), draw(ys)); if (isNum(s)) stats.push(s); }
  if (stats.length < B / 2) return null;
  stats.sort((a, b) => a - b);
  return [quantile(stats, 0.025)!, quantile(stats, 0.975)!];
}

// ------------------------------------------------------------------ reading values

interface Read { valid: Map<string, number[]>; keyed: Map<string, Map<string, number[]>>; trials: Map<string, [number, number]>; invalid: Map<string, Map<string, number>>; seen: Set<string>; order: string[] }
function reader(): Read { return { valid: new Map(), keyed: new Map(), trials: new Map(), invalid: new Map(), seen: new Set(), order: [] }; }
function touch(r: Read, alt: string): void { if (!r.seen.has(alt)) { r.seen.add(alt); r.order.push(alt); } }
function bad(r: Read, alt: string, reason: string): void {
  touch(r, alt);
  const m = r.invalid.get(alt) || new Map<string, number>();
  m.set(reason, (m.get(reason) || 0) + 1);
  r.invalid.set(alt, m);
}
function good(r: Read, alt: string, value: number, key?: string): void {
  touch(r, alt);
  (r.valid.get(alt) || r.valid.set(alt, []).get(alt)!).push(value);
  if (key !== undefined) {
    const k = r.keyed.get(alt) || r.keyed.set(alt, new Map()).get(alt)!;
    (k.get(key) || k.set(key, []).get(key)!).push(value);
  }
}

/** Ordinal levels: the metric's own, else numeric values in order. Text values without levels have no known order. */
export function ordinalLevels(data: Comparison, metric: Metric): string[] {
  if (Array.isArray(metric.levels) && metric.levels.length) return metric.levels.map(String);
  const found = new Set<number>();
  for (const o of items<Observation>(data?.observations)) {
    if (o.metric !== metric.id || o.valid === false || o.value === null || o.value === undefined) continue;
    if (isNum(o.value)) found.add(o.value);
    else if (typeof o.value === "string" && NUMERIC_TEXT.test(o.value)) found.add(Number(o.value));
    else if (o.value !== "") return [];
  }
  for (const a of items<Aggregate>(data?.aggregates)) {
    if (a.metric !== metric.id || !isObj(a.counts)) continue;
    for (const k of Object.keys(a.counts)) { if (NUMERIC_TEXT.test(k)) found.add(Number(k)); else return []; }
  }
  return [...found].sort((a, b) => a - b).map(String);
}
function levelIndex(levels: string[], value: unknown, explicit: boolean): number | null {
  if (typeof value === "string" || isNum(value)) {
    const i = levels.indexOf(String(value));
    if (i >= 0) return i;
  }
  if (!explicit && typeof value === "string" && NUMERIC_TEXT.test(value)) { const i = levels.indexOf(String(Number(value))); if (i >= 0) return i; }
  if (explicit && isNum(value) && Number.isInteger(value) && value >= 0 && value < levels.length) return value;
  return null;
}

/** One observation read by its metric's kind: a number (0/1 for binary, a level
 * index for ordinal, a position for rank), [successes, trials] for count, or the
 * reason it has no valid value. */
function classify(o: Observation, kind: MetricKind | undefined, levels: string[], explicit: boolean): number | [number, number] | string {
  if (o.valid === false) return typeof o.invalid_reason === "string" && o.invalid_reason ? o.invalid_reason : "marked invalid";
  const v = o.value;
  if (v === null || v === undefined || v === "") return "no value";
  if (kind === "binary") return typeof v === "boolean" ? (v ? 1 : 0) : v === 0 || v === 1 ? v : "not true or false";
  if (kind === "count") {
    if (!isNum(v) || !Number.isInteger(v) || v < 0) return "count is not a whole number";
    if (!isNum(o.n) || !Number.isInteger(o.n) || o.n <= 0) return "count has no trials (n)";
    return v > o.n ? "more successes than trials" : [v, o.n];
  }
  if (kind === "numeric") return isNum(v) ? v : "not a number";
  if (kind === "rank") return isNum(v) && v >= 1 ? v : "rank is not a position of 1 or more";
  if (kind === "ordinal") { const i = levels.length ? levelIndex(levels, v, explicit) : null; return i === null ? (levels.length ? "not one of the levels" : "the metric names no levels") : i; }
  if (kind === "preference") return "preference metrics read judgments, not observations";
  return "no metric with that id and a known kind";
}

/** Why each observation has no valid value (null when it has one), in the order given:
 * the same reading every summary uses, for ledgers and counts that must agree with them. */
export function observationStatus(data: Comparison): Array<string | null> {
  const levels = new Map<string, string[]>();
  return (Array.isArray(data?.observations) ? data.observations : []).map(o => {
    if (!isObj(o)) return "not an observation";
    const m = typeof o.metric === "string" ? metricOf(data, o.metric) : undefined, kind = kindOf(m);
    if (kind === "ordinal" && !levels.has(m!.id)) levels.set(m!.id, ordinalLevels(data, m!));
    const c = classify(o as Observation, kind, levels.get(m?.id ?? "") || [], !!m && Array.isArray(m.levels) && m.levels.length > 0);
    return typeof c === "string" ? c : null;
  });
}

/** Observations of one metric, read by its kind into numbers per alternative. */
function readObservations(data: Comparison, metric: Metric, filter: ComparisonFilter): Read {
  const r = reader(), okAlt = altFilter(data, filter), okCase = caseFilter(data, filter);
  const kind = kindOf(metric);
  const levels = kind === "ordinal" ? ordinalLevels(data, metric) : [];
  const explicit = Array.isArray(metric.levels) && metric.levels.length > 0;
  for (const o of items<Observation>(data?.observations)) {
    if (o.metric !== metric.id || !okAlt(o.alternative) || !okCase(o.case)) continue;
    const alt = o.alternative, key = o.case !== undefined || o.unit !== undefined ? `${o.case ?? ""}\u0000${o.unit ?? ""}` : undefined;
    const c = classify(o, kind, levels, explicit);
    if (typeof c === "string") bad(r, alt, c);
    else if (Array.isArray(c)) { touch(r, alt); const t = r.trials.get(alt) || [0, 0]; r.trials.set(alt, [t[0] + c[0], t[1] + c[1]]); }
    else good(r, alt, c, key);
  }
  if (kind === "rank") {
    // A ranking places every alternative it lists; in a grouped comparison one group can hold several places.
    items<Ranking>(data?.rankings).forEach((rk, i) => {
      if (!Array.isArray(rk.order) || !belongs(data, rk.metric, metric.id) || !okCase(rk.case)) return;
      rk.order.forEach((id, pos) => { if (okAlt(id)) good(r, id, pos + 1, `\u0001ranking ${i}`); });
    });
  }
  return r;
}

interface Duel { a: string; b: string; winner: string | null; case?: string; valid: boolean; reason?: string }
/** Head-to-head outcomes on one metric (or the overall preference): each judgment, and each pair of places in a ranking. */
function duels(data: Comparison, metric: string | undefined, filter: ComparisonFilter): Duel[] {
  const okAlt = altFilter(data, filter), okCase = caseFilter(data, filter), out: Duel[] = [];
  for (const p of items<Preference>(data?.preferences)) {
    if (!belongs(data, p.metric, metric) || !okCase(p.case) || !okAlt(p.a) || !okAlt(p.b) || p.a === p.b) continue;
    const w = p.winner;
    if (w === p.a || w === p.b || w === "tie") out.push({ a: p.a, b: p.b, winner: w, case: p.case, valid: true });
    else out.push({ a: p.a, b: p.b, winner: null, case: p.case, valid: false, reason: w === null || w === undefined ? "no judgment reached" : "the winner names neither alternative" });
  }
  for (const rk of items<Ranking>(data?.rankings)) {
    if (!Array.isArray(rk.order) || !belongs(data, rk.metric, metric) || !okCase(rk.case)) continue;
    const order = rk.order.filter(okAlt);
    for (let i = 0; i < order.length; i++) for (let j = i + 1; j < order.length; j++)
      if (order[i] !== order[j]) out.push({ a: order[i], b: order[j], winner: order[i], case: rk.case, valid: true });
  }
  return out;
}

// ------------------------------------------------------------------ aggregates

function aggregatesFor(data: Comparison, metric: string, alt: string, filter: ComparisonFilter): Aggregate[] {
  const okCase = caseFilter(data, filter);
  return items<Aggregate>(data?.aggregates).filter(a => a.metric === metric && a.alternative === alt && okCase(a.case));
}
function supplied(list: Aggregate[]): [number, number] | null {
  return list.length === 1 && isNum(list[0].lo) && isNum(list[0].hi) && list[0].lo <= list[0].hi ? [list[0].lo, list[0].hi] : null;
}
/** Pooled n, mean and sd of several numeric summaries (the exact pooled sample statistics). */
export function poolMoments(parts: Array<{ n: number; mean: number; sd?: number | null }>): { n: number; mean: number | null; sd: number | null } {
  const ok = parts.filter(p => isNum(p.n) && p.n > 0 && isNum(p.mean));
  const n = ok.reduce((a, p) => a + p.n, 0);
  if (!n) return { n: 0, mean: null, sd: null };
  const mean = ok.reduce((a, p) => a + p.n * p.mean, 0) / n;
  if (n < 2 || ok.some(p => !(isNum(p.sd) || p.n === 1))) return { n, mean, sd: null };
  const ss = ok.reduce((a, p) => a + (p.n - 1) * (isNum(p.sd) ? p.sd : 0) ** 2 + p.n * (p.mean - mean) ** 2, 0);
  return { n, mean, sd: Math.sqrt(ss / (n - 1)) };
}

// ------------------------------------------------------------------ summaries

const WILSON = "95% Wilson score interval";
const reasons = (m: Map<string, number> | undefined) => m && m.size ? Object.fromEntries(m) : undefined;
const total = (m: Map<string, number> | undefined) => m ? [...m.values()].reduce((a, b) => a + b, 0) : 0;

function summaryFrom(data: Comparison, metric: Metric, alt: string, r: Read, filter: ComparisonFilter, levels: string[], judged?: { wins: number; losses: number; ties: number; invalid: Map<string, number> }): MetricSummary {
  const kind = kindOf(metric)!;
  const base: MetricSummary = { alternative: alt, metric: metric.id, kind, n: 0, invalid: total(r.invalid.get(alt)) };
  const why = reasons(r.invalid.get(alt));
  if (why) base.invalidReasons = why;
  const fromObs = r.seen.has(alt);
  const aggs = fromObs ? [] : aggregatesFor(data, metric.id, alt, filter);
  if (kind === "binary" || kind === "count") {
    let k = 0, n = 0;
    if (fromObs) {
      if (kind === "binary") { const v = r.valid.get(alt) || []; n = v.length; k = v.filter(x => x === 1).length; }
      else [k, n] = r.trials.get(alt) || [0, 0];
    } else for (const a of aggs) if (validCount(a.k, a.n) && Number.isInteger(a.k) && Number.isInteger(a.n)) { k += a.k!; n += a.n!; }
    const given = fromObs ? null : supplied(aggs);
    return { ...base, k, n, rate: n ? k / n : null, interval: given || wilson(k, n, Z95), ...(n ? { intervalMethod: given ? "as reported by the source" : WILSON } : {}), ...(aggs.length && n ? { fromAggregate: true } : {}) };
  }
  if (kind === "numeric") {
    if (fromObs) {
      const v = r.valid.get(alt) || [], m = meanOf(v), sd = sdOf(v);
      return { ...base, n: v.length, mean: m, median: medianOf(v), sd, interval: m !== null && sd !== null ? tInterval(m, sd, v.length) : null, ...(v.length >= 2 ? { intervalMethod: "95% Student t interval for the mean" } : {}), values: v };
    }
    const parts = aggs.filter(a => isNum(a.mean)).map(a => ({ n: isNum(a.n) && a.n > 0 ? a.n : 0, mean: a.mean!, sd: isNum(a.sd) ? a.sd : null }));
    if (!parts.length) return base;
    const single = parts.length === 1 ? parts[0] : null;
    const pooled = single ? { n: single.n, mean: single.mean, sd: single.sd } : poolMoments(parts);
    const given = supplied(aggs);
    const t = pooled.mean !== null && pooled.sd !== null ? tInterval(pooled.mean, pooled.sd, pooled.n) : null;
    return {
      ...base, n: pooled.n, mean: pooled.mean, sd: pooled.sd, median: single && isNum(aggs[0].median) ? aggs[0].median : null, fromAggregate: true,
      interval: given || t, ...(given ? { intervalMethod: "as reported by the source" } : t ? { intervalMethod: `95% Student t interval for the mean, from the supplied${single ? "" : ", pooled"} mean, sd and n` } : {}),
    };
  }
  if (kind === "ordinal") {
    const counts = levels.map(() => 0);
    if (fromObs) for (const i of r.valid.get(alt) || []) counts[i]++;
    else for (const a of aggs) if (isObj(a.counts)) for (const [name, c] of Object.entries(a.counts)) {
      const i = levels.indexOf(name);
      if (i >= 0 && isNum(c) && Number.isInteger(c) && c >= 0) counts[i] += c;
    }
    const n = counts.reduce((a, b) => a + b, 0);
    let medianLevel: string | null = null, cum = 0;
    for (let i = 0; i < counts.length && n; i++) { cum += counts[i]; if (cum / n >= 0.5) { medianLevel = levels[i]; break; } }
    return { ...base, n, counts, levels, medianLevel, interval: null, ...(aggs.length && n ? { fromAggregate: true } : {}) };
  }
  if (kind === "rank") {
    if (fromObs) {
      const v = r.valid.get(alt) || [], m = meanOf(v), sd = sdOf(v);
      return { ...base, n: v.length, meanRank: m, median: medianOf(v), sd, firstShare: v.length ? v.filter(x => x === 1).length / v.length : null, interval: m !== null && sd !== null ? tInterval(m, sd, v.length) : null, ...(v.length >= 2 ? { intervalMethod: "95% Student t interval for the mean rank" } : {}), values: v };
    }
    const parts = aggs.filter(a => isNum(a.mean)).map(a => ({ n: isNum(a.n) && a.n > 0 ? a.n : 0, mean: a.mean!, sd: isNum(a.sd) ? a.sd : null }));
    if (!parts.length) return base;
    const pooled = parts.length === 1 ? parts[0] : poolMoments(parts);
    const given = supplied(aggs), t = pooled.mean !== null && pooled.sd !== null ? tInterval(pooled.mean, pooled.sd, pooled.n) : null;
    return { ...base, n: pooled.n, meanRank: pooled.mean, sd: pooled.sd, fromAggregate: true, interval: given || t, ...(given ? { intervalMethod: "as reported by the source" } : t ? { intervalMethod: "95% Student t interval for the mean rank, from the supplied mean, sd and n" } : {}) };
  }
  // preference
  const j = judged || { wins: 0, losses: 0, ties: 0, invalid: new Map<string, number>() };
  const invalid = new Map(r.invalid.get(alt) || []);
  for (const [k, c] of j.invalid) invalid.set(k, (invalid.get(k) || 0) + c);
  let { wins, losses } = j;
  const ties = j.ties;
  let fromAggregate = false;
  if (!wins && !losses && !ties) for (const a of aggregatesFor(data, metric.id, alt, filter)) if (validCount(a.k, a.n) && Number.isInteger(a.k) && Number.isInteger(a.n)) { wins += a.k!; losses += a.n! - a.k!; fromAggregate = true; }
  const decisive = wins + losses;
  return {
    ...base, invalid: total(invalid), ...(invalid.size ? { invalidReasons: Object.fromEntries(invalid) } : {}),
    n: wins + losses + ties, k: wins, wins, losses, ties, rate: decisive ? wins / decisive : null, interval: wilson(wins, decisive, Z95),
    ...(decisive ? { intervalMethod: `${WILSON} on wins over decisive judgments` } : {}), ...(fromAggregate ? { fromAggregate } : {}),
  };
}

function tallies(list: Duel[]): Map<string, { wins: number; losses: number; ties: number; invalid: Map<string, number> }> {
  const out = new Map<string, { wins: number; losses: number; ties: number; invalid: Map<string, number> }>();
  const get = (id: string) => out.get(id) || out.set(id, { wins: 0, losses: 0, ties: 0, invalid: new Map() }).get(id)!;
  for (const d of list) {
    const a = get(d.a), b = get(d.b);
    if (!d.valid) { for (const t of [a, b]) t.invalid.set(d.reason || "invalid", (t.invalid.get(d.reason || "invalid") || 0) + 1); }
    else if (d.winner === "tie") { a.ties++; b.ties++; }
    else if (d.winner === d.a) { a.wins++; b.losses++; }
    else { b.wins++; a.losses++; }
  }
  return out;
}

/** Each alternative's summary on one metric, in the comparison's order; an
 * alternative with nothing recorded still appears, with n = 0. */
export function summarize(data: Comparison, metric: string, filter: ComparisonFilter = {}): MetricSummary[] {
  const m = metricOf(data, metric);
  if (!m || !kindOf(m)) return [];
  const r = readObservations(data, m, filter);
  const okAlt = altFilter(data, filter);
  const levels = m.kind === "ordinal" ? ordinalLevels(data, m) : [];
  const judged = m.kind === "preference" ? tallies(duels(data, m.id, filter)) : undefined;
  const ids = [...new Set([...alternativeIds(data).filter(okAlt), ...r.order, ...(judged ? judged.keys() : [])])];
  return ids.map(id => summaryFrom(data, m, id, r, filter, levels, judged?.get(id)));
}

/** Alternative a minus alternative b on one metric, with a 95% interval suited to its kind. */
export function difference(data: Comparison, metric: string, a: string, b: string, filter: ComparisonFilter = {}): MetricDifference {
  const m = metricOf(data, metric);
  const none = (method: string, extra: Partial<MetricDifference> = {}): MetricDifference => ({ metric, a, b, estimate: null, interval: null, method, ...extra });
  if (!m || !kindOf(m)) return none(`no metric "${metric}" with a known kind`);
  const kind = m.kind;
  const scoped: ComparisonFilter = { ...filter, alternatives: [a, b] };
  if (kind === "preference") {
    const list = duels(data, m.id, scoped).filter(d => d.valid);
    const aw = list.filter(d => d.winner === a).length, bw = list.filter(d => d.winner === b).length, ties = list.filter(d => d.winner === "tie").length, n = aw + bw;
    if (!n) return none(ties ? `${ties} tied head-to-head judgment${ties === 1 ? "" : "s"} and no decisive one between them` : "no head-to-head judgments between them", { kind, n: [0, 0] });
    const w = wilson(aw, n, Z95)!;
    return { metric, a, b, kind, n: [n, n], estimate: (aw - bw) / n, interval: [2 * w[0] - 1, 2 * w[1] - 1], method: `net head-to-head share: (${aw} wins − ${bw} wins) ÷ ${n} decisive judgment${n === 1 ? "" : "s"}${ties ? ` (${ties} tie${ties === 1 ? "" : "s"} set aside)` : ""}; 95% interval 2p − 1 from the Wilson score interval on a's share` };
  }
  const [sa, sb] = [a, b].map(id => summarize(data, metric, { ...filter, alternatives: [id] }).find(s => s.alternative === id));
  if (!sa || !sb) return none("one side has no summary", { kind });
  const sizes: [number, number] = [sa.n, sb.n];
  if (kind === "binary" || kind === "count") {
    if (!sa.n || !sb.n || !isNum(sa.k) || !isNum(sb.k)) return none("no valid observations on one side", { kind, n: sizes });
    return { metric, a, b, kind, n: sizes, estimate: sa.k / sa.n - sb.k / sb.n, interval: newcombe(sa.k, sa.n, sb.k, sb.n), method: "difference in rates; 95% Newcombe hybrid score interval (method 10) for two independent proportions" };
  }
  if (kind === "numeric") {
    if (!isNum(sa.mean) || !isNum(sb.mean)) return none("no valid values on one side", { kind, n: sizes });
    const w = welch(sa.mean, sa.sd ?? NaN, sa.n, sb.mean, sb.sd ?? NaN, sb.n);
    const out: MetricDifference = {
      metric, a, b, kind, n: sizes, estimate: w.estimate, interval: w.interval,
      method: w.interval ? `difference in means; 95% Welch interval (${w.df!.toFixed(1)} Welch–Satterthwaite degrees of freedom)` : sa.n < 2 || sb.n < 2 ? "difference in means; no interval with fewer than two values on a side" : !isNum(sa.sd) || !isNum(sb.sd) ? "difference in means; no interval without a standard deviation on both sides" : "difference in means; no interval, since neither side varies",
    };
    if (sa.values?.length && sb.values?.length) {
      const est = medianOf(sa.values)! - medianOf(sb.values)!;
      const iv = bootstrap(sa.values, sb.values, (x, y) => medianOf(x)! - medianOf(y)!, `median|${metric}|${a}|${b}`);
      out.median = { estimate: est, interval: iv, method: `difference in medians; 95% percentile bootstrap, ${BOOT} seeded resamples of each side` };
    }
    return out;
  }
  if (kind === "ordinal") {
    const expand = (s: MetricSummary) => (s.counts || []).flatMap((c, i) => Array<number>(c).fill(i));
    const xs = expand(sa), ys = expand(sb);
    if (!xs.length || !ys.length) return none("no valid observations on one side", { kind, n: sizes });
    return { metric, a, b, kind, n: sizes, estimate: superiority(xs, ys), interval: bootstrap(xs, ys, superiority, `ordinal|${metric}|${a}|${b}`), method: `probability of superiority P(a > b) + ½P(tie) − ½ (Vargha–Delaney A − ½); 95% percentile bootstrap, ${BOOT} seeded resamples of each side` };
  }
  // rank: pair within rankings and cases when both alternatives were placed together
  const r = readObservations(data, m, scoped);
  const ka = r.keyed.get(a), kb = r.keyed.get(b), diffs: number[] = [];
  if (ka && kb) for (const [key, va] of ka) { const vb = kb.get(key); if (vb) diffs.push(meanOf(va)! - meanOf(vb)!); }
  if (diffs.length >= 2) {
    const md = meanOf(diffs)!, sd = sdOf(diffs)!;
    const iv = sd > 0 ? tInterval(md, sd, diffs.length) : null;
    return { metric, a, b, kind, n: sizes, estimate: md, interval: iv, method: `difference in mean rank, paired within ${diffs.length} rankings or cases that placed both; ${iv ? "95% paired t interval" : "no interval, since the paired differences do not vary"}` };
  }
  if (!isNum(sa.meanRank) || !isNum(sb.meanRank)) return none("no valid ranks on one side", { kind, n: sizes });
  const w = welch(sa.meanRank, sa.sd ?? NaN, sa.n, sb.meanRank, sb.sd ?? NaN, sb.n);
  return { metric, a, b, kind, n: sizes, estimate: w.estimate, interval: w.interval, method: w.interval ? `difference in mean rank; 95% Welch interval (${w.df!.toFixed(1)} degrees of freedom)` : "difference in mean rank; no interval" };
}

/** A comparison whose alternatives are the groups at one depth (0 = outermost):
 * observations, aggregates and rankings move to their alternative's group, and
 * judgments between two members of the same group are set aside. Every summary
 * and difference above then works on groups. members lists who was pooled;
 * alternatives without a group at that depth are left out. */
export function groupComparison(data: Comparison, depth = 0, filter: ComparisonFilter = {}): Comparison & { members: Record<string, string[]>; paths: Record<string, string[]> } {
  const okAlt = altFilter(data, filter);
  const d = Math.max(0, Math.floor(isNum(depth) ? depth : 0));
  const groupOf = new Map<string, string>(), members: Record<string, string[]> = {}, paths: Record<string, string[]> = {};
  for (const a of items<{ id: unknown; group?: string[] | string }>(data?.alternatives)) {
    if (!okAlt(a.id)) continue;
    const path = groupPath(a.group);
    if (path.length <= d) continue;
    const at = path.slice(0, d + 1), id = at.join(" › ");
    groupOf.set(a.id, id);
    (members[id] ||= []).push(a.id);
    paths[id] = at;
  }
  const move = (id: unknown) => typeof id === "string" ? groupOf.get(id) : undefined;
  const alternatives = Object.keys(members).map(id => ({ id, label: paths[id][d], ...(d ? { group: paths[id].slice(0, d) } : {}), description: `${members[id].length} alternative${members[id].length === 1 ? "" : "s"} pooled` }));
  const observations = items<Observation>(data?.observations).flatMap(o => { const g = move(o.alternative); return g ? [{ ...o, alternative: g, unit: `${o.alternative}\u0000${o.unit ?? ""}` }] : []; });
  const aggregates = items<Aggregate>(data?.aggregates).flatMap(a => { const g = move(a.alternative); return g ? [{ ...a, alternative: g, lo: undefined, hi: undefined }] : []; });
  const preferences = items<Preference>(data?.preferences).flatMap(p => {
    const ga = move(p.a), gb = move(p.b);
    if (!ga || !gb || ga === gb) return [];
    return [{ ...p, a: ga, b: gb, winner: p.winner === p.a ? ga : p.winner === p.b ? gb : p.winner }];
  });
  const rankings = items<Ranking>(data?.rankings).map(r => ({ ...r, order: (Array.isArray(r.order) ? r.order : []).map(move).filter((g): g is string => !!g) }));
  const baseline = typeof data?.baseline === "string" ? groupOf.get(data.baseline) : undefined;
  return { ...data, alternatives, observations, aggregates, preferences, rankings, identical: [], members, paths, ...(baseline ? { baseline } : { baseline: undefined }) };
}

/** Summaries pooled by group path at one depth (0 = outermost). group is the
 * group's path joined with " › ", so equal names under different parents stay apart. */
export function summarizeGroups(data: Comparison, metric: string, depth = 0, filter: ComparisonFilter = {}): Array<MetricSummary & { group: string; members: string[]; path: string[] }> {
  const g = groupComparison(data, depth, filter);
  return summarize(g, metric, { cases: filter.cases, caseGroups: filter.caseGroups })
    .filter(s => Object.prototype.hasOwnProperty.call(g.members, s.alternative))
    .map(s => ({ ...s, group: s.alternative, members: g.members[s.alternative], path: g.paths[s.alternative] }));
}

/** Head-to-head wins between every pair of alternatives on a preference metric
 * (or, without one, the judgments that name no metric). wins[i][j] counts i
 * beating j; ties are symmetric; unreached judgments are left out. */
export function winMatrix(data: Comparison, metric?: string, filter: ComparisonFilter = {}): { ids: string[]; wins: number[][]; ties: number[][] } {
  const list = duels(data, metric, filter).filter(d => d.valid);
  const okAlt = altFilter(data, filter);
  const ids = [...new Set([...alternativeIds(data).filter(okAlt), ...list.flatMap(d => [d.a, d.b])])];
  const at = new Map(ids.map((id, i) => [id, i]));
  const wins = ids.map(() => ids.map(() => 0)), ties = ids.map(() => ids.map(() => 0));
  for (const d of list) {
    const i = at.get(d.a)!, j = at.get(d.b)!;
    if (d.winner === "tie") { ties[i][j]++; ties[j][i]++; }
    else if (d.winner === d.a) wins[i][j]++;
    else wins[j][i]++;
  }
  return { ids, wins, ties };
}

/** Unreached or malformed judgments on a metric (or overall), for a visible count. */
export function invalidJudgments(data: Comparison, metric?: string, filter: ComparisonFilter = {}): number {
  return duels(data, metric, filter).filter(d => !d.valid).length;
}
