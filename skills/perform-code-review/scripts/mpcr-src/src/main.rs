#![allow(clippy::print_stderr, clippy::print_stdout)]

use anyhow::Context;
use clap::{Parser, Subcommand};
use mpcr::id;
use mpcr::lock::{self, LockConfig};
use mpcr::session::{
    append_note, finalize_review, load_session, register_reviewer, set_initiator_status,
    update_review, AppendNoteParams, FinalizeReviewParams, InitiatorStatus, NoteRole, NoteType,
    RegisterReviewerParams, ReviewPhase, ReviewVerdict, ReviewerStatus, SessionLocator,
    SetInitiatorStatusParams, SeverityCounts, UpdateReviewParams,
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
    about = "UACRP code review coordination utilities"
)]
struct Cli {
    #[arg(long, global = true, default_value_t = false)]
    json: bool,
    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand)]
enum Commands {
    Id {
        #[command(subcommand)]
        command: IdCommands,
    },
    Lock {
        #[command(subcommand)]
        command: LockCommands,
    },
    Session {
        #[command(subcommand)]
        command: SessionCommands,
    },
    Reviewer {
        #[command(subcommand)]
        command: ReviewerCommands,
    },
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
        #[arg(long)]
        bytes: usize,
    },
}

#[derive(Subcommand)]
enum LockCommands {
    Acquire {
        #[arg(long)]
        session_dir: PathBuf,
        #[arg(long)]
        owner: String,
        #[arg(long, default_value_t = 8)]
        max_retries: usize,
    },
    Release {
        #[arg(long)]
        session_dir: PathBuf,
        #[arg(long)]
        owner: String,
    },
}

#[derive(Subcommand)]
enum SessionCommands {
    Show {
        #[arg(long)]
        session_dir: PathBuf,
    },
}

#[derive(Subcommand)]
enum ReviewerCommands {
    Register {
        #[arg(long)]
        target_ref: String,

        #[arg(long)]
        session_dir: Option<PathBuf>,
        #[arg(long)]
        repo_root: Option<PathBuf>,
        #[arg(long)]
        date: Option<String>,

        #[arg(long)]
        reviewer_id: Option<String>,
        #[arg(long)]
        session_id: Option<String>,
        #[arg(long)]
        parent_id: Option<String>,
    },

    Update {
        #[arg(long)]
        session_dir: PathBuf,
        #[arg(long)]
        reviewer_id: String,
        #[arg(long)]
        session_id: String,
        #[arg(long)]
        status: Option<ReviewerStatus>,
        #[arg(long)]
        phase: Option<ReviewPhase>,
        #[arg(long)]
        clear_phase: bool,
    },

    Finalize {
        #[arg(long)]
        session_dir: PathBuf,
        #[arg(long)]
        reviewer_id: String,
        #[arg(long)]
        session_id: String,
        #[arg(long)]
        verdict: ReviewVerdict,
        #[arg(long, default_value_t = 0)]
        blocker: u64,
        #[arg(long, default_value_t = 0)]
        major: u64,
        #[arg(long, default_value_t = 0)]
        minor: u64,
        #[arg(long, default_value_t = 0)]
        nit: u64,
        #[arg(long)]
        report_file: Option<PathBuf>,
    },

    Note {
        #[arg(long)]
        session_dir: PathBuf,
        #[arg(long)]
        reviewer_id: String,
        #[arg(long)]
        session_id: String,
        #[arg(long)]
        note_type: NoteType,
        #[arg(long)]
        content: String,
        #[arg(long)]
        content_json: bool,
    },
}

#[derive(Subcommand)]
enum ApplicatorCommands {
    SetStatus {
        #[arg(long)]
        session_dir: PathBuf,
        #[arg(long)]
        reviewer_id: String,
        #[arg(long)]
        session_id: String,
        #[arg(long)]
        initiator_status: InitiatorStatus,
        #[arg(long)]
        lock_owner: Option<String>,
    },

    Note {
        #[arg(long)]
        session_dir: PathBuf,
        #[arg(long)]
        reviewer_id: String,
        #[arg(long)]
        session_id: String,
        #[arg(long)]
        note_type: NoteType,
        #[arg(long)]
        content: String,
        #[arg(long)]
        content_json: bool,
        #[arg(long)]
        lock_owner: Option<String>,
    },

    Wait {
        #[arg(long)]
        session_dir: PathBuf,
        #[arg(long)]
        target_ref: Option<String>,
        #[arg(long)]
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

                let session = resolve_session_locator(&repo_root, session_date, session_dir)?;

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
                update_review(UpdateReviewParams {
                    session: SessionLocator::new(session_dir),
                    reviewer_id,
                    session_id,
                    status,
                    phase,
                    now,
                })?;
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
                set_initiator_status(SetInitiatorStatusParams {
                    session: SessionLocator::new(session_dir),
                    reviewer_id,
                    session_id,
                    initiator_status,
                    now,
                    lock_owner,
                })?;
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
                wait_for_reviews(session_dir, target_ref, session_id)?;
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
) -> anyhow::Result<SessionLocator> {
    Ok(match override_dir {
        Some(dir) => SessionLocator::new(dir),
        None => SessionLocator::from_repo_root(repo_root, session_date),
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

fn write_result<T: Serialize>(json: bool, value: &T) -> anyhow::Result<()> {
    if json {
        write_json(value)
    } else {
        // human output: best-effort JSON on one line.
        println!("{}", serde_json::to_string(value).context("serialize")?);
        Ok(())
    }
}

fn wait_for_reviews(
    session_dir: PathBuf,
    target_ref: Option<String>,
    session_id: Option<String>,
) -> anyhow::Result<()> {
    let mut delay = std::time::Duration::from_secs(1);
    let max_delay = std::time::Duration::from_secs(60);

    loop {
        let session = load_session(&SessionLocator::new(session_dir.clone()))
            .with_context(|| format!("read session file under {}", session_dir.display()))?;

        let mut has_pending = false;
        for r in session.reviews {
            if let Some(ref tr) = target_ref {
                if &r.target_ref != tr {
                    continue;
                }
            }
            if let Some(ref sid) = session_id {
                if &r.session_id != sid {
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
