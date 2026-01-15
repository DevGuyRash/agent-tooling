# Applicator workflow: `mpcr` coordination

You apply code review feedback by consuming completed review reports and recording dispositions and progress via `mpcr`.

## Workflow

You SHALL use `mpcr` for all operations and interactions regarding the `_session.json` file and for gathering, viewing, and interacting with review reports. The CLI is located at `<skills-file-root>/scripts/mpcr`. It auto-compiles on first run (requires `cargo`). Run `mpcr --help` for full command reference.

> **CRITICAL: Avoid environment-variable workflows in isolated shells**
>
> Many agent tools run each shell command in an isolated session; environment variables set in one invocation do not persist to the next.
> For that reason, `mpcr` does **not** read `MPCR_*` environment variables by default (you SHALL pass explicit flags). IF you are running in a persistent shell and want env-var defaults THEN pass `--use-env`.
>
> You SHALL:
> - Use `mpcr session reports ... --json` to fetch `session_dir`, `reviewer_id`, and `session_id`.
> - Pass those values explicitly on `mpcr applicator ...` commands via `--session-dir`, `--reviewer-id`, and `--session-id`.
>
> You MAY use `--emit-env sh` in POSIX shells to print `export ...` lines for convenience, but explicit flags remain the default/recommended coordination mechanism.

**Complete single-block example:**

```sh
# Fetch reports first (no env vars needed for read-only queries)
mpcr session reports closed --include-notes --include-report-contents --json

# Then, when processing a specific review entry, pass explicit flags:
mpcr applicator set-status --session-dir <DIR> --reviewer-id <ID8> --session-id <ID8> --initiator-status APPLYING
# ... apply fixes ...
mpcr applicator note --session-dir <DIR> --reviewer-id <ID8> --session-id <ID8> --note-type applied --content "Fixed in commit abc123"
mpcr applicator set-status --session-dir <DIR> --reviewer-id <ID8> --session-id <ID8> --initiator-status APPLIED
```

Tip: IF you are processing one review entry at a time THEN you SHALL store `session_dir`, `reviewer_id`, and `session_id` in your context and reuse them explicitly in subsequent `mpcr` commands.

IF you must split your workflow across multiple shell invocations THEN you SHALL pass `--session-dir`, `--reviewer-id`, and `--session-id` explicitly to each command.

Read each report, then read the actual code at the referenced anchors. Verify findings before deciding to fix, decline, or defer.

## Inputs

- A session directory under `.local/reports/code_reviews/YYYY-MM-DD/` containing `_session.json` and reviewer report(s).

## Without session infrastructure

IF you cannot run `mpcr` or session files don't exist THEN you SHALL work directly from the review content provided to you. Your code changes and stated dispositions are the deliverables.
