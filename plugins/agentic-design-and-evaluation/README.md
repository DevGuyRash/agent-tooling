# Agentic Design & Evaluation

Write instructions other AI agents follow, audit them, compare alternatives with repeated blind trials, and heal what keeps going wrong from the evidence agents leave behind. The package works across hosts and models: its trial runtime runs Codex, Claude Code, or any command, and its session digest reads Codex, Claude Code, and Gemini CLI logs.

| Entry | Use it for |
| --- | --- |
| [Prompt and Context Design](skills/prompt-context-design/SKILL.md) | Writing or revising prompts, skills, instruction files, delegation briefs, and prompts for continuing or unattended work. |
| [Skill Auditor](skills/skill-auditor/SKILL.md) | A verdict (keep, cut, move, rewrite) with evidence for each part of an existing skill, plugin, or instruction file. |
| [Split Testing](skills/split-testing/SKILL.md) | Deciding between alternatives of any kind; for agent behavior, repeated isolated trials through the trial runtime. |
| [Self-Healing](skills/self-healing/SKILL.md) | Healing passes over recent sessions that fix causes at their source, verified by trials, with a report of what only the user can decide. |
| [Foundational Knowledge](skills/foundational-knowledge/SKILL.md) | The research behind these choices and the authoring guidance, for large design sessions. |

## Shared resources

These can be read directly, without invoking an entry: the [foundational knowledge](skills/foundational-knowledge/references/foundational-knowledge.md) (the research behind the package), the [authoring guidance](skills/foundational-knowledge/references/governing-architecture.md) (what instructions written for another AI hold), the [portable skill format](skills/skill-auditor/references/open-standard.md), and [host delivery](skills/skill-auditor/references/host-contracts.md) (what each host actually loads).

## Evidence over reading

Whether an instruction helps is a question about behavior, and reading a text cannot settle it. The [trial runtime](skills/split-testing/references/trials.md) (`skills/split-testing/scripts/trial.py`, Python 3.11+ standard library) runs each alternative on each scenario several times in fresh, confined homes and working directories (bubblewrap on Linux), interleaves the order, applies deterministic checks on the resulting state and an optional blind judge, keeps every run's native record, and reports pass counts with intervals. Scenario checks are qualified against known-good and known-bad behavior before they are trusted, and a second stage can hand what one agent wrote to the agent that follows it.

The repository's own scenarios live in `evals/` at the repository root; each is a regression check for a concern agents have failed on.

## Self-healing tools

[`digest.py`](skills/self-healing/scripts/digest.py) summarizes recent sessions across hosts without interpretation: the user's corrections and "continue" nudges paired with the agent message before each, heartbeat prompts, failing command shapes by distinct session, skill files agents read, leftover worktrees and merged branches, and agent-created automations with their stop clauses; `digest.py show` prints the exchange behind any count. [`heal`](skills/self-healing/scripts/heal) starts a healing pass in a fresh session on whichever of Codex, Claude Code, or Gemini is installed and prepares changes on one `heal` branch per repository without landing them unless told to. A weekly systemd timer is included under `assets/` for users who want one; nothing installs it.

## Installation

Install the complete plugin; the entries share resources and extracting one skill directory omits them. For this repository, run `scripts/install-all --include agentic-design-and-evaluation` from the repository root after publication to its canonical GitHub marketplace, omitting `--source` for normal installation. A fresh session picks up the installed catalog.

This package replaces the earlier `skill-auditor`, `split-testing`, and `friction-diagnostics` plugin identities. Friction Diagnostics stores (`.local/reports/friction/events.jsonl`) remain readable evidence: `digest.py --friction DIR` includes them.

## Limits

The package's structural tests cover metadata, resource resolution, the runtime, and the digest. Behavior claims come from trial runs: which model, how many runs, and which scenarios are part of each claim, and a result on one model family speaks for that family.
