/** Why runs failed: every valid failed run grouped by what failed it, across cases
 * and arms. A cause is a required check that did not hold or the judge's verdict,
 * exactly as failureCause() derives it, so this view, the drawer and the ledger
 * can never disagree. Each group counts its runs per arm and per case against the
 * valid runs that could have failed that way, quotes a representative reason (the
 * judge's words, or a recorded detail such as a `problems` check), keeps every
 * other reason one disclosure away, and draws the runs as marks that open the run
 * drawer. Invalid runs are not failures: they are counted in the opening line and
 * never enter a group. When no valid run in scope failed, the block draws nothing. */
import { attrs, count, esc, fmtPct, inline, num } from "../core";
import type { RenderContext } from "../model";
import { outcomeOf, trialAxes } from "../trial-model";
import type { TrialReport, TrialRun, TrialScenario } from "../trial-model";
import { clip, failureCause, FailureCause, failureDetail, invalidReason, judgeDecides, judgeFailed, oneLine, plainText, unmetChecks } from "../failure";
import { frame, FrameInput } from "./frame";

export interface FailuresInput extends FrameInput {
  /** Cases (scenario names) to include; default every case that ran. */
  cases?: string[];
  /** Arms to include; default every arm that ran. */
  arms?: string[];
  /** cause (default): one group per failed required check and one for the judge, each
   * broken down by case. case: one group per case, with its causes under it. */
  by?: "cause" | "case";
  /** Reasons quoted per row before the rest fold into a disclosure (default 1, at most 5). */
  reasons?: number;
}

interface Failed { run: TrialRun; i: number | undefined; cause: FailureCause; modes: string[]; judge: boolean }
interface Mode { key: string; kind: "check" | "judge" | "none"; check: string; runs: Failed[]; order: number }

/** A check name as code, with break opportunities after underscores so long names wrap between words. */
const codeName = (name: string, cls = "") => `<code${cls ? ` class="${cls}"` : ""}>${esc(name).replace(/_/g, "_<wbr>")}</code>`;
const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;
const list = (items: string[]) => items.length <= 1 ? items.join("") : `${items.slice(0, -1).join(", ")} and ${items[items.length - 1]}`;

export function failures(input: FailuresInput, ctx: RenderContext): string {
  if (!ctx.trial) throw new TypeError('A failures block needs trial data: supply the report spec\'s "trial" field (trialReport() does).');
  const data: TrialReport = ctx.trial;
  const axes = trialAxes(data);
  const caseLabel = (id: string) => ctx.caseLabels[id] || id;
  const wantArms = Array.isArray(input.arms) ? new Set(input.arms.map(String)) : null;
  const wantCases = Array.isArray(input.cases) ? new Set(input.cases.map(String)) : null;
  const arms = axes.arms.filter(a => !wantArms || wantArms.has(a)).sort((a, b) => ctx.arms.index(a) - ctx.arms.index(b));
  // Cases in the caller's order when given (a composition may pair variants), else the plan's.
  const cases = wantCases ? [...wantCases].filter(c => axes.cases.includes(c)) : axes.cases;
  const armAt = new Map(arms.map((a, i) => [a, i])), caseAt = new Map(cases.map((c, i) => [c, i]));
  const scenarios = new Map<string, TrialScenario>();
  for (const s of data.plan?.scenarios || []) if (s && typeof s.name === "string" && !scenarios.has(s.name)) scenarios.set(s.name, s);
  const scenarioOf = (r: TrialRun) => scenarios.get(r.scenario);

  const scope = (data.runs || []).filter(r => r && armAt.has(r.arm) && caseAt.has(r.scenario))
    .sort((a, b) => caseAt.get(a.scenario)! - caseAt.get(b.scenario)! || armAt.get(a.arm)! - armAt.get(b.arm)! || (num(a.repeat) ?? 0) - (num(b.repeat) ?? 0));
  const valid = scope.filter(r => outcomeOf(r) !== "invalid");
  const invalid = scope.filter(r => outcomeOf(r) === "invalid");
  const failed: Failed[] = scope.filter(r => outcomeOf(r) === "fail").map(run => {
    const sc = scenarioOf(run), cause = failureCause(run, sc), judge = judgeFailed(run, sc);
    const modes = [...unmetChecks(run, sc).map(u => `check:${u.name}`), ...(judge ? ["judge"] : [])];
    return { run, i: ctx.runIndex.get(run), cause, judge, modes: modes.length ? modes : ["none"] };
  });

  // Nothing failed: no panel at all. The composition leaves the section out, and
  // the invalid view and the figures already say what happened to every run.
  if (!failed.length) return "";

  // ------------------------------------------------------------ modes
  const modes = new Map<string, Mode>();
  for (const f of failed) for (const key of f.modes) {
    if (!modes.has(key)) modes.set(key, { key, kind: key === "judge" ? "judge" : key === "none" ? "none" : "check", check: key.startsWith("check:") ? key.slice(6) : "", runs: [], order: modes.size });
    modes.get(key)!.runs.push(f);
  }
  const ranked = [...modes.values()].sort((a, b) => Number(a.kind === "none") - Number(b.kind === "none") || b.runs.length - a.runs.length || a.order - b.order);
  const applies = (m: Mode, r: TrialRun): boolean => {
    const sc = scenarioOf(r);
    if (m.kind === "check") return !!sc && Array.isArray(sc.required) && sc.required.includes(m.check);
    if (m.kind === "judge") return judgeDecides(r, sc);
    return true;
  };
  const among = (m: Mode, pred: (r: TrialRun) => boolean) => valid.filter(r => applies(m, r) && pred(r)).length;
  const ids = new Map(ranked.map(m => [m.key, ctx.uid(`fx ${m.key}`)]));

  // ------------------------------------------------------------ pieces
  // Group titles sit one level under the section, or under the block's own title.
  const hx = input.title ? "h4" : "h3";
  const who = (f: Failed) => `${caseLabel(f.run.scenario)} · ${ctx.arms.label(f.run.arm)} · repeat ${num(f.run.repeat) ?? "?"}`;
  const mark = (f: Failed) => {
    const label = `${who(f)}: Failed. ${f.cause.text}`;
    return `<button type="button" class="av-run av-run--fail"${attrs({ "data-run": f.i, title: label, "aria-label": label })}></button>`;
  };
  const multiArm = arms.length > 1;
  /** The runs as marks, grouped behind each arm's glyph when several arms are shown. */
  const marks = (runs: Failed[]) => {
    if (!multiArm) return `<span class="av-fx-marks"><span class="av-fx-armruns">${runs.map(mark).join("")}</span></span>`;
    return `<span class="av-fx-marks">${arms.filter(a => runs.some(f => f.run.arm === a)).map(a => `<span class="av-fx-armruns">${ctx.arms.tag(a, { id: false })}${runs.filter(f => f.run.arm === a).map(mark).join("")}</span>`).join("")}</span>`;
  };
  /** Per-arm counts against the valid runs that could have failed this way; zeros stay, since the contrast between arms is the point. */
  const armCounts = (m: Mode | null, runs: Failed[], pred: (r: TrialRun) => boolean) => {
    if (!multiArm) return "";
    const chips = arms.map(a => {
      const n = m ? among(m, r => r.arm === a && pred(r)) : valid.filter(r => r.arm === a && pred(r)).length;
      if (!n) return "";
      const k = runs.filter(f => f.run.arm === a).length;
      return `<li class="av-fx-arm${k ? "" : " av-fx-arm--zero"}"${attrs({ "data-arm": a })}>${ctx.arms.tag(a, { id: false })}<span class="av-fx-armfrac"><b>${k}</b> of ${n}</span></li>`;
    }).join("");
    return chips ? `<ul class="av-fx-arms" aria-label="Failed this way, by arm">${chips}</ul>` : "";
  };

  /** The words a group of runs offers: the judge's reason for a judge cause,
   * otherwise a recorded detail; identical words are gathered with their runs,
   * most frequent first. */
  const reasonsFor = (m: Mode, runs: Failed[]) => {
    const groups: Array<{ text: string; label: string; runs: Failed[] }> = [];
    for (const f of runs) {
      let text = "", label = "";
      if (m.kind === "judge") { text = oneLine(f.run.judge?.reason); label = "Judge"; }
      else if (m.kind === "check") { const d = failureDetail(f.run, scenarioOf(f.run), m.check); if (d) { text = d.value; label = d.name; } }
      if (!text) continue;
      const g = groups.find(x => x.text === text && x.label === label);
      if (g) g.runs.push(f); else groups.push({ text, label, runs: [f] });
    }
    // The most common words or value first; ties keep the order the runs came in.
    return groups.sort((a, b) => b.runs.length - a.runs.length);
  };
  const shown = Math.max(1, Math.min(5, count(input.reasons) || 1));
  const quote = (m: Mode, g: { text: string; label: string; runs: Failed[] }, max: number) => {
    const body = m.kind === "judge" ? inline(clip(g.text, max)) : `<code class="av-fx-detail-name">${esc(g.label)}</code> <span class="av-fx-detail">${esc(clip(g.text, max))}</span>`;
    const first = g.runs[0];
    const cite = g.runs.length === 1
      ? `<button type="button" class="av-fx-cite"${attrs({ "data-run": first.i, "aria-label": `Open the run record: ${who(first)}` })}>${multiArm ? ctx.arms.glyph(first.run.arm) : ""}<span>${multiArm ? `${esc(ctx.arms.label(first.run.arm))} · ` : ""}repeat ${esc(num(first.run.repeat) ?? "?")}</span></button>`
      : `<span class="av-fx-cite av-fx-cite--many">${esc(m.kind === "judge" ? `${g.runs.length} runs got this reason` : `${g.runs.length} runs recorded this value`)}</span>`;
    return `<blockquote class="av-fx-quote av-fx-quote--${m.kind}">${m.kind === "judge" ? "" : '<span class="av-eyebrow">Recorded</span>'}<p>${body}</p><footer>${cite}</footer></blockquote>`;
  };
  const reasonBlock = (m: Mode, runs: Failed[]) => {
    const groups = reasonsFor(m, runs);
    if (!groups.length) {
      if (m.kind === "judge") return `<p class="av-fx-quiet">The judge gave no reason for ${runs.length === 1 ? "this run" : "these runs"}.</p>`;
      return "";
    }
    const head = groups.slice(0, shown).map(g => quote(m, g, 240)).join("");
    const rest = groups.slice(shown), listed = rest.slice(0, 60), unlisted = rest.length - listed.length;
    const more = rest.length
      ? `<details class="av-fx-more"><summary>${esc(m.kind === "judge" ? `${plural(rest.length, "more judge reason")}` : `${plural(rest.length, "other recorded value")}`)}</summary>${listed.map(g => quote(m, g, 600)).join("")}${unlisted ? `<p class="av-fx-quiet">${esc(`${unlisted} more: select a run's mark above, or read the run ledger.`)}</p>` : ""}</details>`
      : "";
    const unexplained = m.kind === "judge" ? runs.length - groups.reduce((n, g) => n + g.runs.length, 0) : 0;
    return `${head}${more}${unexplained ? `<p class="av-fx-quiet">${esc(plural(unexplained, "run"))} without a judge reason.</p>` : ""}`;
  };

  const modeTitle = (m: Mode, scoped: Failed[] = m.runs) => {
    if (m.kind === "judge") {
      const verdicts = new Set(scoped.map(f => oneLine(f.run.judge?.verdict)));
      return verdicts.size === 1 && verdicts.has("fail") ? "The judge said fail" : "The judge did not say pass";
    }
    if (m.kind === "none") return "Failed with no recorded cause";
    const states = new Map<string, number>();
    for (const f of scoped) for (const u of unmetChecks(f.run, scenarioOf(f.run))) if (u.name === m.check) states.set(u.state, (states.get(u.state) || 0) + 1);
    const only = states.size === 1 ? [...states.keys()][0] : "";
    const verb = only === "false" ? "was false" : only === "missing" ? "was not recorded" : "did not hold";
    return `${codeName(m.check)} ${verb}`;
  };
  const stateNote = (m: Mode, scoped: Failed[] = m.runs) => {
    if (m.kind !== "check") return "";
    const states = { false: 0, missing: 0, other: 0 } as Record<string, number>;
    for (const f of scoped) for (const u of unmetChecks(f.run, scenarioOf(f.run))) if (u.name === m.check) states[u.state]++;
    const parts = [states.false ? `false in ${plural(states.false, "run")}` : "", states.missing ? `not recorded in ${states.missing}` : "", states.other ? `neither true nor false in ${states.other}` : ""].filter(Boolean);
    return parts.length > 1 ? `<p class="av-fx-states">${esc(parts.join(", "))}</p>` : "";
  };
  const alsoNote = (m: Mode, scoped: Failed[] = m.runs) => {
    const other = new Map<string, number>();
    for (const f of scoped) for (const k of f.modes) if (k !== m.key) other.set(k, (other.get(k) || 0) + 1);
    if (!other.size) return "";
    const one = scoped.length === 1;
    const items = [...other.entries()].sort((a, b) => b[1] - a[1]).map(([k, n]) => `${k === "judge" ? "the judge" : codeName(k.slice(6))}${one ? "" : ` <span class="av-muted">${n} of ${scoped.length}</span>`}`);
    const shownItems = items.slice(0, 6), extra = items.length - shownItems.length;
    return `<p class="av-fx-also"><span class="av-fx-also-label">${one ? "This run also failed" : "Also failed in these runs"}:</span> ${shownItems.join(", ")}${extra ? `, and ${extra} more` : ""}</p>`;
  };
  const eyebrow = (m: Mode) => m.kind === "judge" ? "Judge" : m.kind === "none" ? "No recorded cause" : "Required check";
  const frac = (k: number, n: number) => `<span class="av-fx-frac"><b>${k}</b><span> of ${n}</span></span>`;

  // ------------------------------------------------------------ lede
  const failedCases = new Set(failed.map(f => f.run.scenario));
  const overlap = failed.some(f => f.modes.length > 1);
  const invalidBy = new Map<string, number>();
  for (const r of invalid) { const c = oneLine(r.invalid_reason) || (r.status && r.status !== "ok" ? oneLine(r.status) : "") || "unrecorded"; invalidBy.set(c, (invalidBy.get(c) || 0) + 1); }
  const invalidNote = invalid.length
    ? `<p class="av-fx-invalid"><span class="av-mark av-mark--invalid" aria-hidden="true"></span><span>Not counted: ${esc(plural(invalid.length, "invalid run"))} (${[...invalidBy.entries()].sort((a, b) => b[1] - a[1]).map(([c, n]) => `<code${attrs({ title: c === "unrecorded" ? "No reason was recorded." : plainText(invalidReason(c).text) })}>${esc(c)}</code> ${n}`).join(", ")}) had no valid result. ${invalid.length === 1 ? "It is" : "They are"} not failures and ${invalid.length === 1 ? "is" : "are"} left out of every count here.</span></p>`
    : "";
  const lede = `<div class="av-fx-lede"><p class="av-fx-headline"><span class="av-fx-big">${failed.length}</span><span>of ${valid.length} valid ${valid.length === 1 ? "run" : "runs"} failed <span class="av-muted">(${esc(fmtPct(failed.length / Math.max(1, valid.length)))})</span>, in ${failedCases.size} of ${cases.length} ${cases.length === 1 ? "case" : "cases"}${input.by === "case" ? "" : `, from ${plural(ranked.length, "cause")}`}.</span></p>${overlap ? `<p class="av-fx-hint">A run that failed more than one way is listed under each cause, so the groups add up to more than ${failed.length}.</p>` : ""}${invalidNote}</div>`;
  const legend = `<p class="av-legend"><span><span class="av-mark av-mark--fail" aria-hidden="true"></span>one failed run; select it for its record</span><span><span class="av-fx-frac"><b>k</b> of n</span>failed this way, of the valid runs that could have</span></p>`;

  // ------------------------------------------------------------ by cause
  const byCause = () => {
    const index = ranked.length >= 3
      ? `<ol class="av-fx-index" aria-label="Causes, most frequent first">${ranked.map(m => `<li><a href="#${esc(ids.get(m.key)!)}"><span class="av-fx-index-name">${m.kind === "check" ? `${codeName(m.check)}` : esc(m.kind === "judge" ? "judge" : "no recorded cause")}</span><span class="av-fx-index-bar" aria-hidden="true" style="--w:${(m.runs.length / ranked[0].runs.length * 100).toFixed(1)}%"></span><span class="av-fx-index-n">${m.runs.length}</span></a></li>`).join("")}</ol>`
      : "";
    const groups = ranked.map(m => {
      const n = among(m, () => true);
      const where = cases.filter(c => m.runs.some(f => f.run.scenario === c)).map(c => ({ c, runs: m.runs.filter(f => f.run.scenario === c) }))
        .sort((a, b) => b.runs.length - a.runs.length || caseAt.get(a.c)! - caseAt.get(b.c)!);
      // Cases with at least one valid run that could have failed this way.
      const applicable = cases.filter(c => valid.some(r => r.scenario === c && applies(m, r)));
      const scopeText = m.kind === "check"
        ? `valid runs in the ${applicable.length === 1 ? "case that requires" : `${applicable.length} cases that require`} it`
        : m.kind === "judge" ? "valid runs the judge decides" : "valid runs";
      const rows = where.map(({ c, runs }) => {
        const k = runs.length, cn = among(m, r => r.scenario === c);
        return `<li class="av-fx-row"><div class="av-fx-row-head"><span class="av-case-name">${esc(caseLabel(c))}</span>${caseLabel(c) !== c ? `<code class="av-fx-id">${esc(c)}</code>` : ""}${frac(k, cn)}</div>${marks(runs)}${reasonBlock(m, runs)}</li>`;
      }).join("");
      const quiet = m.kind === "none" ? `<p class="av-fx-quiet">Every required check held and no judge failed these runs, yet trial.py recorded them as failed. Their native records may say why.</p>` : "";
      const untouched = m.kind === "check" && applicable.length > where.length ? `<p class="av-fx-quiet">No run failed it in ${list(applicable.filter(c => !where.some(w => w.c === c)).slice(0, 4).map(c => esc(caseLabel(c))))}${applicable.length - where.length > 4 ? ` and ${applicable.length - where.length - 4} more` : ""}.</p>` : "";
      return `<li class="av-fx-mode av-fx-mode--${m.kind}" id="${esc(ids.get(m.key)!)}"><div class="av-fx-head"><span class="av-fx-count"><b>${m.runs.length}</b><span>${m.runs.length === 1 ? "run" : "runs"}</span></span><div class="av-fx-title-wrap"><span class="av-eyebrow">${esc(eyebrow(m))}</span><${hx} class="av-fx-title">${modeTitle(m)}</${hx}><p class="av-fx-scope">${frac(m.runs.length, n)} <span>${esc(scopeText)}</span></p>${stateNote(m)}${armCounts(m, m.runs, () => true)}${alsoNote(m)}</div></div><div class="av-fx-body">${quiet}<ul class="av-fx-rows">${rows}</ul>${untouched}</div></li>`;
    }).join("");
    return `${index}<ol class="av-fx-modes">${groups}</ol>`;
  };

  // ------------------------------------------------------------ by case
  const byCase = () => {
    const groups = cases.filter(c => failedCases.has(c)).map(c => {
      const runs = failed.filter(f => f.run.scenario === c);
      const n = valid.filter(r => r.scenario === c).length;
      const local = ranked.filter(m => m.runs.some(f => f.run.scenario === c)).map(m => ({ m, runs: m.runs.filter(f => f.run.scenario === c) }))
        .sort((a, b) => Number(a.m.kind === "none") - Number(b.m.kind === "none") || b.runs.length - a.runs.length || a.m.order - b.m.order);
      const rows = local.map(({ m, runs: rs }) => `<li class="av-fx-row"><div class="av-fx-row-head"><span class="av-fx-row-kind">${esc(eyebrow(m))}</span><span class="av-fx-row-title">${modeTitle(m, rs)}</span>${frac(rs.length, among(m, r => r.scenario === c))}</div>${stateNote(m, rs)}${marks(rs)}${reasonBlock(m, rs)}${alsoNote(m, rs)}</li>`).join("");
      return `<li class="av-fx-mode av-fx-mode--case"><div class="av-fx-head"><span class="av-fx-count"><b>${runs.length}</b><span>of ${n}</span></span><div class="av-fx-title-wrap"><span class="av-eyebrow">Case</span><${hx} class="av-fx-title">${esc(caseLabel(c))}${caseLabel(c) !== c ? ` <code class="av-fx-id">${esc(c)}</code>` : ""}</${hx}><p class="av-fx-scope">${esc(`${runs.length} of ${n} valid ${n === 1 ? "run" : "runs"} failed, from ${plural(local.length, "cause")}`)}</p>${armCounts(null, runs, r => r.scenario === c)}</div></div><div class="av-fx-body"><ul class="av-fx-rows">${rows}</ul></div></li>`;
    }).join("");
    const clean = cases.filter(c => !failedCases.has(c) && valid.some(r => r.scenario === c));
    const cleanNote = clean.length ? `<p class="av-fx-clean"><span class="av-mark av-mark--pass" aria-hidden="true"></span><span>${esc(plural(clean.length, "case"))} had no failed run: ${list(clean.slice(0, 8).map(c => esc(caseLabel(c))))}${clean.length > 8 ? ` and ${clean.length - 8} more` : ""}.</span></p>` : "";
    return `<ol class="av-fx-modes">${groups}</ol>${cleanNote}`;
  };

  const by = input.by === "case" ? "case" : "cause";
  return frame("failures", input, `${lede}${legend}${by === "case" ? byCase() : byCause()}`, { "data-by": by });
}
