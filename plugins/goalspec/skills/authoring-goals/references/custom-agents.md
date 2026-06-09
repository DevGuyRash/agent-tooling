# Custom Agent Templates

Codex custom agents are project/user configuration, not automatically installed by this plugin. GoalSpec includes optional templates under `assets/codex-agents/`:

- `goal-discoverer.toml`: read-only project explorer that returns candidate goals with evidence.
- `goal-auditor.toml`: read-only auditor that compares reports/evidence against `.goals/current.md`.

Install them only when the user wants project-scoped custom agents:

```bash
python3 <skills-file-root>/scripts/init_project.py --install-agents
```

Use custom agents only for noisy, read-heavy discovery and skeptical audits. They are not the source of truth. The source of truth is deterministic evidence: test exit codes, build results, coverage numbers, benchmark output, MCP resource data, artifacts, or human review gates.
