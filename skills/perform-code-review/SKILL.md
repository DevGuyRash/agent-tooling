---
name: perform-code-review
description: Perform adversarial code reviews using the UACRP protocol. Use when reviewing code changes, PRs, or diffs. Produces structured review reports with verdicts (APPROVE/REQUEST_CHANGES/BLOCK), findings by severity, and evidence-backed proofs.
compatibility: Requires a POSIX shell. If `<skills-file-root>/scripts/mpcr` is not prebuilt, requires a Rust toolchain (`cargo`/`rustc`) to build `<skills-file-root>/scripts/mpcr-src`.
---

# Perform Code Review

Perform an adversarial code review using UACRP and coordinate artifacts via `mpcr`.

## Non-negotiables (do these every time)

- You SHALL produce a UACRP report (Sections 0–11) with exactly one verdict: `APPROVE`, `REQUEST_CHANGES`, or `BLOCK`.
- You SHALL reuse the same `reviewer_id` for **all** reviews you perform in this repo (even across multiple target refs).
- You SHALL keep coordination state up to date via `mpcr` (status, phase, notes, counts).
- You SHALL NOT leave scratch files behind in the repo when you finish (see Scratch policy below).

## UACRP ingestion (once per conversation)

Before reviewing any code, you SHALL read `<skills-file-root>/references/uacrp.md`.

- IF you need to ingest it in parts THEN you SHALL read it in **<= 500-line chunks**.
- IF you have already ingested UACRP earlier in this conversation THEN you SHALL NOT re-ingest it; proceed with the workflow below.

## Deliverables

- A UACRP report (Sections 0–11) with exactly one verdict: `APPROVE`, `REQUEST_CHANGES`, or `BLOCK`
- Findings anchored to specific code locations with evidence
- Report saved via `mpcr reviewer finalize` (or output to chat if `mpcr` is unavailable)

## Workflow

You SHALL use `mpcr` for all operations and interactions regarding the `_session.json` file. The CLI is located at `<skills-file-root>/scripts/mpcr` (it auto-compiles on first run; requires `cargo`). Run `mpcr --help` for full command reference.

### 0) Register and capture deterministic context (recommended)

Register once per target ref and capture the returned context into environment variables:

```sh
eval "$(mpcr reviewer register --target-ref '<REF>' --emit-env sh)"
```

This sets:
- `MPCR_REVIEWER_ID` (your stable identity for this agent process; reused across target refs)
- `MPCR_SESSION_ID` (the session for this target ref)
- `MPCR_SESSION_DIR`, `MPCR_SESSION_FILE`, `MPCR_TARGET_REF`

IF `MPCR_REVIEWER_ID` is already set by the launcher THEN `mpcr` will reuse it. Otherwise `mpcr` generates one and exports it; it remains stable for the rest of the process.

### 1) Target ref selection (use high-quality, specific refs)

**Target ref examples (use high-quality, specific refs):**
- Commit: `8a99441ef6189b57881fa7f9127bb0eb440af651`
- Branch: `main` or `refs/heads/main`
- PR: `pr/123` (or your repo’s convention)
- Worktree / uncommitted: `worktree:feature/foo (uncommitted)`

### Switching target refs (same reviewer, new session context)

WHEN you switch to reviewing a different target ref THEN you SHALL re-run register and refresh the exported context:

```sh
eval "$(mpcr reviewer register --target-ref '<NEW_REF>' --emit-env sh)"
```

This reuses `MPCR_REVIEWER_ID` and updates `MPCR_SESSION_ID` / `MPCR_TARGET_REF` for the new review.

### 2) Keep coordination fields updated while you work

You SHALL set `status` and `phase` at minimum at the boundaries below:

```sh
mpcr reviewer update --status IN_PROGRESS --phase INGESTION
mpcr reviewer update --phase DOMAIN_COVERAGE
mpcr reviewer update --phase THEOREM_GENERATION
mpcr reviewer update --phase ADVERSARIAL_PROOFS
mpcr reviewer update --phase SYNTHESIS
mpcr reviewer update --phase REPORT_WRITING
```

Notes are a shared scratchpad between you and the applicator.

WHEN you notice an observation you may want to cite later (or that could help the applicator start early) THEN you SHOULD write a note via `mpcr reviewer note` instead of holding it in your head.

WHEN you write a note THEN you SHALL include code anchors for each involved location: `path:line` plus the function/symbol.
IF the note implies a merge condition or verification step THEN you SHOULD state it explicitly.

WHEN you discover a likely non-`APPROVE` outcome THEN you SHALL post a `blocker_preview` note early with merge condition(s) and anchors (do not wait for the full report).

Example:

```sh
mpcr reviewer note --note-type blocker_preview --content "Merge conditions: run required checks and add evidence to the report. Anchors: crates/foo/src/bar.rs:123 (fn handle_request), crates/foo/src/baz.rs:77 (impl Service::call)."
```

### 3) Finalize without leaving scratch files

You SHALL finalize via `mpcr reviewer finalize` and you SHALL record accurate severity counts (they MUST match the report).
`mpcr reviewer finalize` defaults all counts to `0`; you SHALL pass the real counts via `--blocker/--major/--minor/--nit` (explicitly include zeros if needed).

Prefer stdin / heredocs so you do not leave a `report.md` behind:

```sh
mpcr reviewer finalize --verdict REQUEST_CHANGES --major 2 <<'EOF'
## Adversarial Code Review: <Ref>
...
EOF
```

## Scratch policy (avoid repo litter)

- You SHOULD NOT create scratch markdown files in the repo root.
- IF you must write scratch files to disk THEN you SHALL write them under `.local/scratch/code_reviews/<reviewer_id>/<session_id>/` to avoid collisions across target refs.
- WHEN you finish the review THEN you SHALL delete your scratch directory:

```sh
SCRATCH_DIR=".local/scratch/code_reviews/$MPCR_REVIEWER_ID/$MPCR_SESSION_ID"
mkdir -p "$SCRATCH_DIR"
# Example scratch file path (optional):
#   SCRATCH_REPORT="$SCRATCH_DIR/report.md"
#   mpcr reviewer finalize \
#     --verdict APPROVE --report-file "$SCRATCH_REPORT"
rm -rf "$SCRATCH_DIR"
# Optional: cleanup all scratch for this reviewer id:
#   rm -rf ".local/scratch/code_reviews/$MPCR_REVIEWER_ID"
```

## Inputs

- A diff/patch/PR context (provided by the user and/or repository checkout).
- `mpcr` does NOT fetch diffs; it only coordinates sessions and artifacts.

## Without session infrastructure

IF `mpcr` is unavailable or you lack filesystem write access THEN output the full UACRP report directly in chat. The report itself is the deliverable.
