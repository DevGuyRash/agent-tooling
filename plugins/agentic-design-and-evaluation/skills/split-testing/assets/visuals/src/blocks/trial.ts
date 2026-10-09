/** Views of a trial: the verdict and its rule, pass-rate intervals by arm or by
 * case with identical-arm noise, every run by case and arm, checks by case,
 * pairwise preferences, cost, invalid runs, the run ledger and the plan. Each
 * reads the trial in the render context and accepts explicit data where a
 * caller has its own. */
import { attrs, axisTicks, count, esc, fmtDelta, fmtInt, fmtNum, fmtPct, fmtSeconds, fmtUsd, inline, isNum, logTicks, median, num, Outcome, secondsUnit, outcomeBadge, outcomeLabel, outcomeMark, prose, quantile, wilson } from "../core";
import type { RenderContext } from "../model";
import { failureCause } from "../failure";
import { CasePair, caseChecks, checkTable, costMeasures, displayPath, invalidReason, judgePassWhen, judgeQuestion, outcomeOf, pairedOrder, scenarioOf, tally, TrialReport, TrialRun, trialAxes } from "../trial-model";
import { empty, frame, FrameInput, pos } from "./frame";

const caseLabel = (ctx: RenderContext, id: string) => ctx.caseLabels[id] || id;
function trialOf(ctx: RenderContext, block: string): TrialReport {
  if (!ctx.trial) throw new TypeError(`A ${block} block needs trial data: supply the report spec's "trial" field (trialReport() does).`);
  return ctx.trial;
}
const strings = (v: unknown): string[] | undefined => Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : undefined;
const plural = (n: number, one: string, many = `${one}s`) => `${fmtInt(n)} ${n === 1 ? one : many}`;
const clip = (text: string, max: number) => text.length > max ? `${text.slice(0, max - 1).trimEnd()}…` : text;
const byIdentity = (ctx: RenderContext) => (a: string, b: string) => ctx.arms.index(a) - ctx.arms.index(b);

/** Case variants from a block's input; anything malformed is dropped. */
function pairsOf(raw: unknown): CasePair[] {
  if (!Array.isArray(raw)) return [];
  return raw.filter(p => p && typeof p === "object" && typeof p.base === "string" && typeof p.variant === "string")
    .map(p => ({ base: p.base, variant: p.variant, label: typeof p.label === "string" && p.label ? p.label : "variant", note: typeof p.note === "string" ? p.note : undefined }));
}

/** Why a run did not pass, read once through failureCause() so every view says the same thing. */
interface Cause { checks: string[]; judge: string | null; text: string; invalid: string | null }
function causeOf(run: TrialRun, data: TrialReport): Cause {
  const o = outcomeOf(run);
  if (o === "pass") return { checks: [], judge: null, text: "", invalid: null };
  if (o === "invalid") return { checks: [], judge: null, text: "", invalid: String(run.invalid_reason || run.status || "invalid") };
  let c: { kind?: unknown; text?: unknown; failedChecks?: unknown } = {};
  try { c = failureCause(run, scenarioOf(data, run.scenario)) || {}; } catch { c = {}; }
  const checks = strings(c.failedChecks) || [];
  const text = typeof c.text === "string" ? c.text : "";
  const judge = c.kind === "judge" || run.judge?.verdict === "fail" ? String(run.judge?.reason || "") : null;
  return { checks, judge, text, invalid: null };
}
/** The same cause as one short phrase for a mark's label. */
function causePhrase(run: TrialRun, data: TrialReport): string {
  const c = causeOf(run, data);
  if (c.invalid) return c.invalid;
  const parts = [...c.checks.slice(0, 3), ...(c.checks.length > 3 ? [`${c.checks.length - 3} more checks`] : [])];
  if (c.judge !== null) parts.push(c.judge ? `judge: ${clip(c.judge, 100)}` : "judge said fail");
  if (!parts.length && c.text) parts.push(clip(c.text, 120));
  return parts.join(", ");
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
  /** The rule's terms, each with what was observed. A check with a group (such as "Other candidates against the same bar")
   * is listed under that subheading, apart from the ungrouped terms that decide the verdict. */
  checks?: Array<{ label: string; observed: string; threshold?: string; met?: boolean | null; group?: string }>;
  conditions?: string[];
  limits?: string[];
  changes?: string[];
  /** Case or arm ids the rule names: each is listed with its counts from the trial, and nothing is marked met or unmet. */
  mentions?: string[];
  /** Case variants, so a named case also shows its variant's counts. */
  pairs?: CasePair[];
  /** A notice under the headline, such as that most runs produced no valid result; href is a section anchor such as "#invalid". */
  alert?: { text: string; href?: string; link?: string };
}
const verdictWords = { adopt: "Adopt", reject: "Do not adopt", inconclusive: "Inconclusive", mixed: "Mixed", none: "No decision recorded" };
const verdictIcons = { adopt: "✓", reject: "✕", inconclusive: "?", mixed: "±", none: "–" };
type VerdictKind = keyof typeof verdictWords;

function mentionsHtml(ids: string[], pairs: CasePair[], ctx: RenderContext): string {
  const data = ctx.trial;
  if (!data || !ids.length) return "";
  const axes = trialAxes(data), arms = axes.arms.slice().sort(byIdentity(ctx));
  const frac = (runs: TrialRun[]) => {
    const t = tally(runs);
    return `<span class="av-frac"><b>${t.pass}</b>/${t.valid}</span>${t.invalid ? `<span class="av-mention-inv" title="${plural(t.invalid, "invalid run")}, not counted">${outcomeMark("invalid")}${t.invalid}</span>` : ""}`;
  };
  const counts = (cs: string | string[]) => {
    const set = new Set(Array.isArray(cs) ? cs : [cs]), runs = data.runs.filter(r => set.has(r.scenario));
    if (arms.length < 2) return `<span class="av-mention-counts">${frac(runs)}</span>`;
    return `<span class="av-mention-counts">${arms.filter(a => runs.some(r => r.arm === a)).map(a => `<span class="av-mention-arm" title="${esc(ctx.arms.label(a))}">${ctx.arms.glyph(a)}${frac(runs.filter(r => r.arm === a))}</span>`).join("")}<span class="av-mention-all">all ${frac(runs)}</span></span>`;
  };
  const items = ids.map(id => {
    if (axes.cases.includes(id)) {
      const label = caseLabel(ctx, id);
      const variants = pairs.filter(p => p.base === id && axes.cases.includes(p.variant) && !ids.includes(p.variant));
      return `<li class="av-mention"${attrs({ "data-case": id })}><span class="av-mention-name">${esc(label)}${label !== id ? ` <code>${esc(id)}</code>` : ""}</span>${counts(id)}${variants.map(p => `<span class="av-mention-variant"><span class="av-mention-vlabel"${attrs({ title: p.variant })}>↳ ${esc(p.label)}</span>${counts(p.variant)}</span>`).join("")}</li>`;
    }
    if (axes.arms.includes(id) && arms.length > 1) return `<li class="av-mention av-mention--arm"><span class="av-mention-name">${ctx.arms.tag(id)}</span><span class="av-mention-counts">${frac(data.runs.filter(r => r.arm === id))}</span></li>`;
    return "";
  }).join("");
  if (!items) return "";
  // A rule that names some cases often counts the rest together ("design passes of 56"):
  // the cases it does not name are pooled into one entry, base cases and variants apart.
  const named = ids.filter(id => axes.cases.includes(id)), isVariant = new Set(pairs.map(p => p.variant));
  const covered = new Set([...named, ...pairs.filter(p => named.includes(p.base)).map(p => p.variant)]);
  const rest = axes.cases.filter(c => !covered.has(c) && !isVariant.has(c));
  const restVariants = pairs.filter(p => rest.includes(p.base) && !covered.has(p.variant)).map(p => p.variant);
  const restItem = named.length && rest.length
    ? `<li class="av-mention av-mention--rest"><span class="av-mention-name"${attrs({ title: rest.join(", ") })}>${rest.length === 1 ? `The one case the rule does not name, <code>${esc(rest[0])}</code>` : `The other ${rest.length} cases together`}</span>${counts(rest)}${restVariants.length ? `<span class="av-mention-variant"><span class="av-mention-vlabel">↳ their variants</span>${counts(restVariants)}</span>` : ""}</li>`
    : "";
  const key = arms.length > 1 && arms.length <= 8 ? `<p class="av-mention-key">${arms.map(a => ctx.arms.tag(a, { id: false })).join("")}</p>` : "";
  return `<div class="av-mentions"><h4 class="av-eyebrow">Named in the rule · passed / valid runs</h4>${key}<ul class="av-mention-list">${items}${restItem}</ul><p class="av-mention-note">Counts only: the report does not apply the rule; reading these counts against it is left to the reader.</p></div>`;
}

export function verdict(input: VerdictInput, ctx?: RenderContext): string {
  const asked = String(input.verdict ?? "").toLowerCase();
  const kind: VerdictKind = asked in verdictWords ? asked as VerdictKind : "none";
  const stamp = `<div class="av-stamp av-stamp--${kind}"><span class="av-stamp-icon" aria-hidden="true">${verdictIcons[kind]}</span><span class="av-stamp-word">${esc(input.label || verdictWords[kind])}</span></div>`;
  const lists = ([["conditions", "Holds when"], ["limits", "Does not show"], ["changes", "Would change it"]] as const)
    .filter(([key]) => (strings(input[key]) || []).length)
    .map(([key, title]) => `<div class="av-verdict-list av-verdict-list--${key}"><h4>${title}</h4><ul>${(strings(input[key]) || []).map(x => `<li>${inline(x)}</li>`).join("")}</ul></div>`).join("");
  const checkItems = Array.isArray(input.checks) ? input.checks.filter(c => c && typeof c === "object") : [];
  const checkItem = (c: typeof checkItems[number]) => {
    const state = c.met === true ? "met" : c.met === false ? "unmet" : "open";
    const word = state === "met" ? "met" : state === "unmet" ? "not met" : "not evaluated";
    return `<li class="av-rule-check av-rule-check--${state}"><span class="av-rule-label">${esc(c.label)}</span><span class="av-rule-obs">${esc(c.observed)}</span>${c.threshold ? `<span class="av-rule-thr">${esc(c.threshold)}</span>` : "<span></span>"}<span class="av-rule-state"><span class="av-rule-dot" aria-hidden="true"></span>${word}</span></li>`;
  };
  // Ungrouped terms decide the verdict and come first; each group follows under its own subheading.
  const groupOf = (c: typeof checkItems[number]) => typeof c.group === "string" ? c.group.trim() : "";
  const groupNames = [...new Set(checkItems.map(groupOf).filter(Boolean))];
  const ungrouped = checkItems.filter(c => !groupOf(c));
  const checks = checkItems.length
    ? `${ungrouped.length ? `<ol class="av-rule-checks">${ungrouped.map(checkItem).join("")}</ol>` : ""}${groupNames.map(g => `<h5 class="av-rule-group">${esc(g)}</h5><ol class="av-rule-checks av-rule-checks--group">${checkItems.filter(c => groupOf(c) === g).map(checkItem).join("")}</ol>`).join("")}` : "";
  const ruleText = typeof input.rule === "string" ? input.rule : "";
  const quote = ruleText ? `<blockquote class="av-rule-text${ruleText.length > 400 ? " av-rule-text--long" : ""}">${prose(ruleText, "av-rule-prose")}</blockquote>` : "";
  const href = typeof input.alert?.href === "string" && /^#[A-Za-z][\w:.-]*$/.test(input.alert.href) ? input.alert.href : null;
  const alert = input.alert && typeof input.alert.text === "string" && input.alert.text
    ? `<p class="av-verdict-alert" role="note">${outcomeMark("invalid")}<span>${inline(input.alert.text)}${href ? ` <a href="${esc(href)}">${esc(input.alert.link || "See why")}</a>` : ""}</span></p>` : "";
  const headline = typeof input.headline === "string" ? input.headline : "";
  if (kind === "none") {
    // No decision: the rule is the main text, and the counts it names follow it.
    const rule = quote || checks ? `<div class="av-rule av-rule--main"><h4 class="av-eyebrow">Decision rule${quote ? " · fixed before results" : ""}</h4>${quote}${checks}</div>` : "";
    const mentions = ctx ? mentionsHtml(strings(input.mentions) || [], pairsOf(input.pairs), ctx) : "";
    const body = `<div class="av-verdict-grid av-verdict-grid--solo av-verdict-grid--none"><div class="av-verdict-main">${stamp}${headline ? `<p class="av-verdict-headline av-verdict-headline--quiet">${inline(headline)}</p>` : ""}${prose(input.detail, "av-verdict-detail")}${alert}${rule}${mentions}${lists ? `<div class="av-verdict-lists">${lists}</div>` : ""}</div></div>`;
    return frame("verdict", input, body, { "data-verdict": kind });
  }
  const rule = quote || checks ? `<aside class="av-rule"><h4 class="av-eyebrow">Decision rule${quote ? " · fixed before results" : ""}</h4>${quote}${checks}</aside>` : "";
  const body = `<div class="av-verdict-grid${rule ? "" : " av-verdict-grid--solo"}"><div class="av-verdict-main">${stamp}<p class="av-verdict-headline">${inline(headline)}</p>${prose(input.detail, "av-verdict-detail")}${alert}${lists ? `<div class="av-verdict-lists">${lists}</div>` : ""}</div>${rule}</div>`;
  return frame("verdict", input, body, { "data-verdict": kind });
}

// ------------------------------------------------------------------ figures

export interface FiguresInput extends FrameInput { items: Array<{ value: string | number | null; label: string; note?: string; tone?: "neutral" | "pass" | "fail" | "warn" | "invalid" }> }
export function figures(input: FiguresInput): string {
  const tones = ["neutral", "pass", "fail", "warn", "invalid"];
  const items = (Array.isArray(input.items) ? input.items : []).filter(i => i && typeof i === "object").map(i => {
    const t = tones.includes(i.tone as string) ? i.tone : "neutral";
    const v = i.value === null || i.value === undefined || (typeof i.value === "number" && !isNum(i.value))
      ? '<span class="av-missing">missing</span>'
      : typeof i.value === "number" ? esc(Number.isInteger(i.value) ? fmtInt(i.value) : fmtNum(i.value)) : esc(i.value);
    const text = typeof i.value === "string" && !/^[×x]?[\d.,–-]+%?$/.test(i.value);
    return `<div class="av-figure-stat av-tone--${t}"><dt>${esc(i.label)}</dt><dd><span class="av-figure-value${text ? " av-figure-value--text" : ""}">${v}</span>${i.note ? `<span class="av-figure-note">${esc(i.note)}</span>` : ""}</dd></div>`;
  }).join("");
  return frame("figures", input, `<dl class="av-figures-row">${items}</dl>`);
}

// ------------------------------------------------------------------ ladder

export interface LadderRow { arm?: string; case?: string; k: number; n: number; invalid?: number; note?: string }
export interface LadderInput extends FrameInput {
  rows?: LadderRow[];
  /** Rows are arms (the default) or cases. */
  by?: "arm" | "case";
  /** Restrict to one case, or to a set of cases; otherwise every run of each arm is pooled. */
  case?: string;
  cases?: string[];
  /** Restrict to a set of arms; by case, these arms' runs are pooled per case. */
  arms?: string[];
  /** Groups of arms given identical material: their spread is visible noise. */
  identical?: string[][];
  /** An arm whose rate draws a reference line. */
  baseline?: string;
  /** Order rows by rate instead of by identity order. */
  sort?: "identity" | "rate";
  /** Thresholds to draw across every row, such as a decision rule's bar (rates in 0–1). */
  references?: Array<{ value: number; label: string }>;
  /** Case variants: by case, each variant row sits under its base. */
  pairs?: CasePair[];
}

export function ladder(input: LadderInput, ctx: RenderContext): string {
  const byCase = input.by === "case";
  const pairs = pairsOf(input.pairs);
  const onlyArms = strings(input.arms), onlyCases = strings(input.cases);
  let rows: LadderRow[] | undefined = Array.isArray(input.rows) ? input.rows.filter(r => r && typeof r === "object") : undefined;
  if (!rows) {
    const data = trialOf(ctx, "ladder");
    const axes = trialAxes(data);
    const runs = data.runs.filter(r => (!onlyArms || onlyArms.includes(r.arm)) && (!input.case || r.scenario === input.case) && (!onlyCases || onlyCases.includes(r.scenario)));
    rows = byCase
      ? pairedOrder(onlyCases ? onlyCases.filter(c => axes.cases.includes(c)) : axes.cases, pairs).map(cs => { const t = tally(runs.filter(r => r.scenario === cs)); return { case: cs, k: t.pass, n: t.valid, invalid: t.invalid }; })
      : axes.arms.map(arm => { const t = tally(runs.filter(r => r.arm === arm)); return { arm, k: t.pass, n: t.valid, invalid: t.invalid }; });
    rows = rows.filter(r => r.n + (r.invalid || 0) > 0);
  }
  if (!rows.length) return frame("ladder", input, empty("No runs to show."));
  const key = (r: LadderRow) => String((byCase ? r.case : r.arm) ?? "");
  rows = rows.map(r => ({ ...r, arm: byCase ? r.arm : key(r), case: byCase ? key(r) : r.case, k: count(r.k), n: count(r.n), invalid: count(r.invalid) }));
  if (input.sort === "rate") rows.sort((a, b) => (b.n && b.k <= b.n ? b.k / b.n : -1) - (a.n && a.k <= a.n ? a.k / a.n : -1));
  else if (!byCase) rows.sort((a, b) => ctx.arms.index(a.arm!) - ctx.arms.index(b.arm!));
  // By case, one arm's runs draw in that arm's color; pooled arms draw in the accent.
  const ranArms = byCase && ctx.trial ? [...new Set(ctx.trial.runs.filter(r => !onlyArms || onlyArms.includes(r.arm)).map(r => r.arm))] : [];
  const caseColor = ranArms.length === 1 ? ctx.arms.color(ranArms[0]) : "var(--av-accent)";
  const variantOf = new Map(pairs.map(p => [p.variant, p]));
  // Identical groups sit together, in the position of their first member.
  const groups = byCase ? [] : (Array.isArray(input.identical) ? input.identical : []).map(g => (strings(g) || []).filter(a => rows!.some(r => r.arm === a))).filter(g => g.length > 1);
  const grouped = new Map<string, number>();
  groups.forEach((g, i) => g.forEach(a => grouped.set(a, i)));
  const ordered: Array<LadderRow | { group: number; rows: LadderRow[] }> = [];
  const placed = new Set<number>();
  for (const r of rows) {
    const g = byCase ? undefined : grouped.get(r.arm!);
    if (g === undefined) ordered.push(r);
    else if (!placed.has(g)) { placed.add(g); ordered.push({ group: g, rows: groups[g].map(a => rows!.find(x => x.arm === a)!) }); }
  }
  const base = !byCase && input.baseline ? rows.find(r => r.arm === input.baseline) : undefined;
  const baseRate = base && base.n && base.k <= base.n ? base.k / base.n : null;

  const row = (r: LadderRow, noise?: [number, number]) => {
    const bad = r.k > r.n, p = r.n && !bad ? r.k / r.n : null, ci = bad ? null : wilson(r.k, r.n);
    const color = byCase ? caseColor : ctx.arms.color(r.arm!);
    const style = `--c:${color};${p !== null ? `--p:${pos(p)};` : ""}${ci ? `--lo:${pos(ci[0])};--hi:${pos(ci[1])};` : ""}`;
    const invalid = r.invalid ? `<span class="av-chip av-chip--invalid" title="Invalid runs are excluded, never counted as failures">${outcomeMark("invalid")}${fmtInt(r.invalid!)} invalid</span>` : "";
    const thin = r.n > 0 && r.n < 5 && !bad ? `<span class="av-chip av-chip--warn" title="Too few valid runs for a reliable rate">n = ${r.n}</span>` : "";
    const badChip = bad ? `<span class="av-chip av-chip--warn" title="More passes than valid runs: these counts cannot be a rate">counts invalid</span>` : "";
    const isBase = !byCase && r.arm === input.baseline;
    const label = `${bad ? `counts invalid: ${r.k} of ${r.n}` : p === null ? "no valid runs" : `${r.k} of ${r.n} valid runs passed, ${fmtPct(p)}`}${ci ? `, 95% interval ${fmtPct(ci[0])} to ${fmtPct(ci[1])}` : ""}${r.invalid ? `, ${r.invalid} invalid` : ""}`;
    const variant = byCase ? variantOf.get(r.case!) : undefined;
    const note = r.note ?? (byCase ? undefined : ctx.arms.note(r.arm!));
    const name = byCase
      ? `${variant ? `<span class="av-ladder-variant"${attrs({ title: variant.note })}>↳ ${esc(variant.label)}</span>` : ""}<span class="av-ladder-case">${esc(caseLabel(ctx, r.case!))}</span>`
      : ctx.arms.tag(r.arm!);
    const flags = isBase || thin || invalid || badChip ? `<span class="av-ladder-flags">${isBase ? '<span class="av-chip av-chip--base">baseline</span>' : ""}${badChip}${thin}${invalid}</span>` : "";
    const seg = noise ? `<span class="av-noise-seg" aria-hidden="true" style="--nlo:${pos(noise[0])};--nhi:${pos(noise[1])}"></span>` : "";
    return `<div class="av-ladder-row${variant ? " av-ladder-row--variant" : ""}" role="row"${attrs(byCase ? { "data-case": r.case } : { "data-arm": r.arm })}>
<div class="av-ladder-label" role="rowheader">${name}${note ? `<span class="av-ladder-note">${esc(note)}</span>` : ""}${flags}</div>
<div class="av-ladder-track${p === null ? " av-ladder-track--empty" : ""}" role="cell" style="${style}" aria-label="${esc(label)}">${seg}${ci ? '<span class="av-ci"></span>' : ""}${p !== null ? '<span class="av-pt"></span>' : `<span class="av-ladder-none">${bad ? "counts invalid" : "no valid runs"}</span>`}</div>
<div class="av-ladder-num" role="cell"><span class="av-frac${bad ? " av-frac--bad" : ""}"><b>${r.k}</b>/${r.n}</span><span class="av-rate">${bad ? "—" : fmtPct(p)}</span>${ci ? `<span class="av-ci-text">${fmtPct(ci[0])}–${fmtPct(ci[1])}</span>` : ""}</div>
</div>`;
  };
  const body = ordered.map(item => {
    if (!("group" in item)) return row(item);
    const pts = item.rows.filter(r => r.n && r.k <= r.n).map(r => r.k / r.n);
    const lo = pts.length ? Math.min(...pts) : 0, hi = pts.length ? Math.max(...pts) : 0;
    const spread = pts.length > 1 ? `${Math.round((hi - lo) * 100)} points apart` : "spread not measurable";
    return `<div class="av-ladder-group" role="rowgroup"><div class="av-ladder-group-label"><span class="av-eyebrow">Identical arms</span><span>${esc(spread)}: the noise between copies of the same material</span></div><div class="av-ladder-group-rows">${item.rows.map(r => row(r, pts.length > 1 ? [lo, hi] : undefined)).join("")}</div></div>`;
  }).join("");
  const ticks = [0, .25, .5, .75, 1].map(t => `<span style="--x:${pos(t)}">${t * 100}%</span>`).join("");
  const references = (Array.isArray(input.references) ? input.references : []).filter(r => r && isNum(r.value));
  const refs = [
    ...(baseRate !== null ? [{ value: baseRate, label: `${ctx.arms.label(input.baseline!)} ${fmtPct(baseRate)}`, kind: "base" }] : []),
    ...references.map(r => ({ value: Math.max(0, Math.min(1, r.value)), label: String(r.label ?? ""), kind: "rule" })),
  ];
  const ref = refs.map(r => `<div class="av-ladder-ref av-ladder-ref--${r.kind}" aria-hidden="true" style="--x:${pos(r.value)}"><span>${esc(r.label)}</span></div>`).join("");
  const legend = `<p class="av-legend"><span><span class="av-legend-ci"></span>95% Wilson interval</span><span><span class="av-legend-pt"></span>pass rate over valid runs</span>${groups.length ? '<span><span class="av-legend-noise"></span>spread between identical arms</span>' : ""}${baseRate !== null ? '<span class="av-legend-item--ref"><span class="av-legend-ref"></span>baseline</span>' : ""}${references.length ? '<span class="av-legend-item--ref"><span class="av-legend-ref av-legend-ref--rule"></span>threshold</span>' : ""}</p>`;
  return frame("ladder", { title: input.title, description: input.description, note: input.note, id: input.id },
    `${legend}<div class="av-ladder-grid${ref ? " av-ladder-grid--ref" : ""}${byCase ? " av-ladder-grid--cases" : ""}" role="table" aria-label="${esc(input.title || (byCase ? "Pass rate by case" : "Pass rate by arm"))}"><div class="av-ladder-axis" role="row" aria-hidden="true"><span></span><div class="av-ladder-ticks">${ticks}</div><span></span></div>${body}${ref}</div>`, byCase ? { "data-by": "case" } : {});
}

// ------------------------------------------------------------------ tapestry

export interface CaseGroup { label: string; cases: string[]; note?: string }
export interface TapestryInput extends FrameInput { arms?: string[]; cases?: string[]; transpose?: boolean; groups?: CaseGroup[]; pairs?: CasePair[] }

export function tapestry(input: TapestryInput, ctx: RenderContext): string {
  const data = trialOf(ctx, "tapestry");
  const axes = trialAxes(data);
  const pairs = pairsOf(input.pairs);
  const groupsIn = (Array.isArray(input.groups) ? input.groups : []).filter(g => g && typeof g === "object").map(g => ({ label: String(g.label ?? ""), note: typeof g.note === "string" ? g.note : undefined, cases: strings(g.cases) || [] }));
  const arms = (strings(input.arms) || axes.arms).slice().sort(byIdentity(ctx)), cases = pairedOrder(strings(input.cases) || axes.cases, pairs);
  if (!arms.length || !cases.length) return frame("tapestry", input, empty("No runs to show."));
  const transpose = groupsIn.length ? false : input.transpose ?? (arms.length > 8 && cases.length < arms.length);
  const cols = transpose ? cases : arms, rows = transpose ? arms : cases;
  const variantOf = new Map(pairs.filter(p => cases.includes(p.base)).map(p => [p.variant, p]));
  const baseOf = new Set([...variantOf.values()].map(p => p.base));
  const cell = (arm: string, cs: string) => {
    const runs = data.runs.filter(r => r.arm === arm && r.scenario === cs).sort((a, b) => (num(a.repeat) ?? 0) - (num(b.repeat) ?? 0));
    if (!runs.length) return `<div class="av-tap-cell av-tap-cell--none" role="cell"><span class="av-tap-none">not run</span></div>`;
    const t = tally(runs);
    const marks = runs.map(r => {
      const o = outcomeOf(r), i = ctx.runIndex.get(r);
      const why = causePhrase(r, data);
      const judge = o === "pass" && r.judge?.verdict ? " · judge pass" : "";
      const label = `${caseLabel(ctx, cs)} · ${ctx.arms.label(arm)} · repeat ${num(r.repeat) ?? "?"}: ${outcomeLabel[o]}${judge}${why ? ` · ${why}` : ""}`;
      return `<button type="button" class="av-run av-run--${o}"${attrs({ "data-run": i, title: label, "aria-label": label })}></button>`;
    }).join("");
    const share = t.valid ? t.pass / t.valid : null;
    const ci = t.interval;
    const summary = `${t.pass} of ${t.valid} valid runs passed${ci ? ` (95% interval ${fmtPct(ci[0])}–${fmtPct(ci[1])})` : ""}${t.invalid ? `; ${t.invalid} invalid` : ""}`;
    const track = share !== null && ci
      ? `<div class="av-tap-track" aria-hidden="true" style="--p:${pos(share)};--lo:${pos(ci[0])};--hi:${pos(ci[1])}"><i class="av-tap-ci"></i><b class="av-tap-pt"></b></div>`
      : `<span class="av-tap-none">no valid runs</span>`;
    return `<div class="av-tap-cell${share === null ? " av-tap-cell--novalid" : ""}" role="cell" style="--share:${share === null ? 0 : share.toFixed(3)}" data-arm="${esc(arm)}" title="${esc(summary)}"><div class="av-tap-head"><span class="av-frac"><b>${t.pass}</b>/${t.valid}</span>${share !== null ? `<span class="av-tap-rate">${fmtPct(share)}</span>` : ""}${t.invalid ? `<span class="av-tap-inv" title="${t.invalid} invalid">${outcomeMark("invalid")}${t.invalid}</span>` : ""}</div><div class="av-tap-marks">${marks}</div>${track}</div>`;
  };
  const caseHead = (cs: string) => {
    const v = variantOf.get(cs), d = scenarioOf(data, cs)?.description;
    return `${v ? `<span class="av-tap-variant"${attrs({ title: v.note })}>↳ ${esc(v.label)}</span>` : ""}<span class="av-case-name"${attrs({ title: typeof d === "string" ? clip(d, 400) : undefined })}>${esc(caseLabel(ctx, cs))}</span>`;
  };
  const head = `<div class="av-tap-row av-tap-row--head" role="row"><div class="av-tap-corner" role="columnheader"><span>${transpose ? "Arm" : "Case"}</span><span>${transpose ? "Case" : "Arm"} →</span></div>${cols.map(c => `<div class="av-tap-colhead" role="columnheader">${transpose ? caseHead(c) : ctx.arms.tag(c, { id: false })}</div>`).join("")}</div>`;
  const line = (rw: string) => {
    const kind = transpose ? "" : variantOf.has(rw) ? " av-tap-row--variant" : baseOf.has(rw) ? " av-tap-row--base" : "";
    return `<div class="av-tap-row${kind}" role="row"><div class="av-tap-rowhead" role="rowheader">${transpose ? ctx.arms.tag(rw, { id: false }) : caseHead(rw)}</div>${cols.map(c => transpose ? cell(rw, c) : cell(c, rw)).join("")}</div>`;
  };
  let body = "";
  if (groupsIn.length && !transpose) {
    const placed = new Set<string>();
    const groups = [...groupsIn.map(g => ({ ...g, cases: rows.filter(c => g.cases.includes(c)) })), { label: "Other cases", note: undefined, cases: rows.filter(c => !groupsIn.some(g => g.cases.includes(c))) }].filter(g => g.cases.length);
    for (const g of groups) {
      const t = tally(data.runs.filter(r => g.cases.includes(r.scenario) && arms.includes(r.arm)));
      body += `<div class="av-tap-row av-tap-row--group" role="row"><div class="av-tap-group" role="rowheader"><span class="av-tap-group-label">${esc(g.label)}</span><span class="av-muted">${plural(g.cases.length, "case")} · ${t.pass}/${t.valid} passed${t.invalid ? ` · ${t.invalid} invalid` : ""}${g.note ? ` · ${esc(g.note)}` : ""}</span></div></div>`;
      body += g.cases.filter(c => !placed.has(c)).map(c => { placed.add(c); return line(c); }).join("");
    }
  } else body = rows.map(line).join("");
  const legend = `<p class="av-legend">${(["pass", "fail", "invalid"] as Outcome[]).map(o => `<span>${outcomeMark(o)}${o === "invalid" ? "invalid: excluded, not a failure" : outcomeLabel[o].toLowerCase()}</span>`).join("")}<span><span class="av-legend-tap" aria-hidden="true"><i></i><b></b></span>pass share and its 95% interval</span>${variantOf.size ? "<span>↳ the case above, run with more turns</span>" : ""}<span class="av-legend-hint">Each mark is one run; select it for its record.</span></p>`;
  return frame("tapestry", input, `${legend}<div class="av-scroll-x"><div class="av-tap" role="table" style="--cols:${cols.length}" aria-label="${esc(input.title || "Every run by case and arm")}">${head}${body}</div></div>`);
}

// ------------------------------------------------------------------ checks

export interface ChecksInput extends FrameInput {
  arms?: string[];
  checks?: string[];
  cases?: string[];
  /** One table per case (the default when cases require different checks) or one pooled table per check. */
  by?: "case" | "check";
  /** Case variants: each variant sits under its base. */
  pairs?: CasePair[];
  /** false: only the recorded measures, by case, for a page whose case views already show the required checks and judge. */
  required?: boolean;
}
const heat = (k: number, n: number, measure = false) => {
  if (!n) return `<td class="av-heat av-heat--none"><span>—</span></td>`;
  const s = k / n;
  return `<td class="av-heat${measure ? " av-heat--measure" : ""}" style="--s:${s.toFixed(3)}"><span class="av-frac"><b>${k}</b>/${n}</span><span class="av-heat-bar" aria-hidden="true"><span></span></span></td>`;
};
/** A check or measure name that may wrap after its underscores rather than mid-word. */
const checkName = (name: string) => `<code>${esc(name).replace(/_/g, "_<wbr>")}</code>`;
const chipList = (names: string[]) => `<p class="av-ck-names">${names.map(n => `<code>${esc(n)}</code>`).join(" ")}</p>`;

export function checks(input: ChecksInput, ctx: RenderContext): string {
  const data = trialOf(ctx, "checks");
  const axes = trialAxes(data);
  const arms = (strings(input.arms) || axes.arms).slice().sort(byIdentity(ctx));
  const only = strings(input.checks);
  const ranCases = new Set(data.runs.map(r => r.scenario));
  const cases = pairedOrder((strings(input.cases) || axes.cases).filter(c => ranCases.has(c)), pairsOf(input.pairs));
  const reqCount = new Map<string, number>();
  for (const cs of cases) for (const c of new Set(scenarioOf(data, cs)?.required || [])) reqCount.set(c, (reqCount.get(c) || 0) + 1);
  const autoByCase = cases.length > 1 && [...reqCount.values()].some(n => n < cases.length);
  if (input.required === false) return measuresByCase(input, ctx, data, arms, cases, only);
  return (input.by === "case" || (input.by !== "check" && autoByCase)) && cases.length ? checksByCase(input, ctx, data, arms, cases, only) : checksByCheck(input, ctx, data, arms, only);
}

/** One case's measures: true/false shares, and medians with their range for numbers. */
function measuresTable(t: ReturnType<typeof caseChecks>, arms: string[], armHead: string): string {
  return `<div class="av-scroll-x"><table class="av-heatmap av-heatmap--measures" style="--arms:${arms.length}">${colgroup(arms)}<thead><tr><th scope="col">Measure</th>${armHead}</tr></thead><tbody>${t.measures.map(m => `<tr><th scope="row">${checkName(m.name)}</th>${arms.map(a => {
    const c = m.cells[a];
    if (!c || !c.n) return `<td class="av-heat av-heat--none"><span>—</span></td>`;
    if (m.kind === "boolean") return heat(c.k, c.n, true);
    return `<td class="av-ck-numeric"><span class="av-num-median">${esc(fmtNum(c.median))}</span>${c.min !== c.max ? `<span class="av-muted">${esc(fmtNum(c.min))}–${esc(fmtNum(c.max))}</span>` : ""}</td>`;
  }).join("")}</tr>`).join("")}</tbody></table></div>`;
}

function measuresByCase(input: ChecksInput, ctx: RenderContext, data: TrialReport, arms: string[], cases: string[], only?: string[]): string {
  const variantOf = new Map(pairsOf(input.pairs).map(p => [p.variant, p]));
  const armHead = arms.map(a => `<th scope="col">${ctx.arms.tag(a, { id: false })}</th>`).join("");
  const panels = cases.map(cs => {
    const t = caseChecks(data, cs, arms);
    if (only) t.measures = t.measures.filter(m => only.includes(m.name));
    if (!t.measures.length) return "";
    const v = variantOf.get(cs), label = caseLabel(ctx, cs);
    const bools = t.measures.filter(m => m.kind === "boolean").length, nums = t.measures.length - bools;
    const what = [bools ? plural(bools, "true or false measure") : "", nums ? plural(nums, "number") : ""].filter(Boolean).join(" and ");
    return `<section class="av-ck-case${v ? " av-ck-case--variant" : ""}"${attrs({ "data-case": cs })}><header class="av-ck-head"><h4 class="av-ck-title">${v ? `<span class="av-ck-variant"${attrs({ title: v.note })}>↳ ${esc(v.label)}</span>` : ""}<span class="av-case-name">${esc(label)}</span>${label !== cs ? ` <code>${esc(cs)}</code>` : ""}</h4></header><details class="av-ck-measures"${t.measures.length <= 4 ? " open" : ""}><summary>${esc(what)} <span class="av-muted">· recorded, not required for a pass</span></summary>${measuresTable(t, arms, armHead)}</details></section>`;
  }).join("");
  if (!panels) return frame("checks", input, empty("No measures were recorded beyond the required checks."));
  const legend = `<p class="av-legend"><span>True or false: runs where it was true / valid runs, shaded by share, not by merit.</span><span>Numbers: the median, with the range beneath.</span></p>`;
  return frame("checks", input, `${legend}<div class="av-ck-cases" style="--arms:${arms.length}">${panels}</div>`, { "data-by": "measures" });
}

function colgroup(arms: string[]): string {
  return `<colgroup><col class="av-ck-col-name">${arms.map(() => '<col class="av-ck-col-arm">').join("")}</colgroup>`;
}

function checksByCheck(input: ChecksInput, ctx: RenderContext, data: TrialReport, arms: string[], only?: string[]): string {
  let rows = checkTable(data, arms);
  if (only) rows = rows.filter(r => only.includes(r.name));
  const judged = data.runs.filter(r => r.judge && (r.judge.verdict === "pass" || r.judge.verdict === "fail"));
  if (!rows.length && !judged.length) return frame("checks", input, empty("No pass/fail checks were recorded."));
  const head = `<thead><tr><th scope="col" class="av-heat-corner">Check</th>${arms.map(a => `<th scope="col">${ctx.arms.tag(a, { id: false })}</th>`).join("")}</tr></thead>`;
  const caseCount = new Set(data.runs.map(r => r.scenario)).size;
  const line = (r: typeof rows[number]) => `<tr><th scope="row">${checkName(r.name)}${r.required && r.requiredIn.length < caseCount ? ` <span class="av-chip av-chip--req" title="${esc(r.requiredIn.join(", "))}">in ${r.requiredIn.length} of ${caseCount} cases</span>` : ""}</th>${arms.map(a => heat(r.cells[a].k, r.cells[a].n, !r.required)).join("")}</tr>`;
  const span = arms.length + 1;
  const fold = (summary: string, names: string[]) => names.length ? `<tr class="av-ck-fold"><td colspan="${span}"><details><summary>${esc(summary)}</summary>${chipList(names)}</details></td></tr>` : "";
  const group = (label: string, note: string, items: typeof rows, folded = "") => items.length || folded ? `<tr class="av-heat-group"><th scope="rowgroup" colspan="${span}">${esc(label)} <span class="av-muted">· ${esc(note)}</span></th></tr>${items.map(line).join("")}${folded}` : "";
  // Rows that never differ fold away, so the ones that do are not buried.
  const always = (r: typeof rows[number]) => arms.some(a => r.cells[a].n > 0) && arms.every(a => r.cells[a].k === r.cells[a].n);
  const never = (r: typeof rows[number]) => arms.some(a => r.cells[a].n > 0) && arms.every(a => r.cells[a].k === 0);
  const required = rows.filter(r => r.required), measures = rows.filter(r => !r.required);
  const reqShown = required.length > 3 ? required.filter(r => !always(r)) : required, reqHeld = required.filter(r => !reqShown.includes(r));
  const steady = measures.length > 3 ? measures.filter(r => always(r) || never(r)) : [], measShown = measures.filter(r => !steady.includes(r));
  const judgeRow = judged.length ? `<tr class="av-heat-group"><th scope="rowgroup" colspan="${span}">Judge <span class="av-muted">· runs the judge passed, of valid judged runs</span></th></tr><tr><th scope="row">verdict = pass</th>${arms.map(a => { const js = judged.filter(r => r.arm === a && r.passed !== null); return heat(js.filter(r => r.judge!.verdict === "pass").length, js.length); }).join("")}</tr>` : "";
  const body = group("Required checks", "true is a pass; counted over the cases that require each one", reqShown, fold(`${plural(reqHeld.length, "more required check")} held in every valid run, in every arm`, reqHeld.map(r => r.name)))
    + judgeRow
    + group("Recorded measures", "recorded true or false, not required for a pass; shaded by share, not by merit", measShown, fold(`${plural(steady.length, "measure")} never changed: ${steady.filter(always).length} always true, ${steady.filter(never).length} never true`, steady.map(r => `${r.name} ${always(r) ? "true" : "false"}`)));
  return frame("checks", input, `<div class="av-scroll-x"><table class="av-heatmap" style="--arms:${arms.length}">${colgroup(arms)}${head}<tbody>${body}</tbody></table></div>`, { "data-by": "check" });
}

function checksByCase(input: ChecksInput, ctx: RenderContext, data: TrialReport, arms: string[], cases: string[], only?: string[]): string {
  const pairs = pairsOf(input.pairs), variantOf = new Map(pairs.map(p => [p.variant, p]));
  const span = arms.length + 1;
  const armHead = arms.length > 1 ? arms.map(a => `<th scope="col">${ctx.arms.tag(a, { id: false })}</th>`).join("") : `<th scope="col">${ctx.arms.tag(arms[0], { id: false })}</th>`;
  const anyFailed = (cells: Record<string, { k: number; n: number }>) => arms.some(a => cells[a] && cells[a].k < cells[a].n);
  const panels = cases.map(cs => {
    const t = caseChecks(data, cs, arms);
    const plan = scenarioOf(data, cs);
    const required = only ? t.required.filter(r => only.includes(r.name)) : t.required;
    const failing = required.filter(r => anyFailed(r.cells)), held = required.filter(r => !anyFailed(r.cells));
    const judgeFailed = !!t.judge && anyFailed(t.judge);
    const clean = !failing.length && !judgeFailed && arms.every(a => t.outcome[a].k === t.outcome[a].n);
    const outcome = arms.filter(a => t.outcome[a].n + t.outcome[a].invalid > 0).map(a => {
      const o = t.outcome[a];
      return `<span class="av-ck-arm"${attrs({ title: `${ctx.arms.label(a)}: ${o.k} of ${o.n} valid runs passed${o.invalid ? `; ${o.invalid} invalid` : ""}` })}>${arms.length > 1 ? ctx.arms.glyph(a) : ""}<span class="av-frac"><b>${o.k}</b>/${o.n}</span>${o.invalid ? `<span class="av-tap-inv">${outcomeMark("invalid")}${o.invalid}</span>` : ""}</span>`;
    }).join("");
    const v = variantOf.get(cs), label = caseLabel(ctx, cs);
    const title = `<h4 class="av-ck-title">${v ? `<span class="av-ck-variant"${attrs({ title: v.note })}>↳ ${esc(v.label)}</span>` : ""}<span class="av-case-name">${esc(label)}</span>${label !== cs ? ` <code>${esc(cs)}</code>` : ""}</h4>`;
    const head = `<header class="av-ck-head">${title}<div class="av-ck-outcome"><span class="av-ck-outcome-label">passed</span>${outcome}</div></header>`;
    const row = (name: string, cells: Record<string, { k: number; n: number }>, cls = "") => `<tr${cls ? ` class="${cls}"` : ""}><th scope="row">${name}</th>${arms.map(a => heat(cells[a]?.k ?? 0, cells[a]?.n ?? 0)).join("")}</tr>`;
    const judgeRow = t.judge ? row(`<span class="av-ck-judge">Judge says pass</span>${judgePassWhen(plan) ? `<span class="av-ck-when"${attrs({ title: judgePassWhen(plan) })}>${esc(clip(judgePassWhen(plan)!, 140))}</span>` : ""}`, t.judge, "av-ck-judgerow") : "";
    const measures = t.measures.length ? `<details class="av-ck-measures"><summary>${plural(t.measures.length, "recorded measure")} <span class="av-muted">· recorded, not required for a pass</span></summary>${measuresTable(t, arms, armHead)}</details>` : "";
    if (clean) {
      const what = required.length ? `${required.length === 1 ? "The required check" : `All ${required.length} required checks`} held in every valid run${t.judge ? ", and the judge said pass" : ""}.` : t.judge ? "The judge said pass in every valid run." : "Every valid run passed.";
      const none = arms.every(a => !t.outcome[a].n);
      return `<section class="av-ck-case av-ck-case--clean${v ? " av-ck-case--variant" : ""}"${attrs({ "data-case": cs })}>${head}<p class="av-ck-clean">${none ? `<span class="av-muted">No valid runs.</span>` : `${outcomeMark("pass")}${esc(what)}`}</p>${held.length ? `<details class="av-ck-heldlist"><summary>Show the ${plural(held.length, "check")}</summary>${chipList(held.map(r => r.name))}</details>` : ""}${measures}</section>`;
    }
    const rows = failing.map(r => row(`${checkName(r.name)}`, r.cells, "av-ck-failing")).join("");
    const fold = held.length ? `<tr class="av-ck-fold"><td colspan="${span}"><details><summary>${plural(held.length, "more required check")} held in every valid run</summary>${chipList(held.map(r => r.name))}</details></td></tr>` : "";
    const table = `<div class="av-scroll-x"><table class="av-heatmap av-heatmap--case" style="--arms:${arms.length}">${colgroup(arms)}<thead><tr><th scope="col">Must hold</th>${armHead}</tr></thead><tbody>${rows}${judgeRow}${fold}</tbody></table></div>`;
    return `<section class="av-ck-case${v ? " av-ck-case--variant" : ""}"${attrs({ "data-case": cs })}>${head}${table}${measures}</section>`;
  }).join("");
  const legend = `<p class="av-legend"><span>Each case's required checks and judge, over its valid runs; checks that failed somewhere come first.</span><span>Cells: runs where the check held / valid runs.</span></p>`;
  return frame("checks", input, `${legend}<div class="av-ck-cases" style="--arms:${arms.length}">${panels}</div>`, { "data-by": "case" });
}

// ------------------------------------------------------------------ pairwise

export interface PairwiseInput extends FrameInput { pair?: string }
export function pairwise(input: PairwiseInput, ctx: RenderContext): string {
  const data = trialOf(ctx, "pairwise");
  const pairs = Object.entries(data.pairwise || {}).filter(([k, p]) => p && typeof p === "object" && (!input.pair || k === input.pair));
  if (!pairs.length) return frame("pairwise", input, empty("No pairwise judgments were run."));
  const segs = ["a_wins", "tie", "b_wins", "inconsistent", "invalid"] as const;
  const clean = (st: Partial<Record<string, unknown>> | undefined) => {
    const o = { a_wins: 0, tie: 0, b_wins: 0, inconsistent: 0, invalid: 0 };
    for (const k of segs) o[k] = count(st?.[k]);
    const rate = num(st?.a_win_rate), iv = Array.isArray(st?.a_win_rate_interval) ? (st!.a_win_rate_interval as unknown[]).map(num) : null;
    return { ...o, total: segs.reduce((n, k) => n + o[k], 0), rate, interval: iv && iv[0] !== null && iv[1] !== null ? [iv[0], iv[1]] as [number, number] : null };
  };
  let maxTotal = 1;
  for (const [, p] of pairs) for (const st of [p.overall, ...Object.values(p.scenarios || {})]) maxTotal = Math.max(maxTotal, clean(st as never).total);
  const html = pairs.map(([key, p]) => {
    const [a, b] = (Array.isArray(p.arms) ? p.arms : ["A", "B"]).map(String);
    const present = new Set<string>();
    for (const st of [p.overall, ...Object.values(p.scenarios || {})]) { const c = clean(st as never); for (const k of segs) if (c[k]) present.add(k); }
    const words: Record<string, string> = { a_wins: `${ctx.arms.label(a)} preferred in both orders`, tie: "tie in both orders", b_wins: `${ctx.arms.label(b)} preferred in both orders`, inconsistent: "the two orders disagree", invalid: "invalid" };
    const line = (label: string, raw: unknown, strong = false) => {
      const s = clean(raw as never), total = s.total || 1;
      const bar = segs.map(k => s[k] ? `<span class="av-duel-seg av-duel-seg--${k}" style="flex:${s[k]}" title="${esc(`${words[k]}: ${s[k]}`)}">${s[k] / total > .1 && k !== "inconsistent" ? s[k] : ""}</span>` : "").join("");
      const rate = s.rate !== null && s.interval ? `${fmtPct(s.rate)} <span class="av-ci-text">${fmtPct(s.interval[0])}–${fmtPct(s.interval[1])}</span>` : '<span class="av-muted">no decisive pairs</span>';
      return `<div class="av-duel-row${strong ? " av-duel-row--overall" : ""}"><span class="av-duel-label">${esc(label)}<span class="av-muted"> · ${plural(s.total, "pair")}</span></span><div class="av-duel-track"><div class="av-duel-bar" style="width:${pos(s.total / maxTotal)}" role="img" aria-label="${esc(`${label}: ${ctx.arms.label(a)} preferred ${s.a_wins}, ties ${s.tie}, ${ctx.arms.label(b)} preferred ${s.b_wins}, order-inconsistent ${s.inconsistent}, invalid ${s.invalid}`)}">${bar}</div>${s.inconsistent ? `<span class="av-duel-split" title="the two orders disagree">${s.inconsistent} split</span>` : ""}</div><span class="av-duel-rate">${rate}</span></div>`;
    };
    // One scale for every row, the overall row included, so a bar's length always means the same number of pairs.
    const scen = Object.entries(p.scenarios || {}).map(([s, st]) => line(caseLabel(ctx, s), st)).join("");
    const legend = `<p class="av-legend av-duel-legend">${segs.filter(k => present.has(k)).map(k => `<span><span class="av-sw av-duel-seg--${k}"></span>${k === "a_wins" ? ctx.arms.glyph(a) : k === "b_wins" ? ctx.arms.glyph(b) : ""}${esc(words[k])}</span>`).join("")}<span>Bar length is the number of pairs, on one scale for every row.</span></p>`;
    return `<div class="av-duel" data-pair="${esc(key)}" style="--c-a:${ctx.arms.color(a)};--c-b:${ctx.arms.color(b)}"><div class="av-duel-head">${ctx.arms.tag(a)}<span class="av-duel-vs">preferred over</span>${ctx.arms.tag(b)}<span class="av-duel-rate-head">${esc(ctx.arms.label(a))} win rate</span></div>${legend}${line("All cases", p.overall, true)}${scen}</div>`;
  }).join("");
  return frame("pairwise", input, html);
}

// ------------------------------------------------------------------ cost

export interface CostInput extends FrameInput { measures?: string[]; arms?: string[] }
export function cost(input: CostInput, ctx: RenderContext): string {
  const data = trialOf(ctx, "cost");
  const arms = (strings(input.arms) || trialAxes(data).arms).slice().sort(byIdentity(ctx));
  const only = strings(input.measures);
  const measures = costMeasures(data).filter(m => !only || only.includes(m.id));
  const invalidRuns = data.runs.filter(r => r.passed === null && arms.includes(r.arm)).length;
  const nothing = () => frame("cost", input, empty(`No valid run recorded usage or timing${invalidRuns ? `; ${plural(invalidRuns, "invalid run")} ${invalidRuns === 1 ? "is" : "are"} not placed` : ""}.`));
  if (!measures.length) return nothing();
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
    // marks has no bar length that a truncated axis would distort. Its ticks are
    // round in the unit shown (0, 1, 2 min, not 0.83 min) and it ends on a
    // labelled tick at or past the largest value, so no run sits beyond the last label.
    const su = m.unit === "seconds" ? secondsUnit(hi) : { div: 1, unit: "" };
    let d0 = 0, d1 = hi || 1, lin: number[] = [];
    if (!log) {
      const pad = (hi - min) * 0.08 || Math.abs(hi) * 0.05 || 1;
      lin = axisTicks((min > (hi - min) * 1.5 ? min - pad : 0) / su.div, hi / su.div, 4).map(t => Number((t * su.div).toPrecision(12)));
      if (lin.length >= 2) { d0 = lin[0]; d1 = lin[lin.length - 1]; }
    }
    const x = (v: number) => log ? (Math.log10(Math.max(v, lo)) - Math.log10(lo)) / Math.max(1e-9, Math.log10(hi) - Math.log10(lo)) : (v - d0) / Math.max(1e-12, d1 - d0);
    const fmt = (v: number | null, axis = false) => m.unit === "seconds" ? (axis ? (isNum(v) ? `${fmtNum(v / su.div)} ${su.unit}` : "—") : fmtSeconds(v)) : m.unit === "usd" ? fmtUsd(v) : fmtNum(v);
    const ticks = log ? logTicks(lo, hi, 4) : lin.filter(t => t >= d0 - 1e-9 && t <= d1 + 1e-9);
    const rowsHtml = arms.map(a => {
      const runs = valid.filter(r => r.arm === a && isNum(m.get(r)));
      const invalidHere = data.runs.filter(r => r.arm === a && r.passed === null).length;
      if (!runs.length && !invalidHere) return "";
      const vals = runs.map(r => m.get(r)!).sort((p, q) => p - q), md = median(vals);
      const shown = runs.filter(r => !log || m.get(r)! > 0), atZero = runs.length - shown.length;
      // trial.py's differences read input_tokens alone; where cached input is added back here, they would describe another figure.
      // pct_vs_baseline holds fractions (0.5 is +50%), as summary.md formats them; fmtDelta takes percent.
      const delta = data.baseline && a !== data.baseline && !(m.id === "input_tokens" && m.note) ? num(data.pct_vs_baseline?.[a]?.[m.id === "seconds" ? "seconds_mean" : m.id === "commands" ? "commands_mean" : m.id]?.median) : null;
      const dots = shown.map((r, j) => {
        const o = outcomeOf(r), v = m.get(r)!, why = o === "fail" ? causePhrase(r, data) : "";
        return `<button type="button" class="av-dot av-dot--${o}"${attrs({ "data-run": ctx.runIndex.get(r), style: `--x:${pos(x(v))};--j:${(j % 7) - 3}`, title: `${ctx.arms.label(a)} · ${caseLabel(ctx, r.scenario)} r${num(r.repeat) ?? "?"}: ${fmt(v)} · ${outcomeLabel[o]}${why ? ` · ${why}` : ""}`, "aria-label": `${ctx.arms.label(a)}, ${caseLabel(ctx, r.scenario)} repeat ${num(r.repeat) ?? "?"}: ${fmt(v)}, ${outcomeLabel[o]}${why ? `, ${why}` : ""}` })}></button>`;
      }).join("");
      const q1 = quantile(vals, .25), q3 = quantile(vals, .75);
      const iqr = q1 !== null && q3 !== null && (!log || q1 > 0) ? `<span class="av-iqr" style="--lo:${pos(x(q1))};--hi:${pos(x(q3))}"></span>` : "";
      const mdMark = md !== null && (!log || md > 0) ? `<span class="av-median" style="--x:${pos(x(md))}"></span>` : "";
      return `<div class="av-strip-row" data-arm="${esc(a)}" style="--c:${ctx.arms.color(a)}"><div class="av-strip-label">${ctx.arms.tag(a, { id: false })}</div><div class="av-strip-track">${iqr}${mdMark}${dots}</div><div class="av-strip-num">${md !== null ? `<span class="av-strong">${fmt(md)}</span><span class="av-muted">median</span>` : '<span class="av-muted">no valid runs</span>'}${delta !== null ? `<span class="av-delta" title="median across cases of the per-case difference from ${esc(data.baseline!)}">${fmtDelta(delta * 100)}</span>` : ""}${atZero ? `<span class="av-zero" title="A log scale cannot place zero">${atZero} at 0</span>` : ""}${invalidHere ? `<span class="av-zero" title="Invalid runs are not placed on this axis">${outcomeMark("invalid")} ${invalidHere} not shown</span>` : ""}</div></div>`;
    }).join("");
    // A label aligns to its tick, and only one at the plot's edge is pulled inside it.
    const tickClass = (at: number) => at <= 0.03 ? ' class="av-tick--start"' : at >= 0.97 ? ' class="av-tick--end"' : "";
    const axis = `<div class="av-strip-axis" aria-hidden="true"><span></span><div class="av-strip-ticks">${ticks.map(t => `<span${tickClass(x(t))} style="--x:${pos(x(t))}">${fmt(t, true)}</span>`).join("")}</div><span></span></div>`;
    return `<div class="av-strip-panel"><h4 class="av-strip-title">${esc(m.label)}${m.note ? ` <span class="av-muted">· ${esc(m.note)}</span>` : ""}${log ? ' <span class="av-muted">· log scale</span>' : d0 > 0 ? ' <span class="av-muted">· axis starts at ' + esc(fmt(d0, true)) + "</span>" : ""}</h4>${rowsHtml}${axis}</div>`;
  }).filter(Boolean).join("");
  if (!panels) return nothing();
  // The dots take their arm's color, so the key shows fill in a neutral ink rather than the pass and fail colors.
  const legend = `<p class="av-legend"><span><span class="av-dot-key av-dot-key--pass" aria-hidden="true"></span>one valid run: filled, passed</span><span><span class="av-dot-key av-dot-key--fail" aria-hidden="true"></span>hollow, failed</span>${arms.length > 1 ? "<span>color: the run's arm</span>" : ""}<span><span class="av-legend-iqr"></span>middle half</span><span><span class="av-legend-median"></span>median</span>${invalidRuns ? `<span>${outcomeMark("invalid")}invalid runs are counted, not placed</span>` : ""}${data.baseline ? `<span>Δ vs ${esc(ctx.arms.label(data.baseline))}: median per-case difference</span>` : ""}</p>`;
  return frame("cost", input, legend + `<div class="av-strips">${panels}</div>`);
}

// ------------------------------------------------------------------ invalid

export function invalid(input: FrameInput, ctx: RenderContext): string {
  const data = trialOf(ctx, "invalid");
  const bad = data.runs.filter(r => r.passed === null);
  if (!bad.length) return frame("invalid", input, `<p class="av-allclear">${outcomeMark("pass")}Every run finished with a valid result.</p>`);
  const by = new Map<string, TrialRun[]>();
  for (const r of bad) { const k = String(r.invalid_reason || r.status || "unknown"); by.set(k, [...(by.get(k) || []), r]); }
  const groups = [...by.entries()].sort((a, b) => b[1].length - a[1].length).map(([reason, runs]) => {
    const why = invalidReason(reason);
    const perArm = new Map<string, number>();
    for (const r of runs) perArm.set(r.arm, (perArm.get(r.arm) || 0) + 1);
    const chips = [...perArm.entries()].sort((a, b) => b[1] - a[1] || ctx.arms.index(a[0]) - ctx.arms.index(b[0])).map(([a, n]) => `<span class="av-inv-arm">${ctx.arms.tag(a, { id: false })}<b>${n}</b></span>`).join("");
    const excerpt = typeof runs[0]?.final_message_excerpt === "string" ? runs[0].final_message_excerpt : "";
    const sample = excerpt ? `<p class="av-inv-sample"><span class="av-eyebrow">First message</span> ${esc(clip(excerpt, 220))}</p>` : "";
    const marks = runs.map(r => { const label = `Invalid run: ${caseLabel(ctx, r.scenario)}, ${ctx.arms.label(r.arm)}, repeat ${num(r.repeat) ?? "?"} · ${reason}`; return `<button type="button" class="av-run av-run--invalid"${attrs({ "data-run": ctx.runIndex.get(r), title: label, "aria-label": label })}></button>`; }).join("");
    return `<div class="av-inv-group"><div class="av-inv-head"><code class="av-inv-reason">${esc(reason)}</code><span class="av-inv-count">${plural(runs.length, "run")}</span></div><p class="av-inv-gloss">${inline(why.text)}</p><p class="av-inv-remedy"><span class="av-eyebrow">Remedy</span> ${inline(why.remedy)}</p><div class="av-inv-arms">${chips}</div>${sample}<div class="av-tap-marks av-inv-marks">${marks}</div></div>`;
  }).join("");
  const share = bad.length / Math.max(1, data.runs.length);
  return frame("invalid", { ...input, description: input.description ?? `${bad.length} of ${data.runs.length} runs (${fmtPct(share)}) produced no valid result. They are excluded from every rate in this report and never counted as failures. Each reason below says what happened and what would give those runs a result.` }, `<div class="av-inv">${groups}</div>`);
}

// ------------------------------------------------------------------ ledger

/** A time column in one format: seconds under a minute, otherwise m:ss (or h:mm:ss). */
function clock(max: number): { head: string; fmt: (s: number | null) => string } {
  if (!(max >= 60)) return { head: "Time", fmt: fmtSeconds };
  const two = (n: number) => String(n).padStart(2, "0");
  return {
    head: max >= 3600 ? "Time (h:mm:ss)" : "Time (m:ss)",
    fmt: s => {
      if (!isNum(s) || s < 0) return "—";
      const t = Math.round(s), h = Math.floor(t / 3600), m = Math.floor((t % 3600) / 60), sec = t % 60;
      return max >= 3600 ? `${h}:${two(m)}:${two(sec)}` : `${Math.floor(t / 60)}:${two(sec)}`;
    },
  };
}

export type LedgerInput = FrameInput;
export function ledger(input: LedgerInput, ctx: RenderContext): string {
  const data = trialOf(ctx, "ledger");
  if (!data.runs.length) return frame("ledger", input, empty("No runs."));
  const axes = trialAxes(data);
  const tokens = costMeasures(data).find(m => m.id === "output_tokens");
  const time = clock(Math.max(0, ...data.runs.map(r => num(r.seconds) ?? 0)));
  const reason = (r: TrialRun) => {
    const c = causeOf(r, data);
    if (c.invalid) { const w = invalidReason(c.invalid); return `<span${attrs({ title: w.text.replace(/`/g, "") })}><code class="av-why-code">${esc(c.invalid)}</code> ${inline(w.text)}</span>`; }
    // Judge reasons mark names as `code`, as the drawer shows them.
    if (outcomeOf(r) === "pass") return `<span>${inline(clip(String(r.judge?.reason || ""), 240))}</span>`;
    const chips = c.checks.slice(0, 3).map(n => `<span class="av-why-chip">✕ ${esc(n)}</span>`).join("") + (c.checks.length > 3 ? `<span class="av-why-chip av-why-chip--more">+${c.checks.length - 3}</span>` : "");
    const text = c.judge !== null ? `${c.judge ? `judge: ${c.judge}` : "judge said fail"}` : c.checks.length ? "" : c.text || "no recorded cause";
    return `<span${attrs({ title: [c.checks.length ? `failed: ${c.checks.join(", ")}` : "", text].filter(Boolean).join(" · ") || undefined })}>${chips}${text ? `${chips ? " " : ""}${inline(clip(text, 240))}` : ""}</span>`;
  };
  const rows = data.runs.map((r, i) => {
    const o = outcomeOf(r), tk = tokens ? num(tokens.get(r)) : null, sec = num(r.seconds);
    return `<tr${attrs({ "data-run": i, "data-arm": r.arm, "data-case": r.scenario, "data-outcome": o, tabindex: 0 })}><td class="av-num">${i + 1}</td><td>${outcomeBadge(o)}</td><td>${esc(caseLabel(ctx, r.scenario))}</td><td>${ctx.arms.tag(r.arm, { id: false })}</td><td class="av-num">${esc(num(r.repeat) ?? "")}</td><td>${r.judge?.verdict ? `<span class="av-judge av-judge--${esc(r.judge.verdict)}">${esc(r.judge.verdict)}</span>` : '<span class="av-muted">—</span>'}</td>${tokens ? `<td class="av-num" data-sort="${tk ?? -1}">${fmtNum(tk)}</td>` : ""}<td class="av-num" data-sort="${sec ?? -1}">${time.fmt(sec)}</td><td class="av-why">${reason(r)}</td></tr>`;
  }).join("");
  const opts = (items: string[], label: (x: string) => string) => items.map(x => `<option value="${esc(x)}">${esc(label(x))}</option>`).join("");
  const counts = tally(data.runs);
  const filters = `<div class="av-ledger-tools" data-av-ledger-tools hidden>
<div class="av-seg" role="group" aria-label="Outcome"><button type="button" aria-pressed="true" data-outcome="">All <span>${counts.runs}</span></button><button type="button" aria-pressed="false" data-outcome="pass">${outcomeMark("pass")}Passed <span>${counts.pass}</span></button><button type="button" aria-pressed="false" data-outcome="fail">${outcomeMark("fail")}Failed <span>${counts.fail}</span></button><button type="button" aria-pressed="false" data-outcome="invalid">${outcomeMark("invalid")}Invalid <span>${counts.invalid}</span></button></div>
<label class="av-field"><span>Arm</span><select data-filter="arm"><option value="">All arms</option>${opts(axes.arms, a => ctx.arms.label(a))}</select></label>
<label class="av-field"><span>Case</span><select data-filter="case"><option value="">All cases</option>${opts(axes.cases, c => caseLabel(ctx, c))}</select></label>
<label class="av-field av-field--grow"><span>Search</span><input type="search" data-filter="text" placeholder="Search reasons and causes"></label>
<output class="av-ledger-count" aria-live="polite"></output></div>`;
  const head = `<thead><tr><th scope="col" data-sortable="num" class="av-num">#</th><th scope="col" data-sortable>Outcome</th><th scope="col" data-sortable>Case</th><th scope="col" data-sortable>Arm</th><th scope="col" data-sortable="num" class="av-num">Rep</th><th scope="col" data-sortable>Judge</th>${tokens ? '<th scope="col" data-sortable="num" class="av-num">Tokens out</th>' : ""}<th scope="col" data-sortable="num" class="av-num">${time.head}</th><th scope="col">Why</th></tr></thead>`;
  return frame("ledger", { ...input, description: input.description ?? "Every run, filterable. Why says what failed (the required checks that did not hold, or the judge's reason) and why an invalid run has no result. Select a row for the run's checks, judge reason, output excerpt and the location of its native record." }, `${filters}<div class="av-scroll-x av-ledger-wrap"><table class="av-ledger">${head}<tbody>${rows}</tbody></table></div>`);
}

// ------------------------------------------------------------------ plan

/** The arms' recorded settings and each case's definition: the plan as run.
 * The setup view is the reader-facing account; this stays for callers that want the raw plan. */
export function plan(input: FrameInput, ctx: RenderContext): string {
  const data = trialOf(ctx, "plan");
  const armIds = trialAxes(data).arms.slice().sort(byIdentity(ctx)), settings = data.plan?.arms || {};
  const skip = new Set(["instructions_text", "instructions_truncated", "artifact_text", "artifact_truncated"]);
  const present = [...new Set(armIds.flatMap(a => Object.keys(settings[a] || {})))].filter(k => !skip.has(k) && armIds.some(a => settings[a]?.[k] !== undefined && settings[a]?.[k] !== null));
  const cellText = (k: string, v: unknown) => v === undefined || v === null ? '<span class="av-muted">—</span>' : /sha256$/.test(k) && typeof v === "string" ? `<code title="${esc(v)}">${esc(v.slice(0, 10))}</code>` : `<code>${esc(typeof v === "string" ? v : JSON.stringify(v))}</code>`;
  const armTable = `<div class="av-scroll-x"><table class="av-table av-plan-arms"><thead><tr><th scope="col">Arm</th>${present.map(k => `<th scope="col">${esc(k.replace(/_sha256$/, " digest").replace(/_/g, " "))}</th>`).join("")}</tr></thead><tbody>${armIds.map(a => `<tr><th scope="row">${ctx.arms.tag(a)}${ctx.arms.note(a) ? `<span class="av-ladder-note">${esc(ctx.arms.note(a)!)}</span>` : ""}</th>${present.map(k => `<td>${cellText(k, settings[a]?.[k])}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
  const ran = new Set(data.runs.map(r => r.scenario));
  const cases = (data.plan?.scenarios || []).filter(s => s && ran.has(s.name)).map(s => {
    const q = judgeQuestion(s), when = judgePassWhen(s), req = strings(s.required) || [], fu = strings(s.followups) || [];
    return `<details class="av-case"><summary><span class="av-case-name">${esc(caseLabel(ctx, s.name))}</span>${caseLabel(ctx, s.name) !== s.name ? `<code>${esc(s.name)}</code>` : ""}<span class="av-case-tags">${req.length ? `<span class="av-chip av-chip--req">${plural(req.length, "required check")}</span>` : ""}${q ? '<span class="av-chip">judged</span>' : ""}${fu.length ? `<span class="av-chip">${plural(fu.length, "follow-up")}</span>` : ""}</span></summary><div class="av-case-body">${typeof s.description === "string" && s.description ? `<h5>What it is</h5><p class="av-case-desc">${esc(s.description)}${s.description_truncated ? " …" : ""}</p>` : ""}${s.prompt ? `<h5>Prompt</h5><pre class="av-pre">${esc(s.prompt)}</pre>` : ""}${fu.map((f, i) => `<h5>Follow-up ${i + 1}</h5><pre class="av-pre">${esc(f)}</pre>`).join("")}${q ? `<h5>Judge question</h5><pre class="av-pre">${esc(q)}</pre>` : ""}${when ? `<h5>The judge passes it when</h5><pre class="av-pre">${esc(when)}</pre>` : ""}${req.length ? `<h5>Required checks</h5><p>${req.map(c => `<code>${esc(c)}</code>`).join(" ")}</p>` : ""}</div></details>`;
  }).join("");
  const judge = data.plan?.judge ? `<p class="av-plan-judge"><span class="av-eyebrow">Judge</span> ${Object.entries(data.plan.judge).filter(([k]) => ["executor", "model", "effort"].includes(k)).map(([k, v]) => `${esc(k)} <code>${esc(v)}</code>`).join(" · ")}</p>` : "";
  const dir = data.run_directory ? `<p class="av-plan-judge"><span class="av-eyebrow">Run directory</span> <code>${esc(displayPath(data.run_directory))}</code></p>` : "";
  return frame("plan", input, `${armTable}${judge}${dir}<div class="av-cases">${cases}</div>`);
}
