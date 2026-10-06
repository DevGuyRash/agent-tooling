/** The difference view: how far one set of runs' pass rate sits from another's,
 * in percentage points with a 95% Newcombe interval, on an axis centred on zero.
 * Rows come from explicit counts, from a baseline arm, or from two named sets of
 * runs; identical arms add a "chance alone" reference. Invalid runs are left
 * out of both sides and counted beside them, never as failures. */
import { esc, fmtInt, fmtPct, isNum, outcomeMark } from "../core";
import type { RenderContext } from "../model";
import { newcombe, placement, Placement } from "../stats";
import { tally, TrialReport, TrialRun, trialAxes } from "../trial-model";
import { empty, frame, FrameInput, pos } from "./frame";

/** A set of runs: arms and cases to keep (all when omitted), and its name. */
export interface ContrastSide { label?: string; arms?: string[]; arm?: string; cases?: string[]; case?: string }
/** Explicit counts: k1 of n1 valid runs passed on the first side, k2 of n2 on the second. */
export interface ContrastRow {
  label?: string;
  /** Arm identity of the first side (color, shape, label) and of the second. */
  arm?: string; vs?: string;
  note?: string;
  k1: number; n1: number; k2: number; n2: number;
  invalid1?: number; invalid2?: number;
  /** The two sides received identical material: shown as the chance-alone reference. */
  identical?: boolean;
}
export interface ContrastInput extends FrameInput {
  /** Explicit counts; needs no trial data. */
  rows?: ContrastRow[];
  /** One row per other arm: that arm minus the baseline (one row per baseline when several). */
  baseline?: string | string[];
  /** Arms to compare against the baseline; by default every other arm that ran, except the baseline's identical copies. */
  arms?: string[];
  /** Cases to pool over; by default every case. */
  cases?: string[];
  /** Two named sets of runs: each row is a minus b. */
  a?: ContrastSide; b?: ContrastSide;
  /** Pair each case with its variant named case + suffix: a is the variants, b their base cases. */
  pair?: { suffix: string } | string;
  /** Extra rows: one per case (under each comparison) or one per arm (two-set form). */
  by?: "arm" | "case" | "none";
  /** Groups of arms given identical material: the gaps between them are drawn as the noise reference. */
  identical?: string[][];
  /** A bar the difference is held to, such as a decision rule's +15 points (0.15). */
  threshold?: number | { value: number; label?: string };
  /** Order comparisons by difference instead of by identity order. */
  sort?: "identity" | "difference";
  /** Show the short method note under the rows (default true). */
  method?: boolean;
}

interface Side { html: string; text: string; k: number | null; n: number | null; invalid: number; arm?: string }
type Kind = "main" | "case" | "noise";
interface Row { kind: Kind; head?: string; a: Side; b: Side; note?: string; uneven?: boolean; children?: Row[]; /** Runs both sides select: they are not independent. */ shared?: number }
interface Computed { d: number; ci: [number, number] }

const own = (o: object, k: string) => Object.prototype.hasOwnProperty.call(o, k);
const strings = (v: unknown): string[] | null => Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : typeof v === "string" ? [v] : null;
/** k for a count field: a non-negative whole number, or null when missing or unusable. */
const countOf = (v: unknown): number | null => isNum(v) && v >= 0 ? Math.floor(v) : null;

/** Signed percentage points from a proportion difference: +29, −8, 0, +0.4. */
export function fmtPoints(x: number | null | undefined): string {
  if (!isNum(x)) return "—";
  const p = x * 100, a = Math.abs(p);
  if (a < 0.05) return "0";
  const body = a < 1 ? a.toFixed(1) : String(Math.round(a));
  return `${p > 0 ? "+" : "−"}${body}`;
}

function computed(r: Row): Computed | null {
  if (r.shared) return null;
  const { k: k1, n: n1 } = r.a, { k: k2, n: n2 } = r.b;
  if (k1 === null || n1 === null || k2 === null || n2 === null) return null;
  const ci = newcombe(k1, n1, k2, n2);
  return ci ? { d: k1 / n1 - k2 / n2, ci } : null;
}

/** Why a row has no interval, in words; null when it has one. */
function blocker(r: Row): string | null {
  if (r.shared) return `The two sides share ${r.shared} ${r.shared === 1 ? "run" : "runs"}, so they are not independent sets and an interval for two independent rates does not apply. Give a and b runs that do not overlap.`;
  for (const s of [r.a, r.b]) {
    if (s.k === null || s.n === null) return `${s.text}: counts are missing.`;
    if (s.k > s.n) return `${s.text}: ${s.k} passed of ${s.n} valid runs, which cannot be; the counts are shown as given.`;
  }
  const none = [r.a, r.b].filter(s => s.n === 0).map(s => s.text);
  return none.length ? `${none.join(" and ")} ${none.length > 1 ? "have" : "has"} no valid runs.` : null;
}

export function contrast(input: ContrastInput, ctx: RenderContext): string {
  input = input && typeof input === "object" ? input : {} as ContrastInput;
  const problems: string[] = [];
  const caseName = (id: string) => own(ctx.caseLabels, id) && typeof ctx.caseLabels[id] === "string" && ctx.caseLabels[id] ? ctx.caseLabels[id] : id;
  const armSide = (arm: string, k: number | null, n: number | null, invalid: number): Side =>
    ({ html: ctx.arms.tag(arm, { id: false }), text: ctx.arms.label(arm), k, n, invalid, arm });
  const bar = thresholdOf(input.threshold, problems);
  const by = input.by ?? "none";
  if (!["arm", "case", "none"].includes(by)) problems.push(`“by” is ${typeof by === "string" ? `"${by}"` : `a ${typeof by}`}; use "arm", "case" or "none". No breakdown is shown.`);

  let rows: Row[] = [], noise: Row[] = [];
  let firstName = "the first set", secondName = "the second set", pooledOver = "";

  if (Array.isArray(input.rows)) {
    // ------------------------------------------------ explicit counts
    const aName = typeof input.a?.label === "string" && input.a.label ? input.a.label : "First set";
    const bName = typeof input.b?.label === "string" && input.b.label ? input.b.label : "Second set";
    firstName = aName; secondName = bName;
    for (const raw of input.rows) {
      if (!raw || typeof raw !== "object") continue;
      const side = (arm: unknown, fallback: string, k: unknown, n: unknown, inv: unknown): Side => typeof arm === "string" && arm
        ? armSide(arm, countOf(k), countOf(n), countOf(inv) ?? 0)
        : { html: `<span class="av-contrast-side-label">${esc(fallback)}</span>`, text: fallback, k: countOf(k), n: countOf(n), invalid: countOf(inv) ?? 0 };
      const row: Row = {
        kind: raw.identical === true ? "noise" : "main",
        head: typeof raw.label === "string" && raw.label ? `<span class="av-contrast-head-label">${esc(raw.label)}</span>` : undefined,
        a: side(raw.arm, aName, raw.k1, raw.n1, raw.invalid1), b: side(raw.vs, bName, raw.k2, raw.n2, raw.invalid2),
        note: typeof raw.note === "string" && raw.note ? raw.note : undefined,
      };
      (row.kind === "noise" ? noise : rows).push(row);
    }
    if (!rows.length && !noise.length) return frame("contrast", input, empty("No rows to compare."));
  } else {
    // ------------------------------------------------ from trial runs
    if (!ctx.trial) throw new TypeError(`A contrast block needs "rows" with counts, or trial data in the report spec's "trial" field (trialReport() supplies it).`);
    const data: TrialReport = ctx.trial;
    const runs: TrialRun[] = (data.runs || []).filter(r => r && typeof r.arm === "string" && typeof r.scenario === "string");
    const axes = trialAxes({ ...data, runs });
    const ranArms = new Set(axes.arms), ranCases = new Set(axes.cases);
    const known = (list: string[] | null, ran: Set<string>, what: string, where: string): string[] | null => {
      if (!list) return null;
      const bad = list.filter(x => !ran.has(x));
      if (bad.length) problems.push(`${where}: ${bad.map(x => `“${x}”`).join(", ")} ${bad.length > 1 ? "are not" : "is not"} ${what === "arm" ? "an arm" : "a case"} with runs in this trial, so ${bad.length > 1 ? "they are" : "it is"} left out. ${what === "arm" ? "Arms" : "Cases"} with runs: ${listed([...ran])}.`);
      return list.filter(x => ran.has(x));
    };
    const byIdentity = (list: string[]) => [...new Set(list)].sort((x, y) => ctx.arms.index(x) - ctx.arms.index(y));
    const cases = known(strings(input.cases), ranCases, "case", "cases");
    const match = (r: TrialRun, arms: string[] | null, keep: string[] | null) => (!arms || arms.includes(r.arm)) && (!keep || keep.includes(r.scenario));
    const tallyOf = (arms: string[] | null, keep: string[] | null) => tally(runs.filter(r => match(r, arms, keep)));
    const sharedRuns = (aArms: string[] | null, aCases: string[] | null, bArms: string[] | null, bCases: string[] | null) => runs.filter(r => match(r, aArms, aCases) && match(r, bArms, bCases)).length;
    const validIn = (arms: string[] | null, c: string) => tallyOf(arms, [c]).valid;
    /** Pooled rates weight cases by their valid runs; flag a row whose sides weight them very differently. */
    const uneven = (aArms: string[] | null, bArms: string[] | null, pairs: Array<[string, string]>) => {
      const va = pairs.map(([ca]) => validIn(aArms, ca)), vb = pairs.map(([, cb]) => validIn(bArms, cb));
      const ta = va.reduce((s, x) => s + x, 0), tb = vb.reduce((s, x) => s + x, 0);
      if (!ta || !tb) return false;
      return pairs.some((_, i) => (va[i] > 0) !== (vb[i] > 0) || Math.abs(va[i] / ta - vb[i] / tb) > 0.1);
    };
    const groups = (Array.isArray(input.identical) ? input.identical : [])
      .map(g => byIdentity(known(strings(g), ranArms, "arm", "identical") || [])).filter(g => g.length > 1);
    const casePairs = (keep: string[] | null): Array<[string, string]> => (keep || axes.cases).map(c => [c, c]);
    const noiseRows = (keep: string[] | null) => groups.flatMap(g => g.flatMap((x, i) => g.slice(i + 1).map((y): Row => {
      const ty = tallyOf([y], keep), tx = tallyOf([x], keep);
      return { kind: "noise", a: armSide(y, ty.pass, ty.valid, ty.invalid), b: armSide(x, tx.pass, tx.valid, tx.invalid), uneven: uneven([y], [x], casePairs(keep)) };
    })));
    const armVsArm = (x: string, y: string, keep: string[] | null, withCases: boolean): Row => {
      const tx = tallyOf([x], keep), ty = tallyOf([y], keep);
      const row: Row = { kind: "main", a: armSide(x, tx.pass, tx.valid, tx.invalid), b: armSide(y, ty.pass, ty.valid, ty.invalid), uneven: uneven([x], [y], casePairs(keep)) };
      if (withCases) row.children = (keep || axes.cases).flatMap(c => {
        const cx = tallyOf([x], [c]), cy = tallyOf([y], [c]);
        if (!cx.runs && !cy.runs) return [];
        return [{ kind: "case" as Kind, head: caseHead(c), a: armSide(x, cx.pass, cx.valid, cx.invalid), b: armSide(y, cy.pass, cy.valid, cy.invalid) }];
      });
      return row;
    };
    const caseHead = (c: string) => `<span class="av-contrast-head-label">${esc(caseName(c))}</span>${caseName(c) !== c ? `<code class="av-arm-id">${esc(c)}</code>` : ""}`;
    if (cases) pooledOver = cases.length === axes.cases.length ? "" : cases.map(caseName).join(", ");

    const suffix = typeof input.pair === "string" ? input.pair : input.pair && typeof input.pair === "object" && typeof input.pair.suffix === "string" ? input.pair.suffix : null;
    const twoSets = !!(input.a || input.b || suffix !== null);
    const baselines = input.baseline !== undefined ? known(strings(input.baseline), ranArms, "arm", "baseline") || [] : (!twoSets && typeof data.baseline === "string" && ranArms.has(data.baseline) ? [data.baseline] : []);

    if (input.baseline !== undefined && !baselines.length && !twoSets) {
      known(strings(input.arms), ranArms, "arm", "arms");
      return frame("contrast", input, `${problemList(problems)}${empty("Nothing to compare: no baseline named here is an arm with runs in this trial.")}`);
    }
    if (baselines.length) {
      // One row per compared arm and baseline: arm minus baseline.
      const copies = new Set(groups.filter(g => g.some(a => baselines.includes(a))).flat());
      const explicit = known(strings(input.arms), ranArms, "arm", "arms");
      // The baseline's identical copies are the chance-alone reference, never a candidate as well.
      const compared = byIdentity((explicit || axes.arms).filter(a => !baselines.includes(a) && !copies.has(a)));
      for (const x of compared) for (const y of byIdentity(baselines)) rows.push(armVsArm(x, y, cases, by === "case"));
      noise = noiseRows(cases);
      firstName = compared.length === 1 ? ctx.arms.label(compared[0]) : "the compared arm";
      secondName = baselines.length === 1 ? ctx.arms.label(baselines[0]) : "the baseline";
      if (!rows.length) return frame("contrast", input, `${problemList(problems)}${empty(`Nothing to compare against ${baselines.map(b => ctx.arms.label(b)).join(" and ")}: no other arm ran${cases ? " in these cases" : ""}.`)}`);
    } else if (twoSets) {
      // Two named sets of runs; with a suffix, each case's variant against its base case.
      const sideOf = (s: ContrastSide | undefined, which: string) => ({
        arms: known(strings(s?.arms) ?? strings(s?.arm), ranArms, "arm", `${which}.arms`) ?? known(strings(input.arms), ranArms, "arm", "arms"),
        cases: known(strings(s?.cases) ?? strings(s?.case), ranCases, "case", `${which}.cases`),
      });
      const A = sideOf(input.a, "a"), B = sideOf(input.b, "b");
      let pairs: Array<[string, string]> = [];
      if (suffix !== null) {
        if (!suffix) problems.push("The pair suffix is empty; name the text that ends each variant case, such as \"-review2\".");
        else pairs = axes.cases.filter(c => c.endsWith(suffix) && c.length > suffix.length && ranCases.has(c.slice(0, -suffix.length)))
          .map((c): [string, string] => [c, c.slice(0, -suffix.length)])
          .filter(([v, base]) => (!cases || cases.includes(v) || cases.includes(base)) && (!A.cases || A.cases.includes(v)) && (!B.cases || B.cases.includes(base)));
        if (suffix && !pairs.length) problems.push(`No case has a variant ending in “${suffix}” among the cases with runs.`);
        A.cases = pairs.map(p => p[0]); B.cases = pairs.map(p => p[1]);
      } else {
        if (cases) { A.cases = (A.cases || cases).filter(c => cases.includes(c)); B.cases = (B.cases || cases).filter(c => cases.includes(c)); }
        if (A.cases && B.cases && A.cases.length === B.cases.length && A.cases.some((c, i) => c !== B.cases![i])) pairs = A.cases.map((c, i): [string, string] => [c, B.cases![i]]);
        else { const inA = new Set(A.cases || axes.cases), inB = new Set(B.cases || axes.cases); pairs = axes.cases.filter(c => inA.has(c) && inB.has(c)).map((c): [string, string] => [c, c]); }
        if (JSON.stringify([A.arms, A.cases]) === JSON.stringify([B.arms, B.cases])) problems.push("Both sides select the same runs, so their difference is zero by construction. Give a and b different arms or cases.");
      }
      const onePair = suffix && pairs.length === 1 ? pairs[0] : null;
      firstName = typeof input.a?.label === "string" && input.a.label ? input.a.label : onePair ? caseName(onePair[0]) : suffix ? `“${suffix}” variants` : describe(A, ctx, caseName);
      secondName = typeof input.b?.label === "string" && input.b.label ? input.b.label : onePair ? caseName(onePair[1]) : suffix ? "base cases" : describe(B, ctx, caseName);
      // A named side also says which runs it holds, so the reader can trace it to cases and arms.
      const holds = (arms: string[] | null, keep: string[] | null, name: string) => {
        const parts = [
          arms && arms.length < axes.arms.length ? arms.map(a => ctx.arms.label(a)).join(", ") : "",
          keep && keep.length < axes.cases.length ? (keep.length <= 3 ? keep.join(", ") : `${keep.length} cases`) : "",
        ].filter(Boolean);
        const text = parts.join(" · ");
        return text && text !== name ? `<span class="av-contrast-side-detail"${keep && keep.length > 3 ? ` title="${esc(keep.join(", "))}"` : ""}>${esc(text)}</span>` : "";
      };
      const set = (name: string, arms: string[] | null, keep: string[] | null): Side => {
        const t = tallyOf(arms, keep), arm = arms && arms.length === 1 ? arms[0] : undefined;
        return { html: `${arm ? ctx.arms.glyph(arm) : ""}<span class="av-contrast-side-label">${esc(name)}</span>${holds(arms, keep, name)}`, text: name, k: t.pass, n: t.valid, invalid: t.invalid, arm };
      };
      const main: Row = { kind: "main", a: set(firstName, A.arms, A.cases), b: set(secondName, B.arms, B.cases), uneven: pairs.length ? uneven(A.arms, B.arms, pairs) : false, shared: sharedRuns(A.arms, A.cases, B.arms, B.cases) };
      if (by === "arm") {
        const both = byIdentity(axes.arms.filter(x => (!A.arms || A.arms.includes(x)) && (!B.arms || B.arms.includes(x))));
        if (!both.length) problems.push("No arm ran on both sides, so there are no per-arm rows.");
        main.children = both.map(x => {
          const ta = tallyOf([x], A.cases), tb = tallyOf([x], B.cases);
          return { kind: "case" as Kind, head: ctx.arms.tag(x, { id: false }), shared: sharedRuns([x], A.cases, [x], B.cases), a: { html: esc(firstName), text: firstName, k: ta.pass, n: ta.valid, invalid: ta.invalid, arm: x }, b: { html: esc(secondName), text: secondName, k: tb.pass, n: tb.valid, invalid: tb.invalid, arm: x } };
        });
      } else if (by === "case") {
        main.children = pairs.flatMap(([ca, cb]) => {
          const ta = tallyOf(A.arms, [ca]), tb = tallyOf(B.arms, [cb]);
          if (!ta.runs && !tb.runs) return [];
          const head = ca === cb ? caseHead(ca) : suffix ? caseHead(cb)
            : ca.startsWith(cb) && ca.length > cb.length ? `${caseHead(cb)}<span class="av-contrast-head-note">with <code>${esc(ca.slice(cb.length))}</code> against without</span>`
            : `${caseHead(ca)}<span class="av-contrast-head-note">against ${esc(caseName(cb))}</span>`;
          return [{ kind: "case" as Kind, head, shared: sharedRuns(A.arms, [ca], B.arms, [cb]), a: { html: esc(firstName), text: firstName, k: ta.pass, n: ta.valid, invalid: ta.invalid, arm: main.a.arm }, b: { html: esc(secondName), text: secondName, k: tb.pass, n: tb.valid, invalid: tb.invalid, arm: main.b.arm } }];
        });
      }
      rows = [main];
      noise = noiseRows(cases);
    } else if ((known(strings(input.arms), new Set(axes.arms), "arm", "arms") || axes.arms).length > 1) {
      // No baseline named: every pair of arms, later minus earlier in identity order.
      const order = byIdentity(known(strings(input.arms), ranArms, "arm", "arms") || axes.arms), same = (x: string, y: string) => groups.some(g => g.includes(x) && g.includes(y));
      for (let i = 0; i < order.length; i++) for (let j = i + 1; j < order.length; j++) if (!same(order[i], order[j])) rows.push(armVsArm(order[j], order[i], cases, by === "case"));
      noise = noiseRows(cases);
      firstName = "the later arm"; secondName = "the earlier arm";
      if (!rows.length && !noise.length) return frame("contrast", input, `${problemList(problems)}${empty("Nothing to compare.")}`);
    } else {
      // One arm: compare case variants when the case names show them.
      const found = variantSuffix(axes.cases);
      if (!found) return frame("contrast", input, `${problemList(problems)}${empty("Nothing to compare: this trial ran one arm and no case variants. Name two sets of runs with “a” and “b”, or give counts in “rows”.")}`);
      return contrast({ ...input, pair: { suffix: found } }, ctx);
    }
  }

  if (input.sort === "difference") rows.sort((x, y) => (computed(y)?.d ?? -Infinity) - (computed(x)?.d ?? -Infinity));

  // ------------------------------------------------ axis, centred on zero
  const all = [...rows, ...rows.flatMap(r => r.children || []), ...noise];
  const gaps = noise.map(computed).filter((c): c is Computed => !!c).map(c => Math.abs(c.d));
  const band = gaps.length ? Math.max(...gaps) : null;
  const extent = Math.max(0, ...all.map(computed).flatMap(c => c ? [Math.abs(c.ci[0]), Math.abs(c.ci[1])] : []), bar ? Math.abs(bar.value) : 0, band ?? 0);
  // A little headroom so an interval ending near a round number does not touch the frame.
  const M = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.8, 1].find(m => m >= Math.min(1, extent + 0.02) - 1e-9) ?? 1;
  const x = (v: number) => pos((v + M) / (2 * M));
  const ticks = [-M, -M / 2, 0, M / 2, M];
  const barText = bar ? `the ${fmtPoints(bar.value)}-point bar` : "";

  const sideLine = (s: Side, short: boolean, glyph = true) => {
    const frac = s.k === null || s.n === null ? '<span class="av-missing">missing</span>' : `<span class="av-frac"><b>${fmtInt(s.k)}</b>/${fmtInt(s.n)}</span>${short ? "" : `<span class="av-rate">${s.n && s.k <= s.n ? fmtPct(s.k / s.n) : "—"}</span>`}`;
    const chips = `${s.n !== null && s.n > 0 && s.n < 5 ? `<span class="av-chip av-chip--warn" title="Fewer than five valid runs: a very rough rate">n = ${fmtInt(s.n)}</span>` : ""}${s.n === 0 ? '<span class="av-chip av-chip--warn">no valid runs</span>' : ""}${s.invalid ? `<span class="av-chip av-chip--invalid" title="${esc(`${s.text}: invalid runs are left out, never counted as failures`)}">${outcomeMark("invalid")}${fmtInt(s.invalid)} invalid</span>` : ""}`;
    return short
      ? `<span class="av-contrast-mini">${s.arm && glyph ? ctx.arms.glyph(s.arm) : ""}${frac}${chips}</span>`
      : `<div class="av-contrast-side"><span class="av-contrast-side-name">${s.html}</span><span class="av-contrast-side-n">${frac}</span>${chips ? `<span class="av-contrast-side-chips">${chips}</span>` : ""}</div>`;
  };

  const sentence = (r: Row, c: Computed | null, why: string | null): string => {
    if (!c) return `<strong>No interval.</strong> ${esc(why || "The counts do not allow one.")}`;
    const A = esc(r.a.text), B = esc(r.b.text), place: Placement = placement(c.ci, 0);
    let out = r.kind === "noise"
      ? (Math.abs(c.d) < 0.0005 ? "<strong>Identical material.</strong> These copies passed at the same rate this time." : `<strong>Identical material,</strong> so this gap of ${esc(fmtPoints(Math.abs(c.d)).replace(/^\+/, ""))} points is chance alone.`)
      : place === "above" ? `<strong>The 95% interval lies above zero:</strong> these runs fit only a higher pass rate for ${A} than for ${B}.`
      : place === "below" ? `<strong>The 95% interval lies below zero:</strong> these runs fit only a lower pass rate for ${A} than for ${B}.`
      : `<strong>The 95% interval includes zero:</strong> these runs cannot tell ${A} and ${B} apart.`;
    if (bar && r.kind !== "noise") {
      const t = placement(c.ci, bar.value), d = esc(fmtPoints(c.d));
      out += " " + (t === "above" ? `All of it is above ${esc(barText)}.`
        : t === "below" ? `All of it is below ${esc(barText)}.`
        : c.d >= bar.value ? `The observed ${d} meets ${esc(barText)}, but the interval reaches down to ${esc(fmtPoints(c.ci[0]))}.`
        : `The observed ${d} falls short of ${esc(barText)}; the interval reaches up to ${esc(fmtPoints(c.ci[1]))}.`);
    }
    return out;
  };

  const rowHtml = (r: Row): string => {
    const c = computed(r), why = c ? null : blocker(r), compact = r.kind === "case";
    const color = r.a.arm ? ctx.arms.color(r.a.arm) : "var(--av-ink-2)";
    const style = `--c:${color};--z:${x(0)};${c ? `--p:${x(c.d)};--lo:${x(c.ci[0])};--hi:${x(c.ci[1])};` : ""}${bar && r.kind !== "noise" ? `--t:${x(bar.value)};` : ""}${band && r.kind === "main" ? `--b0:${x(-band)};--b1:${x(band)};` : ""}`;
    const counts = (s: Side) => s.k === null || s.n === null ? "missing counts" : `${s.k} of ${s.n} valid runs passed${s.invalid ? `, ${s.invalid} invalid` : ""}`;
    const aria = `${r.a.text} minus ${r.b.text}${r.head ? ` (${stripTags(r.head)})` : ""}: ${c ? `${fmtPoints(c.d)} points, 95% interval ${fmtPoints(c.ci[0])} to ${fmtPoints(c.ci[1])}` : "no interval"}. ${r.a.text}: ${counts(r.a)}. ${r.b.text}: ${counts(r.b)}.`;
    const track = `<div class="av-contrast-track${c ? "" : " av-contrast-track--empty"}" role="img" aria-label="${esc(aria)}" style="${style}">${band && r.kind === "main" && c ? '<span class="av-contrast-band"></span>' : ""}<span class="av-contrast-zero"></span>${bar && r.kind !== "noise" ? '<span class="av-contrast-bar"></span>' : ""}${c ? '<span class="av-contrast-ci"></span><span class="av-contrast-pt"></span>' : `<span class="av-contrast-none"><span>${esc(compact ? "no interval" : "no interval: see below")}</span></span>`}</div>`;
    const passes = c && r.a.n === r.b.n && r.a.k !== null && r.b.k !== null
      ? `<span class="av-contrast-passes" title="${esc(`${r.a.k} against ${r.b.k} passes, of ${r.a.n} valid runs each`)}">${r.a.k - r.b.k > 0 ? "+" : r.a.k - r.b.k < 0 ? "−" : "±"}${Math.abs(r.a.k - r.b.k)} ${Math.abs(r.a.k - r.b.k) === 1 ? "pass" : "passes"}</span>` : "";
    const place = c ? placement(c.ci, 0) : null;
    const chip = compact && place ? `<span class="av-contrast-place av-contrast-place--${place}">${place === "spans" ? "includes 0" : `${place} 0`}</span>` : "";
    const num = `<div class="av-contrast-num">${c ? `<span class="av-contrast-d">${esc(fmtPoints(c.d))}<span class="av-contrast-unit">pts</span></span><span class="av-contrast-ci-text">${esc(fmtPoints(c.ci[0]))} to ${esc(fmtPoints(c.ci[1]))}</span>${passes}${chip}` : '<span class="av-contrast-d av-contrast-d--none">—</span>'}</div>`;
    const flags = `${r.uneven ? '<span class="av-chip av-chip--warn" title="One side has its valid runs spread over the cases very differently (a share more than 10 points apart, or a case with valid runs on one side only), so its pooled rate weights the cases differently. Read the per-case rows.">uneven case mix</span>' : ""}`;
    const label = compact
      ? `<div class="av-contrast-label">${r.head ? `<div class="av-contrast-head">${r.head}</div>` : ""}<div class="av-contrast-minis">${sideLine(r.a, true, r.a.arm !== r.b.arm)}<span class="av-contrast-vs">vs</span>${sideLine(r.b, true, r.a.arm !== r.b.arm)}</div></div>`
      : `<div class="av-contrast-label">${r.head ? `<div class="av-contrast-head">${r.head}</div>` : ""}<div class="av-contrast-sides">${sideLine(r.a, false)}<div class="av-contrast-minus" aria-hidden="true">minus</div>${sideLine(r.b, false)}</div>${flags || r.note ? `<div class="av-contrast-flags">${flags}${r.note ? `<span class="av-contrast-note">${esc(r.note)}</span>` : ""}</div>` : ""}</div>`;
    const reading = compact ? (c ? "" : `<p class="av-contrast-reading">${esc(why || "")}</p>`) : `<p class="av-contrast-reading">${sentence(r, c, why)}</p>`;
    const kidsLabel = `${by === "arm" ? "By arm" : "By case"}: ${r.a.text} vs ${r.b.text}`;
    const kids = r.children?.length ? `<ul class="av-contrast-cases" aria-label="${esc(kidsLabel)}"><li class="av-contrast-cases-head" aria-hidden="true"><span class="av-eyebrow">${by === "arm" ? "By arm" : "By case"}</span><span>${esc(r.a.text)} <span class="av-contrast-vs">vs</span> ${esc(r.b.text)}</span></li>${r.children.map(k => `<li>${rowHtml(k)}</li>`).join("")}</ul>` : "";
    return `<div class="av-contrast-row av-contrast-row--${r.kind}"${place ? ` data-place="${place}"` : ""}>${label}${track}${num}${reading}</div>${kids}`;
  };

  const tickHtml = ticks.map(t => `<span style="--x:${x(t)}">${esc(fmtPoints(t))}</span>`).join("");
  const axis = `<div class="av-contrast-axis" aria-hidden="true"><span class="av-contrast-axis-unit">difference, points</span><div class="av-contrast-ticks">${tickHtml}</div><span></span></div>
<div class="av-contrast-dir" aria-hidden="true"><span></span><div class="av-contrast-dir-track"><span class="av-contrast-dir-left">← ${esc(secondName)} higher</span><span class="av-contrast-dir-right">${esc(firstName)} higher →</span></div><span></span></div>`;
  const legend = `<p class="av-legend av-contrast-legend"><span><span class="av-legend-pt"></span>difference in pass rate</span><span><span class="av-legend-ci"></span>95% Newcombe interval</span><span><span class="av-contrast-legend-zero"></span>zero: no difference</span>${bar ? `<span><span class="av-legend-ref av-legend-ref--rule"></span>${esc(bar.label || `bar: ${fmtPoints(bar.value)} points`)}</span>` : ""}${band ? `<span><span class="av-legend-noise"></span>gap between identical arms (${esc(fmtPoints(band).replace(/^\+/, ""))} points), either way</span>` : ""}</p>`;
  const list = `<ul class="av-contrast-list" aria-label="${esc(input.title || "Difference in pass rate")}">${rows.map(r => `<li class="av-contrast-item">${rowHtml(r)}</li>`).join("")}</ul>`;
  const noiseHtml = noise.length ? `<div class="av-contrast-group" role="group" aria-label="Chance alone"><p class="av-contrast-group-label"><span class="av-eyebrow">Chance alone</span><span>Arms that received identical material. Their gap is what chance produces between runs of the same thing.</span></p><ul class="av-contrast-list">${noise.map(r => `<li class="av-contrast-item">${rowHtml(r)}</li>`).join("")}</ul></div>` : "";
  const anyUneven = all.some(r => r.uneven);
  const scope = pooledOver ? `<p class="av-contrast-scope"><span class="av-eyebrow">Pooled over</span>${esc(pooledOver)}</p>` : "";
  const method = input.method === false ? "" : `<details class="av-contrast-method"><summary>How these differences are computed</summary><p>Each row is the first pass rate minus the second, in percentage points, over valid runs. Invalid runs are left out of both sides and counted beside them, never as failures. The interval is a 95% Newcombe hybrid score interval for the difference of two independent rates (Newcombe 1998, method 10). It covers run-to-run variation on these cases, not cases the trial did not include, and it is the only statistic this view adds: no p-values and no winners.${anyUneven ? " “Uneven case mix” marks rows whose two sides spread their valid runs over the cases very differently, so their pooled rates weight the cases differently; read the per-case rows for those." : ""}</p></details>`;
  // With no interval anywhere (every side empty, say) the axis and legend would describe nothing.
  const drawn = all.some(r => computed(r));
  return frame("contrast", input, `${problemList(problems)}${drawn ? legend : ""}${scope}<div class="av-contrast-grid">${drawn ? axis : ""}${list}${noiseHtml}</div>${method}`);
}

function thresholdOf(raw: ContrastInput["threshold"], problems: string[]): { value: number; label: string } | null {
  if (raw === undefined || raw === null) return null;
  const value = isNum(raw) ? raw : typeof raw === "object" ? (raw as { value?: unknown }).value : undefined;
  const label = typeof raw === "object" && typeof (raw as { label?: unknown }).label === "string" ? (raw as { label: string }).label : "";
  if (!isNum(value)) { problems.push("The threshold needs a number, such as 0.15 for +15 points; it is not drawn."); return null; }
  if (Math.abs(value) > 1) { problems.push(`The threshold ${value} is outside −1 to 1; write +15 points as 0.15. It is not drawn.`); return null; }
  return { value, label };
}

/** Names for a message, at most twelve, so a long trial does not flood the block. */
function listed(names: string[]): string {
  if (!names.length) return "none";
  return names.length > 12 ? `${names.slice(0, 12).join(", ")} and ${names.length - 12} more` : names.join(", ");
}

function problemList(problems: string[]): string {
  return problems.length ? `<ul class="av-contrast-problems" role="note">${[...new Set(problems)].map(p => `<li>${esc(p)}</li>`).join("")}</ul>` : "";
}

function stripTags(html: string): string {
  return html.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim().replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&amp;/g, "&");
}

function describe(side: { arms: string[] | null; cases: string[] | null }, ctx: RenderContext, caseName: (id: string) => string): string {
  const arms = side.arms ? side.arms.map(a => ctx.arms.label(a)).join(" + ") : "";
  const cases = side.cases ? side.cases.map(caseName).join(" + ") : "";
  return [arms, cases].filter(Boolean).join(" · ") || "all runs";
}

/** The one suffix that turns some case names into others ("x" and "x-review2"), or null. */
export function variantSuffix(cases: string[]): string | null {
  const found = new Set<string>();
  for (const base of cases) for (const other of cases) {
    if (other.length > base.length + 1 && other.startsWith(base) && /^[-_.:]/.test(other.slice(base.length))) {
      const tail = other.slice(base.length);
      found.add(tail);
    }
  }
  if (found.size !== 1) return null;
  const [suffix] = [...found];
  return suffix;
}
