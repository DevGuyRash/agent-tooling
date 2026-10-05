/** Views of a trial: the verdict and its rule, arm intervals with identical-arm
 * noise, every run by case and arm, checks, pairwise preferences, cost, invalid
 * runs, the run ledger and the plan. Each reads the trial in the render context
 * and accepts explicit data where a caller has its own. */
import { attrs, count, esc, fmtDelta, fmtInt, fmtNum, fmtPct, fmtSeconds, fmtUsd, inline, isNum, logTicks, median, niceTicks, num, Outcome, secondsUnit, outcomeBadge, outcomeLabel, outcomeMark, prose, quantile, wilson } from "../core";
import type { RenderContext } from "../model";
import { checkTable, costMeasures, judgeQuestion, outcomeOf, recordPath, tally, TrialReport, TrialRun, trialAxes } from "../trial-model";
import { empty, frame, FrameInput, pos } from "./frame";

const caseLabel = (ctx: RenderContext, id: string) => ctx.caseLabels[id] || id;
function trialOf(ctx: RenderContext, block: string): TrialReport {
  if (!ctx.trial) throw new TypeError(`A ${block} block needs trial data: supply the report spec's "trial" field (trialReport() does).`);
  return ctx.trial;
}

// ------------------------------------------------------------------ verdict

export interface VerdictInput extends FrameInput {
  verdict?: "adopt" | "reject" | "inconclusive" | "mixed" | "none";
  /** The word on the stamp; defaults to the verdict's own word. */
  label?: string;
  headline: string;
  detail?: string | string[];
  /** The decision rule as fixed before results, quoted verbatim. */
  rule?: string;
  checks?: Array<{ label: string; observed: string; threshold?: string; met?: boolean | null }>;
  conditions?: string[];
  limits?: string[];
  changes?: string[];
}
const verdictWords = { adopt: "Adopt", reject: "Do not adopt", inconclusive: "Inconclusive", mixed: "Mixed", none: "No decision recorded" };
const verdictIcons = { adopt: "✓", reject: "✕", inconclusive: "?", mixed: "±", none: "–" };

export function verdict(input: VerdictInput): string {
  const kind = input.verdict && input.verdict in verdictWords ? input.verdict : "none";
  const stamp = `<div class="av-stamp av-stamp--${kind}"><span class="av-stamp-icon" aria-hidden="true">${verdictIcons[kind]}</span><span class="av-stamp-word">${esc(input.label || verdictWords[kind])}</span></div>`;
  const lists = ([["conditions", "Holds when"], ["limits", "Does not show"], ["changes", "Would change it"]] as const)
    .filter(([key]) => (input[key] || []).length)
    .map(([key, title]) => `<div class="av-verdict-list av-verdict-list--${key}"><h4>${title}</h4><ul>${(input[key] || []).map(x => `<li>${inline(String(x))}</li>`).join("")}</ul></div>`).join("");
  const checks = (input.checks || []).length
    ? `<ol class="av-rule-checks">${input.checks!.map(c => {
        const state = c.met === true ? "met" : c.met === false ? "unmet" : "open";
        const word = state === "met" ? "met" : state === "unmet" ? "not met" : "not evaluated";
        return `<li class="av-rule-check av-rule-check--${state}"><span class="av-rule-label">${esc(c.label)}</span><span class="av-rule-obs">${esc(c.observed)}</span>${c.threshold ? `<span class="av-rule-thr">${esc(c.threshold)}</span>` : "<span></span>"}<span class="av-rule-state"><span class="av-rule-dot" aria-hidden="true"></span>${word}</span></li>`;
      }).join("")}</ol>` : "";
  const rule = input.rule || checks
    ? `<aside class="av-rule"><h4 class="av-eyebrow">Decision rule${input.rule ? " · fixed before results" : ""}</h4>${input.rule ? `<blockquote class="av-rule-text">${prose(input.rule, "av-rule-prose")}</blockquote>` : ""}${checks}</aside>`
    : "";
  const body = `<div class="av-verdict-grid${rule ? "" : " av-verdict-grid--solo"}"><div class="av-verdict-main">${stamp}<p class="av-verdict-headline">${inline(input.headline)}</p>${prose(input.detail, "av-verdict-detail")}${lists ? `<div class="av-verdict-lists">${lists}</div>` : ""}</div>${rule}</div>`;
  return frame("verdict", { ...input, title: input.title }, body, { "data-verdict": kind });
}

// ------------------------------------------------------------------ figures

export interface FiguresInput extends FrameInput { items: Array<{ value: string | number | null; label: string; note?: string; tone?: "neutral" | "pass" | "fail" | "warn" | "invalid" }> }
export function figures(input: FiguresInput): string {
  const tones = ["neutral", "pass", "fail", "warn", "invalid"];
  const items = (input.items || []).map(i => {
    const t = tones.includes(i.tone as string) ? i.tone : "neutral";
    const v = i.value === null || i.value === undefined || (typeof i.value === "number" && !isNum(i.value))
      ? '<span class="av-missing">missing</span>'
      : typeof i.value === "number" ? esc(Number.isInteger(i.value) ? fmtInt(i.value) : fmtNum(i.value)) : esc(i.value);
    const text = typeof i.value === "string" && !/^[×x]?[\d.,]+%?$/.test(i.value);
    return `<div class="av-figure-stat av-tone--${t}"><dt>${esc(i.label)}</dt><dd><span class="av-figure-value${text ? " av-figure-value--text" : ""}">${v}</span>${i.note ? `<span class="av-figure-note">${esc(i.note)}</span>` : ""}</dd></div>`;
  }).join("");
  return frame("figures", input, `<dl class="av-figures-row">${items}</dl>`);
}

// ------------------------------------------------------------------ ladder

export interface LadderRow { arm: string; k: number; n: number; invalid?: number; note?: string }
export interface LadderInput extends FrameInput {
  rows?: LadderRow[];
  /** Restrict to one case, or to a set of cases; otherwise every run of each arm is pooled. */
  case?: string;
  cases?: string[];
  /** Groups of arms given identical material: their spread is visible noise. */
  identical?: string[][];
  /** An arm whose rate draws a reference line. */
  baseline?: string;
  /** Order rows by rate instead of by identity order. */
  sort?: "identity" | "rate";
  /** Thresholds to draw across every row, such as a decision rule's bar (rates in 0–1). */
  references?: Array<{ value: number; label: string }>;
}

export function ladder(input: LadderInput, ctx: RenderContext): string {
  let rows = input.rows;
  if (!rows) {
    const data = trialOf(ctx, "ladder");
    rows = trialAxes(data).arms.map(arm => {
      const t = tally(data.runs.filter(r => r.arm === arm && (!input.case || r.scenario === input.case) && (!input.cases || input.cases.includes(r.scenario))));
      return { arm, k: t.pass, n: t.valid, invalid: t.invalid };
    }).filter(r => r.n + (r.invalid || 0) > 0);
  }
  if (!rows.length) return frame("ladder", input, empty("No runs to show."));
  rows = rows.map(r => ({ ...r, arm: String(r.arm), k: count(r.k), n: count(r.n), invalid: count(r.invalid) })).map(r => ({ ...r, k: Math.min(r.k, r.n) }));
  if (input.sort === "rate") rows.sort((a, b) => (b.n ? b.k / b.n : -1) - (a.n ? a.k / a.n : -1));
  else rows.sort((a, b) => ctx.arms.index(a.arm) - ctx.arms.index(b.arm));
  // Identical groups sit together, in the position of their first member.
  const groups = (input.identical || []).map(g => g.filter(a => rows!.some(r => r.arm === a))).filter(g => g.length > 1);
  const grouped = new Map<string, number>();
  groups.forEach((g, i) => g.forEach(a => grouped.set(a, i)));
  const ordered: Array<LadderRow | { group: number; rows: LadderRow[] }> = [];
  const placed = new Set<number>();
  for (const r of rows) {
    const g = grouped.get(r.arm);
    if (g === undefined) ordered.push(r);
    else if (!placed.has(g)) { placed.add(g); ordered.push({ group: g, rows: groups[g].map(a => rows!.find(x => x.arm === a)!) }); }
  }
  const base = input.baseline ? rows.find(r => r.arm === input.baseline) : undefined;
  const baseRate = base && base.n ? base.k / base.n : null;

  const row = (r: LadderRow) => {
    const p = r.n ? r.k / r.n : null, ci = wilson(r.k, r.n);
    const style = `--c:${ctx.arms.color(r.arm)};${p !== null ? `--p:${pos(p)};` : ""}${ci ? `--lo:${pos(ci[0])};--hi:${pos(ci[1])};` : ""}`;
    const invalid = r.invalid ? `<span class="av-chip av-chip--invalid" title="Invalid runs are excluded, never counted as failures">${outcomeMark("invalid")}${fmtInt(r.invalid)} invalid</span>` : "";
    const thin = r.n > 0 && r.n < 5 ? `<span class="av-chip av-chip--warn" title="Too few valid runs for a reliable rate">n = ${r.n}</span>` : "";
    const label = `${p === null ? "no valid runs" : `${r.k} of ${r.n} valid runs passed, ${fmtPct(p)}`}${ci ? `, 95% interval ${fmtPct(ci[0])} to ${fmtPct(ci[1])}` : ""}${r.invalid ? `, ${r.invalid} invalid` : ""}`;
    return `<div class="av-ladder-row" role="row" data-arm="${esc(r.arm)}">
<div class="av-ladder-label" role="rowheader">${ctx.arms.tag(r.arm)}${r.note ? `<span class="av-ladder-note">${esc(r.note)}</span>` : ""}${r.arm === input.baseline || thin || invalid ? `<span class="av-ladder-flags">${r.arm === input.baseline ? '<span class="av-chip av-chip--base">baseline</span>' : ""}${thin}${invalid}</span>` : ""}</div>
<div class="av-ladder-track${p === null ? " av-ladder-track--empty" : ""}" role="cell" style="${style}" aria-label="${esc(label)}">${ci ? '<span class="av-ci"></span>' : ""}${p !== null ? '<span class="av-pt"></span>' : '<span class="av-ladder-none">no valid runs</span>'}</div>
<div class="av-ladder-num" role="cell"><span class="av-frac"><b>${r.k}</b>/${r.n}</span><span class="av-rate">${fmtPct(p)}</span>${ci ? `<span class="av-ci-text">${fmtPct(ci[0])}–${fmtPct(ci[1])}</span>` : ""}</div>
</div>`;
  };
  const body = ordered.map(item => {
    if (!("group" in item)) return row(item);
    const pts = item.rows.filter(r => r.n).map(r => r.k / r.n);
    const lo = pts.length ? Math.min(...pts) : 0, hi = pts.length ? Math.max(...pts) : 0;
    const spread = pts.length > 1 ? `${Math.round((hi - lo) * 100)} points apart` : "spread not measurable";
    return `<div class="av-ladder-group" role="rowgroup"><div class="av-ladder-group-label"><span class="av-eyebrow">Identical arms</span><span>${esc(spread)} — the noise between copies of the same material</span></div><div class="av-ladder-group-rows">${item.rows.map(row).join("")}${pts.length > 1 ? `<div class="av-noise" aria-hidden="true" style="--lo:${pos(lo)};--hi:${pos(hi)}"></div>` : ""}</div></div>`;
  }).join("");
  const ticks = [0, .25, .5, .75, 1].map(t => `<span style="--x:${pos(t)}">${t * 100}%</span>`).join("");
  const refs = [
    ...(baseRate !== null ? [{ value: baseRate, label: `${ctx.arms.label(input.baseline!)} ${fmtPct(baseRate)}`, kind: "base" }] : []),
    ...(input.references || []).filter(r => isNum(r.value)).map(r => ({ value: Math.max(0, Math.min(1, r.value)), label: String(r.label ?? ""), kind: "rule" })),
  ];
  const ref = refs.map(r => `<div class="av-ladder-ref av-ladder-ref--${r.kind}" aria-hidden="true" style="--x:${pos(r.value)}"><span>${esc(r.label)}</span></div>`).join("");
  const legend = `<p class="av-legend"><span><span class="av-legend-ci"></span>95% Wilson interval</span><span><span class="av-legend-pt"></span>pass rate over valid runs</span>${groups.length ? '<span><span class="av-legend-noise"></span>spread between identical arms</span>' : ""}${baseRate !== null ? '<span><span class="av-legend-ref"></span>baseline</span>' : ""}${(input.references || []).length ? '<span><span class="av-legend-ref av-legend-ref--rule"></span>threshold</span>' : ""}</p>`;
  return frame("ladder", { title: input.title, description: input.description, note: input.note, id: input.id },
    `${legend}<div class="av-ladder-grid${ref ? " av-ladder-grid--ref" : ""}" role="table" aria-label="${esc(input.title || "Pass rate by arm")}"><div class="av-ladder-axis" role="row" aria-hidden="true"><span></span><div class="av-ladder-ticks">${ticks}</div><span></span></div>${body}${ref}</div>`);
}

// ------------------------------------------------------------------ tapestry

export interface CaseGroup { label: string; cases: string[]; note?: string }
export interface TapestryInput extends FrameInput { arms?: string[]; cases?: string[]; transpose?: boolean; groups?: CaseGroup[] }

export function tapestry(input: TapestryInput, ctx: RenderContext): string {
  const data = trialOf(ctx, "tapestry");
  const axes = trialAxes(data);
  const arms = (input.arms || axes.arms).slice().sort((a, b) => ctx.arms.index(a) - ctx.arms.index(b)), cases = input.cases || axes.cases;
  if (!arms.length || !cases.length) return frame("tapestry", input, empty("No runs to show."));
  const transpose = input.groups?.length ? false : input.transpose ?? (arms.length > 8 && cases.length < arms.length);
  const cols = transpose ? cases : arms, rows = transpose ? arms : cases;
  const cell = (arm: string, cs: string) => {
    const runs = data.runs.filter(r => r.arm === arm && r.scenario === cs).sort((a, b) => (a.repeat ?? 0) - (b.repeat ?? 0));
    if (!runs.length) return `<div class="av-tap-cell av-tap-cell--none" role="cell"><span class="av-tap-none">not run</span></div>`;
    const t = tally(runs);
    const marks = runs.map(r => {
      const o = outcomeOf(r), i = ctx.runIndex.get(r);
      const judge = r.judge?.verdict ? ` · judge ${r.judge.verdict}` : "";
      const why = o === "invalid" ? ` · ${r.invalid_reason || r.status || "invalid"}` : "";
      const label = `${caseLabel(ctx, cs)} · ${ctx.arms.label(arm)} · repeat ${r.repeat ?? "?"}: ${outcomeLabel[o]}${judge}${why}`;
      return `<button type="button" class="av-run av-run--${o}"${attrs({ "data-run": i, title: label, "aria-label": label })}></button>`;
    }).join("");
    const share = t.valid ? t.pass / t.valid : null;
    const ci = t.interval;
    const summary = `${t.pass} of ${t.valid} valid runs passed${ci ? ` (95% interval ${fmtPct(ci[0])}–${fmtPct(ci[1])})` : ""}${t.invalid ? `; ${t.invalid} invalid` : ""}`;
    return `<div class="av-tap-cell" role="cell" style="--share:${share === null ? 0 : share};${ci ? `--lo:${pos(ci[0])};--hi:${pos(ci[1])};` : ""}" data-arm="${esc(arm)}" title="${esc(summary)}"><div class="av-tap-head"><span class="av-frac"><b>${t.pass}</b>/${t.valid}</span>${t.invalid ? `<span class="av-tap-inv" title="${t.invalid} invalid">${outcomeMark("invalid")}${t.invalid}</span>` : ""}</div><div class="av-tap-marks">${marks}</div><div class="av-tap-bar" aria-hidden="true">${ci ? '<i class="av-tap-ci"></i>' : ""}<span></span></div></div>`;
  };
  const head = `<div class="av-tap-row av-tap-row--head" role="row"><div class="av-tap-corner" role="columnheader"><span>${transpose ? "Arm" : "Case"}</span><span>${transpose ? "Case" : "Arm"} →</span></div>${cols.map(c => `<div class="av-tap-colhead" role="columnheader">${transpose ? `<span class="av-case-name">${esc(caseLabel(ctx, c))}</span>` : ctx.arms.tag(c, { id: false })}</div>`).join("")}</div>`;
  const line = (rw: string) => `<div class="av-tap-row" role="row"><div class="av-tap-rowhead" role="rowheader">${transpose ? ctx.arms.tag(rw, { id: false }) : `<span class="av-case-name">${esc(caseLabel(ctx, rw))}</span>`}</div>${cols.map(c => transpose ? cell(rw, c) : cell(c, rw)).join("")}</div>`;
  let body = "";
  if (input.groups?.length && !transpose) {
    const placed = new Set<string>();
    const groups = [...input.groups.map(g => ({ ...g, cases: g.cases.filter(c => rows.includes(c)) })), { label: "Other cases", cases: rows.filter(c => !input.groups!.some(g => g.cases.includes(c))) }].filter(g => g.cases.length);
    for (const g of groups) {
      const t = tally(data.runs.filter(r => g.cases.includes(r.scenario) && arms.includes(r.arm)));
      body += `<div class="av-tap-row av-tap-row--group" role="row"><div class="av-tap-group" role="rowheader"><span class="av-tap-group-label">${esc(g.label)}</span><span class="av-muted">${g.cases.length} case${g.cases.length === 1 ? "" : "s"} · ${t.pass}/${t.valid} passed${t.invalid ? ` · ${t.invalid} invalid` : ""}${g.note ? ` · ${esc(g.note)}` : ""}</span></div></div>`;
      body += g.cases.filter(c => !placed.has(c)).map(c => { placed.add(c); return line(c); }).join("");
    }
  } else body = rows.map(line).join("");
  const legend = `<p class="av-legend">${(["pass", "fail", "invalid"] as Outcome[]).map(o => `<span>${outcomeMark(o)}${o === "invalid" ? "invalid — excluded, not a failure" : outcomeLabel[o].toLowerCase()}</span>`).join("")}<span class="av-legend-hint">Each mark is one run; select it for its record.</span></p>`;
  return frame("tapestry", input, `${legend}<div class="av-scroll-x"><div class="av-tap" role="table" style="--cols:${cols.length}" aria-label="${esc(input.title || "Every run by case and arm")}">${head}${body}</div></div>`);
}

// ------------------------------------------------------------------ checks

export interface ChecksInput extends FrameInput { arms?: string[]; checks?: string[] }
export function checks(input: ChecksInput, ctx: RenderContext): string {
  const data = trialOf(ctx, "checks");
  const arms = (input.arms || trialAxes(data).arms).slice().sort((a, b) => ctx.arms.index(a) - ctx.arms.index(b));
  let rows = checkTable(data, arms);
  if (input.checks) rows = rows.filter(r => input.checks!.includes(r.name));
  const judged = data.runs.filter(r => r.judge && (r.judge.verdict === "pass" || r.judge.verdict === "fail"));
  if (!rows.length && !judged.length) return frame("checks", input, empty("No pass/fail checks were recorded."));
  const cell = (k: number, n: number, measure = false) => {
    if (!n) return `<td class="av-heat av-heat--none"><span>—</span></td>`;
    const s = k / n;
    return `<td class="av-heat${measure ? " av-heat--measure" : ""}" style="--s:${s.toFixed(3)}"><span class="av-frac"><b>${k}</b>/${n}</span><span class="av-heat-bar" aria-hidden="true"><span></span></span></td>`;
  };
  const head = `<thead><tr><th scope="col" class="av-heat-corner">Check</th>${arms.map(a => `<th scope="col">${ctx.arms.tag(a, { id: false })}</th>`).join("")}</tr></thead>`;
  const caseCount = new Set(data.runs.map(r => r.scenario)).size;
  const line = (r: typeof rows[number]) => `<tr><th scope="row"><code>${esc(r.name)}</code>${r.required && r.requiredIn.length < caseCount ? ` <span class="av-chip av-chip--req" title="${esc(r.requiredIn.join(", "))}">in ${r.requiredIn.length} of ${caseCount} cases</span>` : ""}</th>${arms.map(a => cell(r.cells[a].k, r.cells[a].n, !r.required)).join("")}</tr>`;
  const group = (label: string, note: string, items: typeof rows) => items.length ? `<tr class="av-heat-group"><th scope="rowgroup" colspan="${arms.length + 1}">${esc(label)} <span class="av-muted">· ${esc(note)}</span></th></tr>${items.map(line).join("")}` : "";
  const required = rows.filter(r => r.required), measures = rows.filter(r => !r.required);
  const judgeRow = judged.length ? `<tr class="av-heat-group"><th scope="rowgroup" colspan="${arms.length + 1}">Judge <span class="av-muted">· runs the judge passed, of valid judged runs</span></th></tr><tr><th scope="row">verdict = pass</th>${arms.map(a => { const js = judged.filter(r => r.arm === a && r.passed !== null); return cell(js.filter(r => r.judge!.verdict === "pass").length, js.length); }).join("")}</tr>` : "";
  const body = group("Required checks", "true is a pass; counted over the cases that require each one", required) + judgeRow + group("Recorded measures", "true or false with no pass direction; shaded by share, not by merit", measures);
  return frame("checks", input, `<div class="av-scroll-x"><table class="av-heatmap">${head}<tbody>${body}</tbody></table></div>`);
}

// ------------------------------------------------------------------ pairwise

export interface PairwiseInput extends FrameInput { pair?: string }
export function pairwise(input: PairwiseInput, ctx: RenderContext): string {
  const data = trialOf(ctx, "pairwise");
  const pairs = Object.entries(data.pairwise || {}).filter(([k]) => !input.pair || k === input.pair);
  if (!pairs.length) return frame("pairwise", input, empty("No pairwise judgments were run."));
  const segs = ["a_wins", "tie", "b_wins", "inconsistent", "invalid"] as const;
  const clean = (st: Partial<Record<string, unknown>> | undefined) => {
    const o = { a_wins: 0, tie: 0, b_wins: 0, inconsistent: 0, invalid: 0 };
    for (const k of segs) o[k] = count(st?.[k]);
    const rate = num(st?.a_win_rate), iv = Array.isArray(st?.a_win_rate_interval) ? (st!.a_win_rate_interval as unknown[]).map(num) : null;
    return { ...o, total: segs.reduce((n, k) => n + o[k], 0), rate, interval: iv && iv[0] !== null && iv[1] !== null ? [iv[0], iv[1]] as [number, number] : null };
  };
  const present = new Set<string>();
  let maxTotal = 1;
  for (const [, p] of pairs) for (const st of [p.overall, ...Object.values(p.scenarios || {})]) { const c = clean(st as never); maxTotal = Math.max(maxTotal, c.total); for (const k of segs) if (c[k]) present.add(k); }
  const html = pairs.map(([key, p]) => {
    const [a, b] = (Array.isArray(p.arms) ? p.arms : ["A", "B"]).map(String);
    const line = (label: string, raw: unknown, strong = false, scale = maxTotal) => {
      const s = clean(raw as never), total = s.total || 1;
      const bar = segs.map(k => s[k] ? `<span class="av-duel-seg av-duel-seg--${k}" style="flex:${s[k]}" title="${esc(`${k.replace("_", " ")}: ${s[k]}`)}">${s[k] / total > .08 ? s[k] : ""}</span>` : "").join("");
      const rate = s.rate !== null && s.interval ? `${fmtPct(s.rate)} <span class="av-ci-text">${fmtPct(s.interval[0])}–${fmtPct(s.interval[1])}</span>` : '<span class="av-muted">no decisive pairs</span>';
      return `<div class="av-duel-row${strong ? " av-duel-row--overall" : ""}"><span class="av-duel-label">${esc(label)}<span class="av-muted"> · ${s.total} pair${s.total === 1 ? "" : "s"}</span></span><div class="av-duel-track"><div class="av-duel-bar" style="width:${pos(s.total / scale)}" role="img" aria-label="${esc(`${label}: ${a} preferred ${s.a_wins}, ties ${s.tie}, ${b} preferred ${s.b_wins}, order-inconsistent ${s.inconsistent}, invalid ${s.invalid}`)}">${bar}</div></div><span class="av-duel-rate">${rate}</span></div>`;
    };
    const overall = clean(p.overall as never);
    const scenMax = Math.max(1, ...Object.values(p.scenarios || {}).map(st => clean(st as never).total));
    const scen = Object.entries(p.scenarios || {}).map(([s, st]) => line(caseLabel(ctx, s), st, false, scenMax)).join("");
    return `<div class="av-duel" data-pair="${esc(key)}"><div class="av-duel-head">${ctx.arms.tag(a)}<span class="av-duel-vs">preferred over</span>${ctx.arms.tag(b)}<span class="av-duel-rate-head">${esc(a)} win rate</span></div>${line("All cases", p.overall, true, Math.max(1, overall.total))}${scen}</div>`;
  }).join("");
  const words: Record<string, string> = { a_wins: "first arm preferred in both orders", tie: "tie in both orders", b_wins: "second arm preferred in both orders", inconsistent: "orders disagree", invalid: "invalid" };
  const legend = `<p class="av-legend">${segs.filter(k => present.has(k)).map(k => `<span><span class="av-sw av-duel-seg--${k}"></span>${words[k]}</span>`).join("")}<span>Bar length is the number of pairs.</span></p>`;
  return frame("pairwise", input, legend + html);
}

// ------------------------------------------------------------------ cost

export interface CostInput extends FrameInput { measures?: string[]; arms?: string[] }
export function cost(input: CostInput, ctx: RenderContext): string {
  const data = trialOf(ctx, "cost");
  const arms = (input.arms || trialAxes(data).arms).slice().sort((a, b) => ctx.arms.index(a) - ctx.arms.index(b));
  const measures = costMeasures(data).filter(m => !input.measures || input.measures.includes(m.id));
  if (!measures.length) return frame("cost", input, empty("No executor reported usage or timing."));
  const panels = measures.map(m => {
    // The axis describes valid runs. Invalid runs (timeouts, executor errors) are
    // counted beside each row instead: their cost is real, but it is not a
    // measurement of the arm doing the task, and one outlier would flatten the rest.
    const valid = data.runs.filter(r => r.passed !== null && arms.includes(r.arm));
    const values = valid.map(m.get).filter((v): v is number => isNum(v) && v >= 0);
    if (!values.length) return "";
    const positive = values.filter(v => v > 0).sort((a, b) => a - b);
    const min = Math.min(...values), hi = Math.max(...values), lo = positive[0] ?? 0;
    const log = positive.length > 1 && hi / Math.max(lo, 1e-9) > 40;
    // A linear axis starts at zero only when the data come near it; a strip of
    // marks has no bar length that a truncated axis would distort.
    let d0 = 0, d1 = hi || 1;
    if (!log) {
      const pad = (hi - min) * 0.08 || Math.abs(hi) * 0.05 || 1;
      if (min > (hi - min) * 1.5) { const t = niceTicks(min - pad, hi + pad, 4); d0 = t[0]; d1 = Math.max(hi, t[t.length - 1]); }
      else { const t = niceTicks(0, hi, 4); d1 = Math.max(hi, t[t.length - 1]); }
    }
    const x = (v: number) => log ? (Math.log10(Math.max(v, lo)) - Math.log10(lo)) / Math.max(1e-9, Math.log10(hi) - Math.log10(lo)) : (v - d0) / Math.max(1e-12, d1 - d0);
    const su = secondsUnit(log ? hi : d1);
    const fmt = (v: number | null, axis = false) => m.unit === "seconds" ? (axis ? (isNum(v) ? `${fmtNum(v / su.div)} ${su.unit}` : "—") : fmtSeconds(v)) : m.unit === "usd" ? fmtUsd(v) : fmtNum(v);
    const ticks = (log ? logTicks(lo, hi, 4) : niceTicks(d0, d1, 4).filter(t => t >= d0 - 1e-9 && t <= d1 + 1e-9));
    const rowsHtml = arms.map(a => {
      const runs = valid.filter(r => r.arm === a && isNum(m.get(r)));
      const invalidHere = data.runs.filter(r => r.arm === a && r.passed === null).length;
      if (!runs.length && !invalidHere) return "";
      const vals = runs.map(r => m.get(r)!).sort((p, q) => p - q), md = median(vals);
      const shown = runs.filter(r => !log || m.get(r)! > 0), atZero = runs.length - shown.length;
      const delta = data.baseline && a !== data.baseline ? num(data.pct_vs_baseline?.[a]?.[m.id === "seconds" ? "seconds_mean" : m.id === "commands" ? "commands_mean" : m.id]?.median) : null;
      const dots = shown.map((r, j) => {
        const o = outcomeOf(r), v = m.get(r)!;
        return `<button type="button" class="av-dot av-dot--${o}"${attrs({ "data-run": ctx.runIndex.get(r), style: `--x:${pos(x(v))};--j:${(j % 7) - 3}`, title: `${ctx.arms.label(a)} · ${caseLabel(ctx, r.scenario)} r${r.repeat ?? "?"}: ${fmt(v)} · ${outcomeLabel[o]}`, "aria-label": `${caseLabel(ctx, r.scenario)} repeat ${r.repeat ?? "?"}: ${fmt(v)}, ${outcomeLabel[o]}` })}></button>`;
      }).join("");
      const q1 = quantile(vals, .25), q3 = quantile(vals, .75);
      const iqr = q1 !== null && q3 !== null && (!log || q1 > 0) ? `<span class="av-iqr" style="--lo:${pos(x(q1))};--hi:${pos(x(q3))}"></span>` : "";
      const mdMark = md !== null && (!log || md > 0) ? `<span class="av-median" style="--x:${pos(x(md))}"></span>` : "";
      return `<div class="av-strip-row" data-arm="${esc(a)}" style="--c:${ctx.arms.color(a)}"><div class="av-strip-label">${ctx.arms.tag(a, { id: false })}</div><div class="av-strip-track">${iqr}${mdMark}${dots}</div><div class="av-strip-num">${md !== null ? `<span class="av-strong">${fmt(md)}</span><span class="av-muted">median</span>` : '<span class="av-muted">no valid runs</span>'}${delta !== null ? `<span class="av-delta" title="median across cases of the per-case difference from ${esc(data.baseline!)}">${fmtDelta(delta)}</span>` : ""}${atZero ? `<span class="av-zero" title="A log scale cannot place zero">${atZero} at 0</span>` : ""}${invalidHere ? `<span class="av-zero" title="Invalid runs are not placed on this axis">${outcomeMark("invalid")} ${invalidHere} not shown</span>` : ""}</div></div>`;
    }).join("");
    const axis = `<div class="av-strip-axis" aria-hidden="true"><span></span><div class="av-strip-ticks">${ticks.map(t => `<span style="--x:${pos(x(t))}">${fmt(t, true)}</span>`).join("")}</div><span></span></div>`;
    return `<div class="av-strip-panel"><h4 class="av-strip-title">${esc(m.label)}${log ? ' <span class="av-muted">· log scale</span>' : d0 > 0 ? ' <span class="av-muted">· axis starts at ' + esc(fmt(d0, true)) + "</span>" : ""}</h4>${rowsHtml}${axis}</div>`;
  }).join("");
  const legend = `<p class="av-legend"><span>${outcomeMark("pass")}one valid run, passed</span><span>${outcomeMark("fail")}failed</span><span><span class="av-legend-iqr"></span>middle half</span><span><span class="av-legend-median"></span>median</span>${data.runs.some(r => r.passed === null) ? `<span>${outcomeMark("invalid")}invalid runs are counted, not placed</span>` : ""}${data.baseline ? `<span>Δ vs ${esc(ctx.arms.label(data.baseline))}: median per-case difference</span>` : ""}</p>`;
  return frame("cost", input, legend + `<div class="av-strips">${panels}</div>`);
}

// ------------------------------------------------------------------ invalid

export function invalid(input: FrameInput, ctx: RenderContext): string {
  const data = trialOf(ctx, "invalid");
  const bad = data.runs.filter(r => r.passed === null);
  if (!bad.length) return frame("invalid", input, `<p class="av-allclear">${outcomeMark("pass")}Every run finished with a valid result.</p>`);
  const by = new Map<string, TrialRun[]>();
  for (const r of bad) { const k = r.invalid_reason || r.status || "unknown"; by.set(k, [...(by.get(k) || []), r]); }
  const groups = [...by.entries()].sort((a, b) => b[1].length - a[1].length).map(([reason, runs]) => {
    const perArm = new Map<string, number>();
    for (const r of runs) perArm.set(r.arm, (perArm.get(r.arm) || 0) + 1);
    const chips = [...perArm.entries()].sort((a, b) => b[1] - a[1]).map(([a, n]) => `<span class="av-inv-arm">${ctx.arms.tag(a, { id: false })}<b>${n}</b></span>`).join("");
    const sample = runs[0]?.final_message_excerpt ? `<p class="av-inv-sample"><span class="av-eyebrow">First message</span> ${esc(runs[0].final_message_excerpt.slice(0, 220))}${runs[0].final_message_excerpt.length > 220 ? "…" : ""}</p>` : "";
    const marks = runs.map(r => `<button type="button" class="av-run av-run--invalid"${attrs({ "data-run": ctx.runIndex.get(r), title: `${caseLabel(ctx, r.scenario)} · ${ctx.arms.label(r.arm)} · repeat ${r.repeat ?? "?"}`, "aria-label": `Invalid run: ${caseLabel(ctx, r.scenario)}, ${ctx.arms.label(r.arm)}, repeat ${r.repeat ?? "?"}` })}></button>`).join("");
    return `<div class="av-inv-group"><div class="av-inv-head"><code class="av-inv-reason">${esc(reason)}</code><span class="av-inv-count">${runs.length} run${runs.length === 1 ? "" : "s"}</span></div><div class="av-inv-arms">${chips}</div>${sample}<div class="av-tap-marks av-inv-marks">${marks}</div></div>`;
  }).join("");
  const share = bad.length / Math.max(1, data.runs.length);
  return frame("invalid", { ...input, description: input.description ?? `${bad.length} of ${data.runs.length} runs (${fmtPct(share)}) produced no valid result. They are excluded from every rate above and never counted as failures; rerunning them (trial.py run --retry-invalid) is the remedy.` }, `<div class="av-inv">${groups}</div>`);
}

// ------------------------------------------------------------------ ledger

export type LedgerInput = FrameInput;
export function ledger(input: LedgerInput, ctx: RenderContext): string {
  const data = trialOf(ctx, "ledger");
  if (!data.runs.length) return frame("ledger", input, empty("No runs."));
  const axes = trialAxes(data);
  const tokens = costMeasures(data).find(m => m.id === "output_tokens");
  const rows = data.runs.map((r, i) => {
    const o = outcomeOf(r), tk = tokens ? num(tokens.get(r)) : null, sec = num(r.seconds);
    return `<tr${attrs({ "data-run": i, "data-arm": r.arm, "data-case": r.scenario, "data-outcome": o, tabindex: 0 })}><td class="av-num">${i + 1}</td><td>${outcomeBadge(o)}</td><td>${esc(caseLabel(ctx, r.scenario))}</td><td>${ctx.arms.tag(r.arm, { id: false })}</td><td class="av-num">${esc(num(r.repeat) ?? "")}</td><td>${r.judge?.verdict ? `<span class="av-judge av-judge--${esc(r.judge.verdict)}">${esc(r.judge.verdict)}</span>` : '<span class="av-muted">—</span>'}</td>${tokens ? `<td class="av-num" data-sort="${tk ?? -1}">${fmtNum(tk)}</td>` : ""}<td class="av-num" data-sort="${sec ?? -1}">${fmtSeconds(sec)}</td><td class="av-why"><span>${esc(o === "invalid" ? (r.invalid_reason || r.status || "") : String(r.judge?.reason || "").slice(0, 240))}</span></td></tr>`;
  }).join("");
  const opts = (items: string[], label: (x: string) => string) => items.map(x => `<option value="${esc(x)}">${esc(label(x))}</option>`).join("");
  const counts = tally(data.runs);
  const filters = `<div class="av-ledger-tools" data-av-ledger-tools hidden>
<div class="av-seg" role="group" aria-label="Outcome"><button type="button" aria-pressed="true" data-outcome="">All <span>${counts.runs}</span></button><button type="button" aria-pressed="false" data-outcome="pass">${outcomeMark("pass")}Passed <span>${counts.pass}</span></button><button type="button" aria-pressed="false" data-outcome="fail">${outcomeMark("fail")}Failed <span>${counts.fail}</span></button><button type="button" aria-pressed="false" data-outcome="invalid">${outcomeMark("invalid")}Invalid <span>${counts.invalid}</span></button></div>
<label class="av-field"><span>Arm</span><select data-filter="arm"><option value="">All arms</option>${opts(axes.arms, a => ctx.arms.label(a))}</select></label>
<label class="av-field"><span>Case</span><select data-filter="case"><option value="">All cases</option>${opts(axes.cases, c => caseLabel(ctx, c))}</select></label>
<label class="av-field av-field--grow"><span>Search</span><input type="search" data-filter="text" placeholder="judge reasons, invalid causes…"></label>
<output class="av-ledger-count" aria-live="polite"></output></div>`;
  const head = `<thead><tr><th scope="col" data-sortable="num" class="av-num">#</th><th scope="col" data-sortable>Outcome</th><th scope="col" data-sortable>Case</th><th scope="col" data-sortable>Arm</th><th scope="col" data-sortable="num" class="av-num">Rep</th><th scope="col" data-sortable>Judge</th>${tokens ? '<th scope="col" data-sortable="num" class="av-num">Tokens out</th>' : ""}<th scope="col" data-sortable="num" class="av-num">Time</th><th scope="col">Reason</th></tr></thead>`;
  return frame("ledger", { ...input, description: input.description ?? "Every run, filterable. Select a row for the run's checks, judge reason, output excerpt and the location of its native record." }, `${filters}<div class="av-scroll-x av-ledger-wrap"><table class="av-ledger">${head}<tbody>${rows}</tbody></table></div>`);
}

// ------------------------------------------------------------------ plan

export function plan(input: FrameInput, ctx: RenderContext): string {
  const data = trialOf(ctx, "plan");
  const armIds = trialAxes(data).arms, settings = data.plan?.arms || {};
  const keys = ["executor", "model", "effort", "model_spec", "instructions_sha256", "artifact_sha256", "resources_sha256"];
  const present = keys.filter(k => armIds.some(a => settings[a]?.[k] !== undefined && settings[a]?.[k] !== null));
  const cellText = (k: string, v: unknown) => v === undefined || v === null ? '<span class="av-muted">—</span>' : /sha256$/.test(k) && typeof v === "string" ? `<code title="${esc(v)}">${esc(v.slice(0, 10))}</code>` : `<code>${esc(typeof v === "string" ? v : JSON.stringify(v))}</code>`;
  const armTable = `<div class="av-scroll-x"><table class="av-table av-plan-arms"><thead><tr><th scope="col">Arm</th>${present.map(k => `<th scope="col">${esc(k.replace(/_sha256$/, " digest").replace(/_/g, " "))}</th>`).join("")}</tr></thead><tbody>${armIds.map(a => `<tr><th scope="row">${ctx.arms.tag(a)}${ctx.arms.note(a) ? `<span class="av-ladder-note">${esc(ctx.arms.note(a)!)}</span>` : ""}</th>${present.map(k => `<td>${cellText(k, settings[a]?.[k])}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
  const ran = new Set(data.runs.map(r => r.scenario));
  const cases = (data.plan?.scenarios || []).filter(s => ran.has(s.name)).map(s => {
    const q = judgeQuestion(s);
    return `<details class="av-case"><summary><span class="av-case-name">${esc(caseLabel(ctx, s.name))}</span>${caseLabel(ctx, s.name) !== s.name ? `<code>${esc(s.name)}</code>` : ""}<span class="av-case-tags">${(s.required || []).length ? `<span class="av-chip av-chip--req">${s.required!.length} required check${s.required!.length === 1 ? "" : "s"}</span>` : ""}${q ? '<span class="av-chip">judged</span>' : ""}${(s.followups || []).length ? `<span class="av-chip">${s.followups!.length} follow-up${s.followups!.length === 1 ? "" : "s"}</span>` : ""}</span></summary><div class="av-case-body">${s.prompt ? `<h5>Prompt</h5><pre class="av-pre">${esc(s.prompt)}</pre>` : ""}${(s.followups || []).map((f, i) => `<h5>Follow-up ${i + 1}</h5><pre class="av-pre">${esc(f)}</pre>`).join("")}${q ? `<h5>Judge question</h5><pre class="av-pre">${esc(q)}</pre>` : ""}${(s.required || []).length ? `<h5>Required checks</h5><p>${s.required!.map(c => `<code>${esc(c)}</code>`).join(" ")}</p>` : ""}</div></details>`;
  }).join("");
  const judge = data.plan?.judge ? `<p class="av-plan-judge"><span class="av-eyebrow">Judge</span> ${Object.entries(data.plan.judge).filter(([k]) => ["executor", "model", "effort"].includes(k)).map(([k, v]) => `${esc(k)} <code>${esc(v)}</code>`).join(" · ")}</p>` : "";
  const dir = data.run_directory ? `<p class="av-plan-judge"><span class="av-eyebrow">Run directory</span> <code>${esc(data.run_directory)}</code></p>` : "";
  return frame("plan", input, `${armTable}${judge}${dir}<div class="av-cases">${cases}</div>`);
}
