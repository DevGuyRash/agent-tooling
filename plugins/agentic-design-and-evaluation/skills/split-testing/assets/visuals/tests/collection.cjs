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
    // Interleaved themes (alpha and beta in t1, sandwich in t2) keep the sequence asked for, not one group per theme.
    const [x, y, z] = first(render({ type, members: ["alpha", "sandwich", "beta"] }), ["alpha", "sandwich", "beta"]);
    H.ok(x >= 0 && y > x && z > y, `${type}: alpha, sandwich, beta in that order (${[x, y, z]})`);
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
    'error collection: missing "story", which tells a reader new to this work what it is about',
    'error collection.readings: no reading for the "glance" section',
    'error collection.readings: no reading for the "reports" section',
    'error collection.readings: no reading for the "shifts" section',
    'error collection.members[0].spec.sections[0].blocks[0]: unknown block type "verdit"',
    'error collection.members[0].spec: missing "story", which tells a reader new to this work what it is about',
    "error collection.members[0].spec.sections[0]: says nothing about what its views show for this data",
    'error collection.members[1]: has more than one of "trial", "comparison" and "spec"',
    "warning collection.members[0].narrative: a specification replaces the composition a narrative shapes, so this narrative is not used",
  ], "the collection's own story and readings, then the member's checks under its place");
});

test("the By model design lets any report be picked for comparison", () => {
  const html = render({ type: "reports", layouts: ["matrix"] });
  for (const id of ["alpha", "beta", "sandwich"]) H.includes(html, `data-av-rx-pick="${id}"`, `${id} can be picked`);
});

test("the index table counts every kind of evidence, and a trial's passes as counts", () => {
  // A comparison judged only head to head (three judgments, no observation) and a trial of 3 + 1 passes of 8 runs.
  const judged = { title: "Picks", alternatives: [{ id: "x", label: "X" }, { id: "y", label: "Y" }],
    metrics: [{ id: "pick", label: "Pick", kind: "preference", primary: true }],
    preferences: [{ a: "x", b: "y", winner: "x", metric: "pick" }, { a: "x", b: "y", winner: "x", metric: "pick" }, { a: "x", b: "y", winner: "y", metric: "pick" }] };
  const data = { title: "Evidence", members: [
    { id: "judged", label: "Judged", comparison: judged, narrative: { decision: { verdict: "adopt", headline: "X." } } },
    { id: "ran", label: "Ran", trial: pairTrial(["ref", "new"], "m", 0.1), narrative: narrative(["ref", "new"], "adopt") },
  ] };
  const html = V.renderReport({ title: "T", collection: data, sections: [{ title: "Index", blocks: [{ type: "reports", layouts: ["table"], read: { says: "Two reports." } }] }] });
  const row = id => H.element(H.element(html, "av-rx-table"), `data-member="${id}"`);
  H.includes(row("judged"), '<td class="av-num" data-v="3">3 judgments</td>', "the judgments, with a numeric sort key");
  H.includes(row("ran"), '<td class="av-num" data-v="8">8 runs</td>', "the runs");
  H.includes(row("ran"), "4 of 8", "the trial's setups' passes, as counts");
});

test("the shifts section speaks of pass rates only when every report it draws is a trial", () => {
  const shifts = data => V.collectionReport(data).sections.find(sec => sec.id === "shifts");
  const trials = shifts({ ...collection(), members: collection().members.filter(m => m.trial) });
  H.equal([trials.title, /0–100% scale per model/.test(trials.lead)], ["How the pass rates moved", true], "trials alone");
  const numeric = { alternatives: [{ id: "x" }, { id: "y" }], metrics: [{ id: "minutes", kind: "numeric", unit: "min", primary: true, better: "lower" }],
    observations: [2, 4, 6].map(v => ({ alternative: "x", metric: "minutes", value: v })).concat([5, 7, 9].map(v => ({ alternative: "y", metric: "minutes", value: v }))), baseline: "x" };
  const mixed = shifts({ ...collection(), members: [...collection().members, { id: "n", comparison: numeric }] });
  H.ok(!/pass rate/.test(mixed.title + mixed.lead), `no pass rates for a numeric member: ${mixed.title} / ${mixed.lead}`);
  H.ok(!/0–100% scale per model/.test(mixed.lead), "nor one 0–100% scale for every report");
  H.includes(mixed.lead, "its own", "each measure on its own scale");
});

test("ordinal ratings share a scale only when their ordered levels are the same", () => {
  // The reviewer's reproduction: one setup rated "good" in both reports, on ["bad", "ok", "good"] in A and ["bad", "good"] in B.
  const rated = levels => ({ alternatives: [{ id: "x" }], metrics: [{ id: "taste", kind: "ordinal", levels, better: "higher", primary: true }], observations: [{ alternative: "x", metric: "taste", value: "good" }] });
  const pair = (a, b) => ({ members: [{ id: "a", comparison: rated(a) }, { id: "b", comparison: rated(b) }] });
  const apart = render({ type: "report-compare", a: "a", b: "b" }, pair(["bad", "ok", "good"], ["bad", "good"]));
  H.excludes(apart, "av-cx-shift", "a connector between levels of different scales");
  H.excludes(apart, "av-rc-slope", "one shared scale");
  H.includes(text(apart), "A and B both measure taste, but on different ordered levels (A: bad, ok, good; B: bad, good), so their values are shown apart and never subtracted", "why they are apart");
  H.includes(text(apart), "Each report on its own measure", "each on its own scale");
  const own = apart.slice(apart.indexOf("Each report on its own measure"), apart.indexOf("av-rc-full"));
  H.equal(own.match(/median level “good”/g)?.length, 6, "each rating in its own words, in its label, its tip and its list");
  H.equal(own.match(/<span>“bad”<\/span><span>“good”<\/span>/g)?.length, 2, "each scale's ends named by its own levels");
  // The control: the same ordered levels share one scale, and the same rating draws a flat connector.
  const together = render({ type: "report-compare", a: "a", b: "b" }, pair(["bad", "ok", "good"], ["bad", "ok", "good"]));
  H.includes(together, "av-cx-shift--flat", "no change between equal ratings");
  H.includes(text(together), "both measure taste", "one measure");
  // The same levels in another order are another scale.
  H.excludes(render({ type: "report-compare", a: "a", b: "b" }, pair(["bad", "ok", "good"], ["good", "ok", "bad"])), "av-rc-slope", "reversed levels are another scale");
  // The page that sets them side by side says so in its own story and reading.
  const page = V.compareReport(pair(["bad", "ok", "good"], ["bad", "good"]), "a", "b");
  H.includes(page.sections[0].reading, "different ordered levels", "the page's reading");
});

test("every measure kind set side by side checks what must match: units, direction and kind", () => {
  const pair = (a, b) => render({ type: "report-compare", a: "a", b: "b" }, { members: [{ id: "a", comparison: a }, { id: "b", comparison: b }] });
  // Numbers in different units, or with opposite directions, stay apart.
  const timed = (unit, better) => ({ alternatives: [{ id: "x" }], metrics: [{ id: "time", kind: "numeric", unit, better, primary: true }], observations: [3, 5].map(value => ({ alternative: "x", metric: "time", value })) });
  H.includes(text(pair(timed("min", "lower"), timed("s", "lower"))), "A and B both measure time, but in different units (A: min; B: s)", "units");
  H.includes(text(pair(timed("min", "lower"), timed("min", "higher"))), "A and B both measure time, but in different directions (A: lower is better; B: higher is better)", "directions");
  H.includes(pair(timed("min", "lower"), timed("min", "lower")), "av-rc-slope", "the same unit and direction share a scale");
  // Rates of different kinds stay apart; the same kind shares a scale.
  const rate = kind => ({ alternatives: [{ id: "x" }], metrics: [{ id: "ok", kind, primary: true }], observations: kind === "count" ? [{ alternative: "x", metric: "ok", value: 3, n: 4 }] : [true, false].map(value => ({ alternative: "x", metric: "ok", value })) });
  H.includes(text(pair(rate("binary"), rate("count"))), "A and B both measure ok, but as binary and count values", "kinds");
  H.includes(pair(rate("count"), rate("count")), "av-rc-slope", "the same kind shares a scale");
});

test("a difference with no interval says why: pooled over cases, or a spread that is missing", () => {
  const timed = value => ({ alternatives: [{ id: "x" }], cases: [{ id: "c" }], metrics: [{ id: "time", kind: "numeric", unit: "min", better: "lower", primary: true }], observations: [{ alternative: "x", case: "c", metric: "time", value }] });
  const html = render({ type: "report-compare", a: "a", b: "b" }, { members: [{ id: "a", comparison: timed(3) }, { id: "b", comparison: timed(4) }] });
  H.includes(text(html), "B − A +1 min (no interval: a spread is missing)", "one value each on one case");
  H.excludes(text(html), "pooled over cases", "not a pooling it never did");
});

test("ties and unreached judgments give no value and no invented reason", () => {
  const only = winner => ({ alternatives: [{ id: "x" }, { id: "y" }], metrics: [{ id: "pick", kind: "preference", better: "higher", primary: true }], preferences: [{ a: "x", b: "y", winner }] });
  for (const winner of ["tie", null]) {
    const data = { members: [{ id: "a", comparison: only(winner) }, { id: "b", comparison: only(winner) }] };
    const html = text(render({ type: "report-compare", a: "a", b: "b" }, data));
    H.excludes(html, "not recorded", `no claim of supplied totals (${winner})`);
    H.excludes(html, "faced different opponents", `no claim of different opponents (${winner})`);
    H.excludes(V.compareReport(data, "a", "b").sections[0].reading, "faced different opponents", `nor in the page's reading (${winner})`);
  }
});

test("the index never orders a change in preference or rank against another report's", () => {
  // The reviewer's partial rankings, with y as reference and z in a group of its own, so x's change is each report's only one.
  const ranked = orders => ({ alternatives: [{ id: "x" }, { id: "y" }, { id: "z", group: "other" }], baseline: "y", metrics: [{ id: "place", kind: "rank", better: "lower", primary: true }], rankings: orders.map(order => ({ order })) });
  const html = render({ type: "reports", layouts: ["table"] }, { members: [{ id: "a", comparison: ranked([["x", "y"], ["z", "y"]]) }, { id: "b", comparison: ranked([["z", "x"], ["z", "y"]]) }] });
  const groups = [...html.matchAll(/data-g="([^"]*)"/g)].map(m => m[1]);
  H.equal(groups.length, 2, "both reports have a change from reference");
  H.ok(groups[0] !== groups[1], "each in a sorting group of its own");
});

test("a difference of means with no spread in either report says so, and claims no interval it does not have", () => {
  const timed = values => ({ alternatives: [{ id: "x" }], cases: [{ id: "c" }], metrics: [{ id: "time", kind: "numeric", unit: "min", better: "lower", primary: true }], observations: values.map(value => ({ alternative: "x", case: "c", metric: "time", value })) });
  const html = render({ type: "report-compare", a: "a", b: "b" }, { members: [{ id: "a", comparison: timed([3, 3]) }, { id: "b", comparison: timed([4, 4]) }] });
  H.includes(text(html), "B − A +1 min (no interval: neither report's values vary)", "zero spread, not a missing one");
  H.excludes(html, "with a 95% Welch interval", "no claim of an interval");
});

test("preference and rank values are never set against another report's", () => {
  const times = (n, x) => Array.from({ length: n }, () => x);
  const pair = (a, b) => ({ members: [{ id: "a", comparison: a }, { id: "b", comparison: b }] });
  const compare = data => render({ type: "report-compare", a: "a", b: "b" }, data);
  // The probe: x faces only y; in A it wins 9 on case c1 and loses 1 on c2, in B the reverse.
  const judged = prefs => ({ alternatives: [{ id: "x" }, { id: "y" }], cases: [{ id: "c1" }, { id: "c2" }], metrics: [{ id: "pick", kind: "preference", better: "higher", primary: true }], preferences: prefs.map(([a, b, winner, c]) => ({ a, b, winner, case: c })) });
  const over = compare(pair(judged([...times(9, ["x", "y", "x", "c1"]), ["x", "y", "y", "c2"]]), judged([["x", "y", "x", "c1"], ...times(9, ["x", "y", "y", "c2"])])));
  for (const html of [over, compare(pair(judged([["x", "y", "x", "c1"]]), judged([["x", "y", "x", "c1"]])))]) {
    H.excludes(html, "av-rc-slope", "one shared scale");
    H.excludes(html, "av-cx-shift", "a connector");
    H.excludes(text(html), "B − A", "a difference");
  }
  H.includes(text(over), "A and B both measure pick, a share of decisive judgments that depends on who else was judged and how often, so their values are shown apart and never subtracted", "why");
  H.includes(text(over), "x: won 9 of 10 decisive judgments (90%)", "A's value in its own words");
  H.includes(text(over), "x: won 1 of 10 decisive judgments (10%)", "B's");
  const ranked = orders => ({ alternatives: ["x", "y", "z"].map(id => ({ id })), metrics: [{ id: "place", kind: "rank", better: "lower", primary: true }], rankings: orders.map(order => ({ order })) });
  const ranks = compare(pair(ranked([["x", "y", "z"]]), ranked([["x", "y", "z"]])));
  H.excludes(ranks, "av-cx-shift", "not even between identical rankings");
  H.includes(text(ranks), "A and B both measure place, a mean rank that depends on who else was ranked and how often", "why");
  H.includes(text(ranks), "x: mean rank 1 (n = 1)", "each value in its own words");
});

test("the earlier preference and rank probes, and their controls, are all shown apart with no change", () => {
  const times = (n, x) => Array.from({ length: n }, () => x);
  const pair = (a, b) => ({ members: [{ id: "a", comparison: a }, { id: "b", comparison: b }] });
  const judged = (prefs, ids = ["x", "y", "z"]) => ({ alternatives: ids.map(id => ({ id })), metrics: [{ id: "pick", kind: "preference", better: "higher", primary: true }], preferences: prefs.map(([a, b, winner]) => ({ a, b, winner })) });
  const ranked = orders => ({ alternatives: [...new Set(orders.flat())].map(id => ({ id })), metrics: [{ id: "place", kind: "rank", better: "lower", primary: true }], rankings: orders.map(order => ({ order })) });
  const probes = {
    "different opponents": pair(judged([["x", "y", "x"], ["z", "y", "z"]]), judged([["z", "x", "z"], ["z", "y", "z"]])),
    "different opponent mix": pair(judged([...times(9, ["x", "y", "x"]), ["z", "x", "z"]]), judged([["x", "y", "x"], ...times(9, ["z", "x", "z"])])),
    "the same pair judged": pair(judged([["x", "y", "x"]], ["x", "y"]), judged([["x", "y", "y"]], ["x", "y"])),
    "3 places against 5": pair(ranked([["y", "x", "z"]]), ranked([["y", "x", "z", "u", "v"]])),
    "partial rankings": pair(ranked([["x", "y"], ["z", "y"]]), ranked([["z", "x"], ["z", "y"]])),
    "different ranking mix": pair(ranked([...times(9, ["x", "y"]), ["z", "x"]]), ranked([["x", "y"], ...times(9, ["z", "x"])])),
    "the same rankings": pair(ranked([["x", "y"], ["z", "y"]]), ranked([["y", "x"], ["y", "z"]])),
  };
  for (const [name, data] of Object.entries(probes)) {
    const html = render({ type: "report-compare", a: "a", b: "b" }, data);
    H.excludes(html, "av-rc-slope", `one shared scale (${name})`);
    H.excludes(html, "av-cx-shift", `a connector (${name})`);
    H.excludes(text(html), "B − A", `a difference (${name})`);
    H.includes(text(html), "Each report on its own measure", `each apart (${name})`);
    H.excludes(V.compareReport(data, "a", "b").sections[0].reading, "sit on one scale", `the page's reading (${name})`);
  }
});

test("a change across reports is averaged over the cases both ran, each case weighted equally", () => {
  const times = (n, x) => Array.from({ length: n }, () => x);
  const pair = (a, b) => ({ members: [{ id: "a", comparison: a }, { id: "b", comparison: b }] });
  const compare = data => render({ type: "report-compare", a: "a", b: "b" }, data);
  const pass = (marks, cases = ["easy", "hard"]) => ({ alternatives: [{ id: "x" }], cases: cases.map(id => ({ id })), metrics: [{ id: "ok", kind: "binary", better: "higher", primary: true }], observations: marks.map(([c, v]) => ({ alternative: "x", case: c, metric: "ok", value: v })) });
  // The probe: easy always passes and hard always fails in both; A ran 9 easy and 1 hard, B the reverse. Each case is
  // unchanged, so the case-balanced averages are 50% and 50%, and the line is flat.
  const mixed = compare(pair(pass([...times(9, ["easy", true]), ["hard", false]]), pass([["easy", true], ...times(9, ["hard", false])])));
  H.includes(mixed, "av-cx-shift--flat", "no change in any case");
  H.includes(text(mixed), "A 9 of 10 across 2 cases · B 1 of 10 across 2 cases", "each report's own pooled words");
  H.includes(text(mixed), "B − A ±0 pts (averaged over cases, no interval) Averaged over the 2 cases both ran, each case weighted equally: A 50%, B 50%.", "the balanced values and their change, labeled");
  H.excludes(text(mixed), "different proportions", "nothing kept apart");
  // Shared cases with one invalid run on one side: the line is kept. A: easy 3 of 3, hard 0 of 3 (50%); B: easy 2 of 2
  // valid (one invalid), hard 2 of 3, so (100% + 66.7%) / 2 = 83.3%: +33 points.
  const trials = { members: [{ id: "a", trial: F.gridTrial({ x: { easy: "PPP", hard: "FFF" } }) }, { id: "b", trial: F.gridTrial({ x: { easy: "PPX", hard: "PPF" } }) }] };
  const kept = compare(trials);
  H.includes(kept, "av-cx-shift--good", "the change is drawn");
  H.includes(text(kept), "B − A +33 pts (averaged over cases, no interval) Averaged over the 2 cases both ran, each case weighted equally: A 50%, B 83%.", "its value");
  // Partial overlap: A ran three cases, B two; the line covers the two both ran and says so.
  const partial = compare(pair(pass([["easy", true], ["hard", false], ["extra", true]], ["easy", "hard", "extra"]), pass([["easy", true], ["hard", true]])));
  H.includes(partial, "av-cx-shift--good", "a line over the shared cases");
  H.includes(text(partial), "A ran 3 cases and B 2; the line covers only the 2 both ran.", "its coverage");
  // One shared case among more: that case's own comparison, with its interval. Newcombe for 1 of 1 minus 0 of 1: Wilson
  // gives 0.2065–1 and 0–0.7935, so 1 − √(0.7935² + 0.7935²) = −0.122 to 1.
  const one = compare(pair(pass([["easy", false], ["hard", false]]), pass([["easy", true]], ["easy"])));
  H.includes(text(one), "On the one case both ran, easy: A 0%, B 100%.", "that case's values");
  H.includes(text(one), "A ran 2 cases and B 1; the line covers only the 1 both ran", "its coverage");
  H.includes(text(one), "B − A +100 pts (−12 to +100 pts)", "that case's own interval");
  // No case in common: the values are shown apart.
  const none = compare(pair(pass([["c1", true]], ["c1"]), pass([["c2", false]], ["c2"])));
  H.excludes(none, "av-cx-shift", "no line");
  H.includes(text(none), "x ran no case in common in the two reports (A: c1; B: c2), so the two values are not set against each other", "why");
  // A numeric measure averages each case's mean; an ordinal one takes the median level of the cases weighted equally.
  const timed = obs => ({ alternatives: [{ id: "x" }], cases: [{ id: "c1" }, { id: "c2" }], metrics: [{ id: "t", kind: "numeric", unit: "min", better: "lower", primary: true }], observations: obs.map(([c, value]) => ({ alternative: "x", case: c, metric: "t", value })) });
  H.includes(text(compare(pair(timed([["c1", 3], ...times(9, ["c2", 5])]), timed([...times(9, ["c1", 3]), ["c2", 5]])))), "B − A ±0 min (averaged over cases, no interval) Averaged over the 2 cases both ran, each case weighted equally: A 4 min, B 4 min.", "means of 3 and 5 in both");
  const rated = obs => ({ alternatives: [{ id: "x" }], cases: [{ id: "c1" }, { id: "c2" }], metrics: [{ id: "q", kind: "ordinal", levels: ["bad", "ok", "good"], better: "higher", primary: true }], observations: obs.map(([c, value]) => ({ alternative: "x", case: c, metric: "q", value })) });
  H.includes(compare(pair(rated([...times(9, ["c1", "good"]), ["c2", "bad"]]), rated([["c1", "good"], ...times(9, ["c2", "bad"])]))), "av-cx-shift--flat", "the same levels case by case");
});

test("round 9: every view that sets setups or reports against each other uses their case-balanced values", () => {
  const times = (n, x) => Array.from({ length: n }, () => x);
  const pair = (a, b) => ({ members: [{ id: "a", comparison: a }, { id: "b", comparison: b }] });
  const compare = data => render({ type: "report-compare", a: "a", b: "b" }, data);
  // 1. The reviewer's numbers: A has nine 0 s on c1 and one 100 s on c2, B nine 0 s and one 120 s. Balanced: 50 s and 60 s.
  const timed = (c2) => ({ alternatives: [{ id: "x" }], cases: [{ id: "c1" }, { id: "c2" }], metrics: [{ id: "t", kind: "numeric", unit: "s", better: "lower", primary: true }],
    observations: [...times(9, ["c1", 0]), ["c2", c2]].map(([c, value]) => ({ alternative: "x", case: c, metric: "t", value })) });
  const axes = compare(pair(timed(100), timed(120)));
  const marks = [...axes.matchAll(/class="av-rc-mark av-rc-mark--([ab])" style="--x:([\d.]+)%[^"]*" data-av-tip="([^"]*)"/g)].map(m => [m[1], Number(m[2]), m[3]]);
  H.equal(marks.length, 2, "a mark for A and for B");
  H.ok(marks.every(([, x]) => x > 0 && x < 100), `both marks inside the axis, none clamped: ${marks.map(m => m[1]).join(", ")}`);
  H.ok(marks[0][1] < marks[1][1], "A's 50 s left of B's 60 s");
  H.includes(marks[0][2], "50 s", "A's tip gives the plotted value"); H.includes(marks[1][2], "60 s", "and B's");
  // 2. The reviewer's index: the reference always fails; the candidate always passes easy and fails hard. A ran nine easy and one
  // hard of each, B the reverse. Each case is unchanged, so both changes are +50 points and both case-balanced rates 25%.
  const trial = (easy, hard) => { const t = F.gridTrial({ ref: { easy: "F".repeat(easy), hard: "F".repeat(hard) }, cand: { easy: "P".repeat(easy), hard: "F".repeat(hard) } }); t.baseline = "ref"; return t; };
  const index = render({ type: "reports", layouts: ["table"] }, { members: [{ id: "a", trial: trial(9, 1), narrative: { baseline: "ref" } }, { id: "b", trial: trial(1, 9), narrative: { baseline: "ref" } }] });
  const cells = row => { const tr = index.split("<tr").find(x => x.includes(`data-member="${row}"`)) || ""; return [...tr.matchAll(/<td class="av-num" data-v="([^"]*)"[^>]*>([^<]*)/g)].map(m => [m[1], m[2]]); };
  for (const id of ["a", "b"]) {
    const c = cells(id);
    H.ok(c.some(([v, t]) => Math.abs(Number(v) - 0.25) < 1e-9 && /^\d+ of 20$/.test(t)), `${id}: sorted by a case-balanced 25%, shown as its counts: ${JSON.stringify(c)}`);
    H.ok(c.some(([v]) => Math.abs(Number(v) - 0.5) < 1e-9), `${id}: its change sorted as +50 points`);
  }
  H.includes(index, "sorted by the case-balanced pass rate", "the Passed column says its sort key");
  H.includes(index, "sorted by the largest case-balanced change", "and the Changes column");
  // 3. Undeclared case ids: both reports name c1 and c2 only in their observations.
  const named = v => ({ alternatives: [{ id: "x" }], metrics: [{ id: "ok", kind: "binary", better: "higher", primary: true }], observations: [["c1", true], ["c2", v]].map(([c, value]) => ({ alternative: "x", case: c, metric: "ok", value })) });
  const undeclared = text(compare(pair(named(true), named(false))));
  H.includes(undeclared, "Cases: 2 cases in both", "the cases the data name");
  H.includes(undeclared, "Case by case", "and their table");
  // 4. A case that ran with no valid result: A's c2 run is invalid, B's fails.
  const invalid = text(render({ type: "report-compare", a: "a", b: "b" }, { members: [{ id: "a", trial: F.gridTrial({ x: { c1: "P", c2: "X" } }) }, { id: "b", trial: F.gridTrial({ x: { c1: "P", c2: "F" } }) }] }));
  H.includes(invalid, "Cases: 2 cases in both", "both ran both");
  H.includes(invalid, "On the one case both have a valid result on, c1: A 100%, B 100%.", "the line's one case");
  H.includes(invalid, "A ran 2 cases, 1 with a valid result, and B 2; the line covers only the 1 case both have a valid result on.", "its coverage, told apart from cases never run");
  // 5. A copied invalid-run alert leads to its own report's invalid runs.
  const alerted = render({ type: "report-compare", a: "a", b: "b" }, { members: [{ id: "a", trial: F.gridTrial({ x: { c1: "PX" } }) }, { id: "b", trial: F.gridTrial({ x: { c1: "XF" } }) }] });
  H.includes(alerted, 'href="#report/a/invalid"', "A's alert to A's invalid runs"); H.includes(alerted, 'href="#report/b/invalid"', "B's to B's");
  H.excludes(alerted, 'href="#invalid"', "no link to a section this page lacks");
  // 7. An ordinal line's method names the median level, not a mean.
  const rated = obs => ({ alternatives: [{ id: "x" }], cases: [{ id: "c1" }, { id: "c2" }], metrics: [{ id: "q", kind: "ordinal", levels: ["bad", "ok", "good"], better: "higher", primary: true }], observations: obs.map(([c, value]) => ({ alternative: "x", case: c, metric: "q", value })) });
  const ord = compare(pair(rated([["c1", "good"], ["c2", "bad"]]), rated([["c1", "good"], ["c2", "ok"]])));
  H.excludes(ord, "case-balanced means", "no mean of levels");
  H.includes(ord, "median level", "the statistic it computed");
});

test("a change's hover text names the cases it is taken over, and what it leaves out", () => {
  // The reference ran easy, hard and extra; the candidate easy and hard. The change covers easy and hard: (100% − 100% +
  // 50% − 0%) / 2 = +25 points.
  const t = F.gridTrial({ ref: { easy: "PP", hard: "FF", extra: "PF" }, cand: { easy: "PP", hard: "PF" } });
  t.baseline = "ref";
  const g = V.collectionModel({ members: [{ id: "a", trial: t, narrative: { baseline: "ref" } }] }).members[0].gains[0];
  H.equal(g.delta, 0.25, "the change over the shared cases");
  H.includes(g.method, "over easy and hard, each case weighted equally", "the cases named");
  H.includes(g.method, "ref ran 3 cases and cand 2; the line covers only the 2 both ran", "what it leaves out");
});

H.report();
