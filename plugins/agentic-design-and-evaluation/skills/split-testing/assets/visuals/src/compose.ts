/** Compose a report specification from a trial's data and an optional
 * narrative. The composition is a starting order, not a fixed page: every
 * section is an ordinary spec section a caller can drop, reorder or extend.
 *
 * The order follows the reader who commissioned the trial: the verdict and the
 * rule fixed before results, what was compared, how each arm did, what each
 * case asked and how it went, why runs failed, then checks, pairwise
 * judgments, cost, invalid runs and the ledger. Sections adapt to the trial's
 * shape: with one arm the cases view carries the results and the checks
 * section keeps only what the dossiers do not show; case variants are paired
 * once and every view pairs the same cases; a section with nothing to show is
 * left out, and no view repeats another. The run grid ("grid") is drawn only
 * when a narrative's include names it, since the case dossiers already place
 * every run. */
import { fmtInt, fmtPct } from "./core";
import type { ArmSpec, BlockSpec, ReportSpec, SectionSpec } from "./model";
import { CasePair, caseChecks, casePairs, checkTable, costMeasures, displayPath, pairedOrder, repeatRange, ruleMentions, tally, TrialReport, trialAxes } from "./trial-model";
import type { VerdictInput } from "./blocks/trial";
import { validateNarrative } from "./validate";
import type { Problem } from "./validate";

export interface Narrative {
  title?: string;
  /** The practical question the trial answers, in the reader's words. */
  question?: string;
  summary?: string | string[];
  kicker?: string;
  /** The decision, written by whoever applied the trial's rule. */
  decision?: Omit<VerdictInput, "rule" | "title">;
  /** Labels and identity order for arms. */
  arms?: ArmSpec[] | Record<string, { label?: string; note?: string }>;
  /** Readable labels for cases (scenarios). */
  cases?: Record<string, string>;
  /** Groups of arms that received identical material (calibration copies). */
  identical?: string[][];
  /** Named sets of cases (conditions, variants, rounds): each gets its own interval view, and the run grid is sectioned by them. */
  groups?: Array<{ label: string; cases: string[]; note?: string }>;
  /** Case variants, as [base, variant] or {base, variant, label}. Without this field, variants are found in
   * the plan by content (same prompt, judge, required checks and artifact; more follow-up turns); [] turns that off. */
  pairs?: Array<[string, string] | { base: string; variant: string; label?: string }>;
  /** Reference arm for the interval and difference views; defaults to the trial's baseline. */
  baseline?: string;
  /** The difference the decision rule asks for, drawn on the difference-from-baseline view: a share such as
   * 0.15 for +15 points, or {value, label}. */
  threshold?: number | { value: number; label?: string };
  /** Default sections to keep, by id (see SECTION_IDS; "plan" is accepted for "setup"). */
  include?: string[];
  exclude?: string[];
  /** Extra sections, placed after the named default section or at the end. */
  sections?: Array<SectionSpec & { after?: string }>;
  /** Extra blocks appended to a default section, keyed by its id. */
  append?: Record<string, BlockSpec[]>;
  footer?: string;
}

/** The default sections' ids, in reading order. A section with nothing to show for a trial is left out;
 * "grid" is drawn only when include names it. */
export const SECTION_IDS = ["verdict", "setup", "arms", "cases", "grid", "failures", "checks", "pairwise", "cost", "invalid", "runs"] as const;
/** Earlier ids that still name a default section. */
const ALIASES: Record<string, string> = { plan: "setup" };
const alias = (id: unknown) => { const k = String(id); return ALIASES[k] || k; };

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
/** A date range in words (UTC), such as "4–5 Oct 2026"; unreadable dates are shown as written. */
function fmtDates(first?: unknown, last?: unknown): string | null {
  const read = (v: unknown) => { if (typeof v !== "string" || !v) return null; const d = new Date(v); return Number.isNaN(d.getTime()) ? null : d; };
  const a = read(first), b = read(last) || a;
  if (!a || !b) return typeof first === "string" && first ? String(first) : null;
  const day = (d: Date) => d.getUTCDate(), mon = (d: Date) => MONTHS[d.getUTCMonth()], yr = (d: Date) => d.getUTCFullYear();
  if (a.toISOString().slice(0, 10) === b.toISOString().slice(0, 10)) return `${day(a)} ${mon(a)} ${yr(a)}`;
  if (yr(a) === yr(b) && mon(a) === mon(b)) return `${day(a)}–${day(b)} ${mon(a)} ${yr(a)}`;
  if (yr(a) === yr(b)) return `${day(a)} ${mon(a)} – ${day(b)} ${mon(b)} ${yr(a)}`;
  return `${day(a)} ${mon(a)} ${yr(a)} – ${day(b)} ${mon(b)} ${yr(b)}`;
}

const isObject = (v: unknown): v is Record<string, unknown> => !!v && typeof v === "object" && !Array.isArray(v);
const strings = (v: unknown): string[] => Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : [];

export function trialReport(data: TrialReport, narrativeIn: Narrative = {}): ReportSpec {
  if (!data || !Array.isArray(data.runs)) throw new TypeError("trialReport needs the JSON that `trial.py report RUN_DIR` writes.");
  const narrative: Narrative = isObject(narrativeIn) ? narrativeIn : {};
  let problems: Problem[] = [];
  try { problems = (validateNarrative(narrative, data) || []).filter(p => isObject(p)); }
  catch (error) { problems = [{ level: "warning", where: "narrative", message: `The narrative could not be checked: ${error instanceof Error ? error.message : String(error)}` }]; }

  const axes = trialAxes(data);
  const rawArms: unknown[] = Array.isArray(narrative.arms) ? narrative.arms : isObject(narrative.arms) ? Object.entries(narrative.arms).map(([id, v]) => Object.assign({ id }, isObject(v) ? v : {}, { id })) : [];
  const armSpecs = rawArms.filter((a): a is ArmSpec => isObject(a) && typeof a.id === "string");
  // Narrative arms set the identity order, but only arms that ran enter it: a misspelled id must not shift every color.
  const order = [...new Set([...armSpecs.map(a => a.id).filter(id => axes.arms.includes(id)), ...axes.arms])];
  const arms: ArmSpec[] = order.map(id => armSpecs.find(a => a.id === id) || { id });
  const label = (id: string) => armSpecs.find(a => a.id === id)?.label || id;
  const all = tally(data.runs);
  const range = repeatRange(data);
  const judge = isObject(data.plan?.judge) ? data.plan!.judge! : null;
  const judgeModel = judge ? String(judge.model || judge.executor || "judge") : null;
  const judgeDetail = judge ? [judge.executor, judge.effort ? `${judge.effort} effort` : ""].filter(x => typeof x === "string" && x && x !== judge.model).join(" · ") : "";
  const judgeName = judgeModel ? `${judgeModel}${typeof judge!.effort === "string" && judge!.effort ? ` at ${judge!.effort} effort` : ""}${typeof judge!.executor === "string" && judge!.executor && judge!.executor !== judgeModel ? ` (${judge!.executor})` : ""}` : null;
  const baseline = [narrative.baseline, data.baseline].find((b): b is string => typeof b === "string" && axes.arms.includes(b));
  const threshold = typeof narrative.threshold === "number" || isObject(narrative.threshold) ? narrative.threshold : undefined;
  const identical = (Array.isArray(narrative.identical) ? narrative.identical : []).map(g => [...new Set(strings(g).filter(a => axes.arms.includes(a)))]).filter(g => g.length > 1);
  const groups = (Array.isArray(narrative.groups) ? narrative.groups : []).filter(g => isObject(g) && typeof g.label === "string")
    .map(g => ({ label: g.label, cases: strings(g.cases).filter(c => axes.cases.includes(c)), ...(typeof g.note === "string" ? { note: g.note } : {}) })).filter(g => g.cases.length);
  const detected = casePairs(data);
  const pairs: CasePair[] = Array.isArray(narrative.pairs)
    ? narrative.pairs.map(p => Array.isArray(p) ? { base: p[0], variant: p[1] } : isObject(p) ? p : null)
      .filter((p): p is { base: string; variant: string; label?: string } => !!p && typeof p.base === "string" && typeof p.variant === "string" && p.base !== p.variant && axes.cases.includes(p.base) && axes.cases.includes(p.variant))
      .filter((p, i, all) => all.findIndex(q => q.variant === p.variant) === i)
      .map(p => { const found = detected.find(d => d.base === p.base && d.variant === p.variant); return { base: p.base, variant: p.variant, label: typeof p.label === "string" && p.label ? p.label : found?.label || "variant", ...(found?.note ? { note: found.note } : {}) }; })
    : detected;
  const cases = pairedOrder(axes.cases, pairs);
  const multiArm = axes.arms.length > 1, anyValid = all.valid > 0;
  // A variant is a second version of a case, not another case: the trial's size counts base cases, and names the versions.
  const bases = [...new Set(pairs.map(p => p.base))], variants = pairs.map(p => p.variant);
  const allPaired = pairs.length > 0 && axes.cases.every(c => bases.includes(c) || variants.includes(c));
  const baseCount = axes.cases.length - new Set(variants).size;
  const vLabel = new Set(pairs.map(p => p.label)).size === 1 ? pairs[0].label : "more turns";
  const version = /^\+\s*/.test(vLabel) ? `with ${vLabel.replace(/^\+\s*/, "")} added` : vLabel === "more turns" ? "with more turns" : `as a variant (${vLabel})`;
  const rule = typeof data.plan?.decision_rule === "string" && data.plan.decision_rule.trim() ? data.plan.decision_rule : undefined;

  const reasons = new Map<string, number>();
  for (const r of data.runs) if (r.passed === null) { const k = String(r.invalid_reason || r.status || "unknown"); reasons.set(k, (reasons.get(k) || 0) + 1); }
  const breakdown = [...reasons.entries()].sort((a, b) => b[1] - a[1]).map(([k, n]) => `\`${k}\` ×${n}`).join(", ");
  const alert = all.runs && !anyValid
    ? { text: `All ${fmtInt(all.runs)} run${all.runs === 1 ? " is" : "s are"} invalid (${breakdown}), so no pass rate can be given. Invalid runs are not failures.`, href: "#invalid", link: "What happened, and what would fix it" }
    : all.invalid && all.invalid / all.runs >= 0.2
      ? { text: `${fmtInt(all.invalid)} of ${fmtInt(all.runs)} runs produced no valid result (${breakdown}). They are excluded from every rate and never counted as failures.`, href: "#invalid", link: "Invalid runs" }
      : undefined;

  const appended = new Map<string, BlockSpec[]>();
  for (const [k, blocks] of Object.entries(isObject(narrative.append) ? narrative.append : {})) if (Array.isArray(blocks)) appended.set(alias(k), [...(appended.get(alias(k)) || []), ...blocks]);
  const sections: Array<{ key: string; section: SectionSpec }> = [];
  const add = (key: string, s: SectionSpec) => sections.push({ key, section: { ...s, id: key, blocks: [...s.blocks, ...(appended.get(key) || [])] } });

  // ---------------------------------------------------------------- verdict
  const decision = isObject(narrative.decision) ? narrative.decision : null;
  const verdict: BlockSpec = decision
    ? { type: "verdict", ...decision, rule, ...(alert ? { alert } : {}) }
    : {
        type: "verdict", verdict: "none",
        headline: all.runs && !anyValid ? "No run produced a valid result, and no decision was recorded." : "No decision was recorded with these results.",
        detail: rule ? `The rule below was fixed before the results.${anyValid ? " The counts it names follow it; the sections below hold the rest of the evidence." : ""}` : `The plan states no decision rule; the sections below show what was ${anyValid ? "observed" : "recorded"}.`,
        rule, mentions: ruleMentions(rule, [...axes.cases, ...axes.arms]), pairs, ...(alert ? { alert } : {}),
      };
  add("verdict", {
    title: "Verdict", label: "Verdict", blocks: [verdict, {
      type: "figures", items: [
        { value: all.runs, label: "Runs" },
        { value: all.valid, label: "Valid", note: all.runs ? fmtPct(all.valid / all.runs) : undefined, tone: anyValid ? "pass" : "warn" },
        { value: all.invalid, label: "Invalid", note: all.invalid ? "excluded, not failures" : "none", tone: all.invalid ? "warn" : "neutral" },
        ...(!multiArm && anyValid ? [{ value: fmtPct(all.rate), label: "Pass rate", note: `${all.pass} of ${all.valid} valid${all.interval ? ` · 95% ${fmtPct(all.interval[0])}–${fmtPct(all.interval[1])}` : ""}` }] : []),
        { value: axes.arms.length, label: axes.arms.length === 1 ? "Arm" : "Arms" },
        { value: baseCount, label: baseCount === 1 ? "Case" : "Cases", note: pairs.length ? `+${pairs.length} variant${pairs.length === 1 ? "" : "s"}: ${axes.cases.length} versions` : undefined },
        { value: range ? (range.min === range.max ? `×${range.max}` : `×${range.min}–${range.max}`) : "—", label: "Repeats", note: range && range.min !== range.max ? "varies by arm or case" : undefined },
        ...(judgeModel ? [{ value: judgeModel, label: "Judge", note: judgeDetail || undefined }] : []),
      ],
    }],
  });

  // ---------------------------------------------------------------- what was compared
  add("setup", {
    title: "What was compared", label: "Setup",
    blocks: [{ type: "setup", arms: order, ...(baseline ? { baseline } : {}), ...(identical.length ? { identical } : {}), pairs: pairs.length ? pairs.map(p => [p.base, p.variant]) : "off" }],
  });

  // ---------------------------------------------------------------- results
  // Variants against their base cases: the comparison a variant trial is about.
  const variantContrast = pairs.length ? [{
    type: "contrast",
    // With one arm the section heading already says this; with several, the block sits among the arm views.
    ...(multiArm ? { title: "Variants against their base cases", description: `Each variant's pass rate minus its base case's, pooled over the ${pairs.length === 1 ? "pair" : `${pairs.length} pairs`}, for all arms together and for each arm.` } : {}),
    a: { label: `Variant (${vLabel})`, cases: pairs.map(p => p.variant) }, b: { label: "Base case", cases: pairs.map(p => p.base) },
    ...(multiArm ? { by: "arm" } : pairs.length > 1 ? { by: "case" } : {}),
  },
  // With several arms the pooled difference is broken down by arm above; pairs that move in opposite directions need their own rows too.
  ...(multiArm && pairs.length > 1 ? [{
    type: "contrast", title: "Each variant against its base case",
    description: "The same difference for each pair, all arms together: a pooled difference can hide pairs that move in opposite directions.",
    a: { label: `Variant (${vLabel})`, cases: pairs.map(p => p.variant) }, b: { label: "Base case", cases: pairs.map(p => p.base) }, by: "case",
  }] : [])] : [];
  const tie = { ...(identical.length ? { identical } : {}), ...(baseline ? { baseline } : {}) };
  if (anyValid && multiArm) {
    // Pooling a base case with its variant blurs the comparison; with every case paired, the pooled ladder gives way to one per side.
    add("arms", {
      title: "Results by arm", label: "Arms",
      lead: `Each arm pooled over ${allPaired ? "the cases in each set" : "every case it ran"}. Intervals are 95% Wilson intervals over valid runs; invalid runs are counted beside them, never as failures. Pooling weights cases by their valid runs, so read the cases below before trusting a pooled difference.${identical.length ? " Identical arms received the same material: the distance between them is what chance alone produces." : ""}`,
      blocks: [
        ...(allPaired ? [] : [{ type: "ladder", ...tie, ...(groups.length || pairs.length ? { title: "All cases" } : {}) }]),
        ...(pairs.length ? [
          { type: "ladder", title: "Base cases", description: allPaired ? `The ${bases.length === 1 ? "case" : `${bases.length} cases`} as written.` : `The ${bases.length === 1 ? "case" : `${bases.length} cases`} that also ran as a variant, as written.`, cases: bases, ...tie },
          { type: "ladder", title: `Variants (${vLabel})`, description: `The same ${bases.length === 1 ? "case" : "cases"}, each run with ${vLabel.replace(/^\+\s*/, "")} added.`, cases: pairs.map(p => p.variant), ...tie },
        ] : []),
        ...groups.map(g => ({ type: "ladder", title: g.label, ...(g.note ? { description: g.note } : {}), cases: g.cases, ...tie })),
        ...(baseline || identical.length ? [{ type: "contrast", title: baseline ? `Difference from ${label(baseline)}` : "Difference between identical arms", arms: order, ...tie, ...(baseline && threshold !== undefined ? { threshold } : {}) }] : []),
        ...variantContrast,
      ],
    });
  } else if (anyValid && variantContrast.length) {
    // One arm: the cases view carries the per-case rates; a variant trial also gets its difference here.
    add("arms", {
      title: "Variants against base cases", label: "Variants",
      lead: `The same ${pairs.length === 1 ? "case" : "cases"} run as written and with more turns. The difference is the variant's pass rate minus its base case's, ${pairs.length === 1 ? "" : `pooled over the ${pairs.length} pairs and then for each pair, `}with a 95% interval; invalid runs are counted beside the rates, never as failures.`,
      blocks: variantContrast,
    });
  }
  add("cases", {
    title: "Case by case", label: "Cases",
    lead: `What each case asked, what counted as a pass, and how it went${multiArm ? " for each arm" : ""}.`,
    // The composition decides the pairing once, so every view pairs the same cases. With no valid run, an overview would only repeat "no valid runs".
    blocks: [{ type: "cases", cases, arms: order, ...(groups.length ? { groups } : {}), pairs: pairs.length ? pairs : "off", ...(anyValid ? {} : { index: false }) }],
  });
  const include = Array.isArray(narrative.include) ? narrative.include.map(alias) : null;
  // The case dossiers place every run by case and arm, so the run grid would repeat them; a narrative can still ask for it.
  if (anyValid && include?.includes("grid"))
    add("grid", {
      title: "Every run", label: "Every run",
      lead: "One mark per run, by case and arm. A difference that lives in one case reads differently from one spread across all of them.",
      blocks: [{ type: "tapestry", ...(groups.length ? { groups } : {}), ...(pairs.length ? { pairs } : {}) }],
    });
  if (all.fail)
    add("failures", {
      title: "Why runs failed", label: "Failures",
      blocks: [{ type: "failures", cases, arms: order }],
    });
  if (anyValid && multiArm && (checkTable(data, axes.arms).length || data.runs.some(r => r.judge?.verdict === "pass" || r.judge?.verdict === "fail")))
    add("checks", { title: "Checks", label: "Checks", lead: "How often each check held in each arm, over valid runs. Required checks decide a run's pass; the others are recorded measures the plan does not require, so they never decide a pass, whatever their value.", blocks: [{ type: "checks", ...(pairs.length ? { pairs } : {}) }] });
  else if (anyValid && !multiArm && cases.some(c => caseChecks(data, c, axes.arms).measures.length))
    // One arm: each dossier already shows its required checks and judge, so this section keeps only the measures.
    add("checks", { title: "Recorded measures", label: "Measures", lead: "What each case's checks recorded besides pass and fail, over valid runs: values the plan records but does not require, so they never decide a pass. The required checks and the judge are in each case's dossier above.", blocks: [{ type: "checks", required: false, ...(pairs.length ? { pairs } : {}) }] });
  if (isObject(data.pairwise) && Object.keys(data.pairwise).length)
    add("pairwise", { title: "Pairwise judgments", label: "Pairwise", lead: "A judge saw matched runs side by side in both orders. Only pairs decided the same way in both orders count toward a win rate.", blocks: [{ type: "pairwise" }] });
  if (anyValid && costMeasures(data).length)
    add("cost", { title: "Cost and time", label: "Cost", lead: "Every valid run's usage as its executor reported it. Executors report different fields, so compare like with like.", blocks: [{ type: "cost" }] });
  if (all.invalid)
    add("invalid", { title: "Invalid runs", label: "Invalid", blocks: [{ type: "invalid" }] });
  // The ledger's explanation reads as the section's lead, like every other section's.
  add("runs", { title: "Run ledger", label: "Runs", lead: "Every run, filterable. Why says what failed (the required checks that did not hold, or the judge's reason) and why an invalid run has no result. Select a row for the run's checks, judge reason, output excerpt and the location of its native record.", blocks: [{ type: "ledger", description: "" }] });

  const exclude = (Array.isArray(narrative.exclude) ? narrative.exclude : []).map(alias);
  const kept: Array<{ key: string; section: unknown }> = sections.filter(s => (!include || include.includes(s.key)) && !exclude.includes(s.key));
  for (const extra of Array.isArray(narrative.sections) ? narrative.sections : []) {
    // A malformed entry passes through; renderReport shows it as a visible notice.
    if (!isObject(extra)) { kept.push({ key: "", section: extra }); continue; }
    const { after, ...section } = extra as SectionSpec & { after?: string };
    const at = after !== undefined ? kept.findIndex(s => s.key && s.key === alias(after)) : -1;
    const entry = { key: String(section.id || section.title || ""), section };
    if (at >= 0) kept.splice(at + 1, 0, entry); else kept.push(entry);
  }
  // A link to a section the narrative left out would lead nowhere.
  if (alert && !kept.some(s => s.key === "invalid")) delete (alert as { href?: string }).href;

  const name = typeof data.name === "string" && data.name ? data.name : undefined;
  const armText = order.length === 1 ? `One arm (${label(order[0])})` : order.length <= 4 ? `${order.length} arms (${order.map(label).join(", ")})` : `${order.length} arms`;
  const reps = range ? (range.min === range.max ? `${range.max} repeat${range.max === 1 ? "" : "s"}` : `${range.min}–${range.max} repeats`) : "";
  const caseText = `${baseCount} case${baseCount === 1 ? "" : "s"}${!pairs.length ? "" : allPaired ? `, ${baseCount === 1 ? "run" : "each run"} as written and ${version} (${axes.cases.length} case versions)` : `, ${pairs.length === 1 ? "one" : pairs.length} of them also run ${version} (${axes.cases.length} case versions)`}`;
  // Without a narrative the page has no question of its own; the plan's rule is the one place that says what the trial tested.
  const purpose = rule && !narrative.summary && !narrative.question && !narrative.title ? " What the trial tested is stated only in its decision rule, quoted under Verdict." : "";
  const shape = order.length
    ? `${armText} on ${caseText}${reps ? `, ${reps} each` : ""}: ${fmtInt(all.runs)} run${all.runs === 1 ? "" : "s"}${judgeName ? `, judged by ${judgeName}` : ""}.${purpose}`
    : undefined;
  const ran = isObject(data.ran) ? fmtDates(data.ran.first, data.ran.last) : null;
  const written = fmtDates(data.generated_at);
  return {
    title: [narrative.title, narrative.question, name].find((t): t is string => typeof t === "string" && !!t.trim()) || "Trial results",
    kicker: typeof narrative.kicker === "string" && narrative.kicker ? narrative.kicker : `Split test${name ? ` · ${name}` : ""}`,
    summary: narrative.summary ?? shape,
    meta: [
      ...(narrative.title && narrative.question ? [{ label: "Question", value: String(narrative.question) }] : []),
      // When the runs ran; the footer gives when this report's data were written.
      ...(ran ? [{ label: "Ran", value: ran }] : []),
      ...(typeof data.run_directory === "string" && data.run_directory ? [{ label: "Run directory", value: displayPath(data.run_directory) }] : []),
    ],
    arms, cases: isObject(narrative.cases) ? narrative.cases as Record<string, string> : undefined, trial: data,
    footer: narrative.footer || (written ? `Report data written ${written}. Every view is drawn from the data embedded in this file, and each run names its native record.` : undefined),
    problems,
    sections: kept.map(s => isObject(s.section) ? s.section as unknown as SectionSpec : s.section as SectionSpec),
  };
}
