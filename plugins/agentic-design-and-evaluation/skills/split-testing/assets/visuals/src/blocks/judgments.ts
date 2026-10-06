/** Views of what was compared and how it was judged, for a comparison of any
 * alternatives: the alternatives themselves (nesting, attributes, texts with
 * diffs), head-to-head judgments and rankings, a decision matrix for
 * qualitative or mixed decisions, and every observation in one table. Each
 * block reads ctx.comparison unless it is given its own data. Nothing here
 * assumes what an alternative is: a sandwich, an ad, a prompt, a research
 * direction. Values the author did not supply are shown as missing, never
 * filled in, and totals appear only when the author supplied the weights. */
import { attrs, count as whole, esc, fmtInt, fmtPct, inline, isNum, num, prose, wilson } from "../core";
import { diffRuns, diffStats, DiffLine, lineDiff, splitLines, wordDiff } from "../diff";
import { fingerprint } from "../identity";
import type { Alternative, Comparison, Metric, MetricSummary, Observation } from "../comparison-model";
import { groupPath, judgmentMetric, metricOf, observationStatus, ordinalLevels, summarize, winMatrix } from "../comparison-stats";
import type { RenderContext } from "../model";
import { empty, frame, FrameInput, pos } from "./frame";

interface DataInput extends FrameInput {
  /** Comparison data in place of the report's (ReportSpec.comparison). */
  data?: Comparison;
}

// ------------------------------------------------------------------ shared

const plural = (n: number, one: string, many = `${one}s`) => `${fmtInt(n)} ${n === 1 ? one : many}`;
const isObject = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);
const str = (v: unknown): string | undefined => typeof v === "string" && v.trim() !== "" ? v : undefined;
const sr = (t: string) => `<span class="av-sr">${esc(t)}</span>`;
const missing = (t: string, why: string) => `<span class="av-missing" title="${esc(why)}">${esc(t)}</span>`;
const letterOf = (i: number): string => i < 26 ? String.fromCharCode(65 + i) : letterOf(Math.floor(i / 26) - 1) + letterOf(i % 26);
const chars = (t: string) => Array.from(t).length;
const joinWords = (words: string[]): string => words.length <= 1 ? words.join("") : `${words.slice(0, -1).join(", ")} and ${words[words.length - 1]}`;
/** A number as written: whole numbers grouped, others to six significant digits. */
const shown = (n: number): string => Number.isInteger(n) ? n.toLocaleString("en-US") : String(Number(n.toPrecision(6)));
const byIdentity = (ctx: RenderContext) => (x: string, y: string) => ctx.arms.index(x) - ctx.arms.index(y);
const list = <T,>(v: T[] | undefined): T[] => Array.isArray(v) ? v : [];

/** The comparison a block reads; explicit data registers its alternatives with the arm identities. */
function comparisonOf(input: DataInput, ctx: RenderContext, block: string): Comparison {
  const data = input.data ?? ctx.comparison;
  if (!isObject(data) || !Array.isArray((data as Comparison).alternatives)) {
    throw new TypeError(`A ${block} block needs comparison data (the report spec's "comparison" field, which comparisonReport() sets) or its own "data" with an alternatives list.`);
  }
  if (input.data) for (const a of input.data.alternatives) if (isObject(a) && typeof a.id === "string") ctx.arms.add(a.id, { label: str(a.label), note: str(a.note) });
  return data as Comparison;
}
/** The comparison's alternatives that have an id, once each, narrowed to a requested subset or group-path prefix, in identity order. */
function altsOf(data: Comparison, ctx: RenderContext, only?: string[], groups?: string[]): Alternative[] {
  const seen = new Set<string>(), out: Alternative[] = [];
  for (const a of data.alternatives) {
    if (!isObject(a) || typeof a.id !== "string" || !a.id || seen.has(a.id)) continue;
    if (Array.isArray(only) && !only.includes(a.id)) continue;
    if (Array.isArray(groups) && groups.length && !groups.every((g, i) => groupPath(a.group)[i] === String(g))) continue;
    seen.add(a.id); out.push(a);
  }
  return out.sort((x, y) => ctx.arms.index(x.id) - ctx.arms.index(y.id));
}
const caseLabel = (data: Comparison, ctx: RenderContext, id: string): string => str(list(data.cases).find(c => c?.id === id)?.label) || ctx.caseLabels[id] || id;
const metricLabel = (data: Comparison, id: string): string => str(metricOf(data, id)?.label) || id;
const subhead = (title: string, note = "") => `<h4 class="av-jv-subhead"><span class="av-eyebrow">${esc(title)}</span>${note ? `<span class="av-jv-subnote">${esc(note)}</span>` : ""}</h4>`;

// ------------------------------------------------------------------ alternatives

export interface AlternativesInput extends DataInput {
  /** Alternatives to show, a subset of the comparison's. */
  alternatives?: string[];
  /** The alternative whose text is the reference for diffs; defaults to the comparison's baseline. */
  baseline?: string;
  /** Attribute names to leave out. */
  hide?: string[];
  /** Groups of alternatives meant to receive identical material, in place of the comparison's. */
  identical?: string[][];
}

const canon = (v: unknown): string => v === undefined ? "∅ unrecorded" : (JSON.stringify(v) ?? "∅");
const LONG = 320;

/** A long or multi-line value folds to its first lines with a control that shows all of it. */
function clamp(value: string, what: string): string {
  const lines = splitLines(value).length;
  if (value.length <= LONG && lines <= 3) return `<code class="av-alt-code${value.length > 32 || lines > 1 ? " av-alt-code--long" : ""}">${esc(value)}</code>`;
  return `<details class="av-alt-clamp"><summary><code class="av-alt-code av-alt-preview" aria-hidden="true">${esc(value)}</code><span class="av-alt-toggle"><span class="av-alt-more">Show all${lines > 1 ? ` ${fmtInt(lines)} lines` : ""}</span><span class="av-alt-less">Show less</span>${sr(` of ${what}`)}</span></summary><code class="av-alt-code av-alt-full">${esc(value)}</code></details>`;
}

function attributeValue(v: unknown, what: string): string {
  if (v === undefined) return missing("not recorded", "This alternative records no value for it.");
  if (v === null) return missing("none", "Recorded as no value.");
  if (typeof v === "number") return Number.isFinite(v) ? `<code class="av-alt-code">${esc(v)}</code>` : missing("not a number", "The recorded value is not a finite number.");
  if (typeof v === "boolean") return `<code class="av-alt-code">${v ? "true" : "false"}</code>`;
  if (typeof v === "string") return v === "" ? missing("empty", "An empty value.") : clamp(v, what);
  return clamp(canon(v), what);
}

interface Material { letter: string; key: string; text: string; alts: string[]; anchor: string }

function diffRow(l: DiffLine, pieces?: Array<{ text: string; changed: boolean }>): string {
  const sign = l.op === "add" ? "+" : l.op === "del" ? "−" : "", word = l.op === "add" ? "Added: " : l.op === "del" ? "Removed: " : "";
  const body = pieces ? pieces.map(p => p.changed ? `<mark class="av-diff-word">${esc(p.text)}</mark>` : esc(p.text)).join("") : esc(l.text);
  return `<div class="av-diff-row av-diff-row--${l.op}"><span class="av-diff-n" aria-hidden="true">${l.a ?? ""}</span><span class="av-diff-n" aria-hidden="true">${l.b ?? ""}</span><span class="av-diff-sign" aria-hidden="true">${sign}</span><span class="av-diff-text">${word ? sr(word) : ""}${body}</span></div>`;
}

/** Rows for a run of diff lines; a removed line directly replaced by an added one marks the words that changed. */
function diffRows(lines: DiffLine[]): string {
  let out = "";
  for (let i = 0; i < lines.length;) {
    if (lines[i].op !== "del") { out += diffRow(lines[i]); i++; continue; }
    let d = i; while (d < lines.length && lines[d].op === "del") d++;
    let e = d; while (e < lines.length && lines[e].op === "add") e++;
    const dels = lines.slice(i, d), adds = lines.slice(d, e), words = dels.map((l, k) => k < adds.length ? wordDiff(l.text, adds[k].text) : null);
    out += dels.map((l, k) => diffRow(l, words[k]?.before)).join("") + adds.map((l, k) => diffRow(l, words[k]?.after)).join("");
    i = e;
  }
  return out;
}

function diffView(ref: Material, m: Material, refName: string): { html: string; added: number; removed: number; rows: number } {
  const lines = lineDiff(ref.text, m.text), stats = diffStats(lines), runs = diffRuns(lines);
  const rows = runs.reduce((n, r) => n + (r.fold ? 1 : r.lines.length), 0);
  const body = runs.map(r => r.fold
    ? `<details class="av-diff-fold"><summary><span>${esc(plural(r.lines.length, "unchanged line"))}</span></summary>${diffRows(r.lines)}</details>`
    : diffRows(r.lines)).join("");
  const title = `Changes from ${refName}`;
  const note = !stats.added && !stats.removed ? `<p class="av-alt-textnote">The two texts differ only in line endings or a final line break.</p>` : "";
  return {
    added: stats.added, removed: stats.removed, rows,
    html: `<div class="av-alt-diffhead"><span class="av-eyebrow">${esc(title)}</span><span class="av-alt-legend"><span class="av-alt-legend-add">${esc(`+ ${plural(stats.added, "line")} added`)}</span><span class="av-alt-legend-del">${esc(`− ${plural(stats.removed, "line")} removed`)}</span></span></div>${note}${stats.added || stats.removed ? `<div class="av-diff" role="group" aria-label="${esc(`${title} to Text ${m.letter}`)}">${body}</div>` : ""}`,
  };
}

interface GroupNode { name: string; alts: Alternative[]; kids: Map<string, GroupNode>; total: number }
const newNode = (name: string): GroupNode => ({ name, alts: [], kids: new Map(), total: 0 });
function tally(node: GroupNode): number { node.total = node.alts.length + [...node.kids.values()].reduce((n, k) => n + tally(k), 0); return node.total; }
function depthOf(node: GroupNode): number { return node.kids.size ? 1 + Math.max(...[...node.kids.values()].map(depthOf)) : 0; }

export function alternatives(input: AlternativesInput, ctx: RenderContext): string {
  const data = comparisonOf(input, ctx, "alternatives");
  const alts = altsOf(data, ctx, input.alternatives);
  if (!alts.length) return frame("alternatives", input, empty("No alternatives to show."));
  const ids = alts.map(a => a.id), n = alts.length;
  const hide = new Set(list(input.hide).filter(h => typeof h === "string"));
  const baseline = [input.baseline, data.baseline].find((b): b is string => typeof b === "string" && ids.includes(b));

  // Attributes: those every alternative records identically are one line; the rest are a table.
  const keys: string[] = [];
  for (const a of alts) if (isObject(a.attributes)) for (const k of Object.keys(a.attributes)) if (!hide.has(k) && !keys.includes(k)) keys.push(k);
  const valueOf = (a: Alternative, k: string): unknown => isObject(a.attributes) && k in a.attributes ? a.attributes[k] : undefined;
  const differs = n > 1 ? keys.filter(k => new Set(alts.map(a => canon(valueOf(a, k)))).size > 1) : [];
  const shared = keys.filter(k => !differs.includes(k));

  // Texts: identical texts share a letter.
  const mats: Material[] = [], matOf = new Map<string, Material | null>();
  for (const a of alts) {
    if (typeof a.content !== "string" || a.content === "") { matOf.set(a.id, null); continue; }
    const key = fingerprint(a.content);
    let m = mats.find(x => x.key === key);
    if (!m) { m = { letter: letterOf(mats.length), key, text: a.content, alts: [], anchor: ctx.uid(`alt-text-${key}`) }; mats.push(m); }
    m.alts.push(a.id); matOf.set(a.id, m);
  }
  const withText = alts.filter(a => matOf.get(a.id)).length, textVaries = mats.length > 1 || (mats.length === 1 && withText < n);
  const matChip = (m: Material) => `<a class="av-alt-mat" href="#${esc(m.anchor)}"><span class="av-alt-letter" aria-hidden="true">${esc(m.letter)}</span>${esc(`Text ${m.letter}`)}</a>`;

  // Identical material: groups the author listed, and alternatives whose every recorded attribute and text match.
  const listed = list(input.identical ?? data.identical).filter(Array.isArray).map(g => g.filter((x): x is string => typeof x === "string" && ids.includes(x))).filter(g => g.length > 1);
  const whole1 = (a: Alternative) => [...keys.map(k => `${k}=${canon(valueOf(a, k))}`), `text=${matOf.get(a.id)?.key ?? "∅"}`].join("\n");
  const recorded = (a: Alternative) => keys.some(k => valueOf(a, k) !== undefined) || !!matOf.get(a.id);
  const names = (xs: string[]) => xs.length <= 2 ? joinWords(xs.map(id => ctx.arms.label(id))) : `${xs.length} other alternatives`;
  const chips = new Map<string, string>();
  for (const a of alts) {
    const group = listed.find(g => g.includes(a.id));
    const others = group ? group.filter(b => b !== a.id) : alts.filter(b => b.id !== a.id && recorded(a) && whole1(b) === whole1(a)).map(b => b.id);
    if (!others.length) continue;
    const apart = group ? [...keys.filter(k => others.some(b => canon(valueOf(alts.find(x => x.id === b)!, k)) !== canon(valueOf(a, k)))), ...(others.some(b => (matOf.get(b)?.key ?? "") !== (matOf.get(a.id)?.key ?? "")) ? ["text"] : [])] : [];
    chips.set(a.id, apart.length || (group && !recorded(a))
      ? `<span class="av-alt-ident av-alt-ident--warn"><span class="av-chip av-chip--warn">listed as identical</span><span class="av-alt-ident-text">${esc(apart.length ? `but differs from ${names(others)} in ${joinWords(apart)}` : "but records nothing to confirm it")}</span></span>`
      : `<span class="av-alt-ident"><span class="av-chip">identical material</span><span class="av-alt-ident-text">${esc(`with ${names(others)}`)}</span></span>`);
  }

  // The nesting.
  const root = newNode("");
  for (const a of alts) { let at = root; for (const g of groupPath(a.group)) { let k = at.kids.get(g); if (!k) { k = newNode(g); at.kids.set(g, k); } at = k; } at.alts.push(a); }
  tally(root);
  const levels = depthOf(root);
  const card = (a: Alternative): string => {
    const mat = matOf.get(a.id), note = str(a.note);
    const flags = [a.id === baseline ? '<span class="av-chip av-chip--base">baseline</span>' : "", chips.get(a.id) || "", mat && (mats.length > 1 || withText < n) ? matChip(mat) : ""].filter(Boolean).join("");
    return `<li class="av-alt-card" data-arm="${esc(a.id)}" style="--c:${ctx.arms.color(a.id)}"><div class="av-alt-card-head">${ctx.arms.tag(a.id)}</div>${prose(str(a.description), "av-alt-desc")}${note ? `<p class="av-alt-note">${inline(note)}</p>` : ""}${flags ? `<div class="av-alt-flags">${flags}</div>` : ""}</li>`;
  };
  const renderNode = (node: GroupNode): string => node.alts.map(card).join("") + [...node.kids.values()].map(k =>
    `<li class="av-alt-group"><div class="av-alt-group-head"><span class="av-alt-group-name">${esc(k.name || "unnamed group")}</span><span class="av-alt-group-count">${esc(plural(k.total, "alternative"))}</span></div><ul class="av-alt-list">${renderNode(k)}</ul></li>`).join("");
  const tree = `<ul class="av-alt-list av-alt-list--root${levels ? " av-alt-list--nested" : ""}">${renderNode(root)}</ul>`;

  // One sentence on how they differ.
  const phrase = (k: string) => `<strong>${esc(k)}</strong>`;
  const parts = [...differs.map(phrase), ...(textVaries ? [`<strong>the text</strong>${mats.length > 1 ? ` (${esc(plural(mats.length, "distinct text"))})` : ""}`] : [])];
  const topGroups = root.kids.size;
  const groupNote = topGroups ? `, in ${esc(plural(topGroups, "group"))}${levels > 1 ? ` nested ${esc(fmtInt(levels))} deep` : ""}` : "";
  const lede = n === 1
    ? `One alternative is recorded, so nothing is compared here.`
    : parts.length
      ? `${esc(plural(n, "alternative"))}${groupNote}. They differ in ${joinWords(parts)}${shared.length || (mats.length && !textVaries) ? "; every other recorded attribute is the same" : ""}.`
      : keys.length || mats.length
        ? `${esc(plural(n, "alternative"))}${groupNote}. Every recorded attribute${mats.length ? " and text" : ""} is the same, so any difference in their results is chance.`
        : `${esc(plural(n, "alternative"))}${groupNote}. No attributes or texts were recorded, so only their descriptions set them apart.`;

  const pairs = (ks: string[]) => `<dl class="av-alt-pairs">${ks.map(k => `<div><dt>${esc(k)}</dt><dd>${attributeValue(valueOf(alts[0], k), k)}</dd></div>`).join("")}${mats.length === 1 && withText === n ? `<div><dt>Text</dt><dd>${matChip(mats[0])}</dd></div>` : ""}</dl>`;
  const sharedHtml = (shared.length || (mats.length === 1 && withText === n)) && n > 0
    ? `<div class="av-alt-shared"><span class="av-eyebrow">${n === 1 ? "Attributes" : "Same for every alternative"}</span>${pairs(shared)}</div>` : "";
  const cols = [...differs, ...(textVaries ? ["\u0000text"] : [])];
  const table = n > 1 && cols.length
    ? `<div class="av-alt-differs"><span class="av-eyebrow">Differs between alternatives</span><div class="av-scroll-x av-alt-scroll"><table class="av-table av-alt-table"><thead><tr><th scope="col">Alternative</th>${cols.map(k => `<th scope="col">${esc(k === "\u0000text" ? "Text" : k)}</th>`).join("")}</tr></thead><tbody>${alts.map(a => `<tr data-arm="${esc(a.id)}"><th scope="row">${ctx.arms.tag(a.id, { id: false })}</th>${cols.map(k => {
      const label = k === "\u0000text" ? "Text" : k;
      const cell = k === "\u0000text" ? (matOf.get(a.id) ? matChip(matOf.get(a.id)!) : missing("none", "This alternative records no text.")) : attributeValue(valueOf(a, k), k);
      return `<td data-label="${esc(label)}"><div class="av-alt-val">${cell}</div></td>`;
    }).join("")}</tr>`).join("")}</tbody></table></div></div>` : "";

  // The texts, lettered, each with its changes from the reference text.
  let texts = "";
  if (mats.length) {
    const fromBase = baseline ? mats.find(m => m.alts.includes(baseline)) : undefined;
    const ref = fromBase ?? mats[0], refName = `Text ${ref.letter}${fromBase ? " (the baseline’s text)" : ""}`;
    const items = mats.map(m => {
      const name = `Text ${m.letter}`, lines = splitLines(m.text).length;
      const diff = mats.length > 1 && m !== ref ? diffView(ref, m, refName) : null;
      const full = `<pre class="av-pre av-alt-pre">${esc(m.text)}</pre>`;
      const users = m.alts.length === n && n > 1 ? '<span class="av-alt-users-all">every alternative</span>' : m.alts.map(a => ctx.arms.tag(a, { id: false })).join("");
      const delta = diff && (diff.added || diff.removed) ? `<span class="av-alt-delta" title="${esc(`Lines added and removed, compared with ${refName}`)}">${diff.added ? `<span class="av-alt-delta-add">+${fmtInt(diff.added)}</span>` : ""}${diff.removed ? `<span class="av-alt-delta-del">−${fmtInt(diff.removed)}</span>` : ""}${sr(` lines compared with ${refName}`)}</span>` : "";
      const flag = mats.length > 1 && m === ref ? '<span class="av-chip">reference</span>' : "";
      const open = diff ? diff.rows <= 40 && mats.length <= 6 : lines <= 40 && mats.length <= 6;
      const body = diff ? `${diff.html}<details class="av-alt-fulltext"><summary>${esc(`Full text of ${name}`)}</summary>${full}</details>` : full;
      return `<details class="av-alt-text"${open ? " open" : ""}><summary><span class="av-alt-letter av-alt-letter--big" aria-hidden="true">${esc(m.letter)}</span><span class="av-alt-text-head"><span class="av-alt-text-name">${esc(name)}</span><span class="av-alt-text-meta">${esc(`${plural(lines, "line")} · ${plural(chars(m.text), "character")}`)}</span></span><span class="av-alt-users"><span class="av-alt-users-label">used by</span>${users}</span><span class="av-alt-text-flags">${delta}${flag}</span></summary><div class="av-alt-text-body" id="${esc(m.anchor)}">${body}</div></details>`;
    }).join("");
    const none = alts.filter(a => !matOf.get(a.id));
    const count = mats.length === 1 ? (none.length ? "one text" : n > 1 ? "one text, given to every alternative" : "one text") : `${mats.length} distinct texts; each other text shows its changes from ${refName}`;
    texts = `<div class="av-alt-texts-wrap"><h4 class="av-alt-subhead"><span class="av-eyebrow">Texts</span><span class="av-alt-subnote">${esc(count + (none.length ? `; ${plural(none.length, "alternative")} recorded none` : ""))}</span></h4><div class="av-alt-texts">${items}</div></div>`;
  }

  const hidden = hide.size ? `<p class="av-alt-foot">${esc(`Left out of this view: ${[...hide].join(", ")}.`)}</p>` : "";
  return frame("alternatives", input, `<p class="av-alt-lede">${lede}</p>${tree}${sharedHtml}${table}${texts}${hidden}`);
}

// ------------------------------------------------------------------ preferences

export interface PreferencesInput extends DataInput {
  /** The criterion to show, a preference metric's id; omitted shows the overall judgments (those naming no criterion), or the first criterion when only criteria were judged. */
  metric?: string;
  /** Alternatives to show, a subset of the comparison's. */
  alternatives?: string[];
  /** Cases to keep. */
  cases?: string[];
  /** Keep only alternatives inside this group path, outermost first. */
  groups?: string[];
}

interface WinCounts { wins: number; losses: number; ties: number }

function prefTrack(ctx: RenderContext, id: string, p: number, ci: [number, number] | null, what = "Win rate"): string {
  const c = ctx.arms.color(id);
  return `<span class="av-jv-track" role="img" aria-label="${esc(ci ? `${what} ${fmtPct(p)}, 95% interval ${fmtPct(ci[0])} to ${fmtPct(ci[1])}` : `${what} ${fmtPct(p)}`)}" style="--c:${c}">${ci ? `<span class="av-ci" style="--c:${c};--lo:${pos(ci[0])};--hi:${pos(ci[1])};--p:${pos(p)}"></span>` : ""}<span class="av-pt" style="--c:${c};--p:${pos(p)}"></span></span>`;
}

export function preferences(input: PreferencesInput, ctx: RenderContext): string {
  const data = comparisonOf(input, ctx, "preferences");
  const alts = altsOf(data, ctx, input.alternatives, input.groups), known = new Set(list(data.alternatives).filter(a => isObject(a) && typeof a.id === "string").map(a => a.id));
  const cases = Array.isArray(input.cases) ? input.cases.filter((c): c is string => typeof c === "string") : undefined;
  const allPrefs = list(data.preferences).filter(isObject), allRanks = list(data.rankings).filter(isObject);
  if (!allPrefs.length && !allRanks.length) return frame("preferences", input, empty("No head-to-head judgments or rankings were recorded."));

  // Which judgments: one criterion, or the overall ones.
  const criteria: string[] = [];
  for (const p of [...allPrefs, ...allRanks]) { const m = str(p.metric); if (m && !criteria.includes(m)) criteria.push(m); }
  const hasOverall = [...allPrefs, ...allRanks].some(p => !str(p.metric));
  const metric = str(input.metric) ?? (hasOverall ? undefined : criteria.find(c => metricOf(data, c)?.primary) ?? criteria[0]);
  const keepCase = (p: { case?: string }) => !cases || (typeof p.case === "string" && cases.includes(p.case));
  // Judgments naming no criterion belong to the overall question, or to the one preference metric the comparison declares.
  const belongs = (named: unknown, to: string | undefined): boolean => {
    const own = str(named);
    if (to === undefined) return own === undefined;
    if (own !== undefined) return own === to;
    const kind = metricOf(data, to)?.kind;
    return (kind === "preference" || kind === "rank") && judgmentMetric(data, kind) === to;
  };
  const sel = <T extends { metric?: string; case?: string }>(xs: T[]): T[] => xs.filter(p => belongs(p.metric, metric) && keepCase(p));
  // A subset of alternatives keeps only the judgments between its members, as the comparison's statistics do.
  const subset = input.alternatives || input.groups?.length ? new Set(alts.map(a => a.id)) : null;
  const filter = { cases, ...(subset ? { alternatives: [...subset] } : {}) };
  const inSubset = (a: unknown, b: unknown) => !subset || (typeof a === "string" && subset.has(a) && typeof b === "string" && subset.has(b));
  const prefs = sel(allPrefs).filter(p => inSubset(p.a, p.b)), ranks = sel(allRanks);
  const what = metric === undefined ? "overall" : metricLabel(data, metric);
  if (!prefs.length && !ranks.length) return frame("preferences", input, empty(`No judgments were recorded for ${metric === undefined ? "the overall question" : `“${what}”`}${cases ? " in the chosen cases" : ""}.`));

  // Census of the judgments themselves: undecided and unreadable ones are counted, not dropped.
  let decisive = 0, ties = 0, undecided = 0, unreadable = 0;
  const judges = new Map<string, number>();
  let unnamed = 0;
  const noteJudge = (j: unknown) => { const name = str(j); if (name) judges.set(name, (judges.get(name) || 0) + 1); else unnamed++; };
  for (const p of prefs) {
    noteJudge(p.judge);
    const a = str(p.a), b = str(p.b);
    if (!a || !b || a === b || !known.has(a) || !known.has(b)) unreadable++;
    else if (p.winner === null || p.winner === undefined) undecided++;
    else if (p.winner === "tie") ties++;
    else if (p.winner === a || p.winner === b) decisive++;
    else unreadable++;
  }
  for (const r of ranks) noteJudge(r.judge);
  const m = winMatrix(data, metric, filter);
  const at = new Map(m.ids.map((id, i) => [id, i]));
  const w = (x: string, y: string) => whole(m.wins[at.get(x) ?? -1]?.[at.get(y) ?? -1]);
  const t = (x: string, y: string) => whole(m.ties[at.get(x) ?? -1]?.[at.get(y) ?? -1]);
  const ids = alts.map(a => a.id).filter(id => at.has(id));
  const counts = (id: string, among = ids): WinCounts => ({
    wins: among.reduce((s, o) => s + (o === id ? 0 : w(id, o)), 0),
    losses: among.reduce((s, o) => s + (o === id ? 0 : w(o, id)), 0),
    ties: among.reduce((s, o) => s + (o === id ? 0 : t(id, o)), 0),
  });
  const judged = ids.filter(id => { const c = counts(id); return c.wins + c.losses + c.ties > 0; });
  const rate = (c: WinCounts) => c.wins + c.losses > 0 ? c.wins / (c.wins + c.losses) : null;

  // Lede.
  const named = judges.size;
  const judgeParts = [named ? `by ${plural(named, "judge")}` : "", unnamed ? `${fmtInt(unnamed)} without a named judge` : ""].filter(Boolean);
  const judgeText = judgeParts.length ? ` (${judgeParts.join("; ")})` : "";
  const ranked = judged.map(id => ({ id, c: counts(id) })).filter(x => x.c.wins + x.c.losses > 0).map(x => ({ ...x, p: x.c.wins / (x.c.wins + x.c.losses), ci: wilson(x.c.wins, x.c.wins + x.c.losses) })).sort((x, y) => y.p - x.p || ctx.arms.index(x.id) - ctx.arms.index(y.id));
  let leader = "";
  if (ranked.length > 1 && ranked[0].p > ranked[1].p) {
    const overlap = ranked[0].ci && ranked[1].ci && ranked[0].ci[0] <= ranked[1].ci[1];
    leader = ` ${esc(ctx.arms.label(ranked[0].id))} wins most often (${esc(fmtInt(ranked[0].c.wins))} of ${esc(fmtInt(ranked[0].c.wins + ranked[0].c.losses))} decisive judgments)${overlap ? `, but its interval overlaps ${esc(ctx.arms.label(ranked[1].id))}’s, so the gap between them may be chance` : ""}.`;
  }
  const ledeParts = [prefs.length ? `${plural(prefs.length, "head-to-head judgment")} on <strong>${esc(what)}</strong>${judgeText}: ${esc(plural(decisive, "decisive judgment"))}, ${esc(plural(ties, "tie"))}, ${esc(fmtInt(undecided))} undecided${unreadable ? `, ${esc(fmtInt(unreadable))} unreadable` : ""}.` : "", ranks.length ? `${prefs.length ? " " : ""}${plural(ranks.length, "ranking")} on <strong>${esc(what)}</strong>.` : ""];
  const lede = `<p class="av-jv-lede">${ledeParts.join("")}${leader}</p>`;
  const censusNote = (undecided || unreadable)
    ? `<p class="av-jv-note">${[undecided ? `${plural(undecided, "judgment")} reached no decision and ${undecided === 1 ? "is" : "are"} left out of the wins and losses.` : "", unreadable ? `${plural(unreadable, "judgment")} could not be read (a winner that is not one of the pair, a pair that repeats an alternative, or an alternative that is not in this comparison) and ${unreadable === 1 ? "is" : "are"} left out.` : ""].filter(Boolean).map(esc).join(" ")}</p>` : "";

  // The win matrix: the row alternative's wins and losses against each column.
  let matrix = "";
  if (judged.length > 1) {
    const row = (a: string) => `<tr data-arm="${esc(a)}"><th scope="row">${ctx.arms.tag(a, { id: false })}</th>${judged.map(b => {
      if (a === b) return `<td class="av-jv-self" aria-hidden="true">—</td>`;
      const win = w(a, b), loss = w(b, a), tie = t(a, b), total = win + loss + tie;
      const label = ctx.arms.label(b);
      if (!total) return `<td data-label="${esc(label)}">${missing("no judgments", "No judgment compared this pair.")}</td>`;
      const share = win + loss ? win / (win + loss) : 0.5;
      return `<td class="av-jv-cell${win > loss ? " av-jv-cell--lead" : ""}" data-label="${esc(label)}" style="--share:${pos(share)}"><span class="av-jv-score"><b>${esc(fmtInt(win))}</b>–<b>${esc(fmtInt(loss))}</b></span>${tie ? `<span class="av-jv-tie">+${esc(fmtInt(tie))} ${tie === 1 ? "tie" : "ties"}</span>` : ""}${sr(` ${ctx.arms.label(a)} beat ${label} ${plural(win, "time")}, lost ${plural(loss, "time")}${tie ? ` and tied ${plural(tie, "time")}` : ""}`)}</td>`;
    }).join("")}</tr>`;
    const implied = ranks.reduce((sum, r) => { const k = Array.isArray(r.order) ? r.order.filter(x => typeof x === "string" && known.has(x) && (!subset || subset.has(x))).length : 0; return sum + k * (k - 1) / 2; }, 0);
    matrix = `${subhead("Head to head", `each cell reads the row alternative’s wins–losses against the column alternative, ties beside it, shaded across by the row’s share of the decisive judgments${implied ? `; each ranking also counts as a win for the higher-placed alternative in every pair it lists (${fmtInt(implied)} pairs from ${plural(ranks.length, "ranking")})` : ""}`)}<div class="av-scroll-x av-jv-scroll"><table class="av-jv-matrix"><thead><tr><th scope="col"><span class="av-sr">Row alternative against column alternative</span></th>${judged.map(b => `<th scope="col">${ctx.arms.tag(b, { id: false })}</th>`).join("")}</tr></thead><tbody>${judged.map(row).join("")}</tbody></table></div>`;
  }
  const absent = alts.map(a => a.id).filter(id => !judged.includes(id));

  // Overall win rates, over decisive judgments only.
  let rates = "";
  if (judged.length) {
    const order = judged.slice().sort((x, y) => (rate(counts(y)) ?? -1) - (rate(counts(x)) ?? -1) || ctx.arms.index(x) - ctx.arms.index(y));
    rates = `${subhead("Win rate", "wins ÷ (wins + losses), ties left out; the bar shows a 95% Wilson interval; 50% is an even record")}<div class="av-scroll-x av-jv-scroll"><table class="av-jv-table"><thead><tr><th scope="col">Alternative</th><th scope="col" class="av-num">Wins</th><th scope="col" class="av-num">Losses</th><th scope="col" class="av-num">Ties</th><th scope="col">Win rate</th></tr></thead><tbody>${order.map(id => {
      const c = counts(id), n = c.wins + c.losses, p = rate(c), ci = p === null ? null : wilson(c.wins, n);
      return `<tr data-arm="${esc(id)}"><th scope="row">${ctx.arms.tag(id, { id: false })}</th><td class="av-num" data-label="Wins">${esc(fmtInt(c.wins))}</td><td class="av-num" data-label="Losses">${esc(fmtInt(c.losses))}</td><td class="av-num" data-label="Ties">${esc(fmtInt(c.ties))}</td><td data-label="Win rate">${p === null ? missing("no decisive judgments", "Every judgment of this alternative was a tie.") : `<div class="av-jv-rate"><span class="av-jv-track-wrap">${prefTrack(ctx, id, p, ci)}</span><span class="av-rate">${esc(fmtPct(p))}</span><span class="av-ci-text">${ci ? `${esc(fmtPct(ci[0]))}–${esc(fmtPct(ci[1]))}` : ""} · ${esc(fmtInt(n))} decisive</span></div>`}</td></tr>`;
    }).join("")}</tbody></table></div>`;
  }

  // Rankings: first places and mean position.
  let rankings = "";
  if (ranks.length) {
    const valid: string[][] = []; let bad = 0;
    for (const r of ranks) {
      const order = (Array.isArray(r.order) ? r.order : []).filter(x => !subset || (typeof x === "string" && subset.has(x)));
      if (order.length > 1 && order.every(x => typeof x === "string" && known.has(x)) && new Set(order).size === order.length) valid.push(order as string[]); else bad++;
    }
    const spans = valid.map(o => o.length), partial = valid.some(o => o.length < known.size);
    const stat = (id: string) => {
      const positions = valid.map(o => o.indexOf(id) + 1).filter(p => p > 0), firsts = valid.filter(o => o[0] === id).length;
      return { id, n: positions.length, firsts, mean: positions.length ? positions.reduce((s, p) => s + p, 0) / positions.length : null, positions, ci: positions.length ? wilson(firsts, positions.length) : null };
    };
    const rows = alts.map(a => stat(a.id)).filter(s => s.n > 0).sort((x, y) => (x.mean ?? 99) - (y.mean ?? 99) || ctx.arms.index(x.id) - ctx.arms.index(y.id));
    const top = Math.max(1, ...spans);
    if (rows.length) rankings = `${subhead("Rankings", `${plural(valid.length, "full ordering")}; mean rank counts 1 as first place${partial ? "; some rankings list only some alternatives, so each alternative is averaged over the rankings that include it" : ""}`)}<div class="av-scroll-x av-jv-scroll"><table class="av-jv-table"><thead><tr><th scope="col">Alternative</th><th scope="col">First places</th><th scope="col" class="av-num">Mean rank</th><th scope="col">Positions</th></tr></thead><tbody>${rows.map(s => {
      const dist = Array.from({ length: top }, (_, i) => s.positions.filter(p => p === i + 1).length), peak = Math.max(1, ...dist);
      return `<tr data-arm="${esc(s.id)}"><th scope="row">${ctx.arms.tag(s.id, { id: false })}</th><td data-label="First places"><div class="av-jv-rate"><span class="av-jv-track-wrap">${prefTrack(ctx, s.id, s.firsts / s.n, s.ci, "First-place share")}</span><span class="av-rate">${esc(fmtInt(s.firsts))} of ${esc(fmtInt(s.n))}</span><span class="av-ci-text">${esc(fmtPct(s.firsts / s.n))}${s.ci ? ` (${esc(fmtPct(s.ci[0]))}–${esc(fmtPct(s.ci[1]))})` : ""}</span></div></td><td class="av-num" data-label="Mean rank">${s.mean === null ? "" : esc(s.mean.toFixed(2))}</td><td data-label="Positions"><span class="av-jv-dist" role="img" aria-label="${esc(`Times placed 1st to ${top}th: ${dist.join(", ")}`)}">${dist.map((c, i) => `<span class="av-jv-dist-cell" style="--h:${pos(c / peak)}" title="${esc(`${plural(c, "time")} in position ${i + 1}`)}"><i></i><b>${esc(fmtInt(c))}</b><small>${i + 1}</small></span>`).join("")}</span></td></tr>`;
    }).join("")}</tbody></table></div>${bad ? `<p class="av-jv-note">${esc(`${plural(bad, "ranking")} could not be read (fewer than two alternatives, a repeat, or an alternative that is not in this comparison) and ${bad === 1 ? "is" : "are"} left out.`)}</p>` : ""}`;
  }

  // Breakdowns: by case, and by criterion.
  const breakdown = (title: string, note: string, rowsIn: Array<{ label: string; code?: string; m: ReturnType<typeof winMatrix>; n: number }>): string => {
    const cols = judged;
    const body = rowsIn.map(r => {
      const idx = new Map(r.m.ids.map((id, i) => [id, i]));
      const rw = (x: string, y: string) => whole(r.m.wins[idx.get(x) ?? -1]?.[idx.get(y) ?? -1]);
      const cells = cols.map(id => { const win = cols.reduce((s, o) => s + (o === id ? 0 : rw(id, o)), 0), loss = cols.reduce((s, o) => s + (o === id ? 0 : rw(o, id)), 0); return { id, win, loss, p: win + loss ? win / (win + loss) : null }; });
      const best = Math.max(-1, ...cells.map(c => c.p ?? -1)), contested = cells.filter(c => c.p !== null).length > 1;
      return `<tr><th scope="row"><span class="av-jv-rowname">${esc(r.label)}</span>${r.code && r.code !== r.label ? `<code>${esc(r.code)}</code>` : ""}<span class="av-jv-rowmeta">${esc(plural(r.n, "judgment"))}</span></th>${cells.map(c => `<td class="av-num${contested && c.p === best ? " av-jv-best" : ""}" data-label="${esc(ctx.arms.label(c.id))}">${c.p === null ? missing("none", "No decisive judgment for this alternative here.") : `<span class="av-rate">${esc(fmtPct(c.p))}</span><span class="av-jv-frac">${esc(fmtInt(c.win))}–${esc(fmtInt(c.loss))}</span>${contested && c.p === best ? sr(" (highest in this row)") : ""}`}</td>`).join("")}</tr>`;
    }).join("");
    return `${subhead(title, note)}<div class="av-scroll-x av-jv-scroll av-jv-scroll--tall"><table class="av-jv-table av-jv-table--by"><thead><tr><th scope="col">${esc(title.replace(/^By /, "").replace(/^./, c => c.toUpperCase()))}</th>${cols.map(id => `<th scope="col">${ctx.arms.tag(id, { id: false })}</th>`).join("")}</tr></thead><tbody>${body}</tbody></table></div>`;
  };
  let byCase = "";
  const caseIds: string[] = [];
  for (const p of prefs) { const c = str(p.case); if (c && !caseIds.includes(c)) caseIds.push(c); }
  if (caseIds.length > 1 && judged.length > 1) {
    byCase = breakdown("By case", "each alternative’s win rate over the decisive judgments in that case; the highest in a row is marked", caseIds.map(c => ({ label: caseLabel(data, ctx, c), code: c, m: winMatrix(data, metric, { ...filter, cases: [c] }), n: prefs.filter(p => p.case === c).length })));
    const noCase = prefs.filter(p => !str(p.case)).length;
    if (noCase) byCase += `<p class="av-jv-note">${esc(`${plural(noCase, "judgment")} name no case and ${noCase === 1 ? "is" : "are"} counted only above.`)}</p>`;
  }
  let byCriterion = "";
  const crit = [...(hasOverall && allPrefs.some(p => !str(p.metric)) ? [undefined] : []), ...criteria.filter(c => allPrefs.some(p => p.metric === c))] as Array<string | undefined>;
  if (crit.length > 1 && judged.length > 1) {
    byCriterion = breakdown("By criterion", "the same win rate for each criterion judged; the highest in a row is marked", crit.map(c => ({ label: c === undefined ? "Overall" : metricLabel(data, c), code: c, m: winMatrix(data, c, filter), n: allPrefs.filter(p => belongs(p.metric, c) && keepCase(p)).length })));
  }

  // Judges, and the alternatives no judgment mentions.
  const judgeList = judges.size || unnamed
    ? `${subhead("Judges")}<ul class="av-jv-judges">${[...judges].sort((x, y) => y[1] - x[1] || x[0].localeCompare(y[0])).map(([name, n]) => `<li><span class="av-jv-judge">${esc(name)}</span><span class="av-jv-judge-n">${esc(plural(n, "judgment"))}</span></li>`).join("")}${unnamed ? `<li><span class="av-jv-judge av-muted">not named</span><span class="av-jv-judge-n">${esc(plural(unnamed, "judgment"))}</span></li>` : ""}</ul>${named === 1 && !unnamed ? `<p class="av-jv-note">One judge made every judgment, so these results show that judge’s preferences, not agreement between judges.</p>` : ""}` : "";
  const foot = absent.length ? `<p class="av-jv-note">${esc(`No judgment mentions ${joinWords(absent.map(a => ctx.arms.label(a)))}.`)}</p>` : "";
  const selectNote = metric !== undefined && !str(input.metric) && !hasOverall && criteria.length > 1 ? `<p class="av-jv-note">${esc(`Only criteria were judged; this view shows “${what}”. Set metric to show another.`)}</p>` : "";

  return frame("preferences", input, `${lede}${censusNote}${selectNote}${matrix}${rates}${rankings}${byCase}${byCriterion}${judgeList}${foot}`);
}

// ------------------------------------------------------------------ decision matrix

export interface DecisionCriterion {
  id: string;
  label?: string;
  /** How much the criterion counts toward a weighted total; without weights no total is computed. */
  weight?: number;
  /** "lower" reverses the rating inside the total (needs a numeric scale); "none" keeps the criterion out of any total. Default "higher". */
  better?: "higher" | "lower" | "none";
  description?: string;
  /** Another word for description. */
  note?: string;
  /** A comparison metric this criterion is measured by: alternatives with no cell show the measured value, which is never scaled into a total. */
  metric?: string;
  /** Ratings by alternative id, a shorter way to write this criterion's cells: a level or number as text, yes/no as a boolean, null for no rating. */
  scores?: Record<string, string | boolean | null>;
}
export interface DecisionCell {
  criterion: string;
  alternative: string;
  /** A number, or a level name from scale.levels. */
  rating?: number | string | null;
  /** The author's note on this cell. */
  text?: string;
  /** What the rating rests on: a measurement, a source, a quotation. */
  evidence?: string | string[];
}
export interface DecisionScale {
  min?: number;
  max?: number;
  /** Ordered level names, lowest first; they stand for min, min + 1, …. */
  levels?: string[];
  /** Words for particular ratings, keyed by the rating as written ("1": "poor"). */
  labels?: Record<string, string>;
  note?: string;
}
export interface DecisionMatrixInput extends DataInput {
  criteria: DecisionCriterion[];
  cells: DecisionCell[];
  /** The alternatives to compare: ids, or {id, label}; defaults to the comparison's, then to those the cells name. */
  alternatives?: Array<string | { id: string; label?: string }>;
  scale?: DecisionScale;
}

export function decisionMatrix(input: DecisionMatrixInput, ctx: RenderContext): string {
  const criteria = list(input.criteria).filter(c => isObject(c) && typeof c.id === "string" && c.id !== "").filter((c, i, all) => all.findIndex(x => x.id === c.id) === i);
  const cellsIn = list(input.cells).filter(isObject);
  const source = input.data ?? ctx.comparison;
  if (!criteria.length) return frame("decision-matrix", input, empty("No criteria to show. A decision matrix needs a criteria list: [{ id, label?, weight? }]."));

  // The alternatives, in the order given (identity order when they come from the comparison).
  const given: Array<{ id: string; label?: string }> = [];
  const take = (id: unknown, label?: unknown) => { if (typeof id === "string" && id && !given.some(g => g.id === id)) given.push({ id, label: str(label) }); };
  if (Array.isArray(input.alternatives)) for (const a of input.alternatives) typeof a === "string" ? take(a) : isObject(a) ? take(a.id, a.label) : undefined;
  else if (source) for (const a of altsOf(source, ctx)) take(a.id, a.label);
  if (!given.length) for (const c of cellsIn) take(c.alternative);
  for (const g of given) ctx.arms.add(g.id, g.label ? { label: g.label } : undefined);
  const alts = given.map(g => g.id);
  if (!alts.length) return frame("decision-matrix", input, empty("No alternatives to show. Name them in alternatives, in the comparison, or in the cells."));

  // Scale.
  const scale: DecisionScale = isObject(input.scale) ? input.scale : {};
  const levels = Array.isArray(scale.levels) ? scale.levels.filter((l): l is string => typeof l === "string") : undefined;
  const lo = isNum(scale.min) ? scale.min : levels?.length ? 1 : undefined;
  const hi = isNum(scale.max) ? scale.max : levels?.length && lo !== undefined ? lo + levels.length - 1 : undefined;
  const scored = (r: unknown): number | null => isNum(r) ? r : typeof r === "string" && levels && levels.includes(r) ? levels.indexOf(r) + (lo ?? 1) : typeof r === "string" && /^\s*-?(\d+\.?\d*|\.\d+)\s*$/.test(r) ? Number(r) : null;

  // Cells, once per criterion and alternative; strays and repeats are said, not dropped.
  const cellAt = new Map<string, DecisionCell>();
  let stray = 0, repeats = 0;
  const cids = new Set(criteria.map(c => c.id)), aids = new Set(alts);
  for (const c of cellsIn) {
    if (typeof c.criterion !== "string" || typeof c.alternative !== "string" || !cids.has(c.criterion) || !aids.has(c.alternative)) { stray++; continue; }
    const key = `${c.criterion}\u0000${c.alternative}`;
    if (cellAt.has(key)) repeats++; else cellAt.set(key, c as unknown as DecisionCell);
  }
  // A criterion's scores are the same cells written by alternative; an explicit cell wins.
  for (const c of criteria) if (isObject(c.scores)) for (const [alt, v] of Object.entries(c.scores)) {
    if (!aids.has(alt)) { stray++; continue; }
    const key = `${c.id}\u0000${alt}`;
    if (!cellAt.has(key)) cellAt.set(key, { criterion: c.id, alternative: alt, rating: typeof v === "boolean" ? (v ? "yes" : "no") : v ?? null });
  }
  const cellOf = (crit: string, alt: string) => cellAt.get(`${crit}\u0000${alt}`);

  // A criterion tied to a comparison metric, with no cells of its own, shows each alternative's measured value.
  const summaries = new Map<string, Map<string, MetricSummary>>();
  for (const c of criteria) { const id = str(c.metric); if (id && source && metricOf(source, id) && !summaries.has(c.id)) summaries.set(c.id, new Map(summarize(source, id).map(x => [x.alternative, x]))); }
  const isMeasured = (c: DecisionCriterion) => !!str(c.metric) && !alts.some(a => cellOf(c.id, a));
  const measureDir = (c: DecisionCriterion): "higher" | "lower" | "none" => { const m = source && str(c.metric) ? metricOf(source, c.metric!) : undefined; return c.better === "higher" || c.better === "lower" || c.better === "none" ? c.better : m?.better ?? (m?.kind === "rank" ? "lower" : "none"); };
  const measured = (c: DecisionCriterion, a: string): { html: string; value: number | null } | null => {
    const x = summaries.get(c.id)?.get(a), m = source && str(c.metric) ? metricOf(source, c.metric!) : undefined;
    if (!x || !m || !x.n) return null;
    const ci = x.interval ? `, 95% interval ${fmtPct(x.interval[0])}–${fmtPct(x.interval[1])}` : "";
    const big = (t: string) => `<span class="av-jv-rating"><b class="av-num">${esc(t)}</b>${m.unit && x.mean !== undefined && x.mean !== null ? `<span class="av-jv-of">${esc(m.unit)}</span>` : ""}</span>`;
    const sub = (t: string) => `<span class="av-jv-sub">${esc(`${t}${x.invalid ? `; ${plural(x.invalid, "invalid observation")}` : ""}`)}</span>`;
    let value: number | null = null, html = "";
    if ((m.kind === "binary" || m.kind === "count") && isNum(x.rate)) { value = x.rate; html = big(fmtPct(x.rate)) + sub(`${fmtInt(whole(x.k))} of ${fmtInt(x.n)}${ci}`); }
    else if (m.kind === "numeric" && isNum(x.mean)) { value = x.mean; html = big(shown(x.mean)) + sub(`mean of ${fmtInt(x.n)}${x.interval ? `, 95% interval ${shown(x.interval[0])} to ${shown(x.interval[1])}` : ""}`); }
    else if (m.kind === "rank" && isNum(x.meanRank)) { value = x.meanRank; html = big(x.meanRank.toFixed(2)) + sub(`mean rank over ${fmtInt(x.n)}`); }
    else if (m.kind === "preference" && isNum(x.rate)) { value = x.rate; html = big(fmtPct(x.rate)) + sub(`win rate over ${fmtInt(x.n)} decisive${ci}`); }
    else if (m.kind === "ordinal" && Array.isArray(x.counts)) { const lv = ordinalLevels(source!, m), top = x.counts.indexOf(Math.max(...x.counts)); html = big(lv[top] ?? "—") + sub(`most common of ${fmtInt(x.n)}: ${x.counts.map((k, i) => `${lv[i] ?? i}: ${fmtInt(k)}`).join(" · ")}`); }
    else return null;
    return { html: `${html}<span class="av-jv-sub av-jv-measured">measured: ${esc(metricLabel(source!, m.id))}</span>`, value };
  };

  // Weights: the author's, or none.
  const weightOf = (c: DecisionCriterion): number | null => isNum(c.weight) && c.weight >= 0 ? c.weight : null;
  const badWeight = criteria.filter(c => c.weight !== undefined && c.weight !== null && weightOf(c) === null);
  const direction = (c: DecisionCriterion) => c.better === "lower" || c.better === "none" ? c.better : "higher";
  const counted = criteria.filter(c => weightOf(c) !== null && direction(c) !== "none" && !isMeasured(c));
  const reverses = counted.filter(c => direction(c) === "lower");
  const needScale = reverses.length > 0 && (lo === undefined || hi === undefined);
  const totalsOn = counted.some(c => weightOf(c)! > 0) && !needScale;
  const anyWeight = criteria.some(c => c.weight !== undefined && c.weight !== null);

  interface Term { crit: DecisionCriterion; w: number; r: number; value: number; text: string }
  const totals = new Map<string, { terms: Term[]; skipped: DecisionCriterion[]; total: number; complete: boolean }>();
  if (totalsOn) for (const a of alts) {
    const terms: Term[] = [], skipped: DecisionCriterion[] = [];
    for (const c of counted) {
      const r = scored(cellOf(c.id, a)?.rating), w = weightOf(c)!;
      if (r === null) { skipped.push(c); continue; }
      const rev = direction(c) === "lower", value = rev ? lo! + hi! - r : r;
      terms.push({ crit: c, w, r, value, text: rev ? `${shown(w)}×(${shown(lo!)}+${shown(hi!)}−${shown(r)})` : `${shown(w)}×${shown(r)}` });
    }
    totals.set(a, { terms, skipped, total: terms.reduce((s, t) => s + t.w * t.value, 0), complete: skipped.length === 0 });
  }
  const completeTotals = [...totals.values()].filter(x => x.complete).map(x => x.total);
  const topTotal = completeTotals.length > 1 ? Math.max(...completeTotals) : undefined;
  const maxPossible = totalsOn && hi !== undefined ? counted.reduce((s, c) => s + weightOf(c)! * hi, 0) : undefined;

  // Lede.
  const total = criteria.length * alts.length, assessed = criteria.reduce((n, c) => n + alts.filter(a => cellOf(c.id, a) || measured(c, a)).length, 0);
  const lede = `<p class="av-jv-lede">${esc(plural(criteria.length, "criterion", "criteria"))} × ${esc(plural(alts.length, "alternative"))}: ${esc(fmtInt(assessed))} of ${esc(fmtInt(total))} cells ${assessed === 1 ? "is" : "are"} assessed${total - assessed ? `, ${esc(fmtInt(total - assessed))} not assessed` : ""}. ${totalsOn ? `Criterion weights were supplied, so a weighted total is shown with its arithmetic.` : needScale ? `Criterion weights were supplied, but no total is computed: ${esc(joinWords(reverses.map(c => str(c.label) || c.id)))} ${reverses.length === 1 ? "is" : "are"} lower-is-better and the scale has no min and max to reverse ${reverses.length === 1 ? "it" : "them"}.` : anyWeight ? `The weights supplied leave nothing to total, so no total is computed.` : `No criterion weights were supplied, so no total is computed; read the ratings criterion by criterion.`}</p>`;

  // Cells.
  const best = new Map<string, Set<string>>();
  for (const c of criteria) {
    const d = isMeasured(c) ? measureDir(c) : direction(c), vals = alts.map(a => ({ a, r: isMeasured(c) ? measured(c, a)?.value ?? null : scored(cellOf(c.id, a)?.rating) })).filter((x): x is { a: string; r: number } => x.r !== null);
    if (d === "none" || vals.length < 2 || new Set(vals.map(v => v.r)).size < 2) continue;
    const top = d === "lower" ? Math.min(...vals.map(v => v.r)) : Math.max(...vals.map(v => v.r));
    best.set(c.id, new Set(vals.filter(v => v.r === top).map(v => v.a)));
  }
  const cellHtml = (c: DecisionCriterion, a: string): string => {
    const cell = cellOf(c.id, a);
    const arm = `<span class="av-jv-cell-arm" aria-hidden="true">${ctx.arms.tag(a, { id: false })}</span>`;
    if (!cell) {
      const m = measured(c, a);
      return m ? `${arm}${m.html}${best.get(c.id)?.has(a) ? '<span class="av-chip av-chip--pass">best</span>' : ""}` : `${arm}${missing("not assessed", "No assessment was recorded for this alternative on this criterion.")}`;
    }
    const r = cell.rating, n = scored(r), txt = str(cell.text);
    const ev = (Array.isArray(cell.evidence) ? cell.evidence : [cell.evidence]).map(str).filter((x): x is string => !!x);
    let rating = "";
    if (n !== null) {
      const word = typeof r === "string" ? r : str(scale.labels?.[String(r)]);
      const frac = lo !== undefined && hi !== undefined && hi > lo ? (n - lo) / (hi - lo) : null;
      rating = `<span class="av-jv-rating"><b class="av-num">${esc(shown(n))}</b>${hi !== undefined ? `<span class="av-jv-of">/ ${esc(shown(hi))}</span>` : ""}${word ? `<span class="av-jv-word">${esc(word)}</span>` : ""}${best.get(c.id)?.has(a) ? `<span class="av-chip av-chip--pass">best</span>` : ""}</span>${frac !== null ? `<span class="av-jv-bar" aria-hidden="true" style="--v:${pos(frac)}"></span>` : ""}`;
    } else if (typeof r === "string" && r.trim() !== "") rating = `<span class="av-jv-rating av-jv-rating--text"><span class="av-jv-word">${esc(r)}</span></span>`;
    else if (!txt && !ev.length) rating = missing("no rating", "This cell records neither a rating nor a note.");
    const evidence = ev.length ? `<details class="av-jv-evidence"><summary>${esc(ev.length === 1 ? "Evidence" : `Evidence (${ev.length})`)}</summary><ul>${ev.map(e => `<li>${inline(e)}</li>`).join("")}</ul></details>` : (n !== null || txt || rating.includes("--text")) ? `<span class="av-jv-noev">no evidence given</span>` : "";
    return `${arm}${rating}${txt ? `<p class="av-jv-text">${inline(txt)}</p>` : ""}${evidence}`;
  };
  const head = (c: DecisionCriterion) => {
    const label = str(c.label) || c.id, mo = isMeasured(c), d = mo ? measureDir(c) : direction(c), w = weightOf(c);
    return `<th scope="row"><span class="av-jv-crit">${esc(label)}</span>${label !== c.id ? `<code>${esc(c.id)}</code>` : ""}${mo ? '<span class="av-chip">measured</span>' : ""}${d === "lower" ? '<span class="av-chip">lower is better</span>' : d === "none" && !mo ? '<span class="av-chip">context only</span>' : ""}${prose(str(c.description) ?? str(c.note), "av-jv-critdesc")}${anyWeight ? `<span class="av-jv-weight-phone">${w === null ? "no weight" : `weight ${esc(shown(w))}`}</span>` : ""}</th>`;
  };
  const rows = criteria.map(c => `<tr>${head(c)}${anyWeight ? `<td class="av-num av-jv-weight">${weightOf(c) === null ? missing(c.weight === undefined || c.weight === null ? "none" : "invalid", c.weight === undefined || c.weight === null ? "No weight was supplied; this criterion is not in the total." : "A weight must be a number of 0 or more; this one is ignored.") : esc(shown(weightOf(c)!))}</td>` : ""}${alts.map(a => `<td class="av-jv-dmcell" data-label="${esc(ctx.arms.label(a))}">${cellHtml(c, a)}</td>`).join("")}</tr>`).join("");
  const foot = totalsOn ? `<tfoot><tr><th scope="row">Weighted total${maxPossible !== undefined ? `<span class="av-jv-critdesc">of a possible ${esc(shown(maxPossible))}</span>` : ""}</th>${anyWeight ? "<td></td>" : ""}${alts.map(a => { const x = totals.get(a)!; return `<td class="av-jv-total${x.complete && topTotal === x.total ? " av-jv-total--top" : ""}" data-label="${esc(ctx.arms.label(a))}"><span class="av-jv-cell-arm" aria-hidden="true">${ctx.arms.tag(a, { id: false })}</span><b>${esc(shown(x.total))}</b>${x.complete ? (topTotal === x.total ? `<span class="av-chip av-chip--pass">highest</span>` : "") : `<span class="av-chip av-chip--warn">incomplete</span>`}</td>`; }).join("")}</tr></tfoot>` : "";
  const table = `<div class="av-scroll-x av-jv-scroll"><table class="av-jv-dm"><thead><tr><th scope="col">Criterion</th>${anyWeight ? '<th scope="col" class="av-num">Weight</th>' : ""}${alts.map(a => `<th scope="col">${ctx.arms.tag(a)}</th>`).join("")}</tr></thead><tbody>${rows}</tbody>${foot}</table></div>`;

  // The arithmetic behind each total.
  let arithmetic = "";
  if (totalsOn) {
    arithmetic = `${subhead("How the totals are computed", `total = sum of weight × rating over the weighted criteria${reverses.length ? "; a lower-is-better rating is first reversed as min + max − rating" : ""}; a criterion with no number for an alternative is skipped, never guessed`)}<ul class="av-jv-sums">${alts.map(a => {
      const x = totals.get(a)!;
      return `<li data-arm="${esc(a)}"><span class="av-jv-sum-arm">${ctx.arms.tag(a, { id: false })}</span><code class="av-jv-sum">${x.terms.length ? `${esc(x.terms.map(t => t.text).join(" + "))} = ${esc(shown(x.total))}` : "no weighted criterion has a number for this alternative"}</code>${x.skipped.length ? `<span class="av-jv-skipped">${esc(`not in the total: ${joinWords(x.skipped.map(c => `${str(c.label) || c.id} (weight ${shown(weightOf(c)!)})`))}`)}</span>` : ""}</li>`;
    }).join("")}</ul>`;
  }
  const notes = [
    totalsOn && criteria.some(c => weightOf(c) === null && !badWeight.includes(c)) ? `Criteria without a weight are not in the total: ${joinWords(criteria.filter(c => weightOf(c) === null && !badWeight.includes(c)).map(c => str(c.label) || c.id))}.` : "",
    badWeight.length ? `Ignored weights (a weight must be a number of 0 or more): ${joinWords(badWeight.map(c => str(c.label) || c.id))}.` : "",
    totalsOn && criteria.some(isMeasured) ? `Measured criteria show the measured value and are not scaled into a total: ${joinWords(criteria.filter(isMeasured).map(c => str(c.label) || c.id))}.` : "",
    criteria.some(c => str(c.metric) && !summaries.has(c.id) && isMeasured(c)) ? `${joinWords(criteria.filter(c => str(c.metric) && !summaries.has(c.id) && isMeasured(c)).map(c => str(c.label) || c.id))} name${criteria.filter(c => str(c.metric) && !summaries.has(c.id) && isMeasured(c)).length === 1 ? "s" : ""} a metric the comparison does not define, so there is nothing to show for it.` : "",
    totalsOn && criteria.some(c => weightOf(c) !== null && direction(c) === "none") ? `Context only, so not in the total: ${joinWords(criteria.filter(c => weightOf(c) !== null && direction(c) === "none").map(c => str(c.label) || c.id))}.` : "",
    totalsOn && [...totals.values()].some(x => !x.complete) ? "An incomplete total leaves out criteria with no number for that alternative, so it is not comparable with a complete one." : "",
    stray ? `${plural(stray, "cell")} ${stray === 1 ? "names" : "name"} a criterion or alternative that is not in this matrix and ${stray === 1 ? "is" : "are"} not shown.` : "",
    repeats ? `${plural(repeats, "cell")} ${repeats === 1 ? "repeats" : "repeat"} a criterion and alternative already assessed; the first is shown.` : "",
    str(scale.note) ?? "",
  ].filter(Boolean);
  return frame("decision-matrix", input, `${lede}${table}${arithmetic}${notes.length ? `<div class="av-jv-notes">${notes.map(t => `<p class="av-jv-note">${esc(t)}</p>`).join("")}</div>` : ""}`);
}

// ------------------------------------------------------------------ observations

export interface ObservationsInput extends DataInput {
  /** Alternatives, cases and metrics to keep; the filters in the page can still narrow further. */
  alternatives?: string[];
  cases?: string[];
  metrics?: string[];
  /** One metric, shorthand for metrics: [id]. */
  metric?: string;
  /** Keep only alternatives inside this group path, outermost first. */
  groups?: string[];
}

const SOURCE_LINK = /^https?:\/\/[^\s"'<>]+$/i;

/** One observation's value as its metric's kind reads it; levels come from the comparison's reading of an ordinal metric. */
function valueCell(metric: Metric | undefined, o: Observation, levels: string[]): { html: string; sort: number | string } {
  const v = o.value, unit = str(metric?.unit), kind = metric?.kind;
  const withUnit = (t: string) => `${t}${unit ? `<span class="av-obs-unit">${esc(unit)}</span>` : ""}`;
  if (v === null || v === undefined || v === "") return { html: missing("no value", "No value was recorded."), sort: -Infinity };
  if (kind === "binary" && (typeof v === "boolean" || v === 0 || v === 1)) {
    const yes = v === true || v === 1;
    const tone = metric?.better === "higher" ? (yes ? "good" : "bad") : metric?.better === "lower" ? (yes ? "bad" : "good") : "plain";
    return { html: `<span class="av-obs-bool av-obs-bool--${tone}" data-value="${yes}"><span class="av-obs-bool-mark" aria-hidden="true"></span>${yes ? "yes" : "no"}</span>`, sort: yes ? 1 : 0 };
  }
  if (kind === "count" && isNum(v)) {
    const n = whole(o.n);
    return { html: `<span class="av-num">${esc(fmtInt(v))}${n ? ` of ${esc(fmtInt(n))}` : ""}</span>${n && v <= n ? `<span class="av-obs-sub">${esc(fmtPct(v / n, 1))}</span>` : ""}`, sort: v };
  }
  if (kind === "rank" && isNum(v)) return { html: `<span class="av-num">#${esc(shown(v))}</span>`, sort: v };
  if (kind === "ordinal" && (typeof v === "string" || isNum(v))) {
    let at = levels.indexOf(String(v));
    if (at < 0 && Array.isArray(metric?.levels) && isNum(v) && Number.isInteger(v) && v >= 0 && v < levels.length) at = v;
    if (at >= 0) return { html: `<span class="av-obs-level">${esc(levels[at])}</span><span class="av-obs-sub">${esc(`${at + 1} of ${levels.length}`)}</span>`, sort: at };
  }
  if (kind === "numeric" || kind === undefined || kind === "preference") { if (isNum(v)) return { html: `<span class="av-num">${withUnit(esc(shown(v)))}</span>`, sort: v }; }
  if (typeof v === "boolean") return { html: `<span class="av-obs-raw">${v ? "yes" : "no"}</span>`, sort: v ? 1 : 0 };
  return { html: `<span class="av-obs-raw">${esc(v)}</span>`, sort: isNum(v) ? v : -Infinity };
}

export function observations(input: ObservationsInput, ctx: RenderContext): string {
  const data = comparisonOf(input, ctx, "observations");
  const keepAlt = Array.isArray(input.alternatives) || input.groups?.length ? new Set(altsOf(data, ctx, input.alternatives, input.groups).map(a => a.id)) : null, keepCase = Array.isArray(input.cases) ? new Set(input.cases) : null, keepMetric = Array.isArray(input.metrics) || input.metric ? new Set([...(Array.isArray(input.metrics) ? input.metrics : []), ...(input.metric ? [input.metric] : [])]) : null;
  const known = new Set(list(data.alternatives).filter(a => isObject(a) && typeof a.id === "string").map(a => a.id));
  const keep = (x: { alternative?: unknown; case?: unknown; metric?: unknown }) => (!keepAlt || keepAlt.has(String(x.alternative))) && (!keepCase || keepCase.has(String(x.case))) && (!keepMetric || keepMetric.has(String(x.metric)));
  const raw = Array.isArray(data.observations) ? data.observations : [], status = observationStatus(data);
  const filtered = !!(keepAlt || keepCase || keepMetric);
  const aggs = list(data.aggregates).filter(isObject).filter(keep);
  if (!raw.length && !aggs.length) return frame("observations", input, empty("No observations or aggregates were recorded."));

  interface Row { kind: "observation" | "aggregate"; alt: string; caseId: string; metric: string; value: string; sort: number | string; outcome: "valid" | "invalid" | "aggregate"; reason: string; note: string; excerpt: string; source: string; unit: string }
  const rows: Row[] = [], reasons = new Map<string, number>(), levelsOf = new Map<string, string[]>();
  let observed = 0;
  raw.forEach((o0, i) => {
    const o = isObject(o0) ? o0 as unknown as Observation : null;
    if (o ? !keep(o) : filtered) return;
    observed++;
    const reason = status[i];
    if (reason) reasons.set(reason, (reasons.get(reason) || 0) + 1);
    if (!o) { rows.push({ kind: "observation", alt: "", caseId: "", metric: "", value: missing("no value", "This entry is not an observation."), sort: -Infinity, outcome: "invalid", reason: reason || "not an observation", note: "", excerpt: "", source: "", unit: "" }); return; }
    const metric = metricOf(data, String(o.metric));
    if (metric?.kind === "ordinal" && !levelsOf.has(metric.id)) levelsOf.set(metric.id, ordinalLevels(data, metric));
    const cell = valueCell(metric, o, levelsOf.get(metric?.id ?? "") || []);
    rows.push({ kind: "observation", alt: String(o.alternative ?? ""), caseId: o.case === undefined || o.case === null ? "" : String(o.case), metric: String(o.metric ?? ""), value: reason ? `<span class="av-obs-void">${cell.html}</span>` : cell.html, sort: cell.sort, outcome: reason ? "invalid" : "valid", reason: reason ?? "", note: str(o.note) ?? "", excerpt: str(o.excerpt) ?? "", source: str(o.source) ?? "", unit: o.unit === undefined || o.unit === null ? "" : String(o.unit) });
  });
  const invalid = rows.filter(r => r.outcome === "invalid").length, valid = observed - invalid;
  for (const g of aggs) {
    const metric = metricOf(data, String(g.metric)), unit = str(metric?.unit), parts: string[] = [];
    const k = num(g.k), n = num(g.n);
    if (k !== null && n !== null && n > 0) parts.push(`<span class="av-num">${esc(fmtInt(k))} of ${esc(fmtInt(n))}</span><span class="av-obs-sub">${esc(fmtPct(k / n, 1))}</span>`);
    if (num(g.mean) !== null) parts.push(`<span class="av-num">mean ${esc(shown(g.mean as number))}${unit ? ` ${esc(unit)}` : ""}</span>${num(g.sd) !== null ? `<span class="av-obs-sub">sd ${esc(shown(g.sd as number))}</span>` : ""}`);
    if (num(g.median) !== null) parts.push(`<span class="av-obs-sub">median ${esc(shown(g.median as number))}</span>`);
    if (k === null && n !== null && n > 0) parts.push(`<span class="av-obs-sub">n = ${esc(fmtInt(n))}</span>`);
    if (num(g.lo) !== null && num(g.hi) !== null) parts.push(`<span class="av-obs-sub">reported interval ${esc(shown(g.lo as number))} to ${esc(shown(g.hi as number))}</span>`);
    if (isObject(g.counts)) parts.push(`<span class="av-obs-sub">${esc(Object.entries(g.counts).filter(([, c]) => isNum(c)).map(([l, c]) => `${l}: ${fmtInt(c as number)}`).join(" · "))}</span>`);
    rows.push({ kind: "aggregate", alt: String(g.alternative ?? ""), caseId: g.case === undefined || g.case === null ? "" : String(g.case), metric: String(g.metric ?? ""), value: parts.length ? `<span class="av-obs-agg">${parts.join("")}</span>` : missing("no summary values", "This aggregate supplies no counts or statistics."), sort: num(g.mean) ?? (k !== null && n ? k / n : -Infinity), outcome: "aggregate", reason: "", note: str(g.note) ?? "", excerpt: "", source: str(g.source) ?? "", unit: "" });
  }

  const altIds = [...new Set(rows.map(r => r.alt).filter(Boolean))].sort(byIdentity(ctx)), caseIds = [...new Set(rows.map(r => r.caseId).filter(Boolean))], metricIds = [...new Set(rows.map(r => r.metric).filter(Boolean))];
  const hasCase = caseIds.length > 0, hasUnit = rows.some(r => r.unit), hasSource = rows.some(r => r.source), hasNote = rows.some(r => r.note || r.excerpt);
  const opts = (xs: string[], label: (x: string) => string) => xs.map(x => `<option value="${esc(x)}">${esc(label(x))}</option>`).join("");
  const tally = (o: Row["outcome"]) => rows.filter(r => r.outcome === o).length;
  const seg = (value: string, label: string, n: number, active = false) => `<button type="button" aria-pressed="${active}" data-outcome="${value}">${label} <span>${esc(fmtInt(n))}</span></button>`;
  const tools = `<div class="av-ledger-tools av-obs-tools" data-av-ledger-tools hidden>
<div class="av-seg" role="group" aria-label="Validity">${seg("", "All", rows.length, true)}${seg("valid", "Valid", tally("valid"))}${seg("invalid", "Invalid", tally("invalid"))}${aggs.length ? seg("aggregate", "Aggregates", tally("aggregate")) : ""}</div>
${altIds.length > 1 ? `<label class="av-field"><span>Alternative</span><select data-filter="arm"><option value="">All alternatives</option>${opts(altIds, a => ctx.arms.label(a))}</select></label>` : ""}
${caseIds.length > 1 ? `<label class="av-field"><span>Case</span><select data-filter="case"><option value="">All cases</option>${opts(caseIds, c => caseLabel(data, ctx, c))}</select></label>` : ""}
${metricIds.length > 1 ? `<label class="av-field"><span>Metric</span><select data-filter="metric"><option value="">All metrics</option>${opts(metricIds, m => metricLabel(data, m))}</select></label>` : ""}
<label class="av-field av-field--grow"><span>Search</span><input type="search" data-filter="text" placeholder="Search values, notes and sources"></label>
<output class="av-ledger-count" aria-live="polite"></output></div>`;

  const th = (key: string, label: string, sortable: "text" | "num" | "none" = "text", extra = "") => `<th scope="col" data-col="${key}"${sortable === "none" ? "" : sortable === "num" ? ' data-sortable="num"' : " data-sortable"}${extra}>${esc(label)}</th>`;
  const head = `<thead><tr>${th("n", "#", "num", ' class="av-num"')}${th("alternative", "Alternative")}${hasCase ? th("case", "Case") : ""}${th("metric", "Metric")}${th("value", "Value", "num")}${th("validity", "Validity")}${hasUnit ? th("unit", "Unit") : ""}${hasNote ? th("note", "Note", "none") : ""}${hasSource ? th("source", "Source", "none") : ""}</tr></thead>`;
  const body = rows.map((r, i) => {
    const validity = r.outcome === "invalid" ? `<span class="av-obs-state av-obs-state--invalid">invalid</span>${r.reason ? `<span class="av-obs-reason">${esc(r.reason)}</span>` : ""}`
      : r.outcome === "aggregate" ? `<span class="av-obs-state av-obs-state--aggregate">aggregate</span>` : `<span class="av-obs-state av-obs-state--valid">valid</span>`;
    const outside = r.alt && !known.has(r.alt) ? `<span class="av-chip av-chip--warn" title="This alternative is not in the comparison's list.">not listed</span>` : "";
    const metricName = r.metric ? metricLabel(data, r.metric) : "";
    const link = SOURCE_LINK.test(r.source) ? `<a href="${esc(r.source)}" rel="noopener noreferrer">${esc(r.source)}</a>` : esc(r.source);
    const noteCell = `${r.note ? `<span class="av-obs-note">${esc(r.note)}</span>` : ""}${r.excerpt ? `<details class="av-obs-excerpt"><summary>Excerpt</summary><blockquote class="av-obs-quote">${esc(r.excerpt)}</blockquote></details>` : ""}`;
    return `<tr${attrs({ "data-av-row": i, "data-arm": r.alt, "data-case": r.caseId, "data-metric": r.metric, "data-outcome": r.outcome, "data-kind": r.kind })}><td class="av-num" data-col="n">${i + 1}</td><td data-col="alternative">${r.alt ? ctx.arms.tag(r.alt, { id: false }) : missing("none named", "No alternative is named.")}${outside}</td>${hasCase ? `<td data-col="case">${r.caseId ? esc(caseLabel(data, ctx, r.caseId)) : '<span class="av-muted">—</span>'}</td>` : ""}<td data-col="metric">${metricName ? esc(metricName) : missing("none named", "No metric is named.")}${r.metric && !metricOf(data, r.metric) ? ` <span class="av-chip av-chip--warn" title="This metric is not in the comparison's list.">not listed</span>` : ""}</td><td data-col="value" data-sort="${typeof r.sort === "number" && Number.isFinite(r.sort) ? r.sort : "-1e308"}">${r.value}</td><td data-col="validity">${validity}</td>${hasUnit ? `<td data-col="unit">${r.unit ? `<code>${esc(r.unit)}</code>` : '<span class="av-muted">—</span>'}</td>` : ""}${hasNote ? `<td class="av-obs-notecell" data-col="note">${noteCell}</td>` : ""}${hasSource ? `<td class="av-obs-source" data-col="source">${r.source ? link : '<span class="av-muted">—</span>'}</td>` : ""}</tr>`;
  }).join("");

  const top = [...reasons].sort((x, y) => y[1] - x[1] || x[0].localeCompare(y[0]));
  const why = top.length ? ` Invalid, by reason: ${top.slice(0, 3).map(([r, n]) => `${String(r).trim().replace(/[.;:,]+$/, "")} (${fmtInt(n)})`).join("; ")}${top.length > 3 ? `; and ${plural(top.length - 3, "other reason")}` : ""}.` : "";
  const sentence = `${esc(plural(observed, "observation"))}${observed ? ` (${esc(fmtInt(valid))} valid, ${esc(fmtInt(invalid))} invalid)` : ""}${aggs.length ? `${observed ? " and " : ""}${esc(plural(aggs.length, "aggregate"))}` : ""}.${invalid ? `${esc(why)} An invalid observation has no usable value; it is counted here and never read as a failure.` : ""}`;
  const description = input.description ?? "Every observation and every supplied aggregate, filterable and sortable. Select a column heading to sort; excerpts open in place.";
  return frame("observations", { ...input, description }, `<p class="av-jv-lede av-obs-lede">${sentence}</p>${tools}<div class="av-scroll-x av-obs-wrap"><table class="av-obs" data-av-table="observations" data-av-noun="observations">${head}<tbody>${body}</tbody></table></div>`);
}
