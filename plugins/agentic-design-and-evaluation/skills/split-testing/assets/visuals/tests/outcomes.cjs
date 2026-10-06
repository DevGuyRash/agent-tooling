// Invalid runs are excluded from rates and never counted as failures, yet stay
// visible; missing values render as visibly missing rather than as blanks.
"use strict";
const H = require("./harness.cjs");
const F = require("./fixtures.cjs");
const { test } = H;

const V = H.loadVisuals();

// Arm "steady": 2 passes, 1 failure and 3 invalid runs. Arm "solid": 4 passes,
// 2 failures. Arm "broken": one invalid run and nothing else.
const seconds = { "c1__steady__r1": 10, "c1__steady__r2": 20, "c1__steady__r3": 1000, "c2__steady__r1": 30, "c2__steady__r2": 2000, "c2__steady__r3": 3000 };
const data = F.gridTrial({ steady: { c1: "PP-", c2: "F--" }, solid: { c1: "PFF", c2: "PPP" }, broken: { c1: "-" } }, run => ({
  seconds: seconds[run.job] ?? 15,
  usage: { output_tokens: 100 },
  invalid_reason: run.passed === null ? (run.job === "c2__steady__r3" ? "executor-crashed" : "timeout") : null,
  // Invalid runs carry failing checks; they must not reach any denominator.
  checks: { reply_written: run.passed === null ? false : run.job !== "c2__steady__r1", length_ok: run.passed !== false },
  judge: run.passed === null ? null : { verdict: run.passed ? "pass" : "fail", reason: "ok" },
}));
data.plan.scenarios.forEach(s => { s.required = ["reply_written"]; });
const spec = V.trialReport(data);
const html = V.renderReport(spec);
// The run grid is drawn only when a narrative's include names it.
const gridHtml = V.renderReport(V.trialReport(data, { include: ["grid"] }));
const block = kind => H.element(kind === "tapestry" ? gridHtml : html, `class="av-block av-block--${kind}"`);
const ladderRow = arm => H.element(block("ladder"), `class="av-ladder-row" role="row" data-arm="${arm}"`);

test("the ladder rates an arm over valid runs only", () => {
  const row = ladderRow("steady");
  H.includes(row, "2 of 3 valid runs passed, 67%", "a rate over the three valid runs");
  H.includes(row, '<span class="av-frac"><b>2</b>/3</span>', "the 2/3 fraction");
  H.excludes(row, "of 6 valid", "the invalid runs in the denominator");
});

test("the ladder keeps invalid counts visible beside the rate", () => {
  H.includes(ladderRow("steady"), "3 invalid", "the invalid chip");
  H.includes(ladderRow("steady"), "Invalid runs are excluded, never counted as failures", "the chip's explanation");
  H.excludes(ladderRow("solid"), "invalid</span>", "an invalid chip on an arm without invalid runs");
});

test("an arm whose runs were all invalid stays in the ladder with no rate", () => {
  const row = ladderRow("broken");
  H.includes(row, "no valid runs", "the no-valid-runs notice");
  H.includes(row, "1 invalid", "its invalid count");
  H.excludes(row, "0%", "a zero rate");
});

test("the tapestry draws invalid runs as invalid marks and counts them apart", () => {
  const tap = block("tapestry");
  const cell = H.element(tap, 'title="0 of 1 valid runs passed (95% interval 0%–79%); 2 invalid"');
  H.includes(cell, 'data-arm="steady"', "the cell's arm");
  H.includes(cell, "--lo:0.000%;--hi:79.346%", "the cell's interval on its track");
  H.includes(cell, '<span class="av-frac"><b>0</b>/1</span>', "0 of 1 valid");
  H.includes(cell, 'title="2 invalid"', "the invalid count");
  H.equal(H.count(cell, "av-run--invalid"), 2, "invalid marks in the cell");
  H.equal(H.count(cell, "av-run--fail"), 1, "failure marks in the cell");
  H.equal(H.count(tap, "av-run--invalid"), 4, "invalid marks in the tapestry");
  H.equal(H.count(tap, "av-run--fail"), 3, "failure marks in the tapestry");
});

test("the invalid view groups every invalid run by reason without calling them failures", () => {
  const inv = block("invalid");
  H.includes(inv, "4 of 13 runs (31%) produced no valid result", "the share of invalid runs");
  H.includes(inv, "never counted as failures", "the statement that invalid is not failure");
  H.includes(inv, '<code class="av-inv-reason">timeout</code><span class="av-inv-count">3 runs</span>', "the timeout group");
  H.includes(inv, '<code class="av-inv-reason">executor-crashed</code><span class="av-inv-count">1 run</span>', "the crash group");
  H.equal(H.count(inv, "av-run av-run--invalid"), 4, "one mark per invalid run");
});

test("a trial without invalid runs says so: no invalid section, a zero figure and an all-clear block", () => {
  const data = F.gridTrial({ a: { c: "PF" } });
  const spec = V.trialReport(data), clean = V.renderReport(spec);
  H.ok(!spec.sections.some(s => s.id === "invalid"), "an invalid-runs section for a trial without invalid runs");
  H.includes(H.element(clean, 'class="av-block av-block--figures"'), '<dt>Invalid</dt><dd><span class="av-figure-value">0</span><span class="av-figure-note">none</span>', "the zero invalid figure");
  H.includes(V.renderBlock({ type: "invalid" }, V.createContext({ trial: data })), "Every run finished with a valid result.", "the all-clear");
});

test("the ledger labels invalid runs as invalid, never as failed", () => {
  const ledger = block("ledger");
  H.equal(H.count(ledger, 'data-outcome="invalid" tabindex="0"'), 4, "invalid ledger rows");
  H.equal(H.count(ledger, 'data-outcome="fail" tabindex="0"'), 3, "failed ledger rows");
  H.includes(ledger, "Failed <span>3</span>", "the failure count");
  H.includes(ledger, "Invalid <span>4</span>", "the invalid count");
});

test("the headline figures count valid and invalid runs separately", () => {
  const figures = block("figures");
  H.includes(figures, "<dt>Runs</dt><dd><span class=\"av-figure-value\">13</span>", "13 runs");
  H.includes(figures, "<dt>Valid</dt><dd><span class=\"av-figure-value\">9</span>", "9 valid");
  H.includes(figures, "<dt>Invalid</dt><dd><span class=\"av-figure-value\">4</span><span class=\"av-figure-note\">excluded, not failures</span>", "4 invalid, not failures");
});

test("checks count only valid runs", () => {
  const row = H.element(block("checks"), "<tr><th scope=\"row\"><code>reply_<wbr>written</code>");
  // steady: valid runs c1 r1, c1 r2 (true) and c2 r1 (false): 2 of 3, not 2 of 6.
  H.includes(row, '<span class="av-frac"><b>2</b>/3</span>', "2 of 3 valid runs for steady");
  H.includes(row, '<td class="av-heat av-heat--none"><span>—</span></td>', "a dash for the arm with no valid runs");
});

test("judge pass counts use valid judged runs only", () => {
  const checks = block("checks");
  const row = H.element(checks, "<tr><th scope=\"row\">verdict = pass</th>");
  H.includes(row, '<span class="av-frac"><b>2</b>/3</span>', "2 of 3 judged valid runs for steady");
});

test("cost medians describe valid runs; invalid runs are counted beside the axis, not placed on it", () => {
  const cost = block("cost");
  H.includes(cost, "Executor time", "the executor time panel");
  const strip = H.element(cost.slice(cost.indexOf("Executor time")), 'class="av-strip-row" data-arm="steady"');
  H.includes(strip, '<span class="av-strong">20 s</span><span class="av-muted">median</span>', "the median of 10, 20 and 30 seconds");
  H.equal(H.count(strip, "av-dot--invalid"), 0, "invalid runs are not placed on the axis");
  H.includes(strip, "3 not shown", "the invalid runs are counted beside the row");
});

test("tally and the Wilson interval exclude invalid runs", () => {
  const ci = V.wilson(2, 3);
  H.ok(ci && ci[0] > 0.2 && ci[0] < 0.21 && ci[1] > 0.93 && ci[1] < 0.95, `Wilson 2/3 interval ${JSON.stringify(ci)}`);
  H.equal(V.wilson(0, 0), null, "no interval without valid runs");
});

// ------------------------------------------------------------------ missing values

const ctx = V.createContext({});
const render = b => V.renderBlock(b, ctx);
const MISSING = '<span class="av-missing" title="No value was recorded">';

test("facts mark a null or absent value as missing", () => {
  const out = render({ type: "facts", items: [{ label: "A", value: null }, { label: "B" }] });
  H.equal(H.count(out, `${MISSING}missing</span>`), 2, "missing markers");
});

test("tables mark null cells and short rows as missing", () => {
  const out = render({ type: "table", columns: ["Name", "Value", "Extra"], rows: [["a", null], ["b", { value: null, note: "n" }, 1]] });
  H.equal(H.count(out, `${MISSING}missing</span>`), 3, "missing markers");
});

test("a table without rows says so", () => {
  H.includes(render({ type: "table", columns: ["A"], rows: [] }), '<p class="av-empty">No rows.</p>', "the empty notice");
});

test("matrices mark absent and missing cells as not established", () => {
  const out = render({ type: "matrix", columns: [{ id: "c1", label: "C1" }, { id: "c2", label: "C2" }], rows: [{ id: "r", label: "R" }], cells: [{ row: "r", column: "c2", status: "missing" }] });
  H.equal(H.count(out, `${MISSING}not established</span>`), 2, "not-established markers");
});

test("trend values mark an absent point as missing", () => {
  const out = render({ type: "trend", stages: ["one", "two"], series: [{ label: "s", points: [{ stage: "one", value: 0.5 }] }] });
  H.includes(H.element(out, '<details class="av-data">'), MISSING, "a missing marker in the values table");
  H.includes(render({ type: "trend", stages: ["one"], series: [{ label: "s", points: [{ stage: "one", value: null }] }] }), "No values to plot.", "the empty notice");
});

test("bars count a missing segment value", () => {
  const out = render({ type: "bars", segments: [{ id: "a", label: "A" }, { id: "b", label: "B" }], rows: [{ label: "r", values: { a: 2, b: null } }] });
  H.includes(out, 'title="B not recorded">1 missing</span>', "the missing count");
  H.includes(out, "B missing", "the missing segment in the bar's label");
});

test("intervals show a row without a value as having none", () => {
  const out = render({ type: "intervals", rows: [{ label: "none", value: null }, { label: "zero", k: 0, n: 0 }] });
  H.equal(H.count(out, '<span class="av-ladder-none">no value</span>'), 2, "no-value markers");
  H.equal(H.count(out, '<span class="av-rate">—</span>'), 2, "dashes for the rates");
});

test("an unevaluated rule check says so", () => {
  const out = render({ type: "verdict", headline: "h", checks: [{ label: "rule", observed: "x", met: null }] });
  H.includes(out, "not evaluated", "the not-evaluated state");
});

test("the tapestry marks a case an arm never ran", () => {
  const sparse = V.renderReport(V.trialReport(F.gridTrial({ a: { c1: "P", c2: "F" }, b: { c1: "P" } }), { include: ["grid"] }));
  H.includes(H.element(sparse, 'class="av-block av-block--tapestry"'), '<span class="av-tap-none">not run</span>', "the not-run cell");
});

test("the ledger and plan show dashes for unrecorded time, judge and settings", () => {
  const sparse = F.gridTrial({ a: { c: "P" }, b: { c: "F" } });
  sparse.plan.arms.a.model = "fictional";
  const out = V.renderReport(V.trialReport(sparse));
  const ledger = H.element(out, 'class="av-block av-block--ledger"');
  H.includes(ledger, 'data-sort="-1">—</td>', "a dash for missing time");
  H.includes(ledger, '<td><span class="av-muted">—</span></td>', "a dash for a missing judge verdict");
  const plan = V.renderBlock({ type: "plan" }, V.createContext({ trial: sparse }));
  H.includes(plan, '<td><span class="av-muted">—</span></td>', "a dash for an unrecorded setting");
});

test("a figure with a null value shows it as missing", () => {
  const out = render({ type: "figures", items: [{ value: null, label: "Judge" }] });
  H.ok(!/<span class="av-figure-value[^"]*"><\/span>/.test(out), `the value renders as an empty element: ${out}`);
});

H.report();
