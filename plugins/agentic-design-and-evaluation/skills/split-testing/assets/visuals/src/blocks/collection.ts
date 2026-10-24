/** Views of a collection of reports: the decision board, the report index,
 * shifts across reports, cost against gain, the timeline, suggested pairs and
 * two reports side by side. Each reads the specification's `collection`, takes
 * `members` (in that order) or `themes` to draw a subset, and links every
 * report to its full reading (#report/ID) and every pair to its side-by-side
 * view (#compare/A/B). Every setup keeps the color and shape it has in its own
 * report; every value is the member's own headline value on its measure (a
 * pass rate, or a comparison's primary metric of any kind), and a change is
 * colored good or bad only by that measure's direction. */
import { attrs, axisTicks, esc, fmtInt, fmtNum, fmtPct, fmtUsd, gridlines, inline, isNum, niceTicks, prose, ticksHtml, tipAttr } from "../core";
import type { Tick } from "../core";
import { createContext } from "../model";
import type { RenderContext, ReportSpec } from "../model";
import { renderBlock } from "../report";
import { fmtDates } from "../compose";
import { caseBalanced, caseCell, collectionModel, matchRows, measureDomain, measureKey, measuresApart, relativeMeasure, sameMeasure, selectGroups, selectMembers } from "../collection";
import { caseSplit, casesWords, eachWeighted, NO_CASE } from "../comparison-stats";
import type { CollectionModel, MemberGain, MemberMeasure, MemberRow, MemberSummary } from "../collection";
import { figures, verdict, verdictIcons, verdictWords } from "./trial";
import type { VerdictKind } from "./trial";
import { empty, frame, pos } from "./frame";

interface Subset { title?: string; description?: string | string[]; note?: string; id?: string; members?: string[]; themes?: string[] }
/** The report index's designs, in the switcher's order; the first listed opens. */
export const INDEX_LAYOUTS = ["cards", "list", "table", "matrix"] as const;
type Layout = typeof INDEX_LAYOUTS[number];
const LAYOUT_WORDS: Record<Layout, string> = { cards: "Cards", list: "List", table: "Table", matrix: "By model" };

function need(ctx: RenderContext, type: string): CollectionModel {
  if (!ctx.collection) throw new Error(`The ${type} block needs a collection: pass --collection to report.py, or set the specification's "collection" field.`);
  return collectionModel(ctx.collection);
}
const open = (id: string) => `#report/${encodeURIComponent(id)}`;
const pairHref = (a: string, b: string) => `#compare/${encodeURIComponent(a)}/${encodeURIComponent(b)}`;
const VERDICT_ORDER: VerdictKind[] = ["adopt", "reject", "mixed", "inconclusive", "none"];
const plural = (n: number, word: string) => `${fmtInt(n)} ${word}${n === 1 ? "" : "s"}`;
const signed = (v: number, body: string) => `${v > 0 ? "+" : v < 0 ? "−" : "±"}${body}`;
const isRate = (m: MemberMeasure | null) => !!m && ["binary", "count", "preference"].includes(m.kind);
/** A change in the measure's own units, as plain text: percentage points for rates, units for means, positions for ranks. */
function changeText(m: MemberMeasure | null, d: number | null): string {
  if (!isNum(d) || !m) return "—";
  if (isRate(m)) { const p = Math.round(d * 100); return signed(p, `${Math.abs(p)} pts`); }
  const body = fmtNum(Math.abs(d));
  if (m.kind === "numeric") return signed(d, `${body}${m.unit ? ` ${m.unit}` : ""}`);
  if (m.kind === "rank") return signed(d, `${body} in mean rank`);
  return signed(d, `${body} (superiority)`);
}
/** An interval of changes with the unit written once, as plain text: "−79 to +14 pts". */
function spanText(m: MemberMeasure | null, iv: [number, number] | null): string {
  if (!iv || !m) return "no interval";
  const hi = changeText(m, iv[1]), unit = hi.replace(/^[+−±][\d.,k]+/, "");
  const lo = changeText(m, iv[0]);
  return `${unit && lo.endsWith(unit) ? lo.slice(0, -unit.length) : lo} to ${hi}`;
}
/** Where a value sits on a member's measure, as a share of its track. */
const at = (m: MemberMeasure, v: number) => (v - m.domain[0]) / (m.domain[1] - m.domain[0] || 1);
const intervalText = (m: MemberMeasure | null, iv: [number, number] | null) => !iv || !m ? "—" : m.percent ? `${fmtPct(iv[0])}–${fmtPct(iv[1])}` : `${fmtNum(iv[0])}–${fmtNum(iv[1])}${m.unit ? ` ${m.unit}` : ""}`;
// The same, escaped for HTML: a measure's unit is supplied text.
const change = (m: MemberMeasure | null, d: number | null) => esc(changeText(m, d));
const span = (m: MemberMeasure | null, iv: [number, number] | null) => esc(spanText(m, iv));
const interval = (m: MemberMeasure | null, iv: [number, number] | null) => esc(intervalText(m, iv));
/** A value's interval, or, when it pools several cases, that it has none: runs on one case repeat that case rather than sample new ones. */
const rowIntervalText = (m: MemberMeasure | null, r: MemberRow) => r.cases > 1 ? `none: pooled over ${r.over}` : intervalText(m, r.interval);
const rowInterval = (m: MemberMeasure | null, r: MemberRow) => r.cases > 1 ? `<span class="av-muted">${esc(rowIntervalText(m, r))}</span>` : interval(m, r.interval);
const gainIntervalText = (m: MemberMeasure | null, g: MemberGain) => m?.kind === "ordinal" ? (g.cases > 1 ? `median levels balanced over the ${g.over}` : "median levels") : g.cases > 1 ? `averaged over the ${g.over}, no interval` : g.delta === null ? "—" : spanText(m, g.interval);
const gainInterval = (m: MemberMeasure | null, g: MemberGain) => esc(gainIntervalText(m, g));
/** Whether a row's value weighs evidence naming no case as a group of its own. */
const weighsNoCase = (r: MemberRow) => !!r.perCase?.some(c => c.id === NO_CASE && c.n > 0);
/** A change in words: its size in the measure's units, or for an ordinal measure the median level it moves from and to
 * (no difference is computed for levels). */
const gainWordsText = (m: MemberMeasure | null, g: MemberGain) => isNum(g.delta) ? changeText(m, g.delta) : m?.kind === "ordinal" && isNum(g.from) && isNum(g.to) ? `“${m.levels?.[g.from] ?? g.from}” → “${m.levels?.[g.to] ?? g.to}”` : "—";
const gainWords = (m: MemberMeasure | null, g: MemberGain) => esc(gainWordsText(m, g));
/** Whether a change was taken: a size, or for an ordinal measure the two levels its line runs between. */
const taken = (m: MemberMeasure | null, g: MemberGain) => isNum(g.delta) || (m?.kind === "ordinal" && isNum(g.from) && isNum(g.to));

/** Each case on its own: every setup's value there with its 95% interval, and each change from the reference with its interval. */
function byCase(s: MemberSummary): string {
  const m = s.measure, pooled = s.rows.filter(r => r.perCase?.length);
  if (!m || !pooled.some(r => r.cases > 1)) return "";
  const cases: Array<{ id: string; label: string }> = [];
  for (const r of pooled) for (const c of r.perCase!) if (!cases.some(x => x.id === c.id)) cases.push({ id: c.id, label: c.label });
  const cell = (r: MemberRow, id: string) => { const c = r.perCase!.find(x => x.id === id); return c ? `${esc(c.text)}${c.interval ? ` <span class="av-muted">${interval(m, c.interval)}</span>` : ""}` : '<span class="av-muted">not run</span>'; };
  const values = `<table class="av-table av-table--compact"><thead><tr><th scope="col">Case</th>${pooled.map(r => `<th scope="col">${s.arms.tag(r.id, { id: false })}</th>`).join("")}</tr></thead><tbody>${cases.map(c => `<tr><th scope="row">${esc(c.label)}</th>${pooled.map(r => `<td class="av-num">${cell(r, c.id)}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
  const gains = s.gains.filter(g => g.perCase?.length);
  const changes = gains.length ? `<table class="av-table av-table--compact"><thead><tr><th scope="col">Case</th>${gains.map(g => `<th scope="col">${s.arms.tag(g.arm, { id: false })} <span class="av-muted">minus ${esc(s.rows.find(r => r.id === g.base)?.label || g.base)}</span></th>`).join("")}</tr></thead><tbody>${cases.map(c => `<tr><th scope="row">${esc(c.label)}</th>${gains.map(g => { const x = g.perCase!.find(y => y.id === c.id); return `<td class="av-num">${x ? `${change(m, x.delta)} <span class="av-muted">(${span(m, x.interval)})</span>` : '<span class="av-muted">—</span>'}</td>`; }).join("")}</tr>`).join("")}</tbody></table>` : "";
  return `<details class="av-cx-bycase"><summary>Each case on its own, with its 95% interval (${esc(casesWords(...caseSplit(cases.map(c => c.id))))})</summary><p class="av-muted">The values above pool every case, so they carry no interval: runs on one case repeat that case rather than sample new ones. Here each case stands alone.</p><div class="av-scroll-x">${values}</div>${changes ? `<div class="av-scroll-x">${changes}</div>` : ""}</details>`;
}

/** good, bad or flat by the measure's direction; neutral where it names none. */
function tone(m: MemberMeasure, d: number): string {
  if (Math.abs(d) < 1e-12) return "flat";
  if (m.better === "none") return "neutral";
  return (d > 0) === (m.better === "higher") ? "good" : "bad";
}

/** The decision as a compact stamp, in the verdict block's words and icons. */
export function stampHtml(s: MemberSummary, extra = ""): string {
  return `<span class="av-cx-stamp av-cx-v--${s.verdict}${extra ? " " + extra : ""}"><span class="av-cx-stamp-icon" aria-hidden="true">${verdictIcons[s.verdict]}</span><span class="av-cx-stamp-word">${esc(s.stamp)}</span></span>`;
}

function lanesOf(s: MemberSummary): Array<[string, MemberRow[]]> {
  const out: Array<[string, MemberRow[]]> = [];
  for (const r of s.rows) { const lane = out.find(([l]) => l === r.lane); if (lane) lane[1].push(r); else out.push([r.lane, [r]]); }
  return out;
}

/** Where a setup's value pools several cases, the case-balanced value every view plots, in words; otherwise null. */
function balancedSaid(s: MemberSummary, r: MemberRow): string | null {
  const m = s.measure;
  if (!m || r.cases <= 1 || r.balanced === null || relativeMeasure(m)) return null;
  const v = r.balanced, words = m.percent ? fmtPct(v) : m.kind === "ordinal" ? `median level “${m.levels?.[Math.round(v)] ?? fmtNum(v)}”` : `${fmtNum(v)}${m.unit ? ` ${m.unit}` : ""}`;
  return `${words} with ${eachWeighted(weighsNoCase(r))}`;
}
/** A setup's value in words: the report's own, and where it pools several cases the case-balanced value every view plots. */
function valueSaid(s: MemberSummary, r: MemberRow): string {
  const balanced = balancedSaid(s, r);
  return balanced ? `${r.text}; ${balanced}` : r.text;
}

/** A value in its measure's own terms, briefly: a share, a level's name, a rank, or a number with its unit. */
function valueShort(m: MemberMeasure, v: number): string {
  if (m.percent) return fmtPct(v);
  if (m.kind === "ordinal") return m.levels?.[Math.round(v)] ?? fmtNum(v);
  if (m.kind === "rank") return `rank ${fmtNum(v)}`;
  return `${fmtNum(v)}${m.unit ? ` ${m.unit}` : ""}`;
}
/** What a member's values are read against: quarters of 0–100% for a rate, each level (the ends and middle of a long
 * scale named), each rank, or round numbers across the measure's range. */
function measureTicks(m: MemberMeasure): Tick[] {
  const [lo, hi] = m.domain, inside = (v: number) => v >= lo - 1e-9 && v <= hi + 1e-9;
  if (m.percent) return [0, .25, .5, .75, 1].map(v => ({ x: at(m, v), label: fmtPct(v) }));
  if (m.kind === "ordinal") {
    const levels = m.levels && m.levels.length > 1 ? m.levels : null, last = levels ? levels.length - 1 : hi;
    return Array.from({ length: last + 1 }, (_, i) => ({ x: at(m, i), label: !levels ? (i === 0 ? "lowest level" : i === last ? "highest level" : "") : levels.length <= 5 || i === 0 || i === last || i === Math.round(last / 2) ? levels[i] : "" }));
  }
  const values = m.kind === "rank" && hi - lo <= 6 ? Array.from({ length: Math.round(hi - lo) + 1 }, (_, i) => lo + i) : niceTicks(lo, hi, 4).filter(inside);
  return values.map(v => ({ x: at(m, v), label: fmtNum(v) }));
}
const axisTitle = (m: MemberMeasure) => `${m.label}${m.unit && !m.percent ? `, ${m.unit}` : ""}`;
const cap = (t: string) => t.charAt(0).toUpperCase() + t.slice(1);

/** A setup's hover card: the report and model it ran in, then its value, what was observed, its interval, cost and change. */
function rowTip(s: MemberSummary, r: MemberRow, lane: string): string {
  const m = s.measure!, g = s.gains.find(x => x.arm === r.id);
  return tipAttr({
    over: [s.short, lane].filter(Boolean).join(" · "), title: r.label, mark: s.arms.mark(r.id),
    rows: [
      [cap(m.label), r.balanced === null ? `no valid ${s.noun}` : balancedSaid(s, r) ?? valueShort(m, r.balanced)],
      ["Observed", r.text],
      ["95% interval", rowIntervalText(m, r)],
      ["Invalid", r.invalid ? fmtInt(r.invalid) : ""],
      ["Median cost per run", isNum(r.cost) ? fmtUsd(r.cost) : ""],
      ...(g ? [["Change from reference", gainWordsText(m, g)], ["Change interval", gainIntervalText(m, g)]] as Array<[string, string]> : []),
    ],
    note: r.baseline ? "The reference: each change in its lane is measured from it." : undefined,
  });
}

/** Each setup on a row of its own, grouped by model (or group), on its measure's axis: its value as its mark (the
 * reference as a ring), a value from one case with its 95% interval as a capped whisker, each change as a line from the
 * reference's value toned by the measure's direction, and the value written at the row's end. A row shows its card on
 * hover, so no setup has to be looked up by its color. */
function lanes(s: MemberSummary, names: boolean): string {
  const m = s.measure;
  if (!m || !s.rows.length) return `<p class="av-cx-norate">${s.kind === "spec" ? "A report of its own blocks: open it to read its evidence" : "No headline value recorded"}.</p>`;
  const groups = lanesOf(s), multi = groups.length > 1;
  const said = groups.map(([lane, rows]) => `${lane ? `${lane}: ` : ""}${rows.map(r => `${r.label} ${valueSaid(s, r)}${r.baseline ? ", the reference" : ""}`).join("; ")}`).join(". ");
  const ticks = measureTicks(m), grid = gridlines(ticks);
  const body = groups.map(([lane, rows]) => `<div class="av-cx-lane">${multi || names ? `<p class="av-cx-lane-name">${esc(lane || "setups")}</p>` : ""}${rows.map(r => {
    // A change's line runs between the values it is taken over (the cases both ran), as its stated change is; with no
    // case in common there is no change, and no line.
    const g = s.gains.find(x => x.arm === r.id && isNum(x.from) && isNum(x.to));
    const shift = g ? `<span class="av-cx-shift av-cx-shift--${tone(m, g.to! - g.from!)}" style="--a:${pos(at(m, Math.min(g.from!, g.to!)))};--b:${pos(at(m, Math.max(g.from!, g.to!)))}"></span><span class="av-cx-from" style="--x:${pos(at(m, g.from!))}"></span>` : "";
    const ci = r.interval ? `<span class="av-whisker" style="--a:${pos(at(m, r.interval[0]))};--b:${pos(at(m, r.interval[1]))}"></span>` : "";
    const mark = r.balanced !== null ? `<span class="av-cx-pt${r.baseline ? " av-cx-pt--base" : ""}" style="--x:${pos(at(m, r.balanced))}" data-av-tip-at>${s.arms.glyph(r.id)}</span>` : `<span class="av-cx-none">no valid ${s.noun}</span>`;
    return `<div class="av-cx-row" style="--c:${s.arms.color(r.id)}"${rowTip(s, r, lane)}><span class="av-cx-who">${s.arms.glyph(r.id)}<span>${esc(r.label)}</span></span><div class="av-cx-track">${grid}${shift}${ci}${mark}</div><span class="av-cx-val">${r.balanced === null ? "—" : esc(valueShort(m, r.balanced))}</span></div>`;
  }).join("")}</div>`).join("");
  const axis = `<div class="av-cx-axis" aria-hidden="true"><span class="av-axis-title">${esc(axisTitle(m))}</span>${ticksHtml(ticks)}<span></span></div>`;
  return `<div class="av-cx-lanes" role="img" aria-label="${esc(`${m.label} by setup${m.better === "none" ? "" : `, ${m.better} is better`}. ${said}.`)}">${body}${axis}</div>`;
}

/** The exact values behind a member's tracks. */
function numbers(s: MemberSummary): string {
  if (!s.rows.length) return '<p class="av-muted">No headline value recorded.</p>';
  const costs = s.rows.some(r => isNum(r.cost)), gains = s.gains.length > 0, lanesShown = s.rows.some(r => r.lane);
  const head = ["Setup", ...(lanesShown ? [s.kind === "trial" ? "Model" : "Group"] : []), s.measure ? s.measure.label[0].toUpperCase() + s.measure.label.slice(1) : "Value", "95% interval", ...(costs ? ["Median cost per run"] : []), ...(gains ? ["Change from reference"] : [])];
  const rows = s.rows.map(r => {
    const g = s.gains.find(x => x.arm === r.id);
    return `<tr><th scope="row">${s.arms.tag(r.id, { id: false })}${r.baseline ? ' <span class="av-chip av-chip--base">reference</span>' : ""}</th>${lanesShown ? `<td>${esc(r.lane || "—")}</td>` : ""}<td>${esc(valueSaid(s, r))}${r.invalid ? ` <span class="av-muted">(${r.invalid} invalid)</span>` : ""}</td><td class="av-num">${rowInterval(s.measure, r)}</td>${costs ? `<td class="av-num">${fmtUsd(r.cost)}</td>` : ""}${gains ? `<td class="av-num"${attrs({ title: g?.method })}>${g ? `${gainWords(s.measure, g)} <span class="av-muted">(${gainInterval(s.measure, g)})</span>` : r.baseline ? "reference" : "other lane"}</td>` : ""}</tr>`;
  }).join("");
  const how = s.gains[0]?.method ? `<p class="av-muted">Changes: ${esc(s.gains[0].method)}.</p>` : "";
  return `<div class="av-scroll-x"><table class="av-table av-table--compact"><thead><tr>${head.map(h => `<th scope="col">${esc(h)}</th>`).join("")}</tr></thead><tbody>${rows}</tbody></table></div>${how}${byCase(s)}`;
}

function facts(s: MemberSummary): string {
  const items = [
    s.dates ? `<li><span class="av-sr">Ran </span>${esc(s.dates)}</li>` : "",
    ...s.evidence.map(e => `<li>${plural(e.n, e.noun)}${e.invalid ? ` <span class="av-cx-invalid">${fmtInt(e.invalid)} invalid</span>` : ""}</li>`),
    s.models.length ? `<li>${s.models.map(m => `<code>${esc(m)}</code>`).join(" ")}</li>` : "",
    isNum(s.cost) ? `<li>$${s.cost.toFixed(s.cost >= 10 ? 0 : 2)} recorded</li>` : "",
  ];
  return `<ul class="av-cx-facts">${items.join("")}</ul>`;
}

function tallyBar(ms: MemberSummary[], label: string): string {
  const counts = VERDICT_ORDER.map(v => [v, ms.filter(s => s.verdict === v).length] as const).filter(([, n]) => n > 0);
  const said = counts.map(([v, n]) => `${n} ${verdictWords[v].toLowerCase()}`).join(", ");
  return `<div class="av-dec-bar" role="img" aria-label="${esc(`${label}: ${said}`)}">${counts.map(([v, n]) => `<span class="av-dec-seg av-cx-v--${v}" style="flex:${n}"><b>${n}</b> ${esc(verdictWords[v])}</span>`).join("")}</div>`;
}
const tip = (s: MemberSummary) => s.headline ? s.headline.replace(/\*\*|`/g, "") : undefined;
const pick = (s: MemberSummary) => `<button type="button" class="av-btn av-btn--small av-rx-pick" data-av-rx-pick="${esc(s.id)}" aria-pressed="false" aria-label="Compare ${esc(s.short)}" hidden><span class="av-rx-pick-box" aria-hidden="true"></span>Compare</button>`;

// ------------------------------------------------------------------ decision board

export function decisions(input: Subset, ctx: RenderContext): string {
  const model = need(ctx, "decisions");
  const themes = selectGroups(model, input);
  if (!themes.length) return frame("decisions", input, empty("No report to show."));
  const all = themes.flatMap(t => t.members);
  const rows = themes.map(t => `<div class="av-dec-row"><h3 class="av-dec-theme">${esc(t.label)} <span class="av-muted">${plural(t.members.length, "report")}</span></h3><ul class="av-dec-tiles">${t.members.map(s =>
    `<li><a class="av-dec-tile av-cx-v--${s.verdict}" href="${open(s.id)}"${attrs({ "data-av-tip": tip(s) })}><span class="av-dec-icon" aria-hidden="true">${verdictIcons[s.verdict]}</span><span class="av-dec-word">${esc(s.stamp)}</span><span class="av-dec-name">${esc(s.short)}</span></a></li>`).join("")}</ul></div>`).join("");
  const legend = `<p class="av-dec-legend">${VERDICT_ORDER.filter(v => all.some(s => s.verdict === v)).map(v => `<span class="av-cx-v--${v}"><span class="av-dec-icon" aria-hidden="true">${verdictIcons[v]}</span>${esc(verdictWords[v])}</span>`).join("")}<span class="av-muted">A stamp's own words, where its report gives them, replace these.</span></p>`;
  return frame("decisions", input, `${tallyBar(all, "Decisions")}${legend}<div class="av-dec-board">${rows}</div>`);
}

// ------------------------------------------------------------------ report index

export function reports(input: Subset & { layouts?: string[] }, ctx: RenderContext): string {
  const model = need(ctx, "reports");
  const themes = selectGroups(model, input);
  if (!themes.length) return frame("reports", input, empty("No report to show."));
  const all = themes.flatMap(t => t.members);
  const models = [...new Set(all.flatMap(s => s.models))];
  const verdicts = VERDICT_ORDER.filter(v => all.some(s => s.verdict === v));
  const asked = Array.isArray(input.layouts) ? input.layouts.filter((l): l is Layout => (INDEX_LAYOUTS as readonly string[]).includes(l)) : [];
  const layouts: Layout[] = asked.length ? [...new Set(asked)] : [...INDEX_LAYOUTS];
  const switcher = layouts.length > 1 ? `<div class="av-rx-layouts" role="group" aria-label="Index design">${layouts.map((l, i) => `<button type="button" class="av-rx-layout" data-av-rx-layout="${l}" aria-pressed="${i === 0}"><span class="av-rx-layout-icon av-rx-layout-icon--${l}" aria-hidden="true"></span>${LAYOUT_WORDS[l]}</button>`).join("")}</div>` : "";
  const tools = `<div class="av-rx-tools" data-av-rx-tools hidden>${switcher}
<div class="av-rx-verdicts" role="group" aria-label="Show reports by decision"><button type="button" class="av-rx-chip" data-av-rx-verdict="" aria-pressed="true">All <span>${all.length}</span></button>${verdicts.map(v => `<button type="button" class="av-rx-chip av-cx-v--${v}" data-av-rx-verdict="${v}" aria-pressed="false"><span aria-hidden="true">${verdictIcons[v]}</span> ${esc(verdictWords[v])} <span>${all.filter(s => s.verdict === v).length}</span></button>`).join("")}</div>
<div class="av-rx-fields">${themes.length > 1 ? `<label><span>Theme</span><select data-av-rx-theme><option value="">Every theme</option>${themes.map(t => `<option value="${esc(t.id)}">${esc(t.label)}</option>`).join("")}</select></label>` : ""}${models.length > 1 ? `<label><span>Model</span><select data-av-rx-model><option value="">Every model</option>${models.map(m => `<option value="${esc(m)}">${esc(m)}</option>`).join("")}</select></label>` : ""}<label class="av-rx-search"><span>Search</span><input type="search" data-av-rx-q placeholder="Questions, decisions, setups" autocomplete="off"></label></div>
<p class="av-rx-status"><span data-av-rx-count role="status">${plural(all.length, "report")}</span><button type="button" class="av-btn av-btn--small" data-av-rx-clear hidden>Clear filters</button></p>
</div>`;
  const searchOf = (s: MemberSummary) => [s.title, s.question, s.headline, s.note, s.stamp, ...s.models, ...s.rows.map(r => r.label), s.id].join(" ").toLowerCase();
  const item = (s: MemberSummary) => attrs({ "data-av-rx-card": true, "data-member": s.id, "data-verdict": s.verdict, "data-theme": s.theme, "data-models": s.models.join("\n"), "data-search": searchOf(s) });
  const card = (s: MemberSummary) => {
    const follows = s.follows ? model.byId.get(s.follows) : undefined;
    const head = ctx.uid(`rx-${s.id}`);
    return `<li class="av-rx-card av-cx-v--${s.verdict}"${item(s)}>
<article aria-labelledby="${head}"><header class="av-rx-card-head">${stampHtml(s)}${s.kind === "trial" ? "" : `<span class="av-chip">${s.kind === "spec" ? "specification" : "comparison"}</span>`}</header>
<h4 class="av-rx-title" id="${head}"><a href="${open(s.id)}">${esc(s.title)}</a></h4>
${s.headline ? `<p class="av-rx-headline">${inline(s.headline)}</p>` : ""}${s.note ? `<p class="av-rx-note">${inline(s.note)}</p>` : ""}
${s.measure ? `<div class="av-rx-chart"><span class="av-eyebrow">${esc(s.metric)} by setup</span>${lanes(s, false)}</div>` : ""}
${facts(s)}${follows ? `<p class="av-rx-follows">Follows <a href="${open(follows.id)}">${esc(follows.short)}</a> · <a href="${pairHref(follows.id, s.id)}">compare the two</a></p>` : ""}
${s.rows.length ? `<details class="av-rx-exact"><summary>Exact numbers</summary>${numbers(s)}</details>` : ""}
<div class="av-rx-actions"><a class="av-btn av-btn--primary" href="${open(s.id)}">Read the full report<span aria-hidden="true"> →</span></a>${pick(s)}</div>
</article></li>`;
  };
  const grouped = (body: (t: typeof themes[number]) => string, story: boolean) => themes.map(t => { const hid = ctx.uid(`rx-theme-${t.id || "other"}`); return `<section class="av-rx-theme" data-av-rx-group aria-labelledby="${hid}"><header class="av-rx-theme-head"><h3 id="${hid}" class="av-rx-theme-title">${esc(t.label)}</h3>${tallyBar(t.members, t.label)}${story ? prose(t.summary, "av-rx-story") : ""}</header>${body(t)}</section>`; }).join("");
  const row = (s: MemberSummary) => `<li class="av-rx-row av-cx-v--${s.verdict}"${item(s)}><span class="av-rx-row-stamp">${stampHtml(s)}</span><div class="av-rx-row-main"><a class="av-rx-row-title" href="${open(s.id)}">${esc(s.title)}</a>${s.headline ? `<p class="av-rx-row-head">${inline(s.headline)}</p>` : ""}</div><div class="av-rx-row-chart">${s.measure ? lanes(s, false) : ""}</div><div class="av-rx-row-facts">${facts(s)}</div><div class="av-rx-row-pick">${pick(s)}</div></li>`;
  // Changes sort with others on the same measure (a preference or rank value has none: it depends on who else took part).
  const sortGroup = (s: MemberSummary) => measureKey(s.measure);
  // An ordinal change has no size, so it is said in levels and sorts after every change that has one.
  const changes = (s: MemberSummary) => { const ds = s.gains.map(g => g.delta).filter(isNum); const levels = ds.length ? [] : s.gains.filter(g => taken(s.measure, g)); return ds.length ? { v: Math.max(...ds.map(Math.abs)), sized: true, text: ds.length === 1 ? change(s.measure, ds[0]) : `${change(s.measure, Math.min(...ds))} to ${change(s.measure, Math.max(...ds))}` } : levels.length ? { v: -1, sized: false, text: levels.map(g => gainWords(s.measure, g)).join("; ") } : null; };
  // A trial's setups together, as counts: a rate over runs of several setups and cases would claim more than it holds.
  // Sorted by the case-balanced rate: each case's passes of valid runs, every setup together, averaged with each case weighted equally.
  const pooled = (s: MemberSummary) => {
    if (s.kind !== "trial") return null;
    const k = s.rows.reduce((t, r) => t + r.k, 0), n = s.rows.reduce((t, r) => t + r.n, 0);
    const byCase = new Map<string, [number, number]>();
    for (const r of s.rows) for (const c of r.perCase || []) { const e = byCase.get(c.id) || [0, 0]; byCase.set(c.id, [e[0] + c.k, e[1] + c.n]); }
    const rates = [...byCase.values()].filter(e => e[1] > 0).map(e => e[0] / e[1]);
    return n ? { k, n, balanced: rates.length ? rates.reduce((t, v) => t + v, 0) / rates.length : k / n } : null;
  };
  const head = (label: string, kind: "text" | "number", note?: string) => `<th scope="col"${attrs({ "data-av-rx-sortable": kind, title: note })}><button type="button" class="av-rx-sort">${label}<span class="av-rx-sort-mark" aria-hidden="true"></span></button></th>`;
  const table = `<div class="av-scroll-x"><table class="av-table av-table--compact av-rx-table"><thead><tr>${head("Decision", "text")}${head("Report", "text")}${themes.length > 1 ? head("Theme", "text") : ""}${head("Models", "text")}${head("Evidence", "number", "Trial runs, or a comparison's observations, judgments, rankings and supplied totals; sorted by their total")}${head("Invalid", "number")}${head("Passed", "number", "Passes of valid runs, a trial's setups together: plain counts, sorted by the case-balanced pass rate (each case's rate, every case weighted equally), so no report's mix of cases decides its place")}${head("Changes from reference", "number", "Each setup against its reference on the same model, in its measure's units, over the cases both ran with each case weighted equally; sorted by the largest case-balanced change either way, reports on one measure together, so no change is ranked against another measure's")}${head("Cost", "number")}${head("Ran", "text")}</tr></thead><tbody>${themes.flatMap(t => t.members.map(s => {
    const c = changes(s), p = pooled(s);
    return `<tr${item(s)}><td data-v="${VERDICT_ORDER.indexOf(s.verdict)}">${stampHtml(s)}</td><th scope="row" data-v="${esc(s.title.toLowerCase())}"><a href="${open(s.id)}">${esc(s.short)}</a>${pick(s)}</th>${themes.length > 1 ? `<td data-v="${esc(t.label.toLowerCase())}">${esc(t.label)}</td>` : ""}<td data-v="${esc(s.models.join(" "))}">${s.models.map(m => `<code>${esc(m)}</code>`).join(" ") || "—"}</td><td class="av-num" data-v="${s.evidence.reduce((t, e) => t + e.n, 0)}">${s.evidence.length ? s.evidence.map(e => plural(e.n, e.noun)).join(" · ") : "—"}</td><td class="av-num" data-v="${s.invalid}">${fmtInt(s.invalid)}</td><td class="av-num" data-v="${p ? p.balanced : -1}">${p ? `${fmtInt(p.k)} of ${fmtInt(p.n)}` : "—"}</td><td class="av-num" data-v="${c ? c.v : -1}"${c?.sized ? ` data-g="${esc(sortGroup(s))}"` : ""}>${c ? c.text : "—"}</td><td class="av-num" data-v="${s.cost ?? -1}">${isNum(s.cost) ? fmtUsd(s.cost) : "—"}</td><td data-v="${esc(s.date || "")}">${esc(s.dates || "—")}</td></tr>`;
  })).join("")}</tbody></table></div><p class="av-muted av-rx-sortnote">Passed shows plain counts and sorts by the case-balanced pass rate; Changes from reference sorts by the largest case-balanced change. Both weight every case equally, so no report's mix of cases decides its place.</p>`;
  const single = [...new Set(all.flatMap(s => s.models.length === 1 ? s.models : []))];
  const columns = [...single.map(m => ({ key: m, label: m, test: (s: MemberSummary) => s.models.length === 1 && s.models[0] === m })),
    ...(all.some(s => s.models.length > 1) ? [{ key: "", label: "Several models", test: (s: MemberSummary) => s.models.length > 1 }] : []),
    ...(all.some(s => !s.models.length) ? [{ key: "", label: "Model not recorded", test: (s: MemberSummary) => !s.models.length }] : [])];
  const tile = (s: MemberSummary) => `<li class="av-rx-matrix-item"${item(s)}><a class="av-dec-tile av-dec-tile--small av-cx-v--${s.verdict}" href="${open(s.id)}"${attrs({ "data-av-tip": tip(s) })}><span class="av-dec-icon" aria-hidden="true">${verdictIcons[s.verdict]}</span><span class="av-dec-word">${esc(s.stamp)}</span><span class="av-dec-name">${esc(s.short)}</span></a>${pick(s)}</li>`;
  const matrix = `<p class="av-muted av-rx-matrix-read">Each theme against the models its reports ran on: a question checked on both families shows a decision in each column.</p><div class="av-scroll-x"><table class="av-rx-matrix"><thead><tr><th scope="col">Theme</th>${columns.map(c => `<th scope="col">${c.key ? `<code>${esc(c.label)}</code>` : esc(c.label)}</th>`).join("")}</tr></thead><tbody>${themes.map(t => `<tr data-av-rx-group><th scope="row">${esc(t.label)}</th>${columns.map(c => { const here = t.members.filter(c.test); return `<td>${here.length ? `<ul class="av-rx-matrix-tiles">${here.map(tile).join("")}</ul>` : '<span class="av-rx-matrix-none" aria-label="none">—</span>'}</td>`; }).join("")}</tr>`).join("")}</tbody></table></div>`;
  const body: Record<Layout, () => string> = {
    cards: () => grouped(t => `<ol class="av-rx-list">${t.members.map(card).join("")}</ol>`, true),
    list: () => grouped(t => `<ol class="av-rx-rows">${t.members.map(row).join("")}</ol>`, false),
    table: () => table,
    matrix: () => matrix,
  };
  const views = layouts.map((l, i) => `<div class="av-rx-view av-rx-view--${l}" data-av-rx-view="${l}"${i ? " hidden" : ""}>${body[l]()}</div>`).join("");
  const tray = `<div class="av-rx-tray" data-av-rx-tray hidden><p data-av-rx-picked>Pick two reports to compare them side by side.</p><a class="av-btn av-btn--primary" data-av-rx-go href="#" aria-disabled="true">Compare</a><button type="button" class="av-btn av-btn--small" data-av-rx-unpick>Clear</button></div>`;
  return frame("reports", input, `<div class="av-rx" data-av-rx>${tools}${views}<p class="av-empty" data-av-rx-none hidden>No report matches these filters.</p>${tray}</div>`);
}

// ------------------------------------------------------------------ shifts

export function shifts(input: Subset, ctx: RenderContext): string {
  const model = need(ctx, "shifts");
  const themes = selectGroups(model, input).map(t => ({ ...t, members: t.members.filter(s => s.measure && s.rows.some(r => r.balanced !== null)) })).filter(t => t.members.length);
  if (!themes.length) return frame("shifts", input, empty("No report records a headline value."));
  const line = (s: MemberSummary) => {
    const measured = s.gains.filter(g => taken(s.measure, g));
    if (relativeMeasure(s.measure)) return `values only: ${s.measure!.kind === "preference" ? "a win share depends on who else was judged" : "a mean rank depends on who else was ranked"}, so none is set against another`;
    if (!s.baseline) return "no reference setup named";
    if (!measured.length) return "no change measured in the reference's lane";
    if (measured.length === 1) return `${gainWords(s.measure, measured[0])} <span class="av-muted">(${measured[0].cases > 1 || s.measure?.kind === "ordinal" ? gainInterval(s.measure, measured[0]) : `95%: ${span(s.measure, measured[0].interval)}`})</span>`;
    if (!measured.every(g => isNum(g.delta))) return `${measured.length} changes: ${measured.map(g => gainWords(s.measure, g)).join("; ")}`;
    const ds = measured.map(g => g.delta!);
    return Math.min(...ds) === Math.max(...ds) ? `${measured.length} changes, each ${change(s.measure, ds[0])}` : `${measured.length} changes, ${change(s.measure, Math.min(...ds))} to ${change(s.measure, Math.max(...ds))}`;
  };
  const rows = themes.map(t => `<div class="av-sh-theme"><h3 class="av-sh-theme-title">${esc(t.label)}</h3>${t.members.map(s =>
    `<div class="av-sh-row"><div class="av-sh-name">${stampHtml(s, "av-cx-stamp--icon")}<a href="${open(s.id)}">${esc(s.short)}</a><span class="av-sh-sum">${s.measure!.percent ? "" : `${esc(s.metric)}: `}${line(s)}</span></div><div class="av-sh-plot">${lanes(s, true)}</div></div>`).join("")}</div>`).join("");
  const key = `<ul class="av-sh-key" aria-label="How to read this chart"><li><span class="av-cx-key-ring" aria-hidden="true"></span>the reference setup</li><li><span class="av-cx-key-dot" aria-hidden="true"></span>a setup tried (its color and shape as in its report)</li><li><span class="av-cx-key-up" aria-hidden="true"></span>a change from the reference for the better</li><li><span class="av-cx-key-down" aria-hidden="true"></span>for the worse</li><li><span class="av-cx-key-neutral" aria-hidden="true"></span>on a measure with no better direction</li><li><span class="av-cx-key-ci" aria-hidden="true"></span>95% interval: where the true value likely lies (a value from one case has one)</li></ul><p class="av-muted av-sh-read">Each report is drawn on its own measure's axis. Hover or touch a setup for its numbers.</p>`;
  const table = themes.flatMap(t => t.members).flatMap(s => s.rows.map(r => {
    const g = s.gains.find(x => x.arm === r.id);
    return `<tr><th scope="row"><a href="${open(s.id)}">${esc(s.short)}</a></th><td>${esc(s.metric)}</td><td>${esc(r.lane || "—")}</td><td>${s.arms.tag(r.id, { id: false })}${r.baseline ? ' <span class="av-chip av-chip--base">reference</span>' : ""}</td><td>${esc(valueSaid(s, r))}</td><td class="av-num">${rowInterval(s.measure, r)}</td><td class="av-num"${attrs({ title: g?.method })}>${g ? gainWords(s.measure, g) : "—"}</td><td class="av-num">${g ? gainInterval(s.measure, g) : "—"}</td></tr>`;
  })).join("");
  const exact = `<details class="av-cx-exact"><summary>Every value and change, exactly</summary><div class="av-scroll-x"><table class="av-table av-table--compact"><thead><tr><th scope="col">Report</th><th scope="col">Measure</th><th scope="col">Model or group</th><th scope="col">Setup</th><th scope="col">Value</th><th scope="col">95% interval</th><th scope="col">Change from reference</th><th scope="col">95% interval of the change</th></tr></thead><tbody>${table}</tbody></table></div><p class="av-muted">Rates count valid observations only. A change is the setup minus its reference in the same lane: for trials with a 95% Newcombe interval, for comparisons by the comparison's own method for its metric (hover a change to read it); an interval that spans zero means the change could be chance. A value or change pooled over several cases has no interval, since runs on one case repeat that case rather than sample new ones; its report gives each case's own interval.</p></details>`;
  return frame("shifts", input, `<div class="av-sh">${key}${rows}</div>${exact}`);
}

// ------------------------------------------------------------------ cost against gain

export function costGain(input: Subset, ctx: RenderContext): string {
  const model = need(ctx, "cost-gain");
  const ms = selectMembers(model, input);
  const points = ms.flatMap(s => s.gains.filter(g => isNum(g.delta) && isNum(g.costChange)).map(g => ({ s, g })));
  const left = ms.filter(s => s.rows.length > 1 && !s.gains.some(g => isNum(g.delta) && isNum(g.costChange)));
  if (!points.length) return frame("cost-gain", input, empty("No change records both a pass-rate difference and a cost difference against its reference."));
  // Both axes run symmetric about zero to the round tick past the largest value (and its interval), so no change sits
  // past a labelled bound and either side of zero reads at the same scale.
  const half = (largest: number, cap: number) => { const t = axisTicks(0, Math.min(cap, largest * 1.04), 2); return [...t.slice(1).reverse().map(v => -v), ...t]; };
  const xs = half(Math.max(.1, ...points.map(p => Math.abs(p.g.costChange!))), Infinity);
  const ys = half(Math.max(.1, ...points.flatMap(p => [Math.abs(p.g.delta!), ...(p.g.interval ? p.g.interval.map(Math.abs) : [])])), 1);
  const mx = xs[xs.length - 1], my = ys[ys.length - 1];
  const x = (v: number) => (Math.max(-mx, Math.min(mx, v)) + mx) / (2 * mx), y = (v: number) => (my - Math.max(-my, Math.min(my, v))) / (2 * my);
  const tick = (v: number) => `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(Math.round(v * 100))}%`;
  const pts = (v: number) => { const p = Math.round(v * 100); return signed(p, `${Math.abs(p)}`); };
  // Changes that land on one spot are fanned out where the plot is drawn, at its size (enhance.ts).
  const marks = points.map((p, i) => {
    const px = x(p.g.costChange!), py = y(p.g.delta!), m = p.s.measure;
    const ci = p.g.interval ? `<span class="av-whisker av-whisker--v av-cg-ci" style="--x:${pos(px)};--a:${pos(y(p.g.interval[1]))};--b:${pos(y(p.g.interval[0]))};--v:${p.s.arms.color(p.g.arm)}"></span>` : "";
    const card = tipAttr({ over: `${p.s.short}${p.g.lane ? ` · ${p.g.lane}` : ""}`, title: p.s.arms.label(p.g.arm), mark: p.s.arms.mark(p.g.arm), rows: [["Against", p.s.arms.label(p.g.base)], ["Pass rate change", changeText(m, p.g.delta)], ["Its 95% interval", gainIntervalText(m, p.g)], ["Cost per run change", tick(p.g.costChange!)], ["Report's decision", p.s.stamp]], note: "Open the report to read it in full." });
    return `${ci}<a class="av-cg-pt" href="${open(p.s.id)}" style="--x:${pos(px)};--y:${pos(py)};--v:${p.s.arms.color(p.g.arm)}"${card}><span class="av-cg-dot">${i + 1}</span><span class="av-sr"> ${esc(p.s.arms.label(p.g.arm))} in ${esc(p.s.short)}</span></a>`;
  }).join("");
  const quads = [["More passed, cost less", "tl"], ["More passed, cost more", "tr"], ["Fewer passed, cost less", "bl"], ["Fewer passed, cost more", "br"]].map(([t, c]) => `<span class="av-cg-quad av-cg-quad--${c}" aria-hidden="true">${t}</span>`).join("");
  const grid = xs.map(v => `<span class="av-cg-vline${v === 0 ? " av-cg-zero" : ""}" style="--x:${pos(x(v))}"></span>`).join("") + ys.map(v => `<span class="av-cg-hline${v === 0 ? " av-cg-zero" : ""}" style="--y:${pos(y(v))}"></span>`).join("");
  const yTicks = `<div class="av-cg-yticks" aria-hidden="true">${ys.map(v => `<span style="--y:${pos(y(v))}">${pts(v)}</span>`).join("")}</div>`;
  const xTicks = ticksHtml(xs.map(v => ({ x: x(v), label: tick(v) })));
  const plot = `<figure class="av-cg" aria-label="${esc(`Cost against gain: ${plural(points.length, "change")} against their references`)}"><figcaption class="av-axis-title av-cg-ytitle">Pass rate against the reference, points</figcaption>${yTicks}<div class="av-cg-plot">${quads}${grid}${marks}</div><span></span>${xTicks}<span></span><p class="av-axis-title av-cg-xtitle">Cost per run against the reference, median over cases</p></figure>`;
  const key = `<ol class="av-cg-key">${points.map((p, i) => `<li style="--v:${p.s.arms.color(p.g.arm)}"><span class="av-cg-n" aria-hidden="true">${i + 1}</span><span class="av-cg-text">${p.s.arms.tag(p.g.arm, { id: false })} <span class="av-muted">against ${esc(p.s.arms.label(p.g.base))}${p.g.lane ? ` on ${esc(p.g.lane)}` : ""} in</span> <a href="${open(p.s.id)}">${esc(p.s.short)}</a></span><span class="av-cg-vals"><b>${change(p.s.measure, p.g.delta)}</b> <span class="av-muted">(${span(p.s.measure, p.g.interval)})</span> · cost <b>${tick(p.g.costChange!)}</b> · <span class="av-muted">report:</span> ${stampHtml(p.s, "av-cx-stamp--icon")}</span></li>`).join("")}</ol>`;
  const note = left.length ? `<p class="av-muted">Not drawn, for want of a reference on the same model or a recorded cost: ${left.map(s => `<a href="${open(s.id)}">${esc(s.short)}</a>`).join(", ")}.</p>` : "";
  return frame("cost-gain", input, `<p class="av-cg-legend"><span><span class="av-cg-key-dot" aria-hidden="true">1</span>a change, numbered as in the list below (hover or touch it for its numbers; select it to open its report)</span><span><span class="av-cg-key-ci" aria-hidden="true"></span>95% interval of its pass-rate change: one that crosses zero could be chance</span></p>${plot}<p class="av-muted av-cg-read">Cost changes are each trial's median over its cases of the per-case difference in cost per run.</p>${key}${note}`);
}

// ------------------------------------------------------------------ timeline

/** A day's weekday; the day itself is written by fmtDates, with its year in full (Intl writes the year 99 as "99"). */
const WEEKDAY = new Intl.DateTimeFormat("en-GB", { weekday: "short", timeZone: "UTC" });
export function timeline(input: Subset, ctx: RenderContext): string {
  const model = need(ctx, "timeline");
  const ms = selectMembers(model, input);
  if (!ms.length) return frame("timeline", input, empty("No report to show."));
  // By day (undated last), then by the instant each began (a day with no time first), then as listed.
  const cmp = (a: string | number, b: string | number) => a < b ? -1 : a > b ? 1 : 0;
  const sorted = [...ms].sort((a, b) => cmp(a.date === null ? 1 : 0, b.date === null ? 1 : 0) || cmp(a.date ?? "", b.date ?? "") || cmp(a.time ?? -Infinity, b.time ?? -Infinity) || a.index - b.index);
  const days: Array<[string | null, MemberSummary[]]> = [];
  for (const s of sorted) { const last = days[days.length - 1]; if (last && last[0] === s.date) last[1].push(s); else days.push([s.date, [s]]); }
  const themeLabel = (id: string) => model.themes.find(t => t.id === id)?.label || "";
  const followers = (id: string) => ms.filter(x => x.follows === id);
  const item = (s: MemberSummary) => {
    const before = s.follows ? model.byId.get(s.follows) : undefined, after = followers(s.id);
    const time = isNum(s.time) ? new Date(s.time).toISOString().slice(11, 16) + " UTC" : "";
    return `<li class="av-tl-item av-cx-v--${s.verdict}"><span class="av-tl-dot" aria-hidden="true">${verdictIcons[s.verdict]}</span><div class="av-tl-body"><p class="av-tl-meta">${time ? `<span>${time}</span>` : ""}${themeLabel(s.theme) ? `<span>${esc(themeLabel(s.theme))}</span>` : ""}</p><p class="av-tl-title"><a href="${open(s.id)}">${esc(s.short)}</a> ${stampHtml(s)}</p>${s.headline ? `<p class="av-tl-head">${inline(s.headline)}</p>` : ""}${before ? `<p class="av-tl-link">↳ Follows <a href="${open(before.id)}">${esc(before.short)}</a> (${esc(before.stamp)}) · <a href="${pairHref(before.id, s.id)}">compare before and after</a></p>` : ""}${after.length ? `<p class="av-tl-link">Followed up by ${after.map(x => `<a href="${open(x.id)}">${esc(x.short)}</a>`).join(", ")}</p>` : ""}</div></li>`;
  };
  return frame("timeline", input, `<ol class="av-tl">${days.map(([d, list]) => `<li class="av-tl-day"><h3 class="av-tl-date">${d ? esc(`${WEEKDAY.format(new Date(`${d}T00:00:00Z`))}, ${fmtDates(d)}`) : "Date not recorded"}</h3><ol class="av-tl-items">${list.map(item).join("")}</ol></li>`).join("")}</ol>`);
}

// ------------------------------------------------------------------ suggested pairs

function differs(a: MemberSummary, b: MemberSummary): string {
  const decision = a.verdict === b.verdict && a.stamp === b.stamp ? `Same decision: ${esc(a.stamp)}` : `Decision ${a.verdict === b.verdict ? "worded differently" : "changed"}: ${esc(a.stamp)} → ${esc(b.stamp)}`;
  const am = a.models.join(", "), bm = b.models.join(", ");
  const models = am && bm && am !== bm ? `models ${esc(am)} → ${esc(bm)}` : am && am === bm ? `both on ${esc(am)}` : "";
  return [decision, models].filter(Boolean).join(" · ");
}

export function matchups(input: Subset & { pairs?: Array<{ a: string; b: string; title?: string; note?: string }> }, ctx: RenderContext): string {
  const model = need(ctx, "matchups");
  const chosen = new Set(selectMembers(model, input).map(s => s.id));
  const pairs = (Array.isArray(input.pairs) ? input.pairs.map(p => ({ ...p, source: "pair" as const })) : model.pairs)
    .filter(p => p && model.byId.has(p.a) && model.byId.has(p.b) && p.a !== p.b && (chosen.has(p.a) || chosen.has(p.b)));
  if (!pairs.length) return frame("matchups", input, empty("No pair to show."));
  // Each side has the card's full width for its setups, A above B, so every setup reads as a labelled row; on a card wide
  // enough for two such columns they sit side by side (styles: .av-mu-pair).
  const side = (s: MemberSummary, letter: string) => `<section class="av-mu-side" aria-label="${letter}: ${esc(s.short)}"><header class="av-mu-head"><span class="av-rc-letter" aria-hidden="true">${letter}</span><a class="av-mu-title" href="${open(s.id)}">${esc(s.short)}</a></header>${stampHtml(s)}${s.measure ? lanes(s, false) : ""}</section>`;
  return frame("matchups", input, `<ul class="av-mu">${pairs.map(p => {
    const a = model.byId.get(p.a)!, b = model.byId.get(p.b)!;
    const kind = p.title || (p.source === "follows" ? "A follow-up and the report it followed" : "Read together");
    return `<li class="av-mu-card"><p class="av-mu-kind">${esc(kind)}</p><div class="av-mu-pair">${side(a, "A")}<p class="av-mu-link"><span>${p.source === "follows" ? "followed by" : "against"}</span></p>${side(b, "B")}</div><p class="av-mu-diff">${differs(a, b)}</p>${p.note ? `<p class="av-muted">${inline(p.note)}</p>` : ""}<a class="av-btn" href="${pairHref(a.id, b.id)}">Compare side by side<span aria-hidden="true"> →</span></a></li>`;
  }).join("")}</ul>`);
}

// ------------------------------------------------------------------ two reports side by side

/** A member's own context, its element ids kept apart from the other side's. */
function memberContext(spec: ReportSpec, prefix: string) {
  const ctx = createContext(spec, spec.cases || {});
  const uid = ctx.uid.bind(ctx);
  ctx.uid = (base: string) => uid(`${prefix}-${base}`);
  return ctx;
}
/** A member's views copied into another page link to places in the member's own report (its invalid runs, a run, a
 * section), under its address, since the page they are copied into has none of them. */
const memberLinks = (html: string, id: string) => html.replace(/href="#(?!report\/|compare\/)([^"]*)"/g, (_, rest) => `href="#report/${encodeURIComponent(id)}/${rest}"`);
/** A member's own verdict section, rendered with its own arms and data. */
function decisionInFull(model: CollectionModel, s: MemberSummary, prefix: string): string {
  const spec = model.spec(s.id);
  const block = spec?.sections.flatMap(x => Array.isArray(x.blocks) ? x.blocks : []).find(b => b && b.type === "verdict");
  if (!spec || !block) return empty("This report records no verdict.");
  const section = spec.sections.find(x => Array.isArray(x.blocks) && x.blocks.includes(block))!;
  const mctx = memberContext(spec, prefix);
  return memberLinks(section.blocks.map(b => b.type === "verdict" ? verdict(b as never, mctx) : b.type === "figures" ? figures(b as never) : "").join(""), s.id);
}
/** The views a report's own results are drawn with, for setting two reports' evidence side by side. */
const RESULT_TYPES = ["ladder", "contrast", "scorecard", "metric", "difference", "hierarchy", "preferences", "intervals", "bars", "trend", "table", "matrix"];
function resultsInFull(model: CollectionModel, s: MemberSummary, prefix: string): string {
  const spec = model.spec(s.id);
  if (!spec) return "";
  const blocks = spec.sections.flatMap(x => Array.isArray(x.blocks) ? x.blocks : []).filter(b => b && RESULT_TYPES.includes(b.type)).slice(0, 4);
  if (!blocks.length) return empty("This report draws no result view to set beside the other.");
  const mctx = memberContext(spec, prefix);
  return memberLinks(blocks.map(b => renderBlock(b, mctx)).join(""), s.id);
}

export function reportCompare(input: { a: string; b: string; title?: string; description?: string | string[]; note?: string; id?: string }, ctx: RenderContext): string {
  const model = need(ctx, "report-compare");
  const A = model.byId.get(input.a), B = model.byId.get(input.b);
  if (!A || !B) return frame("report-compare", input, empty(`Not in this collection: ${[!A ? input.a : "", !B ? input.b : ""].filter(Boolean).join(" and ")}.`));
  const side = (s: MemberSummary, letter: "A" | "B") => `<div class="av-rc-side av-rc-side--${letter.toLowerCase()}"><p class="av-rc-top"><span class="av-rc-letter" aria-hidden="true">${letter}</span>${stampHtml(s)}</p><h3 class="av-rc-title"><span class="av-sr">${letter}: </span><a href="${open(s.id)}">${esc(s.title)}</a></h3>${s.headline ? `<p class="av-rc-headline">${inline(s.headline)}</p>` : ""}${facts(s)}<a class="av-btn" href="${open(s.id)}">Read ${letter} in full<span aria-hidden="true"> →</span></a></div>`;
  const same = sameMeasure(A, B);
  const m = same ? A.measure! : null;
  const matched = same ? matchRows(A, B) : [];
  const pairs = matched.filter(x => x.a && x.b);
  const casesA = new Set(A.cases.map(c => c.id)), sharedCases = B.cases.filter(c => casesA.has(c.id)), onlyA = A.cases.filter(c => !B.cases.some(x => x.id === c.id)), onlyB = B.cases.filter(c => !casesA.has(c.id));
  const measures = same ? `both measure ${esc(m!.label)}${m!.better === "none" ? "" : ` (${m!.better} is better)`}` : A.measure && B.measure ? `${esc(measuresApart(A, B) || "")}, so their values are shown apart and never subtracted` : "at least one report has no headline value to set against the other's";
  const pooled = (s: MemberSummary) => { const k = s.rows.reduce((t, r) => t + r.k, 0), n = s.rows.reduce((t, r) => t + r.n, 0); return { k, n }; };
  const pa = pooled(A), pb = pooled(B);
  const diffs = [
    `<li>${differs(A, B)}.</li>`,
    `<li>Measures: ${measures}.</li>`,
    same ? `<li>Setups: ${pairs.length ? `${plural(pairs.length, "setup")} matched` : "none matched"}${matched.some(x => x.a && !x.b) ? `; ${matched.filter(x => x.a && !x.b).length} only in A` : ""}${matched.some(x => !x.a && x.b) ? `; ${matched.filter(x => !x.a && x.b).length} only in B` : ""}.</li>` : "",
    // Evidence naming no case is said beside the cases, in the words every count of cases uses.
    `<li>Cases: ${sharedCases.length || (A.noCase && B.noCase) ? casesWords(sharedCases.length, A.noCase && B.noCase, "in both") : "none in common"}${onlyA.length ? `; ${onlyA.length} only in A` : ""}${onlyB.length ? `; ${onlyB.length} only in B` : ""}${A.noCase !== B.noCase ? `; ${casesWords(0, true, `only in ${A.noCase ? "A" : "B"}`)}` : ""}.</li>`,
    same && A.kind === "trial" && B.kind === "trial" ? `<li>Every setup together: A ${pa.k} of ${pa.n} passed (${fmtPct(pa.n ? pa.k / pa.n : null)}), B ${pb.k} of ${pb.n} (${fmtPct(pb.n ? pb.k / pb.n : null)}).</li>` : "",
  ].join("");
  let setups = "";
  if (same && m) {
    // Each matched setup compared case-balanced over the cases both ran; a setup in one report alone at its own balanced value.
    const compared = matched.map(x => ({ x, cmp: x.a && x.b ? caseBalanced(m, x.a, x.b) : null }));
    // One shared scale, drawn to hold every value plotted on it.
    const plotted = compared.flatMap(({ x, cmp }) => cmp && !("apart" in cmp) ? [cmp.a, cmp.b] : !cmp ? [(x.a || x.b)!.balanced] : []).filter(isNum);
    const shared: MemberMeasure = { ...m, domain: measureDomain(m, plotted) };
    // A value in the measure's own words: a rate, a number with its unit, or a level.
    const valueWords = (v: number) => shared.percent ? fmtPct(v) : m.kind === "ordinal" ? `“${m.levels?.[Math.round(v)] ?? fmtNum(v)}”` : `${fmtNum(v)}${m.unit ? ` ${m.unit}` : ""}`;
    // A mark's card gives the value it is drawn at, and what that value is, beside the report's own words.
    const ticks = measureTicks(shared);
    const marker = (r: MemberRow, v: number, letter: string, near: boolean, over: string | null) => `<span class="av-rc-mark av-rc-mark--${letter.toLowerCase()}" style="--x:${pos(at(shared, v))};--dy:${near ? (letter === "A" ? -7 : 7) : 0}px"${tipAttr({ over: `${letter} · ${(letter === "A" ? A : B).short}`, title: r.label, rows: [[cap(m.label), `${valueWords(v)}${over ? ` (${over})` : ""}`], ["The report says", r.text]] })}>${letter}</span>`;
    const slope = compared.map(({ x, cmp }) => {
      const name = x.a && x.b ? (x.a.label === x.b.label ? esc(x.a.label) : `${esc(x.a.label)} <span class="av-muted">↔</span> ${esc(x.b.label)}`) : esc((x.a || x.b)!.label);
      // The change is taken over the cases both reports ran, each weighted equally, so neither report's mix of cases moves it.
      const apartWhy = cmp && "apart" in cmp ? cmp.apart : null;
      const d = cmp && !("apart" in cmp) ? cmp : null;
      const values = d ? [d.a, d.b] : null;
      const near = !!values && Math.abs(at(shared, values[0]) - at(shared, values[1])) < 0.04;
      const line = values ? `<span class="av-cx-shift av-cx-shift--${tone(m, values[1] - values[0])}" style="--a:${pos(at(shared, Math.min(...values)))};--b:${pos(at(shared, Math.max(...values)))}"></span>` : "";
      const diff = d && d.estimate !== null ? ` · B − A <b>${change(m, d.estimate)}</b> <span class="av-muted">(${d.interval ? span(m, d.interval) : esc(d.why || "no interval")})</span>` : "";
      const nums = `${x.a ? `A ${esc(x.a.text)}` : "not in A"} · ${x.b ? `B ${esc(x.b.text)}` : "not in B"}${diff}`;
      // What the line covers, beneath the track and the numbers, where it has the row's width.
      const covers = d?.label || d?.coverage ? `<p class="av-rc-over">${d.label ? `${esc(d.label.charAt(0).toUpperCase() + d.label.slice(1))}: A ${esc(valueWords(d.a))}, B ${esc(valueWords(d.b))}.` : ""}${d.coverage ? ` ${esc(d.coverage.charAt(0).toUpperCase() + d.coverage.slice(1))}.` : ""}</p>` : "";
      const said = `${(x.a || x.b)!.label}: ${x.a ? `A ${x.a.text}` : "not in A"}; ${x.b ? `B ${x.b.text}` : "not in B"}${d?.label ? `; ${d.label}: A ${valueWords(d.a)}, B ${valueWords(d.b)}` : ""}${d && d.estimate !== null ? `; B minus A ${changeText(m, d.estimate)}, ${d.interval ? `95% interval ${spanText(m, d.interval)}` : d.why || "no interval"}` : ""}${d?.coverage ? `; ${d.coverage}` : ""}`;
      const track = x.a && x.b ? (d ? `<div class="av-cx-track av-rc-track" role="img" aria-label="${esc(said)}"${attrs({ title: d.method })}>${gridlines(ticks)}${line}${marker(x.a, d.a, "A", near, d.label)}${marker(x.b, d.b, "B", near, d.label)}</div>` : `<p class="av-rc-apart">${esc(apartWhy || "")}.</p>`)
        : `<div class="av-cx-track av-rc-track" role="img" aria-label="${esc(said)}">${gridlines(ticks)}${(x.a || x.b)!.balanced !== null ? marker((x.a || x.b)!, (x.a || x.b)!.balanced!, x.a ? "A" : "B", false, (x.a || x.b)!.cases > 1 ? "each case weighted equally" : null) : ""}</div>`;
      return `<div class="av-rc-row"><div class="av-rc-name">${name}${x.how && x.how !== "same label" ? ` <span class="av-chip">${esc(x.how)}</span>` : ""}${(x.a || x.b)!.baseline ? ' <span class="av-chip av-chip--base">reference</span>' : ""}</div>${track}<div class="av-rc-nums">${nums}</div>${covers}</div>`;
    }).join("");
    const scale = `<div class="av-rc-scale" aria-hidden="true"><span class="av-axis-title">${esc(axisTitle(m))}</span>${ticksHtml(ticks, { top: true })}<span></span></div>`;
    const direction = m.better === "none" ? "the line between them is the change, in grey because this measure names no better direction" : `the line between them is the change, green where B is better and red where it is worse (${m.better} is better)`;
    setups = `<h4 class="av-rc-sub">Setup by setup</h4><p class="av-muted">Each setup's ${esc(m.label)} in A and in B on one scale; ${direction}. Setups are matched by label, then id, then id apart from an ending each side shares, then reference with reference.</p><div class="av-rc-slope">${scale}${slope}${scale.replace("av-ticks av-ticks--top", "av-ticks")}</div>`;
  } else if (A.measure || B.measure) {
    // Each report's values in its own words beside its own track.
    const apart = (s: MemberSummary, letter: string) => `<div><p class="av-rc-top"><span class="av-rc-letter" aria-hidden="true">${letter}</span><span>${esc(s.metric || "no headline value")}</span></p>${s.measure ? lanes(s, true) : ""}${s.rows.length ? `<ul class="av-rc-values">${s.rows.map(r => `<li>${esc(r.label)}: ${esc(r.text)}</li>`).join("")}</ul>` : ""}</div>`;
    setups = `<h4 class="av-rc-sub">Each report on its own measure</h4><div class="av-rc-cols">${apart(A, "A")}${apart(B, "B")}</div>`;
  }
  const heat = (c: { k: number; n: number } | null) => c && c.n ? `<span class="av-rc-cell" style="--p:${Math.round((c.k / c.n) * 100)}%">${c.k}/${c.n}</span>` : `<span class="av-rc-cell av-rc-cell--none">${c ? "0 valid" : "not run"}</span>`;
  // The cases both ran on which the headline metric has a value or an invalid result on either side; a case both ran on
  // other metrics only has no row here.
  const tableCases = same && isRate(m) ? sharedCases.filter(c => pairs.some(x => caseCell(model, A, x.a!.id, c.id) || caseCell(model, B, x.b!.id, c.id))) : [];
  const caseTable = same && isRate(m) && tableCases.length && pairs.length ? `<h4 class="av-rc-sub">Case by case</h4><p class="av-muted">Successes of valid observations on each case both reports ran; deeper green is more.</p><div class="av-scroll-x"><table class="av-table av-table--compact av-rc-cases"><thead><tr><th scope="col">Case</th>${pairs.map(x => `<th scope="col" colspan="2">${esc(x.a!.label)}</th>`).join("")}</tr><tr><th scope="col"><span class="av-sr">Case</span></th>${pairs.map(() => '<th scope="col">A</th><th scope="col">B</th>').join("")}</tr></thead><tbody>${tableCases.map(c => `<tr><th scope="row">${esc(c.label)}</th>${pairs.map(x => `<td>${heat(caseCell(model, A, x.a!.id, c.id))}</td><td>${heat(caseCell(model, B, x.b!.id, c.id))}</td>`).join("")}</tr>`).join("")}</tbody></table></div>${onlyA.length || onlyB.length ? `<p class="av-muted">${onlyA.length ? `Only in A: ${onlyA.map(c => esc(c.label)).join(", ")}. ` : ""}${onlyB.length ? `Only in B: ${onlyB.map(c => esc(c.label)).join(", ")}.` : ""}</p>` : ""}` : "";
  const costRows = pairs.filter(x => isNum(x.a!.cost) || isNum(x.b!.cost));
  const cost = costRows.length ? `<h4 class="av-rc-sub">Cost per run</h4><div class="av-scroll-x"><table class="av-table av-table--compact"><thead><tr><th scope="col">Setup</th><th scope="col" class="av-num">A median</th><th scope="col" class="av-num">B median</th></tr></thead><tbody>${costRows.map(x => `<tr><th scope="row">${esc(x.a!.label)}</th><td class="av-num">${fmtUsd(x.a!.cost)}</td><td class="av-num">${fmtUsd(x.b!.cost)}</td></tr>`).join("")}</tbody></table></div>` : "";
  const letters = (letter: string) => `<p class="av-rc-top"><span class="av-rc-letter" aria-hidden="true">${letter}</span><span class="av-sr">${letter}</span></p>`;
  const results = `<details class="av-rc-full"${same ? "" : " open"}><summary>Each report's results as its own report draws them</summary><div class="av-rc-cols"><div>${letters("A")}${resultsInFull(model, A, "rc-a")}</div><div>${letters("B")}${resultsInFull(model, B, "rc-b")}</div></div></details>`;
  const full = `<details class="av-rc-full"><summary>Each decision as its report states it: the rule, its checks, what holds and what does not</summary><div class="av-rc-cols"><div>${letters("A")}${decisionInFull(model, A, "rc-a")}</div><div>${letters("B")}${decisionInFull(model, B, "rc-b")}</div></div></details>`;
  return frame("report-compare", input, `<div class="av-rc-sides">${side(A, "A")}${side(B, "B")}</div><div class="av-rc-what"><h4 class="av-rc-sub">What differs</h4><ul>${diffs}</ul></div>${setups}${caseTable}${cost}${results}${full}`);
}
