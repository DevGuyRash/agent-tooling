// The comparison engine: summaries and differences for every metric kind, each
// method checked against a published worked example; pooled groups; the
// reader-first composition; trial data as a comparison; and the comparison
// checker.
//
//   node engine.cjs                   runs the cases (see test_engine.py)
//   node engine.cjs --corpus IN --out OUT
//                                     writes validateComparison / validateSpec problems for each
//                                     corpus entry to OUT, so test_validate.py can compare report.py
"use strict";
const fs = require("node:fs");
const path = require("node:path");
const H = require("./harness.cjs");
const { test } = H;

const V = H.loadVisuals();

const at = process.argv.indexOf("--corpus");
if (at >= 0) {
  // { comparisons: {name: comparison}, entries: [{kind: "comparison" | "spec", input, narrative?, comparison?: name}] }
  const corpus = JSON.parse(fs.readFileSync(process.argv[at + 1], "utf8"));
  const out = corpus.entries.map(entry => {
    if (entry.kind === "comparison") return H.plain("narrative" in entry ? V.validateComparison(entry.input, entry.narrative) : V.validateComparison(entry.input));
    const comparison = entry.comparison === null || entry.comparison === undefined ? undefined : corpus.comparisons[entry.comparison];
    return H.plain(V.validateSpec(entry.input, { comparison }));
  });
  fs.writeFileSync(process.argv[process.argv.indexOf("--out") + 1], JSON.stringify(out));
  process.exit(0);
}

const close = (actual, expected, tolerance, what) => {
  if (typeof actual !== "number" || Math.abs(actual - expected) > tolerance) H.fail(`${what}: expected ${expected} ± ${tolerance}, got ${actual}`);
};
const closeAll = (actual, expected, tolerance, what) => {
  if (!Array.isArray(actual) || actual.length !== expected.length) H.fail(`${what}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
  expected.forEach((e, i) => close(actual[i], e, tolerance, `${what}[${i}]`));
};
const one = (list, id) => list.find(s => s.alternative === id) || H.fail(`no summary for ${id}`);
const obs = (alternative, metric, values, extra = {}) => values.map((value, i) => ({ alternative, metric, value, unit: i + 1, ...extra }));

// R's sleep data (Cushny and Peebles 1905, as in Student 1908): extra hours of sleep under two drugs.
const SLEEP1 = [0.7, -1.6, -0.2, -1.2, -0.1, 3.4, 3.7, 0.8, 0.0, 2.0];
const SLEEP2 = [1.9, 0.8, 1.1, 0.1, -0.1, 4.4, 5.5, 1.6, 4.6, 3.4];
const sleep = {
  alternatives: [{ id: "drug1" }, { id: "drug2" }],
  metrics: [{ id: "extra", kind: "numeric", unit: "hours", better: "higher" }],
  observations: [...obs("drug1", "extra", SLEEP1), ...obs("drug2", "extra", SLEEP2)],
};

test("Student t quantiles match published tables", () => {
  close(V.tQuantile(0.975, 1), 12.7062, 5e-4, "t(0.975, 1)");
  close(V.tQuantile(0.975, 9), 2.262157, 5e-6, "t(0.975, 9)");
  close(V.tQuantile(0.975, 30), 2.042272, 5e-6, "t(0.975, 30)");
  close(V.tQuantile(0.975, 1e6), 1.959964, 5e-6, "t(0.975, large df)");
  close(V.tCdf(2.262157, 9), 0.975, 1e-6, "t cdf");
});

test("numeric: the mean, sd and t interval match R's t.test on the sleep data", () => {
  const s = one(V.summarize(sleep, "extra"), "drug1");
  close(s.mean, 0.75, 1e-12, "mean");
  close(s.sd, 1.78901, 5e-6, "sd");
  close(s.median, 0.35, 1e-12, "median");
  // t.test(sleep$extra[1:10]): 95 percent confidence interval -0.5297804 2.0297804
  closeAll(s.interval, [-0.5297804, 2.0297804], 5e-7, "t interval");
  H.equal(s.n, 10, "n");
  H.equal(s.values.length, 10, "values kept for distributions");
});

test("numeric: the mean difference matches R's Welch t.test, and the median difference is a seeded bootstrap", () => {
  const d = V.difference(sleep, "extra", "drug1", "drug2");
  close(d.estimate, -1.58, 1e-12, "mean difference");
  // t.test(extra ~ group, data = sleep): t = -1.8608, df = 17.776, CI -3.3654832 0.2054832
  closeAll(d.interval, [-3.3654832, 0.2054832], 5e-7, "Welch interval");
  H.includes(d.method, "17.8 Welch–Satterthwaite", "the degrees of freedom in the method");
  close(d.median.estimate, 0.35 - 1.75, 1e-12, "median difference");
  H.ok(d.median.interval[0] <= d.median.estimate && d.median.estimate <= d.median.interval[1], "the bootstrap interval holds the estimate");
  H.equal(V.difference(sleep, "extra", "drug1", "drug2").median.interval, d.median.interval, "the same data give the same bootstrap interval");
  const w = V.welch(0.75, 1.78901, 10, 2.33, 2.002249, 10);
  close(w.df, 17.776, 5e-3, "Welch–Satterthwaite df");
});

test("numeric aggregates: a supplied mean, sd and n give the same interval; a supplied interval is drawn as given", () => {
  const data = {
    alternatives: [{ id: "a" }, { id: "b" }, { id: "c" }], metrics: [{ id: "x", kind: "numeric" }],
    aggregates: [{ alternative: "a", metric: "x", mean: 0.75, sd: 1.7890097, n: 10 }, { alternative: "b", metric: "x", mean: 2.33, sd: 2.0022487, n: 10 }, { alternative: "c", metric: "x", mean: 5, lo: 4, hi: 7, source: "platform report" }],
  };
  const [a, , c] = V.summarize(data, "x");
  closeAll(a.interval, [-0.5297804, 2.0297804], 5e-6, "t interval from summaries");
  H.equal(a.fromAggregate, true, "marked as from aggregates");
  H.equal(c.interval, [4, 7], "supplied interval");
  H.equal(c.intervalMethod, "as reported by the source", "supplied interval method");
  closeAll(V.difference(data, "x", "a", "b").interval, [-3.3654832, 0.2054832], 5e-6, "Welch from summaries");
  H.equal(V.difference(data, "x", "a", "b").median, undefined, "no median bootstrap without observations");
  // Pooling two summaries gives the statistics of the pooled sample.
  const pooled = V.poolMoments([{ n: 5, mean: V.summarize({ ...sleep, observations: obs("drug1", "extra", SLEEP1.slice(0, 5)) }, "extra")[0].mean, sd: V.summarize({ ...sleep, observations: obs("drug1", "extra", SLEEP1.slice(0, 5)) }, "extra")[0].sd }, { n: 5, mean: V.summarize({ ...sleep, observations: obs("drug1", "extra", SLEEP1.slice(5)) }, "extra")[0].mean, sd: V.summarize({ ...sleep, observations: obs("drug1", "extra", SLEEP1.slice(5)) }, "extra")[0].sd }]);
  close(pooled.mean, 0.75, 1e-12, "pooled mean");
  close(pooled.sd, 1.78901, 5e-6, "pooled sd");
});

test("binary: Wilson intervals and Newcombe differences match Newcombe's worked examples", () => {
  const data = {
    alternatives: [{ id: "a" }, { id: "b" }], metrics: [{ id: "ok", kind: "binary" }],
    observations: [...obs("a", "ok", [...Array(56).fill(true), ...Array(14).fill(false)]), ...obs("b", "ok", [...Array(48).fill(true), ...Array(32).fill(false)])],
  };
  const [a] = V.summarize(data, "ok");
  H.equal([a.k, a.n], [56, 70], "k and n");
  close(a.rate, 0.8, 1e-12, "rate");
  const d = V.difference(data, "ok", "a", "b");
  close(d.estimate, 0.2, 1e-12, "difference");
  // Newcombe (1998b), example (a): 56/70 − 48/80, method 10: 0.0524 to 0.3339.
  closeAll(d.interval, [0.0524, 0.3339], 5e-5, "Newcombe interval");
  // Newcombe (1998a): 81/263 has the Wilson interval 0.2553 to 0.3662.
  const w = V.summarize({ alternatives: [{ id: "a" }], metrics: [{ id: "ok", kind: "binary" }], aggregates: [{ alternative: "a", metric: "ok", k: 81, n: 263 }] }, "ok")[0];
  closeAll(w.interval, [0.2553, 0.3662], 5e-5, "Wilson interval");
});

test("count: successes out of trials pool across observations; 0/1 numbers read as binary values", () => {
  const data = {
    alternatives: [{ id: "ad-a" }, { id: "ad-b" }], metrics: [{ id: "clicks", kind: "count" }],
    observations: [
      { alternative: "ad-a", metric: "clicks", value: 30, n: 40, case: "monday" }, { alternative: "ad-a", metric: "clicks", value: 26, n: 30, case: "tuesday" },
      { alternative: "ad-b", metric: "clicks", value: 48, n: 80 }, { alternative: "ad-b", metric: "clicks", value: 5 },
    ],
  };
  const [a, b] = V.summarize(data, "clicks");
  H.equal([a.k, a.n, b.k, b.n, b.invalid], [56, 70, 48, 80, 1], "pooled counts and the count without n set apart");
  H.equal(b.invalidReasons, { "count has no trials (n)": 1 }, "the reason is kept");
  closeAll(V.difference(data, "clicks", "ad-a", "ad-b").interval, [0.0524, 0.3339], 5e-5, "Newcombe interval");
  H.equal(V.summarize(data, "clicks", { cases: ["monday"] })[0].n, 40, "a case filter");
});

test("invalid observations are counted apart by reason and never as failures", () => {
  const data = {
    alternatives: [{ id: "a" }], metrics: [{ id: "ok", kind: "binary" }],
    observations: [...obs("a", "ok", [true, false, true]), { alternative: "a", metric: "ok", value: null }, { alternative: "a", metric: "ok", value: true, valid: false, invalid_reason: "timed out" }, { alternative: "a", metric: "ok", value: "maybe" }],
  };
  const [s] = V.summarize(data, "ok");
  H.equal([s.k, s.n, s.invalid], [2, 3, 3], "two of three valid, three invalid");
  H.equal(s.invalidReasons, { "no value": 1, "timed out": 1, "not true or false": 1 }, "reasons");
  H.equal(V.observationStatus(data).map(x => x === null), [true, true, true, false, false, false], "status per observation");
});

test("ordinal: level counts, the median level, and the probability of superiority, never a mean of indices", () => {
  const data = {
    alternatives: [{ id: "a" }, { id: "b" }], metrics: [{ id: "taste", kind: "ordinal", levels: ["low", "mid", "high"] }],
    observations: [...obs("a", "taste", ["high", "high", "mid"]), ...obs("b", "taste", ["mid", "low", 0])],
  };
  const [a, b] = V.summarize(data, "taste");
  H.equal(a.counts, [0, 1, 2], "counts in level order");
  H.equal([a.medianLevel, b.medianLevel], ["high", "low"], "median levels");
  H.equal(b.counts, [2, 1, 0], "an index names a level when the metric lists them");
  H.equal([a.mean, a.meanRank], [undefined, undefined], "no mean of level indices");
  // By hand: of 9 pairs a wins 8 and ties 1, so P(a>b) + ½P(tie) − ½ = (8 + 0.5)/9 − 0.5 (Vargha–Delaney A − ½).
  const d = V.difference(data, "taste", "a", "b");
  close(d.estimate, 8.5 / 9 - 0.5, 1e-12, "superiority");
  H.ok(d.interval[0] <= d.estimate && d.estimate <= d.interval[1] && d.interval[1] <= 0.5, "bootstrap interval within bounds");
  close(V.superiority([1, 2], [1, 2]), 0, 1e-12, "equal samples give zero");
  // Numeric values without levels order themselves; text values without levels are invalid, not ordered by guess.
  const loose = { alternatives: [{ id: "a" }], metrics: [{ id: "stars", kind: "ordinal" }], observations: obs("a", "stars", [3, 5, "4", 5]) };
  H.equal(V.summarize(loose, "stars")[0].levels, ["3", "4", "5"], "levels from numeric values");
  H.equal(V.summarize(loose, "stars")[0].counts, [1, 1, 2], "counts");
  const text = { alternatives: [{ id: "a" }], metrics: [{ id: "mood", kind: "ordinal" }], observations: obs("a", "mood", ["ok", "great"]) };
  H.equal(V.summarize(text, "mood")[0].invalid, 2, "text without levels is invalid");
});

test("rank: mean rank and first-place share from rankings; differences pair within rankings", () => {
  const data = {
    alternatives: [{ id: "a" }, { id: "b" }, { id: "c" }], metrics: [{ id: "place", kind: "rank", better: "lower" }],
    rankings: [{ order: ["a", "b", "c"] }, { order: ["b", "a", "c"] }, { order: ["a", "c", "b"] }],
  };
  const [a, b, c] = V.summarize(data, "place");
  closeAll([a.meanRank, b.meanRank, c.meanRank], [4 / 3, 2, 8 / 3], 1e-12, "mean ranks");
  closeAll([a.firstShare, b.firstShare, c.firstShare], [2 / 3, 1 / 3, 0], 1e-12, "first-place shares");
  const d = V.difference(data, "place", "a", "b");
  close(d.estimate, -2 / 3, 1e-12, "paired mean-rank difference");
  H.includes(d.method, "paired within 3 rankings", "paired method");
  // The paired t interval is the sleep data's paired example: t.test(..., paired = TRUE) gives -2.4598858 -0.7001142.
  const paired = { alternatives: [{ id: "a" }, { id: "b" }], metrics: [{ id: "r", kind: "rank" }], observations: [...SLEEP1.map((v, i) => ({ alternative: "a", metric: "r", value: v + 10, case: `c${i}` })), ...SLEEP2.map((v, i) => ({ alternative: "b", metric: "r", value: v + 10, case: `c${i}` }))] };
  closeAll(V.difference(paired, "r", "a", "b").interval, [-2.4598858, -0.7001142], 5e-7, "paired t interval");
});

test("preference: wins, losses and ties from judgments and rankings, with a Wilson interval and a win matrix", () => {
  const data = {
    alternatives: [{ id: "pb" }, { id: "jelly" }, { id: "both" }], metrics: [{ id: "taste", kind: "preference", better: "higher" }],
    preferences: [{ a: "pb", b: "jelly", winner: "pb" }, { a: "pb", b: "jelly", winner: "pb" }, { a: "jelly", b: "pb", winner: "jelly" }, { a: "pb", b: "jelly", winner: "tie" }, { a: "pb", b: "jelly", winner: null }],
    rankings: [{ order: ["both", "pb", "jelly"] }],
  };
  const [pb, jelly, both] = V.summarize(data, "taste");
  H.equal([pb.wins, pb.losses, pb.ties, pb.invalid], [3, 2, 1, 1], "pb");
  H.equal([jelly.wins, jelly.losses, both.wins], [1, 4, 2], "jelly and both");
  close(pb.rate, 3 / 5, 1e-12, "win rate over decisive judgments");
  H.equal(pb.invalidReasons, { "no judgment reached": 1 }, "unreached judgment counted apart");
  const m = V.winMatrix(data, "taste");
  H.equal(m.ids, ["pb", "jelly", "both"], "ids");
  H.equal(m.wins, [[0, 3, 0], [1, 0, 0], [1, 1, 0]], "wins");
  H.equal(m.ties[0][1] + m.ties[1][0], 2, "ties are symmetric");
  const d = V.difference(data, "taste", "pb", "jelly");
  close(d.estimate, (3 - 1) / 4, 1e-12, "net head-to-head share");
  H.includes(d.method, "1 tie set aside", "ties named in the method");
  const w = V.summarize({ alternatives: [{ id: "a" }], metrics: [{ id: "p", kind: "preference" }], aggregates: [{ alternative: "a", metric: "p", k: 81, n: 263 }] }, "p")[0];
  closeAll(w.interval, [0.2553, 0.3662], 5e-5, "preference aggregate Wilson");
  // Judgments naming no metric belong to the only preference metric; with two and no primary they belong to neither.
  H.equal(V.winMatrix({ ...data, metrics: [...data.metrics, { id: "looks", kind: "preference" }] }, "taste").wins[0][1], 0, "no owner with two preference metrics");
  H.equal(V.winMatrix(data).wins[0][1], 3, "the overall matrix reads judgments naming no metric");
});

const research = {
  title: "Which research direction?",
  alternatives: [
    { id: "a1", label: "Survey", group: ["Direction A", "Concept 1"] }, { id: "a2", label: "Interviews", group: ["Direction A", "Concept 1"] },
    { id: "a3", label: "Diary", group: ["Direction A", "Concept 2"] }, { id: "b1", label: "Simulation", group: ["Direction B", "Concept 1"] },
    { id: "b2", label: "Field test", group: ["Direction B", "Concept 3"] },
  ],
  metrics: [{ id: "promising", kind: "binary", better: "higher", primary: true }, { id: "cost", kind: "numeric", better: "lower", unit: "days" }],
  cases: [{ id: "lab" }, { id: "field" }],
  observations: [
    ...obs("a1", "promising", [true, true, false], { case: "lab" }), ...obs("a2", "promising", [true, false], { case: "field" }), ...obs("a3", "promising", [true, true], { case: "lab" }),
    ...obs("b1", "promising", [false, false, true], { case: "field" }), ...obs("b2", "promising", [false], { case: "lab" }),
    ...obs("a1", "cost", [3, 4]), ...obs("b1", "cost", [9, 11]),
  ],
  preferences: [{ a: "a1", b: "b1", winner: "a1" }, { a: "a1", b: "a2", winner: "a2" }, { a: "a3", b: "b2", winner: "b2" }],
  rankings: [{ order: ["a3", "b1", "a1"] }],
};

test("groups: pooled summaries at any depth, compared between and within directions", () => {
  const top = V.summarizeGroups(research, "promising", 0);
  H.equal(top.map(g => [g.group, g.k, g.n, g.members]), [["Direction A", 5, 7, ["a1", "a2", "a3"]], ["Direction B", 1, 4, ["b1", "b2"]]], "directions pooled");
  const concepts = V.summarizeGroups(research, "promising", 1);
  H.equal(concepts.map(g => g.group), ["Direction A › Concept 1", "Direction A › Concept 2", "Direction B › Concept 1", "Direction B › Concept 3"], "equal concept names under different directions stay apart");
  H.equal(V.summarizeGroups(research, "promising", 1, { groups: ["Direction A"] }).map(g => g.path[1]), ["Concept 1", "Concept 2"], "within one direction");
  const grouped = V.groupComparison(research, 0);
  const d = V.difference(grouped, "promising", "Direction A", "Direction B");
  close(d.estimate, 5 / 7 - 1 / 4, 1e-12, "difference between directions");
  H.ok(d.interval, "with an interval");
  // Judgments inside one direction are set aside at that level; between directions they count, rankings included.
  const pref = { ...research, metrics: [{ id: "pick", kind: "preference" }] };
  const g = V.groupComparison(pref, 0);
  // a1 beats b1 (A), b2 beats a3 (B), a1 over a2 stays inside A; the ranking a3, b1, a1 gives A over B and B over A.
  H.equal(V.winMatrix(g, "pick").wins, [[0, 2], [2, 0]], "direction-level head-to-head");
  H.equal(V.summarize(research, "promising", { groups: ["Direction B"] }).map(s => s.alternative), ["b1", "b2"], "a group filter on alternatives");
});

test("the composition adapts to the comparison's shape and keeps every section's data", () => {
  const spec = V.comparisonReport(research, { decision: { verdict: "adopt", headline: "Pursue direction A." } });
  const ids = spec.sections.map(s => s.id);
  H.equal(ids, ["verdict", "compared", "results", "groups", "cases", "judgments", "observations"], "sections");
  const results = spec.sections.find(s => s.id === "results").blocks.map(b => `${b.type}:${b.metric || (b.metrics || []).join("+")}`);
  H.equal(results, ["scorecard:promising+cost", "metric:promising", "metric:cost"], "primary first, scorecard for several metrics");
  H.equal(spec.sections.find(s => s.id === "groups").blocks[0], { type: "hierarchy", metric: "promising" }, "hierarchy on the primary metric");
  H.equal(spec.comparison.alternatives.length, 5, "the data travels with the specification");
  H.equal(spec.arms.map(a => a.id), ["a1", "a2", "a3", "b1", "b2"], "identity order");
  H.equal(V.validateSpec(spec), [], "no problems");
  const html = V.renderReport(spec);
  H.includes(html, "Pursue direction A.", "the decision");
  H.excludes(html, "Unknown block type", "an unknown block");
  // Two alternatives, no baseline: the difference between the two is drawn; a narrative includes, excludes, appends and places sections.
  const sandwich = {
    question: "Peanut butter or jelly?", alternatives: [{ id: "pb", label: "Peanut butter" }, { id: "jelly", label: "Jelly" }],
    metrics: [{ id: "taste", kind: "ordinal", levels: ["meh", "good", "great"], primary: true }], observations: [...obs("pb", "taste", ["great", "good"]), ...obs("jelly", "taste", ["meh", "good"])],
    sources: [{ label: "Kitchen notes", note: "two tasters" }],
  };
  const two = V.comparisonReport(sandwich, { exclude: ["observations"], append: { compared: [{ type: "text", text: "Same bread." }] }, sections: [{ title: "Next", blocks: [], after: "verdict" }], criteria: [{ label: "Taste", metric: "taste", weight: 2 }, { label: "Price", scores: { pb: 3, jelly: 4 }, weight: 1 }] });
  H.equal(two.sections.map(s => s.id || s.title), ["verdict", "Next", "compared", "results", "differences", "decision", "sources"], "narrative shaping");
  H.equal(two.sections.find(s => s.id === "differences").blocks[0].pairs, [["pb", "jelly"]], "first minus second");
  H.equal(two.sections.find(s => s.id === "compared").blocks.at(-1).text, "Same bread.", "appended block");
  H.equal(two.title, "Peanut butter or jelly?", "the question titles the page");
  H.equal(two.sections.find(s => s.id === "decision").blocks[0].type, "decision-matrix", "criteria give a decision matrix");
  // A baseline, and labels from the narrative.
  const based = V.comparisonReport({ ...sandwich, baseline: "jelly" }, { alternatives: { pb: { label: "PB" } } });
  H.equal(based.sections.find(s => s.id === "differences").blocks[0].baseline, "jelly", "baseline");
  H.equal(based.arms[0].label, "PB", "narrative label wins");
  // Nothing measured yet: the page still says what was compared.
  const bare = V.comparisonReport({ alternatives: [{ id: "x" }, { id: "y" }], metrics: [] });
  H.equal(bare.sections.map(s => s.id), ["verdict", "compared"], "only what exists");
});

test("the composition counts invalid observations visibly and says when all are invalid", () => {
  const data = { alternatives: [{ id: "a" }], metrics: [{ id: "ok", kind: "binary" }], observations: [{ alternative: "a", metric: "ok", value: null, valid: false, invalid_reason: "crashed" }] };
  const spec = V.comparisonReport(data);
  const verdict = spec.sections[0].blocks[0];
  H.includes(verdict.alert.text, "All 1 observation are invalid", "the alert");
  const figures = spec.sections[0].blocks[1].items.map(i => `${i.label}=${i.value}`);
  H.ok(figures.includes("Invalid=1") && figures.includes("Valid observations=0"), `figures: ${figures}`);
});

test("trial data becomes a comparison: invalid runs stay invalid, measures and checks become metrics, pairwise becomes judgments", () => {
  const trial = JSON.parse(fs.readFileSync(path.join(H.VISUALS, "examples", "fictional-trial.json"), "utf8"));
  const c = V.fromTrial(trial);
  H.equal(c.metrics[0], { id: "passed", label: "Passed", kind: "binary", better: "higher", primary: true, description: c.metrics[0].description }, "the passed metric");
  const passed = c.observations.filter(o => o.metric === "passed");
  H.equal(passed.length, trial.runs.length, "one passed observation per run");
  H.equal(passed.filter(o => o.valid === false).length, trial.runs.filter(r => r.passed === null).length, "invalid runs stay invalid");
  const arm = trial.runs[0].arm;
  const s = V.summarize(c, "passed").find(x => x.alternative === arm);
  const runs = trial.runs.filter(r => r.arm === arm);
  H.equal([s.k, s.n, s.invalid], [runs.filter(r => r.passed === true).length, runs.filter(r => r.passed !== null).length, runs.filter(r => r.passed === null).length], "pass counts match the runs");
  H.ok(c.metrics.some(m => m.kind === "numeric" && m.better === "lower"), "usage or timing as numeric metrics");
  H.ok(c.metrics.some(m => m.id.startsWith("check:")), "check values as metrics");
  H.equal(c.cases.map(x => x.id).sort(), [...new Set(trial.runs.map(r => r.scenario))].sort(), "scenarios as cases");
  if (trial.pairwise && Object.keys(trial.pairwise).length) H.ok(c.preferences.length > 0 && c.metrics.some(m => m.kind === "preference"), "pairwise as judgments");
  H.equal(V.validateComparison(c).filter(p => p.level === "error"), [], "the converted comparison has no errors");
  const spec = V.comparisonReport(c);
  H.excludes(V.renderReport(spec), "could not render", "a render failure");
});

test("the checker names references, values and judgments the views cannot use", () => {
  const where = list => H.plain(list).map(p => `${p.level} ${p.where}`);
  const problems = V.validateComparison({
    alternatives: [{ id: "a" }, { id: "b" }, { id: "a" }], metrics: [{ id: "ok", kind: "binary" }, { id: "n", kind: "numeric" }, { id: "lvl", kind: "ordinal" }, { id: "c", kind: "count" }, { id: "kind", kind: "score" }],
    observations: [{ alternative: "zz", metric: "ok", value: true }, { alternative: "a", metric: "ok", value: "yes" }, { alternative: "a", metric: "n", value: "3" }, { alternative: "a", metric: "lvl", value: "good" }, { alternative: "a", metric: "c", value: 4 }, { alternative: "b", metric: "c", value: 9, n: 4 }],
    preferences: [{ a: "a", b: "a", winner: "a" }, { a: "a", b: "b", winner: "c" }], rankings: [{ order: ["a", "a"] }], baseline: "bb",
  });
  const got = where(problems);
  for (const w of ["error comparison.alternatives[2].id", "error comparison.observations[0].alternative", "error comparison.observations[1].value", "error comparison.observations[2].value", "error comparison.metrics[2]", "error comparison.observations[4]", "error comparison.observations[5].value", "error comparison.preferences[0]", "error comparison.preferences[1].winner", "error comparison.rankings[0].order[1]", "error comparison.baseline", "error comparison.metrics[4].kind"])
    H.ok(got.includes(w), `expected ${w} in ${JSON.stringify(got)}`);
  H.equal(where(V.validateComparison(research)), [], "the research comparison is clean");
  H.equal(where(V.validateComparison(research, { include: ["verdct"], criteria: [{ label: "x" }], alternatives: { a9: { label: "?" } } })), ["error narrative.criteria[0]", "error narrative.include[0]", "warning narrative.alternatives.a9"], "narrative problems");
  // A specification's blocks are checked against the comparison it carries.
  const spec = { title: "T", comparison: research, sections: [{ title: "S", blocks: [{ type: "metric", metric: "promisng" }, { type: "scorecard", alternatives: ["a1", "zz"] }] }] };
  H.equal(where(V.validateSpec(spec)), ["error sections[0].blocks[0] (metric).metric", "error sections[0].blocks[1] (scorecard).alternatives[1]"], "block references");
  H.equal(where(V.validateSpec({ title: "T", sections: [{ title: "S", blocks: [{ type: "hierarchy" }] }] })), ["error sections[0].blocks[0] (hierarchy)"], "a comparison block needs comparison data");
});

test("an embedded comparison auto-mounts with its narrative", () => {
  const { document, target } = H.autoMountDocument({ "av-comparison": JSON.stringify(research), "av-narrative": JSON.stringify({ title: "Directions" }) });
  H.loadVisuals({ document });
  H.includes(target.innerHTML, "Directions", "the narrative title");
  H.includes(target.innerHTML, 'id="groups"', "the groups section");
});

H.report();
