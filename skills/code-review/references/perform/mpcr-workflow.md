# Reviewer workflow: `mpcr` coordination

Perform an adversarial code review using UACRP and coordinate artifacts via `mpcr`.

## Non-negotiables (do these every time)

- You SHALL produce a UACRP report (Sections 0–11) with exactly one verdict: `APPROVE`, `REQUEST_CHANGES`, or `BLOCK`.
- You SHALL reuse the same `reviewer_id` for **all** reviews you perform in this repo (even across multiple target refs).
- You SHALL keep coordination state up to date via `mpcr` (status, phase, notes, counts).
- You SHALL NOT leave scratch files behind in the repo when you finish (see Scratch policy below).

## Workflow

You SHALL use `mpcr` for all operations and interactions regarding the `_session.json` file. The CLI is located at `<skills-file-root>/scripts/mpcr` (it auto-compiles on first run; requires `cargo`). Run `mpcr --help` for full command reference.

> **CRITICAL: Avoid environment-variable workflows in isolated shells**
>
> Many agent tools run each shell command in an isolated session; environment variables set in one invocation do not persist to the next.
> For that reason, `mpcr` does **not** read `MPCR_*` environment variables by default (you SHALL pass explicit flags). IF you are running in a persistent shell and want env-var defaults THEN pass `--use-env`.
>
> You SHALL:
> - Run `mpcr reviewer register --print-env` and store the printed `MPCR_*` values in your context.
> - Pass those values explicitly on later commands via `--session-dir`, `--reviewer-id`, `--session-id`, etc.
>
> You MAY use `mpcr reviewer register --emit-env sh` in POSIX shells to print `export ...` lines for convenience in a persistent shell.

### 0) Register and capture deterministic context (recommended)

1) Register for the target ref and print the full session context:

```sh
mpcr reviewer register --target-ref '<REF>' --print-env
```

`--print-env` outputs `MPCR_*` as `KEY=value` lines (or JSON when combined with `--json`).

This prints:
- `MPCR_REVIEWER_ID` (your stable identity; reuse across target refs)
- `MPCR_SESSION_ID` (the session for this target ref)
- `MPCR_SESSION_DIR`, `MPCR_SESSION_FILE`, `MPCR_TARGET_REF`
- `MPCR_REPO_ROOT` (resolved repo root used for default session paths)
- `MPCR_DATE` (resolved session date used for default session paths)

2) Store `MPCR_REVIEWER_ID` in your context and reuse it for all future reviews in this repo.

3) When you switch target refs, re-run register while keeping the same reviewer id:

```sh
mpcr reviewer register --target-ref '<NEW_REF>' --reviewer-id <ID8> --print-env
```

Where `<ID8>` is the `MPCR_REVIEWER_ID` value you captured earlier.

4) Use the printed values explicitly in later commands:

```sh
mpcr reviewer update --session-dir <DIR> --reviewer-id <ID8> --session-id <ID8> --status IN_PROGRESS --phase INGESTION
```

### 1) Target ref selection (use high-quality, specific refs)

**Target ref examples (use high-quality, specific refs):**
- Commit: `8a99441ef6189b57881fa7f9127bb0eb440af651`
- Branch: `main` or `refs/heads/main`
- PR: `pr/123` (or your repo's convention)
- Worktree / uncommitted: `worktree:feature/foo (uncommitted)`

### Switching target refs (same reviewer, new session context)

WHEN you switch to reviewing a different target ref THEN you SHALL re-run `register` and capture the new session context. Reuse the same `reviewer_id`.

```sh
mpcr reviewer register --target-ref '<NEW_REF>' --reviewer-id <ID8> --print-env
mpcr reviewer update --session-dir <DIR> --reviewer-id <ID8> --session-id <ID8> --status IN_PROGRESS --phase INGESTION
```

This keeps `MPCR_REVIEWER_ID` stable and updates `MPCR_SESSION_ID` / `MPCR_TARGET_REF` for the new review.

### 2) Keep coordination fields updated while you work

You SHALL set `status` and `phase` at minimum at the boundaries below. Use explicit `--session-dir`, `--reviewer-id`, and `--session-id` on each mutating command (recommended for agent shells).

**Example snippet (after `mpcr reviewer register ... --print-env`):**

```sh
mpcr reviewer update --session-dir <DIR> --reviewer-id <ID8> --session-id <ID8> --status IN_PROGRESS --phase INGESTION
# ... perform ingestion work ...
mpcr reviewer update --session-dir <DIR> --reviewer-id <ID8> --session-id <ID8> --phase DOMAIN_COVERAGE
# ... perform domain coverage work ...
mpcr reviewer update --session-dir <DIR> --reviewer-id <ID8> --session-id <ID8> --phase THEOREM_GENERATION
# ... perform theorem generation work ...
mpcr reviewer update --session-dir <DIR> --reviewer-id <ID8> --session-id <ID8> --phase ADVERSARIAL_PROOFS
# ... perform adversarial proofs work ...
mpcr reviewer update --session-dir <DIR> --reviewer-id <ID8> --session-id <ID8> --phase SYNTHESIS
# ... perform synthesis work ...
mpcr reviewer update --session-dir <DIR> --reviewer-id <ID8> --session-id <ID8> --phase REPORT_WRITING
```

IF you lose the context values THEN re-run `mpcr reviewer register --target-ref '<REF>' --reviewer-id <ID8> --print-env` to reprint them.

Notes are a shared scratchpad between you and the applicator.

WHEN you notice an observation you may want to cite later (or that could help the applicator start early) THEN you SHOULD write a note via `mpcr reviewer note` instead of holding it in your head.

WHEN you write a note THEN you SHALL include code anchors for each involved location: `path:line` plus the function/symbol.
IF the note implies a merge condition or verification step THEN you SHOULD state it explicitly.

WHEN you discover a likely non-`APPROVE` outcome THEN you SHALL post a `blocker_preview` note early with merge condition(s) and anchors (do not wait for the full report).

**Example:**

```sh
mpcr reviewer note --session-dir <DIR> --reviewer-id <ID8> --session-id <ID8> --note-type blocker_preview --content "Merge conditions: run required checks and add evidence to the report. Anchors: crates/foo/src/bar.rs:123 (fn handle_request), crates/foo/src/baz.rs:77 (impl Service::call)."
```

### 3) Finalize without leaving scratch files

You SHALL finalize via `mpcr reviewer finalize` and you SHALL record accurate severity counts (they MUST match the report).
`mpcr reviewer finalize` defaults all counts to `0`; you SHALL pass the real counts via `--blocker/--major/--minor/--nit` (explicitly include zeros if needed).

Prefer stdin / heredocs so you do not leave a `report.md` behind:

```sh
mpcr reviewer finalize --session-dir <DIR> --reviewer-id <ID8> --session-id <ID8> --verdict REQUEST_CHANGES --major 2 <<'EOF'
## Adversarial Code Review: <Ref>
...
EOF
```

**Complete single-block example (entire review lifecycle):**

```sh
mpcr reviewer register --target-ref '<REF>' --reviewer-id <ID8> --print-env
mpcr reviewer update --session-dir <DIR> --reviewer-id <ID8> --session-id <ID8> --status IN_PROGRESS --phase INGESTION
# ... read code, analyze ...
mpcr reviewer update --session-dir <DIR> --reviewer-id <ID8> --session-id <ID8> --phase REPORT_WRITING
mpcr reviewer finalize --session-dir <DIR> --reviewer-id <ID8> --session-id <ID8> --verdict APPROVE --blocker 0 --major 0 --minor 0 --nit 1 <<'EOF'
## Adversarial Code Review: <Ref>
... full report content ...
EOF
```

## Scratch policy (avoid repo litter)

- You SHOULD NOT create scratch markdown files in the repo root.
- IF you must write scratch files to disk THEN you SHALL write them under `.local/scratch/code_reviews/<reviewer_id>/<session_id>/` to avoid collisions across target refs.
- WHEN you finish the review THEN you SHALL delete your scratch directory:

```sh
mkdir -p ".local/scratch/code_reviews/<reviewer_id>/<session_id>"

# Example of using a scratch report file:
#   SCRATCH_REPORT=".local/scratch/code_reviews/<reviewer_id>/<session_id>/report.md"
#   echo "report content" > "$SCRATCH_REPORT"
#   mpcr reviewer finalize --session-dir <DIR> --reviewer-id <ID8> --session-id <ID8> --report-file "$SCRATCH_REPORT" --verdict APPROVE

rm -rf ".local/scratch/code_reviews/<reviewer_id>/<session_id>"
# Optional: cleanup all scratch for this reviewer id:
#   rm -rf ".local/scratch/code_reviews/<reviewer_id>"
```

## Inputs

- A diff/patch/PR context (provided by the user and/or repository checkout).
- `mpcr` does NOT fetch diffs; it only coordinates sessions and artifacts.

## Without session infrastructure

IF you cannot run `mpcr` or you lack filesystem write access THEN you SHALL output the full UACRP report directly in chat. The report itself is the deliverable.
