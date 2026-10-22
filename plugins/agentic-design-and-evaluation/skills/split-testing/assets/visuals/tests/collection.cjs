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

/** A two-arm trial on one model: the reference passes 3 of 4, the candidate 1 of 4. */
function pairTrial(ids, model, cost) {
  const [ref, cand] = ids;
  const data = F.gridTrial({ [ref]: { c1: "PPPF" }, [cand]: { c1: "PFFF" } }, run => ({ usage: { cost_usd: run.arm === ref ? cost : cost * 1.2 } }));
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
  const spec = V.collectionReport(collection());
  H.equal(H.plain(spec.sections.map(s => s.id)), ["glance", "reports", "shifts", "cost-gain", "timeline", "matchups"], "section ids");
  H.equal(H.plain(V.COLLECTION_SECTION_IDS), ["glance", "reports", "shifts", "cost-gain", "timeline", "matchups"], "every section id");
  const figures = H.plain(spec.sections[0].blocks[0].items);
  H.equal(figures.find(f => f.label === "reports"), { value: 3, label: "reports", note: "2 trials, 1 comparison" }, "the reports figure");
  H.equal(figures.find(f => f.label === "trial runs").value, 16, "trial runs");
  H.equal([figures.find(f => f.label === "adopted").value, figures.find(f => f.label === "not adopted").value], [2, 1], "decisions");
  H.ok(spec.collection === spec.collection && spec.title === "Collected", "the spec carries the collection and its title");
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
  H.includes(cards, "is not a rate, so it is not drawn here", "a preference metric is not drawn as a rate");
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
  H.includes(render({ type: "shifts", members: ["nope"] }), "No report records a rate", "an empty subset says so");
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
  H.equal(H.count(html, "av-cx-shift--down"), 2, "both candidates moved down");
  H.includes(html, "−50 pts <span class=\"av-muted\">(95%: −79 to +14 pts)</span>", "the change and its interval");
  H.includes(html, "Every rate and change, exactly", "exact numbers on demand");
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
  H.includes(t, "A 3/4 · B 3/4 · ±0 pts", "references compared");
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

H.report();
