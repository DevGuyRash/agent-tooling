// Why runs failed: failureCause() names the cause of every run that did not pass
// (required checks in the scenario's order, else the judge's reason, else a plain
// statement that none was recorded; an invalid run's reason in plain words), and
// the failures block groups failed runs by cause across cases and arms. Invalid
// runs are never failures there; every supplied value is escaped.
"use strict";
const H = require("./harness.cjs");
const F = require("./fixtures.cjs");
const { test } = H;

const V = H.loadVisuals();
const cause = (run, scenario) => H.plain(V.failureCause(run, scenario));

// ------------------------------------------------------------------ failureCause

const SCEN = { name: "c1", required: ["builds", "tests_pass", "within_budget"], judge: { question: "Is the reply honest?" } };
const UNJUDGED = { name: "c2", required: ["builds", "tests_pass"] };
const run = fields => ({ scenario: "c1", arm: "a", repeat: 1, status: "ok", passed: false, checks: {}, judge: null, ...fields });

test("a passing run has no cause", () => {
  H.equal(cause(run({ passed: true, checks: { builds: true, tests_pass: true, within_budget: true }, judge: { verdict: "pass" } }), SCEN), { kind: "none", text: "", failedChecks: [] }, "a pass");
});

test("failed required checks are named in the scenario's required order, not the checks' order", () => {
  const c = cause(run({ checks: { within_budget: false, tests_pass: true, builds: false }, judge: { verdict: "pass" } }), SCEN);
  H.equal(c.kind, "check", "kind");
  H.equal(c.failedChecks, ["builds", "within_budget"], "failed checks in required order");
  H.equal(c.text, "Required checks builds and within_budget were false.", "text");
});

test("a required check with no recorded value, or a value that is not true, is a cause as trial.py decides", () => {
  const c = cause(run({ checks: { builds: true, tests_pass: "yes" }, judge: { verdict: "pass" } }), SCEN);
  H.equal(c.failedChecks, ["tests_pass", "within_budget"], "a non-boolean and a missing required check");
  H.includes(c.text, "within_budget was not recorded", "the missing check in words");
  H.includes(c.text, "tests_pass was “yes”, not true", "the non-boolean value shown");
});

test("the judge's reason is the cause when every required check held", () => {
  const reason = "The reply claims the integration tests pass, but they never ran. It also promises a release date nobody agreed to, and it repeats that promise twice in the closing paragraph without any condition at all.";
  const c = cause(run({ checks: { builds: true, tests_pass: true, within_budget: true }, judge: { verdict: "fail", reason } }), SCEN);
  H.equal(c.kind, "judge", "kind");
  H.equal(c.failedChecks, [], "no failed checks");
  H.ok(c.text.startsWith("The judge said fail: The reply claims the integration tests pass, but they never ran."), `text starts with the verdict and the reason: ${c.text}`);
  H.ok(c.text.length <= 200, `text is at most 200 characters (${c.text.length})`);
  H.ok(/…$/.test(c.text), "a cut reason ends with an ellipsis");
});

test("a judge verdict other than fail, or none, is named as such", () => {
  H.includes(cause(run({ checks: { builds: true, tests_pass: true, within_budget: true }, judge: { verdict: "unclear", reason: "Hard to say." } }), SCEN).text, "The judge's verdict was “unclear”, not pass: Hard to say.", "another verdict");
  H.equal(cause(run({ checks: { builds: true, tests_pass: true, within_budget: true }, judge: { verdict: "fail" } }), SCEN).text, "The judge said fail and gave no reason.", "no reason");
});

test("failed checks come first, and a failing judge is still mentioned", () => {
  const c = cause(run({ checks: { builds: true, tests_pass: false, within_budget: true }, judge: { verdict: "fail", reason: "Wrong." } }), SCEN);
  H.equal(c.kind, "check", "kind");
  H.equal(c.text, "Required check tests_pass was false; the judge also said fail.", "text");
});

test("a judge that does not decide the case is not a cause", () => {
  const c = cause(run({ checks: { builds: true, tests_pass: true, within_budget: true }, judge: { verdict: "fail", reason: "Meh." } }), { ...SCEN, judge_required: false });
  H.equal(c.kind, "check", "kind");
  H.equal(c.text, "Failed, but no cause was recorded: every required check held.", "text");
});

test("a failure with no recorded cause says so plainly", () => {
  H.equal(cause(run({ scenario: "c2", checks: { builds: true, tests_pass: true } }), UNJUDGED).text, "Failed, but no cause was recorded: every required check held.", "required checks held");
  H.equal(cause(run({ scenario: "c3" }), { name: "c3", required: [] }).text, "Failed, but no cause was recorded: the case lists no required checks and no judge decides it.", "nothing required");
  H.equal(cause(run({ scenario: "gone", checks: { builds: false } })).text, "Failed, but this report does not list the case's required checks, so no cause can be named.", "no scenario: a false check is not guessed to be the cause");
});

test("a recorded detail is added: a problems check, or a value named like the failed check", () => {
  H.equal(cause(run({ scenario: "c2", checks: { builds: true, tests_pass: false, problems: "pricing-down: median 0.650 s, limit 0.400 s", import_error: "-" } }), UNJUDGED).text,
    "Required check tests_pass was false (problems: pricing-down: median 0.650 s, limit 0.400 s).", "a problems detail");
  const s = { name: "c4", required: ["all_follow_rule_edits"] };
  H.equal(cause(run({ scenario: "c4", checks: { all_follow_rule_edits: false, rule_edits_followed_by_receipt: "12/12", rule_edits_followed_by_all: "11/12", rule_edit_sites: "x" } }), s).text,
    "Required check all_follow_rule_edits was false (rule_edits_followed_by_all: 11/12).", "the closest-named value");
  H.equal(cause(run({ scenario: "c2", checks: { builds: true, tests_pass: false, problems: "ok", errors: "-" } }), UNJUDGED).text, "Required check tests_pass was false.", "values that say nothing are left out");
});

test("many failed checks stay within about 200 characters and count the rest", () => {
  const names = Array.from({ length: 12 }, (_, i) => `a_rather_long_required_check_name_${i}`);
  const c = cause(run({ scenario: "big", checks: {} }), { name: "big", required: names });
  H.equal(c.failedChecks.length, 12, "every failed check is listed in failedChecks");
  H.ok(c.text.length <= 205, `text length ${c.text.length}`);
  H.ok(/and \d+ more did not hold|\d+ more were/.test(c.text) || /more/.test(c.text), `the rest are counted: ${c.text}`);
});

test("every invalid reason trial.py writes reads in plain words and is never called a failure", () => {
  const cases = {
    "judge-missing": "plan names no judge", "judge-stale": "another judge", "judge-error": "gave no verdict", "check-error": "checks failed to run",
    timeout: "time limit", "exit-137": "code 137", "setup-failed": "setup did not finish", "no-thread-for-followup": "follow-up", skipped: "not attempted",
  };
  for (const [code, words] of Object.entries(cases)) {
    const c = cause({ scenario: "c1", arm: "a", passed: null, status: /^(timeout|exit-|setup|no-thread|skipped)/.test(code) ? code : "ok", invalid_reason: code }, SCEN);
    H.equal(c.kind, "invalid", `${code} kind`);
    H.includes(c.text, words, `${code} in plain words`);
    H.excludes(c.text.toLowerCase(), "failed run", `${code} called a failure`);
  }
  H.includes(cause({ scenario: "c1", arm: "a", passed: null, status: "ok", invalid_reason: "judge-error", judge: { verdict: "error", reason: "judge produced no verdict" } }, SCEN).text, "gave no verdict: judge produced no verdict.", "the judge error's own words");
  H.includes(cause({ scenario: "c1", arm: "a", passed: null, status: "ok", invalid_reason: "check-error", checks: { check_error: "loading check.py: SyntaxError: bad" } }, SCEN).text, "loading check.py: SyntaxError: bad", "the check error's own words");
  H.includes(cause({ scenario: "c1", arm: "a", passed: null, status: "weird-state" }, SCEN).text, "weird-state", "an unknown status shown verbatim");
  H.excludes(cause({ scenario: "c1", arm: "a", passed: null, status: "timeout", invalid_reason: "timeout" }, SCEN).text, "`", "code marks in plain text");
  H.equal(cause({ scenario: "c1", arm: "a", passed: null, status: "ok" }, SCEN).text, "No valid result, and no reason was recorded.", "no reason at all");
});

test("cause text is plain text for the caller to escape: markup in names is kept, not rendered", () => {
  const c = cause(run({ scenario: "h", checks: { "<b>x</b>": false } }), { name: "h", required: ["<b>x</b>"] });
  H.equal(c.failedChecks, ["<b>x</b>"], "the raw name");
  H.includes(c.text, "<b>x</b>", "raw text, escaped where it is drawn");
});

// ------------------------------------------------------------------ the failures block

// Arms "old" and "new" on cases "fix" (requires builds and tests_pass) and
// "reply" (judged, requires reply_written). Failures: fix/old r1 builds false;
// fix/old r2 builds and tests_pass false; fix/new r1 tests_pass false; reply/old
// r1 and r2 judged fail; reply/new r1 invalid (timeout), r2 judge-missing.
const trial = {
  name: "failures-fixture",
  plan: {
    arms: { old: { executor: "command" }, new: { executor: "command" } },
    scenarios: [{ name: "fix", required: ["builds", "tests_pass"] }, { name: "reply", required: ["reply_written"], judge: { question: "Honest?" } }, { name: "clean", required: ["ok"] }],
    judge: { executor: "command", model: "fictional" },
  },
  runs: [
    { job: "fix__old__r1", scenario: "fix", arm: "old", repeat: 1, status: "ok", passed: false, checks: { builds: false, tests_pass: true, problems: "compile error in main.rs" } },
    { job: "fix__old__r2", scenario: "fix", arm: "old", repeat: 2, status: "ok", passed: false, checks: { builds: false, tests_pass: false } },
    { job: "fix__old__r3", scenario: "fix", arm: "old", repeat: 3, status: "ok", passed: true, checks: { builds: true, tests_pass: true } },
    { job: "fix__new__r1", scenario: "fix", arm: "new", repeat: 1, status: "ok", passed: false, checks: { builds: true, tests_pass: false } },
    { job: "fix__new__r2", scenario: "fix", arm: "new", repeat: 2, status: "ok", passed: true, checks: { builds: true, tests_pass: true } },
    { job: "reply__old__r1", scenario: "reply", arm: "old", repeat: 1, status: "ok", passed: false, checks: { reply_written: true }, judge: { verdict: "fail", reason: "Claims tests ran that never ran." } },
    { job: "reply__old__r2", scenario: "reply", arm: "old", repeat: 2, status: "ok", passed: false, checks: { reply_written: true }, judge: { verdict: "fail", reason: "Promises a date." } },
    { job: "reply__new__r1", scenario: "reply", arm: "new", repeat: 1, status: "timeout", passed: null, invalid_reason: "timeout", checks: { reply_written: false } },
    { job: "reply__new__r2", scenario: "reply", arm: "new", repeat: 2, status: "ok", passed: null, invalid_reason: "judge-missing", checks: { reply_written: true } },
    { job: "reply__new__r3", scenario: "reply", arm: "new", repeat: 3, status: "ok", passed: true, checks: { reply_written: true }, judge: { verdict: "pass", reason: "Fine." } },
    { job: "clean__old__r1", scenario: "clean", arm: "old", repeat: 1, status: "ok", passed: true, checks: { ok: true } },
    { job: "clean__new__r1", scenario: "clean", arm: "new", repeat: 1, status: "ok", passed: true, checks: { ok: true } },
  ],
};
const ctxFor = (data, arms = [], labels = {}) => V.createContext({ trial: data, arms }, labels);
const render = (input = {}, data = trial, arms, labels) => V.renderBlock({ type: "failures", ...input }, ctxFor(data, arms, labels));
const html = render();
const mode = key => H.element(html, `av-fx-mode av-fx-mode--${key}`);
const modeFor = check => {
  const at = html.indexOf(`<code>${check.replace(/_/g, "_<wbr>")}</code> was`);
  if (at < 0) H.fail(`no group for ${check}`);
  return H.element(html.slice(html.lastIndexOf('<li class="av-fx-mode', at)), "av-fx-mode");
};

test("the block is registered, framed and drawn as one panel", () => {
  H.ok(V.blockTypes().includes("failures"), "failures is a block type");
  H.includes(html, '<section class="av-block av-block--failures" data-by="cause">', "the frame with its grouping");
  H.excludes(html, "av-block-error", "an error notice");
});

test("the opening line counts failed of valid runs and the invalid runs it leaves out", () => {
  H.includes(html, '<span class="av-fx-big">5</span><span>of 10 valid runs failed', "5 of 10 valid runs failed");
  H.includes(html, "in 2 of 3 cases, from 3 causes", "cases and causes");
  H.includes(html, "Not counted: 2 invalid runs", "the invalid runs, counted visibly");
  H.includes(html, ">judge-missing</code> 1", "judge-missing named");
  H.includes(html, ">timeout</code> 1", "timeout named");
  H.includes(html, "They are not failures", "invalid is not failure");
  H.includes(html, "listed under each cause", "the overlap explained, since fix/old r2 failed two checks");
});

test("invalid runs never enter a group or a mark", () => {
  H.excludes(html, "av-run--invalid", "an invalid mark");
  const runs = trial.runs;
  for (const i of [...html.matchAll(/data-run="(\d+)"/g)].map(m => Number(m[1]))) H.equal(runs[i].passed, false, `run ${i} drawn as a failure`);
});

test("causes are ranked by runs, each a required check or the judge, with counts against the runs that could fail that way", () => {
  const order = [...html.matchAll(/<li class="av-fx-mode av-fx-mode--(\w+)" id="[^"]+"><div class="av-fx-head"><span class="av-fx-count"><b>(\d+)<\/b>/g)].map(m => `${m[1]}:${m[2]}`);
  H.equal(order, ["check:2", "check:2", "judge:2"], "two checks with 2 runs, then the judge with 2");
  const builds = modeFor("builds");
  H.includes(builds, '<b>2</b><span> of 5</span>', "2 of the 5 valid fix runs");
  H.includes(builds, "valid runs in the case that requires it", "the denominator in words");
  H.includes(H.element(builds, 'class="av-fx-arm" data-arm="old"'), '<b>2</b> of 3', "old: 2 of 3");
  H.includes(H.element(builds, 'class="av-fx-arm av-fx-arm--zero" data-arm="new"'), '<b>0</b> of 2', "new: 0 of 2, kept for contrast and muted");
  H.includes(builds, 'Also failed in these runs:</span> <code>tests_<wbr>pass</code> <span class="av-muted">1 of 2</span>', "the overlapping cause, counted");
  H.includes(modeFor("tests_pass"), 'Also failed in these runs:</span> <code>builds</code> <span class="av-muted">1 of 2</span>', "and from the other side");
  H.equal(H.count(builds, 'class="av-run av-run--fail"'), 2, "two marks for builds");
  const judge = mode("judge");
  H.includes(judge, "The judge said fail", "the judge group title");
  H.includes(judge, "valid runs the judge decides", "judged denominator");
  H.includes(judge, '<b>2</b><span> of 3</span>', "2 of the 3 valid judged runs");
});

test("each case row quotes a representative reason, attributed, and folds the rest", () => {
  const judge = mode("judge");
  H.includes(judge, "Claims tests ran that never ran.", "the first judge reason");
  H.includes(judge, '<details class="av-fx-more"><summary>1 more judge reason</summary>', "the rest behind a disclosure");
  H.includes(judge, "Promises a date.", "the folded reason is present");
  H.includes(judge, 'class="av-fx-cite" data-run="5"', "the reason opens its run");
  H.includes(modeFor("builds"), "compile error in main.rs", "a recorded detail for a single failed check");
  H.excludes(modeFor("tests_pass"), "compile error", "a detail from a run that failed only another check");
});

test("marks name the run and its cause, and open the drawer by run index", () => {
  H.includes(html, 'data-run="0" title="fix · old · repeat 1: Failed. Required check builds was false (problems: compile error in main.rs)."', "the first failed run's mark");
  H.includes(html, 'data-run="6" title="reply · old · repeat 2: Failed. The judge said fail: Promises a date."', "a judged failure's mark");
});

test("with one arm in scope the per-arm counts are left out and invalid runs of that arm still counted", () => {
  const onlyNew = render({ arms: ["new"] });
  H.includes(onlyNew, '<span class="av-fx-big">1</span><span>of 4 valid runs failed', "1 of 4 valid runs of new");
  H.excludes(onlyNew, 'data-run="0"', "old's runs");
  H.excludes(onlyNew, "av-fx-arms", "per-arm counts with one arm");
  H.includes(onlyNew, "Not counted: 2 invalid runs", "new's invalid runs");
  const onlyFix = render({ cases: ["fix"] });
  H.excludes(onlyFix, "The judge said fail", "the judge group outside the chosen case");
  H.excludes(onlyFix, "Not counted", "invalid runs outside the chosen case");
});

test("grouped by case, each case lists its causes and the cases with no failure are named", () => {
  const byCase = render({ by: "case", reasons: 2 });
  H.includes(byCase, 'data-by="case"', "the grouping");
  H.includes(byCase, "3 of 5 valid runs failed, from 2 causes", "fix: 3 of 5, two causes");
  H.includes(byCase, "1 case had no failed run: clean.", "the clean case");
  H.includes(byCase, "Promises a date.", "both reasons quoted with reasons: 2");
  H.excludes(byCase, "more judge reason", "nothing folded with reasons: 2");
});

test("with three or more causes an index ranks them and links to each group", () => {
  const index = H.element(html, 'class="av-fx-index"');
  const links = [...index.matchAll(/href="#([^"]+)"/g)].map(m => m[1]);
  H.equal(links.length, 3, "one link per cause");
  for (const id of links) H.includes(html, `id="${id}"`, `the target ${id}`);
});

test("group titles sit under the section, or under the block's own title", () => {
  H.includes(html, '<h3 class="av-fx-title">', "h3 without a block title");
  const titled = render({ title: "Why" });
  H.includes(titled, '<h3 class="av-block-title">Why</h3>', "the block title");
  H.includes(titled, '<h4 class="av-fx-title">', "h4 under it");
});

test("cases follow the caller's order when given", () => {
  const byCase = render({ by: "case", cases: ["reply", "fix", "clean"] });
  H.ok(byCase.indexOf(">reply</h3>") < byCase.indexOf(">fix</h3>"), "reply before fix");
});

test("a long list of reasons is bounded, with the rest left to the runs", () => {
  const runs = Array.from({ length: 70 }, (_, i) => ({ scenario: "c", arm: "a", repeat: i + 1, passed: false, checks: {}, judge: { verdict: "fail", reason: `Reason number ${i + 1}.` } }));
  const out = render({}, { plan: { judge: { model: "j" }, scenarios: [{ name: "c", required: [], judge: "Good?" }] }, runs });
  H.includes(out, "69 more judge reasons", "the disclosure counts all of them");
  H.includes(out, "<p>Reason number 61.</p>", "the 60th folded reason quoted");
  H.excludes(out, "<p>Reason number 62.</p>", "a quote past the bound");
  H.includes(out, "9 more: select a run&#39;s mark above, or read the run ledger.", "the rest pointed to");
  H.equal(H.count(out, 'class="av-run av-run--fail"'), 70, "every run still has its mark");
});

test("a check required in several cases names the cases where no run failed it", () => {
  const data = { plan: { scenarios: [{ name: "c1", required: ["x"] }, { name: "c2", required: ["x"] }, { name: "c3", required: ["x"] }] }, runs: [
    { scenario: "c1", arm: "a", repeat: 1, passed: false, checks: { x: false } },
    { scenario: "c2", arm: "a", repeat: 1, passed: true, checks: { x: true } },
    { scenario: "c3", arm: "a", repeat: 1, passed: null, status: "timeout", invalid_reason: "timeout", checks: {} },
  ] };
  const out = render({}, data);
  H.includes(out, "valid runs in the 2 cases that require it", "only cases with a valid run count");
  H.includes(out, "No run failed it in c2.", "the case without a failure");
});

test("nothing is drawn when nothing failed, even with invalid runs", () => {
  const data = F.gridTrial({ a: { c1: "PP-" }, b: { c1: "P--" } });
  H.equal(render({}, data), "", "no panel");
  H.equal(render({ cases: ["clean"] }), "", "no failures in the chosen case");
});

test("a check that did not hold in different ways says so", () => {
  const data = { plan: { scenarios: [{ name: "c", required: ["x"] }] }, runs: [
    { scenario: "c", arm: "a", repeat: 1, passed: false, checks: { x: false } },
    { scenario: "c", arm: "a", repeat: 2, passed: false, checks: {} },
  ] };
  const out = render({}, data);
  H.includes(out, "<code>x</code> did not hold", "a mixed title");
  H.includes(out, "false in 1 run, not recorded in 1", "the breakdown");
});

test("failures with no recorded cause form their own group, listed last", () => {
  const data = { plan: { scenarios: [{ name: "c", required: ["x"] }] }, runs: [
    { scenario: "c", arm: "a", repeat: 1, passed: false, checks: { x: true } },
    { scenario: "c", arm: "a", repeat: 2, passed: false, checks: { x: false } },
    { scenario: "c", arm: "a", repeat: 3, passed: false, checks: { x: false } },
  ] };
  const out = render({}, data);
  H.includes(out, "Failed with no recorded cause", "the group");
  H.ok(out.indexOf("Failed with no recorded cause") > out.indexOf("<code>x</code> was false"), "after the named cause");
});

test("a judge failure without a reason says so", () => {
  const data = { plan: { judge: { model: "j" }, scenarios: [{ name: "c", required: [], judge: "Good?" }] }, runs: [{ scenario: "c", arm: "a", repeat: 1, passed: false, checks: {}, judge: { verdict: "fail" } }] };
  H.includes(render({}, data), "The judge gave no reason for this run.", "no reason");
});

test("every supplied value in the failures view is escaped", () => {
  const hostileRuns = F.hostileTrial();
  // A failure caused by the judge, with hostile reason, verdict, detail name and value.
  hostileRuns.runs.push({ job: F.hostile("fx-job"), scenario: F.CASE_1, arm: F.ARM_A, repeat: F.hostile("fx-repeat"), status: "ok", passed: false,
    checks: { [F.hostile("required-check")]: true, reply_written: true, [`${F.hostile("fx-detail-name")}_problems`]: F.hostile("fx-detail-value") },
    judge: { verdict: "fail", reason: F.hostile("fx-judge-reason") } });
  hostileRuns.runs.push({ job: "fx2", scenario: F.CASE_1, arm: F.ARM_B, repeat: 2, status: "ok", passed: false,
    checks: { [F.hostile("required-check")]: false, reply_written: true, problems: F.hostile("fx-problems") }, judge: { verdict: "pass" } });
  const arms = [{ id: F.ARM_A, label: F.hostile("fx-arm-label") }, { id: F.ARM_B }];
  const labels = { [F.CASE_1]: F.hostile("fx-case-label") };
  for (const by of ["cause", "case"]) {
    const out = render({ by, title: F.hostile("fx-title"), description: F.hostile("fx-description"), note: F.hostile("fx-note"), reasons: 5 }, hostileRuns, arms, labels);
    H.equal(F.rawHostileFields(out), [], `raw markup by ${by}`);
    for (const field of ["fx-title", "fx-description", "fx-note", "fx-judge-reason", "fx-case-label", "fx-arm-label", "fx-problems", "case-1", "arm-b", "invalid-reason"])
      H.includes(out, F.escapedHostile(field), `${field} visible as text (by ${by})`);
    H.includes(out, F.escapedHostile("required-check").replace(/_/g, "_<wbr>"), `the required check name visible (by ${by})`);
  }
  const everything = V.renderReport({ ...V.trialReport(hostileRuns, { arms, cases: labels }), sections: [{ title: "Why", blocks: [{ type: "failures" }] }] });
  H.equal(F.rawHostileFields(everything), [], "raw markup in a whole report");
});

test("a non-numeric repeat is shown as unknown, never as supplied markup", () => {
  const data = { plan: { scenarios: [{ name: "c", required: ["x"] }] }, runs: [{ scenario: "c", arm: "a", repeat: "<i>2</i>", passed: false, checks: { x: false } }] };
  const out = render({}, data);
  H.includes(out, "repeat ?", "unknown repeat");
  H.excludes(out, "<i>2</i>", "the raw value");
});

H.report();
