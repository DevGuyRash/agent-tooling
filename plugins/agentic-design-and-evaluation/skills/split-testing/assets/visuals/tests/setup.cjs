// The "What was compared" view (block type setup) and the line diff behind it:
// shared settings on one line, a table of only the settings that differ,
// identical-material chips, lettered texts with a diff from a reference text,
// truncation and absence stated, artifacts treated alike, case variants, and
// every supplied text escaped.
"use strict";
const fs = require("node:fs");
const path = require("node:path");
const H = require("./harness.cjs");
const F = require("./fixtures.cjs");
const { test } = H;

const V = H.loadVisuals();
const example = JSON.parse(fs.readFileSync(path.join(H.VISUALS, "examples", "fictional-trial.json"), "utf8"));
const exampleNarrative = JSON.parse(fs.readFileSync(path.join(H.VISUALS, "examples", "fictional-narrative.json"), "utf8"));

/** Render one setup block against a trial (and optional identity order). */
function setup(trial, input = {}, arms = []) {
  return V.renderBlock({ type: "setup", ...input }, V.createContext({ trial, arms }));
}
/** A trial with the given plan arms; every arm runs every case once. */
function trialWith(arms, extra = {}) {
  const cases = extra.cases || ["c1", "c2"];
  const runs = [];
  for (const arm of Object.keys(arms)) for (const scenario of cases) runs.push({ job: `${scenario}__${arm}`, scenario, arm, repeat: 1, passed: true, status: "ok" });
  return { name: "t", plan: { arms, scenarios: cases.map(name => ({ name, prompt: `Prompt ${name}.` })), ...(extra.plan || {}) }, runs: extra.runs || runs, ...(extra.top || {}) };
}
const differs = html => html.includes("av-setup-table") ? [...H.element(html, "<thead").matchAll(/<th scope="col"[^>]*>([^<]*)<\/th>/g)].map(m => m[1]).slice(1) : [];
const shared = html => html.includes("av-setup-shared") ? [...H.element(html, 'class="av-setup-shared"').matchAll(/<dt[^>]*>([^<]*)<\/dt>/g)].map(m => m[1]) : [];

// ------------------------------------------------------------------ line diff

/** The texts a diff came from, rebuilt from its lines. */
function rebuild(lines) {
  return { a: lines.filter(l => l.op !== "add").map(l => l.text), b: lines.filter(l => l.op !== "del").map(l => l.text) };
}

test("lineDiff keeps both texts and numbers every line", () => {
  const a = "one\ntwo\nthree\nfour\nfive", b = "one\nTWO\nthree\nfive\nsix";
  const d = H.plain(V.lineDiff(a, b));
  H.equal(rebuild(d), { a: a.split("\n"), b: b.split("\n") }, "texts rebuilt from the diff");
  H.equal(d.map(l => l.op).join(","), "same,del,add,same,del,same,add", "edit script");
  H.equal(d.filter(l => l.op !== "add").map(l => l.a), [1, 2, 3, 4, 5], "line numbers in the first text");
  H.equal(d.filter(l => l.op !== "del").map(l => l.b), [1, 2, 3, 4, 5], "line numbers in the second text");
  H.ok(d.every(l => (l.op === "add") === (l.a === undefined) && (l.op === "del") === (l.b === undefined)), "an added line has no first-text number and a removed line no second-text number");
});

test("lineDiff finds a shortest edit script and puts removals before additions", () => {
  const a = ["a", "b", "c", "a", "b", "b", "a"].join("\n"), b = ["c", "b", "a", "b", "a", "c"].join("\n");
  const d = H.plain(V.lineDiff(a, b));
  H.equal(d.filter(l => l.op !== "same").length, 5, "edits in the shortest script (Myers' example)");
  H.equal(rebuild(d), { a: a.split("\n"), b: b.split("\n") }, "texts rebuilt");
  for (let i = 1; i < d.length; i++) H.ok(!(d[i - 1].op === "add" && d[i].op === "del"), "an addition directly before a removal");
});

test("lineDiff treats line endings alike and handles empty and identical texts", () => {
  H.equal(H.plain(V.lineDiff("a\r\nb\r\n", "a\nb")).map(l => l.op), ["same", "same"], "CRLF and a final line break");
  H.equal(H.plain(V.lineDiff("", "")), [], "two empty texts");
  H.equal(H.plain(V.lineDiff("", "x\ny")).map(l => `${l.op}:${l.text}`), ["add:x", "add:y"], "from nothing");
  H.equal(H.plain(V.lineDiff("x\ny", "")).map(l => `${l.op}:${l.text}`), ["del:x", "del:y"], "to nothing");
  H.equal(H.plain(V.lineDiff("same\ntext", "same\ntext")).map(l => l.op), ["same", "same"], "identical texts");
  H.equal(H.plain(V.lineDiff("a\n\nb", "a\nb")).map(l => `${l.op}:${l.text}`), ["same:a", "del:", "same:b"], "a removed blank line");
});

test("lineDiff stays fast and exact on long texts", () => {
  const a = Array.from({ length: 4000 }, (_, i) => `line ${i}`), b = a.slice();
  b.splice(10, 1, "changed early"); b.splice(2500, 0, "inserted"); b.splice(3990, 3);
  const started = Date.now();
  const d = H.plain(V.lineDiff(a.join("\n"), b.join("\n")));
  H.ok(Date.now() - started < 2000, `took ${Date.now() - started} ms`);
  H.equal(rebuild(d), { a, b }, "texts rebuilt");
  H.equal(d.filter(l => l.op !== "same").length, 6, "edits");
  const unrelated = H.plain(V.lineDiff(Array.from({ length: 3000 }, (_, i) => `a${i}`).join("\n"), Array.from({ length: 3000 }, (_, i) => `b${i}`).join("\n")));
  H.equal(unrelated.length, 6000, "two unrelated texts: every line removed and added");
});

// ------------------------------------------------------------------ the view

const ARMS = {
  base: { executor: "codex", model: "m-1", effort: "low", model_spec: "${MODEL:-latest:m-*}", instructions_sha256: "a".repeat(64), instructions_text: "Intro\nKeep it short.\nBe kind.\n", instructions_truncated: false },
  copy: { executor: "codex", model: "m-1", effort: "low", model_spec: "${MODEL:-latest:m-*}", instructions_sha256: "a".repeat(64), instructions_text: "Intro\nKeep it short.\nBe kind.\n", instructions_truncated: false },
  tight: { executor: "codex", model: "m-1", effort: "high", model_spec: "${MODEL:-latest:m-*}", instructions_sha256: "b".repeat(64), instructions_text: "Intro\nKeep it very short.\nBe kind.\nCheck facts.\n", instructions_truncated: false },
};

test("only settings that differ become columns; the rest share one line", () => {
  const html = setup(trialWith(ARMS));
  H.equal(differs(html), ["Instructions", "Effort"], "columns");
  H.equal(shared(html), ["Executor", "Model"], "shared settings");
  H.excludes(html, ">Model spec<", "a model_spec column");
  H.includes(html, 'title="As written in the plan: ${MODEL:-latest:m-*}"', "model_spec as the model's tooltip");
  H.includes(html, "differ only in <strong>instructions</strong> (2 distinct texts) and <strong>effort</strong>", "the one-sentence difference");
});

test("commands, codex settings and other recorded fields are compared like any setting", () => {
  const html = setup(trialWith({
    good: { executor: "command", command: 'sh "$DIR/good.sh"' },
    bad: { executor: "command", command: 'sh "$DIR/bad.sh"' },
    hook: { executor: "command", command: "true", codex_config: ["hooks.Stop=[{hooks=[{type=\"command\",command=\"python3 stop.py\"}]}]"], codex_trust_hooks: true, base_url: "https://example.invalid" },
  }));
  H.equal(differs(html), ["Base URL", "Command", "Codex config", "Trusts hooks"], "columns");
  H.includes(html, "sh &quot;$DIR/good.sh&quot;", "a command");
  H.includes(html, "hooks.Stop=[{hooks=[{type=&quot;command&quot;", "a codex config entry");
  H.ok((html.match(/>not set</g) || []).length >= 6, "an unset value is shown, not blank");
});

test("hide leaves a setting out of the view but not out of the comparison", () => {
  const arms = { a: { executor: "claude", base_url: "https://one.invalid" }, b: { executor: "claude", base_url: "https://two.invalid" } };
  const html = setup(trialWith(arms), { hide: ["base_url"] });
  H.excludes(html, "one.invalid", "the hidden value");
  H.excludes(html, ">identical material<", "an identical chip for arms that differ in a hidden setting");
});

test("arm notes sit on their own line under the arm", () => {
  const html = setup(trialWith(ARMS), {}, [{ id: "base", label: "Base" }, { id: "copy", label: "Copy", note: "same text, run again" }, { id: "tight" }]);
  const cell = H.element(html, 'data-arm="copy"><th');
  H.includes(cell, '</span><span class="av-setup-note">same text, run again</span>', "the note after the arm tag, in its own element");
});

test("identical material is marked, and a listed group that differs is flagged", () => {
  const auto = setup(trialWith(ARMS));
  H.equal((auto.match(/>identical material</g) || []).length, 2, "both copies marked without being listed");
  const listed = setup(trialWith(ARMS), { identical: [["base", "tight"]] });
  H.includes(listed, ">listed as identical<", "a warning chip");
  H.includes(listed, "but differs from tight in instructions and effort", "what differs");
});

test("each distinct text gets a letter in identity order, and arms link to it", () => {
  const html = setup(trialWith(ARMS), {}, [{ id: "tight" }, { id: "base" }, { id: "copy" }]);
  const rows = [...html.matchAll(/<tr role="row" data-arm="([^"]+)">[\s\S]*?class="av-setup-letter" aria-hidden="true">([A-Z]+)</g)].map(m => `${m[1]}:${m[2]}`);
  H.equal(rows, ["tight:A", "base:B", "copy:B"], "letters by first use");
  const anchors = [...html.matchAll(/class="av-setup-mat" href="#([^"]+)"/g)].map(m => m[1]);
  for (const a of anchors) H.includes(html, `id="${a}"`, `the text ${a} a chip links to`);
  H.includes(html, "<details class=\"av-setup-text\"", "texts are expandable");
  H.includes(html, "Keep it very short.", "the text itself");
});

test("diffs run from the baseline's text when there is one, and from Text A otherwise", () => {
  const plain = setup(trialWith(ARMS), {}, [{ id: "tight" }, { id: "base" }]);
  H.includes(plain, "Changes from Text A", "a diff from the first text");
  H.excludes(plain, "the baseline", "a baseline the input never named");
  const based = setup(trialWith(ARMS), { baseline: "base" }, [{ id: "tight" }, { id: "base" }]);
  H.includes(based, "Changes from Text B (the baseline’s text)", "a diff from the baseline's text");
  const diff = H.element(based, 'class="av-diff"');
  H.includes(diff, '<div class="av-diff-row av-diff-row--del">', "a removed line");
  H.includes(diff, '<span class="av-diff-sign" aria-hidden="true">+</span>', "an added line's sign");
  H.ok(/<mark class="av-diff-word">\s?very\s?<\/mark>/.test(diff), "the changed words of a replaced line");
  H.includes(diff, '<span class="av-setup-sr">Added: </span>Check facts.', "an added line in words for screen readers");
  H.includes(based, "+ 2 lines added", "lines added");
  H.includes(based, "− 1 line removed", "lines removed");
});

test("long unchanged stretches fold, short ones stay", () => {
  const body = Array.from({ length: 30 }, (_, i) => `rule ${i}`);
  const arms = { a: { instructions_sha256: "c".repeat(64), instructions_text: body.join("\n") }, b: { instructions_sha256: "d".repeat(64), instructions_text: [...body.slice(0, 15), "new rule", ...body.slice(15)].join("\n") } };
  const html = setup(trialWith(arms));
  H.equal([...html.matchAll(/<details class="av-diff-fold"><summary><span>(\d+) unchanged lines/g)].map(m => Number(m[1])), [12, 12], "folds around one change");
  const short = { a: { instructions_text: "x\ny\nz" }, b: { instructions_text: "x\ny\nz\nw" } };
  H.excludes(setup(trialWith(short)), "av-diff-fold", "a fold for three unchanged lines");
});

test("truncation and absence are stated, never silent", () => {
  const arms = {
    cut: { instructions_sha256: "e".repeat(64), instructions_text: "Only the start", instructions_truncated: true },
    gone: { instructions_sha256: "f".repeat(64) },
    whole: { instructions_sha256: "1".repeat(64), instructions_text: "Only the start\nand the rest" },
    none: { executor: "command" },
  };
  const html = setup(trialWith(arms, { top: { run_directory: "trials/x" } }));
  H.includes(html, "Cut for this report after 14 characters; the whole text is in <code>trials/x/instructions/</code>", "the truncation note");
  H.includes(html, "Not included in this report. The run directory keeps it in <code>trials/x/instructions/</code>, named by its digest <code>ffffffffff…</code>", "the absence note");
  H.includes(html, ">not in this report<", "the absence flag");
  H.includes(html, "Only the part of each text included in this report is compared: Text A was cut.", "a diff of a cut text says so");
  H.includes(html, "1 arm received none", "an arm without instructions");
  H.includes(H.element(html, 'data-arm="none"><th'), ">none<", "the arm's instructions cell");
});

test("artifact texts are lettered and compared like instructions", () => {
  const arms = {
    v1: { executor: "artifact", artifact_sha256: "1".repeat(64), artifact_text: "--- a.md ---\nold line\n" },
    v2: { executor: "artifact", artifact_sha256: "2".repeat(64), artifact_text: "--- a.md ---\nnew line\n" },
  };
  const html = setup(trialWith(arms));
  H.equal(differs(html), ["Artifact"], "columns");
  H.includes(html, "Artifact A", "the first artifact");
  H.includes(html, "Changes from Artifact A", "a diff between artifacts");
  H.includes(html, '<span class="av-eyebrow">Artifacts</span>', "an artifacts heading");
});

test("a single arm shows all of its settings and no comparison table", () => {
  const one = { solo: { executor: "codex", model: "m", codex_config: ["x=1", "y=2"], instructions_sha256: "9".repeat(64), instructions_text: "Do the work." } };
  const html = setup(trialWith(one));
  H.excludes(html, "av-setup-table", "a comparison table");
  H.includes(html, "One arm ran, so no arms are compared", "the single-arm sentence");
  H.equal(shared(html), ["Instructions", "Executor", "Model", "Codex config"], "every setting");
  H.includes(html, '<span class="av-eyebrow">Settings</span>', "the settings heading");
});

test("a subset of arms is compared among itself; unknown ids are named, not drawn", () => {
  const html = setup(trialWith(ARMS), { arms: ["base", "copy", "ghost"] });
  H.excludes(html, 'data-arm="tight"', "an arm outside the subset");
  H.includes(html, "All 2 arms received the same recorded settings and material", "the two copies compared alone");
  H.includes(html, "Not in this trial, so not shown: ghost.", "the unknown id");
  H.excludes(html, 'data-arm="ghost"', "a phantom arm");
});

test("planned arms that never ran, and arms without recorded settings, are said so", () => {
  const data = trialWith({ ran: { executor: "command" }, idle: { executor: "command" } });
  data.runs = data.runs.filter(r => r.arm === "ran").concat([{ job: "x", scenario: "c1", arm: "stray", repeat: 1, passed: false }]);
  const html = setup(data);
  H.includes(html, "Planned but never run: idle.", "the arm that never ran");
  H.includes(html, ">no recorded settings<", "the arm with runs but no plan entry");
  H.includes(html, "Not every arm ran every case", "a warning that arms ran different cases");
  H.includes(html, "Only one of the 2 arms has recorded settings, so this view cannot show how they differ. stray has no recorded settings.", "the sentence never claims the arms match");
  H.includes(H.element(html, 'data-arm="stray"><th'), ">not recorded<", "the unrecorded arm's cells");
  const bare = { name: "old", runs: [{ scenario: "c", arm: "x", passed: true }, { scenario: "c", arm: "y", passed: false }] };
  const old = setup(bare);
  H.includes(old, "The plan records no settings for these arms, so this view cannot show what they received.", "a trial without plan arms");
  H.excludes(old, "same recorded settings", "a claim that the arms match");
});

test("explicit settings render without trial data; neither is a visible error", () => {
  const html = V.renderBlock({ type: "setup", settings: { x: { model: "a" }, y: { model: "b" } }, judge: { executor: "command", model: "j" } }, V.createContext({}));
  H.equal(differs(html), ["Model"], "columns from explicit settings");
  H.includes(html, '<span class="av-eyebrow">Judge</span>', "the judge line");
  const none = V.renderBlock({ type: "setup" }, V.createContext({}));
  H.includes(none, "av-block-error", "a visible notice");
  H.includes(none, "needs trial data", "what is missing");
});

test("case variants show the turns they add, once for all variants that add the same", () => {
  const followup = "Before you finish, review your work.";
  const data = trialWith({ solo: { executor: "codex" } }, { cases: ["fix", "fix-review", "port", "port-review"] });
  data.plan.scenarios = [
    { name: "fix", prompt: "Fix it.", followups: [] }, { name: "fix-review", prompt: "Fix it.", followups: [followup] },
    { name: "port", prompt: "Port it.", followups: [] }, { name: "port-review", prompt: "Port it.", followups: [followup] },
  ];
  const html = setup(data);
  H.includes(html, "the comparison is between 2 cases and their variants, which add a follow-up turn", "the single-arm sentence");
  H.equal((html.match(/Before you finish, review your work\./g) || []).length, 1, "the shared turn shown once");
  H.includes(html, "added in 2 variants", "how many variants add it");
  H.includes(html, "<code>fix</code></span><span class=\"av-setup-arrow\" aria-hidden=\"true\">→</span>", "the pair list");
  H.excludes(setup(data, { pairs: "off" }), "Case variants", "variants switched off");
});

test("the default composition puts the setup view second and the example shows its texts", () => {
  const spec = V.trialReport(example, exampleNarrative);
  H.equal(spec.sections[1] && spec.sections[1].id, "setup", "the second section");
  const html = V.renderReport(spec);
  const block = H.element(html, 'class="av-block av-block--setup"');
  H.includes(block, "differ only in <strong>instructions</strong> (3 distinct texts)", "the difference in one sentence");
  H.equal((block.match(/class="av-setup-text"/g) || []).length, 3, "three lettered texts");
  H.includes(block, "Changes from Text A (the baseline’s text)", "diffs from the baseline's text");
  H.includes(block, '<mark class="av-diff-word">warm</mark>', "the worked example's changed word");
  H.equal((block.match(/>identical material</g) || []).length, 2, "the two copies of the current guidance");
  H.excludes(block, "listed as identical", "a false warning about the copies");
});

// ------------------------------------------------------------------ escaping

test("every supplied text in the setup view renders as escaped text", () => {
  const h = F.hostile;
  const A = h("setup-arm-a"), B = h("setup-arm-b"), C1 = h("setup-case");
  const arms = {
    [A]: { executor: h("setup-executor"), model: h("setup-model"), model_spec: h("setup-model-spec"), effort: "low", instructions_sha256: h("setup-digest-a"), instructions_text: `${h("setup-text-a")}\nshared line`, command: h("setup-command"),
      codex_config: [h("setup-config-entry"), "b=2"], allowed_tools: [h("setup-tool")], stub_skills: { dir: h("setup-stub-dir"), count: 2 }, [h("setup-key")]: h("setup-key-value"), resources_sha256: h("setup-resources-digest") },
    [B]: { executor: "command", model: "plain", instructions_sha256: "0".repeat(64), instructions_text: `${h("setup-text-b")}\nshared line`, instructions_truncated: true,
      artifact_sha256: h("setup-artifact-digest"), artifact_text: h("setup-artifact-text"), resources: [h("setup-resource-path")] },
    [h("setup-planned")]: { executor: "command" },
  };
  const data = {
    name: "x", run_directory: h("setup-run-directory"),
    plan: {
      arms, judge: { executor: "command", model: h("setup-judge-model"), model_spec: h("setup-judge-spec") },
      scenarios: [{ name: C1, prompt: "Same prompt.", followups: [] }, { name: "plain-variant", prompt: "Same prompt.", followups: [h("setup-followup")] }],
    },
    runs: [A, B].flatMap(arm => [C1, "plain-variant"].map(scenario => ({ job: "j", scenario, arm, repeat: 1, passed: true }))),
  };
  const ctx = V.createContext({ trial: data, arms: [{ id: A, label: h("setup-label"), note: h("setup-note") }, { id: B }] }, { [C1]: h("setup-case-label") });
  const html = V.renderBlock({ type: "setup", title: h("setup-title"), description: h("setup-description"), note: h("setup-block-note"), arms: [A, B, h("setup-unknown")], identical: [[A, B]], baseline: B }, ctx);
  H.equal(F.rawHostileFields(html), [], "raw fields");
  const expected = ["setup-arm-a", "setup-arm-b", "setup-executor", "setup-model", "setup-model-spec", "setup-digest-a", "setup-text-a", "setup-text-b", "setup-command", "setup-config-entry",
    "setup-tool", "setup-stub-dir", "setup-key", "setup-key-value", "setup-resources-digest", "setup-artifact-digest", "setup-artifact-text", "setup-resource-path", "setup-judge-model", "setup-judge-spec",
    "setup-run-directory", "setup-case", "setup-case-label", "setup-followup", "setup-label", "setup-note", "setup-unknown", "setup-title", "setup-description", "setup-block-note"];
  const hidden = expected.filter(f => !html.includes(F.escapedHostile(f)));
  if (hidden.length) H.fail(`not visible as escaped text: ${hidden.join(", ")}`);
  const planned = V.renderBlock({ type: "setup" }, V.createContext({ trial: data }));
  H.equal(F.rawHostileFields(planned), [], "raw fields without a subset");
  H.includes(planned, F.escapedHostile("setup-planned"), "a planned arm's escaped id");
});

test("non-finite and odd values never reach markup as blank or raw", () => {
  const html = setup(trialWith({ a: { executor: "command", count: Infinity, list: [], obj: {} }, b: { executor: "command", count: 3, list: ["x"], obj: { k: 1 } } }));
  H.includes(html, ">not a number<", "a non-finite number");
  H.includes(html, ">empty<", "an empty list or object");
  H.excludes(html, "Infinity", "a raw non-finite value");
});

H.report();
