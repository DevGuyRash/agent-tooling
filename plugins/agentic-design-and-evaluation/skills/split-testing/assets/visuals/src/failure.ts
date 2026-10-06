/** Why a run did not pass, in one short line a reader can act on. Used by the
 * run drawer, the ledger, tapestry marks, case dossiers and the failures view.
 *
 * The rule mirrors trial.py's: a valid run passes when every required check is
 * exactly true and, where the case's judge decides (a judge question without
 * judge_required: false), the verdict is "pass". So a cause is either required
 * checks that did not hold, or the judge, and an invalid run names the reason
 * trial.py recorded instead of a result. Nothing here is guessed: a failed run
 * whose data name no cause says so. */
import { invalidReason } from "./trial-model";
import type { TrialRun, TrialScenario } from "./trial-model";

export interface FailureCause {
  /** judge: the judge said fail; check: a required check did not hold (or, with no
   * failedChecks, a failure the data name no cause for); invalid: no valid result; none: the run passed. */
  kind: "judge" | "check" | "invalid" | "none";
  /** One plain sentence, at most about 200 characters; empty for a pass. Plain text: escape it. */
  text: string;
  /** Required checks that did not hold (false, not recorded, or not true/false), in the scenario's required order. */
  failedChecks: string[];
}

/** How a required check ended on one run: held only when exactly true, as trial.py decides. */
export type CheckState = "held" | "false" | "missing" | "other";
export function checkState(value: unknown): CheckState {
  return value === true ? "held" : value === false ? "false" : value === undefined || value === null ? "missing" : "other";
}

/** The required checks that did not hold on a run, with how each ended. */
export function unmetChecks(run: TrialRun, scenario?: TrialScenario): Array<{ name: string; state: Exclude<CheckState, "held">; value: unknown }> {
  const required = Array.isArray(scenario?.required) ? scenario!.required.filter((c): c is string => typeof c === "string") : [];
  const checks = run.checks && typeof run.checks === "object" ? run.checks : {};
  const out: Array<{ name: string; state: Exclude<CheckState, "held">; value: unknown }> = [];
  for (const name of required) {
    const value = Object.prototype.hasOwnProperty.call(checks, name) ? checks[name] : undefined, state = checkState(value);
    if (state !== "held") out.push({ name, state, value });
  }
  return out;
}

/** Whether the case's judge decides the run's pass, as trial.py applies it. Without
 * the scenario, a recorded verdict is taken as deciding. */
export function judgeDecides(run: TrialRun, scenario?: TrialScenario): boolean {
  if (scenario) return !!scenario.judge && scenario.judge_required !== false;
  return typeof run.judge?.verdict === "string" && run.judge.verdict !== "";
}

/** True when a deciding judge did not say pass on a valid failed run. */
export function judgeFailed(run: TrialRun, scenario?: TrialScenario): boolean {
  return run.passed === false && judgeDecides(run, scenario) && run.judge?.verdict !== "pass";
}

/** Collapse whitespace so a value reads as one line. */
export function oneLine(value: unknown): string {
  return (typeof value === "string" ? value : value === null || value === undefined ? "" : String(value)).replace(/\s+/g, " ").trim();
}

/** At most `max` characters: whole sentences where they fit, else a clause, else
 * whole words, always marked with an ellipsis when anything was cut. */
export function clip(value: unknown, max = 200): string {
  const s = oneLine(value);
  if (s.length <= max) return s;
  const room = max - 2;
  let sentence = -1, clause = -1;
  // A sentence ends at . ! ? (not an ellipsis), with any closing quote, before a space.
  for (const m of s.matchAll(/(?<!\.)[.!?;]["”’')\]]?(?=\s)/g)) {
    const end = (m.index ?? 0) + m[0].length;
    if (end > room) break;
    if (m[0] === ";") clause = end - 1; else sentence = end;
  }
  // Prefer whole sentences, but not at the cost of most of the room: the words that
  // follow a short first sentence often carry the point.
  if (sentence >= max * 0.6) return `${s.slice(0, sentence)} …`;
  if (clause >= max * 0.6) return `${s.slice(0, clause)} …`;
  const space = s.lastIndexOf(" ", max - 1);
  return `${s.slice(0, space > max * 0.6 ? space : max - 1).replace(/[\s,;:.–—-]+$/, "")}…`;
}

const NOTHING = new Set(["", "-", "–", "—", "none", "ok", "pass", "passed", "n/a", "na", "null", "no", "0", "false", "true", "yes", "[]", "{}"]);
const DETAIL_NAME = /^(problems?|errors?|failures?|reasons?|why|diagnos[a-z]*)$/i;
const DETAIL_PART = /(^|[_\-.\s])(problems?|errors?|failures?|failed|reasons?|notes?|why|diagnos[a-z]*)($|[_\-.\s])/i;

/** A recorded text value that says more about what went wrong, when the run's checks
 * carry one: a string check named like problems, errors, failures, reason or note
 * whose value is not empty, "-", "ok" or similar. Shown with its name, never as
 * the cause itself. */
export function recordedDetail(run: TrialRun): { name: string; value: string } | null {
  const entries = Object.entries(run.checks && typeof run.checks === "object" ? run.checks : {})
    .filter((e): e is [string, string] => typeof e[1] === "string" && e[0] !== "check_error" && !NOTHING.has(oneLine(e[1]).toLowerCase()));
  const hit = entries.find(([k]) => DETAIL_NAME.test(k)) || entries.find(([k]) => DETAIL_PART.test(k));
  return hit ? { name: hit[0], value: oneLine(hit[1]) } : null;
}

const STOP = new Set(["the", "and", "for", "was", "are", "has", "not", "per", "with", "from", "into", "that"]);
const tokens = (name: string): string[] => name.toLowerCase().split(/[^a-z0-9]+/).filter(t => t.length >= 3 && !STOP.has(t));
const FAILURE_WORD = /^(failed|failures?|errors?|problems?|missed|missing|wrong)$/;

/** A recorded value about one required check: a text or number check whose name
 * shares words with it (rule_edits_followed_by_all for all_follow_rule_edits), or
 * one word plus a failure word (policy_cases_failed for new_policy_charged). The
 * closest name wins. Shown with its name, so the reader judges the connection. */
export function relatedValue(run: TrialRun, check: string): { name: string; value: string } | null {
  const want = tokens(String(check));
  if (!want.length) return null;
  let best: { name: string; value: string; score: number } | null = null;
  for (const [name, raw] of Object.entries(run.checks && typeof run.checks === "object" ? run.checks : {})) {
    if (name === check || name === "check_error" || (typeof raw !== "string" && typeof raw !== "number")) continue;
    const value = oneLine(raw);
    if (typeof raw === "string" && NOTHING.has(value.toLowerCase())) continue;
    const have = tokens(name);
    const shared = want.filter(w => have.some(h => h.startsWith(w) || w.startsWith(h))).length;
    const score = shared >= 2 ? shared : shared === 1 && have.some(h => FAILURE_WORD.test(h)) ? 1 : 0;
    if (score && (!best || score > best.score)) best = { name, value, score };
  }
  return best ? { name: best.name, value: best.value } : null;
}

/** The recorded value that says most about why a valid run failed: one tied by name to
 * a required check that did not hold (the given one, or the first that has one), else,
 * when only one required check failed, a general detail such as a problems check. */
export function failureDetail(run: TrialRun, scenario?: TrialScenario, check?: string): { name: string; value: string } | null {
  const unmet = unmetChecks(run, scenario);
  for (const name of check ? [check] : unmet.map(u => u.name)) { const hit = relatedValue(run, name); if (hit) return hit; }
  return unmet.length === 1 && (!check || unmet[0].name === check) ? recordedDetail(run) : null;
}

/** Plain words and a remedy for an invalid reason code. One vocabulary for every
 * view: the invalid view, the ledger, the drawer and failureCause() all read
 * trial-model's invalidReason(). Its text may mark names as `code`. */
export { invalidReason } from "./trial-model";
export type { InvalidReason } from "./trial-model";

/** Text with `code` marks removed, for places that show plain text (titles, labels). */
export const plainText = (text: unknown): string => oneLine(text).replace(/`([^`]*)`/g, "$1");

/** End with a full stop unless the text already ends a sentence or was clipped. */
const sentence = (text: string): string => /[.!?…]["”')]?$/.test(text) ? text : `${text}.`;
const list = (names: string[]): string => names.length <= 1 ? names.join("") : `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
const shown = (value: unknown): string => { try { return clip(typeof value === "string" ? `“${value}”` : JSON.stringify(value) ?? String(value), 40); } catch { return "a value"; } };

/** Name required checks that did not hold, in one clause, within `max` characters:
 * as many names as fit, in required order, then a count of the rest. */
function checksClause(unmet: ReturnType<typeof unmetChecks>, max: number): string {
  const allFalse = unmet.every(u => u.state === "false");
  let text = "";
  for (let keep = unmet.length; keep >= 1; keep--) {
    const named = unmet.slice(0, keep), rest = unmet.length - keep;
    const falses = named.filter(u => u.state === "false").map(u => u.name);
    const missing = named.filter(u => u.state === "missing").map(u => u.name);
    const parts: string[] = [];
    const lead = (n: number) => parts.length ? "" : n > 1 ? "Required checks " : "Required check ";
    if (allFalse) {
      const names = rest ? [...falses, `${rest} more`] : falses;
      parts.push(`${lead(names.length)}${list(names)} ${names.length > 1 ? "were" : "was"} false`);
    } else {
      if (falses.length) parts.push(`${lead(falses.length)}${list(falses)} ${falses.length > 1 ? "were" : "was"} false`);
      if (missing.length) parts.push(`${lead(missing.length)}${list(missing)} ${missing.length > 1 ? "were" : "was"} not recorded`);
      for (const o of named.filter(u => u.state === "other")) parts.push(`${lead(1)}${o.name} was ${shown(o.value)}, not true`);
      if (rest) parts.push(`${rest} more did not hold`);
    }
    text = parts.join("; ");
    if (text.length <= max) return text;
  }
  return clip(text, max);
}

/** Why a run did not pass. A pass gives kind "none" and empty text. */
export function failureCause(run: TrialRun, scenario?: TrialScenario): FailureCause {
  if (!run || run.passed === true) return { kind: "none", text: "", failedChecks: [] };
  if (run.passed !== false) {
    const code = oneLine(run.invalid_reason) || (run.status && run.status !== "ok" ? oneLine(run.status) : "");
    if (!code) return { kind: "invalid", text: "No valid result, and no reason was recorded.", failedChecks: [] };
    let text = plainText(invalidReason(code).text);
    const extra = code === "judge-error" ? oneLine(run.judge?.reason)
      : code === "check-error" && run.checks && typeof run.checks === "object" ? oneLine(run.checks.check_error) : "";
    if (extra) text = sentence(`${text.replace(/[.!?]$/, "")}: ${clip(extra, Math.max(60, 196 - text.length))}`);
    return { kind: "invalid", text: clip(text, 220), failedChecks: [] };
  }
  const unmet = scenario ? unmetChecks(run, scenario) : [];
  const failedChecks = unmet.map(u => u.name);
  const judged = judgeFailed(run, scenario);
  const verdict = oneLine(run.judge?.verdict), why = oneLine(run.judge?.reason);
  if (unmet.length) {
    let text = `${checksClause(unmet, judged ? 150 : 170)}${judged ? `; the judge also ${verdict === "fail" ? "said fail" : verdict ? `gave “${clip(verdict, 20)}”` : "gave no pass"}` : ""}`;
    const detail = failureDetail(run, scenario) || recordedDetail(run);
    if (detail) {
      const room = 196 - text.length - detail.name.length - 4;
      if (room >= 24) text += ` (${detail.name}: ${clip(detail.value, room)})`;
    }
    return { kind: "check", text: sentence(text), failedChecks };
  }
  if (judged) {
    const head = verdict === "fail" ? "The judge said fail" : verdict ? `The judge's verdict was “${clip(verdict, 24)}”, not pass` : "The case needs a passing judge verdict, and none was recorded";
    return { kind: "judge", text: why ? sentence(`${head}: ${clip(why, 196 - head.length)}`) : verdict ? `${head} and gave no reason.` : `${head}.`, failedChecks };
  }
  if (!scenario) return { kind: "check", text: "Failed, but this report does not list the case's required checks, so no cause can be named.", failedChecks };
  const required = Array.isArray(scenario.required) && scenario.required.length > 0, judge = judgeDecides(run, scenario);
  const why2 = required ? (judge ? "every required check held and the judge did not fail it" : "every required check held")
    : judge ? "the case lists no required checks and the judge did not fail it" : "the case lists no required checks and no judge decides it";
  return { kind: "check", text: `Failed, but no cause was recorded: ${why2}.`, failedChecks };
}
