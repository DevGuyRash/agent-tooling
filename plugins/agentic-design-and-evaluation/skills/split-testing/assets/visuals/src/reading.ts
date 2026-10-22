/** What every report needs for a reader who has never heard of the work: the
 * story before the results, and with every view what it shows, how to read it
 * and what this data says. The library writes "shows" and "how" for each of its
 * views; the author writes the story and what each view says here. */
import { esc, inline, prose } from "./core";
import type { RenderContext } from "./model";

export interface Reading { shows?: string | string[]; how?: string | string[]; says?: string | string[] }
export interface Story {
  /** What a newcomer needs to know first, naming every alternative in plain words. */
  background: string | string[];
  /** What the person deciding wanted, quoted where it was recorded. */
  intent: string | string[];
  /** The questions or theories the work set out to test. */
  questions: string[];
  /** How the decision was to be made, in plain words. */
  rule?: string | string[];
  covers: string | string[];
  notCovered: string | string[];
  /** Each alternative (arm) and each case, by id, in plain words: what it is, why it exists, what it checks. */
  alternatives?: Record<string, string | string[]>;
  cases?: Record<string, string | string[]>;
  glossary?: Array<{ term: string; meaning: string | string[] }>;
}

/** The library's own words for each view: what it shows and how to read it. */
export const READING: Record<string, { shows: string; how: string }> = {
  verdict: { shows: "The decision, the rule it was held to, and the limits of the evidence behind it.", how: "The stamp is the decision and the headline says it in a sentence. “The decision holds when” lists the conditions it depends on; “What this evidence does not show” lists what a reader should not conclude; “What would change the decision” lists the evidence that would. The box beside it quotes the rule as it was fixed before any result, with each of its terms marked met or not met." },
  figures: { shows: "The headline numbers of the report.", how: "Each tile is one count or measure with its label; read the notes under a tile for what it includes. Invalid runs are counted apart, never as failures." },
  ladder: { shows: "How often each setup passed, with the range its true pass rate likely falls in.", how: "Each row is one setup. The dot is its pass rate over valid runs and the band around it is the 95% interval: the narrower the band, the more runs back it. Where two bands overlap a lot, the difference between those setups could be chance. Fewer than five valid runs are flagged; a dashed line marks the reference setup's rate." },
  tapestry: { shows: "Every run as one mark, by case and setup.", how: "A filled circle passed, a hollow ring failed, a struck-through square was invalid (it has no result). Select a mark to read that run. A difference that sits in one case reads differently from one spread across all of them." },
  checks: { shows: "How often each check held for each setup.", how: "Each row is one check, each column a setup; the number is how many valid runs met it out of how many it applied to. Required checks decide whether a run passes; the others are recorded measures that never decide a pass." },
  pairwise: { shows: "A judge's choice between two setups' outputs on the same case, asked in both orders.", how: "Only pairs decided the same way in both orders count as wins; pairs decided differently by order are counted apart as inconsistent, and ties apart again." },
  cost: { shows: "What each run used: tokens, time, commands or money, as its executor reported them.", how: "Each dot is one valid run; the bar marks the middle half of the runs and the line their median. Compare like with like: different executors report different fields." },
  invalid: { shows: "Runs that produced no result, and why.", how: "An invalid run is neither a pass nor a failure: it is left out of every rate. The reason says what went wrong and what would give the run a result." },
  ledger: { shows: "Every run in one table.", how: "Filter by outcome, setup or case, or search; select a row to open the run with its checks, the judge's reason, an excerpt of its output and where its full record lives." },
  plan: { shows: "What each setup was given and how the runs were judged.", how: "Read the settings side by side; the differences between setups are what the report compares." },
  setup: { shows: "What was compared: each setup's settings and the material it was given.", how: "Settings that differ between setups are marked; texts are shown with their differences highlighted, so you can see exactly what changed from one setup to another." },
  cases: { shows: "Each case: the task it set, how a run passed it, and how every setup did on it.", how: "Read a case's task first, then its pass criteria, then the marks: one per run, filled for a pass, hollow for a failure. Open a case for its runs' details." },
  failures: { shows: "Why the failed runs failed, grouped by cause.", how: "Each group is one cause, such as a required check that did not hold or a judge's rejection, with its runs as marks. Select a mark to read that run." },
  contrast: { shows: "The difference in pass rate between setups, with its likely range.", how: "Each row is one setup minus its reference, in percentage points. Right of zero means it passed more often. The band is the 95% interval of the difference: a band that crosses zero means the difference could be chance." },
  table: { shows: "Values laid out in rows and columns.", how: "Read across a row for one item, down a column to compare items on one measure; “missing” marks a value that was not recorded." },
  matrix: { shows: "Which requirement each alternative meets.", how: "Each row is a requirement and each column an alternative; a cell says whether it is met, and “not established” where the evidence does not say." },
  intervals: { shows: "Values with the range each likely falls in, on one scale.", how: "The dot is the value and the band its 95% interval; bands that overlap a lot mean the difference could be chance." },
  bars: { shows: "How each item's total is made up.", how: "Each bar is one item split into parts in proportion; the number at the end is its total, and “missing” counts parts with no value." },
  trend: { shows: "How values change across ordered stages.", how: "Each line is one series, stage by stage; whiskers are 95% intervals, and a gap in a line is a stage without a value. The table below lists every point." },
  excerpts: { shows: "Quoted output, word for word.", how: "Each quote is shown exactly as produced, with where it came from and its outcome; it illustrates the results, it does not measure them." },
  diagram: { shows: "A diagram of how the parts relate.", how: "Follow the arrows; the diagram's source text is under “Diagram source”." },
  scorecard: { shows: "Every alternative on every measure, in one grid.", how: "Each cell is one alternative's summary on one measure, with its 95% interval where one exists. A measure with a better direction marks which way is better; a measure without one is never colored good or bad." },
  metric: { shows: "One measure for each alternative, with the range it likely falls in.", how: "The dot or bar is the summary (a rate, a mean, a median or a share of levels) and the band its 95% interval; the method note says how the interval was found." },
  difference: { shows: "The difference between alternatives on each measure, with its likely range.", how: "Each row is one alternative minus another in the measure's own units. A band that crosses zero means the difference could be chance; “better” or “worse” is said only when the band clears zero in the measure's better direction." },
  hierarchy: { shows: "Results pooled by group, then inside each group.", how: "Read the groups first, then open a group to see the alternatives inside it; pooled values say how many alternatives they combine." },
  alternatives: { shows: "What each alternative is: its settings and the material it was given.", how: "Read across alternatives for what differs; the reference alternative and copies given identical material are marked." },
  preferences: { shows: "Head-to-head choices between alternatives, and rankings.", how: "Win rates count decisive judgments only; ties and unreached judgments are counted apart. Read the table of every pair for who beat whom how often." },
  "decision-matrix": { shows: "The decider's own criteria, weights and ratings, with the total each gives.", how: "Each row is one criterion with its weight; each cell is the decider's rating of one alternative, with the evidence for it. The total is the weighted sum shown with its arithmetic: it is the decider's judgment, not a measurement." },
  observations: { shows: "Every observation behind the summaries.", how: "Filter by validity, alternative, case or metric, or search; invalid observations say why they have no value." },
  decisions: { shows: "What every report decided, grouped by theme.", how: "Each tile is one report: its stamp is the decision in its own words, and selecting it opens the report. The bar on top counts the decisions." },
  reports: { shows: "Every report in the collection, with its decision, its results and how to open it.", how: "Switch between designs (cards, list, table, by model), filter by decision, theme, model or words, and pick two reports to compare them side by side. On each track the ring is the reference setup and each mark another setup; the line between them is the change." },
  shifts: { shows: "How far each change moved its report's measure, every report on one page.", how: "Each row is one report; the ring is its reference setup and the line to each other setup is the change, green when better, red when worse, grey when the measure names no better direction. Bands are 95% intervals." },
  "cost-gain": { shows: "Each change's effect on the result against its effect on cost.", how: "Up means more runs passed, right means each run cost more. The top left is better and cheaper; the bottom right worse and dearer. A whisker that crosses the middle line means the change in result could be chance." },
  timeline: { shows: "The reports in the order they ran, with the follow-ups that link them.", how: "Read top to bottom by day; “Follows” links a report to the one it built on, with a link to set the two side by side." },
  matchups: { shows: "Pairs of reports worth reading together.", how: "Each card sets two reports side by side: whether the decision changed, the models each ran on, and each setup's result. Open the pair for the full comparison." },
  "report-compare": { shows: "Two reports side by side: their decisions, what differs, and their results on one scale where they measure the same thing.", how: "A is on the left and B on the right. “What differs” says it in words; on each track A and B mark each setup's value and the line between them is the change from A to B, with its 95% interval. Reports that measure different things are shown apart, never subtracted." },
};

/** The reading that goes with a view: the library's words, the author's where given, and what this data says. */
export function readHtml(kind: string, read: Reading | undefined): string {
  const own = read && typeof read === "object" ? read : {};
  const base = READING[kind];
  const shows = own.shows ?? base?.shows, how = own.how ?? base?.how;
  if (!shows && !how && !own.says) return "";
  const text = (v: string | string[] | undefined) => Array.isArray(v) ? v.filter(x => typeof x === "string").join(" ") : typeof v === "string" ? v : "";
  return `<div class="av-read">${shows ? `<p class="av-read-shows"><span class="av-read-tag">This view</span>${inline(text(shows))}</p>` : ""}${how ? `<details class="av-read-how"><summary>How to read it</summary>${prose(how, "av-read-prose")}</details>` : ""}${own.says ? `<div class="av-read-says"><span class="av-read-tag">Here</span>${prose(own.says, "av-read-prose")}</div>` : ""}</div>`;
}

/** The story that opens a report: what it is about, before any result. */
export function storyHtml(story: Story, ctx: RenderContext): string {
  if (!story || typeof story !== "object") return "";
  const part = (title: string, body: string) => body ? `<div class="av-story-part"><h3 class="av-story-h">${esc(title)}</h3>${body}</div>` : "";
  const entries = (record: unknown, name: (id: string) => string) => record && typeof record === "object" && !Array.isArray(record)
    ? `<dl class="av-story-list">${Object.entries(record as Record<string, unknown>).filter(([, v]) => typeof v === "string" || Array.isArray(v)).map(([id, v]) => `<div><dt>${name(id)}</dt><dd>${prose(v as string | string[], "av-story-prose")}</dd></div>`).join("")}</dl>` : "";
  const questions = Array.isArray(story.questions) ? story.questions.filter(q => typeof q === "string") : [];
  const glossary = Array.isArray(story.glossary) ? story.glossary.filter(g => g && typeof g === "object" && typeof g.term === "string") : [];
  return `<div class="av-story">${part("Background", prose(story.background, "av-story-prose"))}${part("What the decider wanted", story.intent ? `<blockquote class="av-story-intent">${prose(story.intent, "av-story-prose")}</blockquote>` : "")}${part("What was tested", questions.length ? `<ol class="av-story-questions">${questions.map(q => `<li>${inline(q)}</li>`).join("")}</ol>` : "")}${part("What was compared", entries(story.alternatives, id => ctx.arms.tag(id)))}${part("The cases", entries(story.cases, id => `<span class="av-story-case">${esc(ctx.caseLabels[id] || id)}</span>${ctx.caseLabels[id] && ctx.caseLabels[id] !== id ? ` <code>${esc(id)}</code>` : ""}`))}${part("How the decision was made", prose(story.rule, "av-story-prose"))}<div class="av-story-scope">${part("This report covers", prose(story.covers, "av-story-prose"))}${part("It does not cover", prose(story.notCovered, "av-story-prose"))}</div>${part("Words used here", glossary.length ? `<dl class="av-story-list">${glossary.map(g => `<div><dt>${esc(g.term)}</dt><dd>${prose(g.meaning, "av-story-prose")}</dd></div>`).join("")}</dl>` : "")}</div>`;
}
