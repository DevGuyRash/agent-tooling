// Browser-behavior pieces that need no browser: CSV export and the run drawer's
// markup, checked against the built bundle. test_enhance.py runs this script.
"use strict";
const H = require("./harness.cjs");
const F = require("./fixtures.cjs");
const { test } = H;

const V = H.loadVisuals();

/** Fields of an RFC 4180 document, for checking what a spreadsheet would read. */
function parseCsv(text) {
  const rows = [];
  let row = [], field = "", quoted = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (quoted) {
      if (c === '"' && text[i + 1] === '"') { field += '"'; i++; }
      else if (c === '"') quoted = false;
      else field += c;
    } else if (c === '"' && field === "") quoted = true;
    else if (c === ",") { row.push(field); field = ""; }
    else if (c === "\r" && text[i + 1] === "\n") { row.push(field); rows.push(row); row = []; field = ""; i++; }
    else field += c;
  }
  if (field !== "" || row.length) { row.push(field); rows.push(row); }
  return rows;
}

/** A small trial with one run of each kind of ending. */
function kindsTrial() {
  const base = { status: "ok", invalid_reason: null, seconds: 30, setup_seconds: 0, checks_seconds: 0, judge_seconds: 0, commands: 4, usage: { output_tokens: 300, input_tokens: 900 } };
  return {
    name: "kinds", run_directory: "trials/kinds",
    plan: {
      arms: { a: { executor: "command" }, b: { executor: "command" } },
      scenarios: [
        { name: "budget", prompt: "Make it fast.", required: ["results_correct", "within_budget", "recorded_later"] },
        { name: "reply", prompt: "Reply.", judge: { question: "Is the reply faithful?" }, required: ["reply_written"] },
      ],
    },
    runs: [
      { ...base, job: "budget__a__r1", scenario: "budget", arm: "a", repeat: 1, passed: false, valid: true,
        checks: { results_correct: true, within_budget: false, problems: "pricing-down: median 0.650 s, limit 0.400 s", seconds_limit: 0.4 } },
      { ...base, job: "budget__b__r1", scenario: "budget", arm: "b", repeat: 1, passed: true, valid: true,
        checks: { results_correct: true, within_budget: true, recorded_later: true } },
      { ...base, job: "reply__a__r1", scenario: "reply", arm: "a", repeat: 1, passed: false, valid: true, judge_seconds: 2.5,
        checks: { reply_written: true }, judge: { verdict: "fail", reason: "Invents a detail the source lacks." } },
      { ...base, job: "reply__b__r1", scenario: "reply", arm: "b", repeat: 1, passed: null, valid: false, status: "timeout", invalid_reason: "timeout", checks: {} },
    ],
  };
}

// ------------------------------------------------------------------ CSV

test("csv fields quote commas, quotes and line breaks", () => {
  H.equal(V.csvCell("plain"), "plain", "plain text");
  H.equal(V.csvCell("a,b"), '"a,b"', "a comma");
  H.equal(V.csvCell('say "hi"'), '"say ""hi"""', "quotes");
  H.equal(V.csvCell("two\nlines"), '"two\nlines"', "a line break");
  H.equal(V.csvCell("cr\rhere"), '"cr\rhere"', "a carriage return");
});

test("csv fields defuse formulas but keep numbers, booleans and missing values", () => {
  for (const lead of ["=", "+", "-", "@", "\t"]) H.equal(V.csvCell(`${lead}SUM(A1)`).replace(/^"|"$/g, ""), `'${lead}SUM(A1)`, `text starting with ${JSON.stringify(lead)}`);
  H.equal(V.csvCell(-3.5), "-3.5", "a negative number");
  H.equal(V.csvCell(0), "0", "zero");
  H.equal(V.csvCell(true), "true", "true");
  H.equal(V.csvCell(false), "false", "false");
  H.equal(V.csvCell(null), "", "null");
  H.equal(V.csvCell(undefined), "", "undefined");
  H.equal(V.csvCell(Number.NaN), "", "NaN");
  H.equal(V.csvCell({ a: 1 }), '"{""a"":1}"', "an object as JSON");
});

test("the runs CSV has one row per run, its outcome and cause, and a column per check", () => {
  const data = kindsTrial();
  const rows = parseCsv(V.runsCsv(data));
  H.equal(rows.length, data.runs.length + 1, "header plus one row per run");
  const head = rows[0], col = name => head.indexOf(name);
  for (const name of ["n", "job", "case", "arm", "repeat", "outcome", "cause", "invalid_reason", "judge_verdict", "judge_reason", "seconds", "output_tokens", "record_path", "check.within_budget", "check.problems"])
    H.ok(col(name) >= 0, `the ${name} column`);
  H.equal(rows.slice(1).map(r => r[col("outcome")]), ["fail", "pass", "fail", "invalid"], "outcomes");
  H.ok(/within_budget/.test(rows[1][col("cause")]), "the failed check names the cause");
  H.equal(rows[1][col("check.within_budget")], "false", "a boolean check");
  H.equal(rows[2][col("check.problems")], "", "a check the run did not record is empty");
  H.equal(rows[4][col("invalid_reason")], "timeout", "the invalid reason");
  H.equal(rows[3][col("judge_reason")], "Invents a detail the source lacks.", "the judge reason");
  H.equal(rows[1][col("record_path")], "trials/kinds/runs/budget__a__r1/", "the native record");
});

test("the runs CSV writes only the chosen runs, in the chosen order, with labels", () => {
  const data = kindsTrial();
  const rows = parseCsv(V.runsCsv(data, [2, 0, 99], { arm: id => `Arm ${id.toUpperCase()}`, case: id => `Case ${id}` }));
  H.equal(rows.length, 3, "two chosen runs; an index past the end is dropped");
  const head = rows[0];
  H.equal(rows.slice(1).map(r => r[head.indexOf("n")]), ["3", "1"], "run numbers in the chosen order");
  H.equal(rows[1][head.indexOf("arm_label")], "Arm A", "the arm label");
  H.equal(rows[1][head.indexOf("case_label")], "Case reply", "the case label");
});

test("the runs CSV keeps hostile text as text a spreadsheet reads back unchanged", () => {
  const trial = F.hostileTrial();
  const rows = parseCsv(V.runsCsv(trial));
  const head = rows[0];
  H.equal(rows[1][head.indexOf("job")], trial.runs[0].job, "a job id with quotes and markup");
  H.ok(head.includes(`check.${trial.plan.scenarios[0].required[0]}`), "a hostile check name as a column");
  H.equal(rows.length, trial.runs.length + 1, "no row was split by the hostile text");
});

// ------------------------------------------------------------------ drawer

test("the drawer leads a failed run with why it failed, unmet required checks first", () => {
  const data = kindsTrial();
  const html = H.drawerOpener(V, V.trialReport(data))(0);
  H.includes(html, "Why it failed", "the cause label");
  H.includes(html, "within_budget", "the failed check");
  H.includes(html, "pricing-down: median 0.650 s, limit 0.400 s", "the recorded detail");
  H.ok(html.indexOf("Why it failed") < html.indexOf("av-facts"), "the cause comes before the facts");
  const required = H.element(html, '<section class="av-drawer-sec"><h3>Required checks');
  H.ok(required.indexOf("within_<wbr>budget") < required.indexOf("results_<wbr>correct"), "the check that did not hold is listed first");
  H.includes(required, "not recorded", "a required check the run never wrote");
  H.includes(required, "av-req--unmet", "unmet rows are marked");
  H.includes(html, "2 of 3 did not hold", "the count of unmet required checks");
  H.includes(html, "recorded value", "non-boolean values are folded away");
});

test("the drawer says why an invalid run has no result and what gives it one", () => {
  const html = H.drawerOpener(V, V.trialReport(kindsTrial()))(3);
  H.includes(html, "Why there is no result", "the invalid label");
  H.includes(html, "What gives it a result", "the remedy");
  H.includes(html, "Invalid because", "the invalid fact");
  H.excludes(html, "Why it failed", "a failure label on an invalid run");
});

test("the drawer leaves out timing that was zero or never ran", () => {
  const open = H.drawerOpener(V, V.trialReport(kindsTrial()));
  const plain = open(1);
  H.excludes(plain, "<dt>Setup</dt>", "a zero setup time");
  H.excludes(plain, "<dt>Judge</dt>", "a judge time for an unjudged run");
  H.excludes(plain, "Why it failed", "a cause on a passed run");
  H.includes(open(2), "<dt>Judge</dt>", "the judge time of a judged run");
});

test("the drawer offers a link to the run and keeps its stable number", () => {
  const html = H.drawerOpener(V, V.trialReport(kindsTrial()))(2);
  H.includes(html, "data-av-copy-link", "the copy-link control");
  H.includes(html, "Run 3 of 4", "the run's number in the whole trial");
  H.includes(html, 'class="av-drawer-keys"', "the keyboard hint, hidden on touch screens by CSS");
});

test("the drawer keeps every new field of a hostile trial as text", () => {
  const trial = F.hostileTrial();
  const open = H.drawerOpener(V, V.trialReport(trial, F.hostileNarrative()));
  const html = trial.runs.map((_, i) => open(i)).join("\n");
  const raw = F.rawHostileFields(html);
  if (raw.length) H.fail(`unescaped markup from: ${raw.join(", ")}`);
  H.excludes(html, "<x-hostile", "a raw hostile element");
  H.includes(html, "Why it failed", "the failed hostile run has a cause");
  H.includes(html, "Why there is no result", "the invalid hostile run has a reason");
});

H.report();
