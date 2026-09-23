import type { ChartContext } from "./categories";
/** Presentation inputs contain observations and interpretations supplied by the caller. */
export type Status = "supported" | "conditional" | "uncertain" | "missing" | "failed" | "not-applicable";
export interface EvidenceRef { label: string; href?: string; note?: string }
export interface Annotation { note?: string; evidence?: EvidenceRef[] }
export interface Meta extends Annotation { context?: ChartContext; /** Optional stable document ID for links and reader records. */ id?: string; title: string; description?: string; limitations?: string[]; collapsible?: boolean; open?: boolean }
export interface Cell extends Annotation { value: string | number | null; status?: Status }
export interface Named extends Annotation { id: string; label: string }
export interface TableInput extends Meta { columns: string[]; rows: Cell[][] }
export interface MatrixInput extends Meta {
  alternatives: Named[]; dimensions: Named[];
  findings: (Cell & { alternative: string; dimension: string })[];
}
export interface NumericObservation extends Annotation { label: string; value: number | null; status?: Status }
export interface DistributionInput extends Meta { axis: string; unit?: string; groups: { id?: string; label: string; observations: NumericObservation[] }[] }
export interface IntervalInput extends Meta {
  axis: string; unit?: string; intervalLabel: string;
  items: (Annotation & { label: string; low?: number | null; high?: number | null; estimate?: number | null })[];
}
export interface PairedInput extends Meta {
  axis: string; unit?: string; leftLabel: string; rightLabel: string;
  pairs: (Annotation & { label: string; left: number | null; right: number | null })[];
}
export interface XYPoint extends Annotation { label: string; x: number | null; y: number | null }
export interface TrajectoryInput extends Meta {
  xAxis: string; yAxis: string; xUnit?: string; yUnit?: string;
  series: { id?: string; label: string; points: XYPoint[] }[];
}
export interface ScatterInput extends Meta {
  /** Explicit reader/author scope; known coordinates remain the default domain. */
  coordinateScope?: "known" | "complete";
  xAxis: string; yAxis: string; xUnit?: string; yUnit?: string;
  points: (XYPoint & { id: string; group?: string; groupId?: string })[];
  /** Caller-approved links only; no optimization, ranking, or frontier inference. */
  frontiers?: (Annotation & { label: string; pointIds: string[] })[];
}
export interface HeatmapInput extends Meta {
  rows: Named[]; columns: Named[]; unit?: string;
  cells: (Annotation & { row: string; column: string; value: number | null; status?: Status })[];
}
export interface ConditionalInput extends Meta { items: (Annotation & { condition: string; implication: string; status?: Status })[] }
export interface ExcerptInput extends Meta {
  items: (Annotation & { label: string; text: string; context?: string; status?: Status })[];
}
export interface DisagreementInput extends Meta {
  topics: (Annotation & { topic: string; positions: (Annotation & { contributor: string; position: string; status?: Status })[]; disposition?: string })[];
}
export interface LineageInput extends Meta {
  /** Natural fit keeps graph typography from growing when a layout becomes narrower. */
  fit?: 'natural' | 'width';
  nodes: (Named & { kind: string; detail?: string })[];
  edges: (Annotation & { id?: string; from: string; to: string; relation: string })[];
}
export interface FailureInput extends Meta {
  categories: (Annotation & { label: string; definition: string; alternative?: string; frequency?: string; impact?: string; conditions?: string; cases: (Annotation & { label: string; outcome: string })[] })[];
}
export interface ScenarioInput extends Meta {
  scenarios: (Annotation & { label: string; condition: string; outcomes: (Annotation & { alternative: string; outcome: string; status?: Status })[]; tradeoff?: ScatterInput })[];
}
export interface ArtifactInput extends Meta {
  artifacts: (Annotation & { label: string; mediaType: string; text?: string; imageData?: string; alt?: string })[];
}
export interface UncertaintyInput extends Meta { items: (Annotation & { label: string; reason: string; status?: Status })[] }
export interface EffortInput extends Meta {
  items: (Annotation & { label: string; stage: string; measure: string; value: number | null; unit: string; scope: string })[];
}
export interface FreshnessInput extends Meta {
  events: (Annotation & { label: string; source: string; date: string | null; event: string; assessment?: string })[];
}
export interface UnknownsInput extends Meta {
  alternatives: Named[];
  issues: (Annotation & { label: string; relevance: string; affected: (Annotation & { alternative: string; consequence: string })[] })[];
}
export interface ConfidenceInput extends Meta {
  claims: (Annotation & { claim: string; judgment: string; basis: (Annotation & { dimension: string; observation: string })[] })[];
}
export interface ReliabilityInput extends Meta {
  conditions: Named[]; behaviors: Named[];
  observations: (Cell & { condition: string; behavior: string })[];
}
export interface DecisionHistoryInput extends Meta {
  decisions: (Annotation & { label: string; when: string; decision: string; availableThen: string; changesSince?: string; supersedes?: string })[];
}
/** Declarative extensions cannot introduce raw HTML, scripts, styles, or remote media. */
export type ExtensionBlock =
  | { kind: "narrative"; text: string }
  | { kind: "table"; input: TableInput }
  | { kind: "scatter"; input: ScatterInput }
  | { kind: "excerpts"; input: ExcerptInput };
export interface ExtensionInput extends Meta { purpose: string; blocks: ExtensionBlock[] }
