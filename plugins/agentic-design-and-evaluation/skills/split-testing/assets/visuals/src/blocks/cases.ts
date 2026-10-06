/** Case dossiers: one entry per case in plan order, saying what the case asked,
 * what counted as a pass and how every run went, with the reasons runs failed.
 * Variants of one case (the same prompt with an added turn, say) sit side by
 * side with the difference per arm. For a single-arm trial this is the main
 * result view, so it opens with the pass rate of every case. */
import { count, esc, fmtInt, fmtPct, inline, num, outcomeLabel, outcomeMark, prose, slug } from "../core";
import { failureCause, failureDetail, oneLine } from "../failure";
import type { RenderContext } from "../model";
import { newcombe } from "../stats";
import { outcomeOf, tally, Tally, TrialReport, TrialRun, TrialScenario, trialAxes } from "../trial-model";
import { empty, frame, FrameInput, pos } from "./frame";

export interface CaseGroup { label: string; cases: string[]; note?: string }
/** One explicit variant set: `[base, variant]`; `{base, variant | variants, label?, baseLabel?}`
 * where `variants` is a list or `{case: label}`; or `{suffix, label?, baseLabel?}`, which pairs
 * every case X with the case X+suffix when both exist. */
export type PairSpec =
  | [string, string]
  | { base: string; variant?: string; variants?: string[] | Record<string, string>; label?: string; baseLabel?: string }
  | { suffix: string; label?: string; baseLabel?: string };

export interface CasesInput extends FrameInput {
  /** Cases to show, in this order; defaults to the plan's order. */
  cases?: string[];
  /** Arms to show; defaults to every arm that ran, in identity order. */
  arms?: string[];
  /** Named sets of cases; each gets a heading unless a variant set crosses them, when their labels name the variants instead. */
  groups?: CaseGroup[];
  /** Variants side by side: "auto" (default) pairs cases with the same prompt where one name extends the other; "off"; or explicit sets. */
  pairs?: "auto" | "off" | PairSpec[];
  /** The pass-rate-by-case overview at the top; on by default when there are two or more entries. */
  index?: boolean;
}

/** A case and its variants: the base comes first. */
export interface VariantSet { base: string; members: Array<{ case: string; label?: string }>; source: "auto" | "explicit" }

const SEP = /^[-_.:+/~]/;
const str = (v: unknown): string => typeof v === "string" ? v : "";
const strs = (v: unknown): string[] => Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : [];
const plural = (n: number, one: string, many = `${one}s`) => `${fmtInt(n)} ${n === 1 ? one : many}`;
const signed = (n: number) => `${n > 0 ? "+" : n < 0 ? "−" : "±"}${fmtInt(Math.abs(n))}`;
/** Check names break at underscores instead of mid-word. */
const codeName = (name: string) => `<code>${esc(name).replace(/_/g, "_<wbr>")}</code>`;

function scenarioMap(data: TrialReport): Map<string, TrialScenario> {
  const m = new Map<string, TrialScenario>();
  for (const s of data.plan?.scenarios || []) if (s && typeof s.name === "string" && !m.has(s.name)) m.set(s.name, s);
  return m;
}

/** The anchor id the first cases block gives a case's dossier, for links from other views. */
export function caseAnchor(name: string): string { return slug(`case-${name}`); }

/** Variant sets among `cases`: explicit sets as given, or (auto) cases whose prompt is identical
 * and whose name extends another case's name after a separator, such as X and X-review2. */
export function caseVariants(data: TrialReport, cases: string[], pairs: CasesInput["pairs"] = "auto"): { sets: VariantSet[]; notes: string[] } {
  const scen = scenarioMap(data), known = new Set(cases), notes: string[] = [], sets: VariantSet[] = [];
  if (pairs === "off") return { sets, notes };
  if (Array.isArray(pairs)) {
    const used = new Set<string>();
    const add = (base: string, variants: Array<[string, string | undefined]>, baseLabel?: string) => {
      const missing = [base, ...variants.map(v => v[0])].filter(c => !known.has(c));
      if (missing.length) { notes.push(`A variant set names ${missing.length === 1 ? "a case" : "cases"} not shown here: ${missing.join(", ")}.`); return; }
      let set = sets.find(s => s.base === base);
      if (!set) {
        if (used.has(base)) { notes.push(`${base} already belongs to another variant set.`); return; }
        set = { base, members: [{ case: base, label: baseLabel }], source: "explicit" }; sets.push(set); used.add(base);
      } else if (baseLabel && !set.members[0].label) set.members[0].label = baseLabel;
      for (const [c, label] of variants) {
        if (used.has(c)) { notes.push(`${c} already belongs to another variant set.`); continue; }
        used.add(c); set.members.push({ case: c, label });
      }
    };
    pairs.forEach((p, i) => {
      if (Array.isArray(p) && p.length === 2 && typeof p[0] === "string" && typeof p[1] === "string") add(p[0], [[p[1], undefined]]);
      else if (p && typeof p === "object" && !Array.isArray(p) && typeof (p as { suffix?: unknown }).suffix === "string") {
        const { suffix, label, baseLabel } = p as { suffix: string; label?: string; baseLabel?: string };
        const found = suffix ? cases.filter(c => known.has(c + suffix)) : [];
        if (!found.length) notes.push(`No case has a variant ending in “${suffix}”.`);
        for (const c of found) add(c, [[c + suffix, str(label) || undefined]], str(baseLabel) || undefined);
      } else if (p && typeof p === "object" && !Array.isArray(p) && typeof (p as { base?: unknown }).base === "string") {
        const o = p as { base: string; variant?: unknown; variants?: unknown; label?: unknown; baseLabel?: unknown };
        const vs: Array<[string, string | undefined]> = [];
        if (typeof o.variant === "string") vs.push([o.variant, str(o.label) || undefined]);
        if (Array.isArray(o.variants)) for (const v of strs(o.variants)) vs.push([v, str(o.label) || undefined]);
        else if (o.variants && typeof o.variants === "object") for (const [v, l] of Object.entries(o.variants as Record<string, unknown>)) vs.push([v, str(l) || undefined]);
        if (vs.length) add(o.base, vs, str(o.baseLabel) || undefined); else notes.push(`Variant set ${i + 1} names no variant.`);
      } else notes.push(`Variant set ${i + 1} is not [base, variant], {base, variants} or {suffix}.`);
    });
    return { sets: sets.filter(s => s.members.length > 1), notes };
  }
  const prompt = (c: string) => str(scen.get(c)?.prompt).trim();
  const parent = new Map<string, string>();
  for (const b of cases) {
    let best: string | undefined;
    for (const a of cases) if (a !== b && b.length > a.length + 1 && b.startsWith(a) && SEP.test(b.slice(a.length)) && prompt(a) && prompt(a) === prompt(b) && (!best || a.length > best.length)) best = a;
    if (best) parent.set(b, best);
  }
  const root = (c: string) => { let r = c; for (let guard = 0; parent.has(r) && guard < 64; guard++) r = parent.get(r)!; return r; };
  const byRoot = new Map<string, string[]>();
  for (const c of cases) if (parent.has(c)) { const r = root(c); byRoot.set(r, [...(byRoot.get(r) || []), c]); }
  for (const c of cases) if (byRoot.has(c)) sets.push({ base: c, members: [{ case: c }, ...byRoot.get(c)!.map(v => ({ case: v }))], source: "auto" });
  return { sets, notes };
}

// ------------------------------------------------------------------ model

interface Judge { present: boolean; decides: boolean; question: string; passWhen: string; role: string }
function judgeOf(s?: TrialScenario): Judge {
  const j = s?.judge;
  const question = typeof j === "string" ? j : j && typeof j === "object" ? str((j as Record<string, unknown>).question) : "";
  const passWhen = j && typeof j === "object" ? str((j as Record<string, unknown>).pass_when) : "";
  const present = !!(question.trim() || passWhen.trim() || (j && typeof j === "object"));
  return { present, decides: present && s?.judge_required !== false, question, passWhen, role: str(s?.judge_role) };
}

interface Cell { arm: string; runs: TrialRun[]; t: Tally; failed: Map<string, number>; invalid: Map<string, number> }
interface Member {
  name: string; label: string; scenario?: TrialScenario; judge: Judge; required: string[];
  runs: TrialRun[]; cells: Cell[]; pooled: Tally; anchor: string;
}

/** Why a failed run failed, as keys: required checks that were not true, then the judge's verdict when it decides. */
function failedKeys(r: TrialRun, m: Pick<Member, "required" | "judge">): string[] {
  const out = m.required.filter(c => r.checks?.[c] !== true).map(c => `check:${c}`);
  if (m.judge.decides && r.judge?.verdict !== "pass") out.push(`judge:${str(r.judge?.verdict) || "no verdict"}`);
  return out;
}

/** The one-line cause from failure.ts, with a fallback built from the run itself. */
function causeText(r: TrialRun, m: Member): string {
  let text = "";
  try { text = str(failureCause(r, m.scenario)?.text).trim(); } catch { text = ""; }
  if (text) return text;
  if (r.passed === null) return str(r.invalid_reason) || str(r.status) || "invalid";
  const keys = failedKeys(r, m), checks = keys.filter(k => k.startsWith("check:")).map(k => k.slice(6)), judge = keys.find(k => k.startsWith("judge:"));
  const parts = [...(checks.length ? [`required check${checks.length === 1 ? "" : "s"} not met: ${checks.join(", ")}`] : []), ...(judge ? [`judge: ${judge.slice(6)}${r.judge?.reason ? ` — ${str(r.judge.reason)}` : ""}`] : [])];
  return parts.join("; ") || "no reason recorded";
}

function memberOf(data: TrialReport, ctx: RenderContext, scen: Map<string, TrialScenario>, name: string, arms: string[], label = ""): Member {
  const scenario = scen.get(name), judge = judgeOf(scenario), required = strs(scenario?.required);
  const runs = (Array.isArray(data.runs) ? data.runs : []).filter(r => r && r.scenario === name && arms.includes(r.arm)).sort((a, b) => (num(a.repeat) ?? 0) - (num(b.repeat) ?? 0));
  const base = { name, label, scenario, judge, required, runs, anchor: ctx.uid(`case-${name}`) };
  const cells = arms.map(arm => {
    const rs = runs.filter(r => r.arm === arm), failed = new Map<string, number>(), invalid = new Map<string, number>();
    for (const r of rs) {
      const o = outcomeOf(r);
      if (o === "fail") for (const k of failedKeys(r, base)) failed.set(k, (failed.get(k) || 0) + 1);
      if (o === "invalid") { const k = str(r.invalid_reason) || str(r.status) || "invalid"; invalid.set(k, (invalid.get(k) || 0) + 1); }
    }
    return { arm, runs: rs, t: tally(rs), failed, invalid };
  });
  return { ...base, cells, pooled: tally(runs) };
}

// ------------------------------------------------------------------ pieces

const caseLabel = (ctx: RenderContext, id: string) => ctx.caseLabels[id] || id;
const words = (t: string) => (t.match(/\S+/g) || []).length;
function cut(t: string, n: number): string {
  const flat = t.replace(/\s+/g, " ").trim();
  if (flat.length <= n) return flat;
  const at = flat.lastIndexOf(" ", n);
  let head = flat.slice(0, at > n * 0.6 ? at : n);
  // A cut inside `code` would leave its opening mark showing; end the preview before it.
  if ((head.match(/`/g) || []).length % 2) head = head.slice(0, head.lastIndexOf("`"));
  return head.replace(/[\s,;:.—-]+$/, "") + "…";
}

/** A piece of supplied text in a dossier column: whole when short, a preview when long. */
interface Piece { label?: string; text: string; kind: "verbatim" | "prose"; limit: number; wrap?: (inner: string) => string }
const norm = (t: string) => t.replace(/\r\n?/g, "\n").trim();
const isLong = (p: Piece) => { const t = norm(p.text); return t.length > p.limit || t.split("\n").reduce((n, l) => n + Math.max(1, Math.ceil(l.length / 92)), 0) > 6; };
/** A preview's length: about three lines of a dossier column. The preview is cut here,
 * at a word, and nowhere else (no line clamp), so it never ends mid-word. */
const PREVIEW = 230;
function piece(p: Piece, preview: boolean): string {
  const t = norm(p.text), short = cut(t, Math.min(PREVIEW, Math.round(p.limit * 0.72)));
  const inner = preview && isLong(p) ? `<p class="av-cs-preview">${p.kind === "prose" ? inline(short) : esc(short)}</p>`
    : p.kind === "verbatim" ? `<div class="av-cs-verbatim">${esc(t)}</div>` : prose(t, "av-cs-prose");
  return `${p.label ? `<p class="av-cs-label">${esc(p.label)}</p>` : ""}${p.wrap ? p.wrap(inner) : inner}`;
}
/** A column's texts with one disclosure for all of them: previews until opened,
 * then every text whole (CSS swaps the two), so a column costs one tab stop. */
function pieces(ps: Piece[], what: string, extra = ""): string {
  const list = ps.filter(p => norm(p.text));
  if (!list.some(isLong) && !extra) return list.map(p => piece(p, false)).join("");
  const n = list.reduce((k, p) => k + words(p.text), 0);
  return `<div class="av-cs-switch"><div class="av-cs-short">${list.map(p => piece(p, true)).join("")}</div><details class="av-cs-more"><summary><span class="av-cs-show">${esc(what)}${n ? ` · ${plural(n, "word")}` : ""}</span><span class="av-cs-hide">Show less</span></summary><div class="av-cs-full">${list.map(p => piece(p, false)).join("")}${extra}</div></details></div>`;
}

function track(color: string, t: Tally, label: string, mini = false): string {
  const p = t.rate, ci = t.interval;
  const style = `--c:${color};${p !== null ? `--p:${pos(p)};` : ""}${ci ? `--lo:${pos(ci[0])};--hi:${pos(ci[1])};` : ""}`;
  return `<div class="av-cs-track${mini ? " av-cs-track--mini" : ""}${p === null ? " av-cs-track--empty" : ""}" role="img" style="${style}" aria-label="${esc(label)}">${ci ? '<span class="av-ci"></span>' : ""}${p !== null ? '<span class="av-pt"></span>' : '<span class="av-cs-track-none">no valid runs</span>'}</div>`;
}

function figures(t: Tally, interval = true): string {
  const ci = t.interval;
  return `<span class="av-frac"><b>${count(t.pass)}</b>/${count(t.valid)}</span><span class="av-rate">${fmtPct(t.rate)}</span>${interval && ci ? `<span class="av-ci-text">${fmtPct(ci[0])}–${fmtPct(ci[1])}</span>` : ""}`;
}

function sayRate(t: Tally): string {
  const ci = t.interval;
  return `${t.valid ? `${count(t.pass)} of ${count(t.valid)} valid runs passed, ${fmtPct(t.rate)}` : "no valid runs"}${ci ? `, 95% interval ${fmtPct(ci[0])} to ${fmtPct(ci[1])}` : ""}${t.invalid ? `, ${count(t.invalid)} invalid` : ""}`;
}

const thin = (t: Tally) => t.valid > 0 && t.valid < 5 ? `<span class="av-chip av-chip--warn" title="Too few valid runs for a reliable rate">n = ${count(t.valid)}</span>` : "";
const invalidChip = (n: number, reasons?: Map<string, number>) => n
  ? `<span class="av-chip av-chip--invalid" title="${esc(`Invalid runs are excluded from the rate, never counted as failures${reasons && reasons.size ? `: ${[...reasons].map(([k, v]) => `${k} ×${v}`).join(", ")}` : ""}`)}">${outcomeMark("invalid")}${fmtInt(n)} invalid</span>` : "";

function marks(ctx: RenderContext, m: Member, runs: TrialRun[]): string {
  return runs.map(r => {
    const o = outcomeOf(r), why = o === "pass" ? "" : causeText(r, m);
    const label = `${caseLabel(ctx, m.name)} · ${ctx.arms.label(r.arm)} · repeat ${num(r.repeat) ?? "?"}: ${outcomeLabel[o]}${why ? ` · ${cut(why, 160)}` : ""}`;
    const i = ctx.runIndex.get(r);
    return `<button type="button" class="av-run av-run--${o}"${i === undefined ? "" : ` data-run="${count(i)}"`} title="${esc(label)}" aria-label="${esc(label)}"></button>`;
  }).join("");
}

/** Failed required checks and judge verdicts, with how many failed runs each explains. */
function whyChips(c: Cell, checks = true): string {
  const items = [...(checks ? c.failed : [])].sort((a, b) => b[1] - a[1]).map(([k, n]) => {
    const name = k.startsWith("check:") ? codeName(k.slice(6)) : `judge: ${esc(k.slice(6))}`;
    return `<span class="av-cs-why-chip" title="${esc(`${n} failed run${n === 1 ? "" : "s"} ${k.startsWith("check:") ? `had ${k.slice(6)} not true` : `had the judge verdict ${k.slice(6)}`}`)}"><span aria-hidden="true">✕</span> ${name}<b>${fmtInt(n)}</b></span>`;
  });
  return items.length || c.t.invalid ? `<div class="av-cs-why">${items.join("")}${invalidChip(c.t.invalid, c.invalid)}</div>` : "";
}

// ------------------------------------------------------------------ dossier parts

function criteriaLead(m: Member, planJudge: boolean): string {
  const n = m.required.length, j = m.judge;
  const checks = n ? n === 1 ? "its one required check held" : `all ${n} required checks held` : "";
  if (j.decides && !planJudge) return `${n ? `A run needed ${checks} and the judge to say pass. ` : ""}The case asks a judge question but the plan names no judge, so its runs could not be scored and count as invalid (judge-missing), not as failures.`;
  if (j.decides) return n ? `A run passed when ${checks} and the judge said pass.` : "A run passed when the judge said pass.";
  const recorded = j.present ? " The judge's verdict was recorded but did not decide the pass." : "";
  return n ? `A run passed when ${checks}.${recorded}` : `This case has no required checks${j.present ? " and its judge does not decide" : " and no judge"}: every run that finished counted as a pass.${j.present ? recorded : ""}`;
}

/** Required checks (and the judge) with how often each held over valid runs, one column per member. */
function criteriaTable(ms: Member[]): string {
  const names: string[] = [];
  for (const m of ms) for (const c of m.required) if (!names.includes(c)) names.push(c);
  const judged = ms.some(m => m.judge.decides);
  if (!names.length && !judged) return "";
  const multi = ms.length > 1;
  const cell = (held: number, valid: number, missing = 0) => {
    if (!valid) return `<td class="av-cs-crit-cell"><span class="av-missing">no valid runs</span></td>`;
    const all = held === valid;
    return `<td class="av-cs-crit-cell${all ? "" : " av-cs-crit-cell--short"}">${outcomeMark(all ? "pass" : "fail")}<span class="av-frac"><b>${fmtInt(held)}</b>/${fmtInt(valid)}</span>${missing ? `<span class="av-cs-crit-missing">${fmtInt(missing)} not recorded</span>` : ""}</td>`;
  };
  const rows = names.map(c => `<tr><th scope="row">${codeName(c)}</th>${ms.map(m => {
    if (!m.required.includes(c)) return `<td class="av-cs-crit-cell"><span class="av-muted">not required</span></td>`;
    const valid = m.runs.filter(r => r.passed !== null);
    return cell(valid.filter(r => r.checks?.[c] === true).length, valid.length, valid.filter(r => r.checks?.[c] === undefined || r.checks?.[c] === null).length);
  }).join("")}</tr>`);
  if (judged) rows.push(`<tr class="av-cs-crit-judge"><th scope="row">Judge says pass</th>${ms.map(m => {
    if (!m.judge.decides) return `<td class="av-cs-crit-cell"><span class="av-muted">${m.judge.present ? "does not decide" : "not judged"}</span></td>`;
    const valid = m.runs.filter(r => r.passed !== null);
    return cell(valid.filter(r => r.judge?.verdict === "pass").length, valid.length);
  }).join("")}</tr>`);
  const head = multi ? `<thead><tr><th scope="col">Must hold</th>${ms.map(m => `<th scope="col">${esc(m.label)}</th>`).join("")}</tr></thead>` : "";
  const key = ms.some(m => m.pooled.valid) ? `<p class="av-cs-crit-key">${outcomeMark("pass")}held in every valid run <span>${outcomeMark("fail")}did not always hold</span></p>` : "";
  return `<div class="av-scroll-x"><table class="av-cs-crit">${head}<tbody>${rows.join("")}</tbody></table></div>${key}`;
}

/** A pass criterion up to this many characters is shown whole: it is what decided the runs, so a preview would hide the clause that failed them. */
const PASS_WHOLE = 4000;
function judgeTexts(j: Judge): string {
  if (!j.present) return "";
  const whole = !!j.passWhen.trim() && norm(j.passWhen).length <= PASS_WHOLE;
  const ps: Piece[] = [
    ...(j.question.trim() ? [{ label: "The judge was asked", text: j.question, kind: "prose" as const, limit: 360 }] : []),
    ...(whole ? [] : [{ label: "It says pass when", text: j.passWhen, kind: "prose" as const, limit: 360 }]),
  ];
  const criterion = whole ? `<p class="av-cs-label">It says pass when</p>${prose(j.passWhen, "av-cs-prose")}` : "";
  const role = j.role.trim() ? `<p class="av-cs-label">How the judge was framed</p>${prose(j.role, "av-cs-prose av-cs-role")}` : "";
  const missing = j.passWhen.trim() ? "" : '<p class="av-cs-label">It says pass when</p><p><span class="av-missing">no pass criterion recorded</span></p>';
  const long = ps.some(p => norm(p.text) && isLong(p));
  const framing = role ? `<details class="av-cs-more av-cs-more--role"><summary><span class="av-cs-show">How the judge was framed</span><span class="av-cs-hide">Hide the framing</span></summary><div class="av-cs-full">${prose(j.role, "av-cs-prose av-cs-role")}</div></details>` : "";
  const what = [j.question.trim() ? "question" : "", whole ? "" : "criterion", role ? "framing" : ""].filter(Boolean).join(" and ");
  const body = long ? `${pieces(ps, `Read the judge's whole ${what}`, role)}${criterion}${missing}` : `${pieces(ps, "")}${criterion}${missing}${framing}`;
  return `<div class="av-cs-judge">${body}</div>`;
}

function taskHtml(m: Member, opts: { followups?: boolean } = {}): string {
  const s = m.scenario, prompt = str(s?.prompt), followups = opts.followups === false ? [] : strs(s?.followups), desc = str(s?.description);
  const cutNote = s?.description_truncated ? '<p class="av-cs-cutnote">The report carries the first 24,000 characters of this description.</p>' : "";
  const ps: Piece[] = [
    ...(desc.trim() ? [{ text: desc, kind: "prose" as const, limit: 360, wrap: (x: string) => `<div class="av-cs-desc">${x}${cutNote}</div>` }] : []),
    ...(prompt.trim() ? [{ label: "What the agent was asked", text: prompt, kind: "verbatim" as const, limit: 480, wrap: (x: string) => `<blockquote class="av-cs-prompt">${x}</blockquote>` }] : []),
    ...followups.map((f, i) => ({ label: `Then, follow-up ${i + 1}`, text: f, kind: "verbatim" as const, limit: 360, wrap: (x: string) => `<blockquote class="av-cs-prompt av-cs-prompt--followup">${x}</blockquote>` })),
  ];
  const what = `Read the whole ${[desc.trim() ? "description" : "", prompt.trim() ? "prompt" : "", followups.length ? (followups.length === 1 ? "follow-up" : "follow-ups") : ""].filter(Boolean).join(", ").replace(/, ([^,]*)$/, " and $1")}`;
  return `${desc.trim() ? "" : '<p class="av-cs-desc"><span class="av-missing">no description recorded</span></p>'}${pieces(ps, what)}${prompt.trim() ? "" : '<p class="av-cs-label">What the agent was asked</p><p><span class="av-missing">prompt not in this report</span></p>'}${s?.artifact ? `<p class="av-cs-artifact"><span class="av-cs-label">Judged output</span> ${codeName(String(s.artifact))}</p>` : ""}`;
}

function followupsHtml(m: Member): string {
  const f = strs(m.scenario?.followups);
  if (!f.length) return '<p class="av-cs-none">No follow-up.</p>';
  return pieces(f.map((t, i) => ({ label: `Follow-up ${i + 1}`, text: t, kind: "verbatim" as const, limit: 360, wrap: (x: string) => `<blockquote class="av-cs-prompt av-cs-prompt--followup">${x}</blockquote>` })), f.length === 1 ? "Read the whole follow-up" : "Read the whole follow-ups");
}

function reasons(ctx: RenderContext, m: Member): string {
  const failed = m.runs.filter(r => r.passed === false);
  const t = m.pooled;
  if (!m.runs.length) return `<p class="av-cs-state">${empty("No runs of this case are recorded.")}</p>`;
  if (!t.valid) return `<p class="av-cs-state">${outcomeMark("invalid")}No run of this case produced a valid result, so none passed or failed.</p>`;
  if (!failed.length) return `<p class="av-cs-state av-cs-state--pass">${outcomeMark("pass")}Every valid run passed.</p>`;
  // Runs that failed the same way (the same required checks, the judge) are one reason; a failure the data name no cause for keeps its own words.
  const groups = new Map<string, TrialRun[]>();
  for (const r of failed) { const keys = failedKeys(r, m), k = keys.length ? keys.join("|") : `text:${causeText(r, m)}`; groups.set(k, [...(groups.get(k) || []), r]); }
  const sorted = [...groups].sort((a, b) => b[1].length - a[1].length);
  // Each arm's glyph, in arm order, with how many of the reason's runs it holds.
  const armCounts = (runs: TrialRun[]) => m.cells.length > 1
    ? `<span class="av-cs-reason-arms">${m.cells.map(c => [c.arm, runs.filter(r => r.arm === c.arm).length] as const).filter(([, n]) => n).map(([a, n]) => `<span class="av-cs-reason-arm" title="${esc(`${ctx.arms.label(a)}: ${plural(n, "run")}`)}">${ctx.arms.glyph(a)}<b>${fmtInt(n)}</b></span>`).join("")}</span>` : "";
  const open = (r: TrialRun, what: string) => {
    const i = ctx.runIndex.get(r);
    return i === undefined ? "" : `<button type="button" class="av-cs-open" data-run="${count(i)}" aria-label="${esc(`Open the first run ${what}: ${ctx.arms.label(r.arm)}, repeat ${num(r.repeat) ?? "?"}`)}">open</button>`;
  };
  const item = ([key, runs]: [string, TrialRun[]]) => {
    // What varies between runs that failed the same way: the judge's words, or the recorded value behind a check.
    const detail = (r: TrialRun) => {
      if (key.startsWith("judge:")) return oneLine(r.judge?.reason) || "The judge gave no reason.";
      let d: { name: string; value: string } | null = null;
      try { d = failureDetail(r, m.scenario); } catch { d = null; }
      return d ? `\`${d.name}\` ${d.value}` : causeText(r, m);
    };
    const texts = new Map<string, TrialRun[]>();
    for (const r of runs) { const t = key.startsWith("text:") ? key.slice(5) : detail(r); texts.set(t, [...(texts.get(t) || []), r]); }
    const first = runs[0];
    if (texts.size <= 1) return `<li data-av-row><span class="av-cs-count">${fmtInt(runs.length)}×</span><span class="av-cs-reason-text">${inline(cut(causeText(first, m), 320))}</span>${armCounts(runs)}${open(first, "with this reason")}</li>`;
    const sub = [...texts].sort((a, b) => b[1].length - a[1].length).map(([t, rs]) => `<li data-av-row><span class="av-cs-count av-cs-count--sub">${fmtInt(rs.length)}×</span><span class="av-cs-reason-text">${inline(cut(t, 240))}</span>${open(rs[0], "with this detail")}</li>`).join("");
    return `<li class="av-cs-reason--group"><span class="av-cs-count">${fmtInt(runs.length)}×</span><span class="av-cs-reason-text av-cs-reason-head">${groupHead(key)}</span>${armCounts(runs)}<span></span><ul class="av-cs-reason-sub">${sub}</ul></li>`;
  };
  const shown = sorted.slice(0, 3), rest = sorted.slice(3, 15), hidden = sorted.length - shown.length - rest.length;
  return `<div class="av-cs-reasons"><p class="av-cs-label">Why runs failed${sorted.length > 1 ? ", most frequent first" : ""}</p><ol class="av-cs-reason-list">${shown.map(item).join("")}</ol>${rest.length ? `<details class="av-cs-more-reasons"><summary>${plural(rest.length + hidden, "more reason")}</summary><ol class="av-cs-reason-list">${rest.map(item).join("")}</ol>${hidden ? `<p class="av-muted">${plural(hidden, "further reason")} not listed; the run ledger has every run.</p>` : ""}</details>` : ""}</div>`;
}

/** A reason's heading from its keys: the required checks that did not hold, then the judge. */
function groupHead(key: string): string {
  const parts = key.split("|"), checks = parts.filter(k => k.startsWith("check:")).map(k => codeName(k.slice(6)));
  const verdict = parts.find(k => k.startsWith("judge:"))?.slice(6);
  const judge = verdict === undefined ? "" : verdict === "fail" ? "the judge said fail" : `the judge gave ${esc(verdict === "no verdict" ? "no verdict" : `“${verdict}”`)}, not pass`;
  const names = checks.length <= 1 ? checks.join("") : `${checks.slice(0, -1).join(", ")} and ${checks[checks.length - 1]}`;
  const head = checks.length ? `Required check${checks.length === 1 ? "" : "s"} ${names} did not hold${judge ? `; ${judge.replace(/^the judge/, "the judge also")}` : ""}` : judge;
  return head.charAt(0).toUpperCase() + head.slice(1);
}

function invalidLine(m: Member): string {
  const by = new Map<string, number>();
  for (const c of m.cells) for (const [k, v] of c.invalid) by.set(k, (by.get(k) || 0) + v);
  if (!m.pooled.invalid) return "";
  return `<p class="av-cs-invalid">${outcomeMark("invalid")}<span>${plural(m.pooled.invalid, "invalid run")}, excluded from the rate and not counted as failures: ${[...by].sort((a, b) => b[1] - a[1]).map(([k, v]) => `<code>${esc(k)}</code> ×${fmtInt(v)}`).join(", ")}</span></p>`;
}

function armRows(ctx: RenderContext, m: Member): string {
  const ran = m.cells.filter(c => c.runs.length);
  const rows = m.cells.map(c => {
    if (!c.runs.length) return ran.length ? `<div class="av-cs-arm av-cs-arm--none" role="row" data-arm="${esc(c.arm)}"><div class="av-cs-arm-tag" role="rowheader">${ctx.arms.tag(c.arm, { id: false })}</div><div class="av-cs-arm-none" role="cell">not run on this case</div></div>` : "";
    return `<div class="av-cs-arm" role="row" data-arm="${esc(c.arm)}" data-av-row><div class="av-cs-arm-tag" role="rowheader">${ctx.arms.tag(c.arm, { id: false })}</div><div class="av-cs-arm-track" role="cell">${track(ctx.arms.color(c.arm), c.t, `${ctx.arms.label(c.arm)}: ${sayRate(c.t)}`)}</div><div class="av-cs-num" role="cell">${figures(c.t)}${thin(c.t)}</div><div class="av-cs-marks" role="cell">${marks(ctx, m, c.runs)}</div>${whyChips(c, ran.length > 1) ? `<div class="av-cs-arm-why" role="cell">${whyChips(c, ran.length > 1)}</div>` : ""}</div>`;
  }).join("");
  // The rate axis, labelled once above the rows, so a bar reads without the figures beside it.
  const axis = ran.length ? `<div class="av-cs-arm av-cs-arm--axis" aria-hidden="true"><span></span><div class="av-cs-ix-ticks">${[0, .5, 1].map(t => `<span style="--x:${pos(t)}">${t * 100}%</span>`).join("")}</div></div>` : "";
  return `<div class="av-cs-arms" role="table" aria-label="${esc(`How ${caseLabel(ctx, m.name)} went, by arm`)}">${axis}${rows}</div>`;
}

function deltaHtml(b: Tally, v: Tally): string {
  if (!b.valid || !v.valid) return `<span class="av-cs-delta av-cs-delta--none">no difference measurable</span>`;
  const d = Math.round((v.pass / v.valid - b.pass / b.valid) * 100), iv = newcombe(v.pass, v.valid, b.pass, b.valid);
  const gained = v.pass - b.pass;
  const runs = b.valid === v.valid ? `${signed(gained)} ${Math.abs(gained) === 1 ? "pass" : "passes"} of ${fmtInt(v.valid)} · ` : "";
  const ci = iv ? `${signed(Math.round(iv[0] * 100))} to ${signed(Math.round(iv[1] * 100))} pts` : "";
  return `<span class="av-cs-delta" title="${esc(`Variant minus base: the difference in pass rate over valid runs${ci ? `, with a 95% Newcombe interval of ${ci}` : ""}. Not a significance test.`)}">${runs}${signed(d)} pts</span>${ci ? `<span class="av-cs-delta-ci">95% ${ci}</span>` : ""}`;
}

/** The members of a variant set side by side: one row per arm, a pooled row when several arms ran. */
function sideBySide(ctx: RenderContext, ms: Member[], arms: string[]): string {
  const multi = arms.length > 1;
  const head = `<div class="av-cs-vs-row av-cs-vs-row--head" role="row">${multi ? '<div class="av-cs-vs-corner" role="columnheader">Arm</div>' : ""}${ms.map((m, i) => `<div class="av-cs-vs-head" role="columnheader"${i ? ` id="${esc(m.anchor)}"` : ""} data-case="${esc(m.name)}"><span class="av-cs-vs-label">${esc(m.label)}</span>${caseLabel(ctx, m.name) !== m.name ? `<span class="av-cs-vs-name">${esc(caseLabel(ctx, m.name))}</span>` : `<code class="av-cs-vs-name">${esc(m.name)}</code>`}</div>`).join("")}</div>`;
  const cellHtml = (m: Member, c: Cell | undefined, base: Tally | undefined, t: Tally, armLabel: string, runs: boolean) => {
    const label = `<span class="av-cs-vs-inline">${esc(m.label)}</span>`;
    if (c && !c.runs.length) return `<div class="av-cs-vs-cell av-cs-vs-cell--none" role="cell">${label}<span class="av-cs-arm-none">not run</span></div>`;
    return `<div class="av-cs-vs-cell" role="cell" data-av-cell>${label}<div class="av-cs-num">${figures(t)}${thin(t)}${!runs ? invalidChip(t.invalid) : ""}</div>${track(c ? ctx.arms.color(c.arm) : "var(--av-ink-2)", t, `${armLabel}, ${m.label}: ${sayRate(t)}`, true)}${base ? `<div class="av-cs-vs-delta">${deltaHtml(base, t)}</div>` : ""}${runs && c ? `<div class="av-cs-marks">${marks(ctx, m, c.runs)}</div>${whyChips(c)}` : ""}</div>`;
  };
  const rows = arms.map((arm, ai) => {
    const cells = ms.map(m => m.cells[ai]);
    if (!cells.some(c => c.runs.length)) return "";
    return `<div class="av-cs-vs-row" role="row" data-arm="${esc(arm)}" data-av-row>${multi ? `<div class="av-cs-vs-arm" role="rowheader">${ctx.arms.tag(arm, { id: false })}</div>` : ""}${ms.map((m, i) => cellHtml(m, cells[i], i && cells[0].runs.length && cells[i].runs.length ? cells[0].t : undefined, cells[i].t, ctx.arms.label(arm), true)).join("")}</div>`;
  }).join("");
  const pooled = multi ? `<div class="av-cs-vs-row av-cs-vs-row--pooled" role="row"><div class="av-cs-vs-arm" role="rowheader"><span class="av-cs-pooled">All arms</span><span class="av-muted">pooled</span></div>${ms.map((m, i) => cellHtml(m, undefined, i ? ms[0].pooled : undefined, m.pooled, "All arms", false)).join("")}</div>` : "";
  return `<div class="av-scroll-x"><div class="av-cs-vs${multi ? "" : " av-cs-vs--solo"}" role="table" style="--m:${count(ms.length)}" aria-label="${esc(`${caseLabel(ctx, ms[0].name)} and its variants, side by side`)}">${head}${rows}${pooled}</div></div>`;
}

/** What the recorded fields say differs between a base case and each variant. */
function differences(ms: Member[]): string[] {
  const [b, ...vs] = ms, out: string[] = [];
  const bs = b.scenario;
  for (const v of vs) {
    const s = v.scenario, who = `<b>${esc(v.label)}</b>`, base = `<b>${esc(b.label)}</b>`;
    if (str(bs?.prompt).trim() !== str(s?.prompt).trim()) out.push(`The prompt differs in ${who}; both are shown below.`);
    const bf = strs(bs?.followups), vf = strs(s?.followups);
    for (let i = 0; i < Math.max(bf.length, vf.length); i++) {
      if (bf[i] === vf[i]) continue;
      // The task section below shows each follow-up's text; here it is named, not repeated.
      if (bf[i] === undefined) out.push(`Follow-up ${i + 1}, only in ${who}: its text is under The task.`);
      else if (vf[i] === undefined) out.push(`Follow-up ${i + 1}, only in ${base}: its text is under The task.`);
      else out.push(`Follow-up ${i + 1} differs between ${base} and ${who}; both are under The task.`);
    }
    const bj = judgeOf(bs), vj = judgeOf(s);
    if (bj.present !== vj.present) out.push(`Only ${bj.present ? base : who} is judged.`);
    else if (bj.present && (bj.question !== vj.question || bj.passWhen !== vj.passWhen || bj.decides !== vj.decides)) out.push(`The judge's question or pass criterion differs in ${who}.`);
    const br = strs(bs?.required), vr = strs(s?.required);
    const more = vr.filter(c => !br.includes(c)), fewer = br.filter(c => !vr.includes(c));
    if (more.length) out.push(`${who} also requires ${more.map(codeName).join(", ")}.`);
    if (fewer.length) out.push(`${who} does not require ${fewer.map(codeName).join(", ")}.`);
    if (str(bs?.artifact) !== str(s?.artifact)) out.push(`The judged output differs: ${bs?.artifact ? codeName(str(bs.artifact)) : "none"} against ${s?.artifact ? codeName(str(s.artifact)) : "none"}.`);
    if (str(bs?.description).trim() !== str(s?.description).trim()) out.push(`The description differs in ${who}.`);
  }
  return out;
}

/** A short name for what a variant changes, when the recorded fields show it. */
function variantLabel(base: TrialScenario | undefined, v: TrialScenario | undefined, baseName: string, name: string): string {
  const bf = strs(base?.followups), vf = strs(v?.followups);
  const same = str(base?.prompt).trim() === str(v?.prompt).trim() && JSON.stringify(base?.judge ?? null) === JSON.stringify(v?.judge ?? null) && JSON.stringify(strs(base?.required)) === JSON.stringify(strs(v?.required));
  if (same && vf.length > bf.length && bf.every((f, i) => vf[i] === f)) return vf.length - bf.length === 1 ? "+ follow-up" : `+ ${vf.length - bf.length} follow-ups`;
  if (same && vf.length < bf.length && vf.every((f, i) => bf[i] === f)) return bf.length - vf.length === 1 ? "− follow-up" : `− ${bf.length - vf.length} follow-ups`;
  const suffix = name.startsWith(baseName) ? name.slice(baseName.length).replace(/^[-_.:+/~]+/, "") : "";
  return suffix || name;
}

// ------------------------------------------------------------------ block

type Entry = { kind: "case"; m: Member } | { kind: "set"; set: VariantSet; ms: Member[] };

export function cases(input: CasesInput, ctx: RenderContext): string {
  if (!ctx.trial) throw new TypeError('A cases block needs trial data: supply the report spec\'s "trial" field (trialReport() does).');
  const data = ctx.trial, scen = scenarioMap(data), axes = trialAxes(data);
  const notes: string[] = [];
  const knownArms = new Set([...axes.arms, ...Object.keys(data.plan?.arms || {})]);
  let arms = Array.isArray(input.arms) ? strs(input.arms).filter(a => knownArms.has(a)) : axes.arms;
  if (Array.isArray(input.arms) && arms.length < input.arms.length) notes.push(`Arms not in this trial were left out: ${strs(input.arms).filter(a => !knownArms.has(a)).join(", ") || "entries that are not text"}.`);
  arms = [...new Set(arms)].sort((a, b) => ctx.arms.index(a) - ctx.arms.index(b));
  const all = [...scen.keys(), ...axes.cases.filter(c => !scen.has(c))];
  const names = Array.isArray(input.cases) ? [...new Set(strs(input.cases))].filter(c => all.includes(c)) : all;
  if (Array.isArray(input.cases) && names.length < input.cases.length) notes.push(`Cases not in this trial were left out: ${strs(input.cases).filter(c => !all.includes(c)).join(", ") || "entries that are not text"}.`);
  if (!names.length) return frame("cases", input, empty("No cases to show."));

  const pairs = input.pairs === "off" || Array.isArray(input.pairs) ? input.pairs : "auto";
  const found = caseVariants(data, names, pairs);
  notes.push(...found.notes);
  const groups = (Array.isArray(input.groups) ? input.groups : []).filter(g => g && Array.isArray(g.cases)).map(g => ({ label: str(g.label), note: str(g.note), cases: strs(g.cases).filter(c => names.includes(c)) })).filter(g => g.cases.length);
  const groupOf = (c: string) => groups.findIndex(g => g.cases.includes(c));
  const crossing = found.sets.some(s => new Set(s.members.map(m => groupOf(m.case))).size > 1);

  const inSet = new Map<string, VariantSet>();
  for (const s of found.sets) for (const m of s.members) inSet.set(m.case, s);
  const entries: Entry[] = [];
  for (const c of names) {
    const s = inSet.get(c);
    if (!s) { entries.push({ kind: "case", m: memberOf(data, ctx, scen, c, arms, caseLabel(ctx, c)) }); continue; }
    if (s.base !== c) continue;
    const ms = s.members.map((mm, i) => {
      const fromGroup = crossing && groupOf(mm.case) >= 0 ? groups[groupOf(mm.case)].label : "";
      const label = mm.label || fromGroup || (i ? variantLabel(scen.get(s.base), scen.get(mm.case), s.base, mm.case) : "Base");
      return memberOf(data, ctx, scen, mm.case, arms, label);
    });
    entries.push({ kind: "set", set: s, ms });
  }

  const planJudge = !!data.plan?.judge;
  const single = arms.length === 1;
  const dossier = (e: Entry, n: number) => {
    const ms = e.kind === "case" ? [e.m] : e.ms, head = ms[0];
    const number = String(n).padStart(2, "0");
    const label = caseLabel(ctx, head.name);
    const chips = [
      ...(head.required.length ? [`<span class="av-chip av-chip--req">${plural(head.required.length, "required check")}</span>`] : []),
      ...(head.judge.present ? [`<span class="av-chip">${head.judge.decides ? "judged" : "judge recorded"}</span>`] : []),
      ...(e.kind === "case" && strs(head.scenario?.followups).length ? [`<span class="av-chip">${plural(strs(head.scenario?.followups).length, "follow-up")}</span>`] : []),
      ...(e.kind === "set" ? [`<span class="av-chip av-chip--variant">${e.ms.length === 2 ? "variant pair" : `${e.ms.length - 1} variants`}</span>`] : []),
    ].join("");
    const result = e.kind === "set"
      ? `<div class="av-cs-result av-cs-result--set">${e.ms.map(m => `<span class="av-cs-mres"><span class="av-cs-mres-label">${esc(m.label)}</span><span class="av-frac"><b>${count(m.pooled.pass)}</b>/${count(m.pooled.valid)}</span>${m.pooled.invalid ? `<span class="av-cs-mres-inv">${outcomeMark("invalid")}${fmtInt(m.pooled.invalid)}</span>` : ""}</span>`).join("")}${single ? "" : '<span class="av-muted">all arms</span>'}</div>`
      : single
        ? `<div class="av-cs-result"><span class="av-cs-big"><b>${count(head.pooled.pass)}</b>/${count(head.pooled.valid)}</span><span class="av-cs-result-sub">${head.pooled.valid ? `${fmtPct(head.pooled.rate)} passed` : "no valid runs"}${head.pooled.interval ? ` · ${fmtPct(head.pooled.interval[0])}–${fmtPct(head.pooled.interval[1])}` : ""}</span>${invalidChip(head.pooled.invalid)}</div>`
        : `<ul class="av-cs-result av-cs-result--arms" aria-label="Passed of valid runs, by arm">${head.cells.filter(c => c.runs.length).map(c => `<li title="${esc(`${ctx.arms.label(c.arm)}: ${sayRate(c.t)}`)}" data-arm="${esc(c.arm)}">${ctx.arms.glyph(c.arm)}<span class="av-cs-sr">${esc(ctx.arms.label(c.arm))}</span><span class="av-frac"><b>${count(c.t.pass)}</b>/${count(c.t.valid)}</span>${c.t.invalid ? `<span class="av-cs-mres-inv" aria-label="${esc(`${c.t.invalid} invalid`)}">${outcomeMark("invalid")}${fmtInt(c.t.invalid)}</span>` : ""}</li>`).join("")}</ul>`;
    const header = `<header class="av-cs-head"><span class="av-cs-n" aria-hidden="true">${number}</span><div class="av-cs-titles"><h4 class="av-cs-title" id="${esc(head.anchor)}-h">${esc(label)}</h4><p class="av-cs-sub">${e.kind === "set" ? e.ms.map(m => `<code>${esc(m.name)}</code>`).join('<span class="av-muted"> and </span>') : label !== head.name ? `<code>${esc(head.name)}</code>` : ""}${chips}</p></div>${result}</header>`;
    if (e.kind === "case") {
      const m = e.m;
      return `<article class="av-cs" id="${esc(m.anchor)}" data-case="${esc(m.name)}" aria-labelledby="${esc(m.anchor)}-h" data-av-roving>${header}<div class="av-cs-body"><div class="av-cs-task"><p class="av-cs-eyebrow">The task</p>${taskHtml(m)}</div><div class="av-cs-pass"><p class="av-cs-eyebrow">What counted as a pass</p><p class="av-cs-lead">${esc(criteriaLead(m, planJudge))}</p>${criteriaTable([m])}${judgeTexts(m.judge)}</div></div><div class="av-cs-went"><p class="av-cs-eyebrow">How it went</p>${armRows(ctx, m)}${reasons(ctx, m)}${invalidLine(m)}</div></article>`;
    }
    const msx = e.ms, diff = differences(msx);
    const sameText = (f: (m: Member) => unknown) => msx.every(m => JSON.stringify(f(m)) === JSON.stringify(f(msx[0])));
    const sharedTask = sameText(m => [str(m.scenario?.prompt).trim(), strs(m.scenario?.followups), str(m.scenario?.description).trim(), str(m.scenario?.artifact)]);
    const sharedDesc = sameText(m => str(m.scenario?.description).trim());
    const sharedPrompt = sameText(m => str(m.scenario?.prompt).trim());
    const sharedJudge = sameText(m => [m.judge.question, m.judge.passWhen, m.judge.role, m.judge.decides]);
    const sharedLead = sameText(m => criteriaLead(m, planJudge));
    const cols = (f: (m: Member) => string) => `<div class="av-cs-cols">${msx.map(m => `<div class="av-cs-col"><p class="av-cs-col-label">${esc(m.label)}</p>${f(m)}</div>`).join("")}</div>`;
    const task = sharedTask ? taskHtml(msx[0])
      : sharedDesc && sharedPrompt
        ? `${taskHtml(msx[0], { followups: false })}${cols(followupsHtml)}`
        : cols(m => taskHtml(m));
    const why = `<div class="av-cs-diff"><p class="av-cs-eyebrow">What differs</p>${diff.length ? `<ul>${diff.map(d => `<li>${d}</li>`).join("")}</ul>` : "<p>The report records no difference in prompt, follow-ups, judge, required checks or judged output; the cases may differ in files the report does not carry, such as fixtures, setup or checks.</p>"}${e.set.source === "auto" ? '<p class="av-cs-diff-why">Shown together because they have the same prompt and one name extends the other.</p>' : ""}</div>`;
    const lead = sharedLead ? `<p class="av-cs-lead">${esc(criteriaLead(msx[0], planJudge))}</p>` : cols(m => `<p class="av-cs-lead">${esc(criteriaLead(m, planJudge))}</p>`);
    const judges = sharedJudge ? judgeTexts(msx[0].judge) : cols(m => judgeTexts(m.judge) || '<p class="av-cs-none">Not judged.</p>');
    const went = `${sideBySide(ctx, msx, arms)}${msx.some(m => m.runs.some(r => r.passed === false)) || msx.some(m => m.pooled.invalid) ? cols(m => `${reasons(ctx, m)}${invalidLine(m)}`) : `<p class="av-cs-state av-cs-state--pass">${outcomeMark("pass")}Every valid run of ${msx.length === 2 ? "both versions" : `all ${msx.length} versions`} passed.</p>`}`;
    return `<article class="av-cs av-cs--set" id="${esc(head.anchor)}" data-case="${esc(head.name)}" aria-labelledby="${esc(head.anchor)}-h" data-av-roving>${header}${why}<div class="av-cs-body"><div class="av-cs-task"><p class="av-cs-eyebrow">The task</p>${task}</div><div class="av-cs-pass"><p class="av-cs-eyebrow">What counted as a pass</p>${lead}${criteriaTable(msx)}${judges}</div></div><div class="av-cs-went"><p class="av-cs-eyebrow">How it went, side by side</p>${went}</div></article>`;
  };

  // The overview: one row per case (variants indented under their base). In the
  // multi-arm dot plot, marks that would touch (rates within NEAR of each other) are
  // stacked one glyph's height apart, in arm order, and the row grows to hold them.
  const NEAR = 0.035, STEP = 14;
  const lanes = (cells: Cell[]): Map<string, number> => {
    const out = new Map<string, number>(), sorted = cells.slice().sort((a, b) => (a.t.rate ?? 0) - (b.t.rate ?? 0) || arms.indexOf(a.arm) - arms.indexOf(b.arm));
    for (let i = 0; i < sorted.length;) {
      let j = i + 1;
      while (j < sorted.length && (sorted[j].t.rate ?? 0) - (sorted[j - 1].t.rate ?? 0) < NEAR) j++;
      const group = sorted.slice(i, j).sort((a, b) => arms.indexOf(a.arm) - arms.indexOf(b.arm));
      group.forEach((c, k) => out.set(c.arm, k - (group.length - 1) / 2));
      i = j;
    }
    return out;
  };
  const indexRows = (e: Entry, n: number) => {
    const ms = e.kind === "case" ? [e.m] : e.ms;
    return ms.map((m, i) => {
      const variant = i > 0, name = variant ? m.label : caseLabel(ctx, m.name);
      const lead = `<div class="av-cs-ix-label" role="rowheader">${variant ? '<span class="av-cs-ix-n" aria-hidden="true">↳</span>' : `<span class="av-cs-ix-n">${String(n).padStart(2, "0")}</span>`}<a href="#${esc(variant ? m.anchor : ms[0].anchor)}">${esc(name)}</a>${!variant && e.kind === "set" ? `<span class="av-cs-ix-tag">${esc(m.label)}</span>` : ""}</div>`;
      if (single) {
        const c = m.cells[0];
        return `<div class="av-cs-ix-row${variant ? " av-cs-ix-row--variant" : ""}" role="row">${lead}<div class="av-cs-ix-track" role="cell">${track(ctx.arms.color(c.arm), c.t, `${name}: ${sayRate(c.t)}`)}</div><div class="av-cs-ix-num" role="cell">${figures(c.t)}${thin(c.t)}${invalidChip(c.t.invalid, c.invalid)}${variant && ms[0].cells[0].t.valid ? `<span class="av-cs-ix-delta">${deltaHtml(ms[0].cells[0].t, c.t)}</span>` : ""}</div></div>`;
      }
      const placed = m.cells.filter(c => c.t.valid), lane = lanes(placed);
      const deepest = Math.max(0, ...[...lane.values()].map(Math.abs));
      const dots = placed.map(c => `<span class="av-cs-dot" style="--x:${pos(c.t.rate ?? 0)};--j:${(lane.get(c.arm) ?? 0).toFixed(1)};--gap:${STEP}px" title="${esc(`${ctx.arms.label(c.arm)}: ${sayRate(c.t)}`)}">${ctx.arms.glyph(c.arm)}</span>`).join("");
      const say = m.cells.filter(c => c.runs.length).map(c => `${ctx.arms.label(c.arm)} ${sayRate(c.t)}`).join("; ") || "not run";
      const none = m.cells.filter(c => c.runs.length && !c.t.valid).length;
      const numbers = m.pooled.valid
        ? `${figures(m.pooled, false)}<span class="av-muted">all arms</span>${none ? `<span class="av-chip av-chip--invalid">${plural(none, "arm")} without a valid run</span>` : ""}`
        : `<span class="av-missing">${m.runs.length ? "no valid runs" : "not run"}</span>`;
      return `<div class="av-cs-ix-row${variant ? " av-cs-ix-row--variant" : ""}" role="row">${lead}<div class="av-cs-ix-track" role="cell"><div class="av-cs-dots${placed.length ? "" : " av-cs-track--empty"}" role="img"${deepest ? ` style="height:${Math.round(26 + deepest * 2 * STEP)}px"` : ""} aria-label="${esc(say)}">${dots || '<span class="av-cs-track-none">no valid runs</span>'}</div></div><div class="av-cs-ix-num" role="cell">${numbers}${invalidChip(m.pooled.invalid)}</div></div>`;
    }).join("");
  };

  // Sections by group, unless a variant set crosses groups (the labels then name the variants).
  const blocks: Array<{ group?: { label: string; note: string; cases: string[] }; items: Array<[Entry, number]> }> = [];
  let n = 0;
  if (groups.length && !crossing) {
    const placed = new Set<Entry>();
    for (const g of [...groups, { label: "Other cases", note: "", cases: names.filter(c => groupOf(c) < 0) }]) {
      const items = entries.filter(e => !placed.has(e) && g.cases.includes(e.kind === "case" ? e.m.name : e.set.base));
      items.forEach(e => placed.add(e));
      if (items.length) blocks.push({ group: g, items: items.map(e => [e, ++n] as [Entry, number]) });
    }
  } else blocks.push({ items: entries.map(e => [e, ++n] as [Entry, number]) });

  const showIndex = input.index ?? entries.length + entries.reduce((k, e) => k + (e.kind === "set" ? e.ms.length - 1 : 0), 0) > 1;
  const ticks = [0, .25, .5, .75, 1].map(t => `<span style="--x:${pos(t)}">${t * 100}%</span>`).join("");
  const index = showIndex ? `<nav class="av-cs-index" aria-label="${single ? "Pass rate by case" : "Cases at a glance"}"><p class="av-cs-eyebrow">${single ? "Pass rate by case" : "Cases at a glance"}</p><p class="av-cs-index-desc">${single ? `One arm ran (${esc(ctx.arms.label(arms[0]))}); each case pools its repeats. Select a case for its dossier.` : "Each arm's pass rate on each case, placed by its shape and color; the figures on the right pool every arm. Select a case for its dossier."}</p>${single ? "" : `<p class="av-cs-index-arms">${arms.map(a => ctx.arms.tag(a, { id: false })).join("")}</p>`}<div class="av-cs-ix" role="table" aria-label="${single ? "Pass rate by case" : "Pass rate by case and arm"}"><div class="av-cs-ix-axis" role="row" aria-hidden="true"><span></span><div class="av-cs-ix-ticks">${ticks}</div><span></span></div>${blocks.map(b => `${b.group ? `<div class="av-cs-ix-group" role="row"><span role="rowheader">${esc(b.group.label)}</span></div>` : ""}${b.items.map(([e, k]) => indexRows(e, k)).join("")}`).join("")}</div></nav>` : "";

  const body = blocks.map(b => {
    const head = b.group ? (() => {
      const cs = b.items.flatMap(([e]) => e.kind === "case" ? [e.m] : e.ms), t = tally(cs.flatMap(m => m.runs));
      return `<div class="av-cs-group"><h4 class="av-cs-group-label">${esc(b.group.label)}</h4><span class="av-muted">${plural(cs.length, "case")} · ${count(t.pass)}/${count(t.valid)} passed${t.invalid ? ` · ${fmtInt(t.invalid)} invalid` : ""}${b.group.note ? ` · ${esc(b.group.note)}` : ""}</span></div>`;
    })() : "";
    return head + b.items.map(([e, k]) => dossier(e, k)).join("");
  }).join("");

  const legend = `<p class="av-legend">${(["pass", "fail", "invalid"] as const).map(o => `<span>${outcomeMark(o)}${o === "invalid" ? "invalid — excluded, not a failure" : outcomeLabel[o].toLowerCase()}</span>`).join("")}<span><span class="av-legend-ci"></span>95% Wilson interval over valid runs</span><span class="av-legend-hint">Each mark is one run; select it for its record.</span></p>`;
  const notice = notes.length ? `<div class="av-cs-notice" role="note">${notes.map(t => `<p>${esc(t)}</p>`).join("")}</div>` : "";
  // The section lead introduces the view; the block adds only what it changes.
  const description = input.description ?? (found.sets.length ? "Variants of one case share a panel and sit side by side. Each difference is the variant minus its base case: passes gained or lost, of the runs each side had (“+2 passes of 3”), then percentage points with a 95% interval." : undefined);
  return frame("cases", { ...input, description }, `${legend}${notice}${index}<div class="av-cs-list">${body}</div>`);
}

