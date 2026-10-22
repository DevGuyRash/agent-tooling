// Runs on one case repeat that case rather than sample new cases, so counts pooled over several cases are
// shown as counts with no interval, and each case keeps its own. Expected values are worked out by hand:
// Wilson for 3 of 3 is 43.85%–100% (3 / (3 + 1.96²)), for 0 of 3 0%–56.15%, for 2 of 3 20.8%–93.9%, for 1 of 3
// 6.1%–79.2%; pooled, 3 of 6 would be the 18.8%–81.2% ("19%–81%") that must not appear. Newcombe for 3 of 3
// minus 0 of 3 is 1 − √(0.5615² + 0.5615²) = +0.206 to +1, and for 3 of 3 minus 3 of 3 −0.5615 to +0.5615.
"use strict";
const H = require("./harness.cjs");
const F = require("./fixtures.cjs");
const { test } = H;

const V = H.loadVisuals();
const section = (spec, id) => spec.sections.find(s => s.id === id);
const ladderRow = (html, arm) => H.element(H.element(html, 'class="av-block av-block--ladder"'), `class="av-ladder-row" role="row" data-arm="${arm}"`);
const near = (x, want, what) => H.ok(Math.abs(x - want) < 5e-4, `${what}: ${x} against ${want}`);

test("an arm's runs across two cases are counted, not given a pooled interval", () => {
  const html = V.renderReport(V.trialReport(F.gridTrial({ a: { c1: "PPP", c2: "FFF" }, b: { c1: "PPP", c2: "PPP" } })));
  const row = ladderRow(html, "a");
  H.includes(row, '<span class="av-frac"><b>3</b>/6</span>', "the pooled count");
  H.includes(row, "across 2 cases", "how many cases it pools");
  H.includes(row, "3 of 6 valid runs passed across 2 cases, pooled counts with no interval", "the row's words");
  H.includes(row, 'class="av-share"', "a share bar in place of an estimate");
  for (const bad of ["av-ci-text", 'class="av-ci"', "50%", "19%–81%"]) H.excludes(row, bad, `a pooled rate or interval (${bad})`);
  H.excludes(html, "19%–81%", "the pooled interval anywhere in the report");
  const cases = H.element(html, 'class="av-block av-block--cases"');
  H.includes(cases, "44%–100%", "3 of 3 on one case, with its own interval");
  H.includes(cases, "0%–56%", "0 of 3 on the other, with its own interval");
});

test("an arm that ran one case keeps its interval", () => {
  const html = V.renderReport(V.trialReport(F.gridTrial({ a: { c: "PPF" }, b: { c: "PFF" } })));
  H.includes(ladderRow(html, "a"), "67%", "2 of 3 as a rate");
  H.includes(ladderRow(html, "a"), "21%–94%", "its Wilson interval");
  H.includes(ladderRow(html, "b"), "6%–79%", "1 of 3's Wilson interval");
  H.excludes(ladderRow(html, "a"), "across", "a pooled label on one case");
});

test("the runtime's null interval for an arm is final", () => {
  const data = F.gridTrial({ a: { c: "PPF" }, b: { c: "PFF" } });
  data.arms = { a: { passed: 2, valid: 3, runs: 3, interval: null }, b: { passed: 1, valid: 3, runs: 3, interval: [0.0615, 0.7923] } };
  const html = V.renderReport(V.trialReport(data));
  H.excludes(ladderRow(html, "a"), "21%–94%", "an interval the runtime withheld");
  H.excludes(ladderRow(html, "a"), 'class="av-ci"', "an interval bar the runtime withheld");
  H.includes(ladderRow(html, "b"), "6%–79%", "the other arm's interval");
});

test("one arm over two cases reports 3 of 6 runs, not 50% (19%–81%)", () => {
  const spec = V.trialReport(F.gridTrial({ only: { c1: "PPP", c2: "FFF" } }));
  const items = section(spec, "verdict").blocks[1].items;
  H.ok(!items.some(i => i.label === "Pass rate"), "a pooled pass rate figure");
  const runs = items.find(i => i.label === "Runs passed");
  H.ok(runs && runs.value === "3 of 6" && /across 2 cases/.test(runs.note), `the counts figure ${JSON.stringify(runs)}`);
  const verdict = H.element(V.renderReport(spec), 'class="av-block av-block--figures"');
  H.excludes(verdict, "19%–81%", "the pooled interval");
  const one = V.trialReport(F.gridTrial({ only: { c: "PPF" } }));
  const rate = section(one, "verdict").blocks[1].items.find(i => i.label === "Pass rate");
  H.ok(rate && rate.value === "67%" && /2 of 3 valid · 95% 21%–94%/.test(rate.note), `one case keeps its rate and interval ${JSON.stringify(rate)}`);
});

test("a difference pooled over cases has no interval, and each case's has one", () => {
  const spec = V.trialReport(F.gridTrial({ a: { c1: "FFF", c2: "PPP" }, b: { c1: "PPP", c2: "PPP" } }), { baseline: "a" });
  const block = section(spec, "arms").blocks.find(b => b.type === "contrast");
  H.equal(block.by, "case", "the composition asks for the per-case rows");
  const html = H.element(V.renderReport(spec), 'class="av-block av-block--contrast"');
  H.includes(html, "+50<span class=\"av-contrast-unit\">pts</span>", "6 of 6 minus 3 of 6, pooled");
  H.includes(html, "across 2 cases, no interval", "the pooled row says it has no interval");
  H.includes(html, "Pooled over 2 cases, so no interval", "and why");
  H.includes(html, "av-contrast-pt--pooled", "a hollow mark for the pooled difference");
  H.includes(html, "+21 to +100", "3 of 3 minus 0 of 3 on the first case");
  H.includes(html, "−56 to +56", "3 of 3 minus 3 of 3 on the second");
  H.equal(H.count(html, 'class="av-contrast-ci"'), 2, "an interval on each case row and none on the pooled row");
});

test("a collection member's setups pooled over cases carry counts, and each case its interval", () => {
  const trial = F.gridTrial({ ref: { c1: "FFF", c2: "PPP" }, cand: { c1: "PPP", c2: "PPP" } });
  trial.baseline = "ref";
  const data = { title: "Pooled", members: [{ id: "m", label: "M", trial, narrative: { decision: { verdict: "adopt", headline: "H." }, baseline: "ref" } }] };
  const s = V.collectionModel(data).members[0];
  const ref = s.rows.find(r => r.id === "ref"), cand = s.rows.find(r => r.id === "cand");
  H.equal(ref.text, "3 of 6 runs passed across 2 cases", "the pooled counts in words");
  H.equal(H.plain([ref.interval, ref.cases]), [null, 2], "no pooled interval");
  near(ref.perCase.find(c => c.id === "c2").interval[0], 0.4385, "3 of 3's lower bound");
  near(ref.perCase.find(c => c.id === "c1").interval[1], 0.5615, "0 of 3's upper bound");
  H.equal(cand.text, "6 of 6 runs passed across 2 cases", "the candidate's pooled counts");
  const g = s.gains[0];
  H.equal(H.plain([g.interval, g.cases, g.delta]), [null, 2, 0.5], "the pooled change: +50 points with no interval");
  const c1 = g.perCase.find(c => c.id === "c1"), c2 = g.perCase.find(c => c.id === "c2");
  H.equal(c1.delta, 1, "the first case's change");
  near(c1.interval[0], 0.2059, "its Newcombe lower bound"); near(c1.interval[1], 1, "its upper bound");
  near(c2.interval[0], -0.5615, "the second case's lower bound"); near(c2.interval[1], 0.5615, "its upper bound");
  const html = V.renderReport(V.collectionReport(data));
  H.includes(html, "none: pooled over 2 cases", "the exact numbers say why there is no interval");
  H.includes(html, "Each case on its own, with its 95% interval (2 cases)", "the per-case breakdown");
  H.includes(html, "44%–100%", "a case's own interval in it");
  H.excludes(html, "19%–81%", "the pooled interval");
  // Two reports side by side: matched setups pooled over cases are differenced without an interval.
  const twin = { ...data, members: [...data.members, { ...data.members[0], id: "n", label: "N" }] };
  const side = V.renderReport(V.compareReport(twin, "m", "n"));
  H.includes(side, "B − A <b>±0 pts</b> <span class=\"av-muted\">(pooled over cases, no interval)</span>", "a difference of pooled values with no interval");
});

test("the all-cases row of a pairwise judgment counts decisive pairs, with no pooled interval", () => {
  const data = F.gridTrial({ a: { c1: "PP", c2: "PP" }, b: { c1: "PP", c2: "PP" } });
  const st = (aw, bw, rate, iv) => ({ a_wins: aw, b_wins: bw, tie: 0, inconsistent: 0, invalid: 0, pairs: aw + bw, decisive: aw + bw, a_win_rate: rate, a_win_rate_interval: iv });
  data.pairwise = { a__b: { arms: ["a", "b"], overall: st(3, 1, 0.75, [0.3, 0.95]), scenarios: { c1: st(2, 0, 1, [0.34, 1]), c2: st(1, 1, 0.5, [0.09, 0.91]) } } };
  const html = H.element(V.renderReport(V.trialReport(data)), 'class="av-block av-block--pairwise"');
  H.includes(html, "decisive pairs won, across 2 cases", "the pooled row's counts");
  H.excludes(html, "30%–95%", "the pooled interval");
  H.includes(html, "34%–100%", "the first case's own interval");
});

test("a ladder restricted to some arms shows only those arms", () => {
  // Arm a ran 2 of 3 on one case, arm b 1 of 3; a ladder of arm a alone must not list b.
  const data = F.gridTrial({ a: { c: "PPF" }, b: { c: "PFF" } });
  const html = V.renderReport({ title: "Arms", trial: data, sections: [{ title: "One arm", blocks: [{ type: "ladder", arms: ["a"], read: { says: "Arm a alone." } }] }] });
  H.includes(html, 'data-arm="a"', "the arm asked for");
  H.excludes(H.element(html, 'class="av-block av-block--ladder"'), 'data-arm="b"', "an arm left out of the ladder");
});

test("the general comparison of a trial pools runs over cases without an interval, and keeps each case's", () => {
  // Arm a: 3 of 3 on c1 and 0 of 3 on c2; arm b: 6 of 6. Pooled, a is 3 of 6, which must not read 50% (19%–81%).
  const general = V.fromTrial(F.gridTrial({ a: { c1: "PPP", c2: "FFF" }, b: { c1: "PPP", c2: "PPP" } }));
  const [a] = V.summarize(general, "passed");
  H.equal(H.plain([a.k, a.n, a.interval, a.cases]), [3, 6, null, 2], "a pooled over two cases: counts, no interval");
  const d = V.difference(general, "passed", "b", "a");
  H.equal(H.plain([d.estimate, d.interval]), [0.5, null], "6 of 6 minus 3 of 6, with no interval");
  near(V.summarize(general, "passed", { cases: ["c1"] })[0].interval[0], 0.4385, "c1 alone keeps 3 of 3's interval");
  near(V.difference(general, "passed", "b", "a", { cases: ["c2"] }).interval[0], 0.2059, "c2 alone keeps 3 of 3 minus 0 of 3's interval");
  const html = V.renderReport(V.comparisonReport(general, { baseline: "a" }));
  for (const bad of ["19%–81%", "19% to 81%"]) H.excludes(html, bad, "the pooled interval anywhere in the general report");
  H.includes(html, "across 2 cases", "a value says it pools cases");
});

test("supplied totals pool repeats like observations do: preference and ordinal aggregates over two cases have no interval", () => {
  // The reviewer's preference totals: 3 of 3 on c1 and 0 of 3 on c2 pool to 3 of 6, which must not read 50% (18.76%–81.24%).
  const pref = { alternatives: [{ id: "a" }, { id: "b" }], metrics: [{ id: "pick", kind: "preference" }],
    aggregates: [{ alternative: "a", metric: "pick", case: "c1", k: 3, n: 3 }, { alternative: "a", metric: "pick", case: "c2", k: 0, n: 3 }] };
  H.equal(V.validateComparison(pref), [], "valid input");
  const [p] = V.summarize(pref, "pick");
  H.equal(H.plain([p.rate, p.interval, p.cases]), [0.5, null, 2], "3 of 6 pooled over two cases: no interval");
  near(V.summarize(pref, "pick", { cases: ["c1"] })[0].interval[0], 0.4385, "c1 alone keeps 3 of 3's Wilson interval");
  // Ordinal totals with no n: three "good" on c1 and three "bad" on c2 are three repeats of each case.
  const ord = { alternatives: [{ id: "a" }, { id: "b" }], metrics: [{ id: "q", kind: "ordinal", levels: ["bad", "good"] }],
    aggregates: [{ alternative: "a", metric: "q", case: "c1", counts: { good: 3 } }, { alternative: "a", metric: "q", case: "c2", counts: { bad: 3 } },
      { alternative: "b", metric: "q", case: "c1", counts: { good: 2, bad: 1 } }, { alternative: "b", metric: "q", case: "c2", counts: { bad: 2, good: 1 } }] };
  H.equal(V.validateComparison(ord), [], "valid input");
  const [oa] = V.summarize(ord, "q");
  H.equal(H.plain([oa.n, oa.cases]), [6, 2], "six ordinal values from two cases");
  const d = V.difference(ord, "q", "a", "b");
  H.equal(d.interval, null, "no pooled bootstrap interval over cases that hold repeats");
  H.includes(d.method, "pooled over 2 cases", "says why");
});

test("head-to-head judgments that repeat their cases give win rates and first places without an interval", () => {
  // x beats y three times in case u; y beats x twice in case v: x wins 3 of 5 and y 2 of 5, pooled over 2 cases.
  // Pooled, Wilson for 3 of 5 would be 23.1%–88.2% ("23%–88%") and for 2 of 5 11.8%–76.9% ("12%–77%"); neither may appear.
  const duel = (c, winner) => ({ a: "x", b: "y", winner, case: c });
  const view = data => H.element(V.renderReport({ title: "J", comparison: data, sections: [{ title: "J", blocks: [{ type: "preferences" }] }] }), 'class="av-block av-block--preferences"');
  const base = { alternatives: [{ id: "x" }, { id: "y" }], metrics: [] };
  const repeated = view({ ...base, preferences: [duel("u", "x"), duel("u", "x"), duel("u", "x"), duel("v", "y"), duel("v", "y")] });
  H.includes(repeated, "5 decisive across 2 cases, no interval", "the count and why it has no interval");
  for (const bad of ["23%–88%", "12%–77%", 'class="av-ci"']) H.excludes(repeated, bad, `a pooled interval (${bad})`);
  H.includes(repeated, "no interval says whether the gap is chance", "the lede does not read a pooled gap as settled");
  // One judgment per case samples cases: x wins 2 of 3, Wilson 20.8%–93.9%.
  const sampled = view({ ...base, preferences: [duel("u", "x"), duel("v", "x"), duel("w", "y")] });
  H.includes(sampled, "21%–94%", "an interval where each case was judged once");
  // Rankings: [x, y] twice in case u and [y, x] twice in case v. x is first in 2 of 4 across 2 cases; Wilson for 2 of 4
  // would be 15.0%–85.0% ("15%–85%"), for the first places and for the win rate the rankings imply alike.
  const ranked = view({ ...base, rankings: [{ order: ["x", "y"], case: "u" }, { order: ["x", "y"], case: "u" }, { order: ["y", "x"], case: "v" }, { order: ["y", "x"], case: "v" }] });
  H.includes(ranked, "50% · across 2 cases, no interval", "the first-place share and why it has no interval");
  H.excludes(ranked, "15%–85%", "a pooled interval for first places or wins");
});

test("counts written by hand carry an interval only when how they were sampled allows one", () => {
  // The reviewer's trial: arm a passes three repeats of case u and fails three of v; arm b passes three of u alone.
  // Pooled, Wilson for 3 of 6 would be 18.8%–81.2% ("19%–81%"); for b's 3 of 3 on one case it is 43.9%–100% ("44%–100%").
  const trial = F.gridTrial({ a: { u: "PPP", v: "FFF" }, b: { u: "PPP" } });
  const view = (block, data = trial) => V.renderReport({ title: "Hand", ...(data ? { trial: data } : {}), sections: [{ title: "Counts", reading: "Totals across two repeated cases.", blocks: [block] }] });
  const ivs = (rows, extra = {}, data) => H.element(view({ type: "intervals", rows, ...extra }, data), 'class="av-block av-block--ladder"');
  // A row naming an arm of the attached trial takes that arm's cases.
  const pooled = ivs([{ arm: "a", k: 3, n: 6 }]);
  H.excludes(pooled, "19%–81%", "a pooled interval for arm a");
  H.excludes(pooled, 'class="av-ci"', "an interval band");
  H.includes(pooled, "across 2 cases", "says it pools two cases");
  H.includes(ivs([{ arm: "b", k: 3, n: 3 }]), "44%–100%", "arm b ran one case, so its count keeps its interval");
  // The reviewer's trend: the same count as a point, with no whisker.
  const trend = H.element(view({ type: "trend", stages: ["now"], series: [{ arm: "a", label: "Original", points: [{ stage: "now", k: 3, n: 6 }] }] }), 'class="av-block av-block--trend"');
  H.excludes(trend, "av-svg-whisker", "a pooled whisker");
  H.includes(trend, "across 2 cases", "the point says it pools two cases");
  // With no trial, the author says how the counts were sampled; saying nothing gives none.
  const silent = ivs([{ label: "Observed", k: 3, n: 6 }], {}, null);
  H.excludes(silent, "19%–81%", "an interval with no sampling stated");
  H.includes(silent, "no interval", "says it has none");
  H.includes(ivs([{ label: "Observed", k: 3, n: 6 }], { independent: true }, null), "19%–81%", "independent counts keep theirs");
  H.includes(ivs([{ label: "Observed", k: 3, n: 6, cases: 1 }], {}, null), "19%–81%", "repeats of one case keep theirs");
  const two = ivs([{ label: "Observed", k: 3, n: 6, cases: 2 }], { independent: true }, null);
  H.excludes(two, "19%–81%", "a count the row says pools two cases");
  H.includes(two, "across 2 cases", "says so");
  const silentTrend = H.element(view({ type: "trend", stages: ["now"], series: [{ label: "Observed", points: [{ stage: "now", k: 3, n: 6 }] }] }, null), 'class="av-block av-block--trend"');
  H.excludes(silentTrend, "av-svg-whisker", "a whisker with no sampling stated");
  H.includes(H.element(view({ type: "trend", independent: true, stages: ["now"], series: [{ label: "Observed", points: [{ stage: "now", k: 3, n: 6 }] }] }, null), 'class="av-block av-block--trend"'), "av-svg-whisker", "independent counts keep their whisker");
  // Ladder and contrast rows written by hand follow the same rule.
  const ladder = H.element(view({ type: "ladder", rows: [{ arm: "x", k: 3, n: 6 }] }, null), 'class="av-block av-block--ladder"');
  H.excludes(ladder, "19%–81%", "a hand-written ladder row with no sampling stated");
  H.includes(H.element(view({ type: "ladder", independent: true, rows: [{ arm: "x", k: 3, n: 6 }] }, null), 'class="av-block av-block--ladder"'), "19%–81%", "an independent ladder row");
  // 3 of 6 minus 0 of 6: the difference keeps its Newcombe interval only when the counts are said to be independent.
  const contrast = H.element(view({ type: "contrast", rows: [{ arm: "x", vs: "y", k1: 3, n1: 6, k2: 0, n2: 6 }] }, null), 'class="av-block av-block--contrast"');
  H.excludes(contrast, 'class="av-contrast-ci"', "a hand-written difference with no sampling stated");
  H.includes(contrast, "no interval", "says so");
  H.includes(H.element(view({ type: "contrast", independent: true, rows: [{ arm: "x", vs: "y", k1: 3, n1: 6, k2: 0, n2: 6 }] }, null), 'class="av-block av-block--contrast"'), 'class="av-contrast-ci"', "an independent difference keeps its interval");
});

test("a count's case total is compared, never spelled out one case at a time", () => {
  // The reviewer's row: a case total the checker accepts but no array can hold. It pools more than one case, so no interval.
  const html = H.element(V.renderReport({ title: "Big", sections: [{ title: "C", blocks: [{ type: "intervals", rows: [{ label: "Huge", k: 2147483648, n: 4294967296, cases: 4294967296 }] }] }] }), 'class="av-block av-block--ladder"');
  H.excludes(html, "could not render", "the block renders");
  H.includes(html, "across 4,294,967,296 cases, no interval", "a pooled count with no interval");
});

H.report();
