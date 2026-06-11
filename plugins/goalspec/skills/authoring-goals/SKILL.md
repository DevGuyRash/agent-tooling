---
name: authoring-goals
description: Compile vague or open-ended requests into bounded, verifiable, stoppable Codex /goal contracts. Use to author, lint, scan, decompose, select, render, or audit goals from raw intent, files, PRDs, logs, issues, or existing .goals artifacts.
---

# Authoring Goals

You are GoalSpec's authoring skill. Your job is to convert messy intent and open-world project context into bounded Codex `/goal` contracts.

Core doctrine:

> Open-world discovery. Closed-world execution.

Discovery may inspect broadly and propose many candidates. Execution must run exactly one frozen contract at a time.

## Use this skill when

- The user wants to start or prepare a Codex `/goal`.
- The user gives a vague request such as improve, clean up, modernize, optimize, harden, productionize, polish, stabilize, or make better.
- The user asks to scan files, folders, logs, PRDs, issues, TODOs, diffs, or an existing GOALS.md to create goals.
- The user wants to lint, repair, decompose, select, render, or audit goals.
- A task may run for multiple turns, iterations, files, or tools.

Do not use this skill for simple one-shot answers unless the user explicitly asks for goal authoring.

## Required capability inventory

Before authoring, scanning, decomposing, or auditing any non-trivial goal, inventory available capabilities and include the relevant ones in the output.

Run or emulate:

```bash
python3 <skills-file-root>/scripts/inventory_capabilities.py --format markdown
```

Inventory these sources when available:

- Installed/project/user skills.
- Enabled or discoverable plugins and marketplace entries.
- MCP server declarations in Codex config, `.mcp.json`, and plugin configs.
- Subagent/custom-agent configs.
- Active hooks.
- AGENTS.md guidance and existing `.goals/` artifacts.
- Project test/build/lint commands inferred from package files, task runners, or docs.

Use the inventory to choose verifiers, context sources, and allowed tools. Do not invent capabilities. If inventory fails or is unavailable, say so explicitly, list the capabilities you are assuming, and mark any verifier that could not be confirmed as unverified in the contract.

Every compiled contract should include an **Available Capabilities** section listing only capabilities that are actually discovered, explicitly provided, or clearly inferable from local files.

## Deterministic signals are inputs to judgment

The helper scripts produce deterministic signals. They are **mandatory inputs to your judgment, not substitutes for it and not optional** — read them, then decide. You may override a signal, but only explicitly and with a stated reason; never silently, and never narrate a signal (e.g. a risk level) you did not actually run.

Required for non-trivial work (multi-step authoring, scanning, decomposing, selecting, or auditing):

- **`inventory_capabilities.py`** — before authoring, scanning, decomposing, selecting, or auditing any non-trivial goal. Name the discovered capabilities you use; do not invent ones.
- **`score_goal_risk.py`** — on any raw or vague request, campaign parent, or lint. State the forever-risk level and whether you accepted, repaired, or decomposed it, and why.
- **`extract_candidates.py`** — whenever files, folders, logs, or specs are supplied (NOT for a pure greenfield prompt with no source). Name the extraction frontier: what was inspected and what was left.
- **`validate_goal.py`** — before rendering any contract; do not render an invalid contract.
- **`render_goal.py`** — to produce the final paste-ready `/goal` objective (it also enforces the freeze gate). WHEN the launch target imposes a prompt-length limit THEN you SHALL render with `--pointer` and paste only the launch line; the full mission stays in the written `.goals/rendered-goal.md` / `.goals/rendered-campaign.md` file.

Respond to the signals explicitly in your output: state the risk level and your decision, name the discovered capabilities you used, and name the extraction frontier when you scanned.

Keep it proportionate. A micro-goal — a single concrete one-file change with an obvious verifier and no source files supplied — does not need a full scan or candidate extraction; inventory can be a quick check. But a non-trivial goal cannot skip inventory, risk scoring, validation, and rendering. The point is well-informed judgment, not ceremony on tiny tasks.

## Launchability spine

A goal is launchable only if it has all six fields:

1. **Terminal state** — a state the world is either in or not in.
2. **Verifier** — a test, command, metric, artifact, checklist, MCP/source query, or human gate that can check the state.
3. **Budget** — a hard ceiling in iterations, time, cost, changed files, dependencies, or exploration scope.
4. **Scope edges** — explicit in-scope and out-of-scope boundaries.
5. **Give-up conditions** — named failure states that require stopping unsuccessfully.
6. **Completeness dimensions** — the value dimensions the clauses must cover, so the agent does not satisfy a narrow proxy while missing the user's actual intent.

Also check target stability, priority order, evidence requirements, and contract immutability.

## Output resolution

Choose the artifact based on input shape:

- One concrete task: create `.goals/current.md` and paste-ready `/goal` text.
- Vague task: produce a launchability report and finite replacement options; compile one only if you can make safe assumptions.
- Many files or broad repo context: produce candidate goals and a `.goals/GOALS.md` registry; recommend at most one next `current.md`.
- Existing `GOALS.md`: lint it, mark statuses, repair or extract executable contracts.
- Large aspiration: produce a campaign breakdown or goal graph; do not execute the parent aspiration directly.
- Completed run: audit evidence against `.goals/current.md` and update report/follow-up candidates.

`GOALS.md` is a registry. `.goals/current.md` is the active mission. Never run `/goal` against a backlog or registry.

## Decomposition routing

Route by risk and shape, not just by the literal input:

- If `score_goal_risk.py` reports **high or extreme** forever-risk, OR the request is **broad, multi-objective, or activity-shaped** (e.g. "modernize the app", "fix everything in the backlog", "improve onboarding and checkout and search"), do NOT compile it into a single executable contract. Produce a **campaign** (`.goals/campaign-*.md` from the campaign template — never itself a single goal) and split it into finite child candidates with readiness statuses: **ready | conditional | blocked | not-launchable**.
- A campaign parent is **never compiled or run as a single goal**; it has no single-goal contract hash. Two supported execution paths: human-stepped — compile **at most one ready child** into `.goals/current.md`; or autonomous — render a **locked** campaign as a *chain* via `render_goal.py --campaign` (see "Autonomous campaign execution").
- If **no child is ready**, stop at the campaign/backlog and report the missing fields or decisions that block the most promising child. Do not force a not-ready child into `current.md`.
- Record the remaining children as candidates/backlog, not as implicit scope of the one launched child.
- When decomposing, record provenance for the original request (`record_provenance.py`) and write the campaign's `## Coverage` map: each explicit requirement of the original request → a child id, or `deferred: <reason>`.
- Chain-level red-team before lock: re-read the original request; name anything it explicitly asks that no child covers; cover it or record it as deferred with a reason.

## Greenfield / from spec

When there is no existing code to scan:

- Skip the repo scan, but still run the capability inventory (the languages, tooling, and test runners that will exist).
- Author from the prompt or spec. If a spec/PRD/design doc exists, scan that document as the discovery surface instead of code.
- A first greenfield goal is usually small: produce a minimal verifiable artifact plus a smoke test and run instructions, with a verifier that actually executes (e.g. the smoke-test command), not a manual "looks done".
- Greenfield does not waive the spine: terminal state, verifier, budget, scope, give-up, and completeness are still mandatory.

## Contract style

Generated goal contracts should be declarative. Say what must be true, what must not change, what proves completion, and when to stop.

Avoid implementation recipes such as "edit A, then refactor B, then update C." The executor chooses the path. The contract supplies destination, fences, evidence, and stop conditions.

Allowed procedural rails are generic and finite:

- Read the contract and relevant context.
- Make the smallest effective change.
- Run verifier(s).
- Decide: complete, continue within budget, stop blocked, stop out-of-scope, or stop budget-exhausted.
- Record adjacent discoveries as follow-up candidates.

## Red-team before lock

Before writing the hash, attack your own contract once: actively look for a way to make the Verifier pass without satisfying the Intent — trivial or hardcoded outputs, edits to files the verifier reads but the scope forbids, artifacts that exist but are empty, satisfying the letter of a clause while missing the Completeness Dimensions. If you find a gaming path, strengthen the Verifier or Scope to close it, re-validate, and only then lock. If you find none, state that in one line. `validate_goal.py` flags the mechanical cases (tautological verifiers, out-of-scope reads, verifier/terminal-state disconnects); this pass exists for the semantic ones lint cannot see.

## Contract freeze

After writing `.goals/current.md`, instruct the user or executor to run:

```bash
python3 <skills-file-root>/scripts/validate_goal.py .goals/current.md --write-hash
```

During execution, the agent may read `.goals/current.md` but must not modify it. The only `.goals/` paths the executor may write during a `/goal` run are:

- `.goals/evidence/`
- `.goals/reports/`

Any mid-run change to `.goals/current.md` or `.goals/current.sha256` is an audit failure unless the user explicitly restarts authoring and re-locks the contract.

For unattended runs, launch through `scripts/launch_goal.py`: it refuses unlocked contracts, enforces an external wall-clock ceiling on the executor (the only bound that does not depend on the executor's cooperation), captures the transcript under `.goals/evidence/transcripts/`, and runs the verifiers and audit at close.

## Autonomous campaign execution

The sanctioned autonomous outer loop: one `/goal` that executes an entire decomposed tasklist as a **chain** of frozen child contracts, with its own budget and stop conditions. The core rule: **the plan is frozen, evidence is the truth, checkmarks are a derived view.** The executor never authors mid-run and never edits the manifest; status is recomputed from per-child verifier evidence; the roll-up audit recomputes everything.

Structure:

- Manifest: `.goals/campaign-<slug>.md` (campaign template) with `## Chain Budget` (numeric ceiling on children attempted; retries of one child count once — the wall clock bounds retry grinding) and `## Chain Failure Policy` (exactly one of `halt-on-failure` | `skip-dependents-and-continue`). Dependency truth lives in this hash-locked manifest, never in `graph.json` (an unlocked, validated mirror).
- Children: every ready child is a **full contract** at `.goals/children/G-00N/current.md`, individually validated and locked (`validate_goal.py <path> --write-hash`) — the same spine, applied recursively.
- Evidence/reports per child: `.goals/evidence/children/G-00N/` and `.goals/reports/G-00N-report.md`. Both already inside the executor's allowed write paths.

Freeze procedure:

```bash
python3 <skills-file-root>/scripts/validate_goal.py .goals/children/G-001/current.md --write-hash   # per child
python3 <skills-file-root>/scripts/validate_campaign.py .goals/campaign-<slug>.md --write-hash      # aggregate lock
python3 <skills-file-root>/scripts/render_goal.py --campaign .goals/campaign-<slug>.md              # ONE chain /goal
```

`validate_campaign.py` writes `.goals/campaign.sha256`, an aggregate hash over the manifest bytes plus every ready child's contract hash — any manifest edit or child swap breaks it, and `render_goal.py --campaign` refuses unlocked/mismatched campaigns with no override.

Runtime (encoded in the rendered `/goal`): per child, the executor re-reads the child contract, works within that child's own budget/scope/give-up, runs `run_verifiers.py` into the child's evidence dir, writes the child report, then refreshes `campaign_status.py` and executes its `next_child` (achieved children are skipped on resume). `campaign_status.py` derives ✓/✗/skipped/pending purely from verifier evidence (`overall_passed` + matching `contract_sha256` + report present) and reports `chain_should_stop`. If the status helper itself fails, the executor stops and reports blocked.

Constraints and caveats:

- Sequential only; no parallel children in v1.
- The child set is frozen at launch. Work discovered mid-run goes into each child report's `## Follow-Up Candidates`; `audit_campaign.py` harvests these into the roll-up as the input to the *next* campaign.
- On Codex, hooks are detect-only: the real bounds are the freeze gates, the wall clock, and the audit. For unattended chains use `launch_goal.py --campaign <manifest>` — same external wall-clock ceiling; at close it re-runs verifiers wrapper-side for every attempted child (the wrapper-produced oracle is the trust anchor; unattempted children stay pending, never force-failed) and then runs `audit_campaign.py`. Exit 0 only on `campaign achieved`, 124 on timeout.
- After an **interactive** (non-wrapper) chain, re-run `run_verifiers.py` per child yourself before auditing — never certify off executor-produced results alone.
- Close: run `audit_campaign.py` (verdicts: `campaign achieved` | `partial: n/m` | `not achieved` | `campaign mutated`). Then set `GOALSPEC_ALLOW_CONTRACT_WRITE=1` for the close commands — the armed scope guard otherwise denies them all, including removing the lock itself — and archive/remove `.goals/campaign.sha256` and update statuses with `graph_goal.py --status` / `update_ledger.py` per child.
- Known gap: `stop_guard` is not campaign-aware (nudge-only value); the wall clock and the audit are the bounds.

## Mandatory response structure

For author/compile/lint outputs, include:

```text
Mode:
Launchability:
Forever-risk:
Capability summary:
Missing / assumed fields:
Output artifact decision:
Next action:
```

When producing a contract, include:

```text
1. .goals/current.md content
2. Validation command
3. Paste-ready Codex /goal objective
4. Optional GOALS.md entry or follow-up candidates
```

When scanning, produce candidates with readiness statuses:

```text
ready | conditional | blocked | too broad | maintenance-loop | duplicate | unsafe | needs human decision
```

When auditing, produce:

```text
achieved | not achieved | inconclusive | scope violation | contract mutated | blocked | abandoned
```


## Capability selection rule

After inventory, incorporate discovered capabilities into the contract rather than merely listing them. Examples:

- If a project test command is discovered, prefer it as a verifier over a vague manual check.
- If a relevant MCP server is discovered, name the specific resource/tool it should query and what evidence it must return.
- If another skill is relevant, list it under Available Capabilities and constrain its role.
- If a custom agent is available, use it only for read-heavy discovery or audit unless the contract explicitly authorizes write-capable delegation.
- If hooks are active, state which evidence/scope protections they provide, but do not treat hooks as perfect enforcement.

## Full lifecycle modes

- `init`: create `.goals/` directories, templates, graph, AGENTS snippet, and optional custom-agent templates.
- `author`: convert raw intent into one frozen goal contract or finite options.
- `scan`: inspect broad context and produce candidates plus a frontier report.
- `lint`: validate an existing goal or registry for launchability.
- `decompose`: split a campaign into finite child goals; do not execute the parent.
- `select`: choose one ready, unblocked, low-risk goal.
- `render`: produce paste-ready Codex `/goal` text from `.goals/current.md`.
- `audit`: compare a run report/evidence against the frozen contract.
- `close`: update ledger/graph status and record follow-up candidates.

The outer lifecycle is human-stepped by default. Do not auto-launch the next goal after closing the current one unless the user explicitly requests an autonomous outer loop with its own budget and stop condition.

## Multi-turn conversation flow

Author iteratively. Do not block on questions you can answer from the repo or sensible defaults, and do not silently guess on choices that change the contract's terminal state or scope.

- Proceed autonomously when inventory plus the input make the terminal state, verifier, and scope unambiguous, or when the user said to proceed without asking.
- Ask one focused question when the terminal state is ambiguous, multiple incompatible scopes are plausible, or a verifier/budget the user must own is unknown. Prefer a single high-signal question over a checklist.
- Typical flow: (1) inventory capabilities and restate the goal in launchable terms; (2) if vague, offer 1-3 finite replacement options and let the user pick; (3) compile one `.goals/current.md`, validate, and render; (4) ask the user to lock the hash before any `/goal` run.

After locking, do not auto-launch the next goal; the outer loop stays human-stepped unless the user authorizes an autonomous loop with its own budget and stop condition.

## References and tools

Load these only as needed:

- `references/principles.md`
- `references/launchability-rubric.md`
- `references/contract-schema.md`
- `references/goal-ir-schema.md`
- `references/capability-inventory.md`
- `references/anti-patterns.md`
- `references/renderer-rules.md`
- `references/hooks-policy.md`
- `references/outer-loop.md`
- `references/custom-agents.md`
- `references/examples.md`
- `references/workflows.md`
- `references/goal-graph.md`

Use scripts for deterministic checks and project artifact operations. Prefer the unified wrapper when convenient:

```bash
python3 <skills-file-root>/scripts/goalspec.py init
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

Individual scripts:

- `scripts/init_project.py`
- `scripts/validate_goal.py`
- `scripts/render_goal.py`
- `scripts/score_goal_risk.py`
- `scripts/inventory_capabilities.py`
- `scripts/extract_candidates.py`
- `scripts/select_goal.py`
- `scripts/graph_goal.py`
- `scripts/run_verifiers.py`
- `scripts/launch_goal.py`
- `scripts/audit_goal.py`
- `scripts/update_ledger.py`
- `scripts/validate_campaign.py`
- `scripts/campaign_status.py`
- `scripts/audit_campaign.py`
- `scripts/goalspec.py`

Optional read-only custom-agent templates live in `assets/codex-agents/`. They are templates for project `.codex/agents/`; use `init_project.py --install-agents` only when the user wants them copied into the project.


## Mature-mode helpers

When the user wants the fuller GoalSpec flow, use deterministic helper scripts instead of hand-maintaining state:

- Initialize project state with `python3 <skills-file-root>/scripts/init_project.py`.
- Add a compiled contract to the graph with `python3 <skills-file-root>/scripts/graph_goal.py --add-contract .goals/current.md`.
- Select the next ready goal with `python3 <skills-file-root>/scripts/select_goal.py`.
- Use `python3 <skills-file-root>/scripts/goalspec.py <command>` as the wrapper when convenient.

Optional custom agent templates live in `assets/codex-agents/`. They are templates, not automatically loaded by plugin install. To use them in a repo, copy them into `.codex/agents/` or run `python3 <skills-file-root>/scripts/init_project.py --install-agents`, then explicitly ask Codex to spawn `goal_discoverer` or `goal_auditor` when broad read-only exploration or skeptical audit would otherwise pollute the main context.
