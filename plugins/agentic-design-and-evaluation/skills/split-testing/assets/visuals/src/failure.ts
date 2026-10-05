/** Why a run did not pass, in one short line a reader can act on. Used by the
 * run drawer, the ledger, tapestry marks, case dossiers and the failures view. */
import type { TrialRun, TrialScenario } from "./trial-model";

export interface FailureCause {
  /** judge: the judge said fail; check: a required check was false; invalid: no valid result; none: the run passed. */
  kind: "judge" | "check" | "invalid" | "none";
  /** One plain sentence, at most about 200 characters. */
  text: string;
  /** Required checks that were false, in the scenario's required order. */
  failedChecks: string[];
}

export function failureCause(run: TrialRun, scenario?: TrialScenario): FailureCause {
  void scenario;
  if (run.passed === true) return { kind: "none", text: "", failedChecks: [] };
  if (run.passed === null) return { kind: "invalid", text: String(run.invalid_reason || run.status || "invalid"), failedChecks: [] };
  return { kind: "judge", text: String(run.judge?.reason || ""), failedChecks: [] };
}
