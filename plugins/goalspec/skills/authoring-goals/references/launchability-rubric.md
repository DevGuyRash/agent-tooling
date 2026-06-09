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

## Forever-risk levels

- Low: concrete terminal state, strong verifier, narrow scope, explicit budget.
- Medium: one weak field or local assumption.
- High: vague verb, broad scope, weak verifier, missing budget, or moving target.
- Extreme: loop/maintenance/campaign treated as one goal, no verifier, or no stop.
