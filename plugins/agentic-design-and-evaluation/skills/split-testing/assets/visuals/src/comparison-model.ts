/** A comparison of any alternatives: what the generic composer and views read.
 * Nothing here assumes agents, runs or pass/fail. An alternative can be a
 * prompt, a sandwich, an ad, a game mechanic or a research direction; a case is
 * any context it was tried in; a metric is anything observed about it. */

/** How a metric's values are read. "count" is successes out of trials
 * (conversions of impressions); "rank" is a position where 1 is first;
 * "preference" values come from head-to-head judgments, not observations. */
export type MetricKind = "binary" | "numeric" | "ordinal" | "count" | "rank" | "preference";

export interface Metric {
  id: string;
  label?: string;
  kind: MetricKind;
  /** Which way is better. "none" (the default) never colors a value as good or bad. */
  better?: "higher" | "lower" | "none";
  unit?: string;
  /** Ordinal levels in order, lowest first. */
  levels?: string[];
  /** The metric the decision rests on; at most one should be primary. */
  primary?: boolean;
  description?: string;
  /** A decision threshold in the metric's own units (a share in 0–1 for binary and count). */
  threshold?: number;
}

export interface Alternative {
  id: string;
  label?: string;
  description?: string;
  /** Nested groups, outermost first, such as ["Direction A", "Concept 2"]. A string is one level. */
  group?: string[] | string;
  /** Recorded settings or attributes; differences between alternatives are shown. */
  attributes?: Record<string, string | number | boolean | null>;
  /** The full text of what was compared (instructions, ad copy, a design brief), for side-by-side diffs. */
  content?: string;
  note?: string;
}

export interface Case {
  id: string;
  label?: string;
  description?: string;
  /** Nested groups for cases too (segments, regions, rounds). */
  group?: string[] | string;
}

/** One observation of one alternative on one metric. */
export interface Observation {
  alternative: string;
  metric: string;
  case?: string;
  /** binary: boolean; numeric: number; count: successes (with n); ordinal: a level name or its index; rank: position, 1 first. */
  value: boolean | number | string | null;
  /** Trials behind a count value. */
  n?: number;
  /** Which repeat, rater, session or unit this came from. */
  unit?: string | number;
  /** false marks an observation that produced no valid value; it is counted, never treated as a failure. */
  valid?: boolean;
  invalid_reason?: string;
  note?: string;
  /** A short quotation or output excerpt behind the value. */
  excerpt?: string;
  /** Where the observation came from (a file, a link, a person, a tool). */
  source?: string;
  id?: string;
}

/** A summary when only totals exist (an ad platform's report, a published table). */
export interface Aggregate {
  alternative: string;
  metric: string;
  case?: string;
  /** binary and count: successes and trials. */
  k?: number;
  n?: number;
  /** numeric: summary statistics over n observations. */
  mean?: number;
  sd?: number;
  median?: number;
  /** An interval the source itself reported, drawn as given. */
  lo?: number;
  hi?: number;
  /** ordinal: observations per level name. */
  counts?: Record<string, number>;
  source?: string;
  note?: string;
}

/** One head-to-head judgment between two alternatives. */
export interface Preference {
  a: string;
  b: string;
  /** The preferred alternative's id, "tie", or null when no judgment was reached. */
  winner: string | null;
  case?: string;
  /** The criterion judged, matching a preference metric's id; omitted means the comparison's overall preference. */
  metric?: string;
  judge?: string;
  note?: string;
}

/** A full ordering by one judge, first place first. */
export interface Ranking {
  order: string[];
  case?: string;
  metric?: string;
  judge?: string;
}

export interface Comparison {
  title?: string;
  question?: string;
  summary?: string | string[];
  alternatives: Alternative[];
  cases?: Case[];
  metrics: Metric[];
  observations?: Observation[];
  aggregates?: Aggregate[];
  preferences?: Preference[];
  rankings?: Ranking[];
  /** The alternative others are compared against. */
  baseline?: string;
  /** Alternatives given identical material: the spread between them is chance alone. */
  identical?: string[][];
  /** The rule fixed before results, quoted verbatim. */
  decision_rule?: string;
  sources?: Array<{ label: string; href?: string; note?: string }>;
}

/** One alternative's summary on one metric, over the observations a filter keeps. */
export interface MetricSummary {
  alternative: string;
  metric: string;
  kind: MetricKind;
  /** Valid observations (or trials for binary/count aggregates). */
  n: number;
  invalid: number;
  /** binary/count: successes and the rate with its 95% Wilson interval. */
  k?: number;
  rate?: number | null;
  /** numeric: mean and median with a 95% interval for the mean. */
  mean?: number | null;
  median?: number | null;
  sd?: number | null;
  /** The interval for the headline value: rate, mean, mean rank, or win rate. */
  interval?: [number, number] | null;
  /** ordinal: observations per level, in level order. */
  counts?: number[];
  /** rank: mean position and share of first places; preference: wins over decisive judgments. */
  meanRank?: number | null;
  firstShare?: number | null;
  wins?: number;
  losses?: number;
  ties?: number;
  /** True when the summary came from supplied aggregates rather than observations. */
  fromAggregate?: boolean;
  /** The individual values, when observations exist (for distributions). */
  values?: number[];
  /** How the interval was found, in words a reader can check ("95% Wilson score interval", "as reported by the source"). */
  intervalMethod?: string;
  /** ordinal: the level names counts follow, lowest first, and the level where the cumulative share first reaches one half. */
  levels?: string[];
  medianLevel?: string | null;
  /** Invalid observations (or unreached judgments) by reason. */
  invalidReasons?: Record<string, number>;
}

/** A difference between two alternatives on one metric. */
export interface MetricDifference {
  metric: string;
  a: string;
  b: string;
  /** a minus b in the metric's headline units: rate points as a share, mean units, or, for ordinal, P(a > b) + ½P(tie) − ½. */
  estimate: number | null;
  interval: [number, number] | null;
  /** How the interval was computed, in words a reader can check. */
  method: string;
  kind?: MetricKind;
  /** Valid observations (or decisive judgments) behind each side, a then b. */
  n?: [number, number];
  /** numeric: the difference in medians with a seeded percentile bootstrap interval, when observations exist on both sides. */
  median?: { estimate: number | null; interval: [number, number] | null; method: string };
}

/** Narrows what a summary reads. groups and caseGroups are group-path prefixes, outermost first:
 * ["Direction A"] keeps everything inside Direction A, ["Direction A", "Concept 2"] one concept. */
export interface ComparisonFilter { cases?: string[]; groups?: string[]; alternatives?: string[]; caseGroups?: string[] }
