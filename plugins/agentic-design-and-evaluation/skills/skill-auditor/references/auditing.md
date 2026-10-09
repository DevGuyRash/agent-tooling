# Auditing

## What an audit decides

An audit gives each unit (a line, a section, a skill, a resource, a script) one verdict: keep, cut, move, or rewrite, with its evidence. Reading the target produces hypotheses about behavior; a behavior trial decides them (the [trial runtime](../../split-testing/references/trials.md), with scenarios in the target repository's evaluation suite when it has one). Say which verdicts rest on reading alone. A unit with a measured cost and no detected benefit is a candidate to cut; a boundary that encodes the user's policy stays on its hazard, not on recent failures.

Read the target as its executors will: a literal reader that does exactly what it says and a liberal one that substitutes judgment for anything unmarked, each alongside everything else it loads (the host's system prompt, the user's global file, sibling skills). Source text, the installed copy, catalog exposure, activation, execution, and downstream use are different properties with different evidence.

## Defect shapes

Each shape is a common way instructions go wrong, with its usual repair. The list is a field guide, not the categories of an answer.

- **Restated generic duty.** A skill repeats how to verify, report, finish, or ask. Repair: delete; those duties belong to the always-loaded layer or the host.
- **Local finish line.** A skill declares when the whole task is done, or its method's unit (an increment, a round, a slice) becomes the task's unit. Repair: the skill states its own operation's success and hazards; the user's request sets the finish.
- **Repair by accretion.** A correction is added beside the text that caused the problem, often as a prohibition that restates the unwanted behavior. Repair: rewrite or remove the cause. In trials, such prohibitions added nothing measurable while the text grew.
- **Loose gate.** A consequential action is gated without its exact release condition ("get approval before production"), so an executor reads the request itself as the approval. Repair: name the action and the condition that releases it ("SHALL NOT run it until the user approves in reply"). In trials, the loose form let 6 of 10 executors deploy unasked; the exact form, none.
- **Cheaper exit.** A duty offers an alternative that costs less than the duty itself, such as reporting a failure instead of fixing it, or a gate scoped to steps that are "hard to undo", which exempts every step an executor judges easy to reverse. Executors tend to take the cheaper branch. Unlike a loose gate, the condition can be precise and still be chosen over the duty. Repair: remove the alternative, hold it to the same standard as the duty, or name the exits and close them. In trials, adding "or you have told the user what they report and why" to a duty to run the tests and see them pass lowered passes from 12 of 12 runs to 7 of 12 (gpt-6-luna; small-change-proportion 1/3, sd-bugfix 1/3). An authority gate whose list ended "or take a similar step that is hard to undo" was read the same way until its repair closed the exits: "needing it to finish, being able to undo it, or finding a route around a gate grants nothing."
- **Ask-first repetition.** Approval language on routine steps produces asking at every step. Repair: gate only what the user's policy requires.
- **Snapshot baked into standing text.** What a file does today, what was run, or how the text came to be, written into a skill or instruction file, goes stale. Repair: move it to the reply or a one-time brief.
- **Unreachable continuation.** A recurring prompt, heartbeat, or handoff whose stop is "until the remaining work is complete". Repair: an observable finished state and a blocked exit.
- **Agent text as mandate.** Plans, state files, or summaries written by agents extend scope or speak as the user. Repair: keep the user's words as the user's, quoted with source; agent text records intentions.
- **Condition of degree and certainty demand.** "Where material", "sufficiently", "ensure fully verified" leave a literal reader no point of compliance, and cautious readers resolve them toward more work. Repair: an observable condition, or what suffices.
- **Weight without meaning.** Capitals, repetition, and emphasis add force without adding a reason. Repair: a precise statement, placed where it applies.
- **Catch-all description or mandatory load.** A description that matches most requests, or text that demands a large reference on every activation. Repair: name the capability and the situations it fits; load depth behind a condition.
- **Misplaced mechanism.** A script, hook, or parser makes a decision the executor should make from the request, or prose asks the executor to enforce what a check or permission enforces better. Repair: move the control to where it works.
- **Correction without an exit.** Guidance that compensates for one model's or host's habit without naming it and what would retire it.
- **Obligation behind a link.** What the executor must do is stated only in a reference or a skill it has to select; low-effort executors seldom open either. Repair: state it in the entry or the always-loaded layer, and keep elaboration in the reference.
- **Default as output.** Whatever a skill offers executors to copy or accept, such as a template, a starter, or a tool's default, becomes the result wherever they are not made to choose, and the more of it there is, the more of the result it decides. Repair: offer nothing to copy where the choice matters, or only as much as the task needs; require the choice at a step the executor already takes; and treat the default itself as no choice.
- **Incident as rule.** A rule that names the incident that revealed it, its files, tools, numbers, or wording, instead of the condition under which it holds and the outcome it protects. It governs only cases that resemble the incident and reads as a patch. Repair: restate it as the general condition and outcome, and keep the incident as evidence outside the text.
- **Metadiscourse and negative scoping.** Commentary about the text, process narration, and exclusions of things no reader would do. Repair: delete.

## Composition

Each duty has one owner: the always-loaded layer owns duties of every task; a repository file owns local facts and hazards; a skill owns domain knowledge, domain hazards, and what suffices in its domain; a reference owns conditional detail. A skill is safe to follow literally and safe to skip: nothing that must happen on every task lives only in a skill, and any hazard that must never be missed is stated in the skill that meets it. Catalog cost counts: every installed description is paid on every task, so consider consolidation or explicit invocation for rarely needed entries.

## Executable resources

A script earns its place by a defined contract: it does something deterministic better than the executor would, reports failure with a nonzero exit and a short actionable message, keeps secrets out of output, and makes reruns and partial failures safe. Run changed or representative commands whose effects stay local; a script that only exists, or a structural reporter that passes, establishes structure, not usefulness. The [reporter tools](reporter-tools.md) report frontmatter, references, script hygiene, and plugin structure; [host contracts](host-contracts.md) and the [portable skill format](open-standard.md) cover what each host actually loads.
