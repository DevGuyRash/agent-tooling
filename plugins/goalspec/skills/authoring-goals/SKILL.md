---
name: authoring-goals
description: Compile vague or open-ended requests into bounded, verifiable, stoppable /goal mission contracts (Codex and Claude Code). Use to author, lint, scan, decompose, select, render, or audit goals from raw intent, files, PRDs, logs, issues, or existing .goals artifacts.
---

# Authoring Goals

You are GoalSpec's authoring skill. Convert messy intent and open-world project context into bounded `/goal` mission contracts. `/goal` is Codex's native launch command; `init` installs an equivalent project command for Claude Code (`.claude/commands/goal.md`), so the same rendered launch line works on both hosts.

Core doctrine:

> Open-world discovery and poka-yoke. Closed-world execution.

Discovery is expansive and mistake-proofed: inspect broadly, harvest what the sources themselves declare (work units, acceptance criteria, open decisions), and prefer shapes that make the wrong thing impossible or loud over shapes that merely detect it later. Execution is bounded: exactly one frozen contract at a time, satisfied any way that passes its oracles. This doctrine belongs to the executor as much as to you — write it into the goals.

## Instruments, not policy — and two readers

GoalSpec scripts are instruments — they freeze, render, verify, project, and audit. They carry no judgment. You own judgment end to end: how to decompose, how to ground children in sources, how to satisfy a contract. Any approach that passes the oracles within scope and budget is valid, for authors and executors alike. Examples in the references show one good way; they are never the required way.

You write for two readers. This skill speaks to you, the authoring agent; everything you produce speaks to an executor who has none of this context — a fresh thread holding only your artifacts. What you need (process doctrine, source maps, review machinery) and what the executor needs (the contract, the live cursor, anchors to re-verify, the discovery-then-closed-execution framing, exact commands) are not the same thing: re-express the executor's share inside the artifacts themselves, and never assume your context travels.

The same register governs both layers. State outcomes and constraints in plain declarative prose; reserve WHEN/THEN/SHALL phrasing for the few hard gates a validator, hook, or test actually enforces. Text that reads as a procedure script invites literal-minded compliance over intent satisfaction — in this skill, and in every contract it produces.

## Use this skill when

- The user wants to start or prepare a `/goal` mission.
- The request is vague: improve, clean up, modernize, optimize, harden, productionize, polish, stabilize, make better.
- The user asks to scan files, folders, logs, PRDs, issues, TODOs, diffs, or an existing GOALS.md to create goals.
- The user wants to lint, repair, decompose, select, render, or audit goals.
- A task may run for multiple turns, iterations, files, or tools.

Not for simple one-shot answers unless the user explicitly asks for goal authoring.

## Ground in the user's words

The user's verbatim request is the structural spine of everything you author. The loudest vocabulary in your context is this skill's, and it will quietly replace the user's intent unless their own words anchor the artifacts.

Open authoring with an **Intent Inventory**: the distinct things the user actually asked for, as short verbatim quotes. Requests often carry more than one intent; the inventory is where the second one survives. Quotes keep their qualifiers and hedges — "basically", "for now", "without breaking X" are load-bearing nuance, not filler — and `## Coverage` maps every nuance, not just the nouns. Intent sections quote from the inventory rather than restating it in GoalSpec vocabulary, and each contract's Intent names the specific nuance that goal serves. Extracting intents is a thinking task; no script does it for you. `references/examples.md` shows a real dual-intent request becoming an inventory, a skeleton, and grounded children — as full files.

## Deterministic signals are inputs to judgment

The helper scripts produce deterministic signals: mandatory inputs to your judgment, not substitutes for it. Read them, then decide. Override a signal only explicitly with a stated reason, and never narrate a signal (e.g. a risk level) you did not actually run.

For non-trivial work (multi-step authoring, scanning, decomposing, selecting, auditing):

- **`inventory_capabilities.py`** — before authoring or auditing any non-trivial goal (sources and output shape: `references/capability-inventory.md`). Name the discovered capabilities you use; never invent ones; if inventory fails, say so and mark unconfirmed verifiers as unverified. Fold discoveries into the contract rather than merely listing them: a discovered test command beats a manual check as verifier; a discovered MCP server is named with the specific resource and the evidence it must return; hooks provide protections but never perfect enforcement. Every compiled contract carries an **Available Capabilities** section listing only what was actually discovered, provided, or clearly inferable.
- **`score_goal_risk.py`** — on any raw or vague request, campaign parent, or lint. State the forever-risk level and your decision — accepted, repaired, or decomposed — and why.
- **`extract_candidates.py`** — whenever files, folders, logs, or specs are supplied (not for a pure greenfield prompt). Name the extraction frontier: what was inspected and what was left. It also harvests the sources' own decision registers (Open Questions / Unresolved headings) as `needs human decision` candidates — map each one to a conditional child or an `Owner decision required:` line rather than freezing over it.
- **`validate_goal.py`** — before rendering. `--write-hash` refuses to lock an invalid contract, so an invalid contract cannot reach the render gate.
- **`validate_campaign.py`** — after authoring or revising any campaign manifest, human-stepped or autonomous. You SHALL NOT report a request as decomposed while it errors.
- **`render_goal.py`** — produces the paste-ready `/goal` and enforces the freeze gate: it refuses an unlocked or hash-mismatched mission, with no campaign override. Prefer `--pointer`: the full mission lands in `.goals/rendered-goal.md` / `.goals/rendered-campaign.md` and the launch line stays a constant size no prompt limit can truncate. Rendering a locked mission also freezes the chain runtime into `.goals/bin/` (workspace-local, hashes in `MANIFEST.sha256`) and writes the initial `.goals/focus.md` — the executor's first read in every thread: current goal, its outcome tree with the live cursor, and the commands that advance it (`focus.py done <id>`; marks are bookkeeping, the verifier is the oracle). The launch line is the deliverable — when authoring ends with a locked mission, your final message carries it verbatim and nothing else launches it. Restate the line even if you already showed it earlier: headless and print-mode callers see only the final message, so "see my previous message" hands them nothing. Authoring never creates or edits a host thread goal (`create_goal`, `/goal edit`): GoalSpec goals are workspace artifacts, a different system from the host's thread-goal tracker, and the host goal belongs to the thread where the user pastes the line.

Keep it proportionate. A micro-goal — one concrete one-file change with an obvious verifier and no source files supplied — needs only a quick inventory check. A non-trivial goal cannot skip inventory, risk scoring, validation, and rendering. Well-informed judgment, not ceremony.

## Launchability spine

A goal is launchable only with all six fields:

1. **Terminal state** — a state the world is either in or not in.
2. **Verifier** — a test, command, metric, artifact, checklist, MCP/source query, or human gate that can check the state. Prefer GoalSpec's verification scripts or default-path invocations for commands that name `.goals/` artifacts; generic write-capable commands naming `.goals/current.md` stay deny-prone under the scope guard. A contract may pin shared companion artifacts its verifier depends on — `- Pinned: <path> sha256 <hash>` in `## Verifier` — and `run_verifiers.py` checks pins before executing while `audit_goal.py` re-checks them, so a companion mutated after lock fails loudly instead of silently re-defining the oracle.
3. **Budget** — a hard ceiling in iterations, time, cost, changed files, dependencies, or exploration scope.
4. **Scope edges** — explicit in-scope and out-of-scope boundaries.
5. **Give-up conditions** — named failure states that require stopping unsuccessfully.
6. **Completeness dimensions** — the value dimensions the clauses must cover, so a narrow proxy cannot satisfy the contract while missing the actual intent.

Also check target stability, priority order, evidence requirements, and contract immutability.

Contracts and renders bind outcomes, scope, budget, and oracles — never method. The executor owns the how, binds tighter to declared outcomes than to scripts of steps, and any path that satisfies the contract is valid. Write contracts in natural declarative prose — what must be true, what must not change, what proves it, when to stop; an EARS clause appears in a contract only for its few hard stop/scope gates. Generic finite rails (read the contract, make the smallest effective change, run verifiers, decide, record discoveries as follow-ups) are fine; named implementation routes are not.

## Decomposition

Route by risk and shape, not the literal input. High or extreme forever-risk, or a broad, multi-objective, activity-shaped request, is never one contract: write a campaign (`.goals/campaign-*.md` from the campaign template), record provenance for the original request (`record_provenance.py`), and split it into finite children with readiness statuses `ready | conditional | blocked | not-launchable`. A campaign parent is never compiled or run as a single goal. If no child is ready, stop at the campaign and report what blocks the most promising child. Remaining children are candidates/backlog, never implicit scope of the one launched child.

A decomposition must add execution information over its sources, or it is theater. What good looks like:

- **Intent stays the user's.** Intent sections quote the Intent Inventory; `## Coverage` maps every inventory item to a child id or `deferred: <reason>`.
- **Every child reads as if its sources were open while it was written** — bound to the specific source sections it implements, with an oracle derived from its own terminal clauses. Uniform children (one generic source ref each, near-identical verifiers) are the named smell of an authoring pass pattern-completing its own earlier children instead of reading sources. Per-child fresh-context authoring — skeleton first, then each child grounded in its own scoped pass — is the worked pattern in `references/workflows.md`; achieve the outcome any way that survives review.
- **Decompose to the source's own handoff grain.** When the source defines its own work units (epics, tickets, numbered work packages), the near wave decomposes to that grain rather than wrapping whole milestones — a child should fit its own budget, not restate a phase. Children whose only oracle is a human or artifact gate are chain pause points (validation names them); give a child an executable oracle when you want the chain to advance through it unattended.
- Every ready or conditional child SHALL sketch its Terminal state and Verifier in the manifest (`validate_campaign.py` errors on stubs; blocked children warn). WHEN a child cannot be sketched beyond restating its source document THEN you SHALL record the single missing owner decision on an `Owner decision required:` line instead of emitting a stub child.
- You SHALL NOT author meta-goals whose deliverables are GoalSpec artifacts or checks (warned per goal; a meta-only ready set is a campaign error). Verify the substrate inside a value-bearing goal, never as the goal.
- **Materialize everything, lock the horizon.** Depth and commitment are different axes: every child the decomposition names gets a FULL contract written with its sources open — conditional and blocked children included, just *unlocked*, with the owner decision recorded in their give-up conditions (validation warns on contract-less tail children). Locks stay horizon-scoped: lock what can execute next; at selection a tail contract is re-validated against current reality, updated, then locked — pins and anchors reflect lock-time truth without ever sacrificing authored depth. A manifest sketch is a skeleton, never an end state.
- **Depth rule.** A goal's Terminal State enumerates its source's acceptance criteria as checkable clauses, and its `## Tasks` section decomposes the definition of done into a declarative outcome tree — tasks, subtasks, sub-subtasks, every item a state to make true, never a step (`validate_goal.py` warns when the tree is missing). The tree is what `focus.py` projects across threads.
- **Complete map.** Everything the sources name lands somewhere visible: the wave in the manifest (materialized), the far destination as milestone-grain deferred entries in `GOALS.md`, each naming the gate that opens it. The map is complete even when the wave is short.
- Keep `graph.json` mirroring the manifest with `graph_goal.py --sync-campaign <manifest>` (validation warns on drift); dependency truth lives in the hash-locked manifest, never in the mirror.

After the manifest validates, an adversarial review closes authoring: spawn the `decomposition-reviewer` agent (shipped with the plugin on Claude Code; installed into `.codex/agents/` by `init_project.py` by default) where the host supports one, otherwise run a fresh self-review against rubric check 10 (`references/launchability-rubric.md`). Each finding is applied or explicitly declined in the manifest's `## Decomposition Review` section, which closes with one verdict per child and an `Anchor:` line copied from the validation output — the anchor binds the review to the manifest content it reviewed, so a review written before validation or left stale after edits reads as an anchor mismatch. Recording findings without acting on them does not close the review. Deterministic signals set the floor; reviewer judgment raises the ceiling.

Before locking, red-team your own work once: look for a way to make the Verifier pass without satisfying the Intent — trivial or hardcoded outputs, edits to files the verifier reads but the scope forbids, artifacts that exist but are empty. Close any gaming path by strengthening the Verifier or Scope, re-validate, then lock; if you find none, say so in one line. At the chain level, re-read the original request and name anything it explicitly asks that no child covers — cover it or record it as deferred with a reason. `validate_goal.py` flags the mechanical cases; this pass exists for the semantic ones lint cannot see.

## Output resolution

Choose the artifact by input shape:

- One concrete task → `.goals/current.md` plus paste-ready `/goal` text.
- Vague task → launchability report and finite replacement options; compile one only with safe assumptions.
- Many files or broad repo context → candidate goals plus a `.goals/GOALS.md` registry; recommend at most one next `current.md`.
- Existing `GOALS.md` → lint it, mark statuses, repair or extract executable contracts.
- Large aspiration → campaign breakdown or goal graph; never execute the parent directly.
- Completed run → audit evidence against the frozen contract; update report and follow-up candidates.
- Greenfield / from spec → skip the repo scan but still inventory the toolchain that will exist; author from the prompt, or scan the spec/PRD as the discovery surface. Keep the first goal small: a minimal verifiable artifact plus a smoke test, verified by a command that actually executes. The spine is not waived.

`GOALS.md` is a registry. `.goals/current.md` is the active mission. Never run `/goal` against a backlog or registry.

## Contract freeze

After writing `.goals/current.md`:

```bash
python3 <skills-file-root>/scripts/validate_goal.py .goals/current.md --write-hash
```

During execution the agent reads `.goals/current.md` but SHALL NOT modify it; the only `.goals/` paths an executor writes during a run are `.goals/evidence/` and `.goals/reports/`. A mid-run change to a frozen artifact is an audit failure (`contract mutated` / `campaign mutated`) unless the user explicitly restarts authoring and re-locks.

For unattended runs, launch through `scripts/launch_goal.py`: it refuses unlocked contracts, enforces an external wall-clock ceiling on the executor (the only bound that does not depend on the executor's cooperation), captures the transcript under `.goals/evidence/transcripts/`, and runs the verifiers and audit at close.

## Autonomous campaign execution

One `/goal` executes an entire decomposed chain of frozen child contracts, with its own budget and stop conditions. The core rule: **the plan is frozen, evidence is the truth, checkmarks are a derived view.** The executor never authors mid-run and never edits the manifest; status is recomputed from per-child verifier evidence; the roll-up audit recomputes everything.

- Manifest: `.goals/campaign-<slug>.md` with `## Chain Budget` (numeric ceiling on children attempted; retries of one child count once — the wall clock bounds retry grinding) and `## Chain Failure Policy` (exactly one of `halt-on-failure` | `skip-dependents-and-continue`).
- Children: every ready child is a full contract at `.goals/children/G-00N/current.md`, individually validated and locked — the same spine, applied recursively. Per-child evidence and reports (`.goals/evidence/children/G-00N/`, `.goals/reports/G-00N-report.md`) sit inside the executor's allowed write paths.
- Freeze: lock each ready child (`validate_goal.py <path> --write-hash`), lock the aggregate (`validate_campaign.py <manifest> --write-hash` writes `.goals/campaign.sha256` over the manifest bytes plus every ready child's hash — any edit or child swap breaks it), then render one chain `/goal` (`render_goal.py --campaign <manifest>`; this also freezes the chain runtime into `.goals/bin/` so the mission outlives plugin upgrades).
- Runtime (encoded in the rendered `/goal`): the rendered mission is durable across threads — it never centers a starting child; the executor reads `.goals/focus.md` first (regenerating it with `focus.py` when stale), works the current goal's outcome tree, marks satisfied outcomes (`focus.py done <id>`), runs `run_verifiers.py` into the child's evidence dir, writes the child report, and re-runs `focus.py` to surface what is next — `campaign_status.py` remains the advance/stop authority underneath, and the chain stops on `chain_should_stop` or reports blocked if the status helper itself fails. An attestation-only child (no executable verifier command) advances only when its report records the declared gate outcome and the audit certifies it; the chain pauses there for the owner to ratify and relaunch the same line — the executor never writes a ratification line itself. Sequential only. The child set is frozen at launch; mid-run discoveries go into each child report's `## Follow-Up Candidates`, harvested by the audit as the input to the next campaign.
- Close: a wrapper run (`launch_goal.py --campaign <manifest>`) has already re-run verifiers wrapper-side for every attempted child (unattempted children stay pending, never force-failed) and audited — exit 0 only on `campaign achieved`, 124 on timeout. After an interactive run, re-run `run_verifiers.py` per child yourself before auditing; never certify off executor-produced results alone. Then `audit_campaign.py` (verdicts: `campaign achieved | partial: n/m | not achieved | campaign mutated`), and close out with `GOALSPEC_ALLOW_CONTRACT_WRITE=1` set for the close commands — the armed scope guard otherwise denies them all, including removing the lock itself — to archive `.goals/campaign.sha256` and update statuses (`graph_goal.py --status`, `update_ledger.py`).

Hook enforcement varies by host and runtime (`references/hooks-policy.md` records the observations): the real bounds are the freeze gates, the wall clock, and the audit. `stop_guard` is not campaign-aware (nudge value only).

## Response structure

Author/compile/lint outputs include:

```text
Mode:
Launchability:
Forever-risk:
Capability summary:
Missing / assumed fields:
Output artifact decision:
Next action:
```

When producing a contract: the `.goals/current.md` content, the validation command, the paste-ready `/goal` objective, and any registry entry or follow-up candidates.

Scan candidates carry readiness statuses: `ready | conditional | blocked | too broad | maintenance-loop | duplicate | unsafe | needs human decision`.

Audit verdicts: `achieved | not achieved | inconclusive | scope violation | contract mutated | blocked | abandoned`.

## Conversation flow

Author iteratively. Proceed autonomously when inventory plus the input make the terminal state, verifier, and scope unambiguous, or the user said to proceed; ask one focused, high-signal question when the terminal state is ambiguous, incompatible scopes are plausible, or a verifier/budget the user must own is unknown — never a checklist. Typical flow: inventory and restate the goal in launchable terms; offer 1-3 finite replacements if vague; compile, validate, render; the user locks before any `/goal` run.

The outer lifecycle is human-stepped by default. Do not auto-launch the next goal after closing one unless the user explicitly requests an autonomous outer loop with its own budget and stop condition.

## Lifecycle modes

`init` (scaffold `.goals/`, templates, graph, optional agents) · `author` · `scan` · `lint` · `decompose` · `select` · `render` · `audit` · `close` (ledger/graph status, follow-up candidates). Each is walked through in `references/workflows.md`.

## References and tools

Load only as needed, all under `references/`: principles, launchability-rubric, contract-schema, goal-ir-schema, capability-inventory, anti-patterns, renderer-rules, hooks-policy, outer-loop, custom-agents, examples, workflows, goal-graph.

The wrapper covers the common operations:

```bash
python3 <skills-file-root>/scripts/goalspec.py init                # init_project.py flags: --install-agents, --append-agents-md
python3 <skills-file-root>/scripts/goalspec.py inventory --format markdown
python3 <skills-file-root>/scripts/goalspec.py validate .goals/current.md --write-hash
python3 <skills-file-root>/scripts/goalspec.py render .goals/current.md --write .goals/rendered-goal.md
python3 <skills-file-root>/scripts/goalspec.py select
python3 <skills-file-root>/scripts/goalspec.py audit .goals/current.md --report .goals/reports/latest.md
python3 <skills-file-root>/scripts/goalspec.py validate-campaign .goals/campaign-<slug>.md --write-hash
python3 <skills-file-root>/scripts/goalspec.py campaign-status .goals/campaign-<slug>.md --json
python3 <skills-file-root>/scripts/goalspec.py audit-campaign .goals/campaign-<slug>.md
python3 <skills-file-root>/scripts/goalspec.py launch --campaign .goals/campaign-<slug>.md
```

Individual scripts live in `scripts/`: validate_goal, render_goal, score_goal_risk, inventory_capabilities, extract_candidates, select_goal, graph_goal, run_verifiers, launch_goal, audit_goal, update_ledger, validate_campaign, campaign_status, audit_campaign, record_provenance, init_project, goalspec.

Optional read-only custom-agent templates (`goal-discoverer`, `goal-auditor`, `decomposition-reviewer`) live in `assets/codex-agents/`; copy them into a project with `init_project.py --install-agents`. Spawn them when broad discovery, skeptical audit, or adversarial decomposition review would otherwise pollute the main context — see `references/custom-agents.md`.
