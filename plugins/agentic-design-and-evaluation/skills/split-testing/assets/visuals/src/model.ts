/** Report specification, render context and arm identity. A report is a list
 * of sections, each a list of blocks; a block names its type and carries its
 * own data, so reports are composed from data rather than written per trial. */
import { attrs, esc, slug } from "./core";
import type { TrialReport, TrialRun } from "./trial-model";
import type { Problem } from "./validate";

export interface ArmSpec { id: string; label?: string; note?: string }
export interface MetaItem { label: string; value: string }
export interface BlockSpec { type: string; [field: string]: unknown }
export interface SectionSpec {
  id?: string;
  /** Section heading. */
  title: string;
  /** Short label for the section index; defaults to the title. */
  label?: string;
  lead?: string | string[];
  blocks: BlockSpec[];
}
export interface ReportSpec {
  title: string;
  kicker?: string;
  summary?: string | string[];
  meta?: MetaItem[];
  /** Identity order for arms: color and shape follow this order everywhere. */
  arms?: ArmSpec[];
  sections: SectionSpec[];
  footer?: string;
  /** Trial data for trial blocks and the run drawer; trialReport() sets it. */
  trial?: TrialReport;
  /** Readable labels for trial cases (scenarios), keyed by scenario name. */
  cases?: Record<string, string>;
  /** Problems found while composing (trialReport() puts the narrative's here);
   * renderReport() lists them with the specification's own in one visible panel. */
  problems?: Problem[];
}

const SHAPES = ["circle", "square", "diamond", "triangle", "hexagon", "triangle-down", "star", "cross"];

/** Stable identity per arm: one color and one shape, the same in every view. */
export class ArmRegistry {
  private order: string[] = [];
  private info = new Map<string, ArmSpec>();
  constructor(arms: ArmSpec[] = []) { for (const a of arms) this.add(a.id, a); }
  add(id: string, spec?: Partial<ArmSpec>): void {
    if (!this.info.has(id)) { this.order.push(id); this.info.set(id, { id }); }
    if (spec) this.info.set(id, { ...this.info.get(id)!, ...Object.fromEntries(Object.entries(spec).filter(([, v]) => v !== undefined)) });
  }
  ids(): string[] { return this.order.slice(); }
  index(id: string): number { if (!this.info.has(id)) this.add(id); return this.order.indexOf(id); }
  label(id: string): string { return this.info.get(id)?.label || id; }
  note(id: string): string | undefined { return this.info.get(id)?.note; }
  color(id: string): string { return `var(--av-arm-${this.index(id) % 8})`; }
  shape(id: string): string { const i = this.index(id); return SHAPES[(i + Math.floor(i / 8)) % SHAPES.length]; }
  /** A small colored shape that identifies an arm without relying on color. */
  glyph(id: string, extra = ""): string {
    return `<span class="av-glyph${extra ? " " + extra : ""}" data-shape="${this.shape(id)}" style="--c:${this.color(id)}" aria-hidden="true"></span>`;
  }
  /** Glyph and label; the raw id stays visible when a label replaces it. */
  tag(id: string, opts: { id?: boolean } = {}): string {
    const label = this.label(id), showId = opts.id !== false && label !== id;
    return `<span class="av-arm"${attrs({ "data-arm": id, style: `--c:${this.color(id)}` })}>${this.glyph(id)}<span class="av-arm-label">${esc(label)}</span>${showId ? `<code class="av-arm-id">${esc(id)}</code>` : ""}</span>`;
  }
}

export interface RenderContext {
  arms: ArmRegistry;
  trial?: TrialReport;
  /** Runs addressable by index from marks, the ledger and the drawer. */
  runs: TrialRun[];
  runIndex: Map<TrialRun, number>;
  /** Labels for scenarios (cases) where the narrative supplies them. */
  caseLabels: Record<string, string>;
  uid(base: string): string;
}

export function createContext(spec: Pick<ReportSpec, "arms" | "trial">, caseLabels: Record<string, string> = {}): RenderContext {
  const arms = new ArmRegistry(spec.arms || []);
  const runs = spec.trial?.runs || [];
  for (const r of runs) if (typeof r.arm === "string") arms.add(r.arm);
  const used = new Map<string, number>();
  return {
    arms, trial: spec.trial, runs, runIndex: new Map(runs.map((r, i) => [r, i])), caseLabels,
    uid(base: string): string {
      const id = slug(base), n = used.get(id) || 0;
      used.set(id, n + 1);
      return n ? `${id}-${n}` : id;
    },
  };
}
