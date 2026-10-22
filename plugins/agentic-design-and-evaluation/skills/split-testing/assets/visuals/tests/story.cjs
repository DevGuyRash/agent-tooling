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

H.report();
