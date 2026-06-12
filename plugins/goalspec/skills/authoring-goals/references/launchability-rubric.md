# Launchability Rubric

Score every proposed goal before compiling it.

## Verdicts

- `yes`: all required fields are present and concrete.
- `conditional`: fields are present but rely on assumptions or local discovery.
- `no`: missing one or more spine fields, or the request is a loop/campaign that must be decomposed.
- `unsafe`: execution would require forbidden, destructive, privacy-sensitive, or high-risk behavior outside the user's explicit authorization.

## Checks

### 1. Terminal-state check

Can the goal be stated as `X is true`?

Bad: `Improve checkout reliability.`
Good: `The checkout API returns success for test cases A/B/C and the checkout integration suite exits 0.`

### 2. Verifier check

Is there a verifier that can check completion?

Acceptable verifier classes:

- test command
- lint/build/typecheck command
- benchmark or metric threshold
- coverage report
- artifact existence/content checklist
- human review gate
- MCP/source query when a reliable external system is available

### 3. Budget check

At least one hard ceiling must exist:

- implementation iterations
- changed files
- dependencies added
- time/cost/tool-call bound
- exploration depth/files inspected

### 4. Scope-edge check

Name both in-scope and out-of-scope areas. Include explicit denylist for secrets, deployment config, public APIs, migrations, or data changes when risky.

### 5. Give-up check

Name concrete stop states:

- missing access/credentials
- verifier cannot run
- required product decision
- out-of-scope change required
- target infeasible within budget

### 6. Completeness check

Ask: if every clause passes, could the user still reasonably say “that’s not what I meant”?

Add dimensions for behavior, tests, docs, UX, accessibility, security, performance, data migration, release safety, or rollback when relevant.

### 7. Target-stability check

Freeze moving targets using a date, version, checklist, threshold, or explicit source.

### 8. Capability check

Inventory available skills, plugins, MCP servers, hooks, subagents, and project commands. Use them to pick stronger verifiers and context sources. Do not invent capabilities.

### 9. Contract-freeze check

The final `.goals/current.md` must be hashed. The executor may not modify it during the run.

### 10. Decomposition value-add check (campaigns)

For each child, judged against the source documents it derives from:

- Does the child name at least one concrete workspace artifact or behavior the source does not already state verbatim? A renamed milestone with a status label adds nothing.
- Does each child cite the specific source sections it implements (PRD sections, architecture invariants, design tokens, failure families) rather than one generic roadmap pointer? Uniform, cookie-cutter children are a smell that the authoring loop stamped a template instead of thinking per child.
- Intent-inventory fidelity: does an Intent Inventory of short verbatim quotes anchor the campaign, with `## Coverage` mapping every inventory item — including the second intent of a dual-intent request — to a child or an explicit deferral? Intent sections quoting the inventory, or plugin vocabulary replacing what the user actually asked for?
- Lock-horizon sanity: is the locked set the execution horizon — what can run next — with the tail sketched-conditional, materializing at selection? Far-future children locked on today's guesses are the inverse of stub children: judge the horizon case by case, not by a rule.
- Are gates declared where the audit can enforce them (human gates inside ## Verifier, not only in Terminal State prose)?
- Is the Verifier sketch executable in principle — a command, metric, or named gate, not "TBD"? Do children that share a companion verifier artifact pin it (`Pinned: <path> sha256 <hash>`)?
- Materialization completeness: does EVERY named child carry a full contract (conditional/blocked included, unlocked), or is the tail a pile of 5-line manifest sketches? Depth is always maximal; only locking is horizon-scoped.
- Task-tree depth: does each contract's `## Tasks` decompose the definition of done into nested declarative outcomes derived from the source's acceptance criteria — and is every item a state, never a step?
- Map completeness: does everything the sources name appear somewhere visible — wave in the manifest, far destination as deferred `GOALS.md` entries naming their opening gates?
- Nuance fidelity: did qualifiers and hedges from the verbatim request ("basically", "for now", "without breaking X") survive into the inventory and the contracts that serve them?
- Agent-executability: is any child actually human field work (recruiting, payments, sign-ups, physical checks)? Gate it explicitly or split the agent-executable part out.
- Escape hatches: does each child have a reachable terminal state when its decision or input never arrives — and could a child read as "complete" with most of its work blocked-with-rationale?
- Budget realism: do the per-child budgets and the chain budget plus wall clock plausibly fit the work, or are the numbers ceremony that satisfies the validator?
- Chain-mode sanity: which children are attestation-only pause points (no executable verifier command), and is that pause cadence the intended execution mode? Did discovery follow the sources' own outbound references (files the docs declare authoritative) before declaring coverage?
- Is there a bounded first slice that fits a real budget, rather than the whole milestone restated? When the source defines its own work units (epics, tickets), does the near wave decompose to that grain?
- Is any child a meta-goal about GoalSpec itself? Substrate checks belong inside a value-bearing child.
- Does `graph.json` mirror the manifest's nodes and edges (`graph_goal.py --sync-campaign`)?

`validate_campaign.py` enforces the floor deterministically (stub children, meta-only ready sets, empty mirrors) and emits the review anchor. This check is the reviewer's: the `decomposition-reviewer` agent (shipped with the plugin on Claude Code; installed into `.codex/agents/` by `init_project.py` by default) carries it with a refute bias and per-child verdicts. Answer each question with evidence from the manifest and sources; the authoring agent applies or explicitly declines each finding in the manifest's `## Decomposition Review` section, closing with one verdict per child and the `Anchor:` line from validation output.

## Forever-risk levels

- Low: concrete terminal state, strong verifier, narrow scope, explicit budget.
- Medium: one weak field or local assumption.
- High: vague verb, broad scope, weak verifier, missing budget, or moving target.
- Extreme: loop/maintenance/campaign treated as one goal, no verifier, or no stop.
