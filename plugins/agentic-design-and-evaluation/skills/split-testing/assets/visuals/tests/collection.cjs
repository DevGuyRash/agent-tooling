// A collection of reports: its composition, the index views and their designs,
// the cross-report views and two reports side by side, each drawn from the
// members' own data with the members' own arm identities. Expected rates and
// intervals are worked out by hand (Wilson for 3 of 4 is 30%–95%, for 1 of 4
// 5%–70%; Newcombe for 1 of 4 minus 3 of 4 is −79 to +14 points).
"use strict";
const fs = require("node:fs");
const path = require("node:path");
const H = require("./harness.cjs");
const F = require("./fixtures.cjs");
const { test } = H;

const V = H.loadVisuals();
const read = name => JSON.parse(fs.readFileSync(path.join(H.VISUALS, "examples", name), "utf8"));

/** A two-arm trial on one model: by default the reference passes 3 of 4, the candidate 1 of 4. */
function pairTrial(ids, model, cost, marks = ["PPPF", "PFFF"]) {
  const [ref, cand] = ids;
  const data = F.gridTrial({ [ref]: { c1: marks[0] }, [cand]: { c1: marks[1] } }, run => ({ usage: { cost_usd: run.arm === ref ? cost : cost * 1.2 } }));
  data.name = `${ref}-trial`;
  data.plan.arms[ref].model = model; data.plan.arms[cand].model = model;
  data.baseline = ref;
  data.ran = { first: "2026-10-15T19:00:00Z", last: "2026-10-15T19:30:00Z" };
  data.pct_vs_baseline = { [cand]: { cost_usd: { median: 0.2, mean: 0.2, n_scenarios: 1 } } };
  return data;
}
const narrative = (ids, verdict, extra = {}) => ({
  title: `Question ${ids[0]}`, question: `Does ${ids[1]} beat ${ids[0]}?`,
  decision: { verdict, headline: `Decision for ${ids[0]}.` }, baseline: ids[0],
  arms: [{ id: ids[0], label: "Reference text" }, { id: ids[1], label: "Candidate text" }], ...extra,
});
function collection() {
  return {
    title: "Collected", summary: "Every report.",
    themes: [{ id: "t1", label: "Theme one", summary: "Story one." }, { id: "t2", label: "Theme two" }],
    members: [
      { id: "alpha", theme: "t1", label: "Alpha", trial: pairTrial(["ref-gpt", "new-gpt"], "model-g", 0.1), narrative: narrative(["ref-gpt", "new-gpt"], "adopt") },
      { id: "beta", theme: "t1", label: "Beta", follows: "alpha", date: "2026-10-16", trial: pairTrial(["ref-cl", "new-cl"], "model-c", 0.2), narrative: narrative(["ref-cl", "new-cl"], "reject", { arms: [{ id: "ref-cl", label: "Old wording" }, { id: "new-cl", label: "New wording" }] }) },
      { id: "sandwich", theme: "t2", date: "2026-10-17", comparison: read("comparisons/sandwich.json"), narrative: read("comparisons/sandwich-narrative.json") },
    ],
    pairs: [{ a: "alpha", b: "beta", title: "Same question, two families" }],
  };
}
const ctxOf = data => V.createContext({ collection: data });
const render = (block, data = collection()) => V.renderBlock(block, ctxOf(data));
const text = html => html.replace(/<[^>]+>/g, " ").replace(/&amp;/g, "&").replace(/&#39;/g, "'").replace(/\s+/g, " ");

// ------------------------------------------------------------------ composition

test("the collection composition opens with the glance and the index, then the cross-report views that have content", () => {
  const data = collection();
  const spec = V.collectionReport(data);
  H.equal(H.plain(spec.sections.map(s => s.id)), ["glance", "reports", "shifts", "cost-gain", "timeline", "matchups"], "section ids");
  H.equal(H.plain(V.COLLECTION_SECTION_IDS), ["glance", "reports", "shifts", "cost-gain", "timeline", "matchups"], "every section id");
  const figures = H.plain(spec.sections[0].blocks[0].items);
  H.equal(figures.find(f => f.label === "reports"), { value: 3, label: "reports", note: "2 trials, 1 comparison" }, "the reports figure");
  H.equal(figures.find(f => f.label === "trial runs"), { value: 16, label: "trial runs", note: "16 valid, 0 invalid; the other reports hold 16 observations, 4 judgments" }, "trial runs, and the comparison's evidence by kind");
  H.equal([figures.find(f => f.label === "adopted").value, figures.find(f => f.label === "not adopted").value], [2, 1], "decisions");
  H.ok(spec.collection === data, "the spec carries the very collection it was composed from");
  H.equal(spec.title, "Collected", "its title");
});

test("a member's full report is the composition its standalone file draws", () => {
  const data = collection();
  H.equal(H.plain(V.memberReport(data, "alpha")), H.plain(V.trialReport(data.members[0].trial, data.members[0].narrative)), "trial member");
  H.equal(H.plain(V.memberReport(data, "sandwich")), H.plain(V.comparisonReport(data.members[2].comparison, data.members[2].narrative)), "comparison member");
  H.equal(V.memberReport(data, "nope"), null, "an unknown member");
});

test("a collection without members or one that is not an object is refused by the composition", () => {
  let threw = 0;
  for (const bad of [null, {}, { members: "x" }]) try { V.collectionReport(bad); } catch { threw++; }
  H.equal(threw, 3, "refusals");
});

// ------------------------------------------------------------------ the index and its designs

test("the index lists every report by theme with its decision, its rates and exact counts", () => {
  const html = render({ type: "reports" });
  H.equal(H.count(html, 'data-av-rx-view="cards"'), 1, "the cards design");
  const cards = html.split('data-av-rx-view="list"')[0];
  H.equal(H.count(cards, "<li class=\"av-rx-card"), 3, "one card per report");
  H.includes(cards, "Theme one"); H.includes(cards, "Story one.");
  H.includes(cards, 'href="#report/alpha"', "a link that opens the report");
  H.includes(cards, "30%–95%", "the reference's Wilson interval"); H.includes(cards, "5%–70%", "the candidate's Wilson interval");
  H.includes(cards, "−50 pts", "the change from the reference");
  H.includes(cards, "−79 to +14 pts", "its Newcombe interval");
  H.includes(cards, "won 2 of 2 decisive judgments (100%)", "a preference metric is drawn as its win share: pb won Ana's and Ben's picks; a tie and an unreached judgment are not decisive");
  H.includes(cards, 'Follows <a href="#report/alpha">Alpha</a>', "the follow-up names what it follows");
  H.includes(cards, 'href="#compare/alpha/beta"', "and links the two side by side");
});

test("every index design lists the same reports, and layouts chooses which and in what order", () => {
  const html = render({ type: "reports" });
  H.equal(["cards", "list", "table", "matrix"].map(l => H.count(html, `data-av-rx-view="${l}"`)), [1, 1, 1, 1], "four designs");
  H.equal(H.count(html, 'data-av-rx-layout="'), 4, "a switcher button per design");
  H.ok(/data-av-rx-view="list" hidden/.test(html) && !/data-av-rx-view="cards" hidden/.test(html), "the first design shows");
  for (const l of ["list", "table", "matrix"]) H.equal(H.count(html.split(`data-av-rx-view="${l}"`)[1].split("data-av-rx-view=")[0], 'data-member="'), 3, `${l} lists every report`);
  const table = render({ type: "reports", layouts: ["table", "zz"] });
  H.equal(H.count(table, "data-av-rx-view="), 1, "only the named design"); H.excludes(table, "data-av-rx-layout=", "no switcher for one design");
  H.includes(table, 'aria-label="Compare Alpha"', "the table can pick reports to compare");
  const matrix = render({ type: "reports", layouts: ["matrix"] });
  H.includes(matrix, "<code>model-g</code>"); H.includes(matrix, "<code>model-c</code>"); H.includes(matrix, "Model not recorded", "a comparison without models gets its own column");
});

test("members and themes draw a subset in any view", () => {
  H.equal(H.count(render({ type: "reports", layouts: ["cards"], members: ["beta"] }), "<li class=\"av-rx-card"), 1, "members");
  H.equal(H.count(render({ type: "decisions", themes: ["t2"] }), "av-dec-tile "), 1, "themes");
  H.includes(render({ type: "shifts", members: ["nope"] }), "No report records a headline value", "an empty subset says so");
});

test("the decision board tallies decisions and links each to its report in its own words", () => {
  const html = render({ type: "decisions" });
  H.includes(html, 'aria-label="Decisions: 2 adopt, 1 do not adopt"', "tally");
  H.includes(text(html), "Adopt Alpha"); H.includes(text(html), "Do not adopt Beta");
  H.equal(H.count(html, 'class="av-dec-tile '), 3, "a tile per report");
});

// ------------------------------------------------------------------ cross-report views

test("shifts draw every setup per model with the reference as a ring, and say the change", () => {
  const html = render({ type: "shifts" });
  H.includes(html, "model-g"); H.includes(html, "model-c");
  H.equal(H.count(html, "av-cx-pt--base"), 2, "a reference ring per trial");
  H.equal(H.count(html, "av-cx-shift--bad"), 2, "both candidates did worse on a measure where higher is better");
  H.includes(html, "−50 pts <span class=\"av-muted\">(95%: −79 to +14 pts)</span>", "the change and its interval");
  H.includes(html, "Every value and change, exactly", "exact numbers on demand");
});

test("cost against gain plots each change at the trial's own cost difference, in the setup's identity color", () => {
  const html = render({ type: "cost-gain" });
  H.equal(H.count(html, 'class="av-cg-pt"'), 2, "a point per change");
  H.includes(html, "cost <b>+20%</b>", "the trial's per-case median cost difference");
  H.includes(html, "--v:var(--av-arm-1)", "the candidate keeps its report's color");
});

test("the timeline orders reports by when they ran and links each follow-up both ways", () => {
  const html = render({ type: "timeline" }), t = text(html);
  H.equal([...html.matchAll(/class="av-tl-title"><a href="#report\/([\w.-]+)"/g)].map(m => m[1]), ["alpha", "beta", "sandwich"], "reports in the order they ran");
  H.equal([...html.matchAll(/class="av-tl-date">([^<]+)</g)].map(m => m[1].replace(/^\w+,? /, "")), ["15 Oct 2026", "16 Oct 2026", "17 Oct 2026"], "one heading per day");
  H.includes(t, "19:00 UTC", "the data's own start time");
  H.includes(t, "Follows Alpha (Adopt)"); H.includes(t, "Followed up by Beta");
});

test("matchups pair the author's pairs and each follow-up once", () => {
  const html = render({ type: "matchups" });
  H.equal(H.count(html, 'class="av-mu-card"'), 1, "the pair and the follow-up are the same two reports");
  H.includes(text(html), "Same question, two families");
  H.includes(text(html), "Decision changed: Adopt → Do not adopt");
  H.includes(text(html), "models model-g → model-c");
});

test("two reports side by side match setups by label, then by id apart from a shared ending, and set each decision in full", () => {
  const html = render({ type: "report-compare", a: "alpha", b: "beta" });
  const t = text(html);
  H.includes(t, "Setups: 2 setups matched"); H.includes(t, "Cases: 1 case in both");
  H.includes(html, "same id apart from -gpt and -cl", "ids matched across families");
  H.includes(t, "A 3 of 4 passed (75%) · B 3 of 4 passed (75%) · B − A ±0 pts", "references compared");
  H.includes(html, "av-block--verdict", "each decision rendered by the verdict view");
  H.equal(H.count(html, "Decision for ref-"), 4, "both headlines, in the head and in full");
  H.includes(render({ type: "report-compare", a: "alpha", b: "zz" }), "Not in this collection: zz");
});

test("collection views without a collection render a notice naming what they need", () => {
  for (const type of ["decisions", "reports", "shifts", "cost-gain", "timeline", "matchups", "report-compare"]) {
    const html = V.renderBlock({ type, a: "x", b: "y" }, V.createContext({}));
    H.includes(html, "av-block-error", `${type} notice`); H.includes(html, "needs a collection", `${type} reason`);
  }
});

test("a collection's untrusted text stays text in every view", () => {
  const data = collection();
  data.title = F.hostile("title"); data.themes[0].label = F.hostile("theme"); data.themes[0].summary = F.hostile("story");
  Object.assign(data.members[0], { label: F.hostile("label"), note: F.hostile("note"), models: [F.hostile("model")] });
  data.members[0].narrative.decision.headline = F.hostile("headline"); data.members[0].narrative.decision.label = F.hostile("stamp");
  data.pairs[0].title = F.hostile("pair");
  const html = V.renderReport(V.collectionReport(data)) + render({ type: "reports" }, data) + render({ type: "report-compare", a: "alpha", b: "beta" }, data);
  H.equal(F.rawHostileFields(html), [], "raw hostile markup");
  H.includes(html, F.escapedHostile("headline"), "escaped headline");
});

test("reader addresses name a report or two, and nothing else", () => {
  H.equal(H.plain(V.readerRoute("#report/alpha")), { kind: "report", id: "alpha", base: "#report/alpha" }, "a report");
  H.equal(H.plain(V.readerRoute("#report/alpha/runs?outcome=fail")), { kind: "report", id: "alpha", base: "#report/alpha" }, "an address inside it");
  H.equal(H.plain(V.readerRoute("#compare/alpha/beta")), { kind: "compare", a: "alpha", b: "beta", base: "#compare/alpha/beta" }, "two reports");
  H.equal([V.readerRoute("#runs"), V.readerRoute("#report/9x"), V.readerRoute("#compare/a"), V.readerRoute("")], [null, null, null, null], "other addresses");
});

// ------------------------------------------------------------------ regressions from review

/** Two trials of one question: A's reference passes 3 of 4, B's 1 of 4. */
function directional() {
  return { members: [
    { id: "first", label: "First", trial: pairTrial(["ref-gpt", "new-gpt"], "m", 0.1), narrative: narrative(["ref-gpt", "new-gpt"], "adopt") },
    { id: "second", label: "Second", trial: pairTrial(["ref-cl", "new-cl"], "m", 0.1, ["PFFF", "PPPF"]), narrative: narrative(["ref-cl", "new-cl"], "adopt") },
  ] };
}

test("side by side, B minus A keeps its sign and its interval, and swapping A and B reverses both", () => {
  const ab = text(render({ type: "report-compare", a: "first", b: "second" }, directional()));
  H.includes(ab, "A 3 of 4 passed (75%) · B 1 of 4 passed (25%) · B − A −50 pts (−79 to +14 pts)", "B − A is −50 points, Newcombe −79 to +14");
  const ba = text(render({ type: "report-compare", a: "second", b: "first" }, directional()));
  H.includes(ba, "B − A +50 pts (−14 to +79 pts)", "swapped, +50 points, −14 to +79");
  const html = render({ type: "report-compare", a: "first", b: "second" }, directional());
  H.ok(/av-cx-shift--bad[^>]*><\/span><span class="av-rc-mark av-rc-mark--a" style="--x:75\.000%/.test(html), "the reference's drop from 75% is drawn as a change for the worse");
});

/** One binary metric per comparison: x succeeds k of n, y succeeds n − k of n. */
function single(metric, better, k, n, extra = {}) {
  const obs = (alt, hits) => Array.from({ length: n }, (_, i) => ({ alternative: alt, metric, value: i < hits }));
  return { alternatives: [{ id: "x" }, { id: "y" }], baseline: "x", metrics: [{ id: metric, kind: "binary", primary: true, ...(better ? { better } : {}) }], observations: [...obs("x", k), ...obs("y", n - k)], ...extra };
}

test("reports on different measures are shown apart, never subtracted", () => {
  const data = { members: [{ id: "a", comparison: single("success", "higher", 75, 100) }, { id: "b", comparison: single("defect", "lower", 25, 100) }] };
  const html = render({ type: "report-compare", a: "a", b: "b" }, data);
  H.excludes(html, "B − A", "a difference across measures");
  H.includes(text(html), "A measures success and B measures defect, so their values are shown apart and never subtracted");
});

test("a change is toned by its measure's direction: better where lower is better, neutral where none is named", () => {
  const lower = render({ type: "shifts" }, { members: [{ id: "d", comparison: single("defect", "lower", 1, 4) }] });
  H.includes(lower, "av-cx-shift--bad", "more defects (y: 3 of 4 against x: 1 of 4) is worse"); H.excludes(lower, "av-cx-shift--good");
  const none = render({ type: "shifts" }, { members: [{ id: "n", comparison: single("clicks", null, 1, 4) }] });
  H.includes(none, "av-cx-shift--neutral", "no direction, no judgment"); H.excludes(none, "av-cx-shift--good"); H.excludes(none, "av-cx-shift--bad");
});

test("a comparison's evidence is counted as the comparison engine reads it, judgments, rankings and totals apart", () => {
  const nul = { members: [{ id: "n", comparison: { alternatives: [{ id: "x" }], metrics: [{ id: "m", kind: "binary" }], observations: [{ alternative: "x", metric: "m", value: null }] } }] };
  const s = H.plain(V.collectionModel(nul).members[0]);
  H.equal([s.valid, s.invalid, s.evidence], [0, 1, [{ n: 1, noun: "observation", invalid: 1 }]], "a missing value is invalid");
  const sandwich = H.plain(V.collectionModel(collection()).byId.get("sandwich").evidence);
  H.equal(sandwich, [{ n: 16, noun: "observation", invalid: 2 }, { n: 4, noun: "judgment" }], "observations (Dee's two jelly ratings invalid) and judgments, each counted");
  H.includes(text(render({ type: "reports", layouts: ["cards"], members: ["sandwich"] })), "16 observations 2 invalid 4 judgments", "both on the card");
});

test("a member's numeric or ordinal primary metric is drawn on its own scale with its own words", () => {
  const numeric = { alternatives: [{ id: "x" }, { id: "y" }], metrics: [{ id: "minutes", kind: "numeric", unit: "min", primary: true, better: "lower" }],
    observations: [2, 4, 6].map(v => ({ alternative: "x", metric: "minutes", value: v })).concat([5, 7, 9].map(v => ({ alternative: "y", metric: "minutes", value: v }))), baseline: "x" };
  const html = render({ type: "reports", layouts: ["cards"] }, { members: [{ id: "n", comparison: numeric }] });
  H.includes(html, "mean 4 min (n = 3)", "x's mean, (2 + 4 + 6) / 3"); H.includes(html, "mean 7 min (n = 3)", "y's mean");
  H.includes(html, "+3 min", "y minus x"); H.includes(html, "av-cx-shift--bad", "three more minutes where lower is better");
  const ordinal = { alternatives: [{ id: "x" }], metrics: [{ id: "taste", kind: "ordinal", levels: ["meh", "good", "great"], primary: true }], observations: ["meh", "great", "great"].map(v => ({ alternative: "x", metric: "taste", value: v })) };
  H.includes(render({ type: "reports", layouts: ["cards"] }, { members: [{ id: "o", comparison: ordinal }] }), "median level “great” (n = 3)", "the median of meh, great, great");
});

test("an explicit members list keeps its order in every grouped view", () => {
  const first = (html, ids) => ids.map(id => html.indexOf(`href="#report/${id}"`));
  for (const type of ["reports", "decisions", "shifts"]) {
    const [b, a] = first(render({ type, members: ["beta", "alpha"] }), ["beta", "alpha"]);
    H.ok(b >= 0 && a > b, `${type}: beta before alpha`);
  }
});

test("an impossible date is no date: the checker warns and the timeline draws the report undated", () => {
  const data = collection(); data.members[1].date = "2026-02-30";
  H.equal(H.plain(V.validateCollection(data)).filter(p => p.where === "collection.members[1].date").map(p => p.message), ['"2026-02-30" is not a calendar date written YYYY-MM-DD, so it is not used'], "warning");
  const html = render({ type: "timeline" }, data);
  H.excludes(html, "could not render", "a render failure");
  H.equal([...html.matchAll(/class="av-tl-date">([^<]+)</g)].map(m => m[1].replace(/^\w+,? /, "")), ["15 Oct 2026", "17 Oct 2026"], "beta falls back to its data's own day, 15 Oct");
});

test("a member can be a finished specification of any blocks, with its decision from its verdict block", () => {
  const spec = { title: "Hand-built", sections: [{ title: "Decision", blocks: [{ type: "verdict", verdict: "reject", label: "Keep the old one", headline: "The new one lost." }, { type: "text", text: "Why." }] }] };
  const data = { members: [{ id: "custom", spec }, { id: "alpha", trial: pairTrial(["a", "b"], "m", 0.1) }] };
  const s = H.plain(V.collectionModel(data).byId.get("custom"));
  H.equal([s.kind, s.verdict, s.stamp, s.headline, s.title], ["spec", "reject", "Keep the old one", "The new one lost.", "Hand-built"], "its summary");
  H.ok(V.memberReport(data, "custom") === spec, "it opens as written");
  H.includes(render({ type: "reports", layouts: ["cards"] }, data), "specification", "its card says what it is");
  const bad = { members: [{ id: "custom", spec: { title: "x", sections: [{ title: "S", blocks: [{ type: "verdit" }] }] }, narrative: {} }, { id: "two", spec: {}, trial: pairTrial(["a", "b"], "m", 0.1) }] };
  H.equal(H.plain(V.validateCollection(bad)).map(p => `${p.level} ${p.where}: ${p.message}`), [
    'error collection.members[0].spec.sections[0].blocks[0]: unknown block type "verdit"',
    'error collection.members[1]: has more than one of "trial", "comparison" and "spec"',
    "warning collection.members[0].narrative: a specification replaces the composition a narrative shapes, so this narrative is not used",
  ], "its own checks, under its place");
});

test("the By model design lets any report be picked for comparison", () => {
  const html = render({ type: "reports", layouts: ["matrix"] });
  for (const id of ["alpha", "beta", "sandwich"]) H.includes(html, `data-av-rx-pick="${id}"`, `${id} can be picked`);
});

H.report();
