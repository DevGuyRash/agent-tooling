// The judgment views for a comparison of any alternatives: what was compared
// (alternatives), head-to-head judgments and rankings (preferences), the
// decision matrix, and the observations table. The data is deliberately not
// about agents: advertisements, sandwiches and a game design stand in.
"use strict";
const H = require("./harness.cjs");
const F = require("./fixtures.cjs");
const { test } = H;

const V = H.loadVisuals();

const AD_A1 = "Save an hour a day.\nTry it free.\nNo card needed.";
const AD_A2 = "Save two hours a day.\nTry it free.\nNo card needed.";

/** Four advertisements in two nested directions, one of them ungrouped. */
function ads(extra = {}) {
  return {
    title: "Ad copy", question: "Which headline earns more sign-ups?",
    alternatives: [
      { id: "a1", label: "Save an hour", description: "Benefit first.", group: ["Direction A", "Concept 1"], attributes: { channel: "search", budget: 500, tone: "calm" }, content: AD_A1, note: "The control." },
      { id: "a2", label: "Save two hours", group: ["Direction A", "Concept 2"], attributes: { channel: "search", budget: 500, tone: "bold" }, content: AD_A2 },
      { id: "b1", label: "Do not fall behind", group: "Direction B", attributes: { channel: "search", budget: 500, tone: "urgent" }, content: AD_A1 },
      { id: "c1", label: "Plain", attributes: { channel: "search", budget: 500, tone: "calm" } },
    ],
    cases: [{ id: "us", label: "United States" }, { id: "uk" }],
    metrics: [
      { id: "signup", kind: "binary", better: "higher", primary: true },
      { id: "cost", kind: "numeric", better: "lower", unit: "USD" },
      { id: "quality", kind: "ordinal", levels: ["poor", "fair", "good"] },
      { id: "taste", kind: "preference", better: "higher" },
      { id: "price", kind: "preference", better: "higher" },
    ],
    baseline: "a1",
    ...extra,
  };
}
const render = (type, input, comparison, arms = []) => V.renderBlock({ type, ...input }, V.createContext({ comparison, arms }));
const pref = (a, b, winner, extra = {}) => ({ a, b, winner, ...extra });

// ------------------------------------------------------------------ alternatives

test("alternatives nests group paths and leaves ungrouped alternatives at the top", () => {
  const html = render("alternatives", {}, ads());
  H.equal(H.count(html, 'class="av-alt-group"'), 4, "Direction A, its Concept 1 and Concept 2, and Direction B");
});

test("alternatives shows group nesting as nested lists, outermost first", () => {
  const html = render("alternatives", {}, ads());
  const a = H.element(html, '<li class="av-alt-group"><div class="av-alt-group-head"><span class="av-alt-group-name">Direction A<');
  H.includes(a, ">Concept 1<", "Concept 1 inside Direction A");
  H.includes(a, ">Concept 2<", "Concept 2 inside Direction A");
  H.excludes(a, ">Direction B<", "Direction B outside Direction A");
  H.ok(H.element(html, 'class="av-alt-list av-alt-list--root av-alt-list--nested"').includes('data-arm="c1"'), "the ungrouped alternative sits at the root");
  H.includes(html, "in 2 groups nested 2 deep", "the lede names the nesting");
});

test("alternatives puts shared attributes on one line and only differing ones in a table", () => {
  const html = render("alternatives", {}, ads());
  const shared = H.element(html, 'class="av-alt-shared"');
  H.includes(shared, "<dt>channel</dt>", "channel is shared");
  H.includes(shared, "<dt>budget</dt>", "budget is shared");
  H.excludes(shared, "<dt>tone</dt>", "tone differs, so it is not on the shared line");
  const table = H.element(html, 'class="av-table av-alt-table"');
  H.includes(table, '<th scope="col">tone</th>', "tone is a column");
  H.excludes(table, '<th scope="col">channel</th>', "channel is not a column");
  H.includes(table, 'data-label="tone"', "cells carry their column name for the phone layout");
  H.includes(html, "<strong>tone</strong>", "the lede names what differs");
});

test("alternatives letters the texts, shares a letter between identical texts and diffs from the baseline", () => {
  const html = render("alternatives", {}, ads());
  H.includes(html, ">Text A<", "Text A"); H.includes(html, ">Text B<", "Text B");
  H.excludes(html, ">Text C<", "no third text: b1 repeats a1's");
  const a = H.element(html, 'class="av-alt-text" open');
  H.includes(a, 'data-arm="a1"', "a1 uses Text A"); H.includes(a, 'data-arm="b1"', "b1 shares Text A");
  H.includes(html, "the baseline’s text", "the diff names its reference");
  H.includes(html, "av-diff-row--add", "an added line"); H.includes(html, "av-diff-row--del", "a removed line");
  H.includes(html, '<mark class="av-diff-word">', "the changed words are marked");
  H.includes(html, "+ 1 line added", "the diff counts additions");
  H.includes(html, "1 alternative recorded none", "an alternative with no text is said to record none");
});

test("alternatives says so when nothing but descriptions tells the alternatives apart", () => {
  const html = render("alternatives", {}, { alternatives: [{ id: "pb", label: "Peanut butter" }, { id: "jam", label: "Jelly", description: "Grape." }], metrics: [] });
  H.includes(html, "No attributes or texts were recorded", "no invented difference");
  H.excludes(html, "av-alt-table", "no table"); H.excludes(html, "av-alt-shared", "no shared line");
  H.includes(html, "Peanut butter", "a label"); H.includes(html, "Grape.", "a description");
});

test("alternatives treats one alternative as nothing to compare", () => {
  const html = render("alternatives", {}, { alternatives: [{ id: "only", attributes: { a: 1 } }], metrics: [] });
  H.includes(html, "One alternative is recorded", "single");
  H.includes(html, "<dt>a</dt>", "its attributes show");
});

test("alternatives warns when alternatives listed as identical differ", () => {
  const html = render("alternatives", {}, ads({ identical: [["a1", "a2"], ["a1", "b1"]] }));
  H.includes(html, "listed as identical", "the chip");
  H.includes(html, "but differs from", "the difference is named");
});

test("alternatives narrows to a subset and hides named attributes", () => {
  const html = render("alternatives", { alternatives: ["a1", "b1"], hide: ["tone"] }, ads());
  H.excludes(html, 'data-arm="a2"', "a2 left out"); H.includes(html, 'data-arm="b1"', "b1 kept");
  H.excludes(html, "<dt>tone</dt>", "tone hidden"); H.includes(html, "Left out of this view: tone", "the omission is stated");
});

test("alternatives renders explicit data without a report comparison", () => {
  const html = V.renderBlock({ type: "alternatives", data: ads() }, V.createContext({}));
  H.includes(html, "Save an hour", "labels from the explicit data");
  const missingData = V.renderBlock({ type: "alternatives" }, V.createContext({}));
  H.includes(missingData, "could not render", "a block with no data says so");
  H.includes(missingData, "needs comparison data", "and says what it needs");
});

// ------------------------------------------------------------------ preferences

/** Judgments between a, b and c: a leads b 3-1 with a tie and an unreached judgment; c loses to both. */
function judged(extra = {}) {
  return ads({
    alternatives: [{ id: "a", label: "A" }, { id: "b", label: "B" }, { id: "c", label: "C" }],
    preferences: [
      pref("a", "b", "a", { judge: "ana", case: "us" }), pref("a", "b", "a", { judge: "ana", case: "us" }), pref("b", "a", "a", { judge: "ben", case: "uk" }),
      pref("a", "b", "b", { judge: "ben", case: "uk" }), pref("a", "b", "tie", { judge: "ana", case: "uk" }), pref("a", "b", null, { judge: "ana", case: "us" }),
      pref("a", "c", "a", { judge: "ana", case: "us" }), pref("b", "c", "b", { judge: "ben", case: "us" }), pref("c", "b", "c", { judge: "ben", case: "uk" }),
    ],
    ...extra,
  });
}

test("preferences shows wins, losses and ties per pair as a win matrix", () => {
  const html = render("preferences", {}, judged());
  const matrix = H.element(html, 'class="av-jv-matrix"');
  const row = H.element(matrix, '<tr data-arm="a">');
  H.includes(row, "<b>3</b>–<b>1</b>", "a beat b 3 times and lost once");
  H.includes(row, "+1 tie", "the tie sits beside it");
  H.includes(row, "A beat B 3 times", "the cell says it in words for a screen reader");
  H.includes(H.element(matrix, '<tr data-arm="b">'), "<b>1</b>–<b>3</b>", "b's side of the same pair");
});

test("preferences counts undecided judgments and never as losses", () => {
  const html = render("preferences", {}, judged());
  H.includes(html, "1 undecided", "the lede counts it");
  H.includes(html, "reached no decision", "and says it is left out");
  const rate = H.element(html, 'class="av-jv-table"');
  H.includes(H.element(rate, 'data-arm="a"'), 'data-label="Wins">4<', "a's wins over b (3) and c (1)");
  H.includes(H.element(rate, 'data-arm="a"'), 'data-label="Losses">1<', "the undecided judgment is not a loss");
});

test("preferences gives win rates over decisive judgments with a Wilson interval", () => {
  const html = render("preferences", {}, judged());
  const a = H.element(H.element(html, 'class="av-jv-table"'), 'data-arm="a"');
  const ci = V.wilson(4, 5), pct = x => `${Math.round(x * 100)}%`;
  H.includes(a, `<span class="av-rate">${pct(4 / 5)}</span>`, "4 wins in 5 decisive judgments");
  H.includes(a, `${pct(ci[0])}–${pct(ci[1])}`, "the interval");
  H.includes(a, "5 decisive", "the decisive count");
});

test("preferences names the judges and counts judgments without one", () => {
  const html = render("preferences", {}, judged({ preferences: [...judged().preferences, pref("a", "b", "a")] }));
  const judges = H.element(html, 'class="av-jv-judges"');
  H.includes(judges, ">ana<", "ana"); H.includes(judges, ">ben<", "ben"); H.includes(judges, "not named", "an unnamed judgment is counted");
  H.includes(html, "1 without a named judge", "the lede says so");
});

test("preferences summarizes rankings as first places and mean rank", () => {
  const html = render("preferences", {}, ads({ alternatives: [{ id: "a" }, { id: "b" }, { id: "c" }], rankings: [{ order: ["a", "b", "c"], judge: "x" }, { order: ["a", "c", "b"], judge: "y" }, { order: ["b", "a", "c"], judge: "z" }] }));
  H.includes(html, "Mean rank", "the rankings table");
  const first = H.element(html, 'data-label="First places"'), mean = H.element(html, 'data-label="Mean rank"');
  H.includes(first, "2 of 3", "a is first twice in three"); H.includes(first, "67%", "a share of first places");
  H.includes(mean, "1.33", "mean rank (1 + 1 + 2) / 3");
  H.includes(html, 'class="av-jv-dist"', "the positions");
  H.includes(html, "each ranking also counts as a win", "the matrix says rankings feed it");
});

test("preferences breaks the record down by case and marks the leader", () => {
  const html = render("preferences", {}, judged());
  const by = H.element(html, 'class="av-jv-table av-jv-table--by"');
  H.includes(by, "United States", "a case label"); H.includes(by, ">uk<", "a case with no label shows its id");
  H.includes(by, "highest in this row", "the leader is marked for a screen reader");
});

test("preferences reads one criterion at a time and tabulates all of them", () => {
  const prefs = [pref("a", "b", "a", { metric: "taste" }), pref("a", "b", "a", { metric: "taste" }), pref("a", "b", "b", { metric: "price" }), pref("a", "b", "b", { metric: "price" }), pref("a", "b", "a")];
  const data = ads({ alternatives: [{ id: "a" }, { id: "b" }], preferences: prefs });
  const overall = render("preferences", {}, data);
  H.includes(overall, "on <strong>overall</strong>", "judgments naming no criterion are the overall ones");
  H.includes(overall, "By criterion", "the criteria are tabulated"); H.includes(overall, ">taste<", "taste"); H.includes(overall, ">price<", "price");
  const taste = render("preferences", { metric: "taste" }, data);
  H.includes(taste, "on <strong>taste</strong>", "the chosen criterion"); H.includes(H.element(taste, '<tr data-arm="a">'), "<b>2</b>–<b>0</b>", "a swept taste");
});

test("preferences counts unreadable judgments and names what is left out", () => {
  const data = judged({ preferences: [pref("a", "b", "zzz"), pref("a", "a", "a"), pref("a", "ghost", "a"), pref("a", "b", "a")] });
  const html = render("preferences", {}, data);
  H.includes(html, "3 unreadable", "three unreadable judgments counted"); H.includes(html, "could not be read", "and explained");
  H.includes(html, "No judgment mentions C.", "an alternative nobody judged is named");
});

test("preferences narrows to a subset of alternatives or a group and keeps only judgments between its members", () => {
  const subset = render("preferences", { alternatives: ["a", "b"] }, judged());
  H.includes(subset, "6 head-to-head judgments", "the six judgments between a and b"); H.excludes(H.element(subset, 'class="av-jv-matrix"'), 'data-arm="c"', "no row for c");
  const grouped = ads({
    alternatives: [{ id: "x", group: ["G1"] }, { id: "y", group: ["G1"] }, { id: "z", group: ["G2"] }],
    preferences: [pref("x", "y", "x"), pref("x", "z", "z"), pref("y", "z", "y")],
  });
  const g1 = render("preferences", { groups: ["G1"] }, grouped);
  H.includes(g1, "1 head-to-head judgment", "one judgment inside G1"); H.excludes(g1, "No judgment mentions", "nothing inside G1 goes unjudged");
  const obs = ads({ alternatives: grouped.alternatives, observations: [{ alternative: "x", metric: "signup", value: true }, { alternative: "z", metric: "signup", value: false }] });
  const kept = render("observations", { groups: ["G2"], metric: "signup" }, obs);
  H.equal(H.count(kept, "data-av-row="), 1, "one observation inside G2");
});

test("preferences is an empty notice without judgments", () => {
  H.includes(render("preferences", {}, ads()), "No head-to-head judgments or rankings were recorded.", "empty state");
});

// ------------------------------------------------------------------ decision matrix

const SANDWICH = {
  alternatives: ["pb", { id: "jelly", label: "Jelly" }],
  criteria: [
    { id: "taste", label: "Taste", weight: 3, description: "How it tastes." },
    { id: "mess", label: "Mess", weight: 2, better: "lower" },
    { id: "effort", label: "Effort" },
  ],
  scale: { min: 1, max: 5 },
  cells: [
    { criterion: "taste", alternative: "pb", rating: 4, text: "Rich.", evidence: ["Ate it twice.", "A friend agreed."] },
    { criterion: "taste", alternative: "jelly", rating: 3 },
    { criterion: "mess", alternative: "pb", rating: 2, evidence: "Knife stuck." },
    { criterion: "mess", alternative: "jelly", rating: 5 },
    { criterion: "effort", alternative: "pb", rating: 5 },
  ],
};
const matrix = (input, comparison) => V.renderBlock({ type: "decision-matrix", ...input }, V.createContext({ comparison }));

test("decision-matrix shows each rating with its note and evidence, and a missing cell as not assessed", () => {
  const html = matrix(SANDWICH);
  H.includes(html, "Rich.", "the note"); H.includes(html, "Evidence (2)", "two pieces of evidence"); H.includes(html, "<li>Ate it twice.</li>", "evidence expands");
  H.includes(html, "not assessed", "effort for jelly was never assessed");
  H.includes(html, "5 of 6 cells are assessed, 1 not assessed", "the cell count");
});

test("decision-matrix computes no total without weights", () => {
  const html = matrix({ ...SANDWICH, criteria: SANDWICH.criteria.map(({ weight, ...c }) => c) });
  H.excludes(html, "Weighted total", "no total row"); H.excludes(html, "How the totals are computed", "no arithmetic");
  H.includes(html, "No criterion weights were supplied, so no total is computed", "the absence is stated");
});

test("decision-matrix shows the arithmetic behind each weighted total", () => {
  const html = matrix(SANDWICH);
  H.includes(html, "Weighted total", "the total row");
  H.includes(html, "3×4 + 2×(1+5−2) = 20", "pb: taste 3×4, and mess reversed because lower is better (1+5−2 = 4), 2×4");
  H.includes(html, "3×3 + 2×(1+5−5) = 11", "jelly");
  H.excludes(html, "Effort (weight", "a criterion without a weight is not in any total");
  H.includes(html, "Criteria without a weight are not in the total: Effort.", "and that is said");
});

test("decision-matrix leaves a skipped criterion out of the total and says the total is incomplete", () => {
  const html = matrix({ ...SANDWICH, criteria: SANDWICH.criteria.map(c => c.id === "effort" ? { ...c, weight: 1 } : c) });
  H.includes(html, "incomplete", "jelly has no effort rating");
  H.includes(html, "not in the total: Effort (weight 1)", "the skipped criterion is named");
  H.includes(html, "is not comparable with a complete one", "and the caveat");
  H.excludes(html, 'class="av-chip av-chip--pass">highest', "no leader is named when only one total is complete");
});

test("decision-matrix refuses to guess a total it cannot compute", () => {
  const html = matrix({ ...SANDWICH, scale: undefined });
  H.excludes(html, "Weighted total", "no total");
  H.includes(html, "lower-is-better and the scale has no min and max", "the reason");
});

test("decision-matrix reads level names from the scale and reports stray and repeated cells", () => {
  const html = matrix({
    alternatives: ["x", "y"], criteria: [{ id: "fun", weight: 1 }], scale: { levels: ["dull", "ok", "great"] },
    cells: [{ criterion: "fun", alternative: "x", rating: "great" }, { criterion: "fun", alternative: "y", rating: "ok" }, { criterion: "fun", alternative: "y", rating: "dull" }, { criterion: "zzz", alternative: "x", rating: 1 }],
  });
  H.includes(html, "1×3 = 3", "great is level 3"); H.includes(html, "1×2 = 2", "the first y cell counts");
  H.includes(html, "1 cell names a criterion or alternative that is not in this matrix", "a stray cell is said"); H.includes(html, "1 cell repeats a criterion and alternative", "a repeat is said");
});

test("decision-matrix reads scores by alternative and shows a metric-linked criterion as measured", () => {
  const data = ads({ observations: [{ alternative: "a1", metric: "signup", value: true }, { alternative: "a1", metric: "signup", value: false }, { alternative: "a2", metric: "signup", value: true }, { alternative: "a2", metric: "signup", value: true }, { alternative: "a2", metric: "signup", value: null }] });
  const html = matrix({ alternatives: ["a1", "a2"], scale: { levels: ["poor", "ok", "great"] }, criteria: [{ id: "fit", label: "Fit", weight: 2, scores: { a1: "great", a2: "ok", ghost: "ok" } }, { id: "signup", label: "Sign-up rate", metric: "signup", weight: 1, note: "Measured in the pilot." }, { id: "flag", scores: { a1: true, a2: null } }], cells: [] }, data);
  H.includes(html, "2×3 = 6", "scores become ratings that total"); H.includes(html, "2×2 = 4", "a2's score");
  H.includes(html, "measured: signup", "a metric-linked criterion shows its measured value"); H.includes(html, "50%", "a1: 1 of 2"); H.includes(html, "1 invalid observation", "an invalid observation is counted beside it");
  H.includes(html, "not scaled into a total: Sign-up rate", "a measured criterion is kept out of the total, and that is said");
  H.includes(html, "Measured in the pilot.", "note is the description"); H.includes(html, ">yes<", "a boolean score reads yes"); H.includes(html, "1 cell names a criterion or alternative", "a score for an unknown alternative is said");
});

test("decision-matrix takes its alternatives from the report's comparison", () => {
  const html = matrix({ criteria: [{ id: "k" }], cells: [{ criterion: "k", alternative: "a1", rating: 1 }] }, ads());
  H.includes(html, "Save an hour", "the comparison's label"); H.includes(html, "not assessed", "the other alternatives were not assessed");
});

// ------------------------------------------------------------------ observations

function observed() {
  return ads({
    observations: [
      { alternative: "a1", metric: "signup", case: "us", value: true, unit: 1, source: "https://example.test/export.csv", note: "First session." },
      { alternative: "a1", metric: "signup", case: "us", value: false, unit: 2 },
      { alternative: "a2", metric: "signup", case: "uk", value: null, note: "Tracking was down." },
      { alternative: "a2", metric: "cost", case: "uk", value: 12.5, excerpt: "Invoice 4471\nline two" },
      { alternative: "b1", metric: "cost", value: "n/a", valid: false, invalid_reason: "export failed" },
      { alternative: "b1", metric: "quality", value: "good" },
    ],
    aggregates: [{ alternative: "c1", metric: "signup", k: 12, n: 340, source: "javascript:alert(1)" }, { alternative: "c1", metric: "cost", mean: 9.5, sd: 2.1, n: 40 }],
  });
}

test("observations lists every observation and every aggregate", () => {
  const html = render("observations", {}, observed());
  H.equal(H.count(html, "data-av-row="), 8, "six observations and two aggregates");
  H.includes(html, "12 of 340", "an aggregate count"); H.includes(html, "mean 9.5", "an aggregate mean"); H.includes(html, "3.5%", "the aggregate rate");
  H.includes(html, "6 observations", "the lede counts observations"); H.includes(html, "2 aggregates", "and aggregates");
});

test("observations counts invalid ones visibly and never as failures", () => {
  const html = render("observations", {}, observed());
  H.includes(html, "never read as a failure", "the lede says how they are read");
  H.includes(html, "2 invalid", "the invalid count includes the one with no value");
  H.includes(html, "export failed", "a reason, as given"); H.includes(html, "no value", "a missing value is shown");
  H.equal(H.count(html, 'data-outcome="invalid"'), 3, "two invalid rows and the filter button");
  H.excludes(html, "av-mark--fail", "no failure mark"); H.excludes(html, "av-badge--fail", "no failure badge");
});

test("observations is filterable and sortable by markup the page enhancer reads", () => {
  const html = render("observations", {}, observed());
  const tools = H.element(html, "data-av-ledger-tools");
  H.includes(tools, 'data-filter="arm"', "alternative filter"); H.includes(tools, 'data-filter="case"', "case filter"); H.includes(tools, 'data-filter="metric"', "metric filter");
  H.includes(tools, 'data-filter="text"', "search"); H.includes(tools, 'data-outcome="aggregate"', "aggregate toggle"); H.includes(tools, "hidden", "hidden until enhanced");
  const table = H.element(html, 'data-av-table="observations"');
  H.includes(table, 'data-sortable="num"', "a numeric sort column"); H.includes(table, 'data-col="value"', "named columns");
  H.includes(table, 'data-case="us"', "rows carry case"); H.includes(table, 'data-metric="cost"', "and metric"); H.includes(table, 'data-av-noun="observations"', "the noun for counts");
});

test("observations folds an excerpt away and links only web sources", () => {
  const html = render("observations", {}, observed());
  H.includes(html, '<details class="av-obs-excerpt"><summary>Excerpt</summary>', "the excerpt expands in place"); H.includes(html, "Invoice 4471", "its text");
  H.includes(html, '<a href="https://example.test/export.csv" rel="noopener noreferrer">', "a web source links");
  H.excludes(html, 'href="javascript:', "a script URL never becomes a link"); H.includes(html, "javascript:alert(1)", "but still shows as text");
});

test("observations reads each value by its metric", () => {
  const html = render("observations", {}, observed());
  H.includes(html, 'av-obs-bool--good" data-value="true"', "a binary value with better higher"); H.includes(html, 'av-obs-bool--bad" data-value="false"', "its opposite");
  H.includes(html, '<span class="av-obs-unit">USD</span>', "a unit"); H.includes(html, "<span class=\"av-obs-level\">good</span><span class=\"av-obs-sub\">3 of 3</span>", "an ordinal level with its position");
});

test("observations is an empty notice without data", () => {
  H.includes(render("observations", {}, ads()), "No observations or aggregates were recorded.", "empty state");
});

// ------------------------------------------------------------------ escaping and registration

test("every supplied text field of the judgment views renders as text", () => {
  const h = F.hostile;
  const data = {
    title: h("title"), question: h("question"),
    alternatives: [
      { id: "a", label: h("alt-label"), description: h("alt-description"), group: [h("group-1"), h("group-2")], attributes: { [h("attr-key")]: h("attr-a") }, content: `${h("text-a")}\none`, note: h("alt-note") },
      { id: "b", label: "B", attributes: { [h("attr-key")]: h("attr-b") }, content: `${h("text-b")}\none` },
    ],
    cases: [{ id: h("case"), label: h("case-label") }],
    metrics: [{ id: "m", label: h("metric-label"), kind: "numeric", unit: h("unit") }, { id: "q", kind: "preference" }],
    observations: [{ alternative: "a", metric: "m", case: h("case"), value: 1, unit: h("repeat"), note: h("obs-note"), excerpt: h("obs-excerpt"), source: h("obs-source") }, { alternative: "b", metric: "m", value: "x", valid: false, invalid_reason: h("reason") }, { alternative: h("ghost"), metric: h("ghost-metric"), value: 1 }],
    aggregates: [{ alternative: "a", metric: "m", mean: 1, note: h("agg-note"), source: h("agg-source") }],
    preferences: [{ a: "a", b: "b", winner: "a", judge: h("judge"), case: h("case") }, { a: "a", b: "b", winner: "b", judge: h("judge"), case: "other" }],
    rankings: [{ order: ["a", "b"], judge: h("ranker") }],
  };
  const dm = { criteria: [{ id: "c", label: h("criterion"), description: h("criterion-description") }], alternatives: [{ id: "a", label: h("dm-alt") }, "b"], cells: [{ criterion: "c", alternative: "a", rating: h("rating"), text: h("cell-text"), evidence: [h("evidence")] }, { criterion: "c", alternative: "b", rating: 1 }], scale: { note: h("scale-note") } };
  const ctx = V.createContext({ comparison: data });
  const out = ["alternatives", "preferences", "observations"].map(type => V.renderBlock({ type, title: h("block-title"), description: h("block-description"), note: h("block-note") }, ctx)).concat(V.renderBlock({ type: "decision-matrix", ...dm }, ctx)).join("\n");
  const raw = F.rawHostileFields(out);
  if (raw.length) H.fail(`unescaped markup from: ${raw.join(", ")}`);
  for (const f of ["alt-label", "alt-description", "group-1", "attr-key", "attr-a", "text-a", "alt-note", "obs-note", "obs-excerpt", "reason", "judge", "ranker", "criterion", "cell-text", "evidence", "rating", "scale-note", "block-title"]) H.includes(out, F.escapedHostile(f), `the escaped ${f}`);
});

test("the judgment blocks are registered and compose into a report with the other views", () => {
  for (const t of ["alternatives", "preferences", "decision-matrix", "observations"]) H.ok(V.blockTypes().includes(t), `${t} is a block type`);
  const spec = { title: "Ads", sections: [{ title: "Setup", blocks: [{ type: "alternatives" }] }, { title: "Judged", blocks: [{ type: "preferences" }, { type: "observations" }] }], comparison: judged({ observations: observed().observations }) };
  const html = V.renderReport(spec);
  for (const k of ["av-block--alternatives", "av-block--preferences", "av-block--observations"]) H.includes(html, k, k);
  H.excludes(html, "av-block-error", "no block failed");
});

test("the judgment views stay within the design language", () => {
  const data = judged({ observations: observed().observations });
  const out = [render("alternatives", {}, data), render("preferences", {}, data), render("observations", {}, data), matrix(SANDWICH)].join("\n");
  H.excludes(out, "style=\"color:#", "no literal colors in style attributes"); H.excludes(out, "NaN", "no NaN"); H.excludes(out, "undefined", "no undefined"); H.excludes(out, "[object", "no stringified objects");
  H.ok(!/style="[^"]*(?:#[0-9a-f]{3,6}|rgb\()/i.test(out), "style attributes carry tokens and positions only");
});

H.report();
