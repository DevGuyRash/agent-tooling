/** The shared frame every block sits in: an optional heading, description and
 * note, so blocks read alike without each one inventing its own chrome. */
import { attrs, esc, num, outcomeLabel, prose, tipAttr } from "../core";
import type { RenderContext } from "../model";
import { outcomeOf } from "../trial-model";
import type { TrialRun } from "../trial-model";
import { readHtml } from "../reading";
import type { Reading } from "../reading";

export interface FrameInput { title?: string; description?: string | string[]; note?: string; id?: string; read?: Reading }

/** `readAs` names the view whose explanation the frame carries when its look borrows another kind's class. */
export function frame(kind: string, input: FrameInput, body: string, extra: Record<string, string | boolean | undefined> = {}, readAs = kind): string {
  const head = input.title || input.description
    ? `<header class="av-block-head">${input.title ? `<h3 class="av-block-title">${esc(input.title)}</h3>` : ""}${prose(input.description, "av-block-desc")}</header>`
    : "";
  const note = input.note ? `<p class="av-block-note">${esc(input.note)}</p>` : "";
  // Every view says what it shows and how to read it; the author adds what this data says.
  return `<section${attrs({ class: `av-block av-block--${kind}`, id: input.id, ...extra })}>${head}${readHtml(readAs, input.read)}${body}${note}</section>`;
}

/** A block that has nothing to show says so, rather than disappearing. */
export function empty(message: string): string {
  return `<p class="av-empty">${esc(message)}</p>`;
}

export { pos } from "../core";

/** A run mark's hover card: the case it ran (what was tested) and its repeat above, its arm beside the arm's mark, then
 * its outcome and what the view adds. Selecting the mark opens the run's record. */
export function runCard(ctx: RenderContext, run: TrialRun, rows: Array<[string, string]> = []): string {
  return tipAttr({ over: `${ctx.caseLabels[run.scenario] || run.scenario} · repeat ${num(run.repeat) ?? "?"}`, title: ctx.arms.label(run.arm), mark: ctx.arms.mark(run.arm), rows: [["Outcome", outcomeLabel[outcomeOf(run)]], ...rows], note: "Select it to open the run's record." });
}
