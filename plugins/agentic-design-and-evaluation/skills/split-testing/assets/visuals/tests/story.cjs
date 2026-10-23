// Every report tells its whole story: the checkers refuse a trial, comparison,
// specification or collection that leaves out what a reader new to the work
// needs, and the page opens with the story and reads every view. Expected
// problems are written out by hand.
"use strict";
const fs = require("node:fs");
const path = require("node:path");
const H = require("./harness.cjs");
const F = require("./fixtures.cjs");
const { test } = H;

const V = H.loadVisuals();
const read = name => JSON.parse(fs.readFileSync(path.join(H.VISUALS, "examples", name), "utf8"));
const lines = problems => H.plain(problems).map(p => `${p.level} ${p.where}: ${p.message}`);
const trial = F.gridTrial({ fast: { quick: "PPF", slow: "PF" }, careful: { quick: "PPP", slow: "PP" } });
const STORY = {
  background: "Two ways of answering a support ticket: **fast** replies at once, **careful** checks the account first.",
  intent: "The support lead wanted fewer wrong answers without slower replies.",
  questions: ["Does checking the account first give more right answers?"],
  rule: "Choose careful if it answers right more often on both kinds of ticket.",
  covers: "Two kinds of ticket, a few runs each.",
  notCovered: "Real tickets, cost and speed.",
  alternatives: { fast: "Replies at once from the ticket alone.", careful: "Looks the account up before replying." },
  cases: { quick: "A ticket answered in one line, to see whether checking slows the easy ones.", slow: "A ticket that needs the account, where checking should help." },
};
const READINGS = { setup: "Only the instruction differs.", arms: "Careful passed 5 of 5, fast 3 of 5.", cases: "Careful passed every run on both tickets.", failures: "Fast failed once on each ticket.", runs: "All ten runs." };

test("a trial narrative without its story is refused, part by part", () => {
  H.equal(lines(V.validateNarrative({}, trial)), [
    'error narrative: missing "story", which tells a reader new to this work what it is about',
    'error narrative.readings: no reading for the "setup" section',
    'error narrative.readings: no reading for the "arms" section',
    'error narrative.readings: no reading for the "cases" section',
    'error narrative.readings: no reading for the "failures" section',
    'error narrative.readings: no reading for the "runs" section',
  ], "nothing told");
  H.equal(lines(V.validateNarrative({ story: { background: "b" }, readings: READINGS }, trial)), [
    'error narrative.story: missing required field "intent"',
    'error narrative.story: missing required field "questions"',
    'error narrative.story: missing required field "covers"',
    'error narrative.story: missing required field "notCovered"',
    'error narrative.story: missing "rule": how the decision was to be made, in plain words',
    'error narrative.story.alternatives: does not describe arm "fast"',
    'error narrative.story.alternatives: does not describe arm "careful"',
    'error narrative.story.cases: does not describe case "quick"',
    'error narrative.story.cases: does not describe case "slow"',
  ], "a story with only its background");
  H.equal(lines(V.validateNarrative({ story: STORY, readings: READINGS }, trial)), [], "the whole story");
});

test("a reference to a file the reader cannot open is refused wherever the story or a reading says it", () => {
  const story = { ...STORY, rule: "Fixed before results: see ../README.md (Decision rule).", cases: { ...STORY.cases, slow: "As described in runs/slow/notes.txt." } };
  H.equal(lines(V.validateNarrative({ story, readings: { ...READINGS, cases: "See analysis.md." }, decision: { verdict: "adopt", headline: "Careful, per plan.md." } }, trial)), [
    'error narrative.story.rule: points the reader at "../README.md", which this report does not include',
    'error narrative.story.cases.slow: points the reader at "runs/slow/notes.txt", which this report does not include',
    'error narrative.readings.cases: points the reader at "analysis.md", which this report does not include',
    'error narrative.decision.headline: points the reader at "plan.md", which this report does not include',
  ], "four references");
  H.equal(lines(V.validateNarrative({ story: { ...STORY, background: "Uses gather.py and trial.py, 29/29 runs, https://example.com/a.md." }, readings: READINGS }, trial)), [], "script names, counts and links are not file references");
  // Naming a document as the subject is not pointing the reader at it; a path, or "see"/"in"/"per" a document, is.
  H.equal(lines(V.validateNarrative({ story: { ...STORY, background: "We compared README.md with guide.md; both texts are reproduced in the report below." }, readings: READINGS }, trial)), [], "a document named as the subject");
  H.equal(lines(V.validateNarrative({ story: { ...STORY, background: "The rule is set out in /home/someone/plan.md and in SPEC.md." }, readings: READINGS }, trial)), [
    'error narrative.story.background: points the reader at "/home/someone/plan.md", which this report does not include',
  ], "an absolute path the reader is sent to");
});

test("a decision rule the plan only points at is shown as the narrative states it, and refused when it states none", () => {
  const pointed = { ...trial, plan: { ...trial.plan, decision_rule: "Fixed before results: see ../README.md (Decision rule)" } };
  const { rule, ...unruled } = STORY;
  H.equal(lines(V.validateNarrative({ story: unruled, readings: READINGS, decision: { verdict: "adopt", headline: "Careful." } }, pointed)).filter(l => /rule/.test(l)), [
    'error narrative.story: missing "rule": how the decision was to be made, in plain words',
    'error narrative.story.rule: the plan\'s decision rule points the reader at "../README.md", which this report does not include, so the narrative states the rule',
  ], "a pointer with no rule stated");
  const html = V.renderReport(V.trialReport(pointed, { story: STORY, readings: READINGS, decision: { verdict: "adopt", headline: "Careful." } }));
  const verdict = H.element(html, 'class="av-block av-block--verdict"');
  H.includes(verdict, STORY.rule, "the rule as the narrative states it");
  H.excludes(html, "../README.md", "the plan's pointer anywhere on the page");
});

test("a specification's verdict rule cannot point at a file either", () => {
  const spec = { title: "S", story: { background: "b", intent: "i", questions: ["q"], rule: "r", covers: "c", notCovered: "n" },
    sections: [{ title: "Verdict", blocks: [{ type: "verdict", verdict: "adopt", headline: "Yes.", rule: "As in docs/rule.md." }] }] };
  H.equal(lines(V.validateSpec(spec)), ['error sections[0].blocks[0].rule: points the reader at "docs/rule.md", which this report does not include'], "the verdict's rule");
});

test("a comparison narrative names every alternative and reads every section it shows", () => {
  const sandwich = read("comparisons/sandwich.json"), told = read("comparisons/sandwich-narrative.json");
  H.equal(lines(V.validateComparison(sandwich, told)), [], "the sandwich example tells its whole story");
  const { story, readings, ...rest } = told;
  H.equal(lines(V.validateComparison(sandwich, { ...rest, story: { ...story, alternatives: { pb: story.alternatives.pb, ham: "Ham and tuna." } }, readings: { ...readings, judgments: "" } })), [
    'error narrative.story.alternatives: does not describe alternative "jelly"',
    'error narrative.readings: no reading for the "judgments" section',
    'warning narrative.story.alternatives.ham: "ham" is not an alternative in this report, so this description is not used',
  ], "a missing alternative, an extra one and an empty reading");
});

test("a specification of any blocks tells its story and reads each section that holds a view", () => {
  const spec = { title: "T", sections: [{ title: "Words", blocks: [{ type: "text", text: "x" }] }, { title: "Numbers", blocks: [{ type: "bars", segments: [{ id: "s", label: "S" }], rows: [{ label: "r", values: { s: 1 } }] }] }] };
  H.equal(lines(V.validateSpec(spec)), [
    'error spec: missing "story", which tells a reader new to this work what it is about',
    "error sections[1]: says nothing about what its views show for this data",
  ], "no story, and a view nobody reads");
  const { rule, alternatives, cases, ...plain } = STORY;
  H.equal(lines(V.validateSpec({ ...spec, story: plain, sections: [spec.sections[0], { ...spec.sections[1], reading: "One bar of one." }] })), [], "a section reading");
  const viewSays = { ...spec, story: plain, sections: [spec.sections[0], { ...spec.sections[1], blocks: [{ ...spec.sections[1].blocks[0], read: { says: "One bar of one." } }] }] };
  H.equal(lines(V.validateSpec(viewSays)), [], "or each view's own reading");
  H.equal(lines(V.validateSpec({ ...viewSays, sections: [...viewSays.sections, { title: "D", blocks: [{ type: "verdict", headline: "h" }] }] })), ['error story: missing "rule": how the decision was to be made, in plain words'], "a decision needs its rule");
});

test("a collection tells the story of the whole and of each theme", () => {
  const collection = { themes: [{ id: "t", label: "T" }], members: [{ id: "one", theme: "t", trial, narrative: { story: STORY, readings: READINGS } }] };
  H.equal(lines(V.validateCollection(collection)), [
    'error collection.themes[0]: theme "t" has no summary',
    'error collection: missing "story", which tells a reader new to this work what it is about',
    'error collection.readings: no reading for the "glance" section',
    'error collection.readings: no reading for the "reports" section',
    'error collection.readings: no reading for the "shifts" section',
  ], "an untold collection");
  const told = { ...collection, story: { background: "b", intent: "i", questions: ["q"], covers: "c", notCovered: "n" }, readings: { glance: "g", reports: "r", shifts: "s" }, themes: [{ id: "t", label: "T", summary: "Why these reports belong together." }] };
  H.equal(lines(V.validateCollection(told)), [], "a told collection");
});

test("the story opens the page, each section's reading follows its title, and every view says how to read it", () => {
  const html = V.renderReport(V.trialReport(trial, { title: "Tickets", story: STORY, readings: READINGS, decision: { verdict: "adopt", headline: "Use careful." } }));
  H.equal(H.sectionIds(html)[0], "story", "the story first");
  for (const part of ["Background", "What the decider wanted", "What was tested", "What was compared", "The cases", "How the decision was made", "This report covers", "It does not cover"]) H.includes(html, `<h3 class="av-story-h">${part}</h3>`, part);
  H.includes(html, "Looks the account up before replying.", "an alternative in plain words");
  H.includes(html, '<span class="av-read-tag">What this shows</span><div class="av-read-prose"><p>Careful passed 5 of 5, fast 3 of 5.</p>', "the arms section's reading");
  H.includes(html, "How often each setup passed: on one case with the range its true pass rate likely falls in, over several cases as plain counts.", "the ladder's own words");
  const labelled = V.renderReport(V.trialReport(trial, { story: STORY, readings: READINGS, decision: { verdict: "adopt", headline: "h", conditions: ["c"], limits: ["l"], changes: ["x"] } }));
  for (const h of ["The decision holds when", "What this evidence does not show", "What would change the decision"]) H.includes(labelled, `<h4>${h}</h4>`, `the verdict's list "${h}"`);
  H.excludes(labelled, "<h4>Holds when</h4>", "the old label");
});

test("a view's own reading replaces the library's words where given, and says what this data shows", () => {
  const html = V.renderBlock({ type: "bars", segments: [{ id: "s", label: "S" }], rows: [{ label: "r", values: { s: 1 } }], read: { shows: "Own shows.", says: "It says **this**." } }, V.createContext({}));
  H.includes(html, "Own shows."); H.excludes(html, "How each item's total is made up.", "the library's words");
  H.includes(html, "It says <strong>this</strong>.", "the data's reading");
  H.includes(html, "Each bar is one item split into parts in proportion", "the library's how-to-read, kept");
});

test("story and reading text stays text", () => {
  const hostile = { ...STORY, background: F.hostile("background"), intent: F.hostile("intent"), questions: [F.hostile("question")], alternatives: { fast: F.hostile("alt"), careful: "c" }, glossary: [{ term: F.hostile("term"), meaning: F.hostile("meaning") }] };
  const html = V.renderReport(V.trialReport(trial, { story: hostile, readings: { ...READINGS, arms: F.hostile("reading") } }));
  H.equal(F.rawHostileFields(html), [], "raw markup");
  for (const f of ["background", "intent", "question", "alt", "term", "meaning", "reading"]) H.includes(html, F.escapedHostile(f), f);
});

test("every view keeps its own reading, and an intervals chart reads as values, not pass rates", () => {
  const spec = {
    title: "Views", trial,
    sections: [{ title: "Rates", blocks: [
      { type: "ladder", read: { says: "Only two of three passed." } },
      { type: "diagram", source: "flowchart LR\n  a --> b", read: { says: "The ticket goes to the account first." } },
      { type: "intervals", id: "commute", title: "Commute", rows: [{ label: "Bus", value: 41, lo: 37, hi: 45 }, { label: "Bike", value: 33, lo: 30, hi: 36 }], unit: "min", read: { says: "The bike is about eight minutes quicker." } },
    ] }],
  };
  const html = V.renderReport(spec);
  H.includes(html, "Only two of three passed.", "the ladder's own reading");
  H.includes(html, "The ticket goes to the account first.", "the diagram's own reading");
  const box = H.element(html, 'id="commute"');
  H.includes(box, "Values with the range each likely falls in", "the intervals chart's own explanation");
  H.excludes(box, "How often each setup passed", "a pass-rate explanation on a chart of durations");
});

test("a specification cannot declare itself checked", () => {
  // A results view, no story and no reading: a "problems" field of its own changes nothing.
  const spec = { title: "Claimed", problems: [], sections: [{ title: "Results", blocks: [{ type: "intervals", rows: [{ label: "A", value: 3, lo: 2, hi: 4 }, { label: "B", value: 5, lo: 4, hi: 6 }] }] }] };
  H.equal(lines(V.validateSpec(spec)), [
    'error spec: missing "story", which tells a reader new to this work what it is about',
    "error sections[0]: says nothing about what its views show for this data",
  ], "the checks run as on any specification");
});

test("two reports set side by side tell the story of the pairing", () => {
  const narrated = { title: "Tickets", question: "Fast or careful?", decision: { verdict: "adopt", headline: "Careful." }, story: STORY, readings: READINGS };
  const data = { title: "Pair", members: [{ id: "one", label: "One", trial, narrative: narrated }, { id: "two", label: "Two", trial, narrative: narrated }],
    story: { background: "Two runs of one ticket trial.", intent: "To see whether it repeats.", questions: ["Does it?"], covers: "Both runs.", notCovered: "Other trials." },
    readings: { glance: "Two adopted.", reports: "Both reports.", shifts: "No shift." } };
  const spec = V.compareReport(data, "one", "two");
  H.equal(lines(V.validateSpec(spec)), [], "the side-by-side page passes the checks every specification meets");
  H.includes(V.renderReport(spec), "What this is about", "it opens with its story");
});

test("a story whose parts are empty or blank is refused, whatever the report", () => {
  const hollow = { ...STORY, background: [], intent: [""], questions: ["", "Does checking help?"], covers: [], notCovered: ["  "] };
  const expected = at => [
    `error ${at}story.background: says nothing`,
    `error ${at}story.intent: says nothing`,
    `error ${at}story.questions[0]: is blank`,
    `error ${at}story.covers: says nothing`,
    `error ${at}story.notCovered: says nothing`,
  ];
  H.equal(lines(V.validateNarrative({ story: hollow, readings: READINGS }, trial)).filter(l => /story\./.test(l)), expected("narrative."), "a trial narrative");
  const spec = { title: "S", story: hollow, sections: [{ title: "T", blocks: [{ type: "text", text: "x" }] }] };
  H.equal(lines(V.validateSpec(spec)).filter(l => /story\./.test(l)), expected(""), "a specification");
});

test("a specification describes the alternatives and cases its blocks' own data compare", () => {
  const local = { alternatives: [{ id: "pbj", label: "Peanut butter and jelly" }, { id: "ham", label: "Ham" }],
    cases: [{ id: "hungry", label: "Hungry" }, { id: "after-exercise", label: "After exercise" }],
    metrics: [{ id: "taste", label: "Taste", kind: "numeric", better: "higher" }],
    observations: [["pbj", "hungry", 8], ["ham", "hungry", 6], ["pbj", "after-exercise", 7], ["ham", "after-exercise", 9]].map(([alternative, c, value]) => ({ alternative, case: c, metric: "taste", value })) };
  const story = { background: "Two sandwiches.", intent: "Pick lunch.", questions: ["Which tastes better?"], covers: "Two moments.", notCovered: "Price." };
  const spec = { title: "Lunch", story, sections: [{ title: "Taste", reading: "Peanut butter wins when hungry.", blocks: [{ type: "metric", data: local, metric: "taste" }] }] };
  H.equal(lines(V.validateSpec(spec)), [
    'error story.alternatives: does not describe alternative "pbj"',
    'error story.alternatives: does not describe alternative "ham"',
    'error story.cases: does not describe case "hungry"',
    'error story.cases: does not describe case "after-exercise"',
  ], "the block's own alternatives and cases need describing");
});

test("every section and view the composition draws needs its reading, opt-in and appended ones included", () => {
  const checked = F.gridTrial({ fast: { quick: "PPF", slow: "PF" }, careful: { quick: "PPP", slow: "PP" } }, run => ({ checks: { reply_ok: run.passed === true } }));
  const view = { type: "intervals", rows: [{ label: "Fast", value: 0.6, lo: 0.3, hi: 0.9 }] };
  const narrative = { story: STORY, readings: READINGS, include: ["setup", "arms", "cases", "grid", "checks", "failures", "runs"], append: { arms: [view] } };
  H.equal(lines(V.validateNarrative(narrative, checked)), [
    'error narrative.readings: no reading for the "grid" section',
    'error narrative.readings: no reading for the "checks" section',
    'error narrative.append.arms[0]: says nothing about what this view shows for this data',
  ], "the opt-in sections and the appended view");
  // In a section of two views, one reading cannot stand for both: each view says what it shows.
  const spec = { title: "S", story: { background: "b", intent: "i", questions: ["q"], covers: "c", notCovered: "n" },
    sections: [{ title: "Two views", reading: "The bus is slower.", blocks: [view, { ...view, read: { says: "Fast sits at 60%." } }, view] }] };
  H.equal(lines(V.validateSpec(spec)), [
    "error sections[0].blocks[0]: says nothing about what this view shows for this data",
    "error sections[0].blocks[2]: says nothing about what this view shows for this data",
  ], "views without their own reading in a section of three");
});

test("a collection reads its timeline whenever two reports are dated, and its cost view whenever it is drawn", () => {
  const dated = (id, date) => ({ id, label: id, date, trial: F.gridTrial({ a: { c: "PP" }, b: { c: "PF" } }), narrative: { decision: { verdict: "adopt", headline: "H." }, story: STORY } });
  const data = { title: "C", story: { background: "b", intent: "i", questions: ["q"], covers: "c", notCovered: "n" }, readings: { glance: "g", reports: "r", shifts: "s" },
    members: [dated("one", "2026-10-15"), dated("two", "2026-10-16")] };
  H.equal(lines(V.validateCollection(data)).filter(l => /collection\.readings/.test(l)), ['error collection.readings: no reading for the "timeline" section'], "two dated reports");
  const costly = F.gridTrial({ a: { c: "PP" }, b: { c: "PF" } }, run => ({ usage: { cost_usd: 0.1 } }));
  costly.baseline = "a"; costly.pct_vs_baseline = { b: { cost_usd: { median: 0.2, mean: 0.2, n_scenarios: 1 } } };
  const priced = { ...data, members: [{ id: "one", label: "one", trial: costly, narrative: { decision: { verdict: "adopt", headline: "H." }, baseline: "a", story: STORY } }] };
  H.equal(lines(V.validateCollection(priced)).filter(l => /collection\.readings/.test(l)), ['error collection.readings: no reading for the "cost-gain" section'], "a change with its cost");
});

test("a case's dossier gives the narrative's plain description in place of the scenario file's notes", () => {
  const noted = { ...trial, plan: { ...trial.plan, scenarios: trial.plan.scenarios.map(s => ({ ...s, description: "Checks run per qualify/README.md." })) } };
  const told = H.element(V.renderReport(V.trialReport(noted, { story: STORY, readings: READINGS })), 'class="av-block av-block--cases"');
  H.includes(told, STORY.cases.quick, "the plain description");
  H.excludes(told, "qualify/README.md", "the notes' pointer to a file the report does not hold");
  H.includes(H.element(V.renderReport(V.trialReport(noted)), 'class="av-block av-block--cases"'), "qualify/README.md", "without a narrative, the scenario's own notes");
});

test("a hand-made specification describes the arms and cases it names for its views", () => {
  // No trial or comparison data: the specification's own arms and cases are what its views name.
  const story = { background: "Two sandwiches.", intent: "Pick lunch.", questions: ["Which tastes better?"], covers: "Two moments.", notCovered: "Price.", alternatives: { pbj: "Peanut butter and jelly." } };
  const spec = { title: "Lunch", story, arms: [{ id: "pbj", label: "PB&J" }, { id: "ham", label: "Ham" }], cases: { hungry: "Hungry" },
    sections: [{ title: "Taste", reading: "PB&J wins.", blocks: [{ type: "bars", segments: [{ id: "good", label: "good" }], rows: [{ label: "PB&J", arm: "pbj", values: { good: 3 } }, { label: "Ham", arm: "ham", values: { good: 2 } }] }] }] };
  H.equal(lines(V.validateSpec(spec)), [
    'error story.alternatives: does not describe alternative "ham"',
    'error story.cases: does not describe case "hungry"',
  ], "the named arm and case without a description");
});

test("a story's required parts must be words: a number says nothing", () => {
  // The reviewer's specification: every part a number, which the page drew as "0" or not at all.
  const spec = { title: "Numeric story", story: { background: 0, intent: 0, questions: [0], covers: 0, notCovered: 0 },
    sections: [{ title: "Observed", reading: "Three support tickets passed.", blocks: [{ type: "intervals", rows: [{ label: "Lookup", value: 3, lo: 2, hi: 4 }] }] }] };
  H.equal(lines(V.validateSpec(spec)), [
    "error story.background: says nothing",
    "error story.intent: says nothing",
    "error story.questions[0]: is blank",
    "error story.covers: says nothing",
    "error story.notCovered: says nothing",
  ], "each numeric part");
});

test("the story describes every alternative and case the report draws, from every source of data", () => {
  // A comparison of x and y on cases u and v, carried by a block of its own.
  const local = { alternatives: [{ id: "x" }, { id: "y" }], metrics: [{ id: "m", kind: "numeric" }],
    observations: [["x", "u", 1], ["y", "u", 2], ["x", "v", 3], ["y", "v", 4]].map(([alternative, c, value]) => ({ alternative, case: c, metric: "m", value })) };
  const view = { type: "metric", data: local, metric: "m", read: { says: "Y is higher." } };
  const missing = at => [
    `error ${at}story.alternatives: does not describe alternative "x"`,
    `error ${at}story.alternatives: does not describe alternative "y"`,
    `error ${at}story.cases: does not describe case "u"`,
    `error ${at}story.cases: does not describe case "v"`,
  ];
  const told = { story: STORY, readings: READINGS };
  H.equal(lines(V.validateNarrative({ ...told, sections: [{ title: "Extra", blocks: [view] }] }, trial)), missing("narrative."), "an extra section's own comparison");
  H.equal(lines(V.validateNarrative({ ...told, append: { verdict: [view] } }, trial)), missing("narrative."), "an appended view's own comparison");
  // A specification with a trial and a comparison: the story describes both.
  const both = { title: "Both", trial, comparison: local, story: STORY, sections: [{ title: "Views", reading: "R.", blocks: [{ type: "metric", metric: "m", read: { says: "S." } }] }] };
  H.equal(lines(V.validateSpec(both)).filter(l => /story\./.test(l)), missing(""), "a comparison beside the trial");
  // Rows written by hand name arms that no data declares: those need describing too.
  const ladder = { title: "Hand", story: { background: "b", intent: "i", questions: ["q"], rule: "r", covers: "c", notCovered: "n" },
    sections: [{ title: "Rates", reading: "R.", blocks: [{ type: "ladder", rows: [{ arm: "x", k: 2, n: 3 }, { arm: "y", k: 1, n: 3 }] }] }] };
  H.equal(lines(V.validateSpec(ladder)), [
    'error story.alternatives: does not describe alternative "x"',
    'error story.alternatives: does not describe alternative "y"',
  ], "a hand-written ladder's arms");
});

test("a comparison's cases are those its data name, declared or not, and their view needs its reading", () => {
  const data = { alternatives: [{ id: "x" }, { id: "y" }], metrics: [{ id: "m", kind: "numeric" }],
    observations: [["x", "u", 1], ["y", "u", 2], ["x", "v", 3], ["y", "v", 4]].map(([alternative, c, value]) => ({ alternative, case: c, metric: "m", value })) };
  const narrative = { story: { background: "b", intent: "i", questions: ["q"], rule: "r", covers: "c", notCovered: "n", alternatives: { x: "X.", y: "Y." } },
    readings: { compared: "c", results: "r", differences: "d", observations: "o" } };
  H.equal(lines(V.validateComparison(data, narrative)), [
    'error narrative.story.cases: does not describe case "u"',
    'error narrative.story.cases: does not describe case "v"',
    'error narrative.readings: no reading for the "cases" section',
  ], "cases taken from the observations");
  H.ok(V.comparisonReport(data, narrative).sections.some(s => s.id === "cases"), "the composition does draw the cases section");
});

test("a diagram is a view: it needs a reading too", () => {
  const spec = { title: "Flow", story: { background: "b", intent: "i", questions: ["q"], covers: "c", notCovered: "n" },
    sections: [{ title: "How it flows", blocks: [{ type: "diagram", source: "flowchart LR\n A --> B" }] }] };
  H.equal(lines(V.validateSpec(spec)), ["error sections[0]: says nothing about what its views show for this data"], "a diagram with no reading");
});

test("a one-arm trial with a case and its variant reads its variant comparison", () => {
  // One arm, a case and the same prompt with one more turn: the composition draws "Variants against base cases".
  const variant = F.gridTrial({ only: { base: "PPF", more: "PFF" } });
  variant.plan.scenarios = [{ name: "base", prompt: "Do it.", followups: [], required: [] }, { name: "more", prompt: "Do it.", followups: ["Again."], required: [] }];
  const told = { story: { background: "b", intent: "i", questions: ["q"], rule: "r", covers: "c", notCovered: "n", alternatives: { only: "O." }, cases: { base: "B.", more: "M." } },
    readings: { setup: "s", cases: "c", failures: "f", runs: "r" } };
  H.ok(V.trialReport(variant, told).sections.some(s => s.id === "arms"), "the variant section is drawn");
  H.equal(lines(V.validateNarrative(told, variant)), ['error narrative.readings: no reading for the "arms" section'], "its reading");
});

test("naming a file as the subject is not a pointer; sending the reader to one is", () => {
  const ok = text => H.equal(lines(V.validateNarrative({ story: { ...STORY, background: text }, readings: READINGS }, trial)), [], text);
  ok("We compared docs/README.md with docs/guide.md; both are reproduced below.");
  ok("We found a typo in README.md; both old and new texts are reproduced below.");
  H.equal(lines(V.validateNarrative({ story: { ...STORY, background: "The rule is written in /home/someone/plan.md." }, readings: READINGS }, trial)), [
    'error narrative.story.background: points the reader at "/home/someone/plan.md", which this report does not include',
  ], "a sentence that sends the reader to a file");
});

test("a decision matrix's own alternatives need describing, listed or named only by its cells", () => {
  const plain = { background: "b", intent: "i", questions: ["q"], rule: "r", covers: "c", notCovered: "n" };
  // The reviewer's section: a matrix that lists Procedure X and Procedure Y, with no story.alternatives.
  const matrix = { type: "decision-matrix", alternatives: [{ id: "x", label: "Procedure X" }, { id: "y", label: "Procedure Y" }], criteria: [{ id: "quality", label: "Quality", scores: { x: 5, y: 3 } }] };
  const section = { title: "Choose", reading: "Procedure X has the higher rating.", blocks: [matrix] };
  const missingXY = at => [`error ${at}story.alternatives: does not describe alternative "x"`, `error ${at}story.alternatives: does not describe alternative "y"`];
  H.equal(lines(V.validateSpec({ title: "Pick", story: plain, sections: [section] })), missingXY(""), "in a specification");
  H.equal(lines(V.validateNarrative({ story: STORY, readings: READINGS, sections: [section] }, trial)), missingXY("narrative."), "in a trial narrative's extra section");
  // With no list, the matrix draws the alternatives its cells name; scores alone add none.
  const cells = { type: "decision-matrix", criteria: [{ id: "quality", scores: { z: 1 } }], cells: [{ criterion: "quality", alternative: "p", rating: "4" }, { criterion: "quality", alternative: "q", rating: "2" }] };
  H.equal(lines(V.validateSpec({ title: "Pick", story: plain, sections: [{ title: "Choose", reading: "P rates higher.", blocks: [cells] }] })), [
    'error story.alternatives: does not describe alternative "p"',
    'error story.alternatives: does not describe alternative "q"',
  ], "alternatives inferred from cells");
});

test("cases a trial's pairwise judgments name need describing, even when no run names them, and its arms must be the trial's", () => {
  // The reviewer's probe: pairwise data introducing a case absent from the run list. Its arms are the trial's own.
  const odd = { ...trial, pairwise: { fast__careful: { arms: ["fast", "careful"], overall: { a_wins: 1, b_wins: 0, tie: 0 }, scenarios: { quick: { a_wins: 1 }, nowhere: { b_wins: 0 } } } } };
  H.equal(lines(V.validateNarrative({ story: STORY, readings: { ...READINGS, pairwise: "Fast won its one pair." } }, odd)), [
    'error narrative.story.cases: does not describe case "nowhere"',
  ], "the pairwise case");
  // An arm no run ran and the plan does not list is refused, not described: the judgment is not drawn.
  const ghost = { ...trial, pairwise: { fast__ghost: { arms: ["fast", "ghost"], overall: { a_wins: 1, b_wins: 0, tie: 0 }, scenarios: { quick: { a_wins: 1 } } } } };
  H.equal(lines(V.validateNarrative({ story: STORY, readings: { ...READINGS, pairwise: "Fast won its one pair." } }, ghost)), [
    'error trial.pairwise.fast__ghost.arms[1]: "ghost" is not an arm of this trial',
  ], "the arm the trial does not know");
});

test("an empty override of what a view shows or how to read it keeps the library's words", () => {
  // The reviewer's block: shows and how given as empty text.
  const block = { type: "intervals", independent: true, rows: [{ label: "Observed", k: 3, n: 6 }], read: { shows: "", how: "", says: "Three tickets passed out of six." } };
  const html = H.element(V.renderReport({ title: "R", sections: [{ title: "S", blocks: [block] }] }), 'class="av-block av-block--ladder"');
  H.includes(html, "This view", "what the view shows");
  H.includes(html, "How to read it", "how to read it");
  H.includes(html, "Three tickets passed out of six.", "what this data says");
  const blank = H.element(V.renderReport({ title: "R", sections: [{ title: "S", blocks: [{ ...block, read: { shows: ["  "], how: [], says: "S." } }] }] }), 'class="av-block av-block--ladder"');
  H.includes(blank, "This view", "a blank list keeps it too");
  H.includes(blank, "How to read it", "and an empty one");
});

test("a collection reads its shifts whenever a member's specification carries a comparison", () => {
  // 6. The reviewer's collection: one member, a specification made of the sandwich comparison, readings for glance and reports only.
  const sandwich = read("comparisons/sandwich.json");
  const spec = { title: "Lunch", comparison: sandwich, story: { background: "b", intent: "i", questions: ["q"], covers: "c", notCovered: "n", alternatives: Object.fromEntries(sandwich.alternatives.map(a => [a.id, "A."])), cases: Object.fromEntries((sandwich.cases || []).map(c => [c.id, "C."])) },
    sections: [{ title: "Taste", reading: "R.", blocks: [{ type: "scorecard" }] }] };
  const data = { story: { background: "b", intent: "i", questions: ["q"], covers: "c", notCovered: "n" }, readings: { glance: "g", reports: "r" }, members: [{ id: "lunch", spec }] };
  H.equal(lines(V.validateCollection(data)).filter(l => /collection\.readings/.test(l)), ['error collection.readings: no reading for the "shifts" section'], "the shifts section it draws");
  H.ok(V.collectionReport(data).sections.some(sec => sec.id === "shifts"), "which the composition does draw");
});

H.report();
