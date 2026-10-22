/** Views of a collection of reports: the decision board, the report index,
 * pass-rate shifts across reports, cost against gain, the timeline, suggested
 * pairs and two reports side by side. Each reads the specification's
 * `collection`, takes `members` or `themes` to draw a subset, and links every
 * report to its full reading (#report/ID) and every pair to its side-by-side
 * view (#compare/A/B). Every setup keeps the color and shape it has in its own
 * report, and every number is a count, a Wilson interval or a Newcombe
 * interval drawn from the embedded data. */
import { attrs, esc, fmtInt, fmtPct, fmtUsd, inline, isNum, prose, svg } from "../core";
import { createContext } from "../model";
import type { RenderContext } from "../model";
import { newcombe } from "../stats";
import { caseCell, collectionModel, matchRows, selectMembers } from "../collection";
import type { CollectionModel, MemberRow, MemberSummary } from "../collection";
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
/** A rate change in percentage points, signed. */
const points = (d: number | null) => !isNum(d) ? "—" : `${Math.round(d * 100) > 0 ? "+" : Math.round(d * 100) < 0 ? "−" : "±"}${Math.abs(Math.round(d * 100))} pts`;
const span = (iv: [number, number] | null) => iv ? `${points(iv[0]).replace(" pts", "")} to ${points(iv[1])}` : "no interval";
const rateText = (r: MemberRow) => r.n ? `${r.k} of ${r.n} passed (${fmtPct(r.rate)})` : "no valid runs";
const costText = (x: number | null) => isNum(x) ? `$${x.toFixed(x >= 10 ? 0 : 2)}` : "not recorded";

/** The decision as a compact stamp, in the verdict block's words and icons. */
export function stampHtml(s: MemberSummary, extra = ""): string {
  return `<span class="av-cx-stamp av-cx-v--${s.verdict}${extra ? " " + extra : ""}"><span class="av-cx-stamp-icon" aria-hidden="true">${verdictIcons[s.verdict]}</span><span class="av-cx-stamp-word">${esc(s.stamp)}</span></span>`;
}

function lanesOf(s: MemberSummary): Array<[string, MemberRow[]]> {
  const out: Array<[string, MemberRow[]]> = [];
  for (const r of s.rows) { const lane = out.find(([l]) => l === r.lane); if (lane) lane[1].push(r); else out.push([r.lane, [r]]); }
  return out;
}

/** Every setup on a 0–100% track, one track per model (or group): the reference as a ring, each change as a line from it. */
function lanes(s: MemberSummary, names: boolean): string {
  if (!s.rows.length) return `<p class="av-cx-norate">${s.metric ? `${esc(s.metric)} is not a rate, so it is not drawn here` : "No rate recorded"}.</p>`;
  const groups = lanesOf(s), multi = groups.length > 1;
  const said = groups.map(([lane, rows]) => `${lane ? `${lane}: ` : ""}${rows.map(r => `${r.label} ${rateText(r)}${r.baseline ? ", the reference" : ""}`).join("; ")}`).join(". ");
  const body = groups.map(([lane, rows]) => {
    const base = rows.find(r => r.baseline && r.rate !== null);
    const shifts = base ? rows.filter(r => r !== base && r.rate !== null).map(r => {
      const d = r.rate! - base.rate!, dir = Math.abs(d) < 1e-9 ? "flat" : d > 0 ? "up" : "down";
      return `<span class="av-cx-shift av-cx-shift--${dir}" style="--a:${pos(Math.min(r.rate!, base.rate!))};--b:${pos(Math.max(r.rate!, base.rate!))}"></span>`;
    }).join("") : "";
    const cis = rows.filter(r => r.interval).map(r => `<span class="av-cx-ci" style="--a:${pos(r.interval![0])};--b:${pos(r.interval![1])};--c:${s.arms.color(r.id)}"></span>`).join("");
    const placed: number[] = [];
    const lift = new Map<MemberRow, number>();
    for (const r of [...rows].filter(x => x.rate !== null).sort((x, y) => Number(y.baseline) - Number(x.baseline))) {
      const k = placed.filter(v => Math.abs(v - r.rate!) < 0.035).length;
      placed.push(r.rate!); lift.set(r, k ? (k % 2 ? -1 : 1) * Math.ceil(k / 2) * 8 : 0);
    }
    const high = Math.max(0, ...[...lift.values()].map(Math.abs));
    const dots = rows.filter(r => r.rate !== null).map(r => `<span class="av-cx-pt${r.baseline ? " av-cx-pt--base" : ""}" style="--x:${pos(r.rate!)};--dy:${lift.get(r) || 0}px" data-av-tip="${esc(`${r.label}: ${rateText(r)}${r.baseline ? " · the reference" : ""}`)}">${s.arms.glyph(r.id)}</span>`).join("");
    const none = rows.every(r => r.rate === null) ? '<span class="av-cx-none">no valid runs</span>' : "";
    return `<div class="av-cx-lane">${multi || names ? `<span class="av-cx-lane-name">${esc(lane || "setups")}</span>` : ""}<div class="av-cx-track"${high ? ` style="height:${22 + 2 * high}px"` : ""}>${shifts}${cis}${dots}${none}</div></div>`;
  }).join("");
  return `<div class="av-cx-lanes" role="img" aria-label="${esc(`${s.metric[0].toUpperCase()}${s.metric.slice(1)} by setup. ${said}.`)}">${body}</div>`;
}

/** The exact counts behind a member's tracks. */
function numbers(s: MemberSummary): string {
  if (!s.rows.length) return '<p class="av-muted">No rate recorded.</p>';
  const costs = s.rows.some(r => isNum(r.cost)), gains = s.gains.length > 0, lanesShown = new Set(s.rows.map(r => r.lane)).size > 1 || s.rows.some(r => r.lane);
  const head = ["Setup", ...(lanesShown ? [s.kind === "trial" ? "Model" : "Group"] : []), s.noun === "runs" ? "Passed" : "Succeeded", "Rate", "95% interval", ...(costs ? ["Median cost per run"] : []), ...(gains ? ["Change from reference"] : [])];
  const rows = s.rows.map(r => {
    const g = s.gains.find(x => x.arm === r.id);
    return `<tr><th scope="row">${s.arms.tag(r.id, { id: false })}${r.baseline ? ' <span class="av-chip av-chip--base">reference</span>' : ""}</th>${lanesShown ? `<td>${esc(r.lane || "—")}</td>` : ""}<td class="av-num">${r.k} / ${r.n}${r.invalid ? ` <span class="av-muted">(${r.invalid} invalid)</span>` : ""}</td><td class="av-num">${fmtPct(r.rate)}</td><td class="av-num">${r.interval ? `${fmtPct(r.interval[0])}–${fmtPct(r.interval[1])}` : "—"}</td>${costs ? `<td class="av-num">${fmtUsd(r.cost)}</td>` : ""}${gains ? `<td class="av-num">${g ? `${points(g.delta)} <span class="av-muted">(${span(g.interval)})</span>` : r.baseline ? "reference" : "other model"}</td>` : ""}</tr>`;
  }).join("");
  return `<div class="av-scroll-x"><table class="av-table av-table--compact"><thead><tr>${head.map(h => `<th scope="col">${h}</th>`).join("")}</tr></thead><tbody>${rows}</tbody></table></div>`;
}

function facts(s: MemberSummary): string {
  const items = [
    s.dates ? `<li><span class="av-sr">Ran </span>${esc(s.dates)}</li>` : "",
    `<li>${plural(s.runs, s.noun === "runs" ? "run" : "observation")}${s.invalid ? ` <span class="av-cx-invalid">${fmtInt(s.invalid)} invalid</span>` : ""}</li>`,
    s.models.length ? `<li>${s.models.map(m => `<code>${esc(m)}</code>`).join(" ")}</li>` : "",
    isNum(s.cost) ? `<li>${esc(costText(s.cost))} recorded</li>` : "",
  ];
  return `<ul class="av-cx-facts">${items.join("")}</ul>`;
}

function tallyBar(ms: MemberSummary[], label: string): string {
  const counts = VERDICT_ORDER.map(v => [v, ms.filter(s => s.verdict === v).length] as const).filter(([, n]) => n > 0);
  const said = counts.map(([v, n]) => `${n} ${verdictWords[v].toLowerCase()}`).join(", ");
  return `<div class="av-dec-bar" role="img" aria-label="${esc(`${label}: ${said}`)}">${counts.map(([v, n]) => `<span class="av-dec-seg av-cx-v--${v}" style="flex:${n}"><b>${n}</b> ${esc(verdictWords[v])}</span>`).join("")}</div>`;
}

// ------------------------------------------------------------------ decision board

export function decisions(input: Subset, ctx: RenderContext): string {
  const model = need(ctx, "decisions");
  const chosen = new Set(selectMembers(model, input).map(s => s.id));
  const themes = model.themes.map(t => ({ ...t, members: t.members.filter(s => chosen.has(s.id)) })).filter(t => t.members.length);
  if (!themes.length) return frame("decisions", input, empty("No report to show."));
  const all = themes.flatMap(t => t.members);
  const rows = themes.map(t => `<div class="av-dec-row"><h3 class="av-dec-theme">${esc(t.label)} <span class="av-muted">${plural(t.members.length, "report")}</span></h3><ul class="av-dec-tiles">${t.members.map(s =>
    `<li><a class="av-dec-tile av-cx-v--${s.verdict}" href="${open(s.id)}"${attrs({ "data-av-tip": s.headline ? s.headline.replace(/\*\*|`/g, "") : undefined })}><span class="av-dec-icon" aria-hidden="true">${verdictIcons[s.verdict]}</span><span class="av-dec-word">${esc(s.stamp)}</span><span class="av-dec-name">${esc(s.short)}</span></a></li>`).join("")}</ul></div>`).join("");
  const legend = `<p class="av-dec-legend">${VERDICT_ORDER.filter(v => all.some(s => s.verdict === v)).map(v => `<span class="av-cx-v--${v}"><span class="av-dec-icon" aria-hidden="true">${verdictIcons[v]}</span>${esc(verdictWords[v])}</span>`).join("")}<span class="av-muted">A stamp's own words, where its report gives them, replace these.</span></p>`;
  return frame("decisions", input, `${tallyBar(all, "Decisions")}${legend}<div class="av-dec-board">${rows}</div>`);
}

// ------------------------------------------------------------------ report index

export function reports(input: Subset & { layouts?: string[] }, ctx: RenderContext): string {
  const model = need(ctx, "reports");
  const chosen = selectMembers(model, input), ids = new Set(chosen.map(s => s.id));
  const themes = model.themes.map(t => ({ ...t, members: t.members.filter(s => ids.has(s.id)) })).filter(t => t.members.length);
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
  const pick = (s: MemberSummary) => `<button type="button" class="av-btn av-btn--small av-rx-pick" data-av-rx-pick="${esc(s.id)}" aria-pressed="false" aria-label="Compare ${esc(s.short)}" hidden><span class="av-rx-pick-box" aria-hidden="true"></span>Compare</button>`;
  const card = (s: MemberSummary) => {
    const follows = s.follows ? model.byId.get(s.follows) : undefined;
    const head = ctx.uid(`rx-${s.id}`);
    return `<li class="av-rx-card av-cx-v--${s.verdict}"${item(s)}>
<article aria-labelledby="${head}"><header class="av-rx-card-head">${stampHtml(s)}${s.kind === "comparison" ? '<span class="av-chip">comparison</span>' : ""}</header>
<h4 class="av-rx-title" id="${head}"><a href="${open(s.id)}">${esc(s.title)}</a></h4>
${s.headline ? `<p class="av-rx-headline">${inline(s.headline)}</p>` : ""}${s.note ? `<p class="av-rx-note">${inline(s.note)}</p>` : ""}
<div class="av-rx-chart"><span class="av-eyebrow">${esc(s.metric)} by setup</span>${lanes(s, false)}</div>
${facts(s)}${follows ? `<p class="av-rx-follows">Follows <a href="${open(follows.id)}">${esc(follows.short)}</a> · <a href="${pairHref(follows.id, s.id)}">compare the two</a></p>` : ""}
<details class="av-rx-exact"><summary>Exact numbers</summary>${numbers(s)}</details>
<div class="av-rx-actions"><a class="av-btn av-btn--primary" href="${open(s.id)}">Read the full report<span aria-hidden="true"> →</span></a>${pick(s)}</div>
</article></li>`;
  };
  const grouped = (body: (t: typeof themes[number]) => string, story: boolean) => themes.map(t => { const hid = ctx.uid(`rx-theme-${t.id || "other"}`); return `<section class="av-rx-theme" data-av-rx-group aria-labelledby="${hid}"><header class="av-rx-theme-head"><h3 id="${hid}" class="av-rx-theme-title">${esc(t.label)}</h3>${tallyBar(t.members, t.label)}${story ? prose(t.summary, "av-rx-story") : ""}</header>${body(t)}</section>`; }).join("");
  const row = (s: MemberSummary) => `<li class="av-rx-row av-cx-v--${s.verdict}"${item(s)}><span class="av-rx-row-stamp">${stampHtml(s)}</span><div class="av-rx-row-main"><a class="av-rx-row-title" href="${open(s.id)}">${esc(s.title)}</a>${s.headline ? `<p class="av-rx-row-head">${inline(s.headline)}</p>` : ""}</div><div class="av-rx-row-chart">${lanes(s, false)}</div><div class="av-rx-row-facts">${facts(s)}</div><div class="av-rx-row-pick">${pick(s)}</div></li>`;
  const changes = (s: MemberSummary) => { const ds = s.gains.map(g => g.delta).filter(isNum); return ds.length ? { v: Math.max(...ds.map(Math.abs)), text: ds.length === 1 ? points(ds[0]) : `${points(Math.min(...ds))} to ${points(Math.max(...ds))}` } : null; };
  const pooled = (s: MemberSummary) => { const k = s.rows.reduce((t, r) => t + r.k, 0), n = s.rows.reduce((t, r) => t + r.n, 0); return n ? k / n : null; };
  const head = (label: string, kind: "text" | "number", note?: string) => `<th scope="col"${attrs({ "data-av-rx-sortable": kind, title: note })}><button type="button" class="av-rx-sort">${label}<span class="av-rx-sort-mark" aria-hidden="true"></span></button></th>`;
  const table = `<div class="av-scroll-x"><table class="av-table av-table--compact av-rx-table"><thead><tr>${head("Decision", "text")}${head("Report", "text")}${themes.length > 1 ? head("Theme", "text") : ""}${head("Models", "text")}${head("Runs", "number")}${head("Invalid", "number")}${head("Passed", "number", "Every setup together, valid runs only")}${head("Changes from reference", "number", "Each setup against its reference on the same model; sorted by the largest change either way")}${head("Cost", "number")}${head("Ran", "text")}</tr></thead><tbody>${themes.flatMap(t => t.members.map(s => {
    const c = changes(s), p = pooled(s);
    return `<tr${item(s)}><td data-v="${VERDICT_ORDER.indexOf(s.verdict)}">${stampHtml(s)}</td><th scope="row" data-v="${esc(s.title.toLowerCase())}"><a href="${open(s.id)}">${esc(s.short)}</a>${pick(s)}</th>${themes.length > 1 ? `<td data-v="${esc(t.label.toLowerCase())}">${esc(t.label)}</td>` : ""}<td data-v="${esc(s.models.join(" "))}">${s.models.map(m => `<code>${esc(m)}</code>`).join(" ") || "—"}</td><td class="av-num" data-v="${s.runs}">${fmtInt(s.runs)}</td><td class="av-num" data-v="${s.invalid}">${fmtInt(s.invalid)}</td><td class="av-num" data-v="${p ?? -1}">${fmtPct(p)}</td><td class="av-num" data-v="${c ? c.v : -1}">${c ? c.text : "—"}</td><td class="av-num" data-v="${s.cost ?? -1}">${isNum(s.cost) ? fmtUsd(s.cost) : "—"}</td><td data-v="${esc(s.date || "")}">${esc(s.dates || "—")}</td></tr>`;
  })).join("")}</tbody></table></div>`;
  const single = [...new Set(all.flatMap(s => s.models.length === 1 ? s.models : []))];
  const columns = [...single.map(m => ({ key: m, label: m, test: (s: MemberSummary) => s.models.length === 1 && s.models[0] === m })),
    ...(all.some(s => s.models.length > 1) ? [{ key: "", label: "Several models", test: (s: MemberSummary) => s.models.length > 1 }] : []),
    ...(all.some(s => !s.models.length) ? [{ key: "", label: "Model not recorded", test: (s: MemberSummary) => !s.models.length }] : [])];
  const tile = (s: MemberSummary) => `<li${item(s)}><a class="av-dec-tile av-dec-tile--small av-cx-v--${s.verdict}" href="${open(s.id)}"${attrs({ "data-av-tip": s.headline ? s.headline.replace(/\*\*|`/g, "") : undefined })}><span class="av-dec-icon" aria-hidden="true">${verdictIcons[s.verdict]}</span><span class="av-dec-word">${esc(s.stamp)}</span><span class="av-dec-name">${esc(s.short)}</span></a></li>`;
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
  const chosen = new Set(selectMembers(model, input).filter(s => s.rows.length).map(s => s.id));
  const themes = model.themes.map(t => ({ ...t, members: t.members.filter(s => chosen.has(s.id)) })).filter(t => t.members.length);
  if (!themes.length) return frame("shifts", input, empty("No report records a rate."));
  const line = (s: MemberSummary) => {
    const measured = s.gains.filter(g => isNum(g.delta));
    if (!s.baseline) return "no reference setup named";
    if (!measured.length) return "no change measured on the reference's model";
    if (measured.length === 1) return `${points(measured[0].delta)} <span class="av-muted">(95%: ${span(measured[0].interval)})</span>`;
    const ds = measured.map(g => g.delta!);
    return Math.min(...ds) === Math.max(...ds) ? `${measured.length} changes, each ${points(ds[0])}` : `${measured.length} changes, ${points(Math.min(...ds))} to ${points(Math.max(...ds))}`;
  };
  const rows = themes.map(t => `<div class="av-sh-theme"><h3 class="av-sh-theme-title">${esc(t.label)}</h3>${t.members.map(s =>
    `<div class="av-sh-row"><div class="av-sh-name">${stampHtml(s, "av-cx-stamp--icon")}<a href="${open(s.id)}">${esc(s.short)}</a><span class="av-sh-sum">${line(s)}</span></div><div class="av-sh-plot">${lanes(s, true)}</div></div>`).join("")}</div>`).join("");
  const scale = `<div class="av-sh-scale" aria-hidden="true"><span></span><div>${[0, .25, .5, .75, 1].map(x => `<span style="--x:${pos(x)}">${x * 100}%</span>`).join("")}</div></div>`;
  const key = `<ul class="av-sh-key" aria-label="How to read this chart"><li><span class="av-cx-key-ring" aria-hidden="true"></span>the reference setup</li><li><span class="av-cx-key-dot" aria-hidden="true"></span>a setup tried (its color and shape as in its report)</li><li><span class="av-cx-key-up" aria-hidden="true"></span>more runs passed</li><li><span class="av-cx-key-down" aria-hidden="true"></span>fewer runs passed</li><li><span class="av-cx-key-ci" aria-hidden="true"></span>95% interval: where the true rate likely lies</li></ul>`;
  const table = themes.flatMap(t => t.members).flatMap(s => s.rows.map(r => {
    const g = s.gains.find(x => x.arm === r.id);
    return `<tr><th scope="row"><a href="${open(s.id)}">${esc(s.short)}</a></th><td>${esc(r.lane || "—")}</td><td>${s.arms.tag(r.id, { id: false })}${r.baseline ? ' <span class="av-chip av-chip--base">reference</span>' : ""}</td><td class="av-num">${r.k} / ${r.n}</td><td class="av-num">${fmtPct(r.rate)}</td><td class="av-num">${r.interval ? `${fmtPct(r.interval[0])}–${fmtPct(r.interval[1])}` : "—"}</td><td class="av-num">${g ? points(g.delta) : "—"}</td><td class="av-num">${g ? span(g.interval) : "—"}</td></tr>`;
  })).join("");
  const exact = `<details class="av-cx-exact"><summary>Every rate and change, exactly</summary><div class="av-scroll-x"><table class="av-table av-table--compact"><thead><tr><th scope="col">Report</th><th scope="col">Model or group</th><th scope="col">Setup</th><th scope="col">Passed</th><th scope="col">Rate</th><th scope="col">95% interval</th><th scope="col">Change from reference</th><th scope="col">95% interval of the change</th></tr></thead><tbody>${table}</tbody></table></div><p class="av-muted">Rates count valid runs only. A change is the setup's rate minus its reference's on the same model, with a 95% Newcombe interval; an interval that spans zero means the change could be chance.</p></details>`;
  return frame("shifts", input, `<div class="av-sh">${key}${scale}${rows}</div>${exact}`);
}

// ------------------------------------------------------------------ cost against gain

export function costGain(input: Subset, ctx: RenderContext): string {
  const model = need(ctx, "cost-gain");
  const ms = selectMembers(model, input);
  const points_ = ms.flatMap(s => s.gains.filter(g => isNum(g.delta) && isNum(g.costChange)).map(g => ({ s, g })));
  const left = ms.filter(s => s.rows.length > 1 && !s.gains.some(g => isNum(g.delta) && isNum(g.costChange)));
  if (!points_.length) return frame("cost-gain", input, empty("No change records both a pass-rate difference and a cost difference against its reference."));
  const W = 760, H = 440, L = 64, R = 24, T = 28, B = 56;
  const mx = Math.max(.25, ...points_.map(p => Math.abs(p.g.costChange!))) * 1.12;
  const my = Math.min(1, Math.max(.2, ...points_.flatMap(p => [Math.abs(p.g.delta!), ...(p.g.interval ? p.g.interval.map(Math.abs) : [])])) * 1.08);
  const x = (v: number) => L + ((v + mx) / (2 * mx)) * (W - L - R), y = (v: number) => T + ((my - v) / (2 * my)) * (H - T - B);
  const tick = (v: number) => `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(Math.round(v * 100))}%`;
  const xt = [-mx, -mx / 2, 0, mx / 2, mx].map(v => `<line class="av-cg-grid" x1="${x(v)}" x2="${x(v)}" y1="${T}" y2="${H - B}"/><text class="av-cg-tick" x="${x(v)}" y="${H - B + 18}" text-anchor="middle">${tick(v)}</text>`).join("");
  const yt = [-my, -my / 2, 0, my / 2, my].map(v => `<line class="av-cg-grid" x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}"/><text class="av-cg-tick" x="${L - 8}" y="${y(v) + 4}" text-anchor="end">${points(v).replace(" pts", "")}</text>`).join("");
  const quads = [["More passed, cost less", L + 8, T + 16, "start"], ["More passed, cost more", W - R - 8, T + 16, "end"], ["Fewer passed, cost less", L + 8, H - B - 10, "start"], ["Fewer passed, cost more", W - R - 8, H - B - 10, "end"]]
    .map(([t, qx, qy, a]) => `<text class="av-cg-quad" x="${qx}" y="${qy}" text-anchor="${a}">${t}</text>`).join("");
  const marks = points_.map((p, i) => {
    const cx = x(p.g.costChange!), cy = y(p.g.delta!);
    const ci = p.g.interval ? `<line class="av-cg-ci" x1="${cx}" x2="${cx}" y1="${y(Math.min(my, p.g.interval[1]))}" y2="${y(Math.max(-my, p.g.interval[0]))}"/>` : "";
    return `<g class="av-cg-pt" style="--v:${p.s.arms.color(p.g.arm)}">${ci}<circle cx="${cx.toFixed(1)}" cy="${cy.toFixed(1)}" r="10"/><text x="${cx.toFixed(1)}" y="${(cy + 4).toFixed(1)}" text-anchor="middle">${i + 1}</text></g>`;
  }).join("");
  const plot = svg(`Cost against gain: ${plural(points_.length, "change")} against their references`, H,
    `${quads}${xt}${yt}<line class="av-cg-zero" x1="${x(0)}" x2="${x(0)}" y1="${T}" y2="${H - B}"/><line class="av-cg-zero" x1="${L}" x2="${W - R}" y1="${y(0)}" y2="${y(0)}"/><text class="av-cg-axis" x="${(L + W - R) / 2}" y="${H - 12}" text-anchor="middle">Cost per run against the reference (median over cases) →</text><text class="av-cg-axis" transform="translate(16 ${(T + H - B) / 2}) rotate(-90)" text-anchor="middle">Pass rate against the reference →</text>${marks}`, W);
  const key = `<ol class="av-cg-key">${points_.map((p, i) => `<li style="--v:${p.s.arms.color(p.g.arm)}"><span class="av-cg-n" aria-hidden="true">${i + 1}</span><span class="av-cg-text">${p.s.arms.tag(p.g.arm, { id: false })} <span class="av-muted">against ${esc(p.s.arms.label(p.g.base))}${p.g.lane ? ` on ${esc(p.g.lane)}` : ""} in</span> <a href="${open(p.s.id)}">${esc(p.s.short)}</a></span><span class="av-cg-vals"><b>${points(p.g.delta)}</b> <span class="av-muted">(${span(p.g.interval)})</span> · cost <b>${tick(p.g.costChange!)}</b> · <span class="av-muted">report:</span> ${stampHtml(p.s, "av-cx-stamp--icon")}</span></li>`).join("")}</ol>`;
  const note = left.length ? `<p class="av-muted">Not drawn, for want of a reference on the same model or a recorded cost: ${left.map(s => `<a href="${open(s.id)}">${esc(s.short)}</a>`).join(", ")}.</p>` : "";
  return frame("cost-gain", input, `${plot}<p class="av-muted av-cg-read">Vertical whiskers are 95% intervals of the pass-rate change; one that crosses the middle line could be chance. Cost changes are each trial's median over its cases of the per-case difference in cost per run.</p>${key}${note}`);
}

// ------------------------------------------------------------------ timeline

const DAY = new Intl.DateTimeFormat("en-GB", { weekday: "short", day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
export function timeline(input: Subset, ctx: RenderContext): string {
  const model = need(ctx, "timeline");
  const ms = selectMembers(model, input);
  if (!ms.length) return frame("timeline", input, empty("No report to show."));
  const key = (s: MemberSummary) => `${s.date || "9999"}|${String(s.time ?? 0).padStart(15, "0")}|${String(s.index).padStart(5, "0")}`;
  const sorted = [...ms].sort((a, b) => key(a) < key(b) ? -1 : key(a) > key(b) ? 1 : 0);
  const days: Array<[string | null, MemberSummary[]]> = [];
  for (const s of sorted) { const last = days[days.length - 1]; if (last && last[0] === s.date) last[1].push(s); else days.push([s.date, [s]]); }
  const themeLabel = (id: string) => model.themes.find(t => t.id === id)?.label || "";
  const followers = (id: string) => ms.filter(x => x.follows === id);
  const item = (s: MemberSummary) => {
    const before = s.follows ? model.byId.get(s.follows) : undefined, after = followers(s.id);
    const time = isNum(s.time) ? new Date(s.time).toISOString().slice(11, 16) + " UTC" : "";
    return `<li class="av-tl-item av-cx-v--${s.verdict}"><span class="av-tl-dot" aria-hidden="true">${verdictIcons[s.verdict]}</span><div class="av-tl-body"><p class="av-tl-meta">${time ? `<span>${time}</span>` : ""}${themeLabel(s.theme) ? `<span>${esc(themeLabel(s.theme))}</span>` : ""}</p><p class="av-tl-title"><a href="${open(s.id)}">${esc(s.short)}</a> ${stampHtml(s)}</p>${s.headline ? `<p class="av-tl-head">${inline(s.headline)}</p>` : ""}${before ? `<p class="av-tl-link">↳ Follows <a href="${open(before.id)}">${esc(before.short)}</a> (${esc(before.stamp)}) · <a href="${pairHref(before.id, s.id)}">compare before and after</a></p>` : ""}${after.length ? `<p class="av-tl-link">Followed up by ${after.map(x => `<a href="${open(x.id)}">${esc(x.short)}</a>`).join(", ")}</p>` : ""}</div></li>`;
  };
  return frame("timeline", input, `<ol class="av-tl">${days.map(([d, list]) => `<li class="av-tl-day"><h3 class="av-tl-date">${d ? esc(DAY.format(new Date(`${d}T00:00:00Z`))) : "Date not recorded"}</h3><ol class="av-tl-items">${list.map(item).join("")}</ol></li>`).join("")}</ol>`);
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
  const side = (s: MemberSummary, letter: string) => `<div class="av-mu-side"><span class="av-rc-letter" aria-hidden="true">${letter}</span>${stampHtml(s)}<a class="av-mu-title" href="${open(s.id)}">${esc(s.short)}</a>${lanes(s, false)}</div>`;
  return frame("matchups", input, `<ul class="av-mu">${pairs.map(p => {
    const a = model.byId.get(p.a)!, b = model.byId.get(p.b)!;
    const kind = p.title || (p.source === "follows" ? "A follow-up and the report it followed" : "Read together");
    return `<li class="av-mu-card"><p class="av-mu-kind">${esc(kind)}</p><div class="av-mu-sides">${side(a, "A")}<span class="av-mu-arrow" aria-hidden="true">${p.source === "follows" ? "→" : "vs"}</span>${side(b, "B")}</div><p class="av-mu-diff">${differs(a, b)}</p>${p.note ? `<p class="av-muted">${inline(p.note)}</p>` : ""}<a class="av-btn" href="${pairHref(a.id, b.id)}">Compare side by side<span aria-hidden="true"> →</span></a></li>`;
  }).join("")}</ul>`);
}

// ------------------------------------------------------------------ two reports side by side

/** A member's own verdict section, rendered with its own arms and data. */
function decisionInFull(model: CollectionModel, s: MemberSummary): string {
  const spec = model.spec(s.id);
  const section = spec?.sections.find(x => x.id === "verdict");
  if (!spec || !section) return empty("This report has no verdict section.");
  const mctx = createContext(spec, spec.cases || {});
  return section.blocks.map(b => b.type === "verdict" ? verdict(b as never, mctx) : b.type === "figures" ? figures(b as never) : "").join("");
}

export function reportCompare(input: { a: string; b: string; title?: string; description?: string | string[]; note?: string; id?: string }, ctx: RenderContext): string {
  const model = need(ctx, "report-compare");
  const A = model.byId.get(input.a), B = model.byId.get(input.b);
  if (!A || !B) return frame("report-compare", input, empty(`Not in this collection: ${[!A ? input.a : "", !B ? input.b : ""].filter(Boolean).join(" and ")}.`));
  const side = (s: MemberSummary, letter: "A" | "B") => `<div class="av-rc-side av-rc-side--${letter.toLowerCase()}"><p class="av-rc-top"><span class="av-rc-letter" aria-hidden="true">${letter}</span>${stampHtml(s)}</p><h3 class="av-rc-title"><span class="av-sr">${letter}: </span><a href="${open(s.id)}">${esc(s.title)}</a></h3>${s.headline ? `<p class="av-rc-headline">${inline(s.headline)}</p>` : ""}${facts(s)}<a class="av-btn" href="${open(s.id)}">Read ${letter} in full<span aria-hidden="true"> →</span></a></div>`;
  const matched = matchRows(A, B);
  const pooled = (s: MemberSummary) => { const k = s.rows.reduce((t, r) => t + r.k, 0), n = s.rows.reduce((t, r) => t + r.n, 0); return { k, n }; };
  const pa = pooled(A), pb = pooled(B);
  const casesA = new Set(A.cases.map(c => c.id)), sharedCases = B.cases.filter(c => casesA.has(c.id)), onlyA = A.cases.filter(c => !B.cases.some(x => x.id === c.id)), onlyB = B.cases.filter(c => !casesA.has(c.id));
  const pairs = matched.filter(m => m.a && m.b);
  const diffs = [
    `<li>${differs(A, B)}.</li>`,
    `<li>Setups: ${pairs.length ? `${plural(pairs.length, "setup")} matched` : "none matched"}${matched.some(m => m.a && !m.b) ? `; ${matched.filter(m => m.a && !m.b).length} only in A` : ""}${matched.some(m => !m.a && m.b) ? `; ${matched.filter(m => !m.a && m.b).length} only in B` : ""}.</li>`,
    `<li>Cases: ${sharedCases.length ? `${plural(sharedCases.length, "case")} in both` : "none in common"}${onlyA.length ? `; ${onlyA.length} only in A` : ""}${onlyB.length ? `; ${onlyB.length} only in B` : ""}.</li>`,
    A.rows.length && B.rows.length ? `<li>Every setup together: A ${pa.k} of ${pa.n} passed (${fmtPct(pa.n ? pa.k / pa.n : null)}), B ${pb.k} of ${pb.n} (${fmtPct(pb.n ? pb.k / pb.n : null)}).</li>` : "",
  ].join("");
  const marker = (r: MemberRow, letter: string, s: MemberSummary, near: boolean) => r.rate === null ? "" : `<span class="av-rc-mark av-rc-mark--${letter.toLowerCase()}" style="--x:${pos(r.rate)};--dy:${near ? (letter === "A" ? -7 : 7) : 0}px" data-av-tip="${esc(`${letter} · ${r.label}: ${rateText(r)}`)}">${letter}</span>`;
  const slope = matched.map(m => {
    const name = m.a && m.b ? (m.a.label === m.b.label ? esc(m.a.label) : `${esc(m.a.label)} <span class="av-muted">↔</span> ${esc(m.b.label)}`) : esc((m.a || m.b)!.label);
    const d = m.a && m.b && m.a.rate !== null && m.b.rate !== null ? m.b.rate - m.a.rate : null;
    const iv = m.a && m.b && m.a.n && m.b.n ? newcombe(m.b.k, m.b.n, m.a.k, m.a.n) : null;
    const dir = d === null ? "" : Math.abs(d) < 1e-9 ? "flat" : d > 0 ? "up" : "down";
    const shift = d !== null ? `<span class="av-cx-shift av-cx-shift--${dir}" style="--a:${pos(Math.min(m.a!.rate!, m.b!.rate!))};--b:${pos(Math.max(m.a!.rate!, m.b!.rate!))}"></span>` : "";
    const nums = `${m.a ? `A ${m.a.k}/${m.a.n}` : "not in A"} · ${m.b ? `B ${m.b.k}/${m.b.n}` : "not in B"}${d !== null ? ` · <b>${points(d)}</b> <span class="av-muted">(${span(iv)})</span>` : ""}`;
    const said = `${(m.a || m.b)!.label}: ${m.a ? `A ${rateText(m.a)}` : "not in A"}; ${m.b ? `B ${rateText(m.b)}` : "not in B"}${d !== null ? `; B minus A ${points(d)}, 95% interval ${span(iv)}` : ""}`;
    return `<div class="av-rc-row"><div class="av-rc-name">${name}${m.how && m.how !== "same label" ? ` <span class="av-chip">${esc(m.how)}</span>` : ""}${(m.a || m.b)!.baseline ? ' <span class="av-chip av-chip--base">reference</span>' : ""}</div><div class="av-cx-track av-rc-track" role="img" aria-label="${esc(said)}">${shift}${m.a ? marker(m.a, "A", A, d !== null && Math.abs(d) < 0.04) : ""}${m.b ? marker(m.b, "B", B, d !== null && Math.abs(d) < 0.04) : ""}</div><div class="av-rc-nums">${nums}</div></div>`;
  }).join("");
  const scale = `<div class="av-sh-scale av-rc-scale" aria-hidden="true"><span></span><div>${[0, .25, .5, .75, 1].map(x => `<span style="--x:${pos(x)}">${x * 100}%</span>`).join("")}</div><span></span></div>`;
  const heat = (c: { k: number; n: number } | null) => c && c.n ? `<span class="av-rc-cell" style="--p:${Math.round((c.k / c.n) * 100)}%">${c.k}/${c.n}</span>` : `<span class="av-rc-cell av-rc-cell--none">${c ? "0 valid" : "not run"}</span>`;
  const caseTable = sharedCases.length && pairs.length ? `<h4 class="av-rc-sub">Case by case</h4><p class="av-muted">Passed of valid runs on each case both reports ran; deeper green passed more.</p><div class="av-scroll-x"><table class="av-table av-table--compact av-rc-cases"><thead><tr><th scope="col">Case</th>${pairs.map(m => `<th scope="col" colspan="2">${esc(m.a!.label)}</th>`).join("")}</tr><tr><th scope="col"><span class="av-sr">Case</span></th>${pairs.map(() => '<th scope="col">A</th><th scope="col">B</th>').join("")}</tr></thead><tbody>${sharedCases.map(c => `<tr><th scope="row">${esc(c.label)}</th>${pairs.map(m => `<td>${heat(caseCell(model, A, m.a!.id, c.id))}</td><td>${heat(caseCell(model, B, m.b!.id, c.id))}</td>`).join("")}</tr>`).join("")}</tbody></table></div>${onlyA.length || onlyB.length ? `<p class="av-muted">${onlyA.length ? `Only in A: ${onlyA.map(c => esc(c.label)).join(", ")}. ` : ""}${onlyB.length ? `Only in B: ${onlyB.map(c => esc(c.label)).join(", ")}.` : ""}</p>` : ""}` : "";
  const costRows = pairs.filter(m => isNum(m.a!.cost) || isNum(m.b!.cost));
  const cost = costRows.length ? `<h4 class="av-rc-sub">Cost per run</h4><div class="av-scroll-x"><table class="av-table av-table--compact"><thead><tr><th scope="col">Setup</th><th scope="col" class="av-num">A median</th><th scope="col" class="av-num">B median</th></tr></thead><tbody>${costRows.map(m => `<tr><th scope="row">${esc(m.a!.label)}</th><td class="av-num">${fmtUsd(m.a!.cost)}</td><td class="av-num">${fmtUsd(m.b!.cost)}</td></tr>`).join("")}</tbody></table></div>` : "";
  const setups = A.rows.length || B.rows.length ? `<h4 class="av-rc-sub">Setup by setup</h4><p class="av-muted">Each setup's ${esc(A.metric === B.metric ? A.metric : "rate")} in A and in B on one scale; the line between them is the change, green where B passed more. Setups are matched by label, then id, then reference with reference.</p><div class="av-rc-slope">${scale}${slope}</div>` : "";
  const full = `<details class="av-rc-full"><summary>Each decision as its report states it: the rule, its checks, what holds and what does not</summary><div class="av-rc-cols"><div><p class="av-rc-top"><span class="av-rc-letter" aria-hidden="true">A</span><span class="av-sr">A</span></p>${decisionInFull(model, A)}</div><div><p class="av-rc-top"><span class="av-rc-letter" aria-hidden="true">B</span><span class="av-sr">B</span></p>${decisionInFull(model, B)}</div></div></details>`;
  return frame("report-compare", input, `<div class="av-rc-sides">${side(A, "A")}${side(B, "B")}</div><div class="av-rc-what"><h4 class="av-rc-sub">What differs</h4><ul>${diffs}</ul></div>${setups}${caseTable}${cost}${full}`);
}
