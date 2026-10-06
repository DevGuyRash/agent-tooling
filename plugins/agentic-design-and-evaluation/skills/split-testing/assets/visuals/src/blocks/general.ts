/** General evidence views a report composes alongside, or instead of, trial
 * views: text, callouts, lists, facts, tables, requirement matrices, interval
 * comparisons, composition bars, trends across rounds, excerpts and diagrams. */
import { attrs, count, esc, fmtNum, fmtPct, inline, isNum, isOutcome, niceTicks, num, Outcome, outcomeBadge, outcomeMark, prose, wilson } from "../core";
import { mermaidDiagram } from "../figures";
import type { RenderContext } from "../model";
import { empty, frame, FrameInput, pos } from "./frame";

type Tone = "neutral" | "pass" | "fail" | "invalid" | "warn" | "accent";
const tones: Tone[] = ["neutral", "pass", "fail", "invalid", "warn", "accent"];
const tone = (t: unknown): Tone => tones.includes(t as Tone) ? t as Tone : "neutral";

// ------------------------------------------------------------------ text

export interface TextInput extends FrameInput { text: string | string[] }
export function text(input: TextInput): string {
  return frame("text", input, prose(input.text));
}

export interface CalloutInput extends FrameInput { tone?: Tone | "note" | "limit"; label?: string; text: string | string[] }
export function callout(input: CalloutInput): string {
  const t = input.tone === "note" ? "accent" : input.tone === "limit" ? "warn" : tone(input.tone);
  const label = input.label || ({ neutral: "Note", pass: "Holds", fail: "Problem", invalid: "Not measured", warn: "Limit", accent: "Note" } as Record<Tone, string>)[t];
  return frame("callout", { id: input.id }, `<div class="av-callout-box av-tone--${t}"><span class="av-eyebrow">${esc(label)}</span>${input.title ? `<p class="av-callout-title">${inline(input.title)}</p>` : ""}${prose(input.text)}</div>`);
}

export interface ListInput extends FrameInput { items: Array<string | { text: string; tone?: Tone; detail?: string }>; ordered?: boolean }
export function list(input: ListInput): string {
  const tag = input.ordered ? "ol" : "ul";
  const items = (input.items || []).map(i => typeof i === "string" ? `<li>${inline(i)}</li>` : `<li class="av-tone--${tone(i.tone)}">${inline(i.text)}${i.detail ? `<span class="av-li-detail">${inline(i.detail)}</span>` : ""}</li>`).join("");
  return frame("list", input, `<${tag} class="av-list">${items}</${tag}>`);
}

export interface FactsInput extends FrameInput { items: Array<{ label: string; value: string | number | null; mono?: boolean }> }
export function facts(input: FactsInput): string {
  const rows = (input.items || []).map(i => `<div><dt>${esc(i.label)}</dt><dd>${i.value === null || i.value === undefined ? missing() : i.mono ? `<code>${esc(i.value)}</code>` : inline(String(i.value))}</dd></div>`).join("");
  return frame("facts", input, `<dl class="av-facts">${rows}</dl>`);
}

const missing = (why = "missing") => `<span class="av-missing" title="No value was recorded">${esc(why)}</span>`;

// ------------------------------------------------------------------ table

export type Cell = string | number | boolean | null | { value: string | number | boolean | null; status?: Tone | Outcome; note?: string; mono?: boolean };
export interface TableInput extends FrameInput { columns: string[]; rows: Cell[][]; numeric?: number[]; rowHeader?: boolean }
export function table(input: TableInput): string {
  const cols = input.columns || [], numeric = new Set(input.numeric || []);
  const cell = (c: Cell, i: number, header: boolean) => {
    const o = c !== null && typeof c === "object" ? c : { value: c };
    const status = o.status ? (o.status === "pass" || o.status === "fail" || o.status === "invalid" ? o.status : tone(o.status)) : undefined;
    const v = o.value === null || o.value === undefined ? missing() : typeof o.value === "boolean" ? (o.value ? "yes" : "no") : o.mono ? `<code>${esc(o.value)}</code>` : esc(o.value);
    const mark = status === "pass" || status === "fail" || status === "invalid" ? outcomeMark(status) : "";
    const tag = header ? "th" : "td";
    return `<${tag}${attrs({ scope: header ? "row" : undefined, class: [numeric.has(i) || typeof o.value === "number" ? "av-num" : "", status ? `av-cell--${status}` : ""].filter(Boolean).join(" ") || undefined })}>${mark}${v}${o.note ? `<span class="av-cell-note">${esc(o.note)}</span>` : ""}</${tag}>`;
  };
  const head = `<thead><tr>${cols.map((c, i) => `<th scope="col"${numeric.has(i) ? ' class="av-num"' : ""}>${esc(c)}</th>`).join("")}</tr></thead>`;
  const body = (input.rows || []).map(r => `<tr>${cols.map((_, i) => cell(r[i] === undefined ? null : r[i], i, input.rowHeader !== false && i === 0)).join("")}</tr>`).join("");
  return frame("table", input, (input.rows || []).length ? `<div class="av-scroll-x"><table class="av-table">${head}<tbody>${body}</tbody></table></div>` : empty("No rows."));
}

// ------------------------------------------------------------------ matrix

export interface MatrixInput extends FrameInput {
  columns: Array<{ id: string; label: string; arm?: boolean }>;
  rows: Array<{ id: string; label: string; detail?: string }>;
  cells: Array<{ row: string; column: string; status?: Tone | Outcome | "missing"; text?: string; note?: string }>;
}
export function matrix(input: MatrixInput, ctx: RenderContext): string {
  const find = (r: string, c: string) => (input.cells || []).find(x => x.row === r && x.column === c);
  const head = `<thead><tr><th scope="col" class="av-heat-corner"></th>${input.columns.map(c => `<th scope="col">${c.arm ? ctx.arms.tag(c.id, { id: false }) : esc(c.label)}</th>`).join("")}</tr></thead>`;
  const body = input.rows.map(r => `<tr><th scope="row">${esc(r.label)}${r.detail ? `<span class="av-cell-note">${esc(r.detail)}</span>` : ""}</th>${input.columns.map(c => {
    const x = find(r.id, c.id);
    if (!x || x.status === "missing") return `<td class="av-mx av-mx--missing">${missing("not established")}${x?.note ? `<span class="av-cell-note">${esc(x.note)}</span>` : ""}</td>`;
    const s = x.status === "pass" || x.status === "fail" || x.status === "invalid" ? x.status : tone(x.status);
    const mark = s === "pass" || s === "fail" || s === "invalid" ? outcomeMark(s) : "";
    return `<td class="av-mx av-mx--${s}">${mark}<span>${esc(x.text || "")}</span>${x.note ? `<span class="av-cell-note">${esc(x.note)}</span>` : ""}</td>`;
  }).join("")}</tr>`).join("");
  return frame("matrix", input, `<div class="av-scroll-x"><table class="av-matrix">${head}<tbody>${body}</tbody></table></div>`);
}

// ------------------------------------------------------------------ intervals

export interface IntervalsInput extends FrameInput {
  rows: Array<{ label: string; arm?: string; k?: number; n?: number; value?: number | null; lo?: number | null; hi?: number | null; note?: string }>;
  /** Value domain; rates default to [0, 1]. */
  domain?: [number, number];
  unit?: string;
  percent?: boolean;
  reference?: { value: number; label: string };
}
export function intervals(input: IntervalsInput, ctx: RenderContext): string {
  const rows = (input.rows || []).map(r => {
    if (isNum(r.k) && isNum(r.n)) { const k = count(r.k), n = count(r.n), ci = wilson(Math.min(k, n), n); return { ...r, k: Math.min(k, n), n, value: n ? Math.min(k, n) / n : null, lo: ci?.[0] ?? null, hi: ci?.[1] ?? null }; }
    return { ...r, k: undefined, n: undefined, value: num(r.value), lo: num(r.lo), hi: num(r.hi) };
  });
  const percent = input.percent ?? rows.every(r => r.k !== undefined || (isNum(r.value) && r.value >= 0 && r.value <= 1));
  const nums = rows.flatMap(r => [r.value, r.lo, r.hi]).filter(isNum);
  if (input.reference && isNum(input.reference.value)) nums.push(input.reference.value);
  const domain = input.domain || (percent ? [0, 1] as [number, number] : [Math.min(0, ...nums), Math.max(...nums, 1e-9)] as [number, number]);
  const x = (v: number) => (v - domain[0]) / Math.max(1e-12, domain[1] - domain[0]);
  const f = (v: number | null | undefined) => esc(percent ? fmtPct(v) : `${fmtNum(v)}${input.unit ? " " + input.unit : ""}`);
  const ticks = percent ? [0, .25, .5, .75, 1].filter(t => t >= domain[0] && t <= domain[1]) : niceTicks(domain[0], domain[1], 4);
  const body = rows.map(r => {
    const color = r.arm ? ctx.arms.color(r.arm) : "var(--av-ink-2)";
    const has = isNum(r.value);
    const style = `--c:${color};${has ? `--p:${pos(x(r.value!))};` : ""}${isNum(r.lo) && isNum(r.hi) ? `--lo:${pos(x(r.lo))};--hi:${pos(x(r.hi))};` : ""}`;
    const frac = isNum(r.k) && isNum(r.n) ? `<span class="av-frac"><b>${r.k}</b>/${r.n}</span>` : "";
    return `<div class="av-ladder-row" role="row"><div class="av-ladder-label" role="rowheader">${r.arm ? ctx.arms.tag(r.arm, { id: false }) : `<span class="av-arm-label">${esc(r.label)}</span>`}${r.arm && r.label && r.label !== ctx.arms.label(r.arm) ? `<span class="av-ladder-note">${esc(r.label)}</span>` : ""}${r.note ? `<span class="av-ladder-note">${esc(r.note)}</span>` : ""}</div><div class="av-ladder-track${has ? "" : " av-ladder-track--empty"}" role="cell" style="${style}">${isNum(r.lo) && isNum(r.hi) ? '<span class="av-ci"></span>' : ""}${has ? '<span class="av-pt"></span>' : '<span class="av-ladder-none">no value</span>'}</div><div class="av-ladder-num" role="cell">${frac}<span class="av-rate">${f(r.value)}</span>${isNum(r.lo) && isNum(r.hi) ? `<span class="av-ci-text">${f(r.lo)}–${f(r.hi)}</span>` : ""}</div></div>`;
  }).join("");
  const ref = input.reference && isNum(input.reference.value) ? `<div class="av-ladder-ref" aria-hidden="true" style="--x:${pos(x(input.reference.value))}"><span>${esc(input.reference.label)}</span></div>` : "";
  return frame("ladder", input, `<div class="av-ladder-grid${ref ? " av-ladder-grid--ref" : ""}" role="table"><div class="av-ladder-axis" role="row" aria-hidden="true"><span></span><div class="av-ladder-ticks">${ticks.map(t => `<span style="--x:${pos(x(t))}">${f(t)}</span>`).join("")}</div><span></span></div>${body}${ref}</div>`);
}

// ------------------------------------------------------------------ bars

export interface BarsInput extends FrameInput {
  segments: Array<{ id: string; label: string; tone?: Tone }>;
  rows: Array<{ label: string; arm?: string; values: Record<string, number | null>; note?: string }>;
}
export function bars(input: BarsInput, ctx: RenderContext): string {
  const segs = input.segments || [];
  const sum = (r: BarsInput["rows"][number]) => segs.reduce((n, s) => n + (isNum(r.values?.[s.id]) && r.values[s.id]! > 0 ? r.values[s.id]! : 0), 0);
  const maxTotal = Math.max(1e-12, ...(input.rows || []).map(sum));
  const rows = (input.rows || []).map(r => {
    r = { ...r, values: r.values || {} };
    const total = sum(r);
    const parts = segs.map(s => { const v = r.values[s.id]; return isNum(v) && v > 0 ? `<span class="av-bar-seg av-tone--${tone(s.tone)}" style="flex:${v}" title="${esc(`${s.label}: ${v}`)}">${total && v / total > .07 ? fmtNum(v) : ""}</span>` : ""; }).join("");
    const absent = segs.filter(s => !isNum(r.values[s.id])).map(s => s.label);
    return `<div class="av-bar-row"><div class="av-bar-label">${r.arm ? ctx.arms.tag(r.arm, { id: false }) : esc(r.label)}${r.arm && r.label && r.label !== ctx.arms.label(r.arm) ? `<span class="av-ladder-note">${esc(r.label)}</span>` : ""}${r.note ? `<span class="av-ladder-note">${esc(r.note)}</span>` : ""}</div><div class="av-bar-track"><div class="av-bar" style="width:${pos(total / maxTotal)}" role="img" aria-label="${esc(`${r.label}: ${segs.map(s => `${s.label} ${isNum(r.values[s.id]) ? r.values[s.id] : "missing"}`).join(", ")}`)}">${parts || '<span class="av-bar-empty">no values</span>'}</div></div><div class="av-bar-total">${fmtNum(total)}${absent.length ? `<span class="av-missing" title="${esc(absent.join(", "))} not recorded">${absent.length} missing</span>` : ""}</div></div>`;
  }).join("");
  const legend = `<p class="av-legend">${segs.map(s => `<span><span class="av-sw av-tone--${tone(s.tone)}"></span>${esc(s.label)}</span>`).join("")}</p>`;
  return frame("bars", input, legend + `<div class="av-bars">${rows}</div>`);
}

// ------------------------------------------------------------------ trend

export interface TrendInput extends FrameInput {
  /** Ordered stages: rounds, revisions, dates. */
  stages: string[];
  series: Array<{ label: string; arm?: string; points: Array<{ stage: string; k?: number; n?: number; value?: number | null; lo?: number | null; hi?: number | null }> }>;
  percent?: boolean;
  unit?: string;
}
export function trend(input: TrendInput, ctx: RenderContext): string {
  const stages = input.stages || [], W = 760, H = 300, L = 56, R = 150, T = 18, B = 40;
  const series = (input.series || []).map(s => ({ ...s, points: s.points.map(p => {
    if (isNum(p.k) && isNum(p.n)) { const n = count(p.n), k = Math.min(count(p.k), n), ci = wilson(k, n); return { ...p, k, n, value: n ? k / n : null, lo: ci?.[0] ?? null, hi: ci?.[1] ?? null }; }
    return { ...p, k: undefined, n: undefined, value: num(p.value), lo: num(p.lo), hi: num(p.hi) };
  }) }));
  const vals = series.flatMap(s => s.points.flatMap(p => [p.value, p.lo, p.hi])).filter(isNum);
  if (!stages.length || !vals.length) return frame("trend", input, empty("No values to plot."));
  const percent = input.percent ?? series.every(s => s.points.every(p => p.k !== undefined || !isNum(p.value) || (p.value >= 0 && p.value <= 1)));
  const [d0, d1] = percent ? [0, 1] : [Math.min(0, ...vals), Math.max(...vals)];
  const ticks = percent ? [0, .25, .5, .75, 1] : niceTicks(d0, d1, 4);
  const top = Math.max(d1, ticks[ticks.length - 1]), bottom = Math.min(d0, ticks[0]);
  const X = (i: number) => L + (stages.length === 1 ? (W - L - R) / 2 : i * (W - L - R) / (stages.length - 1));
  const Y = (v: number) => T + (1 - (v - bottom) / Math.max(1e-12, top - bottom)) * (H - T - B);
  const f = (v: number) => percent ? fmtPct(v) : `${fmtNum(v)}${input.unit ? " " + input.unit : ""}`;
  const grid = ticks.map(t => `<line x1="${L}" x2="${W - R}" y1="${Y(t).toFixed(1)}" y2="${Y(t).toFixed(1)}" class="av-svg-grid"/><text x="${L - 8}" y="${(Y(t) + 4).toFixed(1)}" text-anchor="end" class="av-svg-tick">${esc(f(t))}</text>`).join("");
  const xs = stages.map((s, i) => `<text x="${X(i).toFixed(1)}" y="${H - B + 22}" text-anchor="middle" class="av-svg-tick">${esc(s)}</text>`).join("");
  const labels: Array<{ y: number; html: string }> = [];
  const dodge = (si: number) => (si - (series.length - 1) / 2) * Math.min(7, 28 / Math.max(1, series.length));
  const lines = series.map((s, si) => {
    const Xs = (i: number) => X(i) + dodge(si);
    const color = s.arm ? ctx.arms.color(s.arm) : `var(--av-arm-${si % 8})`;
    const pts = stages.map((st, i) => ({ i, p: s.points.find(p => p.stage === st) })).filter(o => o.p && isNum(o.p.value)) as Array<{ i: number; p: { value: number; lo?: number | null; hi?: number | null; k?: number; n?: number } }>;
    // A stage without a value breaks the line rather than bridging the gap.
    const path = pts.map((o, j) => `${j && pts[j - 1].i === o.i - 1 ? "L" : "M"}${Xs(o.i).toFixed(1)},${Y(o.p.value).toFixed(1)}`).join("");
    const whiskers = pts.filter(o => isNum(o.p.lo) && isNum(o.p.hi)).map(o => `<line x1="${Xs(o.i).toFixed(1)}" x2="${Xs(o.i).toFixed(1)}" y1="${Y(o.p.lo!).toFixed(1)}" y2="${Y(o.p.hi!).toFixed(1)}" class="av-svg-whisker"/>`).join("");
    const dots = pts.map(o => `<circle cx="${Xs(o.i).toFixed(1)}" cy="${Y(o.p.value).toFixed(1)}" r="4.5" class="av-svg-dot"><title>${esc(`${s.label} · ${stages[o.i]}: ${f(o.p.value)}${isNum(o.p.k) ? ` (${o.p.k}/${o.p.n})` : ""}`)}</title></circle>`).join("");
    const last = pts[pts.length - 1];
    if (last) labels.push({ y: Y(last.p.value), html: `<text x="${W - R + 12}" class="av-svg-label" style="fill:${color}">${esc(s.label)}</text>` });
    return `<g style="--c:${color}" class="av-svg-series">${whiskers}<path d="${path}" class="av-svg-line"/>${dots}</g>`;
  }).join("");
  // Keep end labels from colliding.
  labels.sort((a, b) => a.y - b.y);
  for (let i = 1; i < labels.length; i++) if (labels[i].y - labels[i - 1].y < 15) labels[i].y = labels[i - 1].y + 15;
  const endLabels = labels.map(l => l.html.replace("<text ", `<text y="${(l.y + 4).toFixed(1)}" `)).join("");
  const svgText = `<svg viewBox="0 0 ${W} ${H}" class="av-svg" role="img" aria-label="${esc(input.title || "Trend across stages")}"><title>${esc(input.title || "Trend across stages")}</title>${grid}${xs}${lines}${endLabels}</svg>`;
  const tableRows = series.map(s => `<tr><th scope="row">${esc(s.label)}</th>${stages.map(st => { const p = s.points.find(q => q.stage === st); return `<td class="av-num">${p && isNum(p.value) ? esc(f(p.value)) + (isNum(p.k) ? ` <span class="av-muted">${p.k}/${p.n}</span>` : "") : missing()}</td>`; }).join("")}</tr>`).join("");
  return frame("trend", input, `<div class="av-scroll-x"><div class="av-svg-wrap">${svgText}</div></div><details class="av-data"><summary>Values</summary><div class="av-scroll-x"><table class="av-table"><thead><tr><th scope="col">Series</th>${stages.map(s => `<th scope="col" class="av-num">${esc(s)}</th>`).join("")}</tr></thead><tbody>${tableRows}</tbody></table></div></details>`);
}

// ------------------------------------------------------------------ excerpts

export interface ExcerptsInput extends FrameInput { items: Array<{ text: string; source?: string; arm?: string; outcome?: Outcome; note?: string }> }
export function excerpts(input: ExcerptsInput, ctx: RenderContext): string {
  const items = (input.items || []).map(i => ({ ...i, outcome: isOutcome(i.outcome) ? i.outcome : undefined })).map(i => `<figure class="av-quote${i.outcome ? ` av-quote--${i.outcome}` : ""}"${i.arm ? ` style="--c:${ctx.arms.color(i.arm)}"` : ""}><blockquote>${esc(i.text)}</blockquote><figcaption>${i.outcome ? outcomeBadge(i.outcome) : ""}${i.arm ? ctx.arms.tag(i.arm, { id: false }) : ""}${i.source ? `<span class="av-quote-src">${esc(i.source)}</span>` : ""}${i.note ? `<span class="av-cell-note">${esc(i.note)}</span>` : ""}</figcaption></figure>`).join("");
  return frame("excerpts", input, `<div class="av-quotes">${items}</div>`);
}

// ------------------------------------------------------------------ diagram

export interface DiagramInput extends FrameInput { source: string; caption?: string; config?: Record<string, unknown> }
export function diagram(input: DiagramInput, ctx: RenderContext): string {
  return frame("diagram", { id: input.id, description: input.description, note: input.note },
    mermaidDiagram({ id: ctx.uid(input.title || "diagram"), title: input.title || "Diagram", source: input.source, caption: input.caption, config: input.config }));
}
