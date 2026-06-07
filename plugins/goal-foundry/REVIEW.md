# Goal Foundry v1.0 Review

Review date: 2026-06-06

## Result

This package is a complete Codex-oriented Goal Foundry plugin, not merely a standalone skill.

## Checked

- Plugin manifest exists at `.codex-plugin/plugin.json`.
- Manifest points to root-level `skills/` and `hooks/hooks.json`.
- Primary `$authoring-goals` skill includes doctrine, launchability spine, capability inventory, artifact decisions, contract style, lifecycle modes, and contract freeze rules.
- Skill metadata exists at `skills/authoring-goals/agents/openai.yaml`.
- Deterministic helper scripts exist for init, inventory, validation, rendering, risk scoring, candidate extraction, selection, graph updates, ledger updates, verifier extraction/execution, and audit.
- Hook bundle exists for UserPromptSubmit, PreToolUse, PostToolUse, and Stop.
- Hook scripts protect frozen goal artifacts, capture evidence, and require final-report evidence fields when a completion claim is made.
- Optional custom-agent templates exist for read-only discovery and audit.
- Templates exist for current goal contracts, GOALS.md, candidate cards, campaign plans, frontier reports, graph.json, decision records, and reports.
- Examples exist for raw inputs, registry, contract, and report.
- Fast smoke test passes.

## Smoke test

Command:

```bash
bash tests/run_smoke_tests.sh
```

Observed result:

```text
Goal Foundry full smoke test passed.
```

## Deliberate boundaries

- The outer loop remains human-stepped by default. This is intentional to avoid reintroducing a runaway loop at the campaign/backlog level.
- The plugin inventories existing MCP servers and skills but does not bundle any MCP server itself.
- Hooks are guardrails, not a perfect security boundary. Contract hash checks and audits supplement them.
