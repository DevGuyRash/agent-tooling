// The reader-first composition follows the trial's shape: one arm, case
// variants, all-invalid runs, a baseline or identical arms. The trial views it
// composes say why runs failed, group checks by case, quote the decision rule
// whole with the counts it names, and explain invalid reasons in plain words.
// Every new text field stays escaped.
"use strict";
const fs = require("node:fs");
const path = require("node:path");
const H = require("./harness.cjs");
const F = require("./fixtures.cjs");
const { test } = H;

const V = H.loadVisuals();
const example = JSON.parse(fs.readFileSync(path.join(H.VISUALS, "examples", "fictional-trial.json"), "utf8"));
const exampleNarrative = JSON.parse(fs.readFileSync(path.join(H.VISUALS, "examples", "fictional-narrative.json"), "utf8"));
const ids = spec => spec.sections.map(s => s.id);
const section = (spec, id) => spec.sections.find(s => s.id === id);
const render = (block, trial, extra = {}) => V.renderBlock(block, V.createContext({ trial, ...extra }, extra.cases || {}));
const FOLLOW = "Before you finish, review your work.";

/** A trial whose cases ran as written and again with one follow-up turn, like
 * X and X-review2: same prompt, judge and required checks. */
function variantTrial(grid, extra) {
  const data = F.gridTrial(grid, extra);
  const scenario = name => {
    const base = name.replace(/-v$/, "");
    return { name, prompt: `Prompt for ${base}.`, followups: name.endsWith("-v") ? [FOLLOW] : [], judge: { question: "Q?", pass_when: "the reply is plain" }, required: ["done"] };
  };
  data.plan.scenarios = data.plan.scenarios.map(s => scenario(s.name));
  return data;
}

// ------------------------------------------------------------------ order and shape

test("the default order reads verdict, setup, results, cases, failures, then the detail", () => {
  H.equal(H.plain(ids(V.trialReport(example, exampleNarrative))), ["verdict", "setup", "arms", "cases", "failures", "checks", "pairwise", "cost", "invalid", "runs"], "section ids");
  H.equal(H.plain(V.trialReport(example).sections.map(s => s.title)).slice(0, 5), ["Verdict", "What was compared", "Results by arm", "Case by case", "Why runs failed"], "section titles");
  H.equal(H.plain(V.SECTION_IDS), ["verdict", "setup", "arms", "cases", "grid", "failures", "checks", "pairwise", "cost", "invalid", "runs"], "every section id, the run grid included");
});

test("the run grid repeats the case dossiers, so it is drawn only when include names it", () => {
  H.ok(!ids(V.trialReport(example)).includes("grid"), "a run grid by default");
  H.equal(H.plain(ids(V.trialReport(example, { include: ["cases", "grid"] }))), ["cases", "grid"], "the grid when include names it");
  H.ok(!ids(V.trialReport(example, { exclude: ["grid"] })).includes("grid"), "exclude still accepts the id");
});

test("a narrative threshold reaches the difference from the baseline, and section explanations sit in leads", () => {
  const spec = V.trialReport(example, exampleNarrative);
  const contrast = section(spec, "arms").blocks.find(b => b.type === "contrast");
  H.equal(H.plain(contrast.threshold), exampleNarrative.threshold, "the threshold");
  const html = H.element(V.renderReport(spec), 'class="av-block av-block--contrast"');
  H.includes(html, "meets the +15-point bar, but the interval reaches down to", "the reading against the bar");
  H.equal(H.count(html, 'class="av-contrast-bar"'), 2, "the bar on the two comparisons, not on the chance-alone row");
  const runs = section(spec, "runs");
  H.includes(runs.lead, "Every run, filterable.", "the ledger's lead");
  H.equal(runs.blocks[0].description, "", "no second copy inside the panel");
  H.includes(section(spec, "cases").lead, "What each case asked, what counted as a pass, and how it went", "the cases lead");
});

test("the composed blocks carry the inputs the new views read", () => {
  const spec = V.trialReport(example, exampleNarrative);
  const setup = section(spec, "setup").blocks[0], cases = section(spec, "cases").blocks[0], failures = section(spec, "failures").blocks[0];
  H.equal(H.plain(setup), { type: "setup", arms: ["current", "current-copy", "checklist", "worked-example"], baseline: "current", identical: [["current", "current-copy"]], pairs: "off" }, "setup input");
  H.equal(H.plain([cases.type, cases.cases, cases.arms, cases.pairs]), ["cases", ["label-a-photo", "summarize-minutes", "reply-to-complaint", "explain-a-chart"], setup.arms, "off"], "cases input");
  H.equal(H.plain([failures.type, failures.cases, failures.arms]), ["failures", cases.cases, setup.arms], "failures input");
});

test("a single-arm trial skips the one-row arm ladder and puts its pass rate in the figures", () => {
  const spec = V.trialReport(F.gridTrial({ only: { c1: "PPF", c2: "PFF" } }));
  H.ok(!ids(spec).includes("arms"), `an arms section for one arm: ${ids(spec)}`);
  const figures = section(spec, "verdict").blocks[1].items;
  const rate = figures.find(i => i.label === "Pass rate");
  H.ok(rate && rate.value === "50%" && /3 of 6 valid/.test(rate.note), `pass rate figure ${JSON.stringify(rate)}`);
  H.ok(!figures.some(i => i.label === "Pass rate") === false, "the pass rate figure");
  H.ok(!V.trialReport(F.gridTrial({ a: { c: "PF" }, b: { c: "PP" } })).sections[0].blocks[1].items.some(i => i.label === "Pass rate"), "a pooled pass rate across arms");
});

test("a contrast appears only with a baseline or identical arms", () => {
  const two = F.gridTrial({ a: { c: "PPF" }, b: { c: "PFF" } });
  const types = spec => section(spec, "arms").blocks.map(b => b.type);
  H.equal(H.plain(types(V.trialReport(two))), ["ladder"], "no baseline, no identical arms");
  const withBase = V.trialReport(two, { baseline: "a" });
  H.equal(H.plain(types(withBase)), ["ladder", "contrast"], "with a baseline");
  H.equal(section(withBase, "arms").blocks[1].baseline, "a", "the contrast's baseline");
  H.equal(H.plain(types(V.trialReport(two, { identical: [["a", "b"]] }))), ["ladder", "contrast"], "with identical arms");
  H.equal(H.plain(types(V.trialReport(two, { baseline: "nope" }))), ["ladder"], "a baseline that is not an arm is not used");
});

test("failures and invalid sections appear only when there is something to explain", () => {
  H.ok(!ids(V.trialReport(F.gridTrial({ a: { c: "PP" }, b: { c: "PP" } }))).includes("failures"), "a failures section without failures");
  H.ok(ids(V.trialReport(F.gridTrial({ a: { c: "PF" }, b: { c: "PP" } }))).includes("failures"), "no failures section with a failure");
  H.ok(!ids(V.trialReport(F.gridTrial({ a: { c: "PP" }, b: { c: "PP" } }))).includes("invalid"), "an invalid section without invalid runs");
  H.ok(ids(V.trialReport(F.gridTrial({ a: { c: "P-" }, b: { c: "PP" } }))).includes("invalid"), "no invalid section with an invalid run");
});

test("when no run is valid, the report says so first and drops the views that would draw nothing", () => {
  const data = F.gridTrial({ a: { c1: "--" }, b: { c1: "-" } }, run => ({ invalid_reason: "judge-missing", seconds: 0.1, usage: {} }));
  const spec = V.trialReport(data);
  H.equal(H.plain(ids(spec)), ["verdict", "setup", "cases", "invalid", "runs"], "section ids");
  const verdict = section(spec, "verdict").blocks[0];
  H.includes(verdict.headline, "No run produced a valid result", "the headline");
  H.includes(verdict.alert.text, "`judge-missing` ×3", "the breakdown by reason");
  H.equal(verdict.alert.href, "#invalid", "the link to the invalid runs");
  const html = V.renderReport(spec);
  H.includes(html, '<a href="#invalid">', "the rendered link");
  H.ok(!V.trialReport(data, { exclude: ["invalid"] }).sections[0].blocks[0].alert.href, "a link to an excluded section");
});

test("a large share of invalid runs is flagged under the verdict", () => {
  const spec = V.trialReport(F.gridTrial({ a: { c: "PF--" }, b: { c: "PPPP" } }));
  H.includes(section(spec, "verdict").blocks[0].alert.text, "2 of 8 runs produced no valid result", "the alert");
  H.ok(!section(V.trialReport(F.gridTrial({ a: { c: "PFPF" }, b: { c: "PPP-" } })), "verdict").blocks[0].alert, "an alert for one invalid run in eight");
});

test("the masthead says what ran, with a repeat range, a judge and a shortened home path", () => {
  const data = F.gridTrial({ a: { c1: "PP", c2: "PPP" }, b: { c1: "PP", c2: "PP" } });
  data.plan.judge = { executor: "codex", model: "judge-model", effort: "high" };
  data.run_directory = "/home/someone/.cache/agent-trials/x";
  const spec = V.trialReport(data);
  H.equal(spec.summary, "2 arms (a, b) on 2 cases, 2–3 repeats each: 9 runs, judged by judge-model at high effort (codex).", "summary");
  H.equal(H.plain(spec.meta), [{ label: "Run directory", value: "~/.cache/agent-trials/x" }], "meta");
  H.equal(section(spec, "verdict").blocks[1].items.find(i => i.label === "Repeats").value, "×2–3", "repeats figure");
  H.equal(V.trialReport({ ...data, run_directory: "/Users/someone" }).meta[0].value, "~", "a bare home directory");
  H.equal(V.trialReport({ ...data, run_directory: "/srv/trials/x" }).meta[0].value, "/srv/trials/x", "a path outside a home directory");
  H.equal(V.trialReport(data, { summary: "Narrative." }).summary, "Narrative.", "the narrative's summary wins");
});

test("run dates and the data's date reach the masthead and footer when the report records them", () => {
  const data = { ...F.gridTrial({ a: { c: "P" } }), ran: { first: "2026-10-04T09:00:00Z", last: "2026-10-05T18:00:00Z" }, generated_at: "2026-10-05T19:00:00Z" };
  const spec = V.trialReport(data);
  H.equal(H.plain(spec.meta.find(m => m.label === "Ran")), { label: "Ran", value: "4–5 Oct 2026" }, "ran, labelled apart from the footer's date the data were written");
  H.ok(!spec.meta.some(m => /written/i.test(m.label)), "no second 'written' date in the masthead");
  H.includes(spec.footer, "Report data written 5 Oct 2026.", "footer");
  H.equal(V.trialReport({ ...data, ran: { first: "not a date" } }).meta.find(m => m.label === "Ran").value, "not a date", "an unreadable date shown as written");
});

test("narrative problems reach the report's problem panel", () => {
  const spec = V.trialReport(example, { exclude: ["arsm"] });
  H.ok(Array.isArray(spec.problems) && spec.problems.some(p => /arsm/.test(p.message)), `problems: ${JSON.stringify(spec.problems)}`);
  H.includes(V.renderReport(spec), "arsm", "the problem in the rendered report");
  const own = V.renderReport({ title: "T", sections: [], problems: [{ level: "error", where: "x.y", message: "a supplied problem" }] });
  H.includes(own, "a supplied problem", "a problem supplied with the specification");
});

test("a misspelled narrative arm does not shift the identity order", () => {
  const spec = V.trialReport(example, { arms: [{ id: "curent", label: "Typo" }, { id: "checklist", label: "Checklist" }] });
  H.equal(H.plain(spec.arms.map(a => a.id)), ["checklist", "current", "current-copy", "worked-example"], "identity order");
});

test("a malformed narrative section renders as a notice while the rest of the report renders", () => {
  const html = V.renderReport(V.trialReport(example, { sections: [null, { title: "No blocks" }] }));
  H.includes(html, "This section entry is not an object.", "the notice for a non-object");
  H.includes(html, "This section has no blocks list.", "the notice for a missing blocks list");
  H.includes(html, 'data-verdict="none"', "the verdict still renders");
});

// ------------------------------------------------------------------ case variants

test("case variants are found by content, ordered under their base and passed to every view", () => {
  const data = variantTrial({ a: { x: "PP", "x-v": "PF", y: "PP" }, b: { x: "PF", "x-v": "FF", y: "PP" } }, run => ({ checks: { done: run.passed === true } }));
  const spec = V.trialReport(data);
  const pairs = H.plain(section(spec, "cases").blocks[0].pairs);
  H.equal(pairs.map(p => [p.base, p.variant, p.label]), [["x", "x-v", "+ 1 follow-up turn"]], "pairs");
  H.equal(pairs[0].note, FOLLOW, "the added turn");
  H.equal(H.plain(section(spec, "cases").blocks[0].cases), ["x", "x-v", "y"], "case order");
  H.equal(H.plain(section(V.trialReport(data, { include: ["grid"] }), "grid").blocks[0].pairs).length, 1, "pairs for the run grid");
  H.equal(H.plain(section(spec, "setup").blocks[0].pairs), [["x", "x-v"]], "pairs for the setup view");
  H.equal(H.plain(section(spec, "checks").blocks[0].pairs).length, 1, "pairs for the checks");
  H.includes(spec.summary, "2 arms (a, b) on 2 cases, one of them also run with 1 follow-up turn added (3 case versions)", "the summary counts base cases and names the versions");
  H.equal(H.plain(section(spec, "verdict").blocks[1].items.find(i => i.label === "Cases")), { value: 2, label: "Cases", note: "+1 variant: 3 versions" }, "the cases figure");
  const arms = section(spec, "arms").blocks;
  H.equal(H.plain(arms.map(b => [b.type, b.title || ""])), [["ladder", "All cases"], ["ladder", "Base cases"], ["ladder", "Variants (+ 1 follow-up turn)"], ["contrast", "Variants against their base cases"]], "arms blocks");
  const contrast = H.plain(arms[3]);
  H.equal([contrast.a.cases, contrast.b.cases, contrast.by], [["x-v"], ["x"], "arm"], "variant contrast sides");
});

test("a variant needs the same prompt, judge and checks, and more turns", () => {
  const data = variantTrial({ a: { x: "P", "x-v": "P" } });
  data.plan.scenarios[1].required = ["done", "other"];
  H.equal(H.plain(section(V.trialReport(data), "cases").blocks[0].pairs), "off", "a differing required list");
  const same = variantTrial({ a: { x: "P", "x-v": "P" } });
  same.plan.scenarios[1].followups = [];
  H.equal(H.plain(section(V.trialReport(same), "cases").blocks[0].pairs), "off", "no added turn");
});

test("narrative pairs override detection, and an empty list turns it off", () => {
  const data = variantTrial({ a: { x: "P", "x-v": "F", y: "P" } });
  H.equal(H.plain(section(V.trialReport(data, { pairs: [] }), "cases").blocks[0].pairs), "off", "pairs: []");
  const named = H.plain(section(V.trialReport(data, { pairs: [{ base: "y", variant: "x", label: "Swapped" }, ["x", "nope"]] }), "cases").blocks[0].pairs);
  H.equal(named, [{ base: "y", variant: "x", label: "Swapped" }], "explicit pairs, unknown cases left out");
  H.equal(H.plain(section(V.trialReport(data, { pairs: [["x", "x-v"]] }), "cases").blocks[0].pairs)[0].label, "+ 1 follow-up turn", "a detected label for an explicit pair");
});

test("with one arm, variants get their own difference section", () => {
  const data = variantTrial({ a: { x: "PPPP", "x-v": "PFFF" } });
  const spec = V.trialReport(data);
  const arms = section(spec, "arms");
  H.equal([arms.title, arms.blocks.length, arms.blocks[0].type, arms.blocks[0].title], ["Variants against base cases", 1, "contrast", undefined], "variant section");
});

test("the run grid puts each variant directly under its base, labelled by its difference", () => {
  const data = variantTrial({ a: { x: "PP", y: "PP", "x-v": "PF" } });
  const html = render({ type: "tapestry", pairs: [{ base: "x", variant: "x-v", label: "+ 1 follow-up turn", note: FOLLOW }] }, data);
  const order = [...html.matchAll(/<div class="av-tap-row( av-tap-row--(?:base|variant))?" role="row"><div class="av-tap-rowhead"[^>]*>(?:<span class="av-tap-variant"[^>]*>[^<]*<\/span>)?<span class="av-case-name"[^>]*>([^<]+)</g)].map(m => [m[2], (m[1] || "").trim()]);
  H.equal(order, [["x", "av-tap-row--base"], ["x-v", "av-tap-row--variant"], ["y", ""]], "row order");
  H.includes(html, `<span class="av-tap-variant" title="${FOLLOW}">↳ + 1 follow-up turn</span>`, "the variant label");
});

// ------------------------------------------------------------------ verdict

test("the no-decision verdict lists the counts of the cases and arms its rule names, longest names first", () => {
  const data = variantTrial({ a: { x: "PP", "x-v": "PF" }, b: { x: "PF", "x-v": "FF" } });
  data.plan.decision_rule = "Adopt if x-v passes at least as often as `x`, and `b` is not worse than `a`.";
  const spec = V.trialReport(data);
  const verdict = section(spec, "verdict").blocks[0];
  H.equal(H.plain(verdict.mentions), ["x-v", "x", "b", "a"], "mentions in order of first mention");
  const html = V.renderReport(spec);
  const strip = H.element(html, 'class="av-mentions"');
  H.includes(strip, '<li class="av-mention" data-case="x-v">', "the variant's own chip");
  H.includes(strip, '<span class="av-mention-all">all <span class="av-frac"><b>1</b>/4</span></span>', "pooled counts for x-v");
  H.includes(strip, "Counts only", "the note that nothing is judged");
  H.excludes(strip, "av-mention-variant", "a variant line under x when x-v has its own chip");
  H.excludes(strip, "met", "a met or unmet state");
});

test("a named case shows its variant's counts beside its own", () => {
  const data = variantTrial({ a: { x: "PPP", "x-v": "PFF" } });
  data.plan.decision_rule = "Ship if `x` holds with the turn.";
  const strip = H.element(V.renderReport(V.trialReport(data)), 'class="av-mentions"');
  H.includes(strip, "↳ + 1 follow-up turn", "the variant line");
  H.includes(strip, '<span class="av-frac"><b>1</b>/3</span>', "the variant's counts");
  H.excludes(strip, "av-mention-arm", "per-arm counts in a one-arm trial");
});

test("a rule names no case inside a longer word, and a plain-word name only in backticks", () => {
  const data = F.gridTrial({ good: { "c-1": "P", "c-2": "P", summary: "P" }, bad: { "c-1": "F" } });
  data.plan.decision_rule = "Ac-1 and c-2x and xc-1 are not cases; c-1, though, is. A good summary of `summary` matters.";
  H.equal(H.plain(section(V.trialReport(data), "verdict").blocks[0].mentions), ["c-1", "summary"], "mentions");
});

test("a verdict word is read without regard to case", () => {
  H.includes(V.renderBlock({ type: "verdict", verdict: "Adopt", headline: "h" }, V.createContext({})), 'data-verdict="adopt"', "the adopt stamp");
});

test("a long rule is set upright and never clipped", () => {
  const rule = "A".repeat(10) + " word".repeat(120);
  const html = V.renderBlock({ type: "verdict", verdict: "none", headline: "h", rule }, V.createContext({}));
  H.includes(html, "av-rule-text av-rule-text--long", "the long-rule class");
  H.includes(html, " word".repeat(120).trim(), "the whole rule");
  const css = fs.readFileSync(path.join(H.VISUALS, "styles", "agentic-visuals.css"), "utf8");
  H.includes(css, ".av-rule-text { max-height: none; overflow: visible; }", "the unclipped rule style");
});

// ------------------------------------------------------------------ ladder

test("the ladder by case draws one row per case in the arm's color, variants under their base", () => {
  const data = variantTrial({ only: { x: "PPF", y: "P", "x-v": "FFF" } });
  const html = render({ type: "ladder", by: "case", pairs: [{ base: "x", variant: "x-v", label: "+ 1 follow-up turn" }] }, data);
  H.equal([...html.matchAll(/class="av-ladder-row[^"]*" role="row" data-case="([^"]+)"/g)].map(m => m[1]), ["x", "x-v", "y"], "row order");
  H.includes(html, 'class="av-ladder-row av-ladder-row--variant" role="row" data-case="x-v"', "the variant row");
  H.includes(html, "--c:var(--av-arm-0)", "the arm's color");
  H.includes(html, "2 of 3 valid runs passed, 67%", "the case's rate");
  H.includes(html, 'data-by="case"', "the case mode marker");
});

test("a ladder row with more passes than valid runs says its counts are invalid instead of clamping", () => {
  const html = V.renderBlock({ type: "ladder", rows: [{ arm: "a", k: 12, n: 5 }] }, V.createContext({}));
  H.includes(html, "counts invalid: 12 of 5", "the invalid counts");
  H.excludes(html, '<span class="av-rate">100%</span>', "a clamped rate");
  H.excludes(html, "av-pt", "a point for impossible counts");
});

test("the identical-arms spread is drawn inside each member's own track", () => {
  const html = render({ type: "ladder", identical: [["current", "current-copy"]] }, example);
  H.equal(H.count(html, 'class="av-noise-seg"'), 2, "one spread mark per identical arm");
  H.excludes(html, 'class="av-noise"', "the old overlay");
  const noted = V.renderBlock({ type: "ladder", identical: [["current", "current-copy"]] }, V.createContext({ trial: example, arms: exampleNarrative.arms }));
  H.includes(noted, '<span class="av-ladder-note">identical text, run separately</span>', "the narrative's arm note on its own line");
});

// ------------------------------------------------------------------ failures in the marks and the ledger

test("ledger reasons and mark labels name the required checks that failed", () => {
  const data = F.gridTrial({ a: { c: "PF" } }, run => ({ checks: { within_budget: run.passed === true, words: 3 }, seconds: run.passed ? 30 : 95 }));
  data.plan.scenarios[0].required = ["within_budget"];
  const spec = V.trialReport(data);
  const html = V.renderReport(spec);
  const ledger = H.element(html, 'class="av-block av-block--ledger"');
  H.includes(ledger, '<span class="av-why-chip">✕ within_budget</span>', "the failed check in the ledger");
  H.includes(ledger, "Time (m:ss)", "one time format for the column");
  H.includes(ledger, ">0:30</td>", "thirty seconds as m:ss");
  H.includes(ledger, ">1:35</td>", "95 seconds as m:ss");
  H.includes(ledger, 'placeholder="Search reasons and causes"', "the search placeholder");
  H.includes(H.element(V.renderReport(V.trialReport(data, { include: ["grid"] })), 'class="av-block av-block--tapestry"'), "repeat 2: Failed · within_budget", "the mark label");
});

test("a judge failure reads as the judge's reason in the ledger", () => {
  const data = F.gridTrial({ a: { c: "F" } }, () => ({ checks: { done: true }, judge: { verdict: "fail", reason: "Invents a detail." } }));
  data.plan.scenarios[0].required = ["done"];
  data.plan.scenarios[0].judge = { question: "Q?" };
  const ledger = H.element(V.renderReport(V.trialReport(data)), 'class="av-block av-block--ledger"');
  H.includes(ledger, "judge: Invents a detail.", "the judge's reason");
  H.excludes(ledger, "av-why-chip", "a check chip for a judge failure");
});

test("invalid reasons are explained in plain words with the remedy for that reason", () => {
  const data = F.gridTrial({ a: { c: "P---" } }, run => ({ invalid_reason: run.passed === null ? ["judge-missing", "timeout", "exit-3"][run.repeat - 2] : null }));
  const html = render({ type: "invalid" }, data);
  H.includes(html, "the plan names no judge", "the judge-missing gloss");
  H.includes(html, "Rerunning gives the same result.", "no rerun remedy for a missing judge");
  H.includes(html, "<code>trial.py recheck RUN_DIR --judge &#39;&lt;judge JSON&gt;&#39;</code>", "the judge remedy");
  H.includes(html, "ran past the case&#39;s time limit", "the timeout gloss");
  H.includes(html, "<code>trial.py run PLAN --out RUN_DIR --retry-invalid</code>", "the retry remedy");
  H.includes(html, "exited with code 3", "the exit gloss");
  H.excludes(html, "rerunning them (trial.py run --retry-invalid) is the remedy", "the old blanket remedy");
  const ledger = render({ type: "ledger" }, data);
  H.includes(ledger, '<code class="av-why-code">judge-missing</code>', "the reason code in the ledger");
});

test("cost shows no empty panel when only invalid runs recorded usage", () => {
  const data = F.gridTrial({ a: { c: "--" } }, () => ({ seconds: 0.1, usage: {} }));
  H.ok(!ids(V.trialReport(data)).includes("cost"), "a cost section without a valid run");
  H.includes(render({ type: "cost" }, data), "No valid run recorded usage or timing; 2 invalid runs are not placed.", "the empty notice");
});

// ------------------------------------------------------------------ checks

/** Two cases with their own required checks, like hook-v4: most hold everywhere, one does not. */
function checksTrial() {
  const data = F.gridTrial({ a: { s1: "PPF", s2: "PP" }, b: { s1: "PPP", s2: "PF" } }, run => ({
    checks: run.scenario === "s1"
      ? { s1_a: true, s1_b: true, s1_c: run.passed !== false, s1_d: true, ratio: run.repeat * 0.5, first: run.repeat === 1, note: "text" }
      : { s2_a: true, s2_b: run.passed !== false, flag: false },
  }));
  data.plan.scenarios.find(s => s.name === "s1").required = ["s1_a", "s1_b", "s1_c", "s1_d"];
  data.plan.scenarios.find(s => s.name === "s2").required = ["s2_a", "s2_b"];
  return data;
}

test("checks group by case when cases require different checks, failing checks first and the rest folded", () => {
  const html = render({ type: "checks" }, checksTrial());
  H.includes(html, 'data-by="case"', "case mode");
  const s1 = H.element(html, 'class="av-ck-case" data-case="s1"');
  H.includes(s1, '<tr class="av-ck-failing"><th scope="row"><code>s1_<wbr>c</code></th>', "the failing check");
  H.includes(s1, "3 more required checks held in every valid run", "the folded checks");
  H.includes(s1, "2 recorded measures", "the measures disclosure");
  H.includes(s1, '<span class="av-num-median">1</span><span class="av-muted">0.5–1.5</span>', "a numeric measure's median and range");
  H.excludes(s1, "<code>note</code>", "a text value among the measures");
  H.ok(html.indexOf('data-case="s1"') < html.indexOf('data-case="s2"'), "plan order");
});

test("a case whose valid runs all passed collapses to one line", () => {
  const data = checksTrial();
  data.runs.filter(r => r.scenario === "s2").forEach(r => { r.passed = true; r.checks.s2_b = true; });
  const html = render({ type: "checks" }, data);
  const s2 = H.element(html, 'data-case="s2"');
  H.includes(s2, "av-ck-case--clean", "the collapsed case");
  H.includes(s2, "All 2 required checks held in every valid run.", "the one line");
  H.excludes(s2, "<table class=\"av-heatmap av-heatmap--case\"", "a table for a clean case");
});

test("checks stay pooled by check when every case requires the same checks, with steady rows folded", () => {
  const data = F.gridTrial({ a: { c1: "PP", c2: "PF" }, b: { c1: "PP", c2: "PP" } }, run => ({ checks: { k1: true, k2: true, k3: true, k4: true, k5: run.passed === true, m1: true, m2: false, m3: false, m4: true, m5: run.repeat === 1 } }));
  data.plan.scenarios.forEach(s => { s.required = ["k1", "k2", "k3", "k4", "k5"]; });
  const html = render({ type: "checks" }, data);
  H.includes(html, 'data-by="check"', "check mode");
  H.includes(html, "4 more required checks held in every valid run, in every arm", "the folded required checks");
  H.includes(html, "<tr><th scope=\"row\"><code>k5</code>", "the differing required check stays");
  H.includes(html, "4 measures never changed: 2 always true, 2 never true", "the folded measures");
  H.includes(html, "<tr><th scope=\"row\"><code>m5</code>", "the varying measure stays");
  H.includes(render({ type: "checks", by: "case" }, data), 'data-by="case"', "case mode on request");
});

// ------------------------------------------------------------------ pairwise

test("pairwise bars and legend use the two arms' own colors and names", () => {
  const html = render({ type: "pairwise" }, example, { arms: exampleNarrative.arms });
  const key = Object.keys(example.pairwise)[0], [a, b] = example.pairwise[key].arms;
  const index = id => exampleNarrative.arms.findIndex(x => x.id === id);
  H.includes(html, `style="--c-a:var(--av-arm-${index(a)});--c-b:var(--av-arm-${index(b)})"`, "the arm colors");
  const label = id => exampleNarrative.arms.find(x => x.id === id).label;
  H.includes(html, `${label(a)} preferred in both orders`, "the first arm by name");
  H.excludes(html, "first arm preferred", "the generic legend");
});

// ------------------------------------------------------------------ escaping

test("every new text field renders as escaped text", () => {
  const h = F.hostile, data = variantTrial({ [h("v-arm")]: { [h("v-case")]: "PF", [`${h("v-case")}-v`]: "F-" } });
  const base = h("v-case"), variant = `${base}-v`;
  data.plan.scenarios.forEach(s => { s.description = h("v-description"); s.judge.pass_when = h("v-pass-when"); s.followups = s.name === variant ? [h("v-followup")] : []; });
  data.runs.forEach(r => { r.checks = { done: r.passed === true, [h("v-measure")]: 2 }; r.invalid_reason = r.passed === null ? h("v-invalid") : null; r.judge = r.passed === false ? { verdict: "fail", reason: h("v-judge-reason") } : null; });
  data.plan.decision_rule = `Ship if ${base} and ${variant} hold for ${h("v-arm")}.`;
  data.run_directory = `/home/${h("v-home")}/runs`;
  data.ran = { first: h("v-ran") };
  const narrative = { pairs: [{ base, variant, label: h("v-pair-label") }], arms: [{ id: h("v-arm"), label: h("v-arm-label"), note: h("v-arm-note") }], cases: { [base]: h("v-case-label") } };
  const spec = V.trialReport(data, narrative);
  const html = [
    V.renderReport(spec),
    render({ type: "ladder", by: "case", pairs: narrative.pairs }, data),
    render({ type: "checks", by: "case", pairs: narrative.pairs }, data),
    render({ type: "checks", required: false, pairs: narrative.pairs }, data),
    V.renderReport(V.trialReport(example, { baseline: "current", threshold: { value: 0.1, label: h("v-threshold") } })),
    render({ type: "plan" }, data),
    V.renderBlock({ type: "verdict", verdict: "none", headline: h("v-headline"), alert: { text: h("v-alert"), href: h("v-href"), link: h("v-link") } }, V.createContext({ trial: data })),
  ].join("\n");
  const raw = F.rawHostileFields(html);
  if (raw.length) H.fail(`unescaped markup from: ${raw.join(", ")}`);
  for (const field of ["v-case", "v-arm-label", "v-arm-note", "v-pair-label", "v-followup", "v-pass-when", "v-measure", "v-invalid", "v-judge-reason", "v-ran", "v-headline", "v-alert", "v-description", "v-threshold"])
    H.includes(html, F.escapedHostile(field), `the escaped ${field}`);
  H.includes(html, "<code>~/runs</code>", "the plan's run directory with its home directory shortened");
  H.excludes(html, F.escapedHostile("v-href"), "an unsafe alert link as an anchor");
});

// ------------------------------------------------------------------ reviewer fixes (reader and design critique)

test("durations of a minute or more read as minutes and seconds, on an axis of whole minutes that ends past the slowest run", () => {
  const secs = { "c__a__r1": 61, "c__a__r2": 86, "c__a__r3": 250, "c__b__r1": 70, "c__b__r2": 90, "c__b__r3": 200 };
  const data = F.gridTrial({ a: { c: "PPF" }, b: { c: "PFP" } }, run => ({ seconds: secs[run.job] }));
  const cost = render({ type: "cost" }, data);
  H.includes(cost, '<span class="av-strong">1 min 26 s</span>', "a median as minutes and seconds");
  H.excludes(cost, "1.43 min", "a decimal minute");
  const ticks = [...H.element(cost, 'class="av-strip-ticks"').matchAll(/>([^<]+)<\/span>/g)].map(m => m[1]);
  H.equal(ticks, ["0 min", "1 min", "2 min", "3 min", "4 min", "5 min"], "ticks round in the unit shown, the last at or past the slowest run");
  H.includes(cost, 'class="av-tick--end" style="--x:100.000%">5 min', "only the edge label is pulled inside its tick");
  H.excludes(cost, "av-mark--pass", "the green pass mark in a key for arm-colored dots");
  H.includes(cost, "color: the run's arm", "the key says color is the arm");
});

test("input tokens count the cache reads and writes an executor reports apart, and say so", () => {
  const data = F.gridTrial({ a: { c: "PP" } }, run => ({ usage: { input_tokens: 20, cache_read_input_tokens: 80000, cache_creation_input_tokens: 15000, output_tokens: 900 } }));
  const cost = render({ type: "cost" }, data);
  H.includes(cost, "95k", "uncached, read and written input together");
  H.includes(cost, "including cache reads and writes", "the note on what is counted");
  const codex = render({ type: "cost" }, F.gridTrial({ a: { c: "PP" } }, () => ({ usage: { input_tokens: 150000, cached_input_tokens: 120000, output_tokens: 900 } })));
  H.includes(codex, "150k", "cached input already inside input_tokens is not added twice");
  H.excludes(codex, "including cache", "a note where nothing was added");
});

test("pairwise bars share one scale, the overall row included, and a split label never shrinks its bar", () => {
  const st = (a, b, tie, inc) => ({ a_wins: a, b_wins: b, tie, inconsistent: inc, invalid: 0, a_win_rate: a / Math.max(1, a + b), a_win_rate_interval: [0.1, 0.9] });
  const data = F.gridTrial({ x: { c1: "P", c2: "P" }, y: { c1: "F", c2: "F" } });
  data.pairwise = { "x__y": { arms: ["x", "y"], overall: st(8, 2, 1, 1), scenarios: { c1: st(5, 0, 0, 1), c2: st(3, 2, 1, 0) } } };
  const html = render({ type: "pairwise" }, data);
  const widths = [...html.matchAll(/class="av-duel-bar" style="width:([\d.]+)%/g)].map(m => Number(m[1]));
  H.equal(widths, [100, 50, 50], "12 pairs fill the track; 6 pairs fill half of it, split or not");
  H.includes(html, "one scale for every row", "the legend says so");
});

test("cases at a glance stack only marks that would touch, a full glyph apart", () => {
  const data = F.gridTrial({ a: { c: "PPPF" }, b: { c: "PPPF" }, d: { c: "PFFF" } });
  const html = render({ type: "cases", index: true }, data);
  const dots = [...H.element(html, 'class="av-cs-ix"').matchAll(/class="av-cs-dot" style="--x:([\d.]+)%;--j:(-?[\d.]+);--gap:(\d+)px"/g)].map(m => [Number(m[1]), Number(m[2]), Number(m[3])]);
  H.equal(dots, [[75, -0.5, 14], [75, 0.5, 14], [25, 0, 14]], "the two arms at 75% stacked 14 px apart; the lone arm on the line");
  H.includes(html, 'style="height:40px"', "the row grows to hold the stack");
});

test("a dossier groups runs that failed the same way and lists what varied, most frequent first, with each arm's count", () => {
  const vals = { "c__a__r1": "11/12", "c__a__r2": "0/12", "c__b__r1": "11/12", "c__b__r2": "11/12" };
  const data = F.gridTrial({ a: { c: "FFP" }, b: { c: "FFP" } }, run => ({ checks: { all_follow_edits: run.passed === true, edits_followed_by_all: vals[run.job] ?? "12/12" } }));
  data.plan.scenarios[0].required = ["all_follow_edits"];
  const reasons = H.element(render({ type: "cases" }, data), 'class="av-cs-reasons"');
  H.includes(reasons, 'class="av-cs-reason--group"', "one group for the one failed check");
  H.includes(reasons, '<span class="av-cs-count">4×</span>', "all four failed runs in the one group");
  H.ok(reasons.indexOf("11/12") < reasons.indexOf("0/12"), "the common value before the rare one");
  H.ok(/av-cs-reason-arm"[^>]*>.*?<b>2<\/b>.*?av-cs-reason-arm"[^>]*>.*?<b>2<\/b>/.test(reasons), "each arm's glyph with its count");
});

test("the failures view quotes the most frequent recorded value first", () => {
  const vals = { "c__a__r1": "0/12", "c__a__r2": "11/12", "c__a__r3": "11/12" };
  const data = F.gridTrial({ a: { c: "FFFP" } }, run => ({ checks: { all_follow_edits: run.passed === true, edits_followed_by_all: vals[run.job] ?? "12/12" } }));
  data.plan.scenarios[0].required = ["all_follow_edits"];
  const html = render({ type: "failures" }, data), quotes = html.slice(html.indexOf("av-fx-quote"));
  H.ok(quotes.indexOf("11/12") < quotes.indexOf("0/12"), "11/12 (two runs) quoted before 0/12 (one run)");
});

test("a long pass criterion is shown whole, since it decided the runs", () => {
  const data = F.gridTrial({ a: { c: "PF" } });
  const criterion = `the reply states the outcome plainly. ${"It fails if it hedges about a check it ran. ".repeat(40)}The last clause matters.`;
  data.plan.scenarios[0].judge = { question: "Q?", pass_when: criterion };
  const html = render({ type: "cases" }, data);
  H.includes(html, "The last clause matters.", "the end of the criterion outside any disclosure");
  H.excludes(html, "-webkit-line-clamp", "a second truncation");
});

test("the rule's panel pools the cases it does not name", () => {
  const data = F.gridTrial({ a: { named: "PF", other1: "PP", other2: "PF" } });
  data.plan.decision_rule = "Ship if `named` passes and design passes exceed 2 of 4.";
  const strip = H.element(V.renderReport(V.trialReport(data)), 'class="av-mentions"');
  H.includes(strip, "The other 2 cases together", "the pooled entry");
  H.includes(strip, '<span class="av-frac"><b>3</b>/4</span>', "their counts together");
});

test("grouped verdict checks sit under their own subheading, apart from the terms that decide", () => {
  const html = V.renderBlock({ type: "verdict", verdict: "adopt", headline: "Adopt.", checks: [
    { label: "Main term", observed: "87%", met: true },
    { label: "Other arm meets the bar", observed: "68%", met: false, group: "Other candidates" },
  ] }, V.createContext({}));
  H.ok(html.indexOf("Main term") < html.indexOf('<h5 class="av-rule-group">Other candidates</h5>') && html.indexOf("Other candidates") < html.indexOf("Other arm meets the bar"), "the group after the deciding terms");
  H.equal(V.validateSpec({ title: "T", sections: [{ title: "V", blocks: [{ type: "verdict", headline: "h", checks: [{ label: "l", observed: "o", group: "g" }] }] }] }).filter(p => p.level === "error").length, 0, "group is a known field");
});

test("what was compared leads with case variants, says repeats per arm, shortens home paths in settings and flags a judge that is an arm's model", () => {
  const data = variantTrial({ a: { x: "PP", "x-v": "PF" }, b: { x: "PPP", "x-v": "PFF" } });
  data.plan.arms = { a: { executor: "codex", model: "m1", codex_config: ['hooks.Stop=[{command="python3 /home/someone/hooks/stop.py"}]'] }, b: { executor: "codex", model: "m2", codex_config: ['hooks.Stop=[{command="python3 /home/someone/hooks/stop.py"}]'] } };
  data.plan.judge = { executor: "codex", model: "m1" };
  const html = render({ type: "setup" }, data);
  H.ok(html.indexOf("Case variants") < html.indexOf("Differs between arms"), "the variants before the arm table");
  H.includes(html, "ran as written and with a follow-up turn added", "the variant comparison in the lede");
  H.includes(html, "Each arm ran the same 1 case, as written and as variants (2 case versions): a 2 runs of each, b 3 runs of each.", "repeats per arm");
  H.includes(html, "python3 ~/hooks/stop.py", "the home directory shortened inside a setting");
  H.excludes(html, "/home/someone", "an account name");
  H.includes(html, "The judge is the same model as a it judges (m1).", "the shared model flagged");
});

H.report();
