/** The document `trial.py report RUN_DIR` writes, and derivations from it.
 * Fields are read defensively: older run directories omit some of them. */
import { isNum, median, Outcome, wilson, entriesOf, isId, keysIn } from "./core";
import { caseKey, caseSplit, casesWords, pooledCases } from "./stats";

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
  /** The judge this arm names for itself, which scored its runs in place of the plan's judge. */
  judge?: TrialArm | null;
  [k: string]: unknown;
}
export interface ArmStats { passed: number; valid: number; runs: number; /** Null when the arm's runs span more than one case. */ interval?: [number, number] | null; /** Per-case counts, from runtimes that give them. */ cases?: unknown; usage_mean?: Record<string, number>; no_usage?: number; commands_mean?: number | null; seconds_mean?: number | null }
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

/** Counts of a set of runs. `cases` is how many cases (scenarios) its valid runs come from. */
export interface Tally { pass: number; fail: number; invalid: number; runs: number; valid: number; rate: number | null; interval: [number, number] | null; cases: number;
  /** The cases its valid runs come from, in the shared words (casesWords). */
  over: string }
/** Counts with a 95% Wilson interval only when the valid runs come from one case. Runs on one case repeat that
 * case rather than sample new cases, so an interval over several cases' runs would overstate certainty: pooled
 * counts are reported as counts ("3 of 6 runs passed across 2 cases"), and each case keeps its own interval. */
export function tally(runs: TrialRun[]): Tally {
  let pass = 0, fail = 0, invalid = 0;
  const perCase = new Map<string, number>();
  const key = (r: TrialRun) => caseKey(r.scenario);
  for (const r of runs) { const o = outcomeOf(r); if (o === "pass") pass++; else if (o === "fail") fail++; else invalid++; if (o !== "invalid") perCase.set(key(r), (perCase.get(key(r)) || 0) + 1); }
  const valid = pass + fail;
  // A trial's runs repeat their case by design: the shared rule withholds an interval over several cases.
  return { pass, fail, invalid, runs: runs.length, valid, rate: valid ? pass / valid : null, interval: pooledCases(perCase.values(), true) ? null : wilson(pass, valid), cases: perCase.size, over: casesWords(...caseSplit(perCase.keys())) };
}
/** Every run of one arm, counted, with the runtime's word on its interval taken as final: `trial.py report`
 * gives an arm's interval as null when its runs span more than one case. */
export function armTally(data: TrialReport, arm: string): Tally {
  const t = tally(data.runs.filter(r => r && r.arm === arm));
  const given = data.arms && Object.prototype.hasOwnProperty.call(data.arms, arm) ? data.arms[arm] : null;
  return given && typeof given === "object" && Object.prototype.hasOwnProperty.call(given, "interval") && given.interval === null ? { ...t, interval: null } : t;
}
/** An arm's valid runs per case, for a count written by hand about it; null when the trial has no runs of that arm. */
export function armCases(data: TrialReport | undefined, arm: unknown): Map<string, number> | null {
  if (!data || typeof arm !== "string" || !Array.isArray(data.runs)) return null;
  const runs = data.runs.filter(r => r && r.arm === arm);
  if (!runs.length) return null;
  const perCase = new Map<string, number>();
  for (const r of runs) if (outcomeOf(r) !== "invalid") perCase.set(String(r.scenario), (perCase.get(String(r.scenario)) || 0) + 1);
  return perCase;
}
/** Pooled counts in words: "3 of 6 runs passed across 2 cases", or the rate when one case holds them. */
export function countsText(t: Tally): string {
  if (!t.valid) return "no valid runs";
  return t.cases > 1 ? `${t.pass} of ${t.valid} runs passed across ${t.over}` : `${t.pass} of ${t.valid} runs passed`;
}

/** Arms and cases in a reading order: the plan's order where it has one. */
export function trialAxes(data: TrialReport): { arms: string[]; cases: string[] } {
  const seenArms = new Set<string>(), seenCases = new Set<string>();
  for (const a of keysIn(data.plan?.arms || {})) seenArms.add(a);
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

/** A run's cost in US dollars: the shared record vocabulary's cost_usd (a launcher's or host's run), else the
 * total_cost_usd an older executor reported. */
export function costUsd(run: TrialRun): number | null {
  return usageValue(run, "cost_usd") ?? usageValue(run, "total_cost_usd");
}

export interface CostMeasure { id: string; label: string; unit: "tokens" | "seconds" | "usd" | "count"; get: (r: TrialRun) => number | null; note?: string }
export function costMeasures(data: TrialReport): CostMeasure[] {
  const runs = (data.runs || []).filter(r => r.passed !== null);
  const has = (get: (r: TrialRun) => number | null) => runs.some(r => { const v = get(r); return isNum(v) && v > 0; });
  const all: CostMeasure[] = [
    { id: "output_tokens", label: "Output tokens", unit: "tokens", get: r => usageValue(r, "output_tokens") },
    { id: "input_tokens", label: "Input tokens", unit: "tokens", get: inputTokens, ...(runs.some(separateCache) ? { note: "including cache reads and writes, which this executor reports apart from input_tokens" } : {}) },
    { id: "seconds", label: "Executor time", unit: "seconds", get: r => isNum(r.seconds) ? r.seconds : null },
    { id: "commands", label: "Commands run", unit: "count", get: r => isNum(r.commands) ? r.commands : null },
    { id: "total_cost_usd", label: "Cost", unit: "usd", get: costUsd },
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
    for (const [k, v] of entriesOf(r.checks || {})) {
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

/** The judge that scored an arm's runs: the one the plan records in the arm's own entry, else the plan's. */
export function judgeFor(data: TrialReport | undefined, arm: string): TrialArm | null {
  const entry = (v: unknown): v is TrialArm => !!v && typeof v === "object" && !Array.isArray(v);
  const own = data?.plan?.arms?.[arm]?.judge, shared = data?.plan?.judge;
  return entry(own) ? own : entry(shared) ? shared : null;
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

/** An invalid reason in plain words, with the remedy for that reason. The codes are those trial.py records: a run
 * status other than ok (timeout, exit-N, setup-failed, setup-exit-N, credential-kept, ...), or, for a run whose
 * executor finished, check-error, check-missing, judge-missing, judge-unassessed, judge-error, judge-unclear,
 * judge-stale, not-exposed and exposure-unknown. Each is worded from references/trials.md and launching.md. */
export interface InvalidReason { code: string; text: string; remedy: string }
export function invalidReason(code: string | null | undefined): InvalidReason {
  const c = String(code || "unknown");
  // A run whose executor did not finish is run again (references/trials.md, Reading results), into the same directory
  // only with the plan unchanged: a run directory holds its runs to the arm and scenario they were made with, and a
  // repair that changes either is refused there ("restore them or use a new --out"), so it starts over in a new one.
  const retry = "With the plan unchanged, rerun them into this directory: `trial.py run PLAN --out RUN_DIR --retry-invalid`.";
  const repair = ", which this directory refuses (it holds its runs to the settings they were made with), so run the repaired plan into a new directory, where every run is made again: `trial.py run PLAN --out NEW_DIR`.";
  // A run whose executor finished keeps its output and is scored again once its check or judge can decide it, never
  // run again (references/trial-flow.md, Validity).
  const resample = "Running them again would resample exactly these runs.";
  const known: Record<string, [string, string]> = {
    "timeout": ["The executor ran past the case's time limit (`timeout_s`).", `${retry} If the task needs longer, raising the scenario's \`timeout_s\` changes the scenario${repair}`],
    "setup-failed": ["The scenario's `setup.sh` failed or ran past 300 seconds (`setup_error` in the run's result says why), so the executor never started.", `${retry} A fix to \`setup.sh\` changes the scenario${repair}`],
    "setup-timeout": ["The launcher's setup turn, which prepares the executor before the agent starts, ran past the case's time limit, so the executor never started.", `${retry} Raising the scenario's \`timeout_s\` changes the scenario${repair}`],
    "setup-watch-unreadable": ["A configuration path the arm watches (`watch`) could not be read after setup, so the executor never started.", `The run's \`stderr.log\` names the paths. ${retry} A change to the arm's \`watch\` or to its launcher changes the arm${repair}`],
    "session-changed": ["A follow-up turn reported another session than the first, so it did not continue the conversation.", `${retry} A launcher continues the same session on every later turn (launching.md, One run, turn by turn); fixing one that does not changes the arm${repair}`],
    "config-changed": ["A turn changed watched configuration that a later turn would load, so the run stopped before that turn.", `The run's \`stderr.log\` names the paths. ${retry} When the executor writes that configuration itself, watch only configuration it loads and does not write during a turn, never its session records, locks or caches; that changes the arm${repair}`],
    "model-changed": ["The run reported another model than the one the probe observed for its arm, or more than one, and the runtime holds an arm's runs to one model.", retry],
    "no-record": ["The launcher left no record of the run, so nothing shows what the executor did.", `\`record_error\` in the run's \`result.json\` says where the record was looked for. ${retry} Fixing the launcher so it writes its record changes the arm${repair}`],
    "record-invalid": ["The run's record could not be used: it is malformed, or breaks the shape launching.md gives a record.", `\`record_error\` in the run's \`result.json\` says why. ${retry} Fixing what writes the record (launching.md, The record) changes the arm${repair}`],
    "unfinished": ["The executor's own record says it did not finish (`finished: false`).", retry],
    "credential-kept": ["The credentials the run was given could not be verified removed, so no check, evidence extractor or judge read it.", `Remove by hand the paths \`RUN_DIR/credentials.jsonl\` lists as \`unremoved\`; until then \`trial.py run\` leaves the run as it is and exits 3, and judging or pairing it is refused too. Then, with the plan unchanged, rerun them into this directory: \`trial.py run PLAN --out RUN_DIR --retry-invalid\`.`],
    "no-thread-for-followup": ["The executor gave no conversation to continue, so the follow-up turn could not be sent.", retry],
    "skipped": ["The run was not attempted: the runtime stopped scheduling it and named the cause.", "Fix the cause `trial.py run` named, then run the same plan into the same `--out`; a fix that changes an arm or a scenario runs into a new `--out` instead, since that directory refuses it."],
    "check-error": ["The executor finished, but the case's checks failed to run.", `Fix the check, then score the runs again: \`trial.py recheck RUN_DIR\`. ${resample}`],
    "check-missing": ["The executor finished, but a required check returned neither true nor false (such as \"unknown\"), so it could not decide the run.", `Fix the check so it can decide, then score the runs again: \`trial.py recheck RUN_DIR\`. ${resample}`],
    "judge-missing": ["The case asks a judge question, but the plan names no judge, so no verdict could be given.", "Rerunning gives the same result. Name a judge: `trial.py recheck RUN_DIR --judge '<judge JSON>'`; or, when the scenario's checks alone should decide, set its `judge_required: false` and score the runs again: `trial.py recheck RUN_DIR`."],
    "judge-unassessed": ["The executor finished, but a judge cannot read its output (unreadable, outside the run, not UTF-8 text, or over 64 MiB), so no judge was shown it.", `Give the scenario's \`check.py\` a \`judge_context\` that returns evidence for it, then judge them again: \`trial.py recheck RUN_DIR --rejudge\`. ${resample}`],
    "judge-error": ["The judge was asked but gave no verdict.", `Ask the judge again: \`trial.py recheck RUN_DIR --rejudge\`. ${resample}`],
    "judge-unclear": ["The judge said the evidence cannot decide the run (an `unclear` verdict).", `Asking the same question of the same evidence again would only wait for a verdict it likes. If the judge lacked evidence or a question it could decide, give it that (a \`judge_context\` in \`check.py\`, a clearer \`pass_when\`), then judge them again: \`trial.py recheck RUN_DIR --rejudge\`; otherwise report them as invalid. ${resample}`],
    "judge-stale": ["The verdict answers another question or evidence than the run's now, or came from another judge than the one its arm calls for, or there is none.", `Judge them again: \`trial.py recheck RUN_DIR --rejudge\`. ${resample}`],
    "not-exposed": ["The scenario asks how well the arm's resources work once they reach the model (`requires_exposure`), and this run's record shows they did not reach the model, so it says nothing about that.", `${resample} Report how many runs each arm lost this way: a treatment that often goes unread is a finding of its own.`],
    "exposure-unknown": ["The scenario asks how well the arm's resources work once they reach the model (`requires_exposure`), and this run's record cannot show whether they did (the executor ran a command, say, or no record holds evidence about them).", `${resample} Report how many runs each arm lost this way. A launcher that records the reads it can identify as \`read\` actions lets later runs show it.`],
  };
  if (known[c]) return { code: c, text: known[c][0], remedy: known[c][1] };
  const exit = /^exit-(-?\d+)$/.exec(c);
  if (exit) return { code: c, text: `The executor exited with code ${exit[1]} before finishing.`, remedy: retry };
  const setupExit = /^setup-exit-(-?\d+)$/.exec(c);
  if (setupExit) return { code: c, text: `The launcher's setup turn, which prepares the executor before the agent starts, exited with code ${setupExit[1]} (as one does to refuse a file already in its way), so the executor never started.`, remedy: `The run's \`stderr.log\` holds what it printed. ${retry} A fix to the launcher or the arm changes the arm${repair}` };
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
  for (const r of valid) for (const [k, v] of entriesOf(r.checks || {})) {
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

const isPlain = (v: unknown): v is Record<string, unknown> => !!v && typeof v === "object" && !Array.isArray(v);
/** The arms a trial knows: those its runs with an arm and a scenario ran, and those its plan lists (entriesOf). */
export function trialArms(trial: unknown): string[] {
  const out: string[] = [];
  if (!isPlain(trial)) return out;
  for (const r of Array.isArray(trial.runs) ? trial.runs : []) if (isPlain(r) && isId(r.arm) && isId(r.scenario) && !out.includes(r.arm)) out.push(r.arm);
  if (isPlain(trial.plan)) for (const a of keysIn(trial.plan.arms)) if (isId(a) && !out.includes(a)) out.push(a);
  return out;
}
/** A pairwise judgment every check and every view reads: two different arms the trial knows, with its overall counts
 * and its counts by case, each an object, each case named by an id. The checks refuse any other, and the pairwise view
 * draws none. */
export function wellFormedPair(p: unknown, known: string[]): boolean {
  return isPlain(p) && Array.isArray(p.arms) && p.arms.length === 2 && p.arms.every(a => isId(a) && known.includes(a)) && p.arms[0] !== p.arms[1] && isPlain(p.overall) && isPlain(p.scenarios) && keysIn(p.scenarios).every(isId);
}
/** The pairwise judgments every check and every view reads, listed one way (entriesOf): each named by an id and
 * well formed (wellFormedPair). The checks refuse the rest, and the pairwise view draws none of them. */
export function wellFormedPairs(trial: unknown): Array<[string, unknown]> {
  const known = trialArms(trial);
  return entriesOf(isPlain(trial) ? trial.pairwise : undefined).filter(([k, p]) => isId(k) && wellFormedPair(p, known));
}
