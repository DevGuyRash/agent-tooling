#![allow(clippy::print_stderr, clippy::print_stdout)]

//! CLI entrypoint for `mpcr` (UACRP code review coordination utilities).
//!
//! The actual coordination logic lives in the `mpcr` library crate (`src/session.rs`, `src/lock.rs`, etc).

use anyhow::Context;
use clap::{Args, Parser, Subcommand, ValueEnum};
use mpcr::id;
use mpcr::lock::{self, LockConfig};
use mpcr::protocol;
use mpcr::session::{
    append_note, close_child_reviews, collect_reports, finalize_review, load_session,
    register_reviewer, set_initiator_status, spawn_child_reviewers, update_review,
    AppendNoteParams, CloseChildReviewsParams, FinalizeReportInput, FinalizeReviewParams,
    InitiatorStatus, NoteRole, NoteType, RegisterReviewerParams, ReportsFilters, ReportsOptions,
    ReportsResult, ReportsView, ReviewPhase, ReviewVerdict, ReviewerStatus, SessionLocator,
    SetInitiatorStatusParams, SeverityCounts, SpawnChildReviewersParams, UpdateReviewParams,
};
use serde::Serialize;
use serde_json::Value;
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use time::{Date, Month, OffsetDateTime};

#[derive(Parser)]
#[command(
    name = "mpcr",
    version,
    about = "UACRP code review coordination utilities",
    long_about = "UACRP code review coordination utilities.\n\n\
`mpcr` manages a shared *session directory* containing `_session.json`, a lock file, and reviewer report markdown files.\n\
All writers acquire `_session.json.lock` and update `_session.json` via an atomic temp-file replace to avoid races.\n\n\
Use `--json` for machine-readable output (compact).\n\
Use `--json-pretty` for human-readable JSON.\n\
Without `--json` or `--json-pretty`, most commands print compact one-line JSON; `id` commands print raw ids and successful mutations print `ok`.",
    after_long_help = r#"Session directory layout (relative to repo root):
  .local/reports/code_reviews/YYYY-MM-DD/
    _session.json
    _session.json.lock
    {HH-MM-SS-mmm}_{ref}_{reviewer_id}.md

Output path notes:
  report_file  Repo-root-relative report path (stored in `_session.json`)
  report_path  Full filesystem report path (best effort)

Environment variables (optional; only read when `--use-env` is passed):
  MPCR_REPO_ROOT    Repo root used for default session dir (default: auto-detect git root; fallback: cwd)
  MPCR_DATE         Session date (YYYY-MM-DD) used for default session dir (default: today in UTC)
  MPCR_SESSION_DIR  Explicit session directory containing `_session.json`
  MPCR_REVIEWER_ID  Stable reviewer identity (id8) for this executor
  MPCR_SESSION_ID   Current session id (id8) for reviewer/applicator commands
  MPCR_TARGET_REF   Current target_ref (used by `applicator wait`)

Common flows:
  # Reviewer (explicit flags; recommended for isolated shells)
  mpcr reviewer register --target-ref main --print-env
  # Store MPCR_* values from output, then pass explicitly:
  mpcr reviewer update --session-dir <DIR> --reviewer-id <ID8> --session-id <ID8> --status IN_PROGRESS --phase INGESTION

  # Applicator (explicit flags; recommended for isolated shells)
  mpcr session reports closed --include-report-contents --include-leaf-children --json
  mpcr applicator wait --session-dir <DIR>
  mpcr applicator set-status --session-dir <DIR> --reviewer-id <ID8> --session-id <ID8> --initiator-status RECEIVED

"#
)]
struct Cli {
    #[arg(
        long,
        global = true,
        default_value_t = false,
        help = "Emit compact JSON output."
    )]
    json: bool,
    #[arg(
        long,
        global = true,
        default_value_t = false,
        help = "Emit pretty JSON output (implies --json)."
    )]
    json_pretty: bool,
    #[arg(
        long,
        global = true,
        default_value_t = false,
        help = "Read MPCR_* environment variables for default values (opt-in)."
    )]
    use_env: bool,
    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand)]
enum Commands {
    /// Generate IDs (`reviewer_id`, `session_id`, lock owners).
    Id {
        #[command(subcommand)]
        command: IdCommands,
    },
    /// Acquire/release the session lock file (`_session.json.lock`).
    Lock {
        #[command(subcommand)]
        command: LockCommands,
    },
    /// Read session state (`_session.json`) without modifying it.
    Session {
        #[command(subcommand)]
        command: SessionCommands,
    },
    /// Reviewer operations (register/update/note/finalize).
    Reviewer {
        #[command(subcommand)]
        command: ReviewerCommands,
    },
    /// Applicator operations (wait, set `initiator_status`, append notes).
    Applicator {
        #[command(subcommand)]
        command: ApplicatorCommands,
    },
    /// Serve phase-appropriate protocol guidance from embedded data.
    Protocol {
        #[command(subcommand)]
        command: ProtocolCommands,
    },
}

#[derive(Copy, Clone, Debug, ValueEnum)]
enum EmitEnvFormat {
    /// Emit `export KEY='value'` lines intended for POSIX shells (`sh`, `bash`, `zsh`).
    Sh,
}

#[derive(Subcommand)]
enum IdCommands {
    /// Generate an 8-character ASCII id (hex).
    Id8,
    /// Generate a lowercase hex id of length 2*bytes.
    Hex {
        #[arg(
            long,
            value_name = "N",
            help = "Number of random bytes; output length is 2*N hex characters."
        )]
        bytes: usize,
    },
}

#[derive(Subcommand)]
enum LockCommands {
    /// Acquire the session lock file (`_session.json.lock`).
    #[command(after_long_help = r#"Examples:
  # From repo root (or with --repo-root/--date):
  mpcr lock acquire --owner <owner_id8>

  # Explicit session directory:
  mpcr lock acquire --session-dir .local/reports/code_reviews/YYYY-MM-DD --owner <owner_id8>

Notes:
  - `lock acquire` leaves the lock held; release it with `lock release` using the same --owner.
"#)]
    Acquire {
        #[command(flatten)]
        session: SessionDirArgs,
        #[arg(
            long,
            value_name = "OWNER",
            help = "Lock owner identifier (recommend: an id8 from `mpcr id id8`)."
        )]
        owner: String,
        #[arg(
            long,
            default_value_t = 8,
            value_name = "N",
            help = "Maximum retries with exponential backoff before failing with LOCK_TIMEOUT."
        )]
        max_retries: usize,
    },
    /// Release the session lock file if you are the current owner.
    #[command(after_long_help = r#"Examples:
  mpcr lock release --owner <owner_id8>
  mpcr lock release --session-dir .local/reports/code_reviews/YYYY-MM-DD --owner <owner_id8>
"#)]
    Release {
        #[command(flatten)]
        session: SessionDirArgs,
        #[arg(
            long,
            value_name = "OWNER",
            help = "Lock owner identifier (must match the contents of `_session.json.lock`)."
        )]
        owner: String,
    },
}

#[derive(Subcommand)]
enum SessionCommands {
    /// Print the parsed `_session.json`.
    #[command(after_long_help = r#"Examples:
  # From repo root (or with --repo-root/--date):
  mpcr session show

  # Explicit session directory:
  mpcr session show --session-dir .local/reports/code_reviews/YYYY-MM-DD
"#)]
    Show {
        #[command(flatten)]
        session: SessionDirArgs,
    },
    /// Report-oriented session views (open/closed/in-progress).
    #[command(after_long_help = r#"Examples:
  # From repo root (or with --repo-root/--date):
  mpcr session reports open
  mpcr session reports closed --include-report-contents --include-leaf-children --json

  # Filter examples:
  mpcr session reports open --include-notes --only-with-notes
  mpcr session reports closed --only-with-report --include-report-contents
  mpcr session reports closed --include-leaf-children --reviewer-status FINISHED
  mpcr session reports open --reviewer-status IN_PROGRESS,BLOCKED
  mpcr session reports closed --initiator-status RECEIVED --verdict APPROVE

  # Explicit session directory:
  mpcr session reports closed --session-dir .local/reports/code_reviews/YYYY-MM-DD --include-report-contents --include-leaf-children --json
"#)]
    Reports {
        #[command(subcommand)]
        command: ReportsCommands,
    },
}

#[derive(Args)]
struct SessionDirArgs {
    #[arg(
        long,
        value_name = "DIR",
        help = "Session directory containing `_session.json` (default: <repo_root>/.local/reports/code_reviews/<date>)."
    )]
    session_dir: Option<PathBuf>,
    #[arg(
        long,
        value_name = "DIR",
        help = "Repo root used to compute the default session dir (default: auto-detect git root; fallback: cwd)."
    )]
    repo_root: Option<PathBuf>,
    #[arg(
        long,
        value_name = "YYYY-MM-DD",
        help = "Session date used to compute the default session dir (default: today in UTC; set for determinism)."
    )]
    date: Option<String>,
}

struct ResolvedSessionInput {
    session_dir: PathBuf,
    repo_root: PathBuf,
    session_date: Date,
}

#[derive(Args)]
#[allow(clippy::struct_excessive_bools)]
struct ReportsArgs {
    #[command(flatten)]
    session: SessionDirArgs,
    #[arg(
        long,
        value_name = "REF",
        help = "If set, only include reviews matching this target_ref."
    )]
    target_ref: Option<String>,
    #[arg(
        long,
        value_name = "ID8",
        help = "If set, only include reviews matching this session_id."
    )]
    session_id: Option<String>,
    #[arg(
        long,
        value_name = "ID8",
        help = "If set, only include reviews matching this reviewer_id."
    )]
    reviewer_id: Option<String>,
    #[arg(
        long,
        value_enum,
        value_delimiter = ',',
        num_args = 1..,
        value_name = "STATUS",
        help = "Filter by reviewer status (comma-separated or repeatable)."
    )]
    reviewer_status: Vec<ReviewerStatus>,
    #[arg(
        long,
        value_enum,
        value_delimiter = ',',
        num_args = 1..,
        value_name = "STATUS",
        help = "Filter by initiator status (comma-separated or repeatable)."
    )]
    initiator_status: Vec<InitiatorStatus>,
    #[arg(
        long,
        value_enum,
        value_delimiter = ',',
        num_args = 1..,
        value_name = "VERDICT",
        help = "Filter by verdict (comma-separated or repeatable)."
    )]
    verdict: Vec<ReviewVerdict>,
    #[arg(
        long,
        value_enum,
        value_delimiter = ',',
        num_args = 1..,
        value_name = "PHASE",
        help = "Filter by review phase (comma-separated or repeatable)."
    )]
    phase: Vec<ReviewPhase>,
    #[arg(long, help = "Only include reviews that already have a report file.")]
    only_with_report: bool,
    #[arg(
        long,
        help = "Only include reviews that contain at least one note (implies --include-notes)."
    )]
    only_with_notes: bool,
    #[arg(long, help = "Include full notes for each review entry.")]
    include_notes: bool,
    #[arg(
        long,
        visible_alias = "include-report",
        help = "Include report markdown contents for each review entry (if available)."
    )]
    include_report_contents: bool,
    #[arg(
        long,
        help = "Include leaf child reviews in top-level report rows (default hides leaf children)."
    )]
    include_leaf_children: bool,
}

#[derive(Subcommand)]
enum ReportsCommands {
    /// Reviews not in a terminal status (`INITIALIZING`, `IN_PROGRESS`, `BLOCKED`).
    Open(ReportsArgs),
    /// Reviews in a terminal status (`FINISHED`, `CANCELLED`, `ERROR`).
    Closed(ReportsArgs),
    /// Reviews actively in progress (`IN_PROGRESS` only).
    InProgress(ReportsArgs),
}

#[derive(Subcommand)]
enum ReviewerCommands {
    /// Register yourself as a reviewer (creates/updates `_session.json`).
    #[command(after_long_help = r#"Examples:
  # Create or join today's session directory under the current repo root:
  mpcr reviewer register --target-ref main

  # Recommended for isolated shells: print the MPCR_* context for copy/paste reuse:
  mpcr reviewer register --target-ref main --print-env

  # Reuse the same reviewer_id across reviews:
  mpcr reviewer register --target-ref main --reviewer-id <id8> --print-env

  # Worktree / uncommitted review (no commit yet):
  mpcr reviewer register --target-ref 'worktree:feature/foo (uncommitted)' --print-env

  # Explicit date and repo root:
  mpcr reviewer register --target-ref pr/123 --repo-root /path/to/repo --date 2026-01-11

  # Override the session directory location:
  mpcr reviewer register --target-ref main --session-dir .local/reports/code_reviews/YYYY-MM-DD
"#)]
    Register {
        #[arg(
            long,
            value_name = "REF",
            help = "Target reference being reviewed (branch name, PR ref, commit, etc)."
        )]
        target_ref: String,

        #[command(flatten)]
        session: SessionDirArgs,

        #[arg(
            long,
            value_name = "ID8",
            help = "8-character ASCII alphanumeric reviewer identifier (default: random; pass --reviewer-id to reuse identity across reviews)."
        )]
        reviewer_id: Option<String>,
        #[arg(
            long,
            value_name = "ID8",
            help = "8-character ASCII alphanumeric session identifier (default: join active session for target_ref, else random)."
        )]
        session_id: Option<String>,
        #[arg(
            long,
            value_name = "ID8",
            help = "Optional parent reviewer id for handoff/chaining (id8). When set, mpcr binds to the parent's existing review entry for this target_ref (pass --session-id if the parent has multiple sessions); prefer `spawn-children` for deterministic lineage."
        )]
        parent_id: Option<String>,

        #[arg(
            long,
            value_enum,
            value_name = "FORMAT",
            help = "Emit `export KEY='value'` lines for POSIX shells."
        )]
        emit_env: Option<EmitEnvFormat>,

        #[arg(
            long,
            conflicts_with = "emit_env",
            help = "Print MPCR_* key/value lines for manual reuse (does not emit `export`)."
        )]
        print_env: bool,
    },

    /// Spawn child reviewer entries under a single parent reviewer id.
    #[command(after_long_help = r#"Examples:
  # After registering as the parent and capturing session context:
  mpcr reviewer spawn-children --target-ref main --session-dir <DIR> --session-id <ID8> --parent-id <PARENT_ID8> --count 3 --json
"#)]
    SpawnChildren {
        #[command(flatten)]
        session: SessionDirArgs,

        #[arg(
            long,
            value_name = "REF",
            help = "Target reference being reviewed (must match the parent review entry)."
        )]
        target_ref: Option<String>,

        #[arg(
            long,
            value_name = "ID8",
            help = "Session id (id8). Capture from the parent's `mpcr reviewer register --print-env`."
        )]
        session_id: Option<String>,

        #[arg(
            long,
            value_name = "ID8",
            help = "Parent reviewer id (id8). Capture from the parent's `mpcr reviewer register --print-env`."
        )]
        parent_id: Option<String>,

        #[arg(long, value_name = "N", help = "Number of child reviewers to spawn.")]
        count: usize,
    },

    /// Bulk-close child reviewer entries under a parent.
    #[command(after_long_help = r#"Examples:
  # Cancel all parent-owned children still in INITIALIZING/IN_PROGRESS/BLOCKED:
  mpcr reviewer close-children --session-dir <DIR> --parent-id <PARENT_ID8> --session-id <ID8>

  # Mark blocked children as ERROR for a specific target:
  mpcr reviewer close-children --session-dir <DIR> --parent-id <PARENT_ID8> --session-id <ID8> --target-ref main --only-status BLOCKED --set-status ERROR
"#)]
    CloseChildren {
        #[command(flatten)]
        session: SessionDirArgs,

        #[arg(
            long,
            value_name = "ID8",
            help = "Parent reviewer id (id8). Capture from parent registration context."
        )]
        parent_id: Option<String>,

        #[arg(
            long,
            value_name = "ID8",
            help = "Session id (id8) shared by the parent and children."
        )]
        session_id: Option<String>,

        #[arg(
            long,
            value_name = "REF",
            help = "If set, only close children for this target_ref."
        )]
        target_ref: Option<String>,

        #[arg(
            long,
            value_enum,
            value_delimiter = ',',
            num_args = 1..,
            value_name = "STATUS",
            help = "Child reviewer statuses eligible for closing (default: INITIALIZING,IN_PROGRESS,BLOCKED)."
        )]
        only_status: Vec<ReviewerStatus>,

        #[arg(
            long,
            value_enum,
            default_value = "CANCELLED",
            value_name = "STATUS",
            help = "Reviewer status to apply to matching child entries."
        )]
        set_status: ReviewerStatus,

        #[arg(
            long,
            default_value_t = false,
            help = "Clear child current_phase while closing entries."
        )]
        clear_phase: bool,
    },

    /// Update your reviewer-owned status and/or current phase.
    #[command(after_long_help = r#"Reviewer statuses:
  INITIALIZING  Registered; review not yet started
  IN_PROGRESS   Actively reviewing
  FINISHED      Completed (typically set by `reviewer finalize`)
  CANCELLED     Stopped early
  ERROR         Fatal error; see notes for details
  BLOCKED       Waiting on an external dependency or intervention

Review phases:
  INGESTION, DOMAIN_COVERAGE, THEOREM_GENERATION, ADVERSARIAL_PROOFS, SYNTHESIS, REPORT_WRITING

Examples:
  # Recommended (explicit flags):
  mpcr reviewer update --session-dir <DIR> --reviewer-id <ID8> --session-id <ID8> --status IN_PROGRESS --phase INGESTION
  mpcr reviewer update --session-dir <DIR> --reviewer-id <ID8> --session-id <ID8> --clear-phase
"#)]
    Update {
        #[command(flatten)]
        session: SessionDirArgs,
        #[arg(
            long,
            value_name = "ID8",
            help = "Your reviewer_id (id8). Capture from `mpcr reviewer register --print-env`."
        )]
        reviewer_id: Option<String>,
        #[arg(
            long,
            value_name = "ID8",
            help = "Session id (id8). Capture from `mpcr reviewer register --print-env`."
        )]
        session_id: Option<String>,
        #[arg(
            long,
            value_enum,
            ignore_case = true,
            value_name = "STATUS",
            help = "Set reviewer-owned status (see `--help` for allowed values)."
        )]
        status: Option<ReviewerStatus>,
        #[arg(
            long,
            value_enum,
            ignore_case = true,
            value_name = "PHASE",
            help = "Set current review phase (see `--help` for allowed values)."
        )]
        phase: Option<ReviewPhase>,
        #[arg(
            long,
            help = "Clear current review phase (sets `current_phase` to null)."
        )]
        clear_phase: bool,
    },

    /// Finalize a review: write the report markdown and mark the review entry FINISHED.
    #[command(after_long_help = r#"Verdicts:
  APPROVE, REQUEST_CHANGES, BLOCK

Report input:
  - Use `--report-file <path>` to move the file into mpcr's canonical report path (single artifact)
  - Add `--copy-report-input` to preserve the original input file and keep copy behavior
  - Or omit it and pipe markdown via stdin

Child lifecycle:
  - By default, unresolved child reviews under this reviewer are auto-closed before finalize.
  - Use `--no-auto-close-children` to fail instead when open children exist.
  - Use `--auto-close-children-status CANCELLED|ERROR` to control auto-close status.

Examples:
  mpcr reviewer finalize --session-dir <DIR> --reviewer-id <ID8> --session-id <ID8> --verdict APPROVE --blocker 0 --major 0 --minor 0 --nit 0 <<'EOF'
  ## Adversarial Code Review: <ref>
  ...
  EOF

  mpcr reviewer finalize --session-dir <DIR> --reviewer-id <ID8> --session-id <ID8> --verdict APPROVE --report-file review.md
  mpcr reviewer finalize --session-dir <DIR> --reviewer-id <ID8> --session-id <ID8> --verdict APPROVE --report-file review.md --copy-report-input
  cat review.md | mpcr reviewer finalize --session-dir <DIR> --reviewer-id <ID8> --session-id <ID8> --verdict REQUEST_CHANGES --major 2
"#)]
    Finalize {
        #[command(flatten)]
        session: SessionDirArgs,
        #[arg(
            long,
            value_name = "ID8",
            help = "Your reviewer_id (id8). Capture from `mpcr reviewer register --print-env`."
        )]
        reviewer_id: Option<String>,
        #[arg(
            long,
            value_name = "ID8",
            help = "Session id (id8). Capture from `mpcr reviewer register --print-env`."
        )]
        session_id: Option<String>,
        #[arg(
            long,
            value_enum,
            ignore_case = true,
            value_name = "VERDICT",
            help = "Final verdict to record in the session entry."
        )]
        verdict: ReviewVerdict,
        #[arg(
            long,
            default_value_t = 0,
            help = "Number of BLOCKER findings in the report."
        )]
        blocker: u64,
        #[arg(
            long,
            default_value_t = 0,
            help = "Number of MAJOR findings in the report."
        )]
        major: u64,
        #[arg(
            long,
            default_value_t = 0,
            help = "Number of MINOR findings in the report."
        )]
        minor: u64,
        #[arg(
            long,
            default_value_t = 0,
            help = "Number of NIT findings in the report."
        )]
        nit: u64,
        #[arg(
            long,
            value_name = "PATH",
            help = "Use this report markdown file as finalize input (moved to canonical path unless --copy-report-input is set)."
        )]
        report_file: Option<PathBuf>,
        #[arg(
            long,
            default_value_t = false,
            help = "Copy --report-file input instead of moving it (preserves the source file)."
        )]
        copy_report_input: bool,
        #[arg(
            long,
            default_value_t = false,
            help = "Do not auto-close unresolved child reviews before finalize."
        )]
        no_auto_close_children: bool,
        #[arg(
            long,
            value_enum,
            default_value = "CANCELLED",
            value_name = "STATUS",
            help = "Status used when auto-closing unresolved child reviews (CANCELLED or ERROR)."
        )]
        auto_close_children_status: ReviewerStatus,
    },

    /// Complete a child review entry with required artifact fields.
    #[command(after_long_help = r#"Examples:
  # Finalize a child from a report file and attach worker proof summary:
  mpcr reviewer complete-child --session-dir <DIR> --reviewer-id <CHILD_ID8> --session-id <ID8> \
    --verdict APPROVE --report-file child.md --proof-note "Proof Packet: ..."

  # Pipe child report via stdin:
  cat child.md | mpcr reviewer complete-child --session-dir <DIR> --reviewer-id <CHILD_ID8> --session-id <ID8> --verdict REQUEST_CHANGES --major 1
"#)]
    CompleteChild {
        #[command(flatten)]
        session: SessionDirArgs,
        #[arg(long, value_name = "ID8", help = "Child reviewer id (id8).")]
        reviewer_id: Option<String>,
        #[arg(long, value_name = "ID8", help = "Session id (id8).")]
        session_id: Option<String>,
        #[arg(
            long,
            value_enum,
            ignore_case = true,
            value_name = "VERDICT",
            help = "Final verdict for the child review."
        )]
        verdict: ReviewVerdict,
        #[arg(
            long,
            default_value_t = 0,
            help = "Number of BLOCKER findings in the child report."
        )]
        blocker: u64,
        #[arg(
            long,
            default_value_t = 0,
            help = "Number of MAJOR findings in the child report."
        )]
        major: u64,
        #[arg(
            long,
            default_value_t = 0,
            help = "Number of MINOR findings in the child report."
        )]
        minor: u64,
        #[arg(
            long,
            default_value_t = 0,
            help = "Number of NIT findings in the child report."
        )]
        nit: u64,
        #[arg(
            long,
            value_name = "PATH",
            help = "Use this child report markdown file as finalize input (moved unless --copy-report-input)."
        )]
        report_file: Option<PathBuf>,
        #[arg(
            long,
            default_value_t = false,
            help = "Copy --report-file input instead of moving it (preserves the source file)."
        )]
        copy_report_input: bool,
        #[arg(
            long,
            value_name = "TEXT",
            conflicts_with = "proof_note_file",
            help = "Optional proof packet summary to append to child notes."
        )]
        proof_note: Option<String>,
        #[arg(
            long,
            value_name = "PATH",
            conflicts_with = "proof_note",
            help = "Optional file containing proof packet summary to append to child notes."
        )]
        proof_note_file: Option<PathBuf>,
    },

    /// Append a reviewer note to the session entry.
    #[command(after_long_help = r#"Note content:
  - By default, `--content` is stored as a JSON string.
  - With `--content-json`, `--content` must be valid JSON (object/array/string/number/etc).

Examples:
  mpcr reviewer note --session-dir <DIR> --reviewer-id <ID8> --session-id <ID8> --note-type question --content "Can you clarify X?"
  mpcr reviewer note --session-dir <DIR> --reviewer-id <ID8> --session-id <ID8> --note-type domain_observation --content-json --content '{"domain":"security","note":"..."}'
"#)]
    Note {
        #[command(flatten)]
        session: SessionDirArgs,
        #[arg(
            long,
            value_name = "ID8",
            help = "Your reviewer_id (id8). Capture from `mpcr reviewer register --print-env`."
        )]
        reviewer_id: Option<String>,
        #[arg(
            long,
            value_name = "ID8",
            help = "Session id (id8). Capture from `mpcr reviewer register --print-env`."
        )]
        session_id: Option<String>,
        #[arg(
            long,
            visible_alias = "type",
            value_enum,
            ignore_case = true,
            value_name = "NOTE_TYPE",
            help = "Structured note type (see `--help` for allowed values)."
        )]
        note_type: NoteType,
        #[arg(
            long,
            value_name = "TEXT",
            help = "Note content (string by default, or JSON when --content-json is set)."
        )]
        content: String,
        #[arg(long, help = "Interpret --content as JSON instead of a plain string.")]
        content_json: bool,
    },
}

#[derive(Subcommand)]
enum ApplicatorCommands {
    /// Set `initiator_status` on an existing review entry (applicator-owned field).
    #[command(after_long_help = r#"Initiator statuses:
  REQUESTING, OBSERVING, RECEIVED, REVIEWED, APPLYING, APPLIED, CANCELLED

Example:
  # Recommended (explicit flags):
  mpcr applicator set-status --session-dir <DIR> --reviewer-id <ID8> --session-id <ID8> --initiator-status RECEIVED
"#)]
    SetStatus {
        #[command(flatten)]
        session: SessionDirArgs,
        #[arg(
            long,
            value_name = "ID8",
            help = "Reviewer id for the entry you are updating (id8)."
        )]
        reviewer_id: Option<String>,
        #[arg(
            long,
            value_name = "ID8",
            help = "Session id for the entry you are updating (id8)."
        )]
        session_id: Option<String>,
        #[arg(
            long,
            value_enum,
            ignore_case = true,
            value_name = "INITIATOR_STATUS",
            help = "New initiator_status value (see `--help` for allowed values)."
        )]
        initiator_status: InitiatorStatus,
        #[arg(
            long,
            value_name = "ID8",
            help = "Lock owner id8 used while updating `_session.json` (default: random)."
        )]
        lock_owner: Option<String>,
    },

    /// Append an applicator note to a review entry.
    #[command(after_long_help = r#"Note content:
  - By default, `--content` is stored as a JSON string.
  - With `--content-json`, `--content` must be valid JSON.

Example:
  # Recommended (explicit flags):
  mpcr applicator note --session-dir <DIR> --reviewer-id <ID8> --session-id <ID8> --note-type applied --content "Fixed in commit abc123"
"#)]
    Note {
        #[command(flatten)]
        session: SessionDirArgs,
        #[arg(
            long,
            value_name = "ID8",
            help = "Reviewer id for the entry you are updating (id8)."
        )]
        reviewer_id: Option<String>,
        #[arg(
            long,
            value_name = "ID8",
            help = "Session id for the entry you are updating (id8)."
        )]
        session_id: Option<String>,
        #[arg(
            long,
            visible_alias = "type",
            value_enum,
            ignore_case = true,
            value_name = "NOTE_TYPE",
            help = "Structured note type (see `--help` for allowed values)."
        )]
        note_type: NoteType,
        #[arg(
            long,
            value_name = "TEXT",
            help = "Note content (string by default, or JSON when --content-json is set)."
        )]
        content: String,
        #[arg(long, help = "Interpret --content as JSON instead of a plain string.")]
        content_json: bool,
        #[arg(
            long,
            value_name = "ID8",
            help = "Lock owner id8 used while updating `_session.json` (default: random)."
        )]
        lock_owner: Option<String>,
    },

    /// Block until matching reviews reach a terminal status.
    #[command(after_long_help = r#"Terminal reviewer statuses:
  FINISHED, CANCELLED, ERROR

Examples:
  # From repo root (or with --repo-root/--date), wait for *all* reviews:
  mpcr applicator wait

  # Explicit flags (recommended):
  mpcr applicator wait --session-dir <DIR> --target-ref main --session-id <ID8>
"#)]
    Wait {
        #[command(flatten)]
        session: SessionDirArgs,
        #[arg(
            long,
            value_name = "REF",
            help = "If set, only wait for reviews matching this target_ref."
        )]
        target_ref: Option<String>,
        #[arg(
            long,
            value_name = "ID8",
            help = "If set, only wait for reviews matching this session_id."
        )]
        session_id: Option<String>,
    },
}

#[derive(Subcommand)]
enum ProtocolCommands {
    /// Phase-appropriate guidance for code review.
    Reviewer {
        #[arg(
            long,
            value_name = "PHASE",
            help = "Review phase (INGESTION, DOMAIN_COVERAGE, THEOREM_GENERATION, ADVERSARIAL_PROOFS, SYNTHESIS, REPORT_WRITING)."
        )]
        phase: String,
    },
    /// Phase-appropriate guidance for applying review feedback.
    Applicator {
        #[arg(
            long,
            value_name = "PHASE",
            help = "Applicator phase (INGESTION, DISPOSITION, APPLICATION, FINALIZATION)."
        )]
        phase: String,
    },
    /// Multi-agent orchestration guidance.
    Orchestrator,
    /// Universal Domains reference table.
    Domains,
    /// Report template skeleton at the specified scale.
    ReportTemplate {
        #[arg(
            long,
            value_name = "SCALE",
            help = "Template scale (compact, standard, full)."
        )]
        scale: String,
    },
    /// Subagent dispatch prompt template for a given role.
    Dispatch {
        #[arg(
            long,
            value_name = "ROLE",
            help = "Subagent role (scope-mapper, red-team, systems-auditor)."
        )]
        role: String,
    },
    /// List all available protocol entries.
    List,
}

#[derive(Debug, Serialize)]
struct OkResult {
    ok: bool,
}

fn main() {
    if let Err(err) = run() {
        eprintln!("{err:?}");
        std::process::exit(1);
    }
}

#[allow(clippy::too_many_lines)]
fn run() -> anyhow::Result<()> {
    let cli = Cli::parse();
    enforce_worker_mode_restrictions(&cli.command)?;
    let json = cli.json || cli.json_pretty;
    let json_pretty = cli.json_pretty;
    let use_env = cli.use_env;
    let now = OffsetDateTime::now_utc();

    match cli.command {
        Commands::Id { command } => match command {
            IdCommands::Id8 => {
                let out = id::random_id8()?;
                if json {
                    write_json(json_pretty, &out)?;
                } else {
                    println!("{out}");
                }
            }
            IdCommands::Hex { bytes } => {
                let out = id::random_hex_id(bytes)?;
                if json {
                    write_json(json_pretty, &out)?;
                } else {
                    println!("{out}");
                }
            }
        },

        Commands::Lock { command } => match command {
            LockCommands::Acquire {
                session,
                owner,
                max_retries,
            } => {
                let resolved = resolve_session_input(use_env, &session, now.date())?;
                let cfg = LockConfig { max_retries };
                let guard = lock::acquire_lock(&resolved.session_dir, owner, cfg)?;
                std::mem::forget(guard);
                write_ok(json, json_pretty)?;
            }
            LockCommands::Release { session, owner } => {
                let resolved = resolve_session_input(use_env, &session, now.date())?;
                lock::release_lock(&resolved.session_dir, owner)?;
                write_ok(json, json_pretty)?;
            }
        },

        Commands::Session { command } => match command {
            SessionCommands::Show { session } => {
                let resolved = resolve_session_input(use_env, &session, now.date())?;
                let session = load_session(&SessionLocator::new(resolved.session_dir))?;
                write_result(json, json_pretty, &session)?;
            }
            SessionCommands::Reports { command } => match command {
                ReportsCommands::Open(args) => {
                    handle_reports(
                        use_env,
                        json,
                        json_pretty,
                        now.date(),
                        ReportsView::Open,
                        args,
                    )?;
                }
                ReportsCommands::Closed(args) => {
                    handle_reports(
                        use_env,
                        json,
                        json_pretty,
                        now.date(),
                        ReportsView::Closed,
                        args,
                    )?;
                }
                ReportsCommands::InProgress(args) => {
                    handle_reports(
                        use_env,
                        json,
                        json_pretty,
                        now.date(),
                        ReportsView::InProgress,
                        args,
                    )?;
                }
            },
        },

        Commands::Reviewer { command } => match command {
            ReviewerCommands::Register {
                target_ref,
                session,
                reviewer_id,
                session_id,
                parent_id,
                emit_env,
                print_env,
            } => {
                let target_ref_for_env = target_ref.clone();
                let resolved = resolve_session_input(use_env, &session, now.date())?;
                let repo_root_for_env = resolved.repo_root.to_string_lossy().to_string();
                let date_for_env = resolved.session_date.to_string();
                let session = SessionLocator::new(resolved.session_dir);

                // When --parent-id is set (child registration), ignore MPCR_REVIEWER_ID from env
                // to prevent accidentally reusing the parent's identity. A child should either
                // provide an explicit --reviewer-id or let mpcr generate a new one.
                let reviewer_id = if parent_id.is_some() {
                    reviewer_id // Ignore env fallback for children
                } else {
                    reviewer_id.or_else(|| opt_env_string(use_env, "MPCR_REVIEWER_ID"))
                };

                let res = register_reviewer(RegisterReviewerParams {
                    repo_root: resolved.repo_root,
                    session_date: resolved.session_date,
                    session,
                    target_ref,
                    reviewer_id,
                    session_id,
                    parent_id,
                    now,
                })?;

                let mut env_pairs = vec![
                    ("MPCR_REPO_ROOT", repo_root_for_env.as_str()),
                    ("MPCR_DATE", date_for_env.as_str()),
                    ("MPCR_REVIEWER_ID", res.reviewer_id.as_str()),
                    ("MPCR_SESSION_ID", res.session_id.as_str()),
                    ("MPCR_SESSION_DIR", res.session_dir.as_str()),
                    ("MPCR_SESSION_FILE", res.session_file.as_str()),
                    ("MPCR_TARGET_REF", target_ref_for_env.as_str()),
                ];
                if let Some(parent_id) = res.parent_id.as_deref() {
                    env_pairs.insert(3, ("MPCR_PARENT_ID", parent_id));
                }

                match emit_env {
                    Some(EmitEnvFormat::Sh) => write_env_sh(&env_pairs)?,
                    None => {
                        if print_env {
                            write_env_kv(json, json_pretty, &env_pairs)?;
                        } else {
                            write_result(json, json_pretty, &res)?;
                        }
                    }
                }
            }

            ReviewerCommands::SpawnChildren {
                session,
                target_ref,
                session_id,
                parent_id,
                count,
            } => {
                let target_ref =
                    require_arg_or_env(target_ref, use_env, "MPCR_TARGET_REF", "--target-ref")?;
                let session_id =
                    require_arg_or_env(session_id, use_env, "MPCR_SESSION_ID", "--session-id")?;
                let parent_reviewer_id =
                    require_arg_or_env(parent_id, use_env, "MPCR_REVIEWER_ID", "--parent-id")?;
                let resolved = resolve_session_input(use_env, &session, now.date())?;

                let res = spawn_child_reviewers(SpawnChildReviewersParams {
                    session: SessionLocator::new(resolved.session_dir),
                    target_ref,
                    session_id,
                    parent_reviewer_id,
                    count,
                    now,
                })?;
                write_result(json, json_pretty, &res)?;
            }

            ReviewerCommands::CloseChildren {
                session,
                parent_id,
                session_id,
                target_ref,
                only_status,
                set_status,
                clear_phase,
            } => {
                let parent_reviewer_id =
                    require_arg_or_env(parent_id, use_env, "MPCR_REVIEWER_ID", "--parent-id")?;
                let session_id =
                    require_arg_or_env(session_id, use_env, "MPCR_SESSION_ID", "--session-id")?;
                let resolved = resolve_session_input(use_env, &session, now.date())?;

                let only_statuses = if only_status.is_empty() {
                    vec![
                        ReviewerStatus::Initializing,
                        ReviewerStatus::InProgress,
                        ReviewerStatus::Blocked,
                    ]
                } else {
                    only_status
                };

                let result = close_child_reviews(CloseChildReviewsParams {
                    session: SessionLocator::new(resolved.session_dir),
                    parent_reviewer_id,
                    session_id,
                    target_ref,
                    only_statuses,
                    set_status,
                    clear_phase,
                    now,
                })?;
                write_result(json, json_pretty, &result)?;
            }

            ReviewerCommands::Update {
                session,
                reviewer_id,
                session_id,
                status,
                phase,
                clear_phase,
            } => {
                let reviewer_id =
                    require_arg_or_env(reviewer_id, use_env, "MPCR_REVIEWER_ID", "--reviewer-id")?;
                let session_id =
                    require_arg_or_env(session_id, use_env, "MPCR_SESSION_ID", "--session-id")?;
                let resolved = resolve_session_input(use_env, &session, now.date())?;
                let phase = if clear_phase {
                    Some(None)
                } else {
                    phase.map(Some)
                };
                let params = UpdateReviewParams {
                    session: SessionLocator::new(resolved.session_dir),
                    reviewer_id,
                    session_id,
                    status,
                    phase,
                    now,
                };
                update_review(&params)?;
                write_ok(json, json_pretty)?;
            }

            ReviewerCommands::Finalize {
                session,
                reviewer_id,
                session_id,
                verdict,
                blocker,
                major,
                minor,
                nit,
                report_file,
                copy_report_input,
                no_auto_close_children,
                auto_close_children_status,
            } => {
                let report_input = match report_file {
                    Some(p) => FinalizeReportInput::File(p),
                    None => FinalizeReportInput::Markdown(
                        read_stdin_to_string().context("read report markdown from stdin")?,
                    ),
                };

                let reviewer_id =
                    require_arg_or_env(reviewer_id, use_env, "MPCR_REVIEWER_ID", "--reviewer-id")?;
                let session_id =
                    require_arg_or_env(session_id, use_env, "MPCR_SESSION_ID", "--session-id")?;
                let resolved = resolve_session_input(use_env, &session, now.date())?;
                let res = finalize_review(FinalizeReviewParams {
                    session: SessionLocator::new(resolved.session_dir),
                    reviewer_id,
                    session_id,
                    verdict,
                    counts: SeverityCounts {
                        blocker,
                        major,
                        minor,
                        nit,
                    },
                    report_input,
                    copy_input_report: copy_report_input,
                    auto_close_open_children: !no_auto_close_children,
                    auto_close_children_status,
                    now,
                })?;
                write_result(json, json_pretty, &res)?;
            }

            ReviewerCommands::CompleteChild {
                session,
                reviewer_id,
                session_id,
                verdict,
                blocker,
                major,
                minor,
                nit,
                report_file,
                copy_report_input,
                proof_note,
                proof_note_file,
            } => {
                let report_input = match report_file {
                    Some(p) => FinalizeReportInput::File(p),
                    None => FinalizeReportInput::Markdown(
                        read_stdin_to_string().context("read child report markdown from stdin")?,
                    ),
                };

                let reviewer_id =
                    require_arg_or_env(reviewer_id, use_env, "MPCR_REVIEWER_ID", "--reviewer-id")?;
                let session_id =
                    require_arg_or_env(session_id, use_env, "MPCR_SESSION_ID", "--session-id")?;
                let resolved = resolve_session_input(use_env, &session, now.date())?;
                let session_locator = SessionLocator::new(resolved.session_dir);

                ensure_complete_child_has_parent(&session_locator, &reviewer_id, &session_id)?;

                let res = finalize_review(FinalizeReviewParams {
                    session: session_locator.clone(),
                    reviewer_id: reviewer_id.clone(),
                    session_id: session_id.clone(),
                    verdict,
                    counts: SeverityCounts {
                        blocker,
                        major,
                        minor,
                        nit,
                    },
                    report_input,
                    copy_input_report: copy_report_input,
                    auto_close_open_children: false,
                    auto_close_children_status: ReviewerStatus::Cancelled,
                    now,
                })?;

                let proof_note = match (proof_note, proof_note_file) {
                    (Some(note), None) => Some(note),
                    (None, Some(path)) => Some(
                        std::fs::read_to_string(&path)
                            .with_context(|| format!("read proof note file {}", path.display()))?,
                    ),
                    (None, None) => None,
                    (Some(_), Some(_)) => {
                        return Err(anyhow::anyhow!(
                            "pass only one of --proof-note or --proof-note-file"
                        ));
                    }
                };

                if let Some(note) = proof_note {
                    append_note(AppendNoteParams {
                        session: session_locator,
                        reviewer_id,
                        session_id,
                        role: NoteRole::Reviewer,
                        note_type: NoteType::ProofPacket,
                        content: Value::String(note),
                        now,
                        lock_owner: id::random_id8()?,
                    })?;
                }

                write_result(json, json_pretty, &res)?;
            }

            ReviewerCommands::Note {
                session,
                reviewer_id,
                session_id,
                note_type,
                content,
                content_json,
            } => {
                let reviewer_id =
                    require_arg_or_env(reviewer_id, use_env, "MPCR_REVIEWER_ID", "--reviewer-id")?;
                let session_id =
                    require_arg_or_env(session_id, use_env, "MPCR_SESSION_ID", "--session-id")?;
                let resolved = resolve_session_input(use_env, &session, now.date())?;
                let content = parse_content(content_json, &content)?;
                append_note(AppendNoteParams {
                    session: SessionLocator::new(resolved.session_dir),
                    reviewer_id: reviewer_id.clone(),
                    session_id,
                    role: NoteRole::Reviewer,
                    note_type,
                    content,
                    now,
                    lock_owner: reviewer_id,
                })?;
                write_ok(json, json_pretty)?;
            }
        },

        Commands::Applicator { command } => match command {
            ApplicatorCommands::SetStatus {
                session,
                reviewer_id,
                session_id,
                initiator_status,
                lock_owner,
            } => {
                let reviewer_id =
                    require_arg_or_env(reviewer_id, use_env, "MPCR_REVIEWER_ID", "--reviewer-id")?;
                let session_id =
                    require_arg_or_env(session_id, use_env, "MPCR_SESSION_ID", "--session-id")?;
                let resolved = resolve_session_input(use_env, &session, now.date())?;
                let lock_owner = match lock_owner {
                    Some(lock_owner) => lock_owner,
                    None => id::random_id8()?,
                };
                let params = SetInitiatorStatusParams {
                    session: SessionLocator::new(resolved.session_dir),
                    reviewer_id,
                    session_id,
                    initiator_status,
                    now,
                    lock_owner,
                };
                set_initiator_status(&params)?;
                write_ok(json, json_pretty)?;
            }

            ApplicatorCommands::Note {
                session,
                reviewer_id,
                session_id,
                note_type,
                content,
                content_json,
                lock_owner,
            } => {
                let reviewer_id =
                    require_arg_or_env(reviewer_id, use_env, "MPCR_REVIEWER_ID", "--reviewer-id")?;
                let session_id =
                    require_arg_or_env(session_id, use_env, "MPCR_SESSION_ID", "--session-id")?;
                let resolved = resolve_session_input(use_env, &session, now.date())?;
                let content = parse_content(content_json, &content)?;
                let lock_owner = match lock_owner {
                    Some(lock_owner) => lock_owner,
                    None => id::random_id8()?,
                };
                append_note(AppendNoteParams {
                    session: SessionLocator::new(resolved.session_dir),
                    reviewer_id,
                    session_id,
                    role: NoteRole::Applicator,
                    note_type,
                    content,
                    now,
                    lock_owner,
                })?;
                write_ok(json, json_pretty)?;
            }

            ApplicatorCommands::Wait {
                session,
                target_ref,
                session_id,
            } => {
                let target_ref = target_ref.or_else(|| opt_env_string(use_env, "MPCR_TARGET_REF"));
                let session_id = session_id.or_else(|| opt_env_string(use_env, "MPCR_SESSION_ID"));
                let resolved = resolve_session_input(use_env, &session, now.date())?;
                wait_for_reviews(
                    &resolved.session_dir,
                    target_ref.as_deref(),
                    session_id.as_deref(),
                )?;
                write_ok(json, json_pretty)?;
            }
        },

        Commands::Protocol { command } => match command {
            ProtocolCommands::Reviewer { phase } => {
                let out = protocol::reviewer_phase(&phase)?;
                if json {
                    write_json(json_pretty, &out)?;
                } else {
                    println!("{}", out.content.trim());
                }
            }
            ProtocolCommands::Applicator { phase } => {
                let out = protocol::applicator_phase(&phase)?;
                if json {
                    write_json(json_pretty, &out)?;
                } else {
                    println!("{}", out.content.trim());
                }
            }
            ProtocolCommands::Orchestrator => {
                let out = protocol::orchestrator()?;
                if json {
                    write_json(json_pretty, &out)?;
                } else {
                    println!("{}", out.content.trim());
                }
            }
            ProtocolCommands::Domains => {
                let out = protocol::domains()?;
                if json {
                    write_json(json_pretty, &out)?;
                } else {
                    println!("{}", out.content.trim());
                }
            }
            ProtocolCommands::ReportTemplate { scale } => {
                let out = protocol::report_template(&scale)?;
                if json {
                    write_json(json_pretty, &out)?;
                } else {
                    println!("{}", out.content.trim());
                }
            }
            ProtocolCommands::Dispatch { role } => {
                let out = protocol::dispatch(&role)?;
                if json {
                    write_json(json_pretty, &out)?;
                } else {
                    println!("{}", out.content.trim());
                }
            }
            ProtocolCommands::List => {
                let entries = protocol::list_entries()?;
                if json {
                    write_json(json_pretty, &entries)?;
                } else {
                    for entry in &entries {
                        println!("{:<16} {:<24} {}", entry.category, entry.key, entry.command);
                    }
                }
            }
        },
    }

    Ok(())
}

fn enforce_worker_mode_restrictions(command: &Commands) -> anyhow::Result<()> {
    let dispatch_role = std::env::var("MPCR_DISPATCH_ROLE")
        .ok()
        .filter(|value| !value.trim().is_empty());
    let Some(dispatch_role) = dispatch_role else {
        return Ok(());
    };

    let allowed = matches!(
        command,
        Commands::Reviewer {
            command: ReviewerCommands::Update { .. } | ReviewerCommands::Note { .. }
        }
    );
    if allowed {
        return Ok(());
    }

    Err(anyhow::anyhow!(
        "MPCR_DISPATCH_ROLE={dispatch_role} restricts this executor to `mpcr reviewer update` and `mpcr reviewer note` only"
    ))
}

fn resolve_session_input(
    use_env: bool,
    args: &SessionDirArgs,
    default_date: Date,
) -> anyhow::Result<ResolvedSessionInput> {
    let cwd = std::env::current_dir().context("get cwd")?;
    resolve_session_input_from_cwd(use_env, args, default_date, &cwd)
}

fn discover_repo_root(start: &Path) -> Option<PathBuf> {
    let mut dir = Some(start);
    while let Some(current) = dir {
        if current.join(".git").exists() {
            return Some(current.to_path_buf());
        }
        dir = current.parent();
    }
    None
}

fn resolve_session_input_from_cwd(
    use_env: bool,
    args: &SessionDirArgs,
    default_date: Date,
    cwd: &Path,
) -> anyhow::Result<ResolvedSessionInput> {
    let repo_root = args
        .repo_root
        .clone()
        .or_else(|| opt_env_pathbuf(use_env, "MPCR_REPO_ROOT"))
        .or_else(|| discover_repo_root(cwd))
        .map_or_else(|| cwd.to_path_buf(), std::convert::identity);
    let date_raw = args
        .date
        .as_deref()
        .map(std::string::ToString::to_string)
        .or_else(|| opt_env_string(use_env, "MPCR_DATE"));
    let session_date = match date_raw.as_deref() {
        Some(date) => parse_date_ymd(date)?,
        None => default_date,
    };
    let session_dir = args
        .session_dir
        .clone()
        .or_else(|| opt_env_pathbuf(use_env, "MPCR_SESSION_DIR"))
        .map_or_else(
            || mpcr::paths::session_paths(&repo_root, session_date).session_dir,
            std::convert::identity,
        );

    Ok(ResolvedSessionInput {
        session_dir,
        repo_root,
        session_date,
    })
}

fn parse_date_ymd(s: &str) -> anyhow::Result<Date> {
    let mut parts = s.split('-');
    let year: i32 = parts
        .next()
        .ok_or_else(|| anyhow::anyhow!("invalid date: missing year"))?
        .parse()
        .context("parse year")?;
    let month_u8: u8 = parts
        .next()
        .ok_or_else(|| anyhow::anyhow!("invalid date: missing month"))?
        .parse()
        .context("parse month")?;
    let day: u8 = parts
        .next()
        .ok_or_else(|| anyhow::anyhow!("invalid date: missing day"))?
        .parse()
        .context("parse day")?;
    if parts.next().is_some() {
        return Err(anyhow::anyhow!("invalid date: too many components"));
    }
    let month = Month::try_from(month_u8).context("invalid month")?;
    Date::from_calendar_date(year, month, day).context("invalid calendar date")
}

fn parse_content(as_json: bool, raw: &str) -> anyhow::Result<Value> {
    if as_json {
        serde_json::from_str(raw).context("parse --content as JSON")
    } else {
        Ok(Value::String(raw.to_string()))
    }
}

fn read_stdin_to_string() -> anyhow::Result<String> {
    let mut buf = String::new();
    std::io::stdin()
        .read_to_string(&mut buf)
        .context("read stdin")?;
    Ok(buf)
}

fn write_ok(json: bool, pretty: bool) -> anyhow::Result<()> {
    if json {
        write_result(true, pretty, &OkResult { ok: true })
    } else {
        println!("ok");
        Ok(())
    }
}

fn write_json<T: Serialize>(pretty: bool, value: &T) -> anyhow::Result<()> {
    let mut stdout = std::io::stdout();
    let raw = if pretty {
        serde_json::to_string_pretty(value)
    } else {
        serde_json::to_string(value)
    }
    .context("serialize JSON")?;
    stdout.write_all(raw.as_bytes()).context("write stdout")?;
    stdout.write_all(b"\n").context("write stdout newline")?;
    Ok(())
}

fn write_env_sh(pairs: &[(&str, &str)]) -> anyhow::Result<()> {
    let mut stdout = std::io::stdout();
    for (key, value) in pairs {
        let quoted = sh_single_quote(value);
        writeln!(stdout, "export {key}={quoted}").context("write stdout")?;
    }
    Ok(())
}

fn write_env_kv(json: bool, pretty: bool, pairs: &[(&str, &str)]) -> anyhow::Result<()> {
    if json {
        let mut map = serde_json::Map::with_capacity(pairs.len());
        for (key, value) in pairs {
            map.insert((*key).to_string(), Value::String((*value).to_string()));
        }
        return write_json(pretty, &Value::Object(map));
    }

    let mut stdout = std::io::stdout();
    for (key, value) in pairs {
        writeln!(stdout, "{key}={value}").context("write stdout")?;
    }
    Ok(())
}

fn sh_single_quote(raw: &str) -> String {
    if raw.is_empty() {
        return "''".to_string();
    }
    let mut out = String::with_capacity(raw.len() + 2);
    out.push('\'');
    for ch in raw.chars() {
        if ch == '\'' {
            out.push_str("'\"'\"'");
        } else {
            out.push(ch);
        }
    }
    out.push('\'');
    out
}

fn write_result<T: Serialize>(json: bool, pretty: bool, value: &T) -> anyhow::Result<()> {
    if json {
        write_json(pretty, value)
    } else {
        // human output: best-effort JSON on one line.
        println!("{}", serde_json::to_string(value).context("serialize")?);
        Ok(())
    }
}

fn handle_reports(
    use_env: bool,
    json: bool,
    json_pretty: bool,
    default_date: Date,
    view: ReportsView,
    args: ReportsArgs,
) -> anyhow::Result<()> {
    let resolved = resolve_session_input(use_env, &args.session, default_date)?;
    let session = SessionLocator::new(resolved.session_dir);

    if session.session_dir().exists() && !session.session_dir().is_dir() {
        return Err(anyhow::anyhow!(
            "session_dir is not a directory: {}",
            session.session_dir().display()
        ));
    }

    let filters = ReportsFilters {
        target_ref: args.target_ref,
        session_id: args.session_id,
        reviewer_id: args.reviewer_id,
        reviewer_statuses: args.reviewer_status,
        initiator_statuses: args.initiator_status,
        verdicts: args.verdict,
        phases: args.phase,
        only_with_report: args.only_with_report,
        only_with_notes: args.only_with_notes,
    };
    let options = ReportsOptions {
        include_notes: args.include_notes || args.only_with_notes,
        include_report_contents: args.include_report_contents,
        include_leaf_children: args.include_leaf_children,
    };

    if !session.session_file().exists() {
        let result = ReportsResult {
            session_dir: session.session_dir().to_string_lossy().to_string(),
            session_file: session.session_file().to_string_lossy().to_string(),
            view,
            filters,
            options,
            total_reviews: 0,
            matching_reviews: 0,
            reviews: Vec::new(),
        };
        return write_result(json, json_pretty, &result);
    }

    let session_data = load_session(&session)?;
    let result = collect_reports(&session_data, &session, view, filters, options);
    write_result(json, json_pretty, &result)
}

fn opt_env_string(use_env: bool, key: &str) -> Option<String> {
    if !use_env {
        return None;
    }
    std::env::var(key).ok()
}

fn opt_env_pathbuf(use_env: bool, key: &str) -> Option<PathBuf> {
    if !use_env {
        return None;
    }
    std::env::var_os(key).map(PathBuf::from)
}

fn require_arg_or_env(
    value: Option<String>,
    use_env: bool,
    env_key: &str,
    arg_flag: &str,
) -> anyhow::Result<String> {
    value
        .or_else(|| opt_env_string(use_env, env_key))
        .ok_or_else(|| {
            if use_env {
                anyhow::anyhow!(
                    "missing {arg_flag}; pass {arg_flag} (or set {env_key} and pass --use-env)"
                )
            } else {
                anyhow::anyhow!("missing {arg_flag}; pass {arg_flag}")
            }
        })
}

fn ensure_complete_child_has_parent(
    session: &SessionLocator,
    reviewer_id: &str,
    session_id: &str,
) -> anyhow::Result<()> {
    let session_data = load_session(session)?;
    let child_entry = session_data
        .reviews
        .iter()
        .find(|entry| entry.reviewer_id == reviewer_id && entry.session_id == session_id)
        .ok_or_else(|| anyhow::anyhow!("review entry not found for reviewer_id/session_id"))?;

    let parent_id = child_entry.parent_id.as_deref().ok_or_else(|| {
        anyhow::anyhow!(
            "complete-child requires a child review entry with parent_id (reviewer_id/session_id points at a parent or standalone review)"
        )
    })?;

    let parent_exists = session_data.reviews.iter().any(|entry| {
        entry.reviewer_id == parent_id
            && entry.session_id == child_entry.session_id
            && entry.target_ref == child_entry.target_ref
    });
    if !parent_exists {
        return Err(anyhow::anyhow!(
            "complete-child parent review entry not found for parent_id/session_id/target_ref"
        ));
    }

    Ok(())
}

fn wait_for_reviews(
    session_dir: &Path,
    target_ref: Option<&str>,
    session_id: Option<&str>,
) -> anyhow::Result<()> {
    let mut delay = std::time::Duration::from_secs(1);
    let max_delay = std::time::Duration::from_secs(60);
    let session = SessionLocator::new(session_dir.to_path_buf());
    let should_wait_for_session = target_ref.is_some() || session_id.is_some();

    if session_dir.exists() && !session_dir.is_dir() {
        return Err(anyhow::anyhow!(
            "session_dir is not a directory: {}",
            session_dir.display()
        ));
    }

    loop {
        if !session.session_file().exists() {
            if !should_wait_for_session {
                return Ok(());
            }
            std::thread::sleep(delay);
            delay = std::cmp::min(delay.saturating_mul(2), max_delay);
            continue;
        }

        let session_data = load_session(&session)
            .with_context(|| format!("read session file under {}", session_dir.display()))?;

        let mut has_pending = false;
        for r in session_data.reviews {
            if let Some(tr) = target_ref {
                if r.target_ref != tr {
                    continue;
                }
            }
            if let Some(sid) = session_id {
                if r.session_id != sid {
                    continue;
                }
            }
            if !r.status.is_terminal() {
                has_pending = true;
                break;
            }
        }

        if !has_pending {
            return Ok(());
        }

        std::thread::sleep(delay);
        delay = std::cmp::min(delay.saturating_mul(2), max_delay);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use anyhow::ensure;
    use mpcr::paths;
    use mpcr::session::{
        InitiatorStatus, ReviewEntry, ReviewVerdict, ReviewerStatus, SessionFile, SeverityCounts,
    };
    use std::fs;
    use time::Month;

    #[test]
    fn parse_date_ymd_valid_and_invalid() -> anyhow::Result<()> {
        let date = parse_date_ymd("2026-01-11")?;
        ensure!(date.to_string() == "2026-01-11");
        ensure!(parse_date_ymd("2026-13-01").is_err());
        ensure!(parse_date_ymd("not-a-date").is_err());
        Ok(())
    }

    #[test]
    fn parse_content_json_and_string() -> anyhow::Result<()> {
        let value = parse_content(true, r#"{"key":1}"#)?;
        let key = value
            .get("key")
            .and_then(serde_json::Value::as_i64)
            .ok_or_else(|| anyhow::anyhow!("key missing"))?;
        ensure!(key == 1);
        let raw = parse_content(false, "hello")?;
        ensure!(raw == serde_json::Value::String("hello".to_string()));
        Ok(())
    }

    #[test]
    fn wait_for_reviews_returns_when_terminal() -> anyhow::Result<()> {
        let dir = tempfile::tempdir()?;
        let session_dir = dir.path().join("session");
        fs::create_dir_all(&session_dir)?;
        let entry = ReviewEntry {
            reviewer_id: "deadbeef".to_string(),
            session_id: "sess0001".to_string(),
            target_ref: "refs/heads/main".to_string(),
            initiator_status: InitiatorStatus::Received,
            status: ReviewerStatus::Finished,
            parent_id: None,
            started_at: "2026-01-11T00:00:00Z".to_string(),
            updated_at: "2026-01-11T01:00:00Z".to_string(),
            finished_at: Some("2026-01-11T02:00:00Z".to_string()),
            current_phase: None,
            verdict: Some(ReviewVerdict::Approve),
            counts: SeverityCounts::zero(),
            report_file: Some("report.md".to_string()),
            notes: Vec::new(),
            child_reviews: Vec::new(),
        };
        let session = SessionFile {
            schema_version: "1.1.0".to_string(),
            session_date: "2026-01-11".to_string(),
            repo_root: dir.path().to_string_lossy().to_string(),
            reviewers: vec!["deadbeef".to_string()],
            reviews: vec![entry],
        };
        let body = serde_json::to_string_pretty(&session)? + "\n";
        fs::write(session_dir.join("_session.json"), body)?;

        wait_for_reviews(&session_dir, None, None)?;
        Ok(())
    }

    #[test]
    fn resolve_session_input_prefers_override_dir() -> anyhow::Result<()> {
        let dir = tempfile::tempdir()?;
        let override_dir = dir.path().join("override");
        let repo_root = dir.path().join("repo");
        let args = SessionDirArgs {
            session_dir: Some(override_dir.clone()),
            repo_root: Some(repo_root.clone()),
            date: Some("2026-01-11".to_string()),
        };
        let fallback = Date::from_calendar_date(2026, Month::January, 12)?;
        let resolved = resolve_session_input(false, &args, fallback)?;
        ensure!(resolved.session_dir == override_dir);
        ensure!(resolved.repo_root == repo_root);
        ensure!(resolved.session_date.to_string() == "2026-01-11");
        Ok(())
    }

    #[test]
    fn resolve_session_input_computes_default_dir() -> anyhow::Result<()> {
        let repo_root = tempfile::tempdir()?;
        let args = SessionDirArgs {
            session_dir: None,
            repo_root: Some(repo_root.path().to_path_buf()),
            date: Some("2026-01-11".to_string()),
        };
        let resolved = resolve_session_input_from_cwd(
            false,
            &args,
            Date::from_calendar_date(2026, Month::January, 12)?,
            repo_root.path(),
        )?;
        let expected = paths::session_paths(
            repo_root.path(),
            Date::from_calendar_date(2026, Month::January, 11)?,
        );
        ensure!(resolved.session_dir == expected.session_dir);
        Ok(())
    }

    #[test]
    fn resolve_session_input_auto_detects_repo_root() -> anyhow::Result<()> {
        let dir = tempfile::tempdir()?;
        let repo_root = dir.path().join("repo");
        let cwd = repo_root.join("a").join("b");
        fs::create_dir_all(&cwd)?;
        fs::create_dir_all(repo_root.join(".git"))?;

        let args = SessionDirArgs {
            session_dir: None,
            repo_root: None,
            date: Some("2026-01-11".to_string()),
        };
        let resolved = resolve_session_input_from_cwd(
            false,
            &args,
            Date::from_calendar_date(2026, Month::January, 12)?,
            &cwd,
        )?;
        ensure!(resolved.repo_root == repo_root);
        ensure!(resolved.session_date.to_string() == "2026-01-11");

        let expected = paths::session_paths(&repo_root, resolved.session_date);
        ensure!(resolved.session_dir == expected.session_dir);
        Ok(())
    }
}
