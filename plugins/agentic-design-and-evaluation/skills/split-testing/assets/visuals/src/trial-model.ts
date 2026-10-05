/** The document `trial.py report RUN_DIR` writes, and derivations from it.
 * Fields are read defensively: older run directories omit some of them. */
import { isNum, Outcome, wilson } from "./core";

export interface TrialRun {
  job?: string; scenario: string; arm: string; repeat?: number; status?: string;
  passed: boolean | null; valid?: boolean; invalid_reason?: string | null;
  checks?: Record<string, unknown>;
  judge?: { verdict?: string | null; reason?: string | null } | null;
  usage?: Record<string, number>; commands?: number | null;
  seconds?: number | null; setup_seconds?: number | null; checks_seconds?: number | null; judge_seconds?: number | null;
  confined?: boolean | null; artifact_missing?: boolean; final_message_excerpt?: string;
}
export interface TrialScenario {
  name: string; prompt?: string; followups?: string[];
  judge?: { question?: string; [k: string]: unknown } | string | null;
  judge_role?: string | null; required?: string[]; artifact?: string | null;
  /** scenario.json's free text, cut to the report's text bound (24,000 characters). */
  description?: string; description_truncated?: boolean; judge_required?: boolean;
}
/** An arm's (or the judge's) entry in the plan: its recorded settings and digests, and the bounded text
 * (24,000 characters) those digests name while the run directory still holds that content. */
export interface TrialArm {
  executor?: string; model?: string; effort?: string; model_spec?: string;
  instructions_sha256?: string; instructions_text?: string; instructions_truncated?: boolean;
  artifact_sha256?: string; artifact_text?: string; artifact_truncated?: boolean;
  resources_sha256?: string; resources?: string[];
  stub_skills?: { dir?: string; count?: number; chars?: number; seed?: number };
  [k: string]: unknown;
}
export interface ArmStats { passed: number; valid: number; runs: number; interval?: [number, number] | null; usage_mean?: Record<string, number>; no_usage?: number; commands_mean?: number | null; seconds_mean?: number | null }
export interface CellStats { scenario: string; arm: string; passed: number; valid: number; runs: number; invalid?: string[]; interval?: [number, number] | null; checks?: Record<string, string> }
export interface PairStats { a_wins: number; b_wins: number; tie: number; inconsistent: number; invalid: number; pairs: number; decisive: number; a_win_rate: number | null; a_win_rate_interval: [number, number] | null }
export interface PairwiseSummary { arms: [string, string]; judge?: Record<string, unknown>; overall: PairStats; scenarios: Record<string, PairStats> }
export interface TrialReport {
  name?: string | null; run_directory?: string;
  plan?: { arms?: Record<string, TrialArm>; scenarios?: TrialScenario[]; judge?: TrialArm | null; decision_rule?: string };
  runs: TrialRun[];
  arms?: Record<string, ArmStats>;
  scenarios?: Record<string, CellStats>;
  pairwise?: Record<string, PairwiseSummary>;
  baseline?: string;
  pct_vs_baseline?: Record<string, Record<string, { median?: number | null; mean?: number | null; n_scenarios?: number }>>;
}

export function outcomeOf(run: TrialRun): Outcome {
  return run.passed === true ? "pass" : run.passed === false ? "fail" : "invalid";
}

export interface Tally { pass: number; fail: number; invalid: number; runs: number; valid: number; rate: number | null; interval: [number, number] | null }
export function tally(runs: TrialRun[]): Tally {
  let pass = 0, fail = 0, invalid = 0;
  for (const r of runs) { const o = outcomeOf(r); if (o === "pass") pass++; else if (o === "fail") fail++; else invalid++; }
  const valid = pass + fail;
  return { pass, fail, invalid, runs: runs.length, valid, rate: valid ? pass / valid : null, interval: wilson(pass, valid) };
}

/** Arms and cases in a reading order: the plan's order where it has one. */
export function trialAxes(data: TrialReport): { arms: string[]; cases: string[] } {
  const seenArms = new Set<string>(), seenCases = new Set<string>();
  for (const a of Object.keys(data.plan?.arms || {})) seenArms.add(a);
  for (const s of data.plan?.scenarios || []) if (s?.name) seenCases.add(s.name);
  for (const r of data.runs || []) { seenArms.add(r.arm); seenCases.add(r.scenario); }
  const ran = new Set((data.runs || []).map(r => r.arm)), ranCases = new Set((data.runs || []).map(r => r.scenario));
  return { arms: [...seenArms].filter(a => ran.has(a)), cases: [...seenCases].filter(c => ranCases.has(c)) };
}

export function runsWhere(data: TrialReport, pred: (r: TrialRun) => boolean): TrialRun[] {
  return (data.runs || []).filter(pred);
}

/** The usage field a reader most likely wants for "tokens out", by executor vocabulary. */
export function usageValue(run: TrialRun, field: string): number | null {
  const v = run.usage?.[field];
  return isNum(v) ? v : null;
}

/** Numeric measures present in this trial, in a fixed preferred order. */
export function costMeasures(data: TrialReport): Array<{ id: string; label: string; unit: "tokens" | "seconds" | "usd" | "count"; get: (r: TrialRun) => number | null }> {
  const runs = (data.runs || []).filter(r => r.passed !== null || r.usage);
  const has = (get: (r: TrialRun) => number | null) => runs.some(r => { const v = get(r); return isNum(v) && v > 0; });
  const all: Array<{ id: string; label: string; unit: "tokens" | "seconds" | "usd" | "count"; get: (r: TrialRun) => number | null }> = [
    { id: "output_tokens", label: "Output tokens", unit: "tokens", get: r => usageValue(r, "output_tokens") },
    { id: "input_tokens", label: "Input tokens", unit: "tokens", get: r => usageValue(r, "input_tokens") },
    { id: "seconds", label: "Executor time", unit: "seconds", get: r => isNum(r.seconds) ? r.seconds : null },
    { id: "commands", label: "Commands run", unit: "count", get: r => isNum(r.commands) ? r.commands : null },
    { id: "total_cost_usd", label: "Cost", unit: "usd", get: r => usageValue(r, "total_cost_usd") },
  ];
  return all.filter(m => has(m.get));
}

/** Boolean checks and their per-arm counts over valid runs. A check that some
 * cases require is counted over those cases' runs, where true is a pass; in
 * other cases it is only a measure, so those runs do not enter its row. */
export interface CheckRow { name: string; required: boolean; requiredIn: string[]; cells: Record<string, { k: number; n: number }> }
export function checkTable(data: TrialReport, arms: string[]): CheckRow[] {
  const requiredIn = new Map<string, Set<string>>();
  for (const s of data.plan?.scenarios || []) for (const c of s?.required || []) { if (!requiredIn.has(c)) requiredIn.set(c, new Set()); requiredIn.get(c)!.add(s.name); }
  const names = new Map<string, boolean>();
  for (const r of data.runs || []) {
    if (r.passed === null) continue;
    for (const [k, v] of Object.entries(r.checks || {})) {
      if (typeof v === "boolean") { if (!names.has(k)) names.set(k, true); }
      else names.set(k, false);
    }
  }
  const rows: CheckRow[] = [];
  for (const [name, boolOnly] of names) {
    if (!boolOnly) continue;
    const req = requiredIn.get(name);
    const cells: Record<string, { k: number; n: number }> = {};
    for (const a of arms) {
      let k = 0, n = 0;
      for (const r of data.runs) if (r.arm === a && r.passed !== null && typeof r.checks?.[name] === "boolean" && (!req || req.has(r.scenario))) { n++; if (r.checks[name]) k++; }
      cells[a] = { k, n };
    }
    rows.push({ name, required: !!req, requiredIn: req ? [...req] : [], cells });
  }
  rows.sort((x, y) => Number(y.required) - Number(x.required) || x.name.localeCompare(y.name));
  return rows;
}

export function judgeQuestion(s: TrialScenario | undefined): string | undefined {
  if (!s?.judge) return undefined;
  if (typeof s.judge === "string") return s.judge;
  return typeof s.judge.question === "string" ? s.judge.question : undefined;
}

/** Where a run's native record lives, relative to the run directory. */
export function recordPath(data: TrialReport, run: TrialRun): string | null {
  if (!run.job) return null;
  return `${data.run_directory ? data.run_directory.replace(/\/+$/, "") + "/" : ""}runs/${run.job}/`;
}
