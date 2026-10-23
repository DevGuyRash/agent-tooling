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

// node validate.cjs --ids IN --out OUT: each entry checked by the validator its kind names, with its data given inline;
// an exception is recorded as {exception}, so a crash on malformed input is a finding, not a failed run.
const ids = process.argv.indexOf("--ids");
if (ids >= 0) {
  const entries = JSON.parse(fs.readFileSync(process.argv[ids + 1], "utf8"));
  const out = entries.map(e => {
    try {
      // A specification is also drawn: whether its page says it has an error, and what its pairwise view draws.
      if (e.kind === "spec" && e.render) {
        const html = V.renderReport(e.input);
        return { problems: H.plain(V.validateSpec(e.input)), flagged: html.includes("av-problems--error"), duels: (html.match(/data-pair="/g) || []).length };
      }
      if (e.kind === "spec") return H.plain(V.validateSpec(e.input));
      if (e.kind === "narrative") return H.plain(V.validateNarrative(e.input, e.trial));
      if (e.kind === "collection") return H.plain(V.validateCollection(e.input));
      return H.plain("narrative" in e ? V.validateComparison(e.input, e.narrative) : V.validateComparison(e.input));
    } catch (error) { return { exception: String(error && error.stack || error).slice(0, 400) }; }
  });
  fs.writeFileSync(process.argv[process.argv.indexOf("--out") + 1], JSON.stringify(out));
  process.exit(0);
}

const at = process.argv.indexOf("--corpus");
if (at >= 0) {
  // { trials: {name: trial}, entries: [{kind, input, trial: name | null}] }
  const corpus = JSON.parse(fs.readFileSync(process.argv[at + 1], "utf8"));
  const out = corpus.entries.map(entry => {
    const trial = entry.trial === null || entry.trial === undefined ? undefined : corpus.trials[entry.trial];
    if (entry.kind === "types") return H.plain(V.blockTypes());
    if (entry.kind === "collection") return H.plain(V.validateCollection(entry.input));
    if (entry.kind === "spec") return H.plain(V.validateSpec(entry.input, { trial, collection: entry.collection ? corpus.collections[entry.collection] : undefined }));
    return H.plain(V.validateNarrative(entry.input, trial));
  });
  // A file, not stdout: exiting right after a large write to a pipe can cut it short.
  fs.writeFileSync(process.argv[process.argv.indexOf("--out") + 1], JSON.stringify(out));
  process.exit(0);
}

const example = JSON.parse(fs.readFileSync(path.join(H.VISUALS, "examples", "fictional-trial.json"), "utf8"));
const exampleNarrative = JSON.parse(fs.readFileSync(path.join(H.VISUALS, "examples", "fictional-narrative.json"), "utf8"));
const showcase = JSON.parse(fs.readFileSync(path.join(H.VISUALS, "examples", "showcase-spec.json"), "utf8"));
const where = problems => H.withoutStory(problems).map(p => `${p.level} ${p.where}`);
const one = blocks => ({ title: "T", sections: [{ title: "S", blocks }] });
const panel = html => (html.match(/<aside class="av-problems[\s\S]*?<\/aside>/) || [""])[0];
// renderProblems is reached through renderReport, which lists the problems a specification carries.
const told = { background: "b", intent: "i", questions: ["q"], covers: "c", notCovered: "n" };
const drawn = problems => panel(V.renderReport({ title: "T", sections: [], story: told, problems }));

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
  const problems = H.withoutStory(V.validateNarrative(narrative, example));
  const find = w => problems.find(p => p.where === w) || H.fail(`no problem at ${w}: ${JSON.stringify(problems)}`);
  H.equal([find("narrative.decision.verdict").level, find("narrative.decision.verdict").hint.startsWith('did you mean "adopt"?')], ["error", true], "verdict");
  H.equal([find("narrative.arms[0].id").level, find("narrative.arms[0].id").hint], ["warning", 'did you mean "current"?'], "arm label");
  H.equal([find("narrative.groups[0].cases[0]").level, find("narrative.groups[0].cases[0]").hint], ["error", 'did you mean "label-a-photo"?'], "group case");
  H.equal([find("narrative.exclude[0]").level, find("narrative.exclude[0]").hint], ["error", 'did you mean "arms"?'], "section id");
});

test("errors come before warnings, and each problem has a hint", () => {
  const problems = H.withoutStory(V.validateSpec(one([{ type: "ladder", titel: "x", rows: [{ arm: "a", k: 6, n: 5 }] }, { type: "sparkline" }])));
  H.equal(problems.map(p => p.level), ["error", "error", "warning"], "levels");
  H.ok(problems.every(p => typeof p.hint === "string" && p.hint), "a problem without a hint");
  H.equal(problems.map(p => p.where), ["sections[0].blocks[0] (ladder).rows[0]", "sections[0].blocks[1]", "sections[0].blocks[0] (ladder).titel"], "places");
});

test("more passes than valid runs is an error, not a clamped rate", () => {
  for (const block of [{ type: "ladder", rows: [{ arm: "a", k: 12, n: 5 }] }, { type: "intervals", rows: [{ label: "x", k: 12, n: 5 }] }, { type: "trend", stages: ["s"], series: [{ label: "x", points: [{ stage: "s", k: 12, n: 5 }] }] }]) {
    const problems = H.withoutStory(V.validateSpec(one([block])));
    H.ok(problems.some(p => p.level === "error" && p.message === "k (12) is larger than n (5)"), `${block.type}: ${JSON.stringify(problems)}`);
  }
});

test("missing arrays a block maps over are errors", () => {
  const problems = H.withoutStory(V.validateSpec(one([{ type: "trend", stages: ["s"], series: [{ label: "x" }] }, { type: "table", columns: ["a"], rows: { a: 1 } }])));
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
  const [problem] = H.withoutStory(V.validateNarrative({ identical: [["current", "checklist"]] }, example));
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
  const [problem] = H.withoutStory(V.validateSpec(one([{ type: "zzzzzzzz" }])));
  H.equal(problem.hint, `block types: ${H.plain(V.blockTypes()).join(", ")}`, "hint");
});

test("the validator's section ids are the composition's", () => {
  const ids = H.plain(V.SECTION_IDS);
  H.equal(H.plain(V.trialReport(example, { include: ids }).sections.map(s => s.id)), ids, "the fictional trial composes every default section when include names them all");
  const [problem] = H.withoutStory(V.validateNarrative({ include: ["zzzzzzzz"] }, example));
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
  H.equal(H.sectionIds(html), ["story", ...spec.sections.map(s => s.id)], "every section still renders, after the story");
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
    const problems = H.withoutStory(V.validateSpec(input));
    H.ok(problems.length && problems.every(p => p.level === "error" || p.level === "warning"), `no problems for ${JSON.stringify(input)}`);
  }
  for (const input of [null, 7, [], { decision: 3, arms: 4, identical: [3], sections: [null] }])
    H.ok(H.withoutStory(V.validateNarrative(input, example)).length, `no problems for narrative ${JSON.stringify(input)}`);
});

test("keys starting with $ are notes, never problems", () => {
  H.equal(where(V.validateNarrative({ $rule: "x", decision: { $verdicts: "y", verdict: "none", headline: "h" }, cases: { $note: "z" } }, example)), [], "narrative notes");
  H.equal(where(V.validateSpec({ ...one([{ type: "text", text: "x", $why: 1 }]), $about: "x" })), [], "spec notes");
});

test("a narrative threshold is a share, the run grid is opt-in, and a setup block with its own settings needs no trial", () => {
  const far = H.withoutStory(V.validateNarrative({ threshold: 15 }, example));
  H.equal(far.map(p => [p.level, p.where]), [["error", "narrative.threshold"]], "a threshold written in points");
  H.includes(far[0].hint, "0.15 for +15 points", "the hint");
  H.equal(where(V.validateNarrative({ threshold: { value: 0.15, label: "bar" } }, example)), [], "a share with a label");
  const grid = H.withoutStory(V.validateNarrative({ append: { grid: [{ type: "text", text: "x" }] } }, example));
  H.equal(grid.map(p => p.message), ['section "grid" is drawn only when include names it, so these blocks do not appear'], "blocks appended to the opt-in grid");
  H.equal(where(V.validateNarrative({ include: ["cases", "grid"], append: { grid: [] } }, example)), [], "the grid once include names it");
  H.equal(where(V.validateSpec(one([{ type: "setup", settings: { a: { model: "m" } } }]))), [], "explicit settings");
  H.equal(where(V.validateSpec(one([{ type: "setup" }]))), ["error sections[0].blocks[0] (setup)"], "neither settings nor a trial");
  H.equal(where(V.validateSpec(one([{ type: "checks", required: false }]), { trial: example })), [], "measures only");
});

test("a trial run that names no scenario is refused by every check that reads trial data", () => {
  // Five runs on c1; runs 1 to 4 then lose their scenario: left out, null, empty and only spaces. trial.py never writes these.
  const t = F.gridTrial({ a: { c1: "PPPPP" } });
  delete t.runs[1].scenario; t.runs[2].scenario = null; t.runs[3].scenario = ""; t.runs[4].scenario = "   ";
  const said = (problems, prefix) => H.plain(problems).filter(p => /scenario/.test(p.where)).map(p => `${p.level} ${p.where}: ${p.message}`);
  const owed = prefix => [1, 2, 3, 4].map(i => `error ${prefix}runs[${i}].scenario: a trial run must name its scenario`);
  H.equal(said(V.validateSpec({ title: "T", sections: [], trial: t })), owed("trial."), "a specification carrying the trial");
  H.equal(said(V.validateNarrative({}, t)), owed("trial."), "a narrative checked against it");
  H.equal(said(V.validateSpec(V.trialReport(t, {}))), owed("trial."), "the composed report, each run once");
  H.equal(said(V.validateCollection({ members: [{ id: "m", trial: t }] })), owed("collection.members[0].trial."), "a collection's member");
  H.includes(V.renderReport(V.trialReport(t, {})), "<p class=\"av-problem-msg\">a trial run must name its scenario</p>", "the page's input check says so");
  H.equal(said(V.validateNarrative({}, F.gridTrial({ a: { c1: "PP" } }))), [], "runs that name their scenario pass");
});

test("round 18: an empty or blank case filter selects the evidence naming no case, and every way trial data enters is checked", () => {
  const text = html => html.replace(/<[^>]+>/g, " ").replace(/&#39;/g, "'").replace(/\s+/g, " ");
  // 1. a passes and b fails, each once, both with case "": a filter on "" or on spaces selects that evidence, 1 of 1 and 0 of 1.
  const data = { alternatives: [{ id: "a" }, { id: "b" }], metrics: [{ id: "ok", kind: "binary" }],
    observations: [{ alternative: "a", case: "", metric: "ok", value: true }, { alternative: "b", case: "", metric: "ok", value: false }] };
  for (const selector of ["", "   "]) {
    const sums = H.plain(V.summarize(data, "ok", { cases: [selector] }).map(s => [s.alternative, s.k, s.n]));
    H.equal(sums, [["a", 1, 1], ["b", 0, 1]], `"${selector}": the summaries`);
    const view = text(V.renderBlock({ type: "metric", metric: "ok", cases: [selector] }, V.createContext({ comparison: data })));
    H.includes(view, "1/1", `"${selector}": a's one observation`); H.excludes(view, "no observations", `"${selector}": nothing missing`);
    H.includes(view, "Only evidence naming no case", `"${selector}": the filter in the words the views use`);
  }
  const said = H.plain(V.validateSpec({ title: "T", sections: [{ title: "S", reading: "r", blocks: [{ type: "metric", metric: "ok", cases: [""] }] }], comparison: data })).filter(p => /cases\[0\]/.test(p.where));
  H.ok(said.length === 1 && /evidence naming no case/.test(said[0].message) && said[0].level === "warning", `the check says what the filter selects: ${JSON.stringify(said)}`);
  // 2. A run naming no scenario, borrowed beside a specification rather than carried in it, is refused as when carried.
  const trial = { runs: [{ job: "j1", arm: "a", scenario: "c1", repeat: 1, passed: true, valid: true }, { job: "j2", arm: "a", scenario: "", repeat: 2, passed: false, valid: true }] };
  const spec = { title: "T", sections: [{ title: "S", reading: "r", blocks: [{ type: "ladder" }] }] };
  const refused = problems => H.plain(problems).filter(p => /scenario/.test(p.where)).map(p => `${p.level} ${p.where}: ${p.message}`);
  const owed = ["error trial.runs[1].scenario: a trial run must name its scenario"];
  H.equal(refused(V.validateSpec(spec, { trial })), owed, "borrowed beside the specification");
  H.equal(refused(V.validateSpec({ ...spec, trial })), owed, "carried in it, once");
  H.equal(refused(V.validateSpec({ ...spec, trial }, { trial })), owed, "both, once");
  H.equal(refused(V.validateNarrative({}, trial)), owed, "a narrative's trial");
  H.equal(refused(V.validateCollection({ members: [{ id: "m", trial }, { id: "s", spec: { ...spec, trial } }] })), ["error collection.members[0].trial.runs[1].scenario: a trial run must name its scenario", "error collection.members[1].spec.trial.runs[1].scenario: a trial run must name its scenario"], "a collection's trial member and its specification member");
});

test("sweep (a selected matrix): every filter form selects the one group of evidence naming no case, in every comparison view", () => {
  // Evidence in each unnamed form, x passing and y failing on each, and a named case c1 the filters leave out.
  const forms = [undefined, null, "", "   "];
  const at = (c, x) => c === undefined ? x : { ...x, case: c };
  const data = { alternatives: [{ id: "x" }, { id: "y" }], metrics: [{ id: "ok", kind: "binary" }, { id: "p", kind: "preference" }],
    observations: [...forms.flatMap(c => [at(c, { alternative: "x", metric: "ok", value: true }), at(c, { alternative: "y", metric: "ok", value: false })]), { alternative: "x", case: "c1", metric: "ok", value: false }],
    preferences: [...forms.map(c => at(c, { a: "x", b: "y", winner: "x" })), { a: "x", b: "y", winner: "y", case: "c1" }] };
  const ctx = () => V.createContext({ comparison: data });
  for (const selector of ["", " ", "   "]) {
    H.equal(H.plain(V.summarize(data, "ok", { cases: [selector] }).map(s => [s.alternative, s.k, s.n])), [["x", 4, 4], ["y", 0, 4]], `"${selector}": the four forms, and not c1`);
    H.equal(V.difference(data, "ok", "x", "y", { cases: [selector] }).estimate, 1, `"${selector}": the difference over them`);
    const wins = H.plain(V.winMatrix(data, "p", { cases: [selector] }).wins);
    H.equal(wins, [[0, 4], [0, 0]], `"${selector}": the judgments' wins`);
    const prefs = V.renderBlock({ type: "preferences", metric: "p", cases: [selector] }, ctx());
    H.excludes(prefs, "No judgments were recorded", `"${selector}": the preferences view keeps them`);
    const ledger = V.renderBlock({ type: "observations", cases: [selector] }, ctx());
    H.equal((ledger.match(/data-av-row=/g) || []).length, 8, `"${selector}": the ledger lists the eight unnamed observations`);
    // x passes all four, y none: 4/4 and 0/4, a difference of +100 points.
    for (const type of ["metric", "scorecard"]) { const html = V.renderBlock({ type, metric: "ok", cases: [selector] }, ctx()); H.includes(html, "4/4", `"${selector}" (${type}): x's four`); H.includes(html, "0/4", `"${selector}" (${type}): y's four`); }
    H.includes(V.renderBlock({ type: "difference", metric: "ok", cases: [selector] }, ctx()).replace(/<[^>]+>/g, " ").replace(/\s+/g, " "), "y 0% · 0/4 minus x 100% · 4/4 −100 pts", `"${selector}" (difference): y minus x over them`);
  }
});

// ------------------------------------------------------------------ data kind × entry path

/** Bad inputs of each kind a report reads, and every way each enters a check: the problems found in the input, under its
 * place on each path, must be the same set whichever way it enters. */
const ENTRY_MATRIX = (() => {
  const badTrial = () => { const t = F.gridTrial({ a: { c1: "PPP" } }); t.runs[1].scenario = ""; t.runs[2].scenario = 0; return t; };
  const goodTrial = () => F.gridTrial({ a: { c1: "PP" }, b: { c1: "PF" } });
  const badComparison = () => ({ alternatives: [{ id: "x" }], metrics: [{ id: "m", kind: "weird" }], observations: [{ alternative: "zz", metric: "m", value: 1, case: 3 }] });
  const goodComparison = () => ({ alternatives: [{ id: "x" }, { id: "y" }], metrics: [{ id: "m", kind: "binary" }], observations: [{ alternative: "x", metric: "m", value: true }] });
  const badCollection = () => ({ members: [{ id: "one", trial: { runs: [{ arm: "a", scenario: "c1", passed: true }] } }] });
  const badNarrative = () => ({ titel: "x", decision: { verdict: "adpot", headline: "H." } });
  const bare = (extra = {}) => ({ title: "T", sections: [], ...extra });
  const view = data => ({ title: "T", sections: [{ title: "S", reading: "r", blocks: [{ type: "metric", metric: "m", data }] }] });
  return {
    "trial": [
      ["a specification's own", () => V.validateSpec(bare({ trial: badTrial() })), "trial"],
      ["supplied beside a specification", () => V.validateSpec(bare(), { trial: badTrial() }), "trial"],
      ["a narrative's", () => V.validateNarrative({}, badTrial()), "trial"],
      ["the composed report", () => V.validateSpec(V.trialReport(badTrial(), {})), "trial"],
      ["a collection member's", () => V.validateCollection({ members: [{ id: "m", trial: badTrial() }] }), "collection.members[0].trial"],
      ["a collection specification member's", () => V.validateCollection({ members: [{ id: "m", spec: bare({ trial: badTrial() }) }] }), "collection.members[0].spec.trial"],
      ["a member of a collection a specification carries", () => V.validateSpec(bare({ collection: { members: [{ id: "m", trial: badTrial() }] } })), "collection.members[0].trial"],
      ["a member of a collection supplied beside a specification", () => V.validateSpec(bare(), { collection: { members: [{ id: "m", trial: badTrial() }] } }), "collection.members[0].trial"],
    ],
    "comparison": [
      ["a specification's own", () => V.validateSpec(bare({ comparison: badComparison() })), "comparison"],
      ["supplied beside a specification", () => V.validateSpec(bare(), { comparison: badComparison() }), "comparison"],
      ["a view's own data", () => V.validateSpec(view(badComparison())), "sections[0].blocks[0] (metric).data"],
      ["checked alone", () => V.validateComparison(badComparison()), "comparison"],
      ["the composed report", () => V.validateSpec(V.comparisonReport(badComparison(), {})), "comparison"],
      ["a collection member's", () => V.validateCollection({ members: [{ id: "m", comparison: badComparison() }] }), "collection.members[0].comparison"],
      ["a collection specification member's", () => V.validateCollection({ members: [{ id: "m", spec: bare({ comparison: badComparison() }) }] }), "collection.members[0].spec.comparison"],
      ["a view a trial narrative adds", () => V.validateNarrative({ sections: [{ title: "More", blocks: [{ type: "metric", metric: "m", data: badComparison() }] }] }, goodTrial()), "narrative.sections[0].blocks[0] (metric).data"],
      ["a view a comparison narrative adds", () => V.validateComparison(goodComparison(), { sections: [{ title: "More", blocks: [{ type: "metric", metric: "m", data: badComparison() }] }] }), "narrative.sections[0].blocks[0] (metric).data"],
    ],
    "collection": [
      ["a specification's own", () => V.validateSpec(bare({ collection: badCollection() })), "collection"],
      ["supplied beside a specification", () => V.validateSpec(bare(), { collection: badCollection() }), "collection"],
      ["checked alone", () => V.validateCollection(badCollection()), "collection"],
      ["the composed report", () => V.validateSpec(V.collectionReport(badCollection())), "collection"],
    ],
    "trial narrative": [
      ["checked against its trial", () => V.validateNarrative(badNarrative(), goodTrial()), "narrative"],
      ["the composed report", () => V.validateSpec(V.trialReport(goodTrial(), badNarrative())), "narrative"],
      ["a collection member's", () => V.validateCollection({ members: [{ id: "m", trial: goodTrial(), narrative: badNarrative() }] }), "collection.members[0].narrative"],
    ],
    "comparison narrative": [
      ["checked against its comparison", () => V.validateComparison(goodComparison(), badNarrative()), "narrative"],
      ["the composed report", () => V.validateSpec(V.comparisonReport(goodComparison(), badNarrative())), "narrative"],
      ["a collection member's", () => V.validateCollection({ members: [{ id: "m", comparison: goodComparison(), narrative: badNarrative() }] }), "collection.members[0].narrative"],
    ],
  };
})();
/** The problems found in the input entered at `at`, each placed within the input. */
const within = (problems, at) => H.plain(problems).filter(p => p.where === at || p.where.startsWith(`${at}.`) || p.where.startsWith(`${at}[`)).map(p => `${p.level} ${p.where.slice(at.length).replace(/^\./, "") || "(the input)"}: ${p.message}`).sort();

test("sweep (a selected matrix): each kind of data a report reads is checked alike on every path it enters by", () => {
  for (const [kind, paths] of Object.entries(ENTRY_MATRIX)) {
    const [first, ...rest] = paths.map(([name, run, at]) => [name, within(run(), at)]);
    H.ok(first[1].length > 0, `${kind}: the bad input has problems (${first[0]})`);
    for (const [name, found] of rest) H.equal(found, first[1], `${kind}: ${name} against ${first[0]}`);
  }
  // A scenario that is not text is refused as a missing one is.
  H.equal(within(V.validateSpec({ title: "T", sections: [], trial: { runs: [{ arm: "a", scenario: 0, passed: true }, { arm: "a", scenario: false, passed: true }, { arm: "a", scenario: {}, passed: true }, { arm: "a", scenario: [], passed: true }, { arm: "a", scenario: "c1", passed: true }] } }), "trial"),
    [0, 1, 2, 3].map(i => `error runs[${i}].scenario: a trial run must name its scenario`), "numbers, booleans, objects and lists");
});

test("round 20: a trial run's arm must be text, and a view's data that is not a comparison is named once", () => {
  // The reviewer's specification: a story describing arm a and case c1, and a second run whose arm is not text.
  const story = { background: "b", intent: "i", questions: ["q"], rule: "r", covers: "c", notCovered: "n", alternatives: { a: "Setup A." }, cases: { c1: "The case." } };
  for (const arm of [0, null, false, {}, [], "", "  "]) {
    const spec = { title: "Probe", story, sections: [{ title: "Cases", reading: "One passed, one failed.", blocks: [{ type: "cases" }] }],
      trial: { runs: [{ arm: "a", scenario: "c1", passed: true }, { arm, scenario: "c1", passed: false }] } };
    H.equal(H.plain(V.validateSpec(spec)).map(p => `${p.level} ${p.where}: ${p.message}`), ["error trial.runs[1].arm: a trial run must name its arm"], `arm ${JSON.stringify(arm)}`);
  }
  const once = H.plain(V.validateSpec({ title: "T", sections: [{ title: "S", reading: "r", blocks: [{ type: "metric", data: { rows: [] } }] }] })).filter(p => /is not comparison data/.test(p.message));
  H.equal(once.map(p => p.where), ["sections[0].blocks[0] (metric).data"], "one problem, in the view's place");
});

test("round 21: a pairwise judgment names two different arms this trial knows, with its counts", () => {
  const story = { background: "b", intent: "i", questions: ["q"], rule: "r", covers: "c", notCovered: "n", alternatives: { a: "Setup a." }, cases: { c1: "Case 1." } };
  const spec = arms => ({ title: "Probe", story, sections: [{ title: "Pairwise", reading: "a was preferred.", blocks: [{ type: "pairwise" }] }],
    trial: { runs: [{ arm: "a", scenario: "c1", passed: true }], pairwise: { p: { ...(arms === undefined ? {} : { arms }), overall: { a_wins: 1, b_wins: 0 }, scenarios: { c1: { a_wins: 1, b_wins: 0 } } } } } });
  const said = s => H.plain(V.validateSpec(s)).map(p => `${p.level} ${p.where}: ${p.message}`);
  for (const arms of [undefined, null, [], ["a"], ["a", "a", "a"]]) {
    H.equal(said(spec(arms)), ["error trial.pairwise.p.arms: a pairwise judgment must name its two arms"], `arms ${JSON.stringify(arms)}`);
    H.excludes(V.renderReport(spec(arms)), 'data-pair="', `arms ${JSON.stringify(arms)}: no judgment drawn against invented arms`);
  }
  H.equal(said(spec(["a", "a"])), ["error trial.pairwise.p.arms: a pairwise judgment must name two different arms"], "the same arm twice");
  H.equal(said(spec(["a", "z"])), ['error trial.pairwise.p.arms[1]: "z" is not an arm of this trial'], "an arm the trial does not know");
});

// ------------------------------------------------------------------ keys that are notes

/** Each keyed map a check or a view reads, given an entry under a "$" key carrying malformed content: a "$" key is a note,
 * so the checks find exactly what they find without it and the page draws exactly what it draws without it. */
const NOTE_MAPS = (() => {
  const story = { background: "b", intent: "i", questions: ["q"], rule: "r", covers: "c", notCovered: "n", alternatives: { a: "A.", b: "B." }, cases: { c1: "C1." } };
  const trial = () => ({ plan: { arms: { a: { model: "m" }, b: { model: "m" } }, scenarios: [{ name: "c1" }] },
    runs: [{ job: "j1", arm: "a", scenario: "c1", repeat: 1, passed: true, valid: true, checks: { ok: true } }, { job: "j2", arm: "b", scenario: "c1", repeat: 1, passed: false, valid: true, checks: { ok: false } }],
    pairwise: { "a|b": { arms: ["a", "b"], overall: { a_wins: 1, b_wins: 0 }, scenarios: { c1: { a_wins: 1, b_wins: 0 } } } } });
  const trialSpec = t => ({ title: "T", story, sections: [{ title: "S", reading: "r", blocks: [{ type: "pairwise", read: { says: "p" } }, { type: "setup", read: { says: "s" } }, { type: "checks", read: { says: "c" } }, { type: "cases", read: { says: "k" } }] }], trial: t });
  const comparison = () => ({ alternatives: [{ id: "x", attributes: { Spread: "pb" } }, { id: "y" }], cases: [{ id: "c1" }],
    metrics: [{ id: "taste", kind: "ordinal", levels: ["bad", "good"], primary: true }], aggregates: [{ alternative: "x", metric: "taste", case: "c1", counts: { good: 2, bad: 1 } }, { alternative: "y", metric: "taste", case: "c1", counts: { bad: 2 } }] });
  const cStory = { ...story, alternatives: { x: "X.", y: "Y." } };
  const comparisonSpec = c => ({ title: "T", story: cStory, sections: [{ title: "S", reading: "r", blocks: [{ type: "metric", metric: "taste", read: { says: "m" } }, { type: "alternatives", read: { says: "a" } },
    { type: "decision-matrix", criteria: [{ id: "cost", label: "Cost", scores: { x: 1, y: 2 } }], read: { says: "d" } }] }], comparison: c });
  const ghost = { arms: ["ghost-a", "ghost-b"], overall: { a_wins: 1, b_wins: 0 }, scenarios: { "ghost-case": { a_wins: 1, b_wins: 0 } } };
  return {
    "pairwise judgments": [trialSpec(trial()), (() => { const t = trial(); t.pairwise.$p = ghost; return trialSpec(t); })()],
    "a judgment's counts by case": [trialSpec(trial()), (() => { const t = trial(); t.pairwise["a|b"].scenarios.$ghost = { a_wins: 9, b_wins: "x" }; return trialSpec(t); })()],
    "a plan's arms": [trialSpec(trial()), (() => { const t = trial(); t.plan.arms.$ghost = { model: { odd: true } }; return trialSpec(t); })()],
    "a run's checks": [trialSpec(trial()), (() => { const t = trial(); t.runs[0].checks.$ghost = "not a check"; t.runs[1].checks.$ghost = 7; return trialSpec(t); })()],
    "a run's usage": [trialSpec(trial()), (() => { const t = trial(); t.runs[0].usage = { $ghost: 1e9 }; const b = trial(); b.runs[0].usage = {}; return trialSpec(t); })(), (() => { const b = trial(); b.runs[0].usage = {}; return trialSpec(b); })()],
    "a total's level counts": [comparisonSpec(comparison()), (() => { const c = comparison(); c.aggregates[0].counts.$ghost = 99; return comparisonSpec(c); })()],
    "an alternative's attributes": [comparisonSpec(comparison()), (() => { const c = comparison(); c.alternatives[0].attributes.$ghost = "ghost"; return comparisonSpec(c); })()],
    "a criterion's scores": [comparisonSpec(comparison()), (() => { const s = comparisonSpec(comparison()); s.sections[0].blocks[2].criteria[0].scores.$ghost = 5; return s; })()],
    "a story's descriptions": [trialSpec(trial()), (() => { const s = trialSpec(trial()); s.story = { ...story, alternatives: { ...story.alternatives, $ghost: "Ghost." }, cases: { ...story.cases, $ghost: "Ghost case." } }; return s; })()],
  };
})();

test("sweep (a selected matrix): a key starting with $ is a note in every keyed map, read by no check and drawn by no view", () => {
  const drawn = html => html.replace(/<script[\s\S]*?<\/script>/g, "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ");
  for (const [map, [base, noted, plainBase]] of Object.entries(NOTE_MAPS)) {
    const without = plainBase || base;
    H.equal(H.plain(V.validateSpec(noted)), H.plain(V.validateSpec(without)), `${map}: the checks find what they find without the note`);
    H.equal(drawn(V.renderReport(noted)), drawn(V.renderReport(without)), `${map}: the page draws what it draws without the note`);
    H.excludes(V.renderReport(noted), "ghost", `${map}: nothing of the note is drawn`);
  }
});

test("round 22: the pairwise view draws exactly the judgments the checks accept", () => {
  const runs = [{ arm: "a", scenario: "c1", passed: true }, { arm: "b", scenario: "c1", passed: false }];
  const page = pairwise => V.renderReport({ title: "T", sections: [{ title: "S", reading: "r", blocks: [{ type: "pairwise" }] }], trial: { runs, pairwise } });
  const counts = { overall: { a_wins: 1, b_wins: 0 }, scenarios: { c1: { a_wins: 1, b_wins: 0 } } };
  H.equal((page({ ok: { arms: ["a", "b"], ...counts } }).match(/data-pair="/g) || []).length, 1, "a well-formed judgment is drawn");
  for (const [what, p] of [["unknown arms", { arms: ["ghost-a", "ghost-b"], ...counts }], ["a list for its overall counts", { arms: ["a", "b"], ...counts, overall: [] }], ["a list for its counts by case", { arms: ["a", "b"], ...counts, scenarios: [] }]]) {
    H.excludes(page({ p }), 'data-pair="', `${what}: not drawn`);
    H.ok(H.plain(V.validateSpec({ title: "T", sections: [], trial: { runs, pairwise: { p } } })).some(x => x.level === "error" && x.where.startsWith("trial.pairwise.p")), `${what}: refused by the checks`);
  }
});

test("round 23: an id starts with no $ and has no space or tab at either end, and ids are compared exactly", () => {
  const story = { background: "b", intent: "i", questions: ["q"], rule: "r", covers: "c", notCovered: "n" };
  // 1. The reviewer's trial: an arm and a case named with "$", described under those keys (which are notes).
  const noted = { title: "T", story: { ...story, alternatives: { $arm: "Arm." }, cases: { $case: "Case." } }, sections: [{ title: "S", reading: "r", blocks: [{ type: "tapestry" }] }],
    trial: { runs: [{ arm: "$arm", scenario: "$case", passed: true }] } };
  const errors = spec => H.plain(V.validateSpec(spec)).filter(p => p.level === "error").map(p => `${p.where}: ${p.message}`);
  H.ok(errors(noted).includes("trial.runs[0].arm: a trial run must name its arm") && errors(noted).includes("trial.runs[0].scenario: a trial run must name its scenario"), `the arm and case are refused: ${errors(noted).join(" | ")}`);
  H.includes(V.renderReport(noted), "av-problems--error", "and the page says so");
  // 2. The reviewer's collection: a theme declared and referenced with spaces around its id.
  const member = { id: "one", theme: " t ", trial: { runs: [{ arm: "a", scenario: "c1", passed: true }] } };
  const said = H.plain(V.validateCollection({ themes: [{ id: "t", label: "Unrelated", summary: "U." }, { id: " t ", label: "Intended", summary: "I." }], members: [member] })).filter(p => p.level === "error").map(p => p.where);
  H.ok(said.includes("collection.themes[1].id") && said.includes("collection.members[0].theme"), `the padded theme id and reference are refused: ${said.join(", ")}`);
  // Ids written exactly join exactly: the report sits under its own theme.
  const exact = V.collectionModel({ themes: [{ id: "t", label: "Its theme" }, { id: "u", label: "Other" }], members: [{ ...member, theme: "t" }] });
  H.equal(H.plain(exact.themes.map(t => [t.label, t.members.map(m => m.id)])), [["Its theme", ["one"]]], "grouped under the theme it names");
  // Keys that are ids are held to the rule too: a plan's arms, a pairwise judgment's name and its cases.
  const keyed = { runs: [{ arm: "a", scenario: "c1", passed: true }, { arm: "b", scenario: "c1", passed: false }], plan: { arms: { a: {}, " b": {} } },
    pairwise: { " p": { arms: ["a", "b"], overall: { a_wins: 1 }, scenarios: { "c1 ": { a_wins: 1 } } } } };
  const keyErrors = H.plain(V.validateSpec({ title: "T", sections: [], trial: keyed })).filter(p => p.level === "error").map(p => p.where);
  for (const at of ['trial.plan.arms[" b"]', 'trial.pairwise[" p"]', 'trial.pairwise[" p"].scenarios["c1 "]']) H.ok(keyErrors.includes(at), `${at} refused: ${keyErrors.join(", ")}`);
});

test("round 24: two names for one section's reading are refused, and composition shows the one the checks assessed", () => {
  const trial = JSON.parse(fs.readFileSync(path.join(H.VISUALS, "examples", "fictional-trial.json"), "utf8"));
  const narrative = JSON.parse(fs.readFileSync(path.join(H.VISUALS, "examples", "fictional-narrative.json"), "utf8"));
  // The reviewer's trial narrative: setup's reading, then "plan" (another name for setup) left empty.
  const told = { ...narrative, readings: { ...narrative.readings, setup: "Essential interpretation.", plan: "" } };
  const clash = H.plain(V.validateNarrative(told, trial)).filter(p => p.where === "narrative.readings.plan");
  H.ok(clash.length === 1 && clash[0].level === "error" && /"plan"/.test(clash[0].message) && /"setup"/.test(clash[0].message), `the two keys named: ${JSON.stringify(clash)}`);
  const setup = V.trialReport(trial, told).sections.find(s => s.id === "setup");
  H.equal(setup.reading, "Essential interpretation.", "composition shows the reading the checks assessed");
  H.ok(H.plain(V.validateSpec(V.trialReport(trial, told))).some(p => p.where === "narrative.readings.plan" && p.level === "error"), "the composed report carries the refusal");
  // The reviewer's comparison narrative: results's reading, then "metrics" (another name for results) left empty.
  const sandwich = JSON.parse(fs.readFileSync(path.join(H.VISUALS, "examples", "comparisons", "sandwich.json"), "utf8"));
  const sandwichTold = JSON.parse(fs.readFileSync(path.join(H.VISUALS, "examples", "comparisons", "sandwich-narrative.json"), "utf8"));
  const cTold = { ...sandwichTold, readings: { ...sandwichTold.readings, results: "Essential interpretation.", metrics: "" } };
  H.ok(H.plain(V.validateComparison(sandwich, cTold)).some(p => p.where === "narrative.readings.metrics" && p.level === "error" && /"results"/.test(p.message)), "the comparison narrative's clash is refused");
  H.equal(V.comparisonReport(sandwich, cTold).sections.find(s => s.id === "results").reading, "Essential interpretation.", "and composition shows the assessed reading");
});

test("round 24: a pairwise judgment whose name the checks refuse is not drawn", () => {
  const runs = [{ arm: "a", scenario: "c1", passed: true }, { arm: "b", scenario: "c1", passed: false }];
  const pairwise = { " p": { arms: ["a", "b"], overall: { a_wins: 1, b_wins: 0 }, scenarios: { c1: { a_wins: 1, b_wins: 0 } } } };
  H.excludes(V.renderReport({ title: "T", sections: [{ title: "S", reading: "r", blocks: [{ type: "pairwise" }] }], trial: { runs, pairwise } }), 'data-pair="', "not drawn");
});

test("sweep (a selected matrix): every other name for a section, given beside its own, is refused and composition shows the first", () => {
  // The names each report's sections answer to, as the catalog lists them.
  const read = name => JSON.parse(fs.readFileSync(path.join(H.VISUALS, "examples", ...name.split("/")), "utf8"));
  const kinds = [
    ["trial", { plan: "setup" }, read("fictional-trial.json"), read("fictional-narrative.json"), (d, n) => V.validateNarrative(n, d), (d, n) => V.trialReport(d, n)],
    ["comparison", { setup: "compared", alternatives: "compared", metrics: "results", hierarchy: "groups", preferences: "judgments", pairwise: "judgments", matrix: "decision", ledger: "observations", runs: "observations" },
      read("comparisons/sandwich.json"), read("comparisons/sandwich-narrative.json"), (d, n) => V.validateComparison(d, n), (d, n) => V.comparisonReport(d, n)],
  ];
  for (const [kind, aliases, data, narrative, check, compose] of kinds) {
    for (const [other, section] of Object.entries(aliases)) {
      for (const [first, again] of [[section, other], [other, section]]) {
        const readings = { ...narrative.readings };
        delete readings[section]; delete readings[other];
        const told = { ...narrative, readings: { ...readings, [first]: "The first reading.", [again]: "" } };
        const refused = H.plain(check(data, told)).filter(p => p.where === `narrative.readings.${again}` && p.level === "error");
        H.ok(refused.length === 1 && refused[0].message.includes(`"${first}"`) && refused[0].message.includes(`"${again}"`), `${kind} ${first} then ${again}: refused, naming both`);
        const shown = compose(data, told).sections.find(s => s.id === section);
        if (shown) H.equal(shown.reading, "The first reading.", `${kind} ${first} then ${again}: the first reading is shown`);
      }
    }
  }
});

// ------------------------------------------------------------------ blank text, one rule

/** Every required text field, given each whitespace character alone, all of them together, or visible text: the check
 * refuses it exactly when the page shows nothing of it. (test_validate.py holds report.py's checker to the same answers.) */
const WS = "\t\n\u000b\f\r \u001c\u001d\u001e\u001f\u0085\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000\ufeff";
const BLANK_VALUES = [...[...WS].map(ch => [`U+${ch.charCodeAt(0).toString(16).padStart(4, "0")}`, ch]), ["every whitespace character", WS], ["visible text", "Visible."]];
const BLANK_FIELDS = (() => {
  const read = name => JSON.parse(fs.readFileSync(path.join(H.VISUALS, "examples", ...name.split("/")), "utf8"));
  const trial = read("fictional-trial.json"), narrative = read("fictional-narrative.json");
  const sandwich = read("comparisons/sandwich.json"), sandwichTold = read("comparisons/sandwich-narrative.json");
  const arm = Object.keys(narrative.story.alternatives)[0];
  const section = (html, id) => { const at = html.indexOf(`id="${id}"`); return at < 0 ? "" : html.slice(at, html.indexOf("</section>", at)); };
  const shownReading = (html, id) => { const s = section(html, id), at = s.indexOf('class="av-section-reading"'); if (at < 0) return false; const rest = s.slice(at), end = rest.indexOf('class="av-block'); return /<p>/.test(end < 0 ? rest : rest.slice(0, end)); };
  const story = (k, v) => ({ ...narrative, story: { ...narrative.story, [k]: v } });
  const storyPart = label => html => html.includes(`<h3 class="av-story-h">${label}</h3>`);
  const trialField = (name, told, refused, shown) => [name, value => V.validateNarrative(told(value), trial), refused, value => shown(V.renderReport(V.trialReport(trial, told(value))))];
  return [
    trialField("a trial narrative's reading", v => ({ ...narrative, readings: { ...narrative.readings, setup: v } }), p => p.where === "narrative.readings" && /"setup"/.test(p.message), html => shownReading(html, "setup")),
    ["a comparison narrative's reading", v => V.validateComparison(sandwich, { ...sandwichTold, readings: { ...sandwichTold.readings, results: v } }), p => p.where === "narrative.readings" && /"results"/.test(p.message),
      v => shownReading(V.renderReport(V.comparisonReport(sandwich, { ...sandwichTold, readings: { ...sandwichTold.readings, results: v } })), "results")],
    trialField("the story's background", v => story("background", v), p => p.where === "narrative.story.background" || (p.where === "narrative.story" && /"background"/.test(p.message)), storyPart("Background")),
    trialField("the story's intent", v => story("intent", v), p => p.where === "narrative.story.intent" || (p.where === "narrative.story" && /"intent"/.test(p.message)), storyPart("What the decider wanted")),
    trialField("the story's question", v => story("questions", [v]), p => p.where.startsWith("narrative.story.questions"), storyPart("What was tested")),
    trialField("the story's rule", v => story("rule", v), p => p.where === "narrative.story.rule" || (p.where === "narrative.story" && /"rule"/.test(p.message)), storyPart("How the decision was made")),
    trialField("what the story covers", v => story("covers", v), p => p.where === "narrative.story.covers" || (p.where === "narrative.story" && /"covers"/.test(p.message)), storyPart("This report covers")),
    trialField("what the story does not cover", v => story("notCovered", v), p => p.where === "narrative.story.notCovered" || (p.where === "narrative.story" && /"notCovered"/.test(p.message)), storyPart("It does not cover")),
    trialField("an arm's description", v => story("alternatives", { ...narrative.story.alternatives, [arm]: v }), p => p.where === "narrative.story.alternatives" && p.message.includes(`"${arm}"`), html => { const at = html.indexOf('<h3 class="av-story-h">What was compared</h3>'); return at >= 0 && html.slice(at, html.indexOf("</dl>", at)).includes(`data-arm="${arm}"`); }),
    ["a text view's text", v => V.validateSpec({ title: "T", sections: [{ title: "S", reading: "r", blocks: [{ type: "text", text: v }] }] }), p => p.where.startsWith("sections[0].blocks[0]") && p.level === "error",
      v => /<p>/.test(H.element(V.renderReport({ title: "T", sections: [{ title: "S", reading: "r", blocks: [{ type: "text", text: v }] }] }), 'class="av-block av-block--text"'))],
  ];
})();

test("sweep (a selected matrix): every required text field is blank to the checks exactly when the page shows nothing of it", () => {
  for (const [field, check, refuses, shows] of BLANK_FIELDS) {
    for (const [name, value] of BLANK_VALUES) {
      const refused = H.plain(check(value)).some(p => p.level === "error" && refuses(p));
      const shown = shows(value);
      const blank = name !== "visible text";
      H.equal([refused, shown], [blank, !blank], `${field}, ${name}: refused ${refused}, shown ${shown}`);
    }
  }
});

H.report();
