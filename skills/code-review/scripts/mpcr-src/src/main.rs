#![allow(clippy::print_stderr, clippy::print_stdout)]

//! CLI entrypoint for `mpcr` (UACRP code review coordination utilities).
//!
//! The actual coordination logic lives in the `mpcr` library crate (`src/session.rs`, `src/lock.rs`, etc).

use anyhow::Context;
use clap::{Args, CommandFactory, Parser, Subcommand, ValueEnum};
use mpcr::fullcycle_plan::{self, BuildParams, DetailLevel};
use mpcr::id;
use mpcr::lock::{self, LockConfig};
use mpcr::report_validation::{
    validate_report_markdown, ReportValidationKind, ReportValidationSummary, SeverityExpectation,
};
use mpcr::session::{
    active_session_artifact, append_note, close_child_reviews, collect_reports, finalize_review,
    load_session, purge_reviews, register_reviewer, session_artifact_or_default,
    set_initiator_status, spawn_child_reviewers, update_review, AppendNoteParams,
    CloseChildReviewsParams, FinalizeReportInput, FinalizeReviewParams, InitiatorStatus, NoteRole,
    NoteType, PurgeReviewsParams, RegisterReviewerParams, ReportsFilters, ReportsOptions,
    ReportsResult, ReportsView, ReviewPhase, ReviewVerdict, ReviewerStatus, SessionLocator,
    SetInitiatorStatusParams, SeverityCounts, SpawnChildReviewersParams, UpdateReviewParams,
};
use mpcr::{analyze, protocol};
use serde::Serialize;
use serde_json::Value;
use std::fs;
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use time::{Date, Month, OffsetDateTime};

fn validate_id8_arg(id8: &str, label: &str) -> anyhow::Result<()> {
    anyhow::ensure!(
        id8.len() == 8,
        "{label} must be 8 ASCII alphanumeric characters"
    );
    anyhow::ensure!(
        id8.chars().all(|c| c.is_ascii_alphanumeric()),
        "{label} must be 8 ASCII alphanumeric characters"
    );
    Ok(())
}

#[derive(Parser)]
#[command(
    name = "mpcr",
    version,
    about = "UACRP code review coordination utilities",
    long_about = "UACRP code review coordination utilities.\n\n\
`mpcr` manages a shared *session directory* containing `_session.toml`, a lock file, and reviewer report markdown files.\n\
All writers acquire `_session.toml.lock` and update `_session.toml` via an atomic temp-file replace to avoid races.\n\
Writers MAY fall back to `_session.json` only when TOML serialization or commit fails.\n\n\
Use `--json` for machine-readable output (compact).\n\
Use `--json-pretty` for human-readable JSON.\n\
Without `--json` or `--json-pretty`, most commands print compact one-line JSON; `id` commands print raw ids and successful mutations print `ok`.",
    after_long_help = r#"Session directory layout (relative to repo root):
  .local/reports/code_reviews/YYYY-MM-DD/
    _session.toml
    _session.toml.lock
    {HH-MM-SS-mmm}_{ref}_{reviewer_id}.md

Output path notes:
  report_file  Repo-root-relative report path (stored in the session artifact)
  report_path  Full filesystem report path (best effort)

Environment variables (optional; only read when `--use-env` is passed):
  MPCR_REPO_ROOT    Repo root used for default session dir (default: auto-detect git root; fallback: cwd)
  MPCR_DATE         Session date (YYYY-MM-DD) used for default session dir (default: today in UTC)
  MPCR_SESSION_DIR  Explicit session directory containing `_session.toml`
  MPCR_SESSION_FORMAT  Active artifact format (`toml_primary` or `json_fallback`)
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
    /// Acquire/release the session lock file (`_session.toml.lock`).
    Lock {
        #[command(subcommand)]
        command: LockCommands,
    },
    /// Read session state (TOML primary; JSON fallback) without modifying it.
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
    /// Language-agnostic static analysis (dead code, duplicates, complexity, TODOs).
    Analyze {
        #[command(subcommand)]
        command: AnalyzeCommands,
    },
    /// Deterministic full-cycle planning and telemetry.
    Fullcycle {
        #[command(subcommand)]
        command: FullcycleCommands,
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
    /// Acquire the session lock file (`_session.toml.lock`).
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
            help = "Lock owner identifier (must match the contents of `_session.toml.lock`)."
        )]
        owner: String,
    },
}

#[derive(Subcommand)]
enum SessionCommands {
    /// Print the parsed active session artifact.
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
    /// Purge review entries and optionally their report files.
    #[command(after_long_help = r#"Examples:
  # Dry-run: preview what would be purged (safe, no changes):
  mpcr session cleanup --dry-run

  # Purge all entries for a specific reviewer (and their children):
  mpcr session cleanup --reviewer-id <ID8> --include-children --delete-report-files

  # Purge entries older than a timestamp:
  mpcr session cleanup --before 2026-01-15T00:00:00Z --delete-report-files

  # Purge entries between two timestamps:
  mpcr session cleanup --after 2026-01-01T00:00:00Z --before 2026-02-01T00:00:00Z

  # Purge only CANCELLED reviews:
  mpcr session cleanup --reviewer-status CANCELLED --delete-report-files

  # Purge entries for a specific session:
  mpcr session cleanup --session-id <ID8> --include-children --delete-report-files

  # Purge by verdict:
  mpcr session cleanup --verdict APPROVE --delete-report-files
"#)]
    Cleanup {
        #[command(flatten)]
        session: SessionDirArgs,
        #[arg(
            long,
            value_name = "ID8",
            help = "Only purge reviews matching this reviewer id."
        )]
        reviewer_id: Option<String>,
        #[arg(
            long,
            value_name = "ID8",
            help = "Only purge reviews matching this session id."
        )]
        session_id: Option<String>,
        #[arg(
            long,
            value_name = "REF",
            help = "Only purge reviews matching this target ref."
        )]
        target_ref: Option<String>,
        #[arg(
            long,
            value_enum,
            value_delimiter = ',',
            num_args = 1..,
            value_name = "STATUS",
            help = "Only purge reviews with these reviewer statuses."
        )]
        reviewer_status: Vec<ReviewerStatus>,
        #[arg(
            long,
            value_enum,
            value_delimiter = ',',
            num_args = 1..,
            value_name = "STATUS",
            help = "Only purge reviews with these initiator statuses."
        )]
        initiator_status: Vec<InitiatorStatus>,
        #[arg(
            long,
            value_enum,
            value_delimiter = ',',
            num_args = 1..,
            value_name = "VERDICT",
            help = "Only purge reviews with these verdicts."
        )]
        verdict: Vec<ReviewVerdict>,
        #[arg(
            long,
            value_name = "RFC3339",
            help = "Only purge reviews started at or after this timestamp (e.g. 2026-01-15T00:00:00Z)."
        )]
        after: Option<String>,
        #[arg(
            long,
            value_name = "RFC3339",
            help = "Only purge reviews started at or before this timestamp (e.g. 2026-02-01T00:00:00Z)."
        )]
        before: Option<String>,
        #[arg(
            long,
            help = "Also purge child entries whose parent matches the filters."
        )]
        include_children: bool,
        #[arg(
            long,
            help = "Delete report markdown files from disk for purged entries."
        )]
        delete_report_files: bool,
        #[arg(
            long,
            help = "Preview what would be purged without modifying anything."
        )]
        dry_run: bool,
    },
}

#[derive(Args)]
struct SessionDirArgs {
    #[arg(
        long,
        value_name = "DIR",
        help = "Session directory containing `_session.toml` (default: <repo_root>/.local/reports/code_reviews/<date>)."
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

#[derive(Copy, Clone, Debug, ValueEnum)]
enum ReviewerValidateKind {
    /// Worker proof packet written by `reviewer complete-child`.
    ChildProofPacket,
    /// Parent synthesized review report written by `reviewer finalize`.
    ParentReviewReport,
}

impl From<ReviewerValidateKind> for ReportValidationKind {
    fn from(value: ReviewerValidateKind) -> Self {
        match value {
            ReviewerValidateKind::ChildProofPacket => Self::ChildProofPacket,
            ReviewerValidateKind::ParentReviewReport => Self::ParentReviewReport,
        }
    }
}

#[derive(Subcommand)]
enum ReviewerCommands {
    /// Register yourself as a reviewer (creates/updates `_session.toml`).
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

  # Start fresh for just this session day before registering:
  mpcr reviewer register --target-ref main --date 2026-01-11 --clear-session-day

  # Start fresh across all prior days before registering:
  mpcr reviewer register --target-ref main --clear-all-session-days
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
        #[arg(
            long,
            conflicts_with = "clear_all_session_days",
            help = "Remove the canonical <repo_root>/.local/reports/code_reviews/<date> directory before registering; rejects custom session-dir overrides."
        )]
        clear_session_day: bool,
        #[arg(
            long,
            conflicts_with = "clear_session_day",
            help = "Remove all YYYY-MM-DD session directories under <repo_root>/.local/reports/code_reviews before registering."
        )]
        clear_all_session_days: bool,
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
            help = "Reviewer status to apply to matching child entries (allowed: CANCELLED, ERROR)."
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

    /// Validate a report artifact without mutating session state.
    #[command(after_long_help = r#"Examples:
  mpcr reviewer validate-report --kind child-proof-packet --report-file child.md
  mpcr reviewer validate-report --kind parent-review-report --blocker 0 --major 1 --minor 0 --nit 0 < parent.md
"#)]
    ValidateReport {
        #[arg(
            long,
            value_enum,
            value_name = "KIND",
            help = "Validation contract to apply to the report artifact."
        )]
        kind: ReviewerValidateKind,
        #[arg(
            long,
            value_name = "PATH",
            help = "Read report markdown from this file instead of stdin."
        )]
        report_file: Option<PathBuf>,
        #[arg(long, help = "Expected BLOCKER count for reconciliation.")]
        blocker: Option<u64>,
        #[arg(long, help = "Expected MAJOR count for reconciliation.")]
        major: Option<u64>,
        #[arg(long, help = "Expected MINOR count for reconciliation.")]
        minor: Option<u64>,
        #[arg(long, help = "Expected NIT count for reconciliation.")]
        nit: Option<u64>,
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
  # Code Review Report
  
  ```toml
  schema_version = "proof_packet.v2"
  artifact_kind = "parent_review_report"
  reviewer_id = "<ID8>"
  session_id = "<ID8>"
  target_ref = "refs/heads/main"
  verdict = "APPROVE"
  ```
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
            help = "Lock owner id8 used while updating the session artifact (default: random)."
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
            help = "Lock owner id8 used while updating the session artifact (default: random)."
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
        #[arg(
            long,
            value_name = "SECS",
            default_value = "3600",
            help = "Maximum seconds to wait before exiting with an error (default: 3600)."
        )]
        timeout_secs: u64,
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
    /// Full-cycle orchestration guidance (review → apply → re-review convergence).
    Fullcycle,
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
            help = "Subagent role (e.g. architecture-critic, security-adversary, domain-specialist). Use `mpcr protocol dispatch-list` for all roles."
        )]
        role: String,
    },
    /// Session management guidance (cleanup, housekeeping).
    Session {
        #[arg(long, value_name = "PHASE", help = "Session phase (CLEANUP).")]
        phase: String,
    },
    /// Invocation alias mapping (user trigger phrases → modes).
    InvocationAliases,
    /// Workflow selection guidance (how to infer mode from context).
    WorkflowSelection,
    /// Proof Packet quality gate rubric.
    QualityGate,
    /// Change size classification table.
    ChangeClassification,
    /// Static analysis integration guidance.
    AnalyzeGuidance,
    /// Scope mapping guidance (PR/issues/branch/commit context compression).
    ScopeMapping,
    /// Convergence planning guidance for recursive full-cycle execution.
    ConvergencePlanning,
    /// List all available dispatch role slugs.
    DispatchList,
    /// List protocol capabilities exposed by this binary.
    Capabilities,
    /// List all available protocol entries.
    List,
}

#[derive(Subcommand)]
enum AnalyzeCommands {
    /// Run all static checks on the given files.
    Run {
        #[arg(
            value_name = "FILE",
            num_args = 1..,
            help = "Files to analyze."
        )]
        files: Vec<PathBuf>,
    },
    /// Run a single named check.
    Check {
        #[arg(
            long,
            value_name = "CHECK",
            help = "Check name (dead-code, todos, long-functions, long-lines, unreachable, duplicates, complexity)."
        )]
        name: String,
        #[arg(
            value_name = "FILE",
            num_args = 1..,
            help = "Files to analyze."
        )]
        files: Vec<PathBuf>,
    },
    /// List available checks.
    ListChecks,
}

#[derive(Subcommand)]
enum FullcycleCommands {
    /// Compute deterministic next-step full-cycle plan (read-only).
    Plan {
        #[command(flatten)]
        session: SessionDirArgs,
        #[arg(
            long,
            value_name = "REF",
            help = "Target reference being orchestrated."
        )]
        target_ref: String,
        #[arg(long, value_name = "ID8", help = "Optional session id filter.")]
        session_id: Option<String>,
        #[arg(
            long,
            value_enum,
            default_value = "auto",
            value_name = "DETAIL",
            help = "Progressive disclosure level (auto, compact, standard, full)."
        )]
        detail: DetailLevel,
        #[arg(
            long,
            value_name = "N",
            help = "Optional worker budget override (4, 6, or 8)."
        )]
        worker_budget: Option<u8>,
    },
    /// Compute recursive convergence plan (read-only).
    LoopPlan {
        #[command(flatten)]
        session: SessionDirArgs,
        #[arg(
            long,
            value_name = "REF",
            help = "Target reference being orchestrated."
        )]
        target_ref: String,
        #[arg(long, value_name = "ID8", help = "Optional session id filter.")]
        session_id: Option<String>,
        #[arg(
            long,
            value_enum,
            default_value = "auto",
            value_name = "DETAIL",
            help = "Progressive disclosure level (auto, compact, standard, full)."
        )]
        detail: DetailLevel,
        #[arg(
            long,
            value_name = "N",
            help = "Optional worker budget override (4, 6, or 8)."
        )]
        worker_budget: Option<u8>,
    },
    /// Show persisted `fullcycle_state` telemetry from session extra fields.
    State {
        #[command(flatten)]
        session: SessionDirArgs,
    },
    /// Persist a deterministic full-cycle telemetry checkpoint.
    Checkpoint {
        #[command(flatten)]
        session: SessionDirArgs,
        #[arg(
            long,
            value_name = "REF",
            help = "Target reference being orchestrated."
        )]
        target_ref: String,
        #[arg(long, value_name = "ID8", help = "Optional session id filter.")]
        session_id: Option<String>,
        #[arg(
            long,
            value_enum,
            default_value = "auto",
            value_name = "DETAIL",
            help = "Progressive disclosure level (auto, compact, standard, full)."
        )]
        detail: DetailLevel,
        #[arg(
            long,
            value_name = "N",
            help = "Optional worker budget override (4, 6, or 8)."
        )]
        worker_budget: Option<u8>,
        #[arg(
            long,
            value_name = "ID8",
            help = "Optional lock owner id8 for session write (default: random)."
        )]
        lock_owner: Option<String>,
    },
}

#[derive(Debug, Serialize)]
struct OkResult {
    ok: bool,
}

fn main() {
    if let Err(err) = run() {
        eprintln!("{}", format_cli_error(&err));
        std::process::exit(1);
    }
}

fn format_cli_error(err: &anyhow::Error) -> String {
    let message = err.to_string();
    if message.starts_with("error:") {
        message
    } else {
        format!("error: {message}")
    }
}

#[allow(clippy::too_many_lines)]
fn run() -> anyhow::Result<()> {
    let (cli_argv, compat_hint) = normalize_argv_for_compat();
    if let Some(hint) = compat_hint {
        eprintln!("{hint}");
    }
    let cli = Cli::parse_from(cli_argv);
    enforce_worker_mode_restrictions(&cli.command)?;
    enforce_worker_session_dir_binding(&cli.command)?;
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
                let cfg = LockConfig {
                    max_retries,
                    ..LockConfig::default()
                };
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
                ReportsCommands::Open(report_args) => {
                    handle_reports(
                        use_env,
                        json,
                        json_pretty,
                        now.date(),
                        ReportsView::Open,
                        report_args,
                    )?;
                }
                ReportsCommands::Closed(report_args) => {
                    handle_reports(
                        use_env,
                        json,
                        json_pretty,
                        now.date(),
                        ReportsView::Closed,
                        report_args,
                    )?;
                }
                ReportsCommands::InProgress(report_args) => {
                    handle_reports(
                        use_env,
                        json,
                        json_pretty,
                        now.date(),
                        ReportsView::InProgress,
                        report_args,
                    )?;
                }
            },
            SessionCommands::Cleanup {
                session,
                reviewer_id,
                session_id,
                target_ref,
                reviewer_status,
                initiator_status,
                verdict,
                after,
                before,
                include_children,
                delete_report_files,
                dry_run,
            } => {
                let resolved = resolve_session_input(use_env, &session, now.date())?;
                let session_locator = SessionLocator::new(resolved.session_dir.clone());
                let result = purge_reviews(&PurgeReviewsParams {
                    session: session_locator,
                    repo_root: resolved.repo_root,
                    reviewer_id,
                    session_id,
                    target_ref,
                    reviewer_statuses: reviewer_status,
                    initiator_statuses: initiator_status,
                    verdicts: verdict,
                    after,
                    before,
                    include_children,
                    delete_report_files,
                    dry_run,
                })?;
                write_result(json, json_pretty, &result)?;
            }
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
                clear_session_day,
                clear_all_session_days,
            } => {
                let target_ref_for_env = target_ref.clone();
                let resolved = resolve_session_input(use_env, &session, now.date())?;

                // When --parent-id is set (child registration), ignore MPCR_REVIEWER_ID from env
                // to prevent accidentally reusing the parent's identity. A child should either
                // provide an explicit --reviewer-id or let mpcr generate a new one.
                let reviewer_id = if parent_id.is_some() {
                    reviewer_id // Ignore env fallback for children
                } else {
                    reviewer_id.or_else(|| opt_env_string(use_env, "MPCR_REVIEWER_ID"))
                };
                let session_id = session_id.or_else(|| opt_env_string(use_env, "MPCR_SESSION_ID"));

                if clear_session_day || clear_all_session_days {
                    if let Some(reviewer_id) = reviewer_id.as_deref() {
                        validate_id8_arg(reviewer_id, "reviewer_id")?;
                    }
                    if let Some(session_id) = session_id.as_deref() {
                        validate_id8_arg(session_id, "session_id")?;
                    }
                    if let Some(parent_id) = parent_id.as_deref() {
                        validate_id8_arg(parent_id, "parent_id")?;
                        anyhow::bail!(
                            "cleanup flags are not allowed with --parent-id; register the child without cleanup"
                        );
                    }
                }
                if clear_session_day {
                    let canonical_session_dir =
                        mpcr::paths::session_paths(&resolved.repo_root, resolved.session_date)
                            .session_dir;
                    ensure_paths_match_for_clear_session_day(
                        &resolved.session_dir,
                        &canonical_session_dir,
                    )?;
                    clear_session_day_dir(&canonical_session_dir)?;
                } else if clear_all_session_days {
                    clear_all_session_days_under_repo_root(&resolved.repo_root)?;
                }
                let repo_root_for_env = resolved.repo_root.to_string_lossy().to_string();
                let date_for_env = resolved.session_date.to_string();
                let session = SessionLocator::new(resolved.session_dir.clone());

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
                    (
                        "MPCR_SESSION_FORMAT",
                        match res.session_format {
                            mpcr::session::SessionStorageFormat::TomlPrimary => "toml_primary",
                            mpcr::session::SessionStorageFormat::JsonFallback => "json_fallback",
                        },
                    ),
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
                if count == 0 {
                    return Err(anyhow::anyhow!("--count must be at least 1"));
                }

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
                let reviewer_id_for_state = reviewer_id.clone();
                let session_id_for_state = session_id.clone();
                let resolved = resolve_session_input(use_env, &session, now.date())?;
                let res = finalize_review(FinalizeReviewParams {
                    session: SessionLocator::new(resolved.session_dir.clone()),
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
                    validation_kind: ReportValidationKind::ParentReviewReport,
                    copy_input_report: copy_report_input,
                    auto_close_open_children: !no_auto_close_children,
                    auto_close_children_status,
                    now,
                })?;
                if let Err(err) = best_effort_refresh_fullcycle_state(
                    &resolved.session_dir,
                    &reviewer_id_for_state,
                    &session_id_for_state,
                    now,
                ) {
                    eprintln!("warning: fullcycle telemetry refresh failed: {err}");
                }
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
                let reviewer_id_for_state = reviewer_id.clone();
                let session_id_for_state = session_id.clone();
                let resolved = resolve_session_input(use_env, &session, now.date())?;
                let session_locator = SessionLocator::new(resolved.session_dir.clone());

                ensure_complete_child_has_parent(&session_locator, &reviewer_id, &session_id)?;

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
                    validation_kind: ReportValidationKind::ChildProofPacket,
                    copy_input_report: copy_report_input,
                    auto_close_open_children: false,
                    auto_close_children_status: ReviewerStatus::Cancelled,
                    now,
                })?;
                if let Err(err) = best_effort_refresh_fullcycle_state(
                    &resolved.session_dir,
                    &reviewer_id_for_state,
                    &session_id_for_state,
                    now,
                ) {
                    eprintln!("warning: fullcycle telemetry refresh failed: {err}");
                }

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

            ReviewerCommands::ValidateReport {
                kind,
                report_file,
                blocker,
                major,
                minor,
                nit,
            } => {
                let markdown = match report_file {
                    Some(path) => std::fs::read_to_string(&path)
                        .with_context(|| format!("read report file {}", path.display()))?,
                    None => read_stdin_to_string().context("read report markdown from stdin")?,
                };
                let expected_counts =
                    if blocker.is_some() || major.is_some() || minor.is_some() || nit.is_some() {
                        Some(SeverityExpectation {
                            blocker: blocker.map_or(0, std::convert::identity),
                            major: major.map_or(0, std::convert::identity),
                            minor: minor.map_or(0, std::convert::identity),
                            nit: nit.map_or(0, std::convert::identity),
                        })
                    } else {
                        None
                    };
                let summary: ReportValidationSummary =
                    validate_report_markdown(&markdown, kind.into(), expected_counts, None)?;
                write_result(json, json_pretty, &summary)?;
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
                let reviewer_id_for_state = reviewer_id.clone();
                let session_id_for_state = session_id.clone();
                let resolved = resolve_session_input(use_env, &session, now.date())?;
                let lock_owner = match lock_owner {
                    Some(lock_owner) => lock_owner,
                    None => id::random_id8()?,
                };
                let params = SetInitiatorStatusParams {
                    session: SessionLocator::new(resolved.session_dir.clone()),
                    reviewer_id,
                    session_id,
                    initiator_status,
                    now,
                    lock_owner,
                };
                set_initiator_status(&params)?;
                if let Err(err) = best_effort_refresh_fullcycle_state(
                    &resolved.session_dir,
                    &reviewer_id_for_state,
                    &session_id_for_state,
                    now,
                ) {
                    eprintln!("warning: fullcycle telemetry refresh failed: {err}");
                }
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
                timeout_secs,
            } => {
                let target_ref = target_ref.or_else(|| opt_env_string(use_env, "MPCR_TARGET_REF"));
                let session_id = session_id.or_else(|| opt_env_string(use_env, "MPCR_SESSION_ID"));
                let resolved = resolve_session_input(use_env, &session, now.date())?;
                wait_for_reviews(
                    &resolved.session_dir,
                    target_ref.as_deref(),
                    session_id.as_deref(),
                    timeout_secs,
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
            ProtocolCommands::Fullcycle => {
                let out = protocol::fullcycle()?;
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
            ProtocolCommands::Session { phase } => {
                let out = protocol::session_phase(&phase)?;
                if json {
                    write_json(json_pretty, &out)?;
                } else {
                    println!("{}", out.content.trim());
                }
            }
            ProtocolCommands::InvocationAliases => {
                let out = protocol::invocation_aliases()?;
                if json {
                    write_json(json_pretty, &out)?;
                } else {
                    println!("{}", out.content.trim());
                }
            }
            ProtocolCommands::WorkflowSelection => {
                let out = protocol::workflow_selection()?;
                if json {
                    write_json(json_pretty, &out)?;
                } else {
                    println!("{}", out.content.trim());
                }
            }
            ProtocolCommands::QualityGate => {
                let out = protocol::quality_gate()?;
                if json {
                    write_json(json_pretty, &out)?;
                } else {
                    println!("{}", out.content.trim());
                }
            }
            ProtocolCommands::ChangeClassification => {
                let out = protocol::change_classification()?;
                if json {
                    write_json(json_pretty, &out)?;
                } else {
                    println!("{}", out.content.trim());
                }
            }
            ProtocolCommands::AnalyzeGuidance => {
                let out = protocol::analyze_guidance()?;
                if json {
                    write_json(json_pretty, &out)?;
                } else {
                    println!("{}", out.content.trim());
                }
            }
            ProtocolCommands::ScopeMapping => {
                let out = protocol::scope_mapping()?;
                if json {
                    write_json(json_pretty, &out)?;
                } else {
                    println!("{}", out.content.trim());
                }
            }
            ProtocolCommands::ConvergencePlanning => {
                let out = protocol::convergence_planning()?;
                if json {
                    write_json(json_pretty, &out)?;
                } else {
                    println!("{}", out.content.trim());
                }
            }
            ProtocolCommands::DispatchList => {
                let roles = protocol::dispatch_list()?;
                if json {
                    write_json(json_pretty, &roles)?;
                } else {
                    for role in &roles {
                        println!("{role}");
                    }
                }
            }
            ProtocolCommands::Capabilities => {
                let out = protocol::capabilities()?;
                if json {
                    write_json(json_pretty, &out)?;
                } else {
                    println!("{}", serde_json::to_string(&out).context("serialize")?);
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
        Commands::Fullcycle { command } => match command {
            FullcycleCommands::Plan {
                session,
                target_ref,
                session_id,
                detail,
                worker_budget,
            } => {
                validate_worker_budget(worker_budget)?;
                let resolved = resolve_session_input(use_env, &session, now.date())?;
                let (plan, _) = fullcycle_plan::build_plan(&BuildParams {
                    session: SessionLocator::new(resolved.session_dir),
                    target_ref,
                    requested_session_id: session_id,
                    worker_budget_override: worker_budget,
                    detail,
                    now,
                    loop_mode: false,
                })?;
                write_result(json, json_pretty, &plan)?;
            }
            FullcycleCommands::LoopPlan {
                session,
                target_ref,
                session_id,
                detail,
                worker_budget,
            } => {
                validate_worker_budget(worker_budget)?;
                let resolved = resolve_session_input(use_env, &session, now.date())?;
                let (plan, _) = fullcycle_plan::build_plan(&BuildParams {
                    session: SessionLocator::new(resolved.session_dir),
                    target_ref,
                    requested_session_id: session_id,
                    worker_budget_override: worker_budget,
                    detail,
                    now,
                    loop_mode: true,
                })?;
                write_result(json, json_pretty, &plan)?;
            }
            FullcycleCommands::State { session } => {
                let resolved = resolve_session_input(use_env, &session, now.date())?;
                let out = fullcycle_plan::load_state(&SessionLocator::new(resolved.session_dir))?;
                write_result(json, json_pretty, &out)?;
            }
            FullcycleCommands::Checkpoint {
                session,
                target_ref,
                session_id,
                detail,
                worker_budget,
                lock_owner,
            } => {
                validate_worker_budget(worker_budget)?;
                let resolved = resolve_session_input(use_env, &session, now.date())?;
                let session_locator = SessionLocator::new(resolved.session_dir);
                let lock_owner = match lock_owner {
                    Some(owner) => owner,
                    None => id::random_id8()?,
                };
                let (_plan, state) = fullcycle_plan::build_plan(&BuildParams {
                    session: session_locator.clone(),
                    target_ref,
                    requested_session_id: session_id,
                    worker_budget_override: worker_budget,
                    detail,
                    now,
                    loop_mode: true,
                })?;
                fullcycle_plan::persist_state(session_locator, lock_owner, &state)?;
                write_result(
                    json,
                    json_pretty,
                    &fullcycle_plan::default_checkpoint_payload(&state),
                )?;
            }
        },
        Commands::Analyze { command } => match command {
            AnalyzeCommands::Run { files } => {
                let file_map = load_file_map(&files)?;
                let report = analyze::run_all(&file_map)?;
                if json {
                    write_json(json_pretty, &report)?;
                } else {
                    print_analysis_text(&report);
                }
            }
            AnalyzeCommands::Check { name, files } => {
                let file_map = load_file_map(&files)?;
                let output = analyze::run_check_output(&file_map, &name)?;
                if json {
                    write_json(json_pretty, &output)?;
                } else {
                    print_analysis_check_text(&output);
                }
            }
            AnalyzeCommands::ListChecks => {
                let checks = analyze::available_checks();
                if json {
                    let list: Vec<serde_json::Value> = checks
                        .iter()
                        .map(|(name, desc)| serde_json::json!({"name": name, "description": desc}))
                        .collect();
                    write_json(json_pretty, &list)?;
                } else {
                    for (name, desc) in &checks {
                        println!("{name:20} {desc}");
                    }
                }
            }
        },
    }

    Ok(())
}
fn load_file_map(paths: &[PathBuf]) -> anyhow::Result<std::collections::HashMap<String, String>> {
    let mut map = std::collections::HashMap::new();
    for path in paths {
        let content = std::fs::read_to_string(path)
            .map_err(|e| anyhow::anyhow!("read {}: {e}", path.display()))?;
        let key = path.to_string_lossy().to_string();
        map.insert(key, content);
    }
    Ok(map)
}

fn print_analysis_text(report: &analyze::AnalysisReport) {
    println!(
        "Scanned {} files ({} lines)",
        report.files_scanned, report.total_lines
    );
    if !report.findings.is_empty() {
        println!("\n--- Findings ({}) ---", report.findings.len());
        for f in &report.findings {
            println!("[{}] {}:{} — {}", f.check, f.file, f.line, f.detail);
        }
    }
    if !report.duplicate_blocks.is_empty() {
        println!(
            "\n--- Duplicate Blocks ({}) ---",
            report.duplicate_blocks.len()
        );
        for dup in &report.duplicate_blocks {
            println!(
                "Block ({} lines, {} locations):",
                dup.line_count,
                dup.locations.len()
            );
            for loc in &dup.locations {
                println!("  {}:{}", loc.file, loc.start_line);
            }
        }
    }
    if !report.complexity_hotspots.is_empty() {
        println!(
            "\n--- Complexity Hotspots ({}) ---",
            report.complexity_hotspots.len()
        );
        for spot in &report.complexity_hotspots {
            println!(
                "  {}:{} {} (nesting={}, branches={})",
                spot.file, spot.start_line, spot.name_hint, spot.max_nesting, spot.branch_count
            );
        }
    }
    if !report.dead_markers.is_empty() {
        println!(
            "\n--- Dead Code Markers ({}) ---",
            report.dead_markers.len()
        );
        for d in &report.dead_markers {
            println!("  {}:{} — {}", d.file, d.line, d.detail);
        }
    }
}

fn print_analysis_check_text(output: &analyze::CheckOutput) {
    match output {
        analyze::CheckOutput::Findings { findings, .. } => {
            for f in findings {
                println!("[{}] {}:{} — {}", f.check, f.file, f.line, f.detail);
                if !f.excerpt.is_empty() {
                    println!("  > {}", f.excerpt);
                }
            }
        }
        analyze::CheckOutput::DuplicateBlocks {
            duplicate_blocks, ..
        } => {
            for dup in duplicate_blocks {
                println!(
                    "Duplicate block ({} lines, {} locations):",
                    dup.line_count,
                    dup.locations.len()
                );
                for loc in &dup.locations {
                    println!("  {}:{}", loc.file, loc.start_line);
                }
            }
        }
        analyze::CheckOutput::ComplexityHotspots {
            complexity_hotspots,
            ..
        } => {
            for spot in complexity_hotspots {
                println!(
                    "{}:{} {} (nesting={}, branches={})",
                    spot.file, spot.start_line, spot.name_hint, spot.max_nesting, spot.branch_count
                );
            }
        }
    }
}

fn enforce_worker_mode_restrictions(command: &Commands) -> anyhow::Result<()> {
    let dispatch_role = std::env::var("MPCR_DISPATCH_ROLE")
        .ok()
        .filter(|value| !value.trim().is_empty());
    let applicator_role = std::env::var("MPCR_APPLICATOR_ROLE")
        .ok()
        .filter(|value| !value.trim().is_empty());

    let role_name = match (&dispatch_role, &applicator_role) {
        (Some(role), _) | (None, Some(role)) => role.clone(),
        (None, None) => return Ok(()),
    };

    // Protocol and Id commands are always allowed for all worker roles.
    if matches!(command, Commands::Protocol { .. } | Commands::Id { .. }) {
        return Ok(());
    }

    let allowed = match (&dispatch_role, &applicator_role) {
        (Some(_), _) => matches!(
            command,
            Commands::Analyze { .. }
                | Commands::Reviewer {
                    command: ReviewerCommands::Update { .. }
                        | ReviewerCommands::Note { .. }
                        | ReviewerCommands::CompleteChild { .. }
                        | ReviewerCommands::ValidateReport { .. }
                }
        ),
        (None, Some(_)) => matches!(
            command,
            Commands::Applicator {
                command: ApplicatorCommands::Note { .. } | ApplicatorCommands::SetStatus { .. }
            }
        ),
        _ => true,
    };
    if !allowed {
        let allowed_cmds = if dispatch_role.is_some() {
            "`mpcr reviewer update`, `mpcr reviewer note`, `mpcr reviewer complete-child`, `mpcr reviewer validate-report`, `mpcr analyze <subcommand>`, `mpcr protocol <subcommand>`, and `mpcr id <subcommand>`"
        } else {
            "`mpcr applicator note`, `mpcr applicator set-status`, `mpcr protocol <subcommand>`, and `mpcr id <subcommand>`"
        };
        return Err(anyhow::anyhow!(
            "{env}={role_name} restricts this executor to {allowed_cmds} only",
            env = if dispatch_role.is_some() {
                "MPCR_DISPATCH_ROLE"
            } else {
                "MPCR_APPLICATOR_ROLE"
            },
        ));
    }

    enforce_worker_identity_binding(command)?;
    Ok(())
}

fn worker_mode_env_active() -> bool {
    std::env::var("MPCR_DISPATCH_ROLE")
        .ok()
        .filter(|v| !v.trim().is_empty())
        .is_some()
        || std::env::var("MPCR_APPLICATOR_ROLE")
            .ok()
            .filter(|v| !v.trim().is_empty())
            .is_some()
}

/// Validates that CLI-supplied `--reviewer-id` and `--session-id` match the
/// worker identity declared via `MPCR_REVIEWER_ID` / `MPCR_SESSION_ID`.
///
/// Only enforced when both the environment variable AND the CLI flag are
/// present — a `None` CLI flag means "use env default" and is always allowed.
///
/// # Arguments
/// * `command` - The parsed CLI command to inspect for identity fields.
///
/// # Returns
/// * `Ok(())` when no mismatch is detected.
/// * `Err` with a descriptive message when a provided CLI id contradicts the env.
///
/// # Examples
/// ```no_run
/// # // Conceptual usage — called internally by enforce_worker_mode_restrictions.
/// # // enforce_worker_identity_binding(&command)?;
/// ```
fn enforce_worker_identity_binding(command: &Commands) -> anyhow::Result<()> {
    let env_reviewer_id = std::env::var("MPCR_REVIEWER_ID")
        .ok()
        .filter(|v| !v.trim().is_empty());
    let env_session_id = std::env::var("MPCR_SESSION_ID")
        .ok()
        .filter(|v| !v.trim().is_empty());

    // Worker mode requires identity binding — fail fast if role is set but IDs are missing.
    if worker_mode_env_active() {
        if env_reviewer_id.is_none() {
            return Err(anyhow::anyhow!(
                "worker mode requires MPCR_REVIEWER_ID to be set"
            ));
        }
        if env_session_id.is_none() {
            return Err(anyhow::anyhow!(
                "worker mode requires MPCR_SESSION_ID to be set"
            ));
        }
    }

    let (cmd_reviewer_id, cmd_session_id) = extract_identity_fields(command);

    if let (Some(provided), Some(expected)) = (cmd_reviewer_id, env_reviewer_id.as_deref()) {
        if provided != expected {
            return Err(anyhow::anyhow!(
                "worker identity mismatch: --reviewer-id {provided} does not match MPCR_REVIEWER_ID={expected}"
            ));
        }
    }

    if let (Some(provided), Some(expected)) = (cmd_session_id, env_session_id.as_deref()) {
        if provided != expected {
            return Err(anyhow::anyhow!(
                "worker identity mismatch: --session-id {provided} does not match MPCR_SESSION_ID={expected}"
            ));
        }
    }

    Ok(())
}

/// Extracts optional `reviewer_id` and `session_id` references from the given
/// command variant, returning `(Option<&str>, Option<&str>)`.
///
/// Only the command variants reachable under worker-mode dispatch
/// (`ReviewerCommands::Update`, `ReviewerCommands::Note`,
/// `ApplicatorCommands::Note`, `ApplicatorCommands::SetStatus`) carry identity
/// fields. All other variants return `(None, None)`.
///
/// # Arguments
/// * `command` - The parsed top-level CLI command.
///
/// # Returns
/// A tuple of `(reviewer_id, session_id)` as optional string slices.
fn extract_identity_fields(command: &Commands) -> (Option<&str>, Option<&str>) {
    match command {
        Commands::Reviewer { command: sub } => match sub {
            ReviewerCommands::Update {
                reviewer_id,
                session_id,
                ..
            }
            | ReviewerCommands::Note {
                reviewer_id,
                session_id,
                ..
            }
            | ReviewerCommands::CompleteChild {
                reviewer_id,
                session_id,
                ..
            } => (reviewer_id.as_deref(), session_id.as_deref()),
            ReviewerCommands::Register { .. }
            | ReviewerCommands::SpawnChildren { .. }
            | ReviewerCommands::CloseChildren { .. }
            | ReviewerCommands::Finalize { .. }
            | ReviewerCommands::ValidateReport { .. } => (None, None),
        },
        Commands::Applicator { command: sub } => match sub {
            ApplicatorCommands::Note {
                reviewer_id,
                session_id,
                ..
            }
            | ApplicatorCommands::SetStatus {
                reviewer_id,
                session_id,
                ..
            } => (reviewer_id.as_deref(), session_id.as_deref()),
            ApplicatorCommands::Wait { .. } => (None, None),
        },
        _ => (None, None),
    }
}

/// Extracts the optional `session_dir` from the `SessionDirArgs` embedded in
/// any command variant that carries one.  Returns `None` for variants without
/// a session-dir field.
fn extract_session_dir_field(command: &Commands) -> Option<&Path> {
    let args: Option<&SessionDirArgs> = match command {
        Commands::Reviewer { command: sub } => match sub {
            ReviewerCommands::Register { session, .. }
            | ReviewerCommands::SpawnChildren { session, .. }
            | ReviewerCommands::CloseChildren { session, .. }
            | ReviewerCommands::CompleteChild { session, .. }
            | ReviewerCommands::Update { session, .. }
            | ReviewerCommands::Finalize { session, .. }
            | ReviewerCommands::Note { session, .. } => Some(session),
            ReviewerCommands::ValidateReport { .. } => None,
        },
        Commands::Applicator { command: sub } => match sub {
            ApplicatorCommands::SetStatus { session, .. }
            | ApplicatorCommands::Note { session, .. }
            | ApplicatorCommands::Wait { session, .. } => Some(session),
        },
        Commands::Lock { command: sub } => match sub {
            LockCommands::Acquire { session, .. } | LockCommands::Release { session, .. } => {
                Some(session)
            }
        },
        Commands::Session { command: sub } => match sub {
            SessionCommands::Show { session, .. } | SessionCommands::Cleanup { session, .. } => {
                Some(session)
            }
            SessionCommands::Reports { .. } => None,
        },
        _ => None,
    };
    args.and_then(|a| a.session_dir.as_deref())
}

/// Ensures that when running in worker mode, any explicit `--session-dir` CLI
/// argument matches the `MPCR_SESSION_DIR` environment variable.
///
/// If no env var is set or no CLI flag is provided, the check passes.
fn enforce_worker_session_dir_binding(command: &Commands) -> anyhow::Result<()> {
    if !worker_mode_env_active() {
        return Ok(());
    }
    // Protocol and Id commands never need a session directory.
    if matches!(command, Commands::Protocol { .. } | Commands::Id { .. }) {
        return Ok(());
    }
    let env_session_dir = std::env::var("MPCR_SESSION_DIR")
        .ok()
        .filter(|v| !v.trim().is_empty());
    let Some(env_session_dir) = env_session_dir else {
        return Err(anyhow::anyhow!(
            "worker mode requires MPCR_SESSION_DIR to be set"
        ));
    };
    let cmd_session_dir = extract_session_dir_field(command);
    let env_path = std::path::PathBuf::from(&env_session_dir);
    match cmd_session_dir {
        Some(provided) => {
            let canonical_provided = provided
                .canonicalize()
                .map_or_else(|_| provided.to_path_buf(), std::convert::identity);
            let canonical_env = env_path
                .canonicalize()
                .map_or_else(|_| env_path.clone(), std::convert::identity);
            if canonical_provided != canonical_env {
                return Err(anyhow::anyhow!(
                    "worker mode: --session-dir {} does not match MPCR_SESSION_DIR={}",
                    provided.display(),
                    env_session_dir,
                ));
            }
        }
        None => {
            if !env_path.is_dir() {
                return Err(anyhow::anyhow!(
                    "worker mode: MPCR_SESSION_DIR={env_session_dir} is not a valid directory",
                ));
            }
        }
    }
    Ok(())
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
    let worker_mode = worker_mode_env_active();
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
        .or_else(|| opt_env_pathbuf(worker_mode, "MPCR_SESSION_DIR"))
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

fn clear_session_day_dir(session_dir: &Path) -> anyhow::Result<()> {
    if !session_dir.exists() {
        return Ok(());
    }
    fs::remove_dir_all(session_dir)
        .with_context(|| format!("remove session day dir {}", session_dir.display()))
}

fn clear_all_session_days_under_repo_root(repo_root: &Path) -> anyhow::Result<()> {
    let code_reviews_root = repo_root
        .join(".local")
        .join("reports")
        .join("code_reviews");
    if !code_reviews_root.exists() {
        return Ok(());
    }
    ensure_repo_scoped_cleanup_root(repo_root, &code_reviews_root)?;
    let entries = fs::read_dir(&code_reviews_root)
        .with_context(|| format!("read_dir {}", code_reviews_root.display()))?;
    for entry in entries {
        let entry = entry?;
        let path = entry.path();
        if !path.is_dir() {
            continue;
        }
        let Some(name) = path.file_name().and_then(std::ffi::OsStr::to_str) else {
            continue;
        };
        if !is_yyyy_mm_dd(name) {
            continue;
        }
        fs::remove_dir_all(&path)
            .with_context(|| format!("remove session day dir {}", path.display()))?;
    }
    Ok(())
}

fn ensure_repo_scoped_cleanup_root(repo_root: &Path, cleanup_root: &Path) -> anyhow::Result<()> {
    let metadata = fs::symlink_metadata(cleanup_root)
        .with_context(|| format!("symlink_metadata {}", cleanup_root.display()))?;
    if metadata.file_type().is_symlink() {
        return Err(anyhow::anyhow!(
            "--clear-all-session-days requires a real directory at {}; symlinked cleanup roots are not allowed",
            display_absoluteish_path(cleanup_root)?,
        ));
    }

    let resolved_repo_root = resolve_absoluteish_path(repo_root)?;
    let resolved_cleanup_root = resolve_absoluteish_path(cleanup_root)?;
    if !resolved_cleanup_root.starts_with(&resolved_repo_root) {
        return Err(anyhow::anyhow!(
            "--clear-all-session-days cleanup root must stay under repo root {}; got {}",
            resolved_repo_root.display(),
            resolved_cleanup_root.display(),
        ));
    }
    Ok(())
}

fn ensure_paths_match_for_clear_session_day(
    session_dir: &Path,
    canonical_session_dir: &Path,
) -> anyhow::Result<()> {
    if same_or_equivalent_path(session_dir, canonical_session_dir)? {
        return Ok(());
    }
    Err(anyhow::anyhow!(
        "--clear-session-day only supports the canonical session day directory {}; got {}",
        display_absoluteish_path(canonical_session_dir)?,
        display_absoluteish_path(session_dir)?,
    ))
}

fn same_or_equivalent_path(a: &Path, b: &Path) -> anyhow::Result<bool> {
    Ok(resolve_absoluteish_path(a)? == resolve_absoluteish_path(b)?)
}

fn display_absoluteish_path(path: &Path) -> anyhow::Result<String> {
    Ok(resolve_absoluteish_path(path)?.display().to_string())
}

fn resolve_absoluteish_path(path: &Path) -> anyhow::Result<PathBuf> {
    let path = if path.is_absolute() {
        path.to_path_buf()
    } else {
        std::env::current_dir().context("get cwd")?.join(path)
    };
    if let Ok(canonical) = path.canonicalize() {
        return Ok(canonical);
    }
    if let Some(parent) = path.parent() {
        if let Ok(canonical_parent) = parent.canonicalize() {
            let name = path
                .file_name()
                .ok_or_else(|| anyhow::anyhow!("path {} has no final component", path.display()))?;
            return Ok(canonical_parent.join(name));
        }
    }
    Ok(path)
}

fn is_yyyy_mm_dd(name: &str) -> bool {
    if name.len() != 10 {
        return false;
    }
    let bytes = name.as_bytes();
    for (idx, byte) in bytes.iter().enumerate() {
        let is_hyphen = idx == 4 || idx == 7;
        if is_hyphen {
            if *byte != b'-' {
                return false;
            }
        } else if !byte.is_ascii_digit() {
            return false;
        }
    }
    true
}

fn parse_content(as_json: bool, raw: &str) -> anyhow::Result<Value> {
    if as_json {
        serde_json::from_str(raw).context("parse --content as JSON")
    } else {
        Ok(Value::String(raw.to_string()))
    }
}

fn is_known_protocol_subcommand(candidate: &str) -> bool {
    Cli::command()
        .find_subcommand("protocol")
        .and_then(|protocol_cmd| protocol_cmd.find_subcommand(candidate))
        .is_some()
}

fn is_known_global_flag(candidate: &str) -> bool {
    matches!(
        candidate,
        "--json" | "--json-pretty" | "--use-env" | "--help" | "-h" | "--version" | "-V"
    )
}

fn normalize_argv_for_compat() -> (Vec<String>, Option<String>) {
    let mut args: Vec<String> = std::env::args().collect();
    if args.len() < 2 {
        return (args, None);
    }
    let mut command_index: Option<usize> = None;
    for (index, arg) in args.iter().enumerate().skip(1) {
        if arg == "--" {
            break;
        }
        if is_known_global_flag(arg) {
            continue;
        }
        if arg.starts_with('-') {
            return (args, None);
        }
        command_index = Some(index);
        break;
    }
    let Some(first_index) = command_index else {
        return (args, None);
    };
    let Some(first) = args.get(first_index).cloned() else {
        return (args, None);
    };
    if first.split_whitespace().count() == 2 && first.starts_with("protocol ") {
        let parts = first.split_whitespace().collect::<Vec<_>>();
        if let Some(subcommand) = parts
            .get(1)
            .copied()
            .filter(|name| is_known_protocol_subcommand(name))
        {
            args.remove(first_index);
            args.insert(first_index, "protocol".to_string());
            args.insert(first_index + 1, subcommand.to_string());
            return (
                args,
                Some(format!(
                    "compat: interpreted single-token subcommand as `mpcr protocol {subcommand}`"
                )),
            );
        }
    }
    (args, None)
}

fn validate_worker_budget(worker_budget: Option<u8>) -> anyhow::Result<()> {
    if let Some(value) = worker_budget {
        if !matches!(value, 4 | 6 | 8) {
            return Err(anyhow::anyhow!("--worker-budget must be one of 4, 6, or 8"));
        }
    }
    Ok(())
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

    if active_session_artifact(&session)?.is_none() {
        let artifact = session_artifact_or_default(&session)?;
        let result = ReportsResult {
            session_dir: session.session_dir().to_string_lossy().to_string(),
            session_file: artifact.session_file,
            session_format: artifact.session_format,
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
    let result = collect_reports(&session_data, &session, view, filters, options)?;
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
    timeout_secs: u64,
) -> anyhow::Result<()> {
    let mut delay = std::time::Duration::from_secs(1);
    let max_delay = std::time::Duration::from_secs(60);
    let deadline = std::time::Instant::now() + std::time::Duration::from_secs(timeout_secs);
    let session = SessionLocator::new(session_dir.to_path_buf());
    let should_wait_for_session = target_ref.is_some() || session_id.is_some();

    if session_dir.exists() && !session_dir.is_dir() {
        return Err(anyhow::anyhow!(
            "session_dir is not a directory: {}",
            session_dir.display()
        ));
    }

    loop {
        if std::time::Instant::now() >= deadline {
            return Err(anyhow::anyhow!(
                "timed out after {timeout_secs}s waiting for reviews to reach terminal status"
            ));
        }
        if active_session_artifact(&session)?.is_none() {
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
        let mut matched_any = false;
        for r in &session_data.reviews {
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
            matched_any = true;
            if !r.status.is_terminal() {
                has_pending = true;
                break;
            }
        }

        if !matched_any && should_wait_for_session && session_data.reviews.is_empty() {
            std::thread::sleep(delay);
            delay = std::cmp::min(delay.saturating_mul(2), max_delay);
            continue;
        }

        if !has_pending {
            return Ok(());
        }

        std::thread::sleep(delay);
        delay = std::cmp::min(delay.saturating_mul(2), max_delay);
    }
}

fn best_effort_refresh_fullcycle_state(
    session_dir: &Path,
    reviewer_id: &str,
    session_id: &str,
    now: OffsetDateTime,
) -> anyhow::Result<()> {
    let locator = SessionLocator::new(session_dir.to_path_buf());
    let session = load_session(&locator)?;
    let Some(target_ref) = session
        .reviews
        .iter()
        .find(|entry| entry.reviewer_id == reviewer_id && entry.session_id == session_id)
        .map(|entry| entry.target_ref.clone())
    else {
        return Ok(());
    };

    let (_plan, state) = fullcycle_plan::build_plan(&BuildParams {
        session: locator.clone(),
        target_ref,
        requested_session_id: Some(session_id.to_string()),
        worker_budget_override: None,
        detail: DetailLevel::Auto,
        now,
        loop_mode: true,
    })?;
    fullcycle_plan::persist_state(locator, id::random_id8()?, &state)?;
    Ok(())
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
            extra: serde_json::Map::default(),
        };
        let session = SessionFile {
            schema_version: "1.2.0".to_string(),
            session_date: "2026-01-11".to_string(),
            repo_root: dir.path().to_string_lossy().to_string(),
            reviewers: vec!["deadbeef".to_string()],
            reviews: vec![entry],
            extra: serde_json::Map::new(),
        };
        let mut body = serde_json::to_value(&session)?;
        let body_object = body
            .as_object_mut()
            .ok_or_else(|| anyhow::anyhow!("session fixture must serialize to object"))?;
        body_object.insert(
            "storage_format".to_string(),
            serde_json::Value::String("json_fallback".to_string()),
        );
        let body = serde_json::to_string_pretty(&body)? + "\n";
        fs::write(session_dir.join("_session.json"), body)?;

        wait_for_reviews(&session_dir, None, None, 60)?;
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
