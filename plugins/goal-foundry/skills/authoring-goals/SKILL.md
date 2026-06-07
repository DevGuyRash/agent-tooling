---
name: authoring-goals
description: Use to create, lint, scan, decompose, audit, or render bounded Codex /goal contracts from raw intent, files, folders, PRDs, logs, issues, or existing .goals artifacts. Converts open-ended work into finite, verifiable, stoppable goals.
---

# Authoring Goals

You are Goal Foundry's authoring skill. Your job is to convert messy intent and open-world project context into bounded Codex `/goal` contracts.

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

Use the inventory to choose verifiers, context sources, and allowed tools. Do not invent capabilities. If inventory fails or is unavailable, say so and proceed with explicit assumptions.

Every compiled contract should include an **Available Capabilities** section listing only capabilities that are actually discovered, explicitly provided, or clearly inferable from local files.

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

## Contract style

Generated goal contracts should be declarative. Say what must be true, what must not change, what proves completion, and when to stop.

Avoid implementation recipes such as "edit A, then refactor B, then update C." The executor chooses the path. The contract supplies destination, fences, evidence, and stop conditions.

Allowed procedural rails are generic and finite:

- Read the contract and relevant context.
- Make the smallest effective change.
- Run verifier(s).
- Decide: complete, continue within budget, stop blocked, stop out-of-scope, or stop budget-exhausted.
- Record adjacent discoveries as follow-up candidates.

## Contract freeze

After writing `.goals/current.md`, instruct the user or executor to run:

```bash
python3 <skills-file-root>/scripts/validate_goal.py .goals/current.md --write-hash
```

During execution, the agent may read `.goals/current.md` but must not modify it. The only `.goals/` paths the executor may write during a `/goal` run are:

- `.goals/evidence/`
- `.goals/reports/`

Any mid-run change to `.goals/current.md` or `.goals/current.sha256` is an audit failure unless the user explicitly restarts authoring and re-locks the contract.

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
python3 <skills-file-root>/scripts/goal_foundry.py init
python3 <skills-file-root>/scripts/goal_foundry.py inventory --format markdown
python3 <skills-file-root>/scripts/goal_foundry.py validate .goals/current.md --write-hash
python3 <skills-file-root>/scripts/goal_foundry.py render .goals/current.md --write .goals/rendered-goal.txt
python3 <skills-file-root>/scripts/goal_foundry.py select
python3 <skills-file-root>/scripts/goal_foundry.py audit .goals/current.md --report .goals/reports/latest.md
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
- `scripts/audit_goal.py`
- `scripts/update_ledger.py`
- `scripts/goal_foundry.py`

Optional read-only custom-agent templates live in `assets/codex-agents/`. They are templates for project `.codex/agents/`; use `init_project.py --install-agents` only when the user wants them copied into the project.


## Mature-mode helpers

When the user wants the fuller Goal Foundry flow, use deterministic helper scripts instead of hand-maintaining state:

- Initialize project state with `python3 <skills-file-root>/scripts/init_project.py`.
- Add a compiled contract to the graph with `python3 <skills-file-root>/scripts/graph_goal.py --add-contract .goals/current.md`.
- Select the next ready goal with `python3 <skills-file-root>/scripts/select_goal.py`.
- Use `python3 <skills-file-root>/scripts/goal_foundry.py <command>` as the wrapper when convenient.

Optional custom agent templates live in `assets/codex-agents/`. They are templates, not automatically loaded by plugin install. To use them in a repo, copy them into `.codex/agents/` or run `python3 <skills-file-root>/scripts/init_project.py --install-agents`, then explicitly ask Codex to spawn `goal_discoverer` or `goal_auditor` when broad read-only exploration or skeptical audit would otherwise pollute the main context.
