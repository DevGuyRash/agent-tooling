# Applicator workflow: `mpcr` coordination

You apply code review feedback by consuming completed review reports and recording dispositions and progress via `mpcr`.

## Workflow

You SHALL use `mpcr` for all operations and interactions regarding the `_session.json` file and for gathering, viewing, and interacting with review reports. The CLI is located at `<skills-file-root>/scripts/mpcr`. It auto-compiles on first run (requires `cargo`). Run `mpcr --help` for full command reference.

> **CRITICAL: Isolated shell sessions**
>
> WHEN you execute shell commands via a tool (e.g., Bash tool) THEN each invocation runs in an **isolated shell session**. Environment variables set in one invocation do NOT persist to subsequent invocations.
>
> You SHALL combine environment variable exports AND all subsequent `mpcr` commands that depend on those variables into a SINGLE shell invocation (one tool call).
>
> **WRONG** (two separate tool calls — env vars are lost):
> ```sh
> # Tool call 1:
> export MPCR_SESSION_DIR='.local/reports/code_reviews/2026-01-14'
> export MPCR_REVIEWER_ID='deadbeef'
> export MPCR_SESSION_ID='sess0001'
> ```
> ```sh
> # Tool call 2 (FAILS: environment variables are unset):
> mpcr applicator set-status --initiator-status APPLYING
> ```
>
> **CORRECT** (single tool call — env vars persist within the session):
> ```sh
> export MPCR_SESSION_DIR='.local/reports/code_reviews/2026-01-14'
> export MPCR_REVIEWER_ID='deadbeef'
> export MPCR_SESSION_ID='sess0001'
> mpcr applicator set-status --initiator-status APPLYING
> mpcr applicator note --note-type applied --content "Fixed in commit abc123"
> ```

**Complete single-block example:**

```sh
# Fetch reports first (no env vars needed for read-only queries)
mpcr session reports closed --include-notes --include-report-contents --json

# Then, when processing a specific review entry, set env vars and use them:
export MPCR_SESSION_DIR='.local/reports/code_reviews/2026-01-14'
export MPCR_REVIEWER_ID='deadbeef'
export MPCR_SESSION_ID='sess0001'
mpcr applicator set-status --initiator-status APPLYING
# ... apply fixes ...
mpcr applicator note --note-type applied --content "Fixed in commit abc123"
mpcr applicator set-status --initiator-status APPLIED
```

Tip: IF you are processing one review entry at a time THEN you MAY export `MPCR_SESSION_DIR`, `MPCR_REVIEWER_ID`, and `MPCR_SESSION_ID` for that entry and omit repeated flags in subsequent `mpcr` commands.

IF you must split your workflow across multiple shell invocations THEN you SHALL repeat the environment variable exports at the start of EACH new invocation, OR pass `--session-dir`, `--reviewer-id`, and `--session-id` explicitly to each command.

Read each report, then read the actual code at the referenced anchors. Verify findings before deciding to fix, decline, or defer.

## Inputs

- A session directory under `.local/reports/code_reviews/YYYY-MM-DD/` containing `_session.json` and reviewer report(s).

## Without session infrastructure

IF `mpcr` is unavailable or session files don't exist THEN work directly from the review content provided to you. Your code changes and stated dispositions are the deliverables.
