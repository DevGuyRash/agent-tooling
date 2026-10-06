/** The document `trial.py report RUN_DIR` writes, and derivations from it.
 * Fields are read defensively: older run directories omit some of them. */
import { isNum, median, Outcome, wilson } from "./core";

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
  judge?: { question?: string; pass_when?: string; [k: string]: unknown } | string | null;
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
  /** When the runs were written (ISO-8601), where the report records it. */
  ran?: { first?: string; last?: string } | null;
  generated_at?: string | null;
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

/** Numeric measures present in this trial, in a fixed preferred order. A measure
 * is present when a valid run recorded a positive value for it: the views place
 * valid runs only, so a measure only invalid runs carry would draw an empty panel. */
/** Input tokens a run read in all. Executors that report cache reads and writes beside
 * input_tokens (cache_read_input_tokens, cache_creation_input_tokens) leave them out of
 * it, so they are added back; one that reports cached_input_tokens counts them inside
 * input_tokens already. Either way the figure is every token of input. */
export function inputTokens(run: TrialRun): number | null {
  const base = usageValue(run, "input_tokens");
  if (base === null) return null;
  return base + (usageValue(run, "cache_read_input_tokens") ?? 0) + (usageValue(run, "cache_creation_input_tokens") ?? 0);
}
const separateCache = (run: TrialRun) => usageValue(run, "cache_read_input_tokens") !== null || usageValue(run, "cache_creation_input_tokens") !== null;

export interface CostMeasure { id: string; label: string; unit: "tokens" | "seconds" | "usd" | "count"; get: (r: TrialRun) => number | null; note?: string }
export function costMeasures(data: TrialReport): CostMeasure[] {
  const runs = (data.runs || []).filter(r => r.passed !== null);
  const has = (get: (r: TrialRun) => number | null) => runs.some(r => { const v = get(r); return isNum(v) && v > 0; });
  const all: CostMeasure[] = [
    { id: "output_tokens", label: "Output tokens", unit: "tokens", get: r => usageValue(r, "output_tokens") },
    { id: "input_tokens", label: "Input tokens", unit: "tokens", get: inputTokens, ...(runs.some(separateCache) ? { note: "including cache reads and writes, which this executor reports apart from input_tokens" } : {}) },
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

/** What the judge was told counts as a pass, when the scenario says. */
export function judgePassWhen(s: TrialScenario | undefined): string | undefined {
  return s?.judge && typeof s.judge === "object" && typeof s.judge.pass_when === "string" ? s.judge.pass_when : undefined;
}

/** The plan's entry for a scenario, by name. */
export function scenarioOf(data: TrialReport | undefined, name: string): TrialScenario | undefined {
  return (data?.plan?.scenarios || []).find(s => s?.name === name);
}

/** Where a run's native record lives, relative to the run directory. */
export function recordPath(data: TrialReport, run: TrialRun): string | null {
  if (!run.job) return null;
  return `${data.run_directory ? data.run_directory.replace(/\/+$/, "") + "/" : ""}runs/${run.job}/`;
}

/** A path for display: a home-directory prefix (/home/NAME, /Users/NAME) reads
 * as ~, so a forwarded report does not carry an account name in its headings.
 * Copy actions keep the full path. */
export function displayPath(path: string): string {
  return String(path).replace(/^\/(?:home|Users)\/[^/]+(?=\/|$)/, "~");
}

/** Text that may hold paths anywhere in it, such as a recorded command line or
 * config value: each home-directory prefix reads as ~, as displayPath() does for a
 * path on its own. */
export function displayText(text: string): string {
  return String(text).replace(/(^|[^\w.~/-])\/(?:home|Users)\/[^/\s"'`=;,)\]}]+(?=\/|$|[\s"'`=;,)\]}])/g, "$1~");
}

/** How many runs each arm made of each case, as a range over the cells that ran. */
export function repeatRange(data: TrialReport): { min: number; max: number } | null {
  const cells = new Map<string, number>();
  for (const r of data.runs || []) { const key = `${r.arm}\u0000${r.scenario}`; cells.set(key, (cells.get(key) || 0) + 1); }
  if (!cells.size) return null;
  const counts = [...cells.values()];
  return { min: Math.min(...counts), max: Math.max(...counts) };
}

// ------------------------------------------------------------------ invalid reasons

/** An invalid reason in plain words, with the remedy for that reason. The codes
 * are those trial.py records: a run status other than ok (timeout, setup-failed,
 * exit-N, ...), or judge-missing, judge-stale, judge-error and check-error. */
export interface InvalidReason { code: string; text: string; remedy: string }
export function invalidReason(code: string | null | undefined): InvalidReason {
  const c = String(code || "unknown");
  const retry = "Rerun them: `trial.py run PLAN --out RUN_DIR --retry-invalid`.";
  const known: Record<string, [string, string]> = {
    "judge-missing": ["The case asks a judge question, but the plan names no judge, so no verdict could be given.", "Rerunning gives the same result. Name a judge: `trial.py recheck RUN_DIR --judge '<judge JSON>'`, or set `judge_required: false` in the scenario when its checks alone should decide."],
    "judge-stale": ["The verdict came from another judge than this run directory's, or there is none.", "Judge them again: `trial.py recheck RUN_DIR --rejudge`."],
    "judge-error": ["The judge was asked but gave no verdict.", "Ask the judge again: `trial.py recheck RUN_DIR --rejudge`."],
    "check-error": ["The executor finished, but the case's checks failed to run.", "Fix the check, then score the runs again: `trial.py recheck RUN_DIR`."],
    "timeout": ["The executor ran past the case's time limit (`timeout_s`).", `Raise the scenario's \`timeout_s\` if the task needs longer. ${retry}`],
    "setup-failed": ["The run's setup did not finish, so the executor never started.", retry],
    "no-thread-for-followup": ["The executor gave no conversation to continue, so the follow-up turn could not be sent.", retry],
    "skipped": ["The run was not attempted.", retry],
  };
  if (known[c]) return { code: c, text: known[c][0], remedy: known[c][1] };
  const exit = /^exit-(-?\d+)$/.exec(c);
  if (exit) return { code: c, text: `The executor exited with code ${exit[1]} before finishing.`, remedy: retry };
  return { code: c, text: `The run did not finish with a valid result (recorded as \`${c}\`).`, remedy: retry };
}

// ------------------------------------------------------------------ case variants

/** A case run a second way: the same prompt, judge, required checks and
 * artifact as its base case, with more follow-up turns. */
export interface CasePair { base: string; variant: string; label: string; note?: string }

const same = (a: unknown, b: unknown) => JSON.stringify(a ?? null) === JSON.stringify(b ?? null);

/** Case variants found in the plan by content, never by name: scenarios that
 * ran and share prompt, judge, judge role, required checks and artifact, where
 * one (the base) has fewer follow-up turns and the other repeats them and adds
 * more. Each variant pairs with exactly one base, the closest one. */
export function casePairs(data: TrialReport): CasePair[] {
  const ran = new Set((data.runs || []).map(r => r.scenario));
  const scenarios = (data.plan?.scenarios || []).filter(s => s && typeof s.name === "string" && ran.has(s.name) && typeof s.prompt === "string" && s.prompt);
  const pairs: CasePair[] = [], used = new Set<string>();
  const turns = (s: TrialScenario) => Array.isArray(s.followups) ? s.followups.map(String) : [];
  for (const variant of scenarios) {
    if (used.has(variant.name)) continue;
    const vt = turns(variant);
    const bases = scenarios.filter(b => b !== variant && !used.has(b.name) && b.prompt === variant.prompt && same(b.judge, variant.judge) && same(b.judge_role, variant.judge_role)
      && same(b.required, variant.required) && same(b.artifact, variant.artifact) && turns(b).length < vt.length && turns(b).every((t, i) => t === vt[i]));
    // The closest base wins (the one whose turns it extends the least); a tie means no single base.
    const most = Math.max(-1, ...bases.map(b => turns(b).length)), closest = bases.filter(b => turns(b).length === most);
    if (closest.length !== 1) continue;
    const base = closest[0], extra = vt.slice(turns(base).length);
    pairs.push({ base: base.name, variant: variant.name, label: `+ ${extra.length} follow-up turn${extra.length === 1 ? "" : "s"}`, note: extra.join("\n\n").slice(0, 600) });
    used.add(variant.name);
  }
  return pairs;
}

/** Cases in reading order with each variant directly after its base (a
 * variant of a variant after that one). Each case appears once. */
export function pairedOrder(cases: string[], pairs: CasePair[]): string[] {
  const variantsOf = new Map<string, string[]>(), isVariant = new Set<string>();
  for (const p of pairs) {
    if (!cases.includes(p.base) || !cases.includes(p.variant) || isVariant.has(p.variant) || p.base === p.variant) continue;
    variantsOf.set(p.base, [...(variantsOf.get(p.base) || []), p.variant]); isVariant.add(p.variant);
  }
  const out: string[] = [], placed = new Set<string>();
  const place = (c: string) => { if (placed.has(c)) return; placed.add(c); out.push(c); for (const v of variantsOf.get(c) || []) place(v); };
  for (const c of cases) if (!isVariant.has(c)) place(c);
  for (const c of cases) place(c);
  return out;
}

/** Names (case or arm ids) the text mentions as whole tokens, in order of first
 * mention. Longer names win where they overlap, so "x-review2" is not read as "x".
 * A name that is a plain word ("good", "current") counts only when the text sets
 * it in backticks, since prose uses such words for their own meaning. */
export function ruleMentions(text: string | undefined, names: string[]): string[] {
  if (typeof text !== "string" || !text) return [];
  const found: Array<{ name: string; at: number }> = [];
  const taken: Array<[number, number]> = [];
  for (const name of [...new Set(names.filter(n => typeof n === "string" && n))].sort((a, b) => b.length - a.length)) {
    const quoted = name.replace(/[.*+?^$|()[\]{}\\]/g, "\\$&");
    const re = /^[A-Za-z]+$/.test(name)
      ? new RegExp("(`)(" + quoted + ")(?=`)", "g")
      : new RegExp("(^|[^A-Za-z0-9_-])(" + quoted + ")(?![A-Za-z0-9_]|-[A-Za-z0-9])", "g");
    let m: RegExpExecArray | null, first = -1;
    while ((m = re.exec(text))) {
      const at = m.index + m[1].length, end = at + name.length;
      if (!taken.some(([a, b]) => at < b && end > a)) { taken.push([at, end]); if (first < 0) first = at; }
    }
    if (first >= 0) found.push({ name, at: first });
  }
  return found.sort((a, b) => a.at - b.at).map(f => f.name);
}

// ------------------------------------------------------------------ checks by case

export interface CaseCheckRow { name: string; cells: Record<string, { k: number; n: number }> }
export interface CaseMeasureRow { name: string; kind: "boolean" | "number"; cells: Record<string, { k: number; n: number; median: number | null; min: number | null; max: number | null }> }
export interface CaseChecks {
  /** Required checks in the plan's order, counted over the case's valid runs; a missing value is not a pass. */
  required: CaseCheckRow[];
  /** The judge's verdicts over valid judged runs, when the case's judge decides its pass. */
  judge: Record<string, { k: number; n: number }> | null;
  /** Other recorded values: true/false measures and numbers. */
  measures: CaseMeasureRow[];
  /** The case's own outcome per arm over valid runs. */
  outcome: Record<string, { k: number; n: number; invalid: number }>;
}
export function caseChecks(data: TrialReport, scenario: string, arms: string[]): CaseChecks {
  const plan = scenarioOf(data, scenario);
  const runs = (data.runs || []).filter(r => r.scenario === scenario && arms.includes(r.arm));
  const valid = runs.filter(r => r.passed !== null);
  const required = (plan?.required || []).filter((c, i, all) => typeof c === "string" && all.indexOf(c) === i);
  const req = required.map(name => ({ name, cells: Object.fromEntries(arms.map(a => { const vs = valid.filter(r => r.arm === a); return [a, { k: vs.filter(r => r.checks?.[name] === true).length, n: vs.length }]; })) }));
  const judged = valid.filter(r => r.judge?.verdict === "pass" || r.judge?.verdict === "fail");
  // The judge is a pass condition only where it decides: a question the plan asks without judge_required: false.
  const decides = plan ? !!plan.judge && plan.judge_required !== false : judged.length > 0;
  const judge = decides ? Object.fromEntries(arms.map(a => { const js = judged.filter(r => r.arm === a); return [a, { k: js.filter(r => r.judge!.verdict === "pass").length, n: js.length }]; })) : null;
  const kinds = new Map<string, "boolean" | "number" | "other">();
  for (const r of valid) for (const [k, v] of Object.entries(r.checks || {})) {
    if (required.includes(k)) continue;
    const t = typeof v === "boolean" ? "boolean" : isNum(v) ? "number" : "other";
    const prev = kinds.get(k);
    kinds.set(k, prev === undefined || prev === t ? t : "other");
  }
  const measures: CaseMeasureRow[] = [];
  for (const [name, kind] of kinds) {
    if (kind === "other") continue;
    measures.push({ name, kind, cells: Object.fromEntries(arms.map(a => {
      const vals = valid.filter(r => r.arm === a).map(r => r.checks?.[name]).filter(v => kind === "boolean" ? typeof v === "boolean" : isNum(v));
      const nums = kind === "number" ? (vals as number[]) : [];
      return [a, { k: kind === "boolean" ? vals.filter(v => v === true).length : 0, n: vals.length, median: nums.length ? median(nums) : null, min: nums.length ? Math.min(...nums) : null, max: nums.length ? Math.max(...nums) : null }];
    })) });
  }
  measures.sort((x, y) => (x.kind === y.kind ? 0 : x.kind === "boolean" ? -1 : 1) || x.name.localeCompare(y.name));
  const outcome = Object.fromEntries(arms.map(a => { const t = tally(runs.filter(r => r.arm === a)); return [a, { k: t.pass, n: t.valid, invalid: t.invalid }]; }));
  return { required: req, judge, measures, outcome };
}
