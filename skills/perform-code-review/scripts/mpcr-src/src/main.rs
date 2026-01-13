#![allow(clippy::print_stderr, clippy::print_stdout)]

//! CLI entrypoint for `mpcr` (UACRP code review coordination utilities).
//!
//! The actual coordination logic lives in the `mpcr` library crate (`src/session.rs`, `src/lock.rs`, etc).

use anyhow::Context;
use clap::{Args, Parser, Subcommand, ValueEnum};
use mpcr::id;
use mpcr::lock::{self, LockConfig};
use mpcr::session::{
    append_note, collect_reports, finalize_review, load_session, register_reviewer,
    set_initiator_status, update_review, AppendNoteParams, FinalizeReviewParams, InitiatorStatus,
    NoteRole, NoteType, RegisterReviewerParams, ReportsFilters, ReportsOptions, ReportsView,
    ReviewPhase, ReviewVerdict, ReviewerStatus, SessionLocator, SetInitiatorStatusParams,
    SeverityCounts, UpdateReviewParams,
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
Use `--json` for machine-readable output.\n\
Without `--json`, structured results are printed as one-line JSON and successful mutations print `ok`.",
    after_long_help = r#"Session directory layout (relative to repo root):
  .local/reports/code_reviews/YYYY-MM-DD/
    _session.json
    _session.json.lock
    {HH-MM-SS-mmm}_{ref}_{reviewer_id}.md

Environment variables (optional):
  MPCR_REPO_ROOT    Repo root used for default session dir (no auto-detection; default: cwd)
  MPCR_DATE         Session date (YYYY-MM-DD) used for default session dir (default: today in UTC)
  MPCR_SESSION_DIR  Explicit session directory containing `_session.json`
  MPCR_REVIEWER_ID  Stable reviewer identity (id8) for this executor
  MPCR_SESSION_ID   Current session id (id8) for reviewer/applicator commands
  MPCR_TARGET_REF   Current target_ref (used by `applicator wait`)

Common flows:
  # Reviewer (recommended; POSIX shell)
  eval "$(mpcr reviewer register --target-ref main --emit-env sh)"
  mpcr reviewer update --status IN_PROGRESS --phase INGESTION
  mpcr reviewer finalize --verdict APPROVE --blocker 0 --major 0 --minor 0 --nit 0 <<'EOF'
  ## Adversarial Code Review: main
  ...
  EOF

  # Reviewer (explicit flags; no env)
  mpcr reviewer register --target-ref main --reviewer-id <id8>
  mpcr reviewer update --session-dir .local/reports/code_reviews/YYYY-MM-DD --reviewer-id <id8> --session-id <id8> --status IN_PROGRESS --phase INGESTION

  # Applicator
  mpcr applicator wait --session-dir .local/reports/code_reviews/YYYY-MM-DD
  mpcr applicator set-status --session-dir .local/reports/code_reviews/YYYY-MM-DD --reviewer-id <id8> --session-id <id8> --initiator-status RECEIVED
"#
)]
struct Cli {
    #[arg(
        long,
        global = true,
        default_value_t = false,
        help = "Emit pretty JSON (suitable for scripting)."
    )]
    json: bool,
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
  # From repo root (or with MPCR_REPO_ROOT / MPCR_DATE set):
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
  # From repo root (or with MPCR_REPO_ROOT / MPCR_DATE set):
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
  # From repo root (or with MPCR_REPO_ROOT / MPCR_DATE set):
  mpcr session reports open
  mpcr session reports closed --include-report-contents --json

  # Filter examples:
  mpcr session reports open --include-notes --only-with-notes
  mpcr session reports closed --only-with-report --include-report-contents
  mpcr session reports open --reviewer-status IN_PROGRESS,BLOCKED
  mpcr session reports closed --initiator-status RECEIVED --verdict APPROVE

  # Explicit session directory:
  mpcr session reports closed --session-dir .local/reports/code_reviews/YYYY-MM-DD --include-report-contents --json
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
        env = "MPCR_SESSION_DIR",
        value_name = "DIR",
        help = "Session directory containing `_session.json` (default: <repo_root>/.local/reports/code_reviews/<date>)."
    )]
    session_dir: Option<PathBuf>,
    #[arg(
        long,
        env = "MPCR_REPO_ROOT",
        value_name = "DIR",
        help = "Repo root used to compute the default session dir (default: cwd; not auto-detected—set when running from a subdir)."
    )]
    repo_root: Option<PathBuf>,
    #[arg(
        long,
        env = "MPCR_DATE",
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
    #[arg(
        long,
        help = "Only include reviews that already have a report file."
    )]
    only_with_report: bool,
    #[arg(
        long,
        help = "Only include reviews that contain at least one note (implies --include-notes)."
    )]
    only_with_notes: bool,
    #[arg(
        long,
        help = "Include full notes for each review entry."
    )]
    include_notes: bool,
    #[arg(
        long,
        alias = "include-report",
        help = "Include report markdown contents for each review entry (if available)."
    )]
    include_report_contents: bool,
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

  # Recommended: capture deterministic context into env vars (POSIX shell):
  eval "$(mpcr reviewer register --target-ref main --emit-env sh)"

  # Use a stable reviewer_id (recommended when reviewing multiple target refs):
  export MPCR_REVIEWER_ID="<id8>"
  eval "$(mpcr reviewer register --target-ref main --emit-env sh)"

  # Worktree / uncommitted review (no commit yet):
  eval "$(mpcr reviewer register --target-ref 'worktree:feature/foo (uncommitted)' --emit-env sh)"

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
            env = "MPCR_REVIEWER_ID",
            value_name = "ID8",
            help = "8-character ASCII alphanumeric reviewer identifier (default: random; set MPCR_REVIEWER_ID to reuse identity across reviews)."
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
            help = "Optional parent reviewer id for handoff/chaining (8-character ASCII alphanumeric)."
        )]
        parent_id: Option<String>,

        #[arg(
            long,
            value_enum,
            value_name = "FORMAT",
            help = "Emit environment exports for reuse in later commands (e.g., `eval \"$(mpcr reviewer register ... --emit-env sh)\"`)."
        )]
        emit_env: Option<EmitEnvFormat>,
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
  # If you used `--emit-env sh` earlier, you can omit repeated flags:
  mpcr reviewer update --status IN_PROGRESS --phase INGESTION

  mpcr reviewer update --session-dir .local/reports/code_reviews/YYYY-MM-DD --reviewer-id <id8> --session-id <id8> --status IN_PROGRESS --phase INGESTION
  mpcr reviewer update --session-dir .local/reports/code_reviews/YYYY-MM-DD --reviewer-id <id8> --session-id <id8> --clear-phase
"#)]
    Update {
        #[command(flatten)]
        session: SessionDirArgs,
        #[arg(
            long,
            env = "MPCR_REVIEWER_ID",
            value_name = "ID8",
            help = "Your reviewer_id (8-character ASCII alphanumeric)."
        )]
        reviewer_id: String,
        #[arg(
            long,
            env = "MPCR_SESSION_ID",
            value_name = "ID8",
            help = "Session id (8-character ASCII alphanumeric)."
        )]
        session_id: String,
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
  - Use `--report-file <path>` to read markdown from a file
  - Or omit it and pipe markdown via stdin

Examples:
  # If you used `--emit-env sh` earlier, you can omit repeated flags:
  mpcr reviewer finalize --verdict APPROVE --blocker 0 --major 0 --minor 0 --nit 0 <<'EOF'
  ## Adversarial Code Review: <ref>
  ...
  EOF

  mpcr reviewer finalize --session-dir .local/reports/code_reviews/YYYY-MM-DD --reviewer-id <id8> --session-id <id8> --verdict APPROVE --report-file review.md
  cat review.md | mpcr reviewer finalize --session-dir .local/reports/code_reviews/YYYY-MM-DD --reviewer-id <id8> --session-id <id8> --verdict REQUEST_CHANGES --major 2
"#)]
    Finalize {
        #[command(flatten)]
        session: SessionDirArgs,
        #[arg(
            long,
            env = "MPCR_REVIEWER_ID",
            value_name = "ID8",
            help = "Your reviewer_id (8-character ASCII alphanumeric)."
        )]
        reviewer_id: String,
        #[arg(
            long,
            env = "MPCR_SESSION_ID",
            value_name = "ID8",
            help = "Session id (8-character ASCII alphanumeric)."
        )]
        session_id: String,
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
            help = "Read report markdown from this file (if omitted, reads from stdin)."
        )]
        report_file: Option<PathBuf>,
    },

    /// Append a reviewer note to the session entry.
    #[command(after_long_help = r#"Note content:
  - By default, `--content` is stored as a JSON string.
  - With `--content-json`, `--content` must be valid JSON (object/array/string/number/etc).

Examples:
  # If you used `--emit-env sh` earlier, you can omit repeated flags:
  mpcr reviewer note --note-type question --content \"Can you clarify X?\"

  mpcr reviewer note --session-dir .local/reports/code_reviews/YYYY-MM-DD --reviewer-id <id8> --session-id <id8> --note-type question --content \"Can you clarify X?\"
  mpcr reviewer note --session-dir .local/reports/code_reviews/YYYY-MM-DD --reviewer-id <id8> --session-id <id8> --note-type domain_observation --content-json --content '{\"domain\":\"security\",\"note\":\"...\"}'
"#)]
    Note {
        #[command(flatten)]
        session: SessionDirArgs,
        #[arg(
            long,
            env = "MPCR_REVIEWER_ID",
            value_name = "ID8",
            help = "Your reviewer_id (8-character ASCII alphanumeric)."
        )]
        reviewer_id: String,
        #[arg(
            long,
            env = "MPCR_SESSION_ID",
            value_name = "ID8",
            help = "Session id (8-character ASCII alphanumeric)."
        )]
        session_id: String,
        #[arg(
            long,
            alias = "type",
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
  # If MPCR_SESSION_DIR / MPCR_SESSION_ID / MPCR_REVIEWER_ID are set:
  mpcr applicator set-status --initiator-status RECEIVED

  mpcr applicator set-status --session-dir .local/reports/code_reviews/YYYY-MM-DD --reviewer-id <id8> --session-id <id8> --initiator-status RECEIVED
"#)]
    SetStatus {
        #[command(flatten)]
        session: SessionDirArgs,
        #[arg(
            long,
            env = "MPCR_REVIEWER_ID",
            value_name = "ID8",
            help = "Reviewer id for the entry you are updating (8-character ASCII alphanumeric)."
        )]
        reviewer_id: String,
        #[arg(
            long,
            env = "MPCR_SESSION_ID",
            value_name = "ID8",
            help = "Session id for the entry you are updating (8-character ASCII alphanumeric)."
        )]
        session_id: String,
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
  # If MPCR_SESSION_DIR / MPCR_SESSION_ID / MPCR_REVIEWER_ID are set:
  mpcr applicator note --note-type applied --content \"Fixed in commit abc123\"

  mpcr applicator note --session-dir .local/reports/code_reviews/YYYY-MM-DD --reviewer-id <id8> --session-id <id8> --note-type applied --content \"Fixed in commit abc123\"
"#)]
    Note {
        #[command(flatten)]
        session: SessionDirArgs,
        #[arg(
            long,
            env = "MPCR_REVIEWER_ID",
            value_name = "ID8",
            help = "Reviewer id for the entry you are updating (8-character ASCII alphanumeric)."
        )]
        reviewer_id: String,
        #[arg(
            long,
            env = "MPCR_SESSION_ID",
            value_name = "ID8",
            help = "Session id for the entry you are updating (8-character ASCII alphanumeric)."
        )]
        session_id: String,
        #[arg(
            long,
            alias = "type",
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
  # Wait for *all* reviews in the session dir:
  mpcr applicator wait --session-dir .local/reports/code_reviews/YYYY-MM-DD

  # Wait for a specific target/session id:
  mpcr applicator wait --session-dir .local/reports/code_reviews/YYYY-MM-DD --target-ref main --session-id <id8>
"#)]
    Wait {
        #[command(flatten)]
        session: SessionDirArgs,
        #[arg(
            long,
            env = "MPCR_TARGET_REF",
            value_name = "REF",
            help = "If set, only wait for reviews matching this target_ref."
        )]
        target_ref: Option<String>,
        #[arg(
            long,
            env = "MPCR_SESSION_ID",
            value_name = "ID8",
            help = "If set, only wait for reviews matching this session_id."
        )]
        session_id: Option<String>,
    },
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
    let now = OffsetDateTime::now_utc();

    match cli.command {
        Commands::Id { command } => match command {
            IdCommands::Id8 => {
                let out = id::random_id8()?;
                if cli.json {
                    write_json(&out)?;
                } else {
                    println!("{out}");
                }
            }
            IdCommands::Hex { bytes } => {
                let out = id::random_hex_id(bytes)?;
                if cli.json {
                    write_json(&out)?;
                } else {
                    println!("{out}");
                }
            }
        },

        Commands::Lock { command } => match command {
            LockCommands::Acquire { session, owner, max_retries } => {
                let resolved = resolve_session_input(&session, now.date())?;
                let cfg = LockConfig { max_retries };
                let guard = lock::acquire_lock(&resolved.session_dir, owner, cfg)?;
                std::mem::forget(guard);
                write_ok(cli.json)?;
            }
            LockCommands::Release { session, owner } => {
                let resolved = resolve_session_input(&session, now.date())?;
                lock::release_lock(&resolved.session_dir, owner)?;
                write_ok(cli.json)?;
            }
        },

        Commands::Session { command } => match command {
            SessionCommands::Show { session } => {
                let resolved = resolve_session_input(&session, now.date())?;
                let session = load_session(&SessionLocator::new(resolved.session_dir))?;
                write_result(cli.json, &session)?;
            }
            SessionCommands::Reports { command } => match command {
                ReportsCommands::Open(args) => {
                    handle_reports(cli.json, now.date(), ReportsView::Open, args)?;
                }
                ReportsCommands::Closed(args) => {
                    handle_reports(cli.json, now.date(), ReportsView::Closed, args)?;
                }
                ReportsCommands::InProgress(args) => {
                    handle_reports(cli.json, now.date(), ReportsView::InProgress, args)?;
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
            } => {
                let target_ref_for_env = target_ref.clone();
                let resolved = resolve_session_input(&session, now.date())?;
                let session = SessionLocator::new(resolved.session_dir);

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
                match emit_env {
                    Some(EmitEnvFormat::Sh) => write_env_sh(&[
                        ("MPCR_REVIEWER_ID", res.reviewer_id.as_str()),
                        ("MPCR_SESSION_ID", res.session_id.as_str()),
                        ("MPCR_SESSION_DIR", res.session_dir.as_str()),
                        ("MPCR_SESSION_FILE", res.session_file.as_str()),
                        ("MPCR_TARGET_REF", target_ref_for_env.as_str()),
                    ])?,
                    None => write_result(cli.json, &res)?,
                }
            }

            ReviewerCommands::Update {
                session,
                reviewer_id,
                session_id,
                status,
                phase,
                clear_phase,
            } => {
                let resolved = resolve_session_input(&session, now.date())?;
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
                write_ok(cli.json)?;
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
            } => {
                let report_markdown = match report_file {
                    Some(p) => std::fs::read_to_string(&p)
                        .with_context(|| format!("read report file {}", p.display()))?,
                    None => read_stdin_to_string().context("read report markdown from stdin")?,
                };

                let resolved = resolve_session_input(&session, now.date())?;
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
                    report_markdown,
                    now,
                })?;
                write_result(cli.json, &res)?;
            }

            ReviewerCommands::Note {
                session,
                reviewer_id,
                session_id,
                note_type,
                content,
                content_json,
            } => {
                let resolved = resolve_session_input(&session, now.date())?;
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
                write_ok(cli.json)?;
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
                let resolved = resolve_session_input(&session, now.date())?;
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
                write_ok(cli.json)?;
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
                let resolved = resolve_session_input(&session, now.date())?;
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
                write_ok(cli.json)?;
            }

            ApplicatorCommands::Wait {
                session,
                target_ref,
                session_id,
            } => {
                let resolved = resolve_session_input(&session, now.date())?;
                wait_for_reviews(
                    &resolved.session_dir,
                    target_ref.as_deref(),
                    session_id.as_deref(),
                )?;
                write_ok(cli.json)?;
            }
        },
    }

    Ok(())
}

fn resolve_session_input(
    args: &SessionDirArgs,
    default_date: Date,
) -> anyhow::Result<ResolvedSessionInput> {
    let repo_root = match args.repo_root.as_ref() {
        Some(repo_root) => repo_root.clone(),
        None => std::env::current_dir().context("get cwd")?,
    };
    let session_date = match args.date.as_deref() {
        Some(date) => parse_date_ymd(date)?,
        None => default_date,
    };
    let session_dir = args.session_dir.as_ref().map_or_else(
        || mpcr::paths::session_paths(&repo_root, session_date).session_dir,
        std::clone::Clone::clone,
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

fn write_ok(json: bool) -> anyhow::Result<()> {
    if json {
        write_result(true, &OkResult { ok: true })
    } else {
        println!("ok");
        Ok(())
    }
}

fn write_json<T: Serialize>(value: &T) -> anyhow::Result<()> {
    let mut stdout = std::io::stdout();
    let raw = serde_json::to_string_pretty(value).context("serialize JSON")?;
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

fn write_result<T: Serialize>(json: bool, value: &T) -> anyhow::Result<()> {
    if json {
        write_json(value)
    } else {
        // human output: best-effort JSON on one line.
        println!("{}", serde_json::to_string(value).context("serialize")?);
        Ok(())
    }
}

fn handle_reports(
    json: bool,
    default_date: Date,
    view: ReportsView,
    args: ReportsArgs,
) -> anyhow::Result<()> {
    let resolved = resolve_session_input(&args.session, default_date)?;
    let session = SessionLocator::new(resolved.session_dir);
    let session_data = load_session(&session)?;
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
    };
    let result = collect_reports(&session_data, &session, view, filters, options);
    write_result(json, &result)
}

fn wait_for_reviews(
    session_dir: &Path,
    target_ref: Option<&str>,
    session_id: Option<&str>,
) -> anyhow::Result<()> {
    let mut delay = std::time::Duration::from_secs(1);
    let max_delay = std::time::Duration::from_secs(60);
    let session = SessionLocator::new(session_dir.to_path_buf());

    loop {
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
    use mpcr::session::{InitiatorStatus, ReviewEntry, ReviewVerdict, ReviewerStatus, SessionFile, SeverityCounts};
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
        };
        let session = SessionFile {
            schema_version: "1.0.0".to_string(),
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
        let resolved = resolve_session_input(&args, fallback)?;
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
        let resolved = resolve_session_input(&args, Date::from_calendar_date(2026, Month::January, 12)?)?;
        let expected = paths::session_paths(repo_root.path(), Date::from_calendar_date(2026, Month::January, 11)?);
        ensure!(resolved.session_dir == expected.session_dir);
        Ok(())
    }
}
