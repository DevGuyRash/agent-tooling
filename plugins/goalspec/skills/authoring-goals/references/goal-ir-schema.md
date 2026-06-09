# Goal IR Schema

GoalSpec internally normalizes raw intent, files, issues, PRDs, logs, and existing goals into this intermediate representation before rendering artifacts.

This IR is the internal model, distinct from `references/contract-schema.md` (the field-by-field spec of the rendered `.goals/current.md`) and `references/goal-graph.md` (the `.goals/graph.json` node/edge schema): the IR is normalized once, then projected into those concrete artifacts.

```yaml
id: G-000
title: Short stable title
status: candidate | ready | active | completed | blocked | abandoned | superseded | duplicate | maintenance-loop | not-launchable
type: bugfix | test | docs | refactor | research | maintenance-slice | campaign-child | audit
source:
  prompted_by: user | file | issue | log | prior-goal | scan
  evidence:
    - path-or-system:line or description
intent: Why this work matters and how to resolve tradeoffs
available_capabilities:
  skills: []
  plugins: []
  mcp_servers: []
  hooks: []
  subagents: []
  project_commands: []
completeness_dimensions:
  - functional behavior
  - verification
  - regression safety
terminal_state:
  - Checkable proposition
verifier:
  - command/artifact/metric/checklist/human/MCP gate
scope:
  in: []
  out: []
budget:
  iterations: 3
  changed_files: 6
  new_dependencies: 0
  exploration_files: 200
give_up_conditions:
  - missing access
  - verifier unavailable
  - out-of-scope change required
priority_order:
  - correctness
  - minimal scope
  - verification
follow_up_policy: adjacent work becomes candidate goals, not implicit scope
relationships:
  depends_on: []
  blocks: []
  spawned_from: []
  follow_up_to: []
  supersedes: []
  duplicates: []
```

Renderings:

- `.goals/current.md`: one active executable contract (spec: `references/contract-schema.md`).
- `.goals/GOALS.md`: human-readable registry.
- `.goals/graph.json`: machine-readable relationships and statuses (spec: `references/goal-graph.md`).
- `.goals/frontier.md`: discovery coverage and limits.
- Codex `/goal`: compact projection of `current.md`; it must not drop terminal-state, scope, budget, give-up, or evidence obligations (rules: `references/renderer-rules.md`).
