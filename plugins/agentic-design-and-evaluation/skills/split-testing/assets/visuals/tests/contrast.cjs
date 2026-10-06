// The contrast block (difference in pass rate with a 95% Newcombe interval)
// and the interval arithmetic behind it, checked against the built bundle.
"use strict";
const H = require("./harness.cjs");
const F = require("./fixtures.cjs");
const { test } = H;

const V = H.loadVisuals();
const block = (input, spec = {}) => V.renderBlock({ type: "contrast", ...input }, V.createContext(spec, spec.cases || {}));
const near = (actual, expected, what, digits = 4) => {
  if (!Array.isArray(actual)) H.fail(`${what}: expected an interval, got ${JSON.stringify(actual)}`);
  const a = actual.map(x => x.toFixed(digits)), e = expected.map(x => x.toFixed(digits));
  H.equal(a, e, what);
};
// Four arms on four cases, six repeats: the fictional example's shape.
const grid = F.gridTrial({
  current: { photo: "PPPPFF", minutes: "PPFFFF", complaint: "PPPPFF", chart: "PPPPFF" },
  "current-copy": { photo: "PPFFFF", minutes: "PPFFFF", complaint: "PPPPPF", chart: "PPPFFF" },
  checklist: { photo: "PPPPFF", minutes: "PPPPPP", complaint: "PPPPPF", chart: "PPPPP-" },
});
const trialSpec = { trial: grid, arms: [{ id: "current", label: "Current guidance" }, { id: "current-copy", label: "Current (copy)" }, { id: "checklist", label: "Checklist" }] };

// ------------------------------------------------------------------ arithmetic

test("newcombe reproduces Newcombe (1998) Table II, method 10, to four decimals", () => {
  // Newcombe RG. Interval estimation for the difference between independent
  // proportions: comparison of eleven methods. Statistics in Medicine 1998;17:873–890.
  const table = [
    [[56, 70, 48, 80], [0.0524, 0.3339]],
    [[9, 10, 3, 10], [0.1705, 0.8090]],
    [[6, 7, 2, 7], [0.0582, 0.8062]],
    [[5, 56, 0, 29], [-0.0381, 0.1926]],
    [[0, 10, 0, 20], [-0.1611, 0.2775]],
    [[0, 10, 0, 10], [-0.2775, 0.2775]],
    [[10, 10, 0, 20], [0.6791, 1.0000]],
    [[10, 10, 0, 10], [0.6075, 1.0000]],
  ];
  for (const [args, expected] of table) near(H.plain(V.newcombe(...args)), expected, `newcombe(${args.join(", ")})`);
});

test("newcombe handles zero and full counts on either side and refuses unusable counts", () => {
  for (const args of [[0, 6, 6, 6], [6, 6, 0, 6], [0, 5, 0, 5], [5, 5, 5, 5], [0, 1, 1, 1]]) {
    const ci = H.plain(V.newcombe(...args)), d = args[0] / args[1] - args[2] / args[3];
    H.ok(ci && ci[0] >= -1 && ci[1] <= 1 && ci[0] <= d && d <= ci[1], `newcombe(${args}) gave ${JSON.stringify(ci)}, which does not hold ${d}`);
  }
  near(H.plain(V.newcombe(0, 5, 5, 5)), [-1, -0.3855], "0/5 against 5/5");
  for (const args of [[0, 0, 1, 2], [1, 2, 0, 0], [3, 2, 1, 2], [-1, 4, 1, 2], [NaN, 4, 1, 2], [1, 4, 1, Infinity]])
    H.equal(V.newcombe(...args), null, `newcombe(${args})`);
});

// ------------------------------------------------------------------ explicit counts

test("explicit rows need no trial and show the difference, its interval and both sides' counts", () => {
  const html = block({ rows: [{ label: "Pooled", k1: 20, n1: 23, k2: 14, n2: 24 }], a: { label: "Checklist" }, b: { label: "Current" } });
  H.includes(html, 'av-block--contrast');
  H.includes(html, '+29<span class="av-contrast-unit">pts</span>', "the difference in points");
  H.includes(html, "+3 to +50", "the 95% interval in points");
  H.includes(html, "<b>20</b>/23", "the first side's counts");
  H.includes(html, "<b>14</b>/24", "the second side's counts");
  H.includes(html, "Checklist minus Current (Pooled): +29 points, 95% interval +3 to +50.", "the accessible reading");
  H.includes(html, "The 95% interval lies above zero:", "the plain reading");
  H.includes(html, "--z:50.000%", "an axis centred on zero");
});

test("the reading names where the interval lies and never claims significance", () => {
  const html = block({ rows: [
    { label: "up", k1: 9, n1: 10, k2: 3, n2: 10 },
    { label: "down", k1: 0, n1: 5, k2: 5, n2: 5 },
    { label: "unclear", k1: 4, n1: 12, k2: 3, n2: 12 },
  ] });
  H.includes(html, "lies above zero");
  H.includes(html, "lies below zero");
  H.includes(html, "includes zero:</strong> these runs cannot tell");
  H.ok(!/significan|p-value|p =|winner/i.test(html.replace(/no p-values and no winners/, "")), "the view must not call a difference significant or name a winner");
});

test("a pass difference appears only when both sides have the same number of valid runs", () => {
  const same = block({ rows: [{ k1: 11, n1: 15, k2: 9, n2: 15 }] });
  H.includes(same, "+2 passes", "the difference in passes");
  const differ = block({ rows: [{ k1: 20, n1: 23, k2: 14, n2: 24 }] });
  H.excludes(differ, "av-contrast-passes", "a pass difference over unequal denominators");
});

test("invalid runs are counted beside each side and never as failures", () => {
  const html = block({ rows: [{ arm: "x", vs: "y", k1: 5, n1: 5, k2: 4, n2: 6, invalid1: 1 }] });
  H.includes(html, "<b>5</b>/5", "the valid count is unchanged by the invalid run");
  H.includes(html, "1 invalid", "the invalid count");
  H.includes(html, "never counted as failures");
  H.includes(html, "+33<span", "the difference over valid runs only (5/5 − 4/6)");
});

test("impossible counts are shown as given, not clamped, and get no interval", () => {
  const html = block({ rows: [{ label: "bad", k1: 12, n1: 5, k2: 1, n2: 5 }] });
  H.includes(html, "<b>12</b>/5", "the counts as given");
  H.includes(html, "12 passed of 5 valid runs, which cannot be");
  H.excludes(html, "av-contrast-ci\"", "an interval for impossible counts");
  H.excludes(html, "100%", "a clamped rate");
});

test("missing counts and empty sides are visible, never blank", () => {
  const html = block({ rows: [{ label: "absent", k1: 3, n1: 5, n2: 5 }, { label: "empty", k1: 0, n1: 0, k2: 2, n2: 4 }] });
  H.includes(html, '<span class="av-missing">missing</span>', "a missing count");
  H.includes(html, "counts are missing");
  H.includes(html, "has no valid runs");
  H.includes(html, "no valid runs</span>", "the empty side's chip");
  H.includes(html, '<span class="av-contrast-d av-contrast-d--none">—</span>', "a dash for the missing difference");
});

test("a threshold is drawn and read against the whole interval", () => {
  const html = block({ rows: [{ k1: 20, n1: 23, k2: 14, n2: 24 }, { k1: 6, n1: 6, k2: 0, n2: 6 }], threshold: { value: 0.15, label: "rule: +15 points" } });
  H.includes(html, "rule: +15 points", "the threshold's label");
  H.includes(html, "av-contrast-bar", "the threshold line");
  H.includes(html, "The observed +29 meets the +15-point bar, but the interval reaches down to +3.");
  H.includes(html, "All of it is above the +15-point bar.");
  H.includes(block({ rows: [{ k1: 1, n1: 2, k2: 1, n2: 2 }], threshold: 7 }), "outside −1 to 1", "a threshold written in points");
});

// ------------------------------------------------------------------ trial data

test("a baseline gives one row per other arm; identical copies become the chance-alone reference", () => {
  const html = block({ baseline: "current", identical: [["current", "current-copy"]] }, trialSpec);
  H.equal(H.count(html, "av-contrast-row--main"), 1, "comparison rows (the copy is not a candidate)");
  H.includes(html, "Checklist minus Current guidance:", "the checklist row");
  H.includes(html, "Chance alone", "the noise reference heading");
  H.equal(H.count(html, "av-contrast-row--noise"), 1, "noise rows");
  H.includes(html, "Current (copy) minus Current guidance:", "the copy against the original");
  H.includes(html, "av-contrast-band", "the identical-arm gap drawn on comparison rows");
  H.includes(html, "<b>20</b>/23", "valid runs only: the invalid checklist run is left out");
});

test("several baselines give one row per baseline, and by case adds a row per case", () => {
  const html = block({ baseline: ["current", "current-copy"], arms: ["checklist"], by: "case" }, trialSpec);
  H.equal(H.count(html, "av-contrast-row--main"), 2, "one comparison per baseline");
  H.equal(H.count(html, "av-contrast-row--case"), 8, "four cases under each comparison");
  H.includes(html, "By case");
  H.includes(html, "includes 0", "a placement chip on case rows");
});

test("without a baseline every pair of arms is compared, later minus earlier", () => {
  const html = block({}, trialSpec);
  H.equal(H.count(html, "av-contrast-row--main"), 3, "three pairs of three arms");
});

test("case variants pair by suffix, and a one-arm trial finds the suffix itself", () => {
  const variants = F.gridTrial({ only: { a: "PPPP", "a-v2": "PFFF", b: "PPFF", "b-v2": "PPPF" } });
  const spec = { trial: variants };
  const html = block({ pair: { suffix: "-v2" }, by: "case", a: { label: "With v2" }, b: { label: "Without" } }, spec);
  H.includes(html, "With v2 minus Without: −25 points", "pooled: 4/8 against 6/8");
  H.equal(H.count(html, "av-contrast-row--case"), 2, "one row per pair");
  const auto = block({}, spec);
  H.includes(auto, "“-v2” variants minus base cases:", "the suffix found without being named");
  const one = block({}, { trial: F.gridTrial({ only: { c: "PPPPPP", "c-review2": "PPFFFF" } }) });
  H.includes(one, "c-review2 minus c:", "a single pair is named by its cases");
});

test("two named sets compare any runs, and overlapping sets get no interval", () => {
  const html = block({ a: { arms: ["checklist"] }, b: { arms: ["current", "current-copy"] } }, trialSpec);
  H.includes(html, "Checklist minus Current guidance + Current (copy):", "sides described from their arms");
  H.includes(html, "<b>26</b>/48", "both copies pooled on the second side");
  const overlap = block({ a: { arms: ["checklist"] }, b: { cases: ["photo"] } }, trialSpec);
  H.includes(overlap, "share 6 runs", "the overlap named");
  H.excludes(overlap, 'class="av-contrast-ci"', "an interval for overlapping sets");
});

test("by arm splits a two-set comparison per arm, and sort orders comparisons by difference", () => {
  const variants = F.gridTrial({ x: { a: "PPPP", "a-v2": "PPFF" }, y: { a: "PPFF", "a-v2": "PPPP" } });
  const html = block({ pair: "-v2", by: "arm" }, { trial: variants });
  H.equal(H.count(html, "av-contrast-row--case"), 2, "one row per arm");
  H.includes(html, "By arm");
  const sorted = block({ baseline: "current", arms: ["current-copy", "checklist"], sort: "difference" }, trialSpec);
  H.ok(sorted.indexOf("Checklist minus") < sorted.indexOf("Current (copy) minus"), "the larger difference comes first");
});

test("rows whose sides weight the cases very differently are marked, with the reason on hand", () => {
  const lopsided = F.gridTrial({ base: { p: "PPPPPP", q: "FFFFFF" }, alt: { p: "PPPPPP", q: "F-----" } });
  const html = block({ baseline: "base" }, { trial: lopsided });
  H.includes(html, "uneven case mix");
  H.includes(html, "weight the cases differently");
  H.excludes(block({ baseline: "current" }, trialSpec), "uneven case mix</span>", "a mark for one invalid run in 24");
});

test("unknown arms, cases and options are named visibly and add no phantom arm", () => {
  const ctx = V.createContext(trialSpec);
  const html = V.renderBlock({ type: "contrast", baseline: "curent", arms: ["checklist", "ghost"], cases: ["nope"], by: "sideways" }, ctx);
  H.includes(html, "av-contrast-problems");
  H.includes(html, "“curent” is not an arm with runs in this trial");
  H.includes(html, "“ghost” is not an arm");
  H.includes(html, "“nope” is not a case");
  H.includes(html, "use &quot;arm&quot;, &quot;case&quot; or &quot;none&quot;");
  H.ok(!H.plain(ctx.arms.ids()).includes("ghost") && !H.plain(ctx.arms.ids()).includes("curent"), "a misspelled arm joined the identity order");
});

test("without rows or trial data the block renders a visible notice, not a crash", () => {
  const html = block({ baseline: "x" });
  H.includes(html, "av-block-error");
  H.includes(html, "needs");
});

test("a contrast block composes into a full report through a narrative section", () => {
  const spec = V.trialReport(grid, { arms: trialSpec.arms, sections: [{ id: "differences", title: "Difference from baseline", after: "arms", blocks: [{ type: "contrast", baseline: "current", identical: [["current", "current-copy"]] }] }] });
  const html = V.renderReport(spec);
  H.ok(H.sectionIds(html).includes("differences"), "the differences section");
  H.includes(html, "av-block--contrast");
});

// ------------------------------------------------------------------ escaping

test("every text field of a contrast block renders as escaped text", () => {
  const h = F.hostile, A = F.ARM_A, B = F.ARM_B, C1 = F.CASE_1;
  const trial = F.hostileTrial();
  const spec = { trial, arms: [{ id: A, label: h("c-arm-label") }, { id: B }], cases: { [C1]: h("c-case-label") } };
  const outputs = [
    block({ title: h("c-title"), description: h("c-description"), note: h("c-note"), a: { label: h("c-a-label") }, b: { label: h("c-b-label") },
      threshold: { value: 0.1, label: h("c-threshold-label") },
      rows: [{ label: h("c-row-label"), note: h("c-row-note"), k1: 1, n1: 2, k2: 0, n2: 2 }, { label: "Arms", arm: h("c-row-arm"), vs: h("c-row-vs"), k1: 1, n1: 2, k2: 1, n2: 2, identical: true }] }),
    block({ baseline: A, by: "case", identical: [[A, B]], threshold: 0.1 }, spec),
    block({ baseline: h("c-unknown-baseline"), cases: [h("c-unknown-case")] }, spec),
    block({ pair: { suffix: h("c-suffix") } }, spec),
    block({ a: { arms: [A], cases: [C1] }, b: { arms: [B] }, by: "case" }, spec),
  ];
  const all = outputs.join("\n");
  const raw = F.rawHostileFields(all);
  if (raw.length) H.fail(`unescaped markup from: ${raw.join(", ")}`);
  H.excludes(all, "<x-hostile", "a raw hostile element");
  const fields = ["c-title", "c-description", "c-note", "c-a-label", "c-b-label", "c-threshold-label", "c-row-label", "c-row-note", "c-row-arm", "c-row-vs",
    "c-arm-label", "c-case-label", "c-unknown-baseline", "c-unknown-case", "c-suffix", "arm-b", "case-1"];
  const hidden = fields.filter(f => !all.includes(F.escapedHostile(f)));
  if (hidden.length) H.fail(`these fields are not visible: ${hidden.join(", ")}`);
});

test("numbers reach markup and style attributes only as coerced numbers", () => {
  const html = block({ rows: [{ label: "x", k1: "3", n1: { toString: () => "<b>" }, k2: 1e400, n2: -2 }, { label: "y", k1: 1.7, n1: 4.2, k2: 1, n2: 4 }] });
  H.excludes(html, "<b>\"", "an object coerced into markup");
  H.excludes(html, "Infinity");
  H.excludes(html, "NaN");
  for (const m of html.matchAll(/style="([^"]*)"/g)) if (/[<>]|url\(|expression/i.test(m[1])) H.fail(`unexpected style text: ${m[1]}`);
  H.includes(html, "<b>1</b>/4", "fractional counts floor to whole runs");
});

H.report();
