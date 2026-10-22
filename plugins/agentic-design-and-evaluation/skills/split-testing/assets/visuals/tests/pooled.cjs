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
  H.includes(html, "across 2 cases, no interval", "a value says it pools cases");
});

H.report();
