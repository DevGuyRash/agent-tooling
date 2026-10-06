/** What was compared: one sentence on how the arms differ, the settings every
 * arm shared, a table of only the settings that set arms apart, which arms
 * received identical material, and the instruction and artifact texts
 * themselves, lettered (Text A, Text B) with a line diff from a reference text.
 * Reads the trial plan in the render context, or explicit `settings`. */
import { esc, fmtInt } from "../core";
import { diffRuns, diffStats, DiffLine, lineDiff, splitLines, wordDiff } from "../diff";
import { fingerprint } from "../identity";
import type { RenderContext } from "../model";
import { casePairs, displayPath, displayText, trialAxes, TrialArm, TrialReport, TrialScenario } from "../trial-model";
import { empty, frame, FrameInput } from "./frame";

export interface SetupInput extends FrameInput {
  /** Arms to show, a subset of the trial's; identity order still sets their order. */
  arms?: string[];
  /** The arm whose text is the reference for diffs; defaults to the trial's baseline. */
  baseline?: string;
  /** Groups of arms meant to receive identical material, such as calibration copies. */
  identical?: string[][];
  /** Setting names to leave out of the view (for example "base_url"). */
  hide?: string[];
  /** Arm settings keyed by arm id, in place of the trial plan's. */
  settings?: Record<string, TrialArm>;
  /** The judge's settings in place of the trial plan's; null shows no judge. */
  judge?: TrialArm | null;
  /** Case variants whose added turns to show: found by content by default (casePairs), "off", or explicit [base, variant] pairs. */
  pairs?: "auto" | "off" | Array<[string, string] | { base: string; variant: string }>;
}

type Settings = Record<string, unknown>;

/** Reading order for the settings trial.py records: the material an arm received first, since
 * it is most often what a trial varies, then how it ran; other fields follow by name. */
const ORDER = ["instructions_sha256", "artifact_sha256", "executor", "model", "effort", "base_url", "command", "codex_config", "codex_trust_hooks", "allowed_tools", "permission_mode", "approval_mode", "bare", "resources", "resources_sha256", "stub_skills"];
const LABELS: Record<string, string> = {
  executor: "Executor", model: "Model", effort: "Effort", base_url: "Base URL", command: "Command", codex_config: "Codex config",
  codex_trust_hooks: "Trusts hooks", allowed_tools: "Allowed tools", permission_mode: "Permission mode", approval_mode: "Approval mode",
  bare: "Bare", instructions_sha256: "Instructions", artifact_sha256: "Artifact", resources: "Resources", resources_sha256: "Resources digest", stub_skills: "Stub skills",
};
/** Fields that are content or annotation, not settings: texts render below, model_spec as the model's tooltip. */
const NOT_SETTINGS = new Set(["instructions_text", "instructions_truncated", "artifact_text", "artifact_truncated", "model_spec"]);
const byOrder = (x: string, y: string) => {
  const i = ORDER.indexOf(x), j = ORDER.indexOf(y);
  return (i < 0 ? ORDER.length : i) - (j < 0 ? ORDER.length : j) || x.localeCompare(y);
};

interface Kind { digest: string; text: string; cut: string; noun: string; heading: string; folder: string }
const KINDS: Kind[] = [
  { digest: "instructions_sha256", text: "instructions_text", cut: "instructions_truncated", noun: "Text", heading: "Instructions", folder: "instructions/" },
  { digest: "artifact_sha256", text: "artifact_text", cut: "artifact_truncated", noun: "Artifact", heading: "Artifacts", folder: "artifacts/" },
];

interface Material { kind: Kind; letter: string; key: string; digest?: string; text?: string; truncated: boolean; arms: string[]; anchor: string }

const label = (key: string) => LABELS[key] || (key.charAt(0).toUpperCase() + key.slice(1)).replace(/_/g, " ");
/** A label inside a sentence: "Base URL" reads "base URL", "Codex config" reads "codex config". */
const lower = (text: string) => text.replace(/^[A-Z](?![A-Z])/, c => c.toLowerCase());
const isObject = (v: unknown): v is Settings => typeof v === "object" && v !== null && !Array.isArray(v);
const present = (v: unknown) => v !== undefined && v !== null && v !== "";
const str = (v: unknown) => typeof v === "string" && v !== "" ? v : undefined;
const letterOf = (i: number): string => i < 26 ? String.fromCharCode(65 + i) : letterOf(Math.floor(i / 26) - 1) + letterOf(i % 26);
const chars = (text: string) => Array.from(text).length;
const plural = (n: number, one: string, many = `${one}s`) => `${fmtInt(n)} ${n === 1 ? one : many}`;
const hex = (v: string) => /^[0-9a-f]{16,}$/i.test(v);
const sr = (text: string) => `<span class="av-setup-sr">${esc(text)}</span>`;
const missing = (text: string, why: string) => `<span class="av-missing" title="${esc(why)}">${esc(text)}</span>`;

/** A value's identity for comparison: key order and absence never make two values differ. */
function canon(v: unknown): string {
  if (!present(v)) return "∅";
  const sort = (x: unknown): unknown => Array.isArray(x) ? x.map(sort) : isObject(x) ? Object.fromEntries(Object.keys(x).sort().map(k => [k, sort(x[k])])) : x;
  try { return JSON.stringify(sort(v)) ?? String(v); } catch { return String(v); }
}

function joinWords(words: string[]): string {
  return words.length <= 1 ? words.join("") : `${words.slice(0, -1).join(", ")} and ${words[words.length - 1]}`;
}

// ------------------------------------------------------------------ values

/** Values up to this many characters (and three lines) show whole; longer ones fold to their first lines. */
const LONG = 320;

/** Long or multi-line text, clamped to its first lines with a control that shows all of it. */
function clamp(text: string, what: string): string {
  const lines = splitLines(text).length;
  if (text.length <= LONG && lines <= 3) return `<code class="av-setup-code${text.length > 32 || lines > 1 ? " av-setup-code--long" : ""}">${esc(text)}</code>`;
  return `<details class="av-setup-clamp"><summary><code class="av-setup-code av-setup-preview" aria-hidden="true">${esc(text)}</code><span class="av-setup-toggle"><span class="av-setup-more">Show all${lines > 1 ? ` ${fmtInt(lines)} lines` : ""}</span><span class="av-setup-less">Show less</span>${sr(` of ${what}`)}</span></summary><code class="av-setup-code av-setup-full">${esc(text)}</code></details>`;
}

function digestHtml(v: string): string {
  return hex(v) ? `<code class="av-setup-digest" title="${esc(v)}">${esc(v.slice(0, 10))}</code>` : `<code class="av-setup-digest">${esc(v)}</code>`;
}

/** A lettered material ("Text B") linking to its text below, with its digest. */
function materialChip(m: Material): string {
  return `<a class="av-setup-mat" href="#${esc(m.anchor)}"><span class="av-setup-letter" aria-hidden="true">${esc(m.letter)}</span>${esc(`${m.kind.noun} ${m.letter}`)}</a>${m.digest ? digestHtml(m.digest) : ""}`;
}

/** What a value renders against: an arm's settings and lettered materials, or (arm null) the judge's settings. */
interface ValueCtx { arm: string | null; settings: Settings | undefined; materials: Map<string, Map<string, Material | null>> }

function valueHtml(key: string, vc: ValueCtx): string {
  const s = vc.settings;
  if (!s) return missing("not recorded", "The plan records no settings for this arm.");
  const kind = KINDS.find(k => k.digest === key);
  if (kind && vc.arm !== null) {
    const m = vc.materials.get(kind.digest)?.get(vc.arm);
    return m ? materialChip(m) : missing(kind.noun === "Text" ? "none" : "not set", `This entry names no ${kind.heading.toLowerCase()}.`);
  }
  const v = s[key];
  if (!present(v)) return missing("not set", "This entry does not set it.");
  if (key === "model" && typeof v === "string" && str(s.model_spec) && s.model_spec !== v)
    return `<code class="av-setup-code av-setup-spec" title="${esc(`As written in the plan: ${s.model_spec}`)}">${esc(v)}</code>${sr(` (written in the plan as ${s.model_spec})`)}`;
  if (/_sha256$/.test(key) && typeof v === "string") return digestHtml(v);
  if (typeof v === "number") return Number.isFinite(v) ? `<code class="av-setup-code">${esc(v)}</code>` : missing("not a number", "The recorded value is not a finite number.");
  // A recorded value can carry an absolute path (a hook command, say); its home-directory prefix reads as ~, as the run directory does.
  if (typeof v === "boolean" || typeof v === "string") return clamp(typeof v === "string" ? displayText(v) : String(v), label(key));
  if (Array.isArray(v)) {
    if (!v.length) return missing("empty", "An empty list.");
    const items = v.map(x => displayText(typeof x === "string" ? x : canon(x)));
    return items.length <= 3 && items.every(x => x.length <= 100) && !items.some(x => /[\r\n]/.test(x))
      ? `<span class="av-setup-items">${items.map(x => `<code class="av-setup-code${x.length > 32 ? " av-setup-code--long" : ""}">${esc(x)}</code>`).join("")}</span>`
      : clamp(items.join("\n"), label(key));
  }
  if (isObject(v)) {
    const entries = Object.keys(v).sort().map(k => `${k} ${displayText(typeof v[k] === "string" ? v[k] as string : canon(v[k]))}`);
    return entries.length ? `<span class="av-setup-items av-setup-items--inline">${entries.map(x => `<code class="av-setup-code">${esc(x)}</code>`).join("")}</span>` : missing("empty", "An empty setting.");
  }
  return `<code class="av-setup-code">${esc(displayText(canon(v)))}</code>`;
}

/** Name–value pairs: short values sit on one wrapping line, long ones stack beneath. */
function pairs(keys: string[], vc: ValueCtx): string {
  const isLong = (k: string) => {
    if (/_sha256$/.test(k)) return false;
    const v = vc.settings?.[k];
    return (typeof v === "string" && (v.length > 60 || /[\r\n]/.test(v))) || (Array.isArray(v) && (v.length > 1 || v.some(x => typeof x !== "string" || x.length > 60))) || isObject(v);
  };
  const item = (k: string) => `<div><dt title="${esc(`plan field: ${k}`)}">${esc(label(k))}</dt><dd>${valueHtml(k, vc)}</dd></div>`;
  const short = keys.filter(k => !isLong(k)), long = keys.filter(isLong);
  return `${short.length ? `<dl class="av-setup-pairs">${short.map(item).join("")}</dl>` : ""}${long.length ? `<dl class="av-setup-pairs av-setup-pairs--stacked">${long.map(item).join("")}</dl>` : ""}`;
}

// ------------------------------------------------------------------ materials

function collectMaterials(kind: Kind, arms: string[], settings: Record<string, Settings | undefined>, ctx: RenderContext): { list: Material[]; byArm: Map<string, Material | null> } {
  const list: Material[] = [], byArm = new Map<string, Material | null>();
  for (const a of arms) {
    const s = settings[a], digest = str(s?.[kind.digest]), text = typeof s?.[kind.text] === "string" ? s![kind.text] as string : undefined;
    if (!digest && text === undefined) { byArm.set(a, null); continue; }
    const key = digest ? `sha:${digest}` : `text:${fingerprint(text!)}`;
    let m = list.find(x => x.key === key);
    if (!m) { m = { kind, letter: letterOf(list.length), key, digest, text, truncated: s?.[kind.cut] === true, arms: [], anchor: ctx.uid(`setup-${kind.noun}-${key}`) }; list.push(m); }
    else if (m.text === undefined && text !== undefined) { m.text = text; m.truncated = s?.[kind.cut] === true; }
    m.arms.push(a);
    byArm.set(a, m);
  }
  return { list, byArm };
}

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

function diffView(ref: Material, m: Material, refName: string): { html: string; added: number; removed: number; rows: number } | null {
  if (ref.text === undefined || m.text === undefined) return null;
  const lines = lineDiff(ref.text, m.text), stats = diffStats(lines), runs = diffRuns(lines);
  const rows = runs.reduce((n, r) => n + (r.fold ? 1 : r.lines.length), 0);
  const notes: string[] = [];
  if (!stats.added && !stats.removed) notes.push("The two texts differ only in line endings or a final line break.");
  if (ref.truncated || m.truncated) notes.push(`Only the part of each text included in this report is compared: ${ref.truncated && m.truncated ? "both were" : `${(ref.truncated ? ref : m).kind.noun} ${(ref.truncated ? ref : m).letter} was`} cut.`);
  const body = runs.map(r => r.fold
    ? `<details class="av-diff-fold"><summary><span>${esc(plural(r.lines.length, "unchanged line"))}</span></summary>${diffRows(r.lines)}</details>`
    : diffRows(r.lines)).join("");
  const title = `Changes from ${refName}`;
  return {
    added: stats.added, removed: stats.removed, rows,
    html: `<div class="av-setup-diffhead"><span class="av-eyebrow">${esc(title)}</span><span class="av-setup-legend">${stats.added || !stats.removed ? `<span class="av-setup-legend-add">${esc(`+ ${plural(stats.added, "line")} added`)}</span>` : ""}${stats.removed || !stats.added ? `<span class="av-setup-legend-del">${esc(`− ${plural(stats.removed, "line")} removed`)}</span>` : ""}</span></div>${notes.map(t => `<p class="av-setup-textnote">${esc(t)}</p>`).join("")}${stats.added || stats.removed ? `<div class="av-diff" role="group" aria-label="${esc(`${title} to ${m.kind.noun} ${m.letter}`)}">${body}</div>` : ""}`,
  };
}

function materialSection(kind: Kind, list: Material[], baseline: string | undefined, runDir: string | undefined, ctx: RenderContext, armCount: number): string {
  if (!list.length) return "";
  const noun = kind.noun === "Text" ? "text" : "artifact", nouns = `${noun}s`;
  const fromBaseline = baseline ? list.find(m => m.arms.includes(baseline) && m.text !== undefined) : undefined;
  const ref = fromBaseline || list.find(m => m.text !== undefined);
  const refName = ref ? `${kind.noun} ${ref.letter}${fromBaseline ? ` (the baseline’s ${noun})` : ""}` : "";
  const where = `${runDir ? displayPath(runDir).replace(/\/+$/, "") + "/" : ""}${kind.folder}`;
  const items = list.map(m => {
    const name = `${kind.noun} ${m.letter}`;
    const hasText = m.text !== undefined;
    const diff = list.length > 1 && ref && m !== ref ? diffView(ref, m, refName) : null;
    const lines = hasText ? splitLines(m.text!).length : 0;
    const full = hasText ? `<pre class="av-pre av-setup-pre">${esc(m.text)}</pre>` : "";
    const notes: string[] = [];
    if (!hasText) notes.push(`<p class="av-setup-textnote">Not included in this report. The run directory keeps it in <code>${esc(where)}</code>${m.digest ? `, named by its digest <code>${esc(hex(m.digest) ? m.digest.slice(0, 10) + "…" : m.digest)}</code>` : ""}.</p>`);
    else if (m.truncated) notes.push(`<p class="av-setup-textnote">${esc(`Cut for this report after ${plural(chars(m.text!), "character")}; the whole ${noun} is in `)}<code>${esc(where)}</code>.</p>`);
    if (hasText && list.length > 1 && ref && m !== ref && ref.text === undefined) notes.push(`<p class="av-setup-textnote">${esc(`No changes shown: ${ref.kind.noun} ${ref.letter} is not included in this report.`)}</p>`);
    const textBody = diff
      ? `${diff.html}<details class="av-setup-fulltext"><summary>${esc(`Full text of ${name}`)}</summary>${full}</details>${notes.join("")}`
      : `${notes.join("")}${full}`;
    const users = m.arms.length === armCount && armCount > 1 ? '<span class="av-setup-users-all">every arm</span>' : m.arms.map(a => ctx.arms.tag(a, { id: false })).join("");
    const meta = hasText ? `${plural(lines, "line")} · ${plural(chars(m.text!), "character")}` : "";
    const delta = diff && (diff.added || diff.removed) ? `<span class="av-setup-delta" title="${esc(`Lines added and removed, compared with ${refName}`)}">${diff.added ? `<span class="av-setup-delta-add">+${fmtInt(diff.added)}</span>` : ""}${diff.removed ? `<span class="av-setup-delta-del">−${fmtInt(diff.removed)}</span>` : ""}${sr(` lines compared with ${refName}`)}</span>` : "";
    const flag = list.length > 1 && m === ref ? '<span class="av-chip">reference</span>' : !hasText ? '<span class="av-chip av-chip--warn">not in this report</span>' : m.truncated ? '<span class="av-chip av-chip--warn">cut</span>' : "";
    const open = !!diff && diff.rows <= 60;
    return `<details class="av-setup-text"${open ? " open" : ""}><summary><span class="av-setup-letter av-setup-letter--big" aria-hidden="true">${esc(m.letter)}</span><span class="av-setup-text-head"><span class="av-setup-text-name">${esc(name)}</span><span class="av-setup-text-meta">${esc(meta)}${meta && m.digest ? " · " : ""}${m.digest ? digestHtml(m.digest) : ""}</span></span><span class="av-setup-users"><span class="av-setup-users-label">used by</span>${users}</span><span class="av-setup-text-flags">${delta}${flag}</span></summary><div class="av-setup-text-body" id="${esc(m.anchor)}">${textBody}</div></details>`;
  }).join("");
  const given = list.reduce((k, m) => k + m.arms.length, 0), without = armCount - given;
  const count = list.length === 1
    ? (armCount === 1 ? `one ${noun}` : without ? `one ${noun}` : `one ${noun}, given to every arm`)
    : `${list.length} distinct ${nouns}${ref ? `; each other ${noun} shows its changes from ${refName}` : ""}`;
  const none = without > 0 ? `; ${plural(without, "arm")} received none` : "";
  return `<div class="av-setup-materials"><h4 class="av-setup-subhead"><span class="av-eyebrow">${esc(kind.heading)}</span><span class="av-setup-subnote">${esc(count + none)}</span></h4><div class="av-setup-texts">${items}</div></div>`;
}

// ------------------------------------------------------------------ case variants

interface Pair { base: string; variant: string }
interface Added { key: string; turns: string[]; pairs: Pair[]; anchor: string }

/** Variant cases: the same case with turns added. Pairs whose variant differs from its
 * base in more than added turns are named, not described. */
function variantsOf(data: TrialReport, input: SetupInput, ctx: RenderContext): { added: Added[]; other: Pair[]; count: number } {
  const none = { added: [], other: [], count: 0 };
  if (input.pairs === "off") return none;
  const scen = new Map<string, TrialScenario>();
  for (const sc of Array.isArray(data.plan?.scenarios) ? data.plan!.scenarios! : []) if (isObject(sc) && typeof sc.name === "string" && !scen.has(sc.name)) scen.set(sc.name, sc);
  const raw: unknown[] = Array.isArray(input.pairs) ? input.pairs : casePairs(data);
  const pairs = raw.map(p => Array.isArray(p) ? { base: p[0], variant: p[1] } : isObject(p) ? { base: p.base, variant: p.variant } : null)
    .filter((p): p is Pair => !!p && typeof p.base === "string" && typeof p.variant === "string" && p.base !== p.variant && scen.has(p.base) && scen.has(p.variant));
  const turns = (sc: TrialScenario) => Array.isArray(sc.followups) ? sc.followups.map(t => typeof t === "string" ? t : canon(t)) : [];
  const added: Added[] = [], other: Pair[] = [];
  for (const p of pairs) {
    const b = scen.get(p.base)!, v = scen.get(p.variant)!, bt = turns(b), vt = turns(v);
    const alike = b.prompt === v.prompt && canon(b.judge) === canon(v.judge) && canon(b.judge_role) === canon(v.judge_role) && canon(b.required) === canon(v.required) && canon(b.artifact) === canon(v.artifact);
    if (!alike || vt.length <= bt.length || !bt.every((t, i) => t === vt[i])) { other.push(p); continue; }
    const extra = vt.slice(bt.length), key = JSON.stringify(extra);
    let g = added.find(x => x.key === key);
    if (!g) { g = { key, turns: extra, pairs: [], anchor: ctx.uid(`setup-variant-${key.slice(0, 40)}`) }; added.push(g); }
    g.pairs.push(p);
  }
  return { added, other, count: pairs.length };
}

function variantSection(v: { added: Added[]; other: Pair[]; count: number }, ctx: RenderContext): string {
  if (!v.count) return "";
  const caseName = (id: string) => { const l = ctx.caseLabels[id]; return l && l !== id ? `${esc(l)} <code>${esc(id)}</code>` : `<code>${esc(id)}</code>`; };
  const pairList = (pairs: Pair[]) => `<ul class="av-setup-pairlist">${pairs.map(p => `<li><span>${caseName(p.base)}</span><span class="av-setup-arrow" aria-hidden="true">→</span>${sr(" becomes ")}<span>${caseName(p.variant)}</span></li>`).join("")}</ul>`;
  const many = v.added.length > 1;
  const items = v.added.map((g, i) => {
    const total = g.turns.reduce((n, t) => n + chars(t), 0);
    const name = `Added follow-up ${g.turns.length === 1 ? "turn" : "turns"}${many ? ` ${letterOf(i)}` : ""}`;
    const body = g.turns.map((t, k) => `${g.turns.length > 1 ? `<span class="av-eyebrow">${esc(`Added turn ${k + 1}`)}</span>` : ""}<pre class="av-pre av-setup-pre">${esc(t)}</pre>`).join("");
    return `<details class="av-setup-text"${total <= 1500 ? " open" : ""}><summary><span class="av-setup-letter av-setup-letter--big" aria-hidden="true">+${esc(g.turns.length)}</span><span class="av-setup-text-head"><span class="av-setup-text-name">${esc(name)}</span><span class="av-setup-text-meta">${esc(`${plural(g.turns.length, "follow-up turn")} · ${plural(total, "character")}`)}</span></span><span class="av-setup-users"><span class="av-setup-users-label">${esc(`added in ${plural(g.pairs.length, "variant")}`)}</span></span></summary><div class="av-setup-text-body" id="${esc(g.anchor)}"><p class="av-setup-textnote">${esc(`${g.pairs.length === 1 ? "The variant is its" : "Each variant is its"} base case with ${g.turns.length === 1 ? "this follow-up turn" : "these follow-up turns"} added; the prompt, judge and required checks are the same.`)}</p>${body}${pairList(g.pairs)}</div></details>`;
  }).join("");
  const other = v.other.length ? `<p class="av-setup-textnote">${esc(`${v.other.length === 1 ? "This pair was named as a variant but differs" : "These pairs were named as variants but differ"} from the base case in more than added turns:`)}</p>${pairList(v.other)}` : "";
  const n = v.added.reduce((k, g) => k + g.pairs.length, 0);
  const note = n ? `${plural(n, "case")} also ran as a variant with ${v.added.every(g => g.turns.length === 1) ? "one follow-up turn" : "follow-up turns"} added${many || n === 1 ? "" : `, the same ${v.added[0].turns.length === 1 ? "turn" : "turns"} in every variant`}` : `${plural(v.other.length, "named variant")}`;
  return `<div class="av-setup-materials av-setup-variants"><h4 class="av-setup-subhead"><span class="av-eyebrow">Case variants</span><span class="av-setup-subnote">${esc(note)}</span></h4><div class="av-setup-texts">${items}</div>${other}</div>`;
}

// ------------------------------------------------------------------ the view

export function setup(input: SetupInput, ctx: RenderContext): string {
  const data = ctx.trial;
  const explicit = isObject(input.settings) ? input.settings as Record<string, unknown> : undefined;
  if (!explicit && !data) throw new TypeError('A setup block needs trial data (the report spec\'s "trial" field, which trialReport() sets) or its own "settings".');
  const source: Record<string, unknown> = explicit || (isObject(data?.plan?.arms) ? data!.plan!.arms as Record<string, unknown> : {});
  const settings: Record<string, Settings | undefined> = {};
  for (const [k, v] of Object.entries(source)) settings[k] = isObject(v) ? v : undefined;

  // Which arms: the trial's arms that ran (or every explicit entry), narrowed to a requested subset.
  const pool = explicit ? Object.keys(source) : trialAxes(data!).arms;
  const known = new Set(pool);
  const asked = Array.isArray(input.arms) ? input.arms.filter((a): a is string => typeof a === "string") : null;
  const unknown = asked ? asked.filter(a => !known.has(a)) : [];
  const arms = (asked ? pool.filter(a => asked.includes(a)) : pool).slice().sort((x, y) => ctx.arms.index(x) - ctx.arms.index(y));
  const notRun = !explicit && !asked ? Object.keys(source).filter(a => !known.has(a)) : [];
  const footnotes = [
    ...(notRun.length ? [`Planned but never run: ${notRun.join(", ")}.`] : []),
    ...(unknown.length ? [`Not in this trial, so not shown: ${unknown.join(", ")}.`] : []),
  ];
  const foot = footnotes.length ? `<p class="av-setup-foot">${footnotes.map(esc).join(" ")}</p>` : "";
  if (!arms.length) return frame("setup", input, `${empty("No arm settings to show.")}${foot}`);

  const hide = new Set(Array.isArray(input.hide) ? input.hide.filter(h => typeof h === "string") : []);
  const materials = new Map<string, Map<string, Material | null>>(), lists = new Map<string, Material[]>();
  for (const kind of KINDS) { const { list, byArm } = collectMaterials(kind, arms, settings, ctx); materials.set(kind.digest, byArm); lists.set(kind.digest, list); }

  // Every setting any shown arm records, in reading order; a material counts when only its text is present.
  const keySet = new Set<string>();
  for (const a of arms) for (const [k, v] of Object.entries(settings[a] || {})) if (!NOT_SETTINGS.has(k) && present(v)) keySet.add(k);
  for (const kind of KINDS) if (lists.get(kind.digest)!.length) keySet.add(kind.digest);
  const keys = [...keySet].filter(k => !hide.has(k)).sort(byOrder);
  const compareValue = (a: string, k: string): string => {
    const kind = KINDS.find(x => x.digest === k);
    if (kind) return materials.get(k)!.get(a)?.key ?? "∅";
    return settings[a] ? canon(settings[a]![k]) : "∅ unrecorded";
  };
  // Differences among the arms whose settings are recorded; an arm without a plan entry is said so, not compared.
  const recorded = arms.filter(a => settings[a]), unrecorded = arms.filter(a => !settings[a]);
  const differs = recorded.length > 1 ? keys.filter(k => new Set(recorded.map(a => compareValue(a, k))).size > 1) : arms.length > 1 ? keys : [];
  const shared = keys.filter(k => !differs.includes(k));

  // Identical material: arms whose every recorded setting matches, and groups the author listed.
  const whole = (a: string) => settings[a] ? [...keySet].map(k => `${k}=${compareValue(a, k)}`).join("\n") : `∅ ${a}`;
  const listed = (Array.isArray(input.identical) ? input.identical : [])
    .filter(Array.isArray).map(g => g.filter((a): a is string => typeof a === "string" && arms.includes(a))).filter(g => g.length > 1);
  const chips = new Map<string, string>();
  const names = (ids: string[]) => ids.length <= 2 ? joinWords(ids.map(id => ctx.arms.label(id))) : `${ids.length} other arms`;
  for (const a of arms) {
    const group = listed.find(g => g.includes(a));
    const others = group ? group.filter(b => b !== a) : arms.filter(b => b !== a && whole(b) === whole(a));
    if (!others.length) continue;
    const apart = group ? keys.filter(k => others.some(b => compareValue(b, k) !== compareValue(a, k))) : [];
    chips.set(a, apart.length || (group && !settings[a])
      ? `<span class="av-setup-ident av-setup-ident--warn"><span class="av-chip av-chip--warn">listed as identical</span><span class="av-setup-ident-text">${esc(apart.length ? `but differs from ${names(others)} in ${joinWords(apart.map(k => lower(label(k))))}` : "but has no recorded settings to confirm it")}</span></span>`
      : `<span class="av-setup-ident" title="${esc(`Every recorded setting matches ${others.map(b => ctx.arms.label(b)).join(", ")}`)}"><span class="av-chip">identical material</span><span class="av-setup-ident-text">${esc(`with ${names(others)}`)}</span></span>`);
  }

  const baseline = typeof input.baseline === "string" && arms.includes(input.baseline) ? input.baseline
    : !input.baseline && typeof data?.baseline === "string" && arms.includes(data.baseline) ? data.baseline : undefined;
  const vcFor = (a: string): ValueCtx => ({ arm: a, settings: settings[a], materials });
  const armHead = (a: string) => `<div class="av-setup-armcell">${ctx.arms.tag(a)}${ctx.arms.note(a) ? `<span class="av-setup-note">${esc(ctx.arms.note(a)!)}</span>` : ""}${a === baseline || chips.has(a) || !settings[a] ? `<span class="av-setup-flags">${a === baseline ? '<span class="av-chip av-chip--base">baseline</span>' : ""}${!settings[a] ? '<span class="av-chip av-chip--warn">no recorded settings</span>' : ""}${chips.get(a) || ""}</span>` : ""}</div>`;

  // One sentence: how the arms differ.
  const phrase = (k: string) => {
    const kind = KINDS.find(x => x.digest === k), count = kind ? lists.get(k)!.length : 0;
    return `<strong>${esc(lower(label(k)))}</strong>${kind && count > 1 ? ` (${esc(`${count} distinct ${kind.noun === "Text" ? "texts" : "artifacts"}`)})` : ""}`;
  };
  const n = arms.length;
  const variants = data && !explicit ? variantsOf(data, input, ctx) : { added: [], other: [], count: 0 };
  const varied = variants.added.reduce((k, g) => k + g.pairs.length, 0);
  const r = recorded.length;
  const missingNote = unrecorded.length ? ` ${esc(unrecorded.length === 1 ? `${ctx.arms.label(unrecorded[0])} has` : `${fmtInt(unrecorded.length)} arms have`)} no recorded settings.` : "";
  const lede = !r
    ? `The plan records no settings for ${n === 1 ? "this arm" : "these arms"}, so this view cannot show what ${n === 1 ? "it" : "they"} received.`
    : n === 1
    ? varied
      ? `One arm ran, so no arms are compared: the comparison is between ${varied === 1 ? "one case and its variant, which adds" : `${esc(fmtInt(varied))} cases and their variants, which add`} ${variants.added.every(g => g.turns.length === 1) ? "a follow-up turn" : "follow-up turns"}.`
      : `One arm ran, so no arms are compared: each case’s runs are measured against that case’s own pass criteria.`
    : r === 1
      ? `Only one of the ${esc(fmtInt(n))} arms has recorded settings, so this view cannot show how they differ.${missingNote}`
      : !differs.length
        ? `${r === n ? `All ${esc(fmtInt(n))} arms` : `The ${esc(fmtInt(r))} arms with recorded settings`} received the same recorded settings and material, so any difference between their results is chance.${missingNote}`
        : `The ${esc(fmtInt(r))} arms${r === n ? "" : " with recorded settings"} differ ${shared.length ? "only " : ""}in ${joinWords(differs.map(phrase))}${shared.length ? "; every other recorded setting is the same" : ""}.${missingNote}`;
  // With several arms and case variants, the variants are a comparison of their own: it leads, and the arms are where it ran.
  const variantLede = n > 1 && varied
    ? `Each ${varied === 1 ? "case with a variant" : `of the ${esc(fmtInt(varied))} cases`} ran as written and with ${variants.added.every(g => g.turns.length === 1) ? "a follow-up turn" : "follow-up turns"} added (the case variants, first below), on every arm. `
    : "";

  // Whether the arms faced the same cases: a comparison across different cases is not like for like.
  let scope = "";
  if (data && !explicit && Array.isArray(data.runs)) {
    const runs = data.runs.filter(r => arms.includes(r.arm));
    const casesOf = new Map(arms.map(a => [a, new Set(runs.filter(r => r.arm === a).map(r => r.scenario))]));
    const all = new Set(runs.map(r => r.scenario));
    const cells = new Map<string, number>();
    for (const r of runs) cells.set(`${r.arm}\u0000${r.scenario}`, (cells.get(`${r.arm}\u0000${r.scenario}`) || 0) + 1);
    const per = [...cells.values()], lo = Math.min(...per), hi = Math.max(...per);
    const short = arms.filter(a => casesOf.get(a)!.size < all.size);
    // Repeats that differ only between arms are said per arm, plainly.
    const perArm = arms.map(a => { const v = runs.filter(x => x.arm === a).length ? [...cells.entries()].filter(([k]) => k.startsWith(`${a}\u0000`)).map(([, c]) => c) : [0]; return { a, lo: Math.min(...v), hi: Math.max(...v) }; });
    const byArm = lo !== hi && perArm.every(x => x.lo === x.hi);
    const versions = variants.count ? `${plural(all.size - variants.count, "case")}, as written and as variants (${fmtInt(all.size)} case versions)` : plural(all.size, "case");
    if (all.size && n > 1) scope = short.length
      ? `<p class="av-setup-scope av-setup-scope--warn">Not every arm ran every case: ${short.map(a => `${ctx.arms.tag(a, { id: false })} ${esc(`ran ${casesOf.get(a)!.size} of ${all.size}`)}`).join(", ")}. Compare arms within the cases they share.</p>`
      : `<p class="av-setup-scope">${esc(`Each arm ran the same ${versions}${byArm ? `: ${perArm.map(x => `${ctx.arms.label(x.a)} ${fmtInt(x.lo)} ${x.lo === 1 ? "run" : "runs"} of each`).join(", ")}.` : `, ${lo === hi ? fmtInt(lo) : `${fmtInt(lo)}–${fmtInt(hi)}`} ${hi === 1 ? "run" : "runs"} per case.`}`)}</p>`;
  }

  const sharedHtml = shared.length && r
    ? `<div class="av-setup-shared"><span class="av-eyebrow">${n === 1 ? "Settings" : r === n ? "Same for every arm" : "Same for every arm with recorded settings"}</span>${pairs(shared, vcFor(recorded[0]))}</div>`
    : "";
  const singleHead = n === 1 ? `<div class="av-setup-single">${armHead(arms[0])}</div>` : "";

  const table = n > 1 && differs.length
    ? `<div class="av-setup-differs"><span class="av-eyebrow">Differs between arms</span><div class="av-scroll-x av-setup-scroll"><table class="av-table av-setup-table" role="table"><thead><tr role="row"><th scope="col" role="columnheader">Arm</th>${differs.map(k => `<th scope="col" role="columnheader" title="${esc(`plan field: ${k}`)}">${esc(label(k))}</th>`).join("")}</tr></thead><tbody>${arms.map(a => `<tr role="row" data-arm="${esc(a)}"><th scope="row" role="rowheader">${armHead(a)}</th>${differs.map(k => `<td role="cell" data-label="${esc(label(k))}"><div class="av-setup-val">${valueHtml(k, vcFor(a))}</div></td>`).join("")}</tr>`).join("")}</tbody></table></div></div>`
    : n > 1 ? `<div class="av-setup-armlist">${arms.map(a => `<div class="av-setup-armline" data-arm="${esc(a)}">${armHead(a)}</div>`).join("")}</div>` : "";

  const judgeSettings = "judge" in input ? (isObject(input.judge) ? input.judge as Settings : undefined) : isObject(data?.plan?.judge) ? data!.plan!.judge as Settings : undefined;
  let judge = "";
  if (judgeSettings) {
    const jkeys = Object.keys(judgeSettings).filter(k => !NOT_SETTINGS.has(k) && !hide.has(k) && present(judgeSettings[k])).sort(byOrder);
    // A judge that is the same model as an arm it scores is worth knowing before trusting its verdicts.
    const jm = str(judgeSettings.model), same = jm ? arms.filter(a => str(settings[a]?.model) === jm) : [];
    const selfNote = same.length ? `<p class="av-setup-textnote av-setup-judge-same"><span class="av-chip av-chip--warn">same model</span> ${esc(`The judge is the same model as ${same.length === arms.length ? (arms.length === 1 ? "the arm" : "every arm") : joinWords(same.map(a => ctx.arms.label(a)))} it judges (${jm}).`)}</p>` : "";
    if (jkeys.length) judge = `<div class="av-setup-shared av-setup-judge"><span class="av-eyebrow">Judge</span>${pairs(jkeys, { arm: null, settings: judgeSettings, materials: new Map() })}${selfNote}</div>`;
  }

  const texts = KINDS.map(kind => materialSection(kind, lists.get(kind.digest)!, baseline, data?.run_directory, ctx, n)).join("");
  const variantHtml = variantSection(variants, ctx);
  const variantsFirst = n === 1 || !!varied;
  return frame("setup", input, `<p class="av-setup-lede">${variantLede}${lede}</p>${scope}${variantsFirst ? variantHtml : ""}${singleHead}${sharedHtml}${table}${judge}${texts}${variantsFirst ? "" : variantHtml}${foot}`);
}
