// Supplied text never becomes markup: every text-bearing field of a trial, a
// narrative and a specification renders as visible, escaped text.
"use strict";
const H = require("./harness.cjs");
const F = require("./fixtures.cjs");
const { test } = H;

const V = H.loadVisuals();
const trial = F.hostileTrial(), narrative = F.hostileNarrative(), spec = F.hostileSpec();
const outputs = {};

function noRawMarkup(name, html) {
  outputs[name] = html;
  const raw = F.rawHostileFields(html);
  if (raw.length) H.fail(`unescaped markup from: ${raw.join(", ")}`);
  H.excludes(html, "<x-hostile", "a raw hostile element");
}

function drawers(label, reportSpec) {
  const open = H.drawerOpener(V, reportSpec);
  return reportSpec.trial.runs.map((_, i) => {
    const html = open(i);
    H.ok(html.includes("av-drawer-head"), `${label}: run ${i} opened no drawer`);
    return html;
  }).join("\n");
}

test("trial data alone renders every field as text", () => {
  noRawMarkup("bare", V.renderReport(V.trialReport(trial)));
});

test("trial data with a narrative renders every field as text", () => {
  noRawMarkup("narrated", V.renderReport(V.trialReport(trial, narrative)));
});

test("the run drawer renders checks, judge reasons, excerpts and paths as text", () => {
  noRawMarkup("drawer-bare", drawers("bare", V.trialReport(trial)));
  noRawMarkup("drawer-narrated", drawers("narrated", V.trialReport(trial, narrative)));
});

test("a report specification renders every field as text", () => {
  noRawMarkup("spec", V.renderReport(spec));
});

test("every hostile field stays visible as escaped text", () => {
  for (const name of ["bare", "narrated", "drawer-bare", "drawer-narrated", "spec"]) H.ok(outputs[name], `the ${name} case did not run`);
  const all = Object.values(outputs).join("\n");
  const fields = F.hostileFields([trial, narrative, spec]);
  H.ok(fields.size > 80, `expected many hostile fields, found ${fields.size}`);
  const hidden = [...fields].filter(field => !all.includes(F.escapedHostile(field)));
  if (hidden.length) H.fail(`these fields are not visible anywhere: ${hidden.join(", ")}`);
});

test("escapeText escapes the five HTML-significant characters and rejects non-finite numbers", () => {
  H.equal(V.escapeText(`<a href="x" title='y'>&</a>`), "&lt;a href=&quot;x&quot; title=&#39;y&#39;&gt;&amp;&lt;/a&gt;", "escaped text");
  H.equal(V.escapeText(-0), "-0", "negative zero");
  H.throws(() => V.escapeText(NaN), /finite/, "NaN");
  H.throws(() => V.escapeText({}), /text or a number/, "an object");
});

test("inline emphasis applies only after escaping", () => {
  const html = V.renderBlock({ type: "text", text: "`<b>code</b>` and **<i>strong</i>**" }, V.createContext({}));
  H.includes(html, "<code>&lt;b&gt;code&lt;/b&gt;</code>", "escaped code");
  H.includes(html, "<strong>&lt;i&gt;strong&lt;/i&gt;</strong>", "escaped strong text");
});

test("an unknown block type is escaped in its notice", () => {
  const html = V.renderBlock({ type: F.hostile("block-type") }, V.createContext({}));
  H.equal(F.rawHostileFields(html), [], "raw fields");
  H.includes(html, F.escapedHostile("block-type"), "the escaped type name");
});

test("a renderer's error message is escaped in its notice", () => {
  const restore = V.registerBlock("hostile-error", () => { throw new Error(F.hostile("error-message")); });
  try {
    const html = V.renderBlock({ type: "hostile-error" }, V.createContext({}));
    H.equal(F.rawHostileFields(html), [], "raw fields");
    H.includes(html, F.escapedHostile("error-message"), "the escaped message");
  } finally { restore(); }
});

// Known library defects: fields that reach markup unescaped. Each case states
// the input; see the final report of the test run for the reproduction.
const one = blocks => V.renderReport({ title: "t", sections: [{ title: "s", blocks }] });
const noRaw = html => H.excludes(html, "<x-hostile", "a raw hostile element");

test("an excerpt's outcome is escaped", () => {
  noRaw(one([{ type: "excerpts", items: [{ text: "a", outcome: F.hostile("excerpt-outcome") }] }]));
});
test("a figure's tone is escaped", () => {
  noRaw(one([{ type: "figures", items: [{ value: 1, label: "a", tone: F.hostile("figure-tone") }] }]));
});
test("an intervals block's unit is escaped", () => {
  noRaw(one([{ type: "intervals", unit: F.hostile("intervals-unit"), rows: [{ label: "x", value: 4, lo: 2, hi: 6 }] }]));
});
test("ladder rows' counts are escaped when they are not numbers", () => {
  noRaw(one([{ type: "ladder", rows: [{ arm: "a", k: F.hostile("ladder-k"), n: 3 }, { arm: "b", k: 1, n: F.hostile("ladder-n") }] }]));
});
test("a trend point's n is escaped when it is not a number", () => {
  noRaw(one([{ type: "trend", stages: ["s1"], series: [{ label: "x", points: [{ stage: "s1", k: 1, n: F.hostile("trend-n"), value: 0.5 }] }] }]));
});
test("a run's seconds are escaped in the ledger when they are not a number", () => {
  const data = F.gridTrial({ a: { c: "PF" } });
  data.runs[0].seconds = F.hostile("run-seconds");
  noRaw(V.renderReport(V.trialReport(data)));
});
test("pairwise counts are escaped when they are not numbers", () => {
  const data = F.gridTrial({ a: { c: "P" }, b: { c: "F" } });
  data.pairwise = { "a__b": { arms: ["a", "b"], overall: { a_wins: F.hostile("pair-count"), b_wins: 1, tie: 0, inconsistent: 0, invalid: 0, pairs: 2, decisive: 2, a_win_rate: 0.5, a_win_rate_interval: [0.1, 0.9] }, scenarios: {} } };
  noRaw(V.renderReport(V.trialReport(data)));
});

H.report();
