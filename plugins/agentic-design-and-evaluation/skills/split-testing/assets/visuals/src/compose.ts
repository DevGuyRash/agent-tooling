/** Compose a report specification from a trial's data and an optional
 * narrative. The composition is a starting order, not a fixed page: every
 * section is an ordinary spec section a caller can drop, reorder or extend. */
import { fmtInt, fmtPct } from "./core";
import type { ArmSpec, BlockSpec, ReportSpec, SectionSpec } from "./model";
import { costMeasures, checkTable, tally, TrialReport, trialAxes } from "./trial-model";
import type { VerdictInput } from "./blocks/trial";

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
  /** Reference arm for the interval view; defaults to the trial's baseline. */
  baseline?: string;
  /** Default sections to keep (ids: verdict, arms, cases, checks, pairwise, cost, invalid, runs, plan). */
  include?: string[];
  exclude?: string[];
  /** Extra sections, placed after the named default section or at the end. */
  sections?: Array<SectionSpec & { after?: string }>;
  /** Extra blocks appended to a default section, keyed by its id. */
  append?: Record<string, BlockSpec[]>;
  footer?: string;
}

export function trialReport(data: TrialReport, narrative: Narrative = {}): ReportSpec {
  if (!data || !Array.isArray(data.runs)) throw new TypeError("trialReport needs the JSON that `trial.py report RUN_DIR` writes.");
  const axes = trialAxes(data);
  const armSpecs: ArmSpec[] = Array.isArray(narrative.arms)
    ? narrative.arms
    : Object.entries(narrative.arms || {}).map(([id, v]) => ({ id, ...v }));
  const order = [...armSpecs.map(a => a.id), ...axes.arms.filter(a => !armSpecs.some(s => s.id === a))];
  const arms: ArmSpec[] = order.map(id => armSpecs.find(a => a.id === id) || { id });
  const all = tally(data.runs);
  const repeats = Math.max(0, ...data.runs.map(r => r.repeat ?? 0));
  const judge = data.plan?.judge as Record<string, unknown> | undefined;
  const judgeName = judge ? String(judge.model || judge.executor || "judge") : null;
  const baseline = narrative.baseline || data.baseline;

  const sections: Array<SectionSpec & { key: string }> = [];
  const add = (key: string, s: SectionSpec) => sections.push({ ...s, id: key, key, blocks: [...s.blocks, ...(narrative.append?.[key] || [])] });

  const verdict: BlockSpec = narrative.decision
    ? { type: "verdict", ...narrative.decision, rule: data.plan?.decision_rule }
    : { type: "verdict", verdict: "none", headline: "These are the results; no decision was supplied with them.", detail: data.plan?.decision_rule ? "Apply the rule below to the views that follow." : "The plan states no decision rule.", rule: data.plan?.decision_rule };
  add("verdict", {
    title: "Verdict", label: "Verdict", blocks: [verdict, {
      type: "figures", items: [
        { value: all.runs, label: "Runs" },
        { value: all.valid, label: "Valid", note: all.runs ? fmtPct(all.valid / all.runs) : undefined, tone: "pass" },
        { value: all.invalid, label: "Invalid", note: all.invalid ? "excluded, not failures" : "none", tone: all.invalid ? "warn" : "neutral" },
        { value: axes.arms.length, label: axes.arms.length === 1 ? "Arm" : "Arms" },
        { value: axes.cases.length, label: axes.cases.length === 1 ? "Case" : "Cases" },
        { value: repeats ? `×${repeats}` : "—", label: "Repeats" },
        ...(judgeName ? [{ value: judgeName, label: "Judge" }] : []),
      ],
    }],
  });
  add("arms", {
    title: "Pass rate by arm", label: "Arms",
    lead: `Each arm pooled over every case it ran. Intervals are 95% Wilson intervals over valid runs; invalid runs are counted beside them, never as failures. Pooling weights cases by their valid runs, so read the cases below before trusting a pooled difference.${narrative.identical?.length ? " Identical arms received the same material: the distance between them is what chance alone produces." : ""}`,
    blocks: [
      { type: "ladder", identical: narrative.identical, baseline, ...(narrative.groups?.length ? { title: "All cases" } : {}) },
      ...(narrative.groups || []).map(g => ({ type: "ladder", title: g.label, description: g.note, cases: g.cases, identical: narrative.identical, baseline })),
    ],
  });
  add("cases", {
    title: "Every run, by case", label: "Cases",
    lead: "One mark per run. A difference that lives in one case reads differently from one spread across all of them.",
    blocks: [{ type: "tapestry", groups: narrative.groups }],
  });
  if (checkTable(data, axes.arms).length || data.runs.some(r => r.judge?.verdict === "pass" || r.judge?.verdict === "fail"))
    add("checks", { title: "Checks", label: "Checks", lead: "How often each recorded check held, over valid runs. Required checks decide a run's pass; the others are measures.", blocks: [{ type: "checks" }] });
  if (Object.keys(data.pairwise || {}).length)
    add("pairwise", { title: "Pairwise judgments", label: "Pairwise", lead: "A judge saw matched runs side by side in both orders. Only pairs decided the same way in both orders count toward a win rate.", blocks: [{ type: "pairwise" }] });
  if (costMeasures(data).length)
    add("cost", { title: "Cost and time", label: "Cost", lead: "Every run's usage as its executor reported it. Executors report different fields, so compare like with like.", blocks: [{ type: "cost" }] });
  add("invalid", { title: "Invalid runs", label: "Invalid", blocks: [{ type: "invalid" }] });
  add("runs", { title: "Run ledger", label: "Runs", blocks: [{ type: "ledger" }] });
  add("plan", { title: "What was compared", label: "Plan", lead: "The arms' recorded settings and digests, and each case's prompt, judge question and required checks.", blocks: [{ type: "plan" }] });

  let kept = sections.filter(s => (!narrative.include || narrative.include.includes(s.key)) && !(narrative.exclude || []).includes(s.key));
  for (const extra of narrative.sections || []) {
    const { after, ...section } = extra;
    const at = after ? kept.findIndex(s => s.key === after) : -1;
    const entry = { ...section, key: section.id || section.title };
    if (at >= 0) kept.splice(at + 1, 0, entry); else kept.push(entry);
  }
  const name = data.name || undefined;
  return {
    title: narrative.title || narrative.question || name || "Trial results",
    kicker: narrative.kicker || `Split test${name ? ` · ${name}` : ""}`,
    summary: narrative.summary,
    meta: [
      ...(narrative.title && narrative.question ? [{ label: "Question", value: narrative.question }] : []),
      { label: "Runs", value: `${fmtInt(all.runs)} · ${fmtInt(all.valid)} valid` },
      ...(judgeName ? [{ label: "Judge", value: judgeName }] : []),
      ...(data.run_directory ? [{ label: "Run directory", value: data.run_directory }] : []),
    ],
    arms, cases: narrative.cases, trial: data, footer: narrative.footer,
    sections: kept.map(({ key: _key, ...s }) => s),
  };
}
