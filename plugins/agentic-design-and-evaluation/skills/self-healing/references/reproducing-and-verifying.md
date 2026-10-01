# Reproducing and verifying

## Conditions

A reproduction holds constant what the claimed cause depends on and nothing it does not. A deterministic defect in code, a tool, or a script reproduces with a command or test run from a clean state; repeating it a few times confirms that the conditions, not leftover state, produce the failure. Agent behavior varies between runs, so an attempt is a set of fresh runs, and the failure condition is a count over that set fixed in advance ("the agent stops before step 2 in at least 4 of 5 runs"). Five runs per attempt is a common floor; the Split Testing trial runtime reports each rate with an interval so a before-and-after difference can be told from noise.

Each run starts from a fresh environment that carries the source under test and the task, and nothing written by an earlier run. Where the source serves several hosts or models, a reproduction on one host speaks for that host.

A severe incident that is unsafe to repeat in place, such as a destructive command, reproduces in a disposable copy of the environment.

## The check

A check reads resulting state (files, commits, remotes, recorded tool calls, the change's own output) in preference to wording. Before relying on it, run a reference behavior that should pass and one that should fail; a check that passes both or fails both measures something else. A check can also be wrong about the requirement: counting every mention of "ask" in a repaired skill counts "without asking" as asking. Correcting such a check is legitimate when the requirement shows it wrong, and the correction and its reason stay with the evidence.

Scenarios written for a reproduction are lasting assets. The failing scenario joins the set that later changes run against, and a few scenarios stay out of development so a change can be tested for generalizing beyond the cases that shaped it.

## The trial runtime

For agent behavior, [`trial.py`](../../split-testing/scripts/trial.py) in Split Testing runs each arm on each scenario in isolated homes and working directories, repeats, interleaves, applies checks and an optional blind judge, and keeps every run's native record. The arms are the source before the change, the source after it, and, when the question is whether the source should exist, no source. Its plan and scenario format are in [trials.md](../../split-testing/references/trials.md).

## How an agent read its instructions

Four kinds of evidence exist, with different weight:

- Exposure. Native session logs record the instruction text actually delivered, including host-provided system prompts, loaded skills, compaction summaries, and tool output. Whether a file existed, whether its text entered the context, and whether the agent said it followed it are three different facts.
- The agent's account at the time. An observation written in the moment records what the agent took its guidance to mean before any outcome was known. It is a self-report, and it covers only what the agent recognized as worth recording.
- A later interview of a forked session. It has the exact context and can state an interpretation, and it remains a self-report. Hosts that keep reasoning private do not disclose it to a fork.
- Replay. Branching the session before the instruction's first relevant exposure, changing that one instruction, and regenerating the rest N times shows whether the instruction influenced the behavior. Unchanged reruns give the baseline variation, and a meaning-preserving rewording separates the instruction's content from its wording. Removing an instruction after it has already shaped a plan tests responsiveness to a late edit, not the instruction's influence.

An account that names an instruction as the reason for a behavior is a hypothesis that replay can test.

## Session logs

`scripts/gather.py [--since 7d|YYYY-MM-DD] [--until YYYY-MM-DD] [--out DIR] [--force] [--root HOST=PATH ...] [--max-chars N]` reads Codex rollouts (`~/.codex/sessions` and `.../archived_sessions`, or under `$CODEX_HOME`), Claude Code transcripts (`~/.claude/projects`, or `$CLAUDE_CONFIG_DIR/projects`), and Gemini CLI chats (`~/.gemini/tmp/*/chats`, both its legacy `.json` and its current append-only `.jsonl` shape), plus the git state of the working directories those sessions used. With no `--out` it writes to a new private (mode 0700) temporary directory and prints that path; an explicit `--out` that already has content in it is refused unless `--force`. It writes an index and one faithful, timestamped transcript per session (user messages, agent messages, tool calls and their results, compactions, and any record type it does not render as one of those, as a note naming its type and raw file:line, never dropped -- named from the raw log file's own identity, not from the id inside its records, since a Claude subagent transcript carries its parent's sessionId rather than one of its own), and a workspace file of each repository's branches, worktrees, and stashes, and any scheduled automations it can find, as facts only. It does no counting-as-interpretation of what a message means; masks token-like strings, keys, and bearer/basic/URL credentials in everything it writes, while leaving a bare 40- or 64-character hex string (a git SHA, a sha256 digest) unmasked as evidence a pass needs to check state.

Codex logs keep reasoning encrypted, and their readable summaries are short headings, so the agent's own account of its interpretation exists only where it wrote one.
