// The trial composition follows the data and the narrative; the block registry
// adds and restores types; an unknown or failing block leaves a visible notice;
// checks shade required checks by outcome and measures neutrally; the drawer and
// auto-mount paths render what the document carries.
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
const ALL = ["verdict", "arms", "cases", "checks", "pairwise", "cost", "invalid", "runs", "plan"];

// ------------------------------------------------------------------ composition

test("the example trial composes every default section in order", () => {
  const spec = V.trialReport(example, exampleNarrative);
  H.equal(ids(spec), ALL, "section ids");
  H.equal(H.sectionIds(V.renderReport(spec)), ALL, "rendered section ids");
});

test("pairwise appears only with pairwise data", () => {
  const without = { ...example, pairwise: undefined };
  H.ok(!ids(V.trialReport(without)).includes("pairwise"), "a pairwise section without pairwise data");
  H.ok(!ids(V.trialReport({ ...example, pairwise: {} })).includes("pairwise"), "a pairwise section for an empty pairwise object");
  H.ok(ids(V.trialReport(example)).includes("pairwise"), "no pairwise section with pairwise data");
});

test("checks appear only with boolean checks or judge verdicts", () => {
  const bare = F.gridTrial({ a: { c: "PF" }, b: { c: "FP" } });
  H.ok(!ids(V.trialReport(bare)).includes("checks"), "a checks section without checks or a judge");
  const nonBoolean = F.gridTrial({ a: { c: "PF" } }, () => ({ checks: { words: 120 } }));
  H.ok(!ids(V.trialReport(nonBoolean)).includes("checks"), "a checks section for numeric checks only");
  const withChecks = F.gridTrial({ a: { c: "PF" } }, run => ({ checks: { reply_written: run.passed === true } }));
  H.ok(ids(V.trialReport(withChecks)).includes("checks"), "no checks section with boolean checks");
  const judged = F.gridTrial({ a: { c: "PF" } }, run => ({ judge: { verdict: run.passed ? "pass" : "fail" } }));
  H.ok(ids(V.trialReport(judged)).includes("checks"), "no checks section with judge verdicts");
});

test("cost appears only with usage, time or command counts", () => {
  const bare = F.gridTrial({ a: { c: "PF" } });
  H.ok(!ids(V.trialReport(bare)).includes("cost"), "a cost section without usage");
  const zero = F.gridTrial({ a: { c: "PF" } }, () => ({ usage: { output_tokens: 0 }, seconds: 0 }));
  H.ok(!ids(V.trialReport(zero)).includes("cost"), "a cost section for zero usage");
  const usage = F.gridTrial({ a: { c: "PF" } }, () => ({ usage: { output_tokens: 50 } }));
  H.ok(ids(V.trialReport(usage)).includes("cost"), "no cost section with usage");
});

test("a trial without the optional data keeps the always-present sections", () => {
  H.equal(ids(V.trialReport(F.gridTrial({ a: { c: "PF" } }))), ["verdict", "arms", "cases", "invalid", "runs", "plan"], "section ids");
});

test("narrative include keeps only the named sections", () => {
  H.equal(ids(V.trialReport(example, { include: ["runs", "verdict"] })), ["verdict", "runs"], "section ids");
});

test("narrative exclude drops the named sections", () => {
  H.equal(ids(V.trialReport(example, { exclude: ["plan", "cases", "pairwise"] })), ["verdict", "arms", "checks", "cost", "invalid", "runs"], "section ids");
});

test("narrative sections go after the named section or at the end", () => {
  const spec = V.trialReport(example, { sections: [
    { id: "context", title: "Context", after: "verdict", blocks: [{ type: "text", text: "Why." }] },
    { id: "closing", title: "Closing", blocks: [{ type: "text", text: "End." }] },
    { id: "orphan", title: "Orphan", after: "no-such-section", blocks: [] },
  ] });
  H.equal(ids(spec), ["verdict", "context", ...ALL.slice(1), "closing", "orphan"], "section ids");
  H.ok(!("after" in spec.sections[1]), "the placement hint leaks into the section");
  H.includes(V.renderReport(spec), '<section class="av-section" id="context"', "the inserted section");
});

test("narrative append adds blocks to a default section", () => {
  const spec = V.trialReport(example, { append: { runs: [{ type: "callout", text: "Appended note." }] } });
  const runs = spec.sections.find(s => s.id === "runs");
  H.equal(runs.blocks.map(b => b.type), ["ledger", "callout"], "runs blocks");
  const html = V.renderReport(spec);
  H.includes(H.element(html, '<section class="av-section" id="runs"'), "Appended note.", "the appended text");
});

test("blocks appended to an excluded section do not appear", () => {
  const html = V.renderReport(V.trialReport(example, { exclude: ["plan"], append: { plan: [{ type: "text", text: "Hidden." }] } }));
  H.excludes(html, "Hidden.", "text appended to an excluded section");
});

test("narrative groups add a ladder per group and section the run grid", () => {
  const data = F.gridTrial({ a: { c1: "PP", c2: "FF", c3: "P" }, b: { c1: "FF", c2: "PP", c3: "F" } });
  const spec = V.trialReport(data, { groups: [{ label: "First", cases: ["c1"], note: "Group note." }, { label: "Second", cases: ["c2"] }] });
  H.equal(spec.sections.find(s => s.id === "arms").blocks.map(b => [b.type, b.title]), [["ladder", "All cases"], ["ladder", "First"], ["ladder", "Second"]], "arms blocks");
  const html = V.renderReport(spec);
  const ladders = html.split('class="av-block av-block--ladder"').slice(1);
  H.equal(ladders.length, 3, "ladder blocks");
  H.includes(ladders[0], "3 of 5 valid runs passed", "the pooled rate for arm a");
  H.includes(ladders[1], "2 of 2 valid runs passed", "arm a in the first group");
  H.includes(ladders[2], "0 of 2 valid runs passed", "arm a in the second group");
  const tap = H.element(html, 'class="av-block av-block--tapestry"');
  H.equal(H.count(tap, "av-tap-row--group"), 3, "group rows in the run grid");
  for (const label of ["First", "Second", "Other cases", "Group note."]) H.includes(tap, label, `the group heading ${label}`);
});

test("a narrative decision becomes the verdict with the plan's rule", () => {
  const spec = V.trialReport(example, exampleNarrative);
  const verdict = spec.sections[0].blocks[0];
  H.equal([verdict.type, verdict.verdict, verdict.rule], ["verdict", "adopt", example.plan.decision_rule], "verdict block");
  H.includes(V.renderReport(spec), 'data-verdict="adopt"', "the adopt stamp");
});

test("without a decision the verdict says none was supplied", () => {
  const html = V.renderReport(V.trialReport(example));
  H.includes(html, 'data-verdict="none"', "the none stamp");
  H.includes(html, "no decision was supplied", "the no-decision headline");
});

test("titles fall back from narrative title to question, trial name and a default", () => {
  H.equal(V.trialReport(example, { title: "T", question: "Q" }).title, "T", "narrative title");
  H.equal(V.trialReport(example, { question: "Q" }).title, "Q", "question");
  H.equal(V.trialReport({ ...example, name: "N" }).title, "N", "trial name");
  H.equal(V.trialReport({ ...example, name: null }).title, "Trial results", "default");
  H.ok(V.trialReport(example, { title: "T", question: "Q" }).meta.some(m => m.label === "Question" && m.value === "Q"), "the question in the metadata");
});

test("narrative arms set identity order and labels", () => {
  const spec = V.trialReport(example, { arms: { checklist: { label: "Checklist" } } });
  H.equal(spec.arms[0], { id: "checklist", label: "Checklist" }, "first arm");
  H.equal(H.plain(spec.arms.map(a => a.id)).sort(), ["checklist", "current", "current-copy", "worked-example"], "every arm present");
});

test("trialReport refuses data without a runs array", () => {
  H.throws(() => V.trialReport({}), /trial\.py report/, "data without runs");
});

// ------------------------------------------------------------------ registry and notices

test("an unknown block type renders a notice naming every valid type", () => {
  const html = V.renderBlock({ type: "sparkline" }, V.createContext({}));
  H.includes(html, 'class="av-block av-block-error" role="note"', "the notice element");
  H.includes(html, "Unknown block type “sparkline”", "the unknown type");
  const types = H.plain(V.blockTypes());
  H.ok(types.length >= 21, `only ${types.length} block types`);
  for (const type of types) H.includes(html, `<code>${type}</code>`, `the valid type ${type}`);
});

test("a block without a type renders a notice", () => {
  H.includes(V.renderBlock({}, V.createContext({})), "Unknown block type", "the notice");
});

test("an unknown block inside a report leaves the rest of the section intact", () => {
  const html = V.renderReport({ title: "T", sections: [{ title: "S", blocks: [{ type: "text", text: "Before." }, { type: "nope" }, { type: "text", text: "After." }] }] });
  for (const needle of ["Before.", "Unknown block type “nope”", "After."]) H.includes(html, needle);
});

test("a throwing renderer renders a notice with its message", () => {
  const restore = V.registerBlock("explodes", () => { throw new Error("no data for this view"); });
  try {
    const html = V.renderBlock({ type: "explodes" }, V.createContext({}));
    H.includes(html, "The explodes block could not render.", "the notice");
    H.includes(html, "no data for this view", "the message");
  } finally { restore(); }
});

test("a trial block without trial data renders a notice that names the missing field", () => {
  const html = V.renderReport({ title: "T", sections: [{ title: "S", blocks: [{ type: "ladder" }, { type: "ledger" }] }] });
  H.equal(H.count(html, "av-block-error"), 2, "notices");
  H.includes(html, "needs trial data", "the explanation");
});

test("renderReport refuses a specification without a title or sections", () => {
  H.throws(() => V.renderReport({ sections: [] }), /title and a sections array/, "no title");
  H.throws(() => V.renderReport({ title: "T" }), /title and a sections array/, "no sections");
});

test("registerBlock adds a type and its restore function removes it", () => {
  const before = H.plain(V.blockTypes());
  const restore = V.registerBlock("custom-note", input => `<p class="custom">${V.escapeText(input.text)}</p>`);
  H.ok(V.blockTypes().includes("custom-note"), "the type is not listed");
  H.includes(V.renderBlock({ type: "custom-note", text: "<hi>" }, V.createContext({})), '<p class="custom">&lt;hi&gt;</p>', "the custom output");
  restore();
  H.equal(H.plain(V.blockTypes()), before, "types after restore");
  H.includes(V.renderBlock({ type: "custom-note" }, V.createContext({})), "Unknown block type", "the notice after restore");
});

test("registerBlock replaces a built-in and restore brings the original back", () => {
  const ctx = V.createContext({});
  const original = V.renderBlock({ type: "text", text: "Same." }, ctx);
  const restore = V.registerBlock("text", () => "<p>replaced</p>");
  H.equal(V.renderBlock({ type: "text", text: "Same." }, ctx), "<p>replaced</p>", "replaced output");
  restore();
  H.equal(V.renderBlock({ type: "text", text: "Same." }, ctx), original, "restored output");
});

test("nested registrations restore in reverse order", () => {
  const first = V.registerBlock("layered", () => "first");
  const second = V.registerBlock("layered", () => "second");
  const render = () => V.renderBlock({ type: "layered" }, V.createContext({}));
  H.equal(render(), "second", "top registration");
  second();
  H.equal(render(), "first", "after the inner restore");
  first();
  H.includes(render(), "Unknown block type", "after the outer restore");
});

test("registerBlock refuses malformed type names", () => {
  for (const name of ["", "Text", "1x", "a_b", "a b", "-a"]) H.throws(() => V.registerBlock(name, () => ""), /lowercase/, `type ${JSON.stringify(name)}`);
});

// ------------------------------------------------------------------ checks shading

test("required checks are shaded pass/fail and other boolean measures neutrally", () => {
  const data = F.gridTrial({ a: { c: "PPF" }, b: { c: "PFF" } }, run => ({ checks: { reply_written: run.passed === true, cites_source: run.repeat !== 2, words: 100 } }));
  data.plan.scenarios[0].required = ["reply_written"];
  const html = V.renderBlock({ type: "checks" }, V.createContext({ trial: data }));
  const required = H.element(html, "<tr><th scope=\"row\"><code>reply_written</code>");
  const measure = H.element(html, "<tr><th scope=\"row\"><code>cites_source</code>");
  H.equal(H.count(required, 'class="av-heat"'), 2, "pass/fail-shaded cells in the required row");
  H.equal(H.count(required, "av-heat--measure"), 0, "neutral cells in the required row");
  H.equal(H.count(measure, 'class="av-heat av-heat--measure"'), 2, "neutral cells in the measure row");
  H.ok(html.indexOf("Required checks") < html.indexOf("Recorded measures"), "required checks come first");
  H.excludes(html, "<code>words</code>", "a numeric check in the heatmap");
});

test("the judge row is shaded as an outcome, not a measure", () => {
  const data = F.gridTrial({ a: { c: "PF" } }, run => ({ judge: { verdict: run.passed ? "pass" : "fail" } }));
  const row = H.element(V.renderBlock({ type: "checks" }, V.createContext({ trial: data })), "<tr><th scope=\"row\">verdict = pass</th>");
  H.equal(H.count(row, "av-heat--measure"), 0, "neutral judge cells");
  H.includes(row, '<span class="av-frac"><b>1</b>/2</span>', "one of two judged runs passed");
});

// ------------------------------------------------------------------ drawer and auto-mount

test("the run drawer shows a run's record", () => {
  const spec = V.trialReport(example, exampleNarrative);
  const open = H.drawerOpener(V, spec);
  const i = example.runs.findIndex(r => r.judge && r.judge.reason && Object.keys(r.checks || {}).length);
  const run = example.runs[i], html = open(i);
  H.includes(html, `Run ${i + 1} of ${example.runs.length}`, "the run position");
  H.includes(html, V.escapeText(exampleNarrative.cases[run.scenario]), "the case label");
  H.includes(html, V.escapeText(run.judge.reason), "the judge reason");
  for (const name of Object.keys(run.checks)) H.includes(html, `<code>${V.escapeText(name)}</code>`, `the check ${name}`);
  H.includes(html, '<span class="av-chip av-chip--req">required</span>', "the required marker");
  H.includes(html, V.escapeText(run.final_message_excerpt), "the output excerpt");
  H.includes(html, `${V.escapeText(example.run_directory.replace(/\/+$/, ""))}/runs/${V.escapeText(run.job)}/`, "the native record path");
});

test("the run drawer explains why an invalid run is invalid", () => {
  const spec = V.trialReport(example);
  const i = example.runs.findIndex(r => r.passed === null);
  const html = H.drawerOpener(V, spec)(i);
  H.includes(html, "Invalid because", "the invalid reason label");
  H.includes(html, V.escapeText(example.runs[i].invalid_reason || example.runs[i].status), "the reason");
  H.includes(html, "av-badge--invalid", "the invalid badge");
  H.excludes(html, "av-badge--fail", "a failure badge");
});

test("auto-mount renders trial data with its narrative", () => {
  const stub = H.autoMountDocument({ "av-trial": JSON.stringify(example), "av-narrative": JSON.stringify(exampleNarrative) });
  H.loadVisuals({ document: stub.document });
  H.ok(stub.attributes.has("data-av-mounted"), "the target is not marked mounted");
  H.ok(stub.attributes.has("data-av-ready"), "the report is not marked ready");
  H.includes(stub.target.innerHTML, V.escapeText(exampleNarrative.title), "the narrative title");
  H.equal(H.sectionIds(stub.target.innerHTML), ALL, "rendered section ids");
});

test("auto-mount renders a specification, lending it the trial when present", () => {
  const spec = { title: "Spec title", sections: [{ title: "Arms", blocks: [{ type: "ladder" }] }] };
  const stub = H.autoMountDocument({ "av-spec": JSON.stringify(spec), "av-trial": JSON.stringify(example) });
  H.loadVisuals({ document: stub.document });
  H.includes(stub.target.innerHTML, "Spec title", "the specification title");
  H.includes(stub.target.innerHTML, 'data-arm="checklist"', "a ladder drawn from the trial");
  H.excludes(stub.target.innerHTML, "av-block-error", "a notice");
});

test("auto-mount ignores an unreadable narrative and still renders the trial", () => {
  const stub = H.autoMountDocument({ "av-trial": JSON.stringify(example), "av-narrative": "{not json" });
  H.loadVisuals({ document: stub.document });
  H.includes(stub.target.innerHTML, 'data-verdict="none"', "the bare composition");
});

test("auto-mount shows a visible alert when the data cannot render", () => {
  const stub = H.autoMountDocument({ "av-trial": JSON.stringify({ runs: "not a list" }) });
  H.loadVisuals({ document: stub.document });
  H.includes(stub.target.innerHTML, 'role="alert"', "the alert");
  H.includes(stub.target.innerHTML, "This report could not render.", "the alert text");
});

test("auto-mount leaves a document without report data untouched", () => {
  const stub = H.autoMountDocument({});
  H.loadVisuals({ document: stub.document });
  H.equal(stub.target.innerHTML, "", "target markup");
  H.ok(!stub.attributes.has("data-av-mounted"), "the target was marked mounted");
});

H.report();
