# ADR 0030: Self-Healing gathers evidence without classifying it

- Status: Accepted; supersedes ADR 0028's cross-host digest and launcher for Self-Healing.
- Scope: Self-Healing's scripts and how a pass starts.

## Context

The digest classified the user's messages with English phrase patterns as corrections or nudges, ranked threads by a fixed formula, and showed only the top items, so code decided what the healing agent saw first, in ways that failed on ordinary phrasing and on every other language; it read one version of each host's log format and silently dropped what it did not recognize. The user asked that the script "just pulls out all of the stuff and into a file that's ready to be read ... or just points it to the threads", relying on the agent's judgment. A systemd timer and a shell launcher tied scheduled passes to one operating system.

## Decision

`scripts/gather.py` finds session logs from Codex, Claude Code, and Gemini CLI for a time window (honoring each host's home override) and writes a readable transcript per session, an index, and the workspace facts (branches, worktrees, stashes, scheduled automations), masking obvious secrets; it classifies and ranks nothing, and renders a record it does not know as a note pointing at the raw line. For a host it does not cover, the skill directs the agent to read that host's session files directly. A pass starts in a fresh session on any host, or on the host's or the operating system's own scheduler only when the user asks; the timer and launcher are gone.

## Consequences

On native-log healing scenarios with the logs where each host keeps them and a prompt naming no path, agents on two model families passed 10 of 18 runs with the gatherer, 5 of 18 given only where hosts keep their logs, and 0 of 18 without the skill; the gatherer costs about a third more output. Records: `context/convergence-rca/experiments/self-healing/README.md` in the maintainer's local context.
