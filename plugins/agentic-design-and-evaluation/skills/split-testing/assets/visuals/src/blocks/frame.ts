/** The shared frame every block sits in: an optional heading, description and
 * note, so blocks read alike without each one inventing its own chrome. */
import { attrs, esc, prose } from "../core";

export interface FrameInput { title?: string; description?: string | string[]; note?: string; id?: string }

export function frame(kind: string, input: FrameInput, body: string, extra: Record<string, string | boolean | undefined> = {}): string {
  const head = input.title || input.description
    ? `<header class="av-block-head">${input.title ? `<h3 class="av-block-title">${esc(input.title)}</h3>` : ""}${prose(input.description, "av-block-desc")}</header>`
    : "";
  const note = input.note ? `<p class="av-block-note">${esc(input.note)}</p>` : "";
  return `<section${attrs({ class: `av-block av-block--${kind}`, id: input.id, ...extra })}>${head}${body}${note}</section>`;
}

/** A block that has nothing to show says so, rather than disappearing. */
export function empty(message: string): string {
  return `<p class="av-empty">${esc(message)}</p>`;
}

/** Percent position for CSS custom properties, clamped to the track. */
export function pos(x: number): string {
  return `${(Math.max(0, Math.min(1, x)) * 100).toFixed(3)}%`;
}
