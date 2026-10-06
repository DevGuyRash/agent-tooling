// Input validation: validateSpec and validateNarrative name what the library
// cannot use as written, and renderProblems draws them in a visible, escaped
// panel at the top of the report.
//
//   node validate.cjs                 runs the cases (see test_validate.py)
//   node validate.cjs --corpus IN --out OUT
//                                     writes the problems for each corpus entry to OUT,
//                                     so test_validate.py can compare report.py's checker
"use strict";
const fs = require("node:fs");
const path = require("node:path");
const H = require("./harness.cjs");
const F = require("./fixtures.cjs");
const { test } = H;

const V = H.loadVisuals();

const at = process.argv.indexOf("--corpus");
if (at >= 0) {
  // { trials: {name: trial}, entries: [{kind, input, trial: name | null}] }
  const corpus = JSON.parse(fs.readFileSync(process.argv[at + 1], "utf8"));
  const out = corpus.entries.map(entry => {
    const trial = entry.trial === null || entry.trial === undefined ? undefined : corpus.trials[entry.trial];
    if (entry.kind === "types") return H.plain(V.blockTypes());
    if (entry.kind === "spec") return H.plain(V.validateSpec(entry.input, { trial }));
    return H.plain(V.validateNarrative(entry.input, trial));
  });
  // A file, not stdout: exiting right after a large write to a pipe can cut it short.
  fs.writeFileSync(process.argv[process.argv.indexOf("--out") + 1], JSON.stringify(out));
  process.exit(0);
}

const example = JSON.parse(fs.readFileSync(path.join(H.VISUALS, "examples", "fictional-trial.json"), "utf8"));
const exampleNarrative = JSON.parse(fs.readFileSync(path.join(H.VISUALS, "examples", "fictional-narrative.json"), "utf8"));
const showcase = JSON.parse(fs.readFileSync(path.join(H.VISUALS, "examples", "showcase-spec.json"), "utf8"));
const where = problems => H.plain(problems).map(p => `${p.level} ${p.where}`);
const one = blocks => ({ title: "T", sections: [{ title: "S", blocks }] });
const panel = html => (html.match(/<aside class="av-problems[\s\S]*?<\/aside>/) || [""])[0];
// renderProblems is reached through renderReport, which lists the problems a specification carries.
const drawn = problems => panel(V.renderReport({ title: "T", sections: [], problems }));

test("the examples carry no problems", () => {
  H.equal(where(V.validateNarrative(exampleNarrative, example)), [], "fictional narrative");
  H.equal(where(V.validateSpec(showcase)), [], "showcase specification");
  const spec = V.trialReport(example, exampleNarrative);
  H.equal(where(V.validateSpec(spec)), [], "composed specification");
  H.excludes(V.renderReport(spec), "av-problems", "a problems panel");
  H.excludes(V.renderReport(showcase), "av-problems", "a problems panel");
});

test("a misspelled verdict, arm, case and section are named with a suggestion", () => {
  const narrative = {
    ...exampleNarrative,
    decision: { ...exampleNarrative.decision, verdict: "adpot" },
    arms: [{ id: "curent", label: "Current" }],
    groups: [{ label: "G", cases: ["label-a-foto"] }],
    exclude: ["arm"],
  };
  const problems = H.plain(V.validateNarrative(narrative, example));
  const find = w => problems.find(p => p.where === w) || H.fail(`no problem at ${w}: ${JSON.stringify(problems)}`);
  H.equal([find("narrative.decision.verdict").level, find("narrative.decision.verdict").hint.startsWith('did you mean "adopt"?')], ["error", true], "verdict");
  H.equal([find("narrative.arms[0].id").level, find("narrative.arms[0].id").hint], ["warning", 'did you mean "current"?'], "arm label");
  H.equal([find("narrative.groups[0].cases[0]").level, find("narrative.groups[0].cases[0]").hint], ["error", 'did you mean "label-a-photo"?'], "group case");
  H.equal([find("narrative.exclude[0]").level, find("narrative.exclude[0]").hint], ["error", 'did you mean "arms"?'], "section id");
});

test("errors come before warnings, and each problem has a hint", () => {
  const problems = H.plain(V.validateSpec(one([{ type: "ladder", titel: "x", rows: [{ arm: "a", k: 6, n: 5 }] }, { type: "sparkline" }])));
  H.equal(problems.map(p => p.level), ["error", "error", "warning"], "levels");
  H.ok(problems.every(p => typeof p.hint === "string" && p.hint), "a problem without a hint");
  H.equal(problems.map(p => p.where), ["sections[0].blocks[0] (ladder).rows[0]", "sections[0].blocks[1]", "sections[0].blocks[0] (ladder).titel"], "places");
});

test("more passes than valid runs is an error, not a clamped rate", () => {
  for (const block of [{ type: "ladder", rows: [{ arm: "a", k: 12, n: 5 }] }, { type: "intervals", rows: [{ label: "x", k: 12, n: 5 }] }, { type: "trend", stages: ["s"], series: [{ label: "x", points: [{ stage: "s", k: 12, n: 5 }] }] }]) {
    const problems = H.plain(V.validateSpec(one([block])));
    H.ok(problems.some(p => p.level === "error" && p.message === "k (12) is larger than n (5)"), `${block.type}: ${JSON.stringify(problems)}`);
  }
});

test("missing arrays a block maps over are errors", () => {
  const problems = H.plain(V.validateSpec(one([{ type: "trend", stages: ["s"], series: [{ label: "x" }] }, { type: "table", columns: ["a"], rows: { a: 1 } }])));
  H.equal(problems.map(p => `${p.where}: ${p.message}`), [
    'sections[0].blocks[0] (trend).series[0]: missing required field "points"',
    "sections[0].blocks[1] (table).rows: expected a list, found an object",
  ], "problems");
});

test("trial blocks without trial data are named, and borrow a trial supplied beside the spec", () => {
  const spec = one([{ type: "tapestry" }, { type: "ladder" }]);
  H.equal(where(V.validateSpec(spec)), ["error sections[0].blocks[0] (tapestry)", "error sections[0].blocks[1] (ladder)"], "without a trial");
  H.equal(where(V.validateSpec(spec, { trial: example })), [], "with a trial beside it");
  H.equal(where(V.validateSpec({ ...spec, trial: example })), [], "with its own trial");
});

test("ids are checked against the trial only when there is one", () => {
  const spec = one([{ type: "tapestry", arms: ["nope"], cases: ["label-a-photo"] }]);
  H.equal(where(V.validateSpec({ ...spec, trial: example })), ["error sections[0].blocks[0] (tapestry).arms[0]"], "with the trial");
  const free = one([{ type: "intervals", rows: [{ label: "x", arm: "anything", value: 0.5 }] }]);
  H.equal(where(V.validateSpec(free)), [], "an arm in a general block of a spec without a trial");
});

test("arms called identical must match in every recorded setting", () => {
  H.equal(where(V.validateNarrative({ identical: [["current", "current-copy"]] }, example)), [], "true copies");
  const [problem] = H.plain(V.validateNarrative({ identical: [["current", "checklist"]] }, example));
  H.equal([problem.level, problem.where], ["error", "narrative.identical[0][1]"], "the differing arm");
  H.equal(problem.message, '"checklist" differs from "current" in instructions_sha256, so the gap between them is not chance alone', "the message");
  const copy = JSON.parse(JSON.stringify(example));
  copy.plan.arms["current-copy"].instructions_text = "The text itself, which the digest already stands for.";
  H.equal(where(V.validateNarrative({ identical: [["current", "current-copy"]] }, copy)), [], "material text is compared through its digest");
});

test("a type registered at run time is known to the validator", () => {
  const restore = V.registerBlock("custom-view", () => "<p>custom</p>");
  try { H.equal(where(V.validateSpec(one([{ type: "custom-view", anything: 1 }]))), [], "registered type"); }
  finally { restore(); }
  H.equal(where(V.validateSpec(one([{ type: "custom-view" }]))), ["error sections[0].blocks[0]"], "after restore");
});

test("the validator's block types are the registry's", () => {
  const [problem] = H.plain(V.validateSpec(one([{ type: "zzzzzzzz" }])));
  H.equal(problem.hint, `block types: ${H.plain(V.blockTypes()).join(", ")}`, "hint");
});

test("the validator's section ids are the composition's", () => {
  const ids = H.plain(V.SECTION_IDS);
  H.equal(H.plain(V.trialReport(example, { include: ids }).sections.map(s => s.id)), ids, "the fictional trial composes every default section when include names them all");
  const [problem] = H.plain(V.validateNarrative({ include: ["zzzzzzzz"] }, example));
  H.equal(problem.hint, `sections: ${ids.join(", ")}`, "the hint lists every default section");
  H.equal(where(V.validateNarrative({ include: ["plan"], append: { plan: [{ type: "text", text: "x" }] } }, example)), [], "the earlier id plan still names setup");
  H.equal(H.plain(V.trialReport(example, { include: ["plan"] }).sections.map(s => s.id)), ["setup"], "the composition agrees");
});

test("a narrative's problems reach the report's panel once", () => {
  const spec = V.trialReport(example, { ...exampleNarrative, decision: { ...exampleNarrative.decision, verdict: "adpot" } });
  const html = V.renderReport(spec);
  const box = panel(html);
  H.ok(box, "no problems panel");
  H.equal(H.count(box, "narrative.decision.verdict"), 1, "times the problem is listed");
  H.includes(box, "This report's input has 1 error", "the summary line");
  H.includes(box, "<details class=\"av-problems-details\" open>", "an open list for an error");
  H.equal(H.sectionIds(html), spec.sections.map(s => s.id), "every section still renders");
});

test("warnings alone fold the list under a visible summary", () => {
  const html = drawn([{ level: "warning", where: "narrative.titel", message: 'unknown field "titel" is not used', hint: 'did you mean "title"?' }]);
  H.includes(html, "av-problems--warning", "the warning tone");
  H.includes(html, "This report's input has 1 warning", "the summary");
  H.excludes(html, " open>", "an open list");
  H.includes(html, "<summary>", "the toggle");
});

test("a long list keeps eight in view and folds the rest", () => {
  const problems = Array.from({ length: 11 }, (_, i) => ({ level: i < 2 ? "error" : "warning", where: `w${i}`, message: `m${i}` }));
  const html = drawn(problems);
  H.equal(H.count(html, 'class="av-problem av-problem--'), 11, "items");
  H.includes(html, "Show 3 more problems", "the second fold");
  H.includes(html, '<ol class="av-problems-list" start="9">', "numbering continues");
  H.includes(html, "2 errors and 9 warnings", "the summary");
});

test("no panel is drawn for no problems or only malformed entries", () => {
  H.equal(drawn([]), "", "no problems");
  H.equal(drawn([null, 3, { level: "error" }, { where: "x" }]), "", "only malformed entries");
  H.equal(drawn(undefined), "", "no problems field");
});

test("every text field of a problem is escaped", () => {
  const html = drawn([{ level: F.hostile("level"), where: F.hostile("where"), message: F.hostile("message"), hint: F.hostile("hint") }]);
  H.equal(F.rawHostileFields(html), [], "raw fields");
  for (const field of ["where", "message", "hint"]) H.includes(html, F.escapedHostile(field), `the escaped ${field}`);
  H.excludes(html, F.escapedHostile("level"), "the level, which is a fixed word");
});

test("hostile ids and values are escaped where the validator quotes them", () => {
  const narrative = { decision: { verdict: F.hostile("verdict-word"), headline: "h" }, arms: [{ id: F.hostile("arm-id") }], exclude: [F.hostile("section")], [F.hostile("field")]: 1 };
  const html = V.renderReport(V.trialReport(example, narrative));
  const box = panel(html);
  H.equal(F.rawHostileFields(html), [], "raw fields");
  for (const field of ["verdict-word", "arm-id", "section", "field"]) H.includes(box, F.escapedHostile(field).slice(0, 40), `the escaped ${field}`);
});

test("a malformed specification is reported without throwing", () => {
  for (const input of [null, 7, "spec", [], { title: 3, sections: {} }, { title: "T", sections: [null, { title: "S", blocks: [null, 4, { type: 5 }] }] }]) {
    const problems = H.plain(V.validateSpec(input));
    H.ok(problems.length && problems.every(p => p.level === "error" || p.level === "warning"), `no problems for ${JSON.stringify(input)}`);
  }
  for (const input of [null, 7, [], { decision: 3, arms: 4, identical: [3], sections: [null] }])
    H.ok(H.plain(V.validateNarrative(input, example)).length, `no problems for narrative ${JSON.stringify(input)}`);
});

test("keys starting with $ are notes, never problems", () => {
  H.equal(where(V.validateNarrative({ $rule: "x", decision: { $verdicts: "y", verdict: "none", headline: "h" }, cases: { $note: "z" } }, example)), [], "narrative notes");
  H.equal(where(V.validateSpec({ ...one([{ type: "text", text: "x", $why: 1 }]), $about: "x" })), [], "spec notes");
});

test("a narrative threshold is a share, the run grid is opt-in, and a setup block with its own settings needs no trial", () => {
  const far = H.plain(V.validateNarrative({ threshold: 15 }, example));
  H.equal(far.map(p => [p.level, p.where]), [["error", "narrative.threshold"]], "a threshold written in points");
  H.includes(far[0].hint, "0.15 for +15 points", "the hint");
  H.equal(where(V.validateNarrative({ threshold: { value: 0.15, label: "bar" } }, example)), [], "a share with a label");
  const grid = H.plain(V.validateNarrative({ append: { grid: [{ type: "text", text: "x" }] } }, example));
  H.equal(grid.map(p => p.message), ['section "grid" is drawn only when include names it, so these blocks do not appear'], "blocks appended to the opt-in grid");
  H.equal(where(V.validateNarrative({ include: ["cases", "grid"], append: { grid: [] } }, example)), [], "the grid once include names it");
  H.equal(where(V.validateSpec(one([{ type: "setup", settings: { a: { model: "m" } } }]))), [], "explicit settings");
  H.equal(where(V.validateSpec(one([{ type: "setup" }]))), ["error sections[0].blocks[0] (setup)"], "neither settings nor a trial");
  H.equal(where(V.validateSpec(one([{ type: "checks", required: false }]), { trial: example })), [], "measures only");
});

H.report();
