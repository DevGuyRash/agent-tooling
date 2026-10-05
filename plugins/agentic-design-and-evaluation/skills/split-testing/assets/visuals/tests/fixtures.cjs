// Test data: a hostile trial, narrative and specification whose every
// text-bearing field carries markup, plus a small builder for trials with known
// outcomes. `node fixtures.cjs --write DIR` writes the hostile documents as
// JSON files for the Python report and browser tests.
"use strict";
const fs = require("node:fs");
const path = require("node:path");

/** Markup that breaks out of an attribute and opens an element. If any field
 * is inserted unescaped, `<x-hostile id="h-FIELD"` appears raw in the output,
 * naming the field. The escaped form is visible text. */
const hostile = field => `"'><x-hostile id="h-${field}">`;
const escapedHostile = field => `&lt;x-hostile id=&quot;h-${field}&quot;&gt;`;
const rawHostileFields = html => [...new Set([...html.matchAll(/<x-hostile id="h-([^"]+)"/g)].map(m => m[1]))];

const ARM_A = hostile("arm-a"), ARM_B = hostile("arm-b"), CASE_1 = hostile("case-1"), CASE_2 = "plain-case";

function hostileTrial() {
  const pair = (a, b, tie = 0) => ({ a_wins: a, b_wins: b, tie, inconsistent: 1, invalid: 1, pairs: a + b + tie + 2, decisive: a + b, a_win_rate: a / Math.max(1, a + b), a_win_rate_interval: [0.1, 0.9] });
  const run = fields => ({
    status: "ok", invalid_reason: null, commands: 3, seconds: 12.5, setup_seconds: 0.5, checks_seconds: 0.2, judge_seconds: 1.5,
    usage: { input_tokens: 1200, output_tokens: 240, [hostile("usage-key")]: 7 }, confined: true, artifact_missing: false,
    ...fields, valid: fields.passed !== null,
  });
  return {
    name: hostile("trial-name"),
    run_directory: hostile("run-directory"),
    plan: {
      arms: {
        [ARM_A]: { executor: hostile("arm-executor"), model: hostile("arm-model"), effort: "low", instructions_sha256: hostile("arm-digest") },
        [ARM_B]: { executor: "command", model: "fictional", effort: "low" },
      },
      scenarios: [
        { name: CASE_1, prompt: hostile("prompt"), followups: [hostile("followup")], judge: { question: hostile("judge-question") }, required: [hostile("required-check"), "reply_written"] },
        { name: CASE_2, prompt: "Plain prompt.", followups: [], judge: hostile("judge-question-text"), required: ["reply_written"] },
      ],
      judge: { executor: "command", model: hostile("judge-model") },
      decision_rule: hostile("decision-rule"),
    },
    runs: [
      run({ job: hostile("job"), scenario: CASE_1, arm: ARM_A, repeat: 1, passed: true,
        checks: { [hostile("required-check")]: true, reply_written: true, [hostile("measure-check")]: false, note: hostile("check-value"), words: 120 },
        judge: { verdict: "pass", reason: hostile("judge-reason") }, final_message_excerpt: hostile("excerpt") }),
      run({ job: "case-1__b__r1", scenario: CASE_1, arm: ARM_B, repeat: 1, passed: false,
        checks: { [hostile("required-check")]: false, reply_written: true, [hostile("measure-check")]: true, words: 80 },
        judge: { verdict: hostile("judge-verdict"), reason: "Plain reason." }, final_message_excerpt: "Plain excerpt." }),
      run({ job: "plain__a__r1", scenario: CASE_2, arm: ARM_A, repeat: 1, passed: null, status: hostile("status"),
        invalid_reason: hostile("invalid-reason"), checks: {}, judge: null, final_message_excerpt: hostile("invalid-excerpt") }),
      run({ job: "plain__b__r1", scenario: CASE_2, arm: ARM_B, repeat: 1, passed: true,
        checks: { reply_written: true }, judge: { verdict: "pass", reason: "Plain." }, final_message_excerpt: "Plain." }),
    ],
    pairwise: {
      [`${ARM_A}__${ARM_B}`]: { arms: [ARM_A, ARM_B], judge: { model: "fictional" }, overall: pair(3, 1), scenarios: { [CASE_1]: pair(2, 1), [CASE_2]: pair(1, 0, 1) } },
    },
  };
}

/** Every general block, with markup in each text field. `p` prefixes the field names. */
function generalBlocks(p) {
  const h = field => hostile(`${p}-${field}`);
  return [
    { type: "text", title: h("text-title"), description: h("text-description"), note: h("text-note"), text: [h("text-para"), "Second paragraph."] },
    { type: "callout", tone: "limit", title: h("callout-title"), label: h("callout-label"), text: h("callout-text") },
    { type: "list", ordered: true, items: [h("list-item"), { text: h("list-object"), detail: h("list-detail"), tone: "pass" }] },
    { type: "facts", items: [{ label: h("facts-label"), value: h("facts-value") }, { label: "Mono", value: h("facts-mono"), mono: true }, { label: "Absent", value: null }] },
    { type: "table", columns: [h("table-column"), "Value", "Number"], numeric: [2],
      rows: [[h("table-cell"), { value: h("table-object"), note: h("table-note"), status: "fail" }, 4], [{ value: h("table-mono"), mono: true }, null, 2.5]] },
    { type: "matrix", title: h("matrix-title"),
      columns: [{ id: "c1", label: h("matrix-column") }, { id: ARM_A, label: "ignored for arms", arm: true }],
      rows: [{ id: "r1", label: h("matrix-row"), detail: h("matrix-detail") }],
      cells: [{ row: "r1", column: "c1", status: "pass", text: h("matrix-text"), note: h("matrix-note") }, { row: "r1", column: ARM_A, status: "missing", note: h("matrix-missing-note") }] },
    { type: "intervals", reference: { value: 0.5, label: h("intervals-reference") },
      rows: [{ label: h("intervals-label"), note: h("intervals-note"), k: 3, n: 5 }, { label: "By arm", arm: ARM_A, value: 0.4, lo: 0.2, hi: 0.6 }] },
    { type: "bars", segments: [{ id: "s1", label: h("bars-segment"), tone: "pass" }, { id: "s2", label: "Other", tone: "fail" }],
      rows: [{ label: h("bars-row"), note: h("bars-note"), values: { s1: 3, s2: null } }, { label: "By arm", arm: ARM_B, values: { s1: 1, s2: 2 } }] },
    { type: "trend", title: h("trend-title"), stages: [h("trend-stage"), "Round 2"],
      series: [{ label: h("trend-series"), points: [{ stage: h("trend-stage"), k: 2, n: 4 }, { stage: "Round 2", k: 3, n: 4 }] }, { label: "Arm series", arm: ARM_A, points: [{ stage: "Round 2", value: 0.5 }] }] },
    { type: "excerpts", items: [{ text: h("excerpt-text"), source: h("excerpt-source"), note: h("excerpt-note"), arm: ARM_A, outcome: "fail" }] },
    { type: "diagram", title: h("diagram-title"), caption: h("diagram-caption"), source: `flowchart LR\n  %% ${h("diagram-source")}\n  A[Run] --> B[Checks]` },
    { type: "figures", items: [{ value: h("figures-value"), label: h("figures-label"), note: h("figures-note") }, { value: 12, label: "Runs" }] },
    { type: "verdict", verdict: "mixed", label: h("verdict-label"), headline: h("verdict-headline"), detail: h("verdict-detail"), rule: h("verdict-rule"),
      checks: [{ label: h("verdict-check"), observed: h("verdict-observed"), threshold: h("verdict-threshold"), met: false }],
      conditions: [h("verdict-condition")], limits: [h("verdict-limit")], changes: [h("verdict-change")] },
    { type: "ladder", title: h("ladder-title"), rows: [{ arm: ARM_A, k: 3, n: 4, invalid: 1, note: h("ladder-note") }, { arm: ARM_B, k: 1, n: 4 }] },
  ];
}

function hostileNarrative() {
  return {
    title: hostile("n-title"), question: hostile("n-question"), summary: hostile("n-summary"), kicker: hostile("n-kicker"),
    decision: {
      verdict: hostile("n-verdict-kind"), label: hostile("n-verdict-label"), headline: hostile("n-headline"), detail: hostile("n-detail"),
      checks: [{ label: hostile("n-rule-label"), observed: hostile("n-rule-observed"), threshold: hostile("n-rule-threshold"), met: null }],
      conditions: [hostile("n-condition")], limits: [hostile("n-limit")], changes: [hostile("n-change")],
    },
    arms: [{ id: ARM_A, label: hostile("n-arm-label-a"), note: hostile("n-arm-note") }, { id: ARM_B, label: hostile("n-arm-label-b") }],
    cases: { [CASE_1]: hostile("n-case-label") },
    identical: [[ARM_A, ARM_B]],
    groups: [{ label: hostile("n-group-label"), cases: [CASE_1], note: hostile("n-group-note") }],
    baseline: ARM_A,
    sections: [{ id: hostile("n-section-id"), title: hostile("n-section-title"), label: hostile("n-section-label"), lead: hostile("n-section-lead"), after: "verdict", blocks: generalBlocks("ns") }],
    append: { runs: [{ type: "text", title: hostile("n-append-title"), text: hostile("n-append-text") }] },
    footer: hostile("n-footer"),
  };
}

function hostileSpec() {
  return {
    title: hostile("s-title"), kicker: hostile("s-kicker"), summary: [hostile("s-summary"), "Second."], footer: hostile("s-footer"),
    meta: [{ label: hostile("s-meta-label"), value: hostile("s-meta-value") }],
    arms: [{ id: ARM_A, label: hostile("s-arm-label") }, { id: ARM_B }],
    sections: [{ title: hostile("s-section-title"), label: hostile("s-section-label"), lead: hostile("s-section-lead"), blocks: generalBlocks("sb") }],
  };
}

/** Fields whose hostile value is validated or replaced rather than displayed. */
const NOT_DISPLAYED = new Set(["n-verdict-kind", "n-section-id"]);

/** Every field name a document carries, read back from its hostile values. */
function hostileFields(value, found = new Set()) {
  if (typeof value === "string") { for (const m of value.matchAll(/<x-hostile id="h-([^"]+)"/g)) if (!NOT_DISPLAYED.has(m[1])) found.add(m[1]); }
  else if (Array.isArray(value)) value.forEach(v => hostileFields(v, found));
  else if (value && typeof value === "object") for (const [k, v] of Object.entries(value)) { hostileFields(k, found); hostileFields(v, found); }
  return found;
}

/** A trial from a compact outcome grid: { arm: { case: "PPF-" } } where P is a
 * pass, F a failure and - an invalid run (passed null). `extra(run)` may add
 * fields to each run. */
function gridTrial(grid, extra = () => ({})) {
  const runs = [];
  for (const [arm, cases] of Object.entries(grid)) for (const [scenario, marks] of Object.entries(cases)) {
    [...marks].forEach((m, i) => {
      const passed = m === "P" ? true : m === "F" ? false : null;
      const run = { job: `${scenario}__${arm}__r${i + 1}`, scenario, arm, repeat: i + 1, status: passed === null ? "timeout" : "ok", passed, valid: passed !== null, invalid_reason: passed === null ? "timeout" : null };
      runs.push({ ...run, ...extra(run) });
    });
  }
  const cases = [...new Set(runs.map(r => r.scenario))];
  return { name: "grid", plan: { arms: Object.fromEntries(Object.keys(grid).map(a => [a, { executor: "command" }])), scenarios: cases.map(name => ({ name, prompt: `Prompt for ${name}.`, required: [] })) }, runs };
}

if (require.main === module) {
  const at = process.argv.indexOf("--write");
  if (at < 0 || !process.argv[at + 1]) { process.stderr.write("error: missing --write DIR\nhint: node fixtures.cjs --write DIR\n"); process.exit(2); }
  const dir = process.argv[at + 1];
  fs.mkdirSync(dir, { recursive: true });
  for (const [name, value] of Object.entries({ "hostile-trial.json": hostileTrial(), "hostile-narrative.json": hostileNarrative(), "hostile-spec.json": hostileSpec() }))
    fs.writeFileSync(path.join(dir, name), JSON.stringify(value, null, 1) + "\n");
}

module.exports = { hostile, escapedHostile, rawHostileFields, hostileFields, hostileTrial, hostileNarrative, hostileSpec, generalBlocks, gridTrial, ARM_A, ARM_B, CASE_1, CASE_2 };
