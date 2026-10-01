# Agentic Design & Evaluation

Write instructions other AI agents follow, audit them, compare alternatives with repeated blind trials, and heal what keeps going wrong from the evidence agents leave behind. The package works across hosts and models: its trial runtime runs Codex, Claude Code, or any command, and its evidence gatherer reads Codex, Claude Code, and Gemini CLI logs.

| Entry | Use it for |
| --- | --- |
| [Prompt and Context Design](skills/prompt-context-design/SKILL.md) | Writing or revising prompts, skills, instruction files, delegation briefs, and prompts for continuing or unattended work. |
| [Skill Auditor](skills/skill-auditor/SKILL.md) | A verdict (keep, cut, move, rewrite) with evidence for each part of an existing skill, plugin, or instruction file. |
| [Split Testing](skills/split-testing/SKILL.md) | Deciding between alternatives of any kind; for agent behavior, repeated isolated trials through the trial runtime. |
| [Self-Healing](skills/self-healing/SKILL.md) | Healing passes over recent sessions that fix causes at their source, verified by trials, with a report of what only the user can decide. |
| [Foundational Knowledge](skills/foundational-knowledge/SKILL.md) | The research behind these choices and the authoring guidance, for large design sessions. |

## Shared resources

These can be read directly, without invoking an entry: the [foundational knowledge](skills/foundational-knowledge/references/foundational-knowledge.md) (the research behind the package), the [authoring guidance](skills/foundational-knowledge/references/governing-architecture.md) (what instructions written for another AI hold), the [portable skill format](skills/skill-auditor/references/open-standard.md), and [host delivery](skills/skill-auditor/references/host-contracts.md) (what each host actually loads).

These entries carry domain knowledge, not the duties every task has (finishing, checking, gates, cleanup); those belong to the always-loaded instruction layer, and [Prompt and Context Design's tested standing-instruction text](skills/prompt-context-design/SKILL.md#a-tested-standing-instruction-text) is the trialed example of it.

## Evidence over reading

Whether an instruction helps is a question about behavior, and reading a text cannot settle it. The [trial runtime](skills/split-testing/references/trials.md) (`skills/split-testing/scripts/trial.py`, Python 3.11+ standard library) runs each alternative on each scenario several times in fresh, confined homes and working directories (bubblewrap on Linux), interleaves the order, applies deterministic checks on the resulting state and an optional blind judge, keeps every run's native record, and reports pass counts with intervals. Scenario checks are qualified against known-good and known-bad behavior before they are trusted, and judges against fixed reference outcomes, preferably with a judge from another model family than the executors; stored runs can be re-scored and re-judged when either changes, and a second stage can hand what one agent wrote to the agent that follows it.

The repository's own scenarios live in `evals/` at the repository root; each is a regression check for a concern agents have failed on.

## Self-healing tools

[`gather.py`](skills/self-healing/scripts/gather.py) extracts recent sessions across hosts into a small output directory ready to read: an index of every session, a faithful timestamped transcript per session (user messages, agent messages, tool calls and their results, compactions, and any record type it doesn't recognize noted rather than dropped), and the git facts and scheduled automations of the working directories those sessions used. It does no classification of what a message means; that reading is left to the executor. [Running a pass](skills/self-healing/references/running-passes.md) covers starting a pass on each host, and scheduling one, when asked, with the host's own features or the operating system's scheduler.

## Installation

Install the complete plugin; the entries share resources and extracting one skill directory omits them. For this repository, run `scripts/install-all --include agentic-design-and-evaluation` from the repository root after publication to its canonical GitHub marketplace, omitting `--source` for normal installation. A fresh session picks up the installed catalog.

This package replaces the earlier `skill-auditor`, `split-testing`, and `friction-diagnostics` plugin identities. Friction Diagnostics stores (`.local/reports/friction/events.jsonl`) remain readable evidence, alongside whatever `gather.py` wrote.

## Limits

The package's structural tests cover metadata, resource resolution, the runtime, and the gatherer. Behavior claims come from trial runs: which model, how many runs, and which scenarios are part of each claim, and a result on one model family speaks for that family.
