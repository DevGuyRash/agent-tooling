# Custom Agent Templates

GoalSpec ships read-only agent templates under `assets/codex-agents/`:

- `goal-discoverer.toml`: read-only project explorer that returns candidate goals with evidence.
- `goal-auditor.toml`: read-only auditor that compares reports/evidence against `.goals/current.md`.
- `decomposition-reviewer.toml`: read-only adversarial reviewer for campaign decompositions — rubric check 10 with a refute bias and a per-child verdict. Spawn it after `validate_campaign.py` passes; apply or explicitly decline each finding in the manifest's `## Decomposition Review` section, closing with per-child verdicts and the `Anchor:` line from validation output.

`init_project.py` installs them into `.codex/agents/` by default (`--no-agents` opts out; existing files are never overwritten without `--overwrite`). On Claude Code hosts the plugin additionally ships `decomposition-reviewer` as a plugin agent (`goalspec:decomposition-reviewer`) — available in every session with no install step. Opting out with `--no-agents` trades away the shipped adversary: the decomposition review then falls back to self-review, which is exactly the weaker mode the reviewer exists to replace — three read-only TOMLs are rarely worth that trade.

Use custom agents for noisy, read-heavy discovery, skeptical audits, and adversarial review. They are not the source of truth. The source of truth is deterministic evidence: test exit codes, build results, coverage numbers, benchmark output, MCP resource data, artifacts, or human review gates.

## Child-author pattern (no shipped template)

Grounding each campaign child in its own sources is judgment work, and one context window authoring many children in a single pass tends to drift into pattern-completing its own earlier children. One good way to get per-child grounding — not the required way — is a fresh scoped pass per child: spawn a subagent (or start a fresh pass) holding only the user's verbatim ask, that child's source sections, the contract template, and the interfaces of neighboring children, and let it write the one contract. The outcome that matters is in the manifest, not the process: each child bound to the specific sections it implements, with an oracle derived from its own terminal clauses.
