#![allow(clippy::print_stderr, clippy::print_stdout)]

//! CLI entrypoint for `mpcr` (UACRP code review coordination utilities).
//!
//! The actual coordination logic lives in the `mpcr` library crate (`src/session.rs`, `src/lock.rs`, etc).

use anyhow::Context;
use clap::{Args, Parser, Subcommand};
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

Common flows:
  # Reviewer
  mpcr reviewer register --target-ref main
  mpcr reviewer update --session-dir .local/reports/code_reviews/YYYY-MM-DD --reviewer-id <id8> --session-id <id8> --status IN_PROGRESS --phase INGESTION
  mpcr reviewer finalize --session-dir .local/reports/code_reviews/YYYY-MM-DD --reviewer-id <id8> --session-id <id8> --verdict APPROVE --report-file review.md

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
    /// Generate deterministic IDs (`reviewer_id`, `session_id`, lock owners).
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
    #[command(after_long_help = r#"Example:
  mpcr lock acquire --session-dir .local/reports/code_reviews/YYYY-MM-DD --owner <id8>
"#)]
    Acquire {
        #[arg(
            long,
            value_name = "DIR",
            help = "Session directory containing `_session.json`."
        )]
        session_dir: PathBuf,
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
    #[command(after_long_help = r#"Example:
  mpcr lock release --session-dir .local/reports/code_reviews/YYYY-MM-DD --owner <id8>
"#)]
    Release {
        #[arg(
            long,
            value_name = "DIR",
            help = "Session directory containing `_session.json`."
        )]
        session_dir: PathBuf,
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
    #[command(after_long_help = r#"Example:
  mpcr session show --session-dir .local/reports/code_reviews/YYYY-MM-DD
"#)]
    Show {
        #[arg(
            long,
            value_name = "DIR",
            help = "Session directory containing `_session.json`."
        )]
        session_dir: PathBuf,
    },
    /// Report-oriented session views (open/closed/in-progress).
    #[command(after_long_help = r#"Examples:
  mpcr session reports open --session-dir .local/reports/code_reviews/YYYY-MM-DD
  mpcr session reports closed --session-dir .local/reports/code_reviews/YYYY-MM-DD
  mpcr session reports in-progress --session-dir .local/reports/code_reviews/YYYY-MM-DD
  mpcr session reports open --session-dir .local/reports/code_reviews/YYYY-MM-DD --include-notes --only-with-notes
  mpcr session reports closed --session-dir .local/reports/code_reviews/YYYY-MM-DD --only-with-report
  mpcr session reports open --session-dir .local/reports/code_reviews/YYYY-MM-DD --reviewer-status IN_PROGRESS,BLOCKED
  mpcr session reports closed --session-dir .local/reports/code_reviews/YYYY-MM-DD --initiator-status RECEIVED --verdict APPROVE
"#)]
    Reports {
        #[command(subcommand)]
        command: ReportsCommands,
    },
}

#[derive(Args)]
struct ReportsArgs {
    #[arg(
        long,
        value_name = "DIR",
        help = "Session directory containing `_session.json`."
    )]
    session_dir: PathBuf,
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

        #[arg(
            long,
            value_name = "DIR",
            help = "Override the session directory (otherwise computed from repo_root + date)."
        )]
        session_dir: Option<PathBuf>,
        #[arg(
            long,
            value_name = "DIR",
            help = "Repository root used to compute the default session directory (defaults to cwd)."
        )]
        repo_root: Option<PathBuf>,
        #[arg(
            long,
            value_name = "YYYY-MM-DD",
            help = "Session date used to compute the default session directory (defaults to today, UTC)."
        )]
        date: Option<String>,

        #[arg(
            long,
            value_name = "ID8",
            help = "8-character ASCII alphanumeric reviewer identifier (default: random)."
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
  mpcr reviewer update --session-dir .local/reports/code_reviews/YYYY-MM-DD --reviewer-id <id8> --session-id <id8> --status IN_PROGRESS --phase INGESTION
  mpcr reviewer update --session-dir .local/reports/code_reviews/YYYY-MM-DD --reviewer-id <id8> --session-id <id8> --clear-phase
"#)]
    Update {
        #[arg(
            long,
            value_name = "DIR",
            help = "Session directory containing `_session.json`."
        )]
        session_dir: PathBuf,
        #[arg(
            long,
            value_name = "ID8",
            help = "Your reviewer_id (8-character ASCII alphanumeric)."
        )]
        reviewer_id: String,
        #[arg(
            long,
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
  mpcr reviewer finalize --session-dir .local/reports/code_reviews/YYYY-MM-DD --reviewer-id <id8> --session-id <id8> --verdict APPROVE --report-file review.md
  cat review.md | mpcr reviewer finalize --session-dir .local/reports/code_reviews/YYYY-MM-DD --reviewer-id <id8> --session-id <id8> --verdict REQUEST_CHANGES --major 2
"#)]
    Finalize {
        #[arg(
            long,
            value_name = "DIR",
            help = "Session directory containing `_session.json` and where the report file will be written."
        )]
        session_dir: PathBuf,
        #[arg(
            long,
            value_name = "ID8",
            help = "Your reviewer_id (8-character ASCII alphanumeric)."
        )]
        reviewer_id: String,
        #[arg(
            long,
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
  mpcr reviewer note --session-dir .local/reports/code_reviews/YYYY-MM-DD --reviewer-id <id8> --session-id <id8> --note-type question --content \"Can you clarify X?\"
  mpcr reviewer note --session-dir .local/reports/code_reviews/YYYY-MM-DD --reviewer-id <id8> --session-id <id8> --note-type domain_observation --content-json --content '{\"domain\":\"security\",\"note\":\"...\"}'
"#)]
    Note {
        #[arg(
            long,
            value_name = "DIR",
            help = "Session directory containing `_session.json`."
        )]
        session_dir: PathBuf,
        #[arg(
            long,
            value_name = "ID8",
            help = "Your reviewer_id (8-character ASCII alphanumeric)."
        )]
        reviewer_id: String,
        #[arg(
            long,
            value_name = "ID8",
            help = "Session id (8-character ASCII alphanumeric)."
        )]
        session_id: String,
        #[arg(
            long,
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
  mpcr applicator set-status --session-dir .local/reports/code_reviews/YYYY-MM-DD --reviewer-id <id8> --session-id <id8> --initiator-status RECEIVED
"#)]
    SetStatus {
        #[arg(
            long,
            value_name = "DIR",
            help = "Session directory containing `_session.json`."
        )]
        session_dir: PathBuf,
        #[arg(
            long,
            value_name = "ID8",
            help = "Reviewer id for the entry you are updating (8-character ASCII alphanumeric)."
        )]
        reviewer_id: String,
        #[arg(
            long,
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
  mpcr applicator note --session-dir .local/reports/code_reviews/YYYY-MM-DD --reviewer-id <id8> --session-id <id8> --note-type applied --content \"Fixed in commit abc123\"
"#)]
    Note {
        #[arg(
            long,
            value_name = "DIR",
            help = "Session directory containing `_session.json`."
        )]
        session_dir: PathBuf,
        #[arg(
            long,
            value_name = "ID8",
            help = "Reviewer id for the entry you are updating (8-character ASCII alphanumeric)."
        )]
        reviewer_id: String,
        #[arg(
            long,
            value_name = "ID8",
            help = "Session id for the entry you are updating (8-character ASCII alphanumeric)."
        )]
        session_id: String,
        #[arg(
            long,
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
        #[arg(
            long,
            value_name = "DIR",
            help = "Session directory containing `_session.json`."
        )]
        session_dir: PathBuf,
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
            LockCommands::Acquire {
                session_dir,
                owner,
                max_retries,
            } => {
                let cfg = LockConfig { max_retries };
                let guard = lock::acquire_lock(&session_dir, owner, cfg)?;
                std::mem::forget(guard);
                write_ok(cli.json)?;
            }
            LockCommands::Release { session_dir, owner } => {
                lock::release_lock(&session_dir, owner)?;
                write_ok(cli.json)?;
            }
        },

        Commands::Session { command } => match command {
            SessionCommands::Show { session_dir } => {
                let session = load_session(&SessionLocator::new(session_dir))?;
                write_result(cli.json, &session)?;
            }
            SessionCommands::Reports { command } => match command {
                ReportsCommands::Open(args) => handle_reports(cli.json, ReportsView::Open, args)?,
                ReportsCommands::Closed(args) => {
                    handle_reports(cli.json, ReportsView::Closed, args)?;
                }
                ReportsCommands::InProgress(args) => {
                    handle_reports(cli.json, ReportsView::InProgress, args)?;
                }
            },
        },

        Commands::Reviewer { command } => match command {
            ReviewerCommands::Register {
                target_ref,
                session_dir,
                repo_root,
                date,
                reviewer_id,
                session_id,
                parent_id,
            } => {
                let repo_root = match repo_root {
                    Some(repo_root) => repo_root,
                    None => std::env::current_dir().context("get cwd")?,
                };
                let session_date = match date.as_deref() {
                    Some(d) => parse_date_ymd(d)?,
                    None => now.date(),
                };

                let session = resolve_session_locator(&repo_root, session_date, session_dir);

                let res = register_reviewer(RegisterReviewerParams {
                    repo_root,
                    session_date,
                    session,
                    target_ref,
                    reviewer_id,
                    session_id,
                    parent_id,
                    now,
                })?;
                write_result(cli.json, &res)?;
            }

            ReviewerCommands::Update {
                session_dir,
                reviewer_id,
                session_id,
                status,
                phase,
                clear_phase,
            } => {
                let phase = if clear_phase {
                    Some(None)
                } else {
                    phase.map(Some)
                };
                let params = UpdateReviewParams {
                    session: SessionLocator::new(session_dir),
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
                session_dir,
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

                let res = finalize_review(FinalizeReviewParams {
                    session: SessionLocator::new(session_dir),
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
                session_dir,
                reviewer_id,
                session_id,
                note_type,
                content,
                content_json,
            } => {
                let content = parse_content(content_json, &content)?;
                append_note(AppendNoteParams {
                    session: SessionLocator::new(session_dir),
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
                session_dir,
                reviewer_id,
                session_id,
                initiator_status,
                lock_owner,
            } => {
                let lock_owner = match lock_owner {
                    Some(lock_owner) => lock_owner,
                    None => id::random_id8()?,
                };
                let params = SetInitiatorStatusParams {
                    session: SessionLocator::new(session_dir),
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
                session_dir,
                reviewer_id,
                session_id,
                note_type,
                content,
                content_json,
                lock_owner,
            } => {
                let content = parse_content(content_json, &content)?;
                let lock_owner = match lock_owner {
                    Some(lock_owner) => lock_owner,
                    None => id::random_id8()?,
                };
                append_note(AppendNoteParams {
                    session: SessionLocator::new(session_dir),
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
                session_dir,
                target_ref,
                session_id,
            } => {
                wait_for_reviews(&session_dir, target_ref.as_deref(), session_id.as_deref())?;
                write_ok(cli.json)?;
            }
        },
    }

    Ok(())
}

fn resolve_session_locator(
    repo_root: &Path,
    session_date: Date,
    override_dir: Option<PathBuf>,
) -> SessionLocator {
    override_dir.map_or_else(
        || SessionLocator::from_repo_root(repo_root, session_date),
        SessionLocator::new,
    )
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

fn write_result<T: Serialize>(json: bool, value: &T) -> anyhow::Result<()> {
    if json {
        write_json(value)
    } else {
        // human output: best-effort JSON on one line.
        println!("{}", serde_json::to_string(value).context("serialize")?);
        Ok(())
    }
}

fn handle_reports(json: bool, view: ReportsView, args: ReportsArgs) -> anyhow::Result<()> {
    let session = SessionLocator::new(args.session_dir);
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
    use mpcr::session::{InitiatorStatus, ReviewEntry, ReviewVerdict, ReviewerStatus, SessionFile, SeverityCounts};
    use std::fs;

    #[test]
    fn parse_date_ymd_valid_and_invalid() -> anyhow::Result<()> {
        let date = parse_date_ymd("2026-01-11")?;
        assert_eq!(date.to_string(), "2026-01-11");
        assert!(parse_date_ymd("2026-13-01").is_err());
        assert!(parse_date_ymd("not-a-date").is_err());
        Ok(())
    }

    #[test]
    fn parse_content_json_and_string() -> anyhow::Result<()> {
        let value = parse_content(true, r#"{"key":1}"#)?;
        assert_eq!(value["key"], 1);
        let raw = parse_content(false, "hello")?;
        assert_eq!(raw, serde_json::Value::String("hello".to_string()));
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
}
