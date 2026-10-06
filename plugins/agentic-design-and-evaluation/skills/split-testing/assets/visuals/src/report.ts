/** The block registry and the report shell: masthead, section index, numbered
 * sections and the run drawer's container. renderReport() is a pure string
 * function; mount() in enhance.ts adds behavior in a browser. */
import { esc, prose } from "./core";
import { createContext, RenderContext, ReportSpec, BlockSpec, SectionSpec } from "./model";
import * as T from "./blocks/trial";
import * as G from "./blocks/general";
import { setup } from "./blocks/setup";
import { cases } from "./blocks/cases";
import { failures } from "./blocks/failures";
import { contrast } from "./blocks/contrast";
import * as C from "./blocks/compare";
import * as J from "./blocks/judgments";
import { renderProblems, validateSpec } from "./validate";

export type BlockRenderer = (input: any, ctx: RenderContext) => string;
const registry = new Map<string, BlockRenderer>();

/** Add or replace a block type; returns a function that restores the previous one. */
export function registerBlock(type: string, render: BlockRenderer): () => void {
  if (!/^[a-z][a-z0-9-]*$/.test(type)) throw new TypeError("A block type is lowercase letters, digits and hyphens, starting with a letter.");
  const previous = registry.get(type);
  registry.set(type, render);
  return () => { if (previous) registry.set(type, previous); else registry.delete(type); };
}
export function blockTypes(): string[] { return [...registry.keys()].sort(); }

for (const [type, fn] of Object.entries({
  verdict: T.verdict, figures: T.figures, ladder: T.ladder, tapestry: T.tapestry, checks: T.checks,
  pairwise: T.pairwise, cost: T.cost, invalid: T.invalid, ledger: T.ledger, plan: T.plan,
  text: G.text, callout: G.callout, list: G.list, facts: G.facts, table: G.table, matrix: G.matrix,
  intervals: G.intervals, bars: G.bars, trend: G.trend, excerpts: G.excerpts, diagram: G.diagram,
  setup, cases, failures, contrast,
  scorecard: C.scorecard, metric: C.metric, difference: C.difference, hierarchy: C.hierarchy,
  alternatives: J.alternatives, preferences: J.preferences, "decision-matrix": J.decisionMatrix, observations: J.observations,
} as Record<string, BlockRenderer>)) registry.set(type, fn);

/** Render one block. An unknown type or a renderer error renders as a visible
 * notice in place of the block, so a report never silently drops evidence. */
export function renderBlock(block: BlockSpec, ctx: RenderContext): string {
  const fn = registry.get(block?.type);
  if (!fn) return `<div class="av-block av-block-error" role="note"><strong>Unknown block type “${esc(block?.type ?? "")}”.</strong> Valid types: ${blockTypes().map(t => `<code>${t}</code>`).join(", ")}.</div>`;
  try { return fn(block, ctx); }
  catch (error) { return `<div class="av-block av-block-error" role="note"><strong>The ${esc(block.type)} block could not render.</strong> ${esc(error instanceof Error ? error.message : String(error))}</div>`; }
}

export function renderReport(spec: ReportSpec): string {
  if (!spec || typeof spec.title !== "string" || !Array.isArray(spec.sections)) throw new TypeError("A report needs a title and a sections array.");
  const ctx = createContext(spec, spec.cases || {});
  // A malformed section entry renders as a visible notice in its place; the rest of the report still renders.
  const sections = spec.sections.map((raw, i) => {
    const s = (raw && typeof raw === "object" ? raw : {}) as Partial<SectionSpec>;
    const title = typeof s.title === "string" && s.title ? s.title : `Section ${i + 1}`;
    const problem = !raw || typeof raw !== "object" ? "This section entry is not an object." : !Array.isArray(s.blocks) ? "This section has no blocks list." : "";
    return { ...s, title, blocks: Array.isArray(s.blocks) ? s.blocks : [], problem, id: typeof s.id === "string" && /^[A-Za-z][\w:.-]*$/.test(s.id) ? s.id : ctx.uid(title), n: String(i + 1).padStart(2, "0") };
  });
  const toc = sections.map(s => `<li><a href="#${esc(s.id)}"><span class="av-toc-n">${s.n}</span><span class="av-toc-label">${esc(s.label || s.title)}</span></a></li>`).join("");
  const metaItems = (Array.isArray(spec.meta) ? spec.meta : []).filter(m => m && typeof m === "object");
  const meta = metaItems.length ? `<dl class="av-meta">${metaItems.map(m => `<div><dt>${esc(m.label)}</dt><dd>${esc(m.value)}</dd></div>`).join("")}</dl>` : "";
  const body = sections.map(s => `<section class="av-section" id="${esc(s.id)}" aria-labelledby="${esc(s.id)}-h"><header class="av-section-head"><span class="av-section-n" aria-hidden="true">${s.n}</span><div><h2 id="${esc(s.id)}-h" class="av-section-title">${esc(s.title)}</h2>${prose(s.lead, "av-section-lead")}</div></header>${s.problem ? `<div class="av-block av-block-error" role="note"><strong>${esc(s.problem)}</strong> Each section needs a title and a blocks list.</div>` : ""}${s.blocks.map(b => renderBlock(b, ctx)).join("")}</section>`).join("");
  return `<div class="av-report" data-av-report>
<a class="av-skip" href="#${esc(sections[0]?.id || "top")}">Skip to the first section</a>
<header class="av-topbar"><div class="av-topbar-inner"><a class="av-brand" href="#av-top"><span class="av-brand-mark" aria-hidden="true"></span><span class="av-brand-text">${esc(spec.kicker || "Report")}</span></a><nav class="av-toc" aria-label="Sections"><ol>${toc}</ol></nav><button type="button" class="av-theme-toggle" data-av-theme-toggle hidden><span class="av-theme-icon" aria-hidden="true"></span><span class="av-theme-word">Auto</span></button></div></header>
<header class="av-masthead" id="av-top"><div class="av-masthead-inner">${spec.kicker ? `<p class="av-kicker">${esc(spec.kicker)}</p>` : ""}<h1 class="av-title">${esc(spec.title)}</h1>${prose(spec.summary, "av-summary")}${meta}</div></header>
<main class="av-sections">${renderProblems([...(Array.isArray(spec.problems) ? spec.problems.filter(p => p && typeof p === "object") : []), ...validateSpec(spec)])}${body}</main>
<footer class="av-footer"><p>${esc(spec.footer || "A self-contained report: every view is drawn from the data embedded in this file, and each run names its native record.")}</p></footer>
<dialog class="av-drawer" data-av-drawer aria-labelledby="av-drawer-title"><div class="av-drawer-inner" data-av-drawer-body></div></dialog>
</div>`;
}
