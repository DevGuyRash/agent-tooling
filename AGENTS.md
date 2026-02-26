# Repo-wide agent notes

This file contains cross-cutting constraints that apply regardless of language or skill.
Language/toolchain-specific workflows live in the corresponding skill `SKILL.md` files under `skills/`.

---

## ⚠️ Command Isolation: Environment Variables Do NOT Persist Across Commands

**Critical for agents and subagents**: Each `exec_command` / shell invocation runs in a **completely isolated** process. Environment variables set via `export`, `cd` directory changes, shell aliases, and any other process-level state are **lost** between commands.

### What does NOT work

```bash
# Command 1
export MPCR_REVIEWER_ID=deadbeef
export MPCR_SESSION_ID=sess0001
```
```bash
# Command 2 — these are NOT set; env is empty again
mpcr reviewer update --use-env --status IN_PROGRESS  # FAILS: env vars are gone
```

### What works instead

**Option A (recommended): pass values as CLI flags**
```bash
mpcr reviewer update --reviewer-id deadbeef --session-id sess0001 --status IN_PROGRESS
```

**Option B: use `--print-env` to capture, then inline on the same command**
```bash
# Single command — everything stays in one process
mpcr reviewer register --target-ref main --print-env
# Then use the output values as flags in subsequent commands
```

**Option C: chain commands in a single shell invocation**
```bash
export MPCR_REVIEWER_ID=deadbeef && export MPCR_SESSION_ID=sess0001 && mpcr --use-env reviewer update --status IN_PROGRESS
```

### Why this matters for `mpcr`

The `mpcr` CLI has `--use-env` which reads `MPCR_*` environment variables as defaults.
This is designed for shell scripts and CI pipelines where the entire pipeline runs in one shell session.
When used by agents (where each command is a separate process), `--use-env` provides no benefit.

**Always prefer explicit CLI flags** (`--reviewer-id`, `--session-id`, `--session-dir`, etc.) over `--use-env` when running from agents.

---

## Skill authoring: `<skills-file-root>`

When writing or editing a skill, use `<skills-file-root>` as the path prefix for all references to files within the skill directory (scripts, references, assets). It resolves to the directory containing the skill's `SKILL.md`.
