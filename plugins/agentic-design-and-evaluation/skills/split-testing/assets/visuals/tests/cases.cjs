// The cases view (case dossiers): one entry per case in plan order with what it
// asked and what counted as a pass, then how every run went; variants of one
// case side by side; a pass-rate-by-case overview; every supplied text escaped.
"use strict";
const H = require("./harness.cjs");
const F = require("./fixtures.cjs");
const { test } = H;

const V = H.loadVisuals();

/** Render a cases block over `trial` inside a one-section report. */
function render(trial, block = {}, extra = {}) {
  return V.renderReport({ title: "Cases", sections: [{ id: "cases", title: "Cases", blocks: [{ type: "cases", ...block }] }], trial, ...extra });
}
const caseOrder = html => [...html.matchAll(/<article class="av-cs[^"]*" id="[^"]+" data-case="([^"]+)"/g)].map(m => m[1]);
const dossier = (html, name) => H.element(html, `data-case="${name}" aria-labelledby`);

function run(scenario, arm, repeat, passed, fields = {}) {
  return { job: `${scenario}__${arm}__r${repeat}`, scenario, arm, repeat, status: passed === null ? "timeout" : "ok", passed, valid: passed !== null, invalid_reason: passed === null ? "timeout" : null, ...fields };
}

/** Two arms; "fix" and "fix-review" share a prompt and differ by a follow-up;
 * "other" stands alone with a judge. */
function variantTrial() {
  const P = "Fix the limiter so it never runs more than four requests at once.";
  const runs = [];
  for (const arm of ["a", "b"]) for (let r = 1; r <= 3; r++) {
    runs.push(run("fix", arm, r, true, { checks: { limit_held: true, tests_pass: true } }));
    runs.push(run("fix-review", arm, r, r === 1, { checks: { limit_held: r === 1, tests_pass: true } }));
    runs.push(run("other", arm, r, r === 3 ? null : r === 1, { checks: { reply_written: true }, judge: r === 3 ? null : { verdict: r === 1 ? "pass" : "fail", reason: "Leaves out the deadline." } }));
  }
  return {
    name: "variants",
    plan: {
      arms: { a: { executor: "command" }, b: { executor: "command" } },
      judge: { executor: "command", model: "fictional" },
      scenarios: [
        { name: "fix", prompt: P, followups: [], required: ["limit_held", "tests_pass"], description: "A limiter that accepts started promises." },
        { name: "fix-review", prompt: P, followups: ["Before you finish, review your work."], required: ["limit_held", "tests_pass"], description: "A limiter that accepts started promises." },
        { name: "other", prompt: "Reply to the customer.", followups: [], required: ["reply_written"], judge: { question: "Is the reply accurate?", pass_when: "it names the new delivery date" }, judge_role: "You check one reply." },
      ],
    },
    runs,
  };
}

// ------------------------------------------------------------------ content

test("one dossier per case, in plan order, with its task and pass criterion", () => {
  const html = render(variantTrial(), { pairs: "off" });
  H.equal(caseOrder(html), ["fix", "fix-review", "other"], "dossier order");
  const other = dossier(html, "other");
  H.includes(other, "Reply to the customer.", "the prompt");
  H.includes(other, "Is the reply accurate?", "the judge question");
  H.includes(other, "it names the new delivery date", "the judge's pass criterion");
  H.includes(other, "You check one reply.", "the judge's framing");
  H.includes(other, "A run passed when its one required check held and the judge said pass.", "the pass rule");
  H.includes(other, "reply_<wbr>written", "the required check, breakable at underscores");
  H.includes(dossier(html, "fix-review"), "Before you finish, review your work.", "the follow-up");
  H.includes(dossier(html, "fix"), "A limiter that accepts started promises.", "the description");
});

test("long prompts collapse behind a disclosure; short ones show whole", () => {
  const t = variantTrial();
  t.plan.scenarios[2].prompt = Array.from({ length: 40 }, (_, i) => `Line ${i + 1} of a long request.`).join("\n");
  const html = render(t, { pairs: "off" });
  const other = dossier(html, "other"), fix = dossier(html, "fix");
  H.includes(other, '<details class="av-cs-more">', "a disclosure for the long prompt");
  H.includes(other, "Read the whole prompt", "the disclosure label");
  H.includes(other, '<div class="av-cs-short">', "the previews shown until the disclosure opens");
  H.includes(other, "Line 40 of a long request.", "the whole prompt inside the disclosure");
  H.excludes(fix, 'class="av-cs-more"', "a disclosure for a short prompt");
});

test("run marks open the drawer, and invalid runs are counted beside the rate, never as failures", () => {
  const t = variantTrial(), html = render(t, { pairs: "off" });
  const other = dossier(html, "other");
  const marks = [...other.matchAll(/<button type="button" class="av-run av-run--(pass|fail|invalid)" data-run="(\d+)"/g)];
  H.equal(marks.length, 6, "marks in the dossier");
  for (const [, outcome, i] of marks) {
    const r = t.runs[Number(i)];
    H.equal(r.scenario, "other", `run ${i} case`);
    H.equal(outcome, r.passed === true ? "pass" : r.passed === false ? "fail" : "invalid", `run ${i} outcome`);
  }
  // Per arm: one pass, one failure, one invalid run: 1 of 2 valid.
  H.ok(H.count(other, '<span class="av-frac"><b>1</b>/2</span>') >= 2, "per-arm 1/2 over valid runs");
  H.includes(other, "1 invalid", "the invalid chip");
  H.includes(other, "2 invalid runs, excluded from the rate and not counted as failures", "the invalid line");
  H.excludes(other, "<b>1</b>/3", "invalid runs counted as failures");
});

test("failed required checks are counted per arm and failure reasons are listed with a run to open", () => {
  const html = render(variantTrial(), { pairs: "off" });
  const review = dossier(html, "fix-review");
  H.includes(review, 'class="av-cs-why-chip"', "a failed-check chip");
  H.ok(/limit_<wbr>held<\/code><b>2<\/b>/.test(review), "limit_held failed in two runs of each arm");
  H.includes(review, "Why runs failed", "the reasons heading");
  H.ok(/<button type="button" class="av-cs-open" data-run="\d+"/.test(review), "a reason without a run to open");
  H.includes(review, 'av-cs-crit-cell--short', "the check that did not always hold is marked");
  H.includes(dossier(html, "fix"), "Every valid run passed.", "the all-passed state");
});

test("a case asked of a judge the plan does not name says why its runs are invalid", () => {
  const t = variantTrial();
  delete t.plan.judge;
  for (const r of t.runs) if (r.scenario === "other") Object.assign(r, { passed: null, status: "ok", invalid_reason: "judge-missing", judge: null });
  const other = dossier(render(t, { pairs: "off" }), "other");
  H.includes(other, "the plan names no judge", "the judge-missing explanation");
  H.includes(other, "No run of this case produced a valid result", "the no-valid-run state");
  H.includes(other, "<code>judge-missing</code> ×6", "the invalid reason and its count");
});

test("a judge that does not decide, and a case with no criterion, say so", () => {
  const t = variantTrial();
  t.plan.scenarios[2].judge_required = false;
  t.plan.scenarios[0].required = [];
  const html = render(t, { pairs: "off" });
  H.includes(dossier(html, "other"), "verdict was recorded but did not decide the pass", "a non-deciding judge");
  H.includes(dossier(html, "fix"), "every run that finished counted as a pass", "a case with no criterion");
});

test("missing description and prompt are shown, never blank", () => {
  const t = variantTrial();
  delete t.plan.scenarios[2].prompt;
  const html = render(t, { pairs: "off" });
  H.includes(dossier(html, "other"), "prompt not in this report", "the missing prompt");
  H.includes(dossier(html, "other"), "no description recorded", "the missing description");
});

// ------------------------------------------------------------------ variants

test("variants are detected when the prompt matches and one name extends the other", () => {
  const html = render(variantTrial());
  H.equal(caseOrder(html), ["fix", "other"], "the pair shares one dossier");
  const set = dossier(html, "fix");
  H.includes(set, 'class="av-cs av-cs--set"', "the variant dossier");
  H.includes(set, "<code>fix-review</code>", "the variant's name");
  H.includes(set, "Follow-up 1, only in <b>+ follow-up</b>", "what differs");
  H.includes(set, "same prompt and one name extends the other", "why they are shown together");
  // Per arm: base 3/3, variant 1/3, so one fewer… two fewer passes of three.
  H.includes(set, "−2 passes of 3 · −67 pts", "the difference per arm, its unit spelled out");
  H.includes(set, "95% −", "the difference's interval");
  H.includes(set, "All arms", "the pooled row");
  H.includes(set, "−4 passes of 6", "the pooled difference");
});

test("no auto pairing without the same prompt and an extending name, and pairs: off turns it off", () => {
  const t = variantTrial();
  t.plan.scenarios[1].prompt = "A different request.";
  H.equal(caseOrder(render(t)), ["fix", "fix-review", "other"], "different prompts paired");
  const u = variantTrial();
  for (const s of u.plan.scenarios) if (s.name === "fix-review") s.name = "fixreview";
  for (const r of u.runs) if (r.scenario === "fix-review") r.scenario = "fixreview";
  H.equal(caseOrder(render(u)), ["fix", "fixreview", "other"], "a name without a separator paired");
  H.equal(caseOrder(render(variantTrial(), { pairs: "off" })), ["fix", "fix-review", "other"], "pairs: off still paired");
});

test("explicit pairs pair what they name and report what they cannot", () => {
  const html = render(variantTrial(), { pairs: [{ base: "other", variant: "fix", label: "Named side" }, ["fix-review", "missing-case"]] });
  H.equal(caseOrder(html), ["fix-review", "other"], "explicit pairing, placed where its base case is");
  H.includes(dossier(html, "other"), "Named side", "the explicit label");
  H.includes(html, 'class="av-cs-notice" role="note"', "a visible notice");
  H.includes(html, "missing-case", "the unknown case named");
  const suffix = render(variantTrial(), { pairs: [{ suffix: "-review", label: "Reviewed", baseLabel: "Plain" }] });
  H.equal(caseOrder(suffix), ["fix", "other"], "suffix pairing");
  H.includes(dossier(suffix, "fix"), "Reviewed", "the suffix label");
  H.includes(dossier(suffix, "fix"), "Plain", "the base label");
});

test("groups head their cases; a variant set across groups takes the group labels instead", () => {
  const groups = [{ label: "Limiter", cases: ["fix", "fix-review"], note: "both limiter cases" }, { label: "Replies", cases: ["other"] }];
  const html = render(variantTrial(), { groups, pairs: "off" });
  H.equal(H.count(html, 'class="av-cs-group"'), 2, "group headings");
  H.includes(html, "both limiter cases", "the group note");
  const crossing = render(variantTrial(), { groups: [{ label: "As written", cases: ["fix", "other"] }, { label: "With a review turn", cases: ["fix-review"] }] });
  H.equal(H.count(crossing, 'class="av-cs-group"'), 0, "group headings across a variant set");
  H.includes(dossier(crossing, "fix"), "With a review turn", "the variant side named by its group");
});

// ------------------------------------------------------------------ shapes

test("a single-arm trial opens with the pass rate of every case", () => {
  const t = variantTrial();
  t.runs = t.runs.filter(r => r.arm === "a");
  delete t.plan.arms.b;
  const html = render(t, { pairs: "off" });
  H.includes(html, '<nav class="av-cs-index" aria-label="Pass rate by case">', "the overview");
  H.equal(H.count(html, 'class="av-cs-ix-row'), 3, "one overview row per case");
  H.includes(html, 'href="#av-case-other-', "rows link to their dossiers");
  const paired = render(t);
  H.equal(H.count(paired, 'class="av-cs-ix-row'), 3, "a variant keeps its own overview row");
  H.includes(paired, "av-cs-ix-row--variant", "the variant row is marked");
});

test("ten arms render one row per arm with its identity, and arms that did not run a case say so", () => {
  const grid = {};
  for (let i = 0; i < 10; i++) grid[`arm-${i}`] = i === 9 ? { one: "PF" } : { one: "PF-", two: "FP" };
  const t = F.gridTrial(grid);
  const html = render(t);
  const one = dossier(html, "one"), two = dossier(html, "two");
  H.equal(H.count(one, 'class="av-cs-arm" role="row"'), 10, "arm rows in a case all arms ran");
  H.equal(H.count(two, 'av-cs-arm--none'), 1, "the arm that did not run the case");
  H.includes(two, "not run on this case", "the not-run row");
  H.equal(new Set([...one.matchAll(/data-shape="([a-z-]+)"/g)].map(m => m[1])).size, 8, "distinct shapes");
  H.includes(html, '<nav class="av-cs-index" aria-label="Cases at a glance">', "the multi-arm overview");
  H.excludes(html, "av-block-error", "a render error");
});

test("the block is registered, reads its trial from the report, and fails visibly without one", () => {
  H.ok(V.blockTypes().includes("cases"), "cases is not a registered block type");
  const spec = { title: "No trial", sections: [{ title: "S", blocks: [{ type: "cases" }] }] };
  const html = V.renderReport(spec);
  H.includes(html, "The cases block could not render.", "a visible notice");
  H.includes(html, "needs trial data", "the reason");
});

test("unknown cases and arms named by the block are reported, not drawn", () => {
  const html = render(variantTrial(), { cases: ["other", "nope"], arms: ["a", "ghost"], pairs: "off" });
  H.equal(caseOrder(html), ["other"], "only the named known case");
  H.includes(html, "Cases not in this trial were left out: nope.", "the unknown case notice");
  H.includes(html, "Arms not in this trial were left out: ghost.", "the unknown arm notice");
  H.excludes(html, 'data-arm="ghost"', "a phantom arm");
});

// ------------------------------------------------------------------ escaping

test("every supplied text in the cases view renders as escaped, visible text", () => {
  const h = F.hostile, P = h("cs-prompt");
  const A = h("cs-arm"), C1 = h("cs-case"), C2 = `${C1}-${h("cs-suffix")}`;
  const trial = {
    name: "hostile",
    plan: {
      arms: { [A]: { executor: "command" }, plain: { executor: "command" } },
      judge: { executor: "command" },
      scenarios: [
        { name: C1, prompt: P, followups: [], required: [h("cs-check")], description: h("cs-description"), artifact: h("cs-artifact"),
          judge: { question: h("cs-question"), pass_when: h("cs-pass-when") }, judge_role: h("cs-role") },
        { name: C2, prompt: P, followups: [h("cs-followup")], required: [h("cs-check")], description: h("cs-description"), artifact: h("cs-artifact"),
          judge: { question: h("cs-question"), pass_when: h("cs-pass-when") }, judge_role: h("cs-role") },
        { name: "solo", prompt: "Plain.", followups: [], required: [], judge: h("cs-judge-text") },
      ],
    },
    runs: [
      run(C1, A, 1, false, { checks: { [h("cs-check")]: true }, judge: { verdict: "fail", reason: h("cs-judge-reason") } }),
      run(C1, A, 2, false, { checks: { [h("cs-check")]: false }, judge: { verdict: "pass", reason: "Plain." } }),
      run(C1, "plain", 1, null, { status: h("cs-status"), invalid_reason: h("cs-invalid-reason") }),
      run(C2, A, 1, false, { checks: { [h("cs-check")]: true }, judge: { verdict: h("cs-verdict"), reason: "Plain." } }),
      run(C2, "plain", 1, true, { checks: { [h("cs-check")]: true }, judge: { verdict: "pass" } }),
      run("solo", A, h("cs-repeat"), true, { checks: {} }),
    ],
  };
  const spec = { cases: { solo: h("cs-label") }, arms: [{ id: A, label: h("cs-arm-label") }, { id: "plain" }] };
  const outputs = [
    render(trial, { title: h("cs-title"), description: h("cs-block-description"), note: h("cs-note") }, spec),
    render(trial, { pairs: [{ base: C1, variant: C2, label: h("cs-pair-label"), baseLabel: h("cs-base-label") }, [h("cs-unknown-pair"), C1]], cases: [C1, C2, "solo", h("cs-unknown-case")], arms: [A, "plain", h("cs-unknown-arm")] }, spec),
    render(trial, { pairs: "off", groups: [{ label: h("cs-group-label"), cases: [C1, "solo"], note: h("cs-group-note") }] }, spec),
    render(trial, { pairs: [{ suffix: `-${h("cs-suffix")}`, label: "x" }, { suffix: h("cs-bad-suffix") }] }, spec),
  ];
  const all = outputs.join("\n");
  const raw = F.rawHostileFields(all);
  if (raw.length) H.fail(`unescaped markup from: ${raw.join(", ")}`);
  H.excludes(all, "<x-hostile", "a raw hostile element");
  const fields = ["cs-prompt", "cs-arm", "cs-case", "cs-suffix", "cs-check", "cs-description", "cs-artifact", "cs-question", "cs-pass-when", "cs-role",
    "cs-followup", "cs-judge-text", "cs-judge-reason", "cs-invalid-reason", "cs-verdict", "cs-label", "cs-arm-label", "cs-title", "cs-block-description",
    "cs-note", "cs-pair-label", "cs-base-label", "cs-unknown-pair", "cs-unknown-case", "cs-unknown-arm", "cs-group-label", "cs-group-note", "cs-bad-suffix"];
  const hidden = fields.filter(f => !all.includes(F.escapedHostile(f)));
  if (hidden.length) H.fail(`these fields are not visible anywhere: ${hidden.join(", ")}`);
  H.excludes(all, `data-run="${h("cs-repeat")}"`, "a supplied value in a run index");
  H.includes(outputs[0], "repeat ?", "a non-numeric repeat shown as unknown");
});

H.report();
