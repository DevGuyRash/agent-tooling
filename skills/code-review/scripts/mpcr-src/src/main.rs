#![allow(
    clippy::all,
    clippy::pedantic,
    clippy::nursery,
    clippy::cargo,
    clippy::print_stderr,
    clippy::print_stdout
)]

//! CLI entrypoint for the v2 `mpcr` code-review tool.

use anyhow::Context;
use clap::{Args, Parser, Subcommand, ValueEnum};
use mpcr::analyze;
use mpcr::artifacts::{
    now_rfc3339, parse_artifact_file, ArtifactDocument, ArtifactHeader, ArtifactKind,
    ConfidenceLabel, ExecutionCapability, Mode, PolicyCategory, PolicyRef, PolicyView,
    ProducerKind, POLICY_BUNDLE_VERSION,
};
use mpcr::fullcycle_plan;
use mpcr::id;
use mpcr::lock::{self, LockConfig};
use mpcr::paths;
use mpcr::protocol;
use mpcr::render::render_artifact_markdown;
use mpcr::router::{build_route_decision, build_surface_map, default_router_policy_refs};
use mpcr::router_types::RouteInputs;
use mpcr::session::{
    append_applicator_note, append_reviewer_note, applicator_wait, apply_route_revision_artifact,
    checkpoint_convergence_state, cleanup_session, close_child_reviews, collect_reports,
    complete_child_review, ensure_session, finalize_application, finalize_review, list_artifacts,
    load_session, persist_route_artifacts, register_reviewer, set_applicator_status,
    spawn_child_reviewers, update_review, AppendApplicatorNoteParams, AppendReviewerNoteParams,
    ApplicatorArtifactParams, ApplicatorStatus, ApplyRouteRevisionParams, CloseChildReviewsParams,
    PersistRouteArtifactsParams, RegisterReviewerParams, ReportView, ReportsResult,
    ReviewProcessStatus, ReviewerArtifactParams, SessionLocator, SetApplicatorStatusParams,
    SpawnChildReviewersParams, UpdateReviewParams,
};
use mpcr::validate::{validate_artifact_file, ValidationLayer};
use serde::Serialize;
use std::collections::HashMap;
use std::fs;
use std::path::PathBuf;
use time::format_description;
use time::{Date, OffsetDateTime};

#[derive(Parser)]
#[command(
    name = "mpcr",
    version,
    about = "Machine-first code review coordination utilities"
)]
struct Cli {
    #[arg(long, global = true, default_value_t = false)]
    json: bool,
    #[arg(long, global = true, default_value_t = false)]
    json_pretty: bool,
    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand)]
enum Commands {
    Route(RouteArgs),
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
    Protocol {
        #[command(subcommand)]
        command: ProtocolCommands,
    },
    Render(RenderArgs),
    Validate(ValidateArgs),
    Fullcycle {
        #[command(subcommand)]
        command: FullcycleCommands,
    },
    Analyze {
        #[command(subcommand)]
        command: AnalyzeCommands,
    },
}

#[derive(Subcommand)]
enum IdCommands {
    Id8,
    Hex {
        #[arg(long)]
        bytes: usize,
    },
}

#[derive(Subcommand)]
enum LockCommands {
    Acquire {
        #[command(flatten)]
        session: SessionDirArgs,
        #[arg(long)]
        owner: String,
        #[arg(long, default_value_t = 8)]
        max_retries: usize,
    },
    Release {
        #[command(flatten)]
        session: SessionDirArgs,
        #[arg(long)]
        owner: String,
    },
}

#[derive(Subcommand)]
enum SessionCommands {
    Show {
        #[command(flatten)]
        session: SessionDirArgs,
    },
    Reports {
        #[command(flatten)]
        session: SessionDirArgs,
        #[arg(long, value_enum, default_value_t = ReportView::All)]
        view: ReportView,
        #[arg(long, default_value_t = false)]
        recursive: bool,
        #[arg(long, default_value_t = false)]
        include_report_contents: bool,
        #[arg(long, default_value_t = false)]
        include_leaf_children: bool,
        #[arg(long, default_value_t = false)]
        concatenate: bool,
    },
    Artifacts {
        #[command(flatten)]
        session: SessionDirArgs,
        #[arg(long)]
        kind: Option<ArtifactKind>,
    },
    Cleanup {
        #[command(flatten)]
        session: SessionDirArgs,
    },
    Metrics {
        #[command(flatten)]
        session: SessionDirArgs,
    },
    ApplyRouteRevision {
        #[command(flatten)]
        session: SessionDirArgs,
        #[arg(long)]
        artifact_file: PathBuf,
    },
}

#[derive(Subcommand)]
enum ReviewerCommands {
    Register {
        #[command(flatten)]
        session: SessionDirArgs,
        #[arg(long)]
        target_ref: String,
        #[arg(long)]
        reviewer_id: Option<String>,
    },
    SpawnChildren {
        #[command(flatten)]
        session: SessionDirArgs,
        #[arg(long)]
        parent_id: String,
        #[arg(long)]
        count: u8,
        #[arg(long)]
        role_id: Option<String>,
        #[arg(long, value_enum)]
        worker_kind: Option<mpcr::artifacts::WorkerKind>,
        #[arg(long, value_enum)]
        domain_id: Option<mpcr::artifacts::ModuleId>,
        #[arg(long)]
        language: Option<String>,
        #[arg(long, value_enum)]
        module_id: Vec<mpcr::artifacts::ModuleId>,
        #[arg(long, value_enum)]
        focus_surface: Vec<mpcr::artifacts::SurfaceId>,
        #[arg(long)]
        claimed_scope: Vec<String>,
        #[arg(long)]
        delegated_scope: Vec<String>,
    },
    CloseChildren {
        #[command(flatten)]
        session: SessionDirArgs,
        #[arg(long)]
        parent_id: String,
        #[arg(long, value_enum, default_value_t = ReviewProcessStatus::Cancelled)]
        set_status: ReviewProcessStatus,
    },
    Update {
        #[command(flatten)]
        session: SessionDirArgs,
        #[arg(long)]
        reviewer_id: String,
        #[arg(long, value_enum)]
        status: ReviewProcessStatus,
        #[arg(long)]
        phase: Option<String>,
    },
    Note {
        #[command(flatten)]
        session: SessionDirArgs,
        #[arg(long)]
        reviewer_id: String,
        #[arg(long)]
        content: String,
    },
    CompleteChild {
        #[command(flatten)]
        session: SessionDirArgs,
        #[arg(long)]
        reviewer_id: String,
        #[arg(long)]
        artifact_file: PathBuf,
    },
    Finalize {
        #[command(flatten)]
        session: SessionDirArgs,
        #[arg(long)]
        reviewer_id: String,
        #[arg(long)]
        artifact_file: PathBuf,
    },
}

#[derive(Subcommand)]
enum ApplicatorCommands {
    SetStatus {
        #[command(flatten)]
        session: SessionDirArgs,
        #[arg(long, value_enum)]
        status: ApplicatorStatus,
    },
    Note {
        #[command(flatten)]
        session: SessionDirArgs,
        #[arg(long)]
        content: String,
    },
    Wait {
        #[command(flatten)]
        session: SessionDirArgs,
    },
    Finalize {
        #[command(flatten)]
        session: SessionDirArgs,
        #[arg(long)]
        artifact_file: PathBuf,
    },
    Verify {
        #[command(flatten)]
        session: SessionDirArgs,
        #[arg(long)]
        artifact_file: PathBuf,
    },
}

#[derive(Subcommand)]
enum ProtocolCommands {
    List,
    Mode {
        #[arg(long, value_enum)]
        mode: mpcr::artifacts::Mode,
        #[arg(long, value_enum)]
        view: PolicyView,
    },
    Worker {
        #[arg(long, value_enum)]
        kind: mpcr::artifacts::WorkerKind,
        #[arg(long, value_enum)]
        view: PolicyView,
    },
    Module {
        #[arg(long, value_enum)]
        id: mpcr::artifacts::ModuleId,
        #[arg(long, value_enum)]
        view: PolicyView,
    },
    Escalation {
        #[arg(long, value_enum)]
        id: mpcr::artifacts::EscalationId,
        #[arg(long, value_enum)]
        view: PolicyView,
    },
    Dispatch {
        #[command(flatten)]
        session: SessionDirArgs,
        #[arg(long)]
        reviewer_id: Option<String>,
        #[arg(long)]
        role: String,
        #[arg(long, value_enum, default_value_t = PolicyView::Checklist)]
        view: PolicyView,
    },
}

#[derive(Args)]
struct RenderArgs {
    #[arg(long)]
    artifact_file: PathBuf,
    #[arg(long, value_enum, default_value_t = RenderFormat::Markdown)]
    format: RenderFormat,
    #[arg(long)]
    output: Option<PathBuf>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, ValueEnum)]
enum RenderFormat {
    Markdown,
}

#[derive(Args)]
struct ValidateArgs {
    #[arg(long)]
    artifact_file: PathBuf,
    #[arg(long, value_enum)]
    kind: ArtifactKind,
    #[arg(long, value_enum)]
    layer: ValidationLayer,
    #[arg(long)]
    session_dir: Option<PathBuf>,
}

#[derive(Subcommand)]
enum FullcycleCommands {
    Plan {
        #[command(flatten)]
        session: SessionDirArgs,
        #[arg(long)]
        output: Option<PathBuf>,
    },
    State {
        #[command(flatten)]
        session: SessionDirArgs,
    },
    Checkpoint {
        #[command(flatten)]
        session: SessionDirArgs,
        #[arg(long)]
        artifact_file: PathBuf,
    },
}

#[derive(Subcommand)]
enum AnalyzeCommands {
    ListChecks,
    Run {
        files: Vec<PathBuf>,
    },
    Check {
        #[arg(long)]
        name: String,
        files: Vec<PathBuf>,
    },
}

#[derive(Args, Clone)]
struct SessionDirArgs {
    #[arg(long)]
    session_dir: Option<PathBuf>,
    #[arg(long)]
    repo_root: Option<PathBuf>,
    #[arg(long)]
    date: Option<String>,
}

impl SessionDirArgs {
    fn is_empty(&self) -> bool {
        self.session_dir.is_none() && self.repo_root.is_none() && self.date.is_none()
    }
}

#[derive(Args, Clone)]
struct RouteArgs {
    #[command(flatten)]
    session: SessionDirArgs,
    #[arg(long, value_enum)]
    mode: Mode,
    #[arg(long)]
    target_ref: String,
    #[arg(long, value_enum)]
    execution_capability: ExecutionCapability,
    #[arg(long)]
    max_worker_count: u8,
    #[arg(long)]
    orchestrator_read_budget_lines: u16,
    #[arg(long)]
    orchestrator_read_budget_snippets: u16,
    #[arg(long)]
    changed_file: Vec<String>,
    #[arg(long)]
    public_interface: Vec<String>,
    #[arg(long)]
    behavior_facing_artifact: Vec<String>,
    #[arg(long, default_value_t = false)]
    persist: bool,
}

#[derive(Debug, Clone, Serialize)]
struct RouteCommandOutput {
    surface_map: mpcr::artifacts::SurfaceMapArtifact,
    route_decision: mpcr::artifacts::RouteDecisionArtifact,
    #[serde(skip_serializing_if = "Option::is_none")]
    persisted: Option<mpcr::session::PersistRouteArtifactsResult>,
}

fn date_format() -> anyhow::Result<Vec<time::format_description::FormatItem<'static>>> {
    Ok(format_description::parse("[year]-[month]-[day]")?)
}

fn discover_repo_root() -> anyhow::Result<PathBuf> {
    if let Ok(output) = std::process::Command::new("git")
        .args(["rev-parse", "--show-toplevel"])
        .output()
    {
        if output.status.success() {
            let text = String::from_utf8_lossy(&output.stdout).trim().to_string();
            if !text.is_empty() {
                return Ok(PathBuf::from(text));
            }
        }
    }
    std::env::current_dir().context("resolve current working directory")
}

fn resolve_session_locator(args: &SessionDirArgs) -> anyhow::Result<SessionLocator> {
    if let Some(session_dir) = &args.session_dir {
        return Ok(SessionLocator::from_session_dir(session_dir.clone()));
    }
    let repo_root = match &args.repo_root {
        Some(repo_root) => repo_root.clone(),
        None => discover_repo_root()?,
    };
    let session_date = match &args.date {
        Some(date) => Date::parse(date, &date_format()?)?,
        None => OffsetDateTime::now_utc().date(),
    };
    Ok(SessionLocator::from_session_dir(
        paths::session_paths(&repo_root, session_date).session_dir,
    ))
}

fn emit_json<T: Serialize>(value: &T, pretty: bool) -> anyhow::Result<()> {
    if pretty {
        println!("{}", serde_json::to_string_pretty(value)?);
    } else {
        println!("{}", serde_json::to_string(value)?);
    }
    Ok(())
}

fn emit_text_or_json<T: Serialize>(
    json: bool,
    json_pretty: bool,
    value: &T,
    render_text: impl FnOnce() -> anyhow::Result<String>,
) -> anyhow::Result<()> {
    if json || json_pretty {
        emit_json(value, json_pretty)
    } else {
        println!("{}", render_text()?);
        Ok(())
    }
}

fn read_files(files: &[PathBuf]) -> anyhow::Result<HashMap<String, String>> {
    let mut map = HashMap::new();
    for file in files {
        let body = fs::read_to_string(file).with_context(|| format!("read {}", file.display()))?;
        let key = file.to_string_lossy().into_owned();
        map.insert(key, body);
    }
    Ok(map)
}

fn format_artifact_list(artifacts: &[mpcr::session::ArtifactPointer]) -> String {
    if artifacts.is_empty() {
        return "no artifacts".to_string();
    }
    artifacts
        .iter()
        .map(|artifact| {
            format!(
                "{} {} {}",
                artifact.artifact_kind, artifact.artifact_id, artifact.path
            )
        })
        .collect::<Vec<_>>()
        .join("\n")
}

fn review_status_text(status: ReviewProcessStatus) -> &'static str {
    match status {
        ReviewProcessStatus::Registered => "registered",
        ReviewProcessStatus::InProgress => "in-progress",
        ReviewProcessStatus::Delegating => "delegating",
        ReviewProcessStatus::WaitingOnChildren => "waiting-on-children",
        ReviewProcessStatus::Synthesizing => "synthesizing",
        ReviewProcessStatus::Completed => "completed",
        ReviewProcessStatus::Cancelled => "cancelled",
        ReviewProcessStatus::Error => "error",
        ReviewProcessStatus::Blocked => "blocked",
    }
}

fn format_reports_output(reports: &ReportsResult) -> String {
    if let Some(concatenated) = &reports.concatenated_report {
        return concatenated.clone();
    }
    if reports.reports.is_empty() {
        return "no reports".to_string();
    }

    let mut lines = vec![format!(
        "view={} recursive={} include_leaf_children={}",
        toml::Value::try_from(reports.view).map_or_else(
            |_| "all".to_string(),
            |value| value.to_string().trim_matches('"').to_string()
        ),
        reports.recursive,
        reports.include_leaf_children
    )];

    for report in &reports.reports {
        let mut line = format!(
            "{} {} {} {}",
            report.reviewer_id,
            review_status_text(report.status),
            report.role,
            report.agent_dir
        );
        if let Some(report_path) = &report.report_path {
            line.push_str(&format!(" report={report_path}"));
        }
        if report.child_count > 0 {
            line.push_str(&format!(" children={}", report.child_count));
        }
        if !report.warnings.is_empty() {
            line.push_str(&format!(" warnings={}", report.warnings.join(" | ")));
        }
        lines.push(line);
        if let Some(contents) = &report.report_contents {
            lines.push(String::new());
            lines.push(format!("## {}", report.reviewer_id));
            lines.push(contents.clone());
        }
    }
    if let Some(final_report_path) = &reports.final_report_path {
        lines.push(String::new());
        lines.push(format!("final_report {final_report_path}"));
    }
    lines.join("\n")
}

fn render_protocol_output(output: &mpcr::protocol::ProtocolOutput) -> String {
    output.content.clone()
}

fn render_dispatch_output(output: &mpcr::protocol::DispatchOutput) -> String {
    output.content.clone()
}

fn render_protocol_list(entries: &[mpcr::policy_store::PolicyListEntry]) -> String {
    let mut lines = if entries.is_empty() {
        vec!["no policies".to_string()]
    } else {
        entries
            .iter()
            .map(|entry| format!("{} {} {}", entry.category, entry.id, entry.version))
            .collect::<Vec<_>>()
    };
    let dispatch_roles = protocol::dispatch_list();
    if !dispatch_roles.is_empty() {
        lines.push(String::new());
        lines.push("dispatch roles".to_string());
        lines.extend(
            dispatch_roles
                .into_iter()
                .map(|role| format!("worker {role}")),
        );
    }
    lines.join("\n")
}

fn router_surface_policy_refs() -> Vec<PolicyRef> {
    vec![PolicyRef {
        category: PolicyCategory::Worker,
        id: "surface-mapper".to_string(),
        version: POLICY_BUNDLE_VERSION.to_string(),
        view: PolicyView::Checklist,
    }]
}

fn role_slug_from_spawn_args(
    role_id: Option<&str>,
    worker_kind: Option<mpcr::artifacts::WorkerKind>,
    domain_id: Option<mpcr::artifacts::ModuleId>,
    language: Option<&str>,
) -> String {
    if let Some(role_id) = role_id {
        return role_id.to_string();
    }
    if let Some(domain_id) = domain_id {
        let slug = toml::Value::try_from(domain_id).map_or_else(
            |_| "unknown".to_string(),
            |value| value.to_string().trim_matches('"').to_string(),
        );
        return format!("domain:{slug}");
    }
    match worker_kind {
        Some(mpcr::artifacts::WorkerKind::LanguageDetector) => "language-detector".to_string(),
        Some(mpcr::artifacts::WorkerKind::LanguageResearch) => {
            format!(
                "language-research:{}",
                language.map_or("unknown", |value| value)
            )
        }
        Some(mpcr::artifacts::WorkerKind::FinalSynthesizer) => "final-synthesis".to_string(),
        Some(mpcr::artifacts::WorkerKind::ApplicatorWorker) => "applicator-worker".to_string(),
        Some(mpcr::artifacts::WorkerKind::ApplicatorVerifier) => "applicator-verifier".to_string(),
        _ => "domain:unassigned".to_string(),
    }
}

fn build_route_output(
    mode: Mode,
    target_ref: &str,
    session_id: &str,
    inputs: &RouteInputs,
) -> anyhow::Result<RouteCommandOutput> {
    let surface_map = build_surface_map(
        ArtifactHeader::new(
            ArtifactKind::SurfaceMap,
            id::random_hex_id(6)?,
            session_id.to_string(),
            target_ref.to_string(),
            ProducerKind::Router,
            now_rfc3339(),
            ConfidenceLabel::High,
            90,
            router_surface_policy_refs(),
        )?,
        inputs,
    );
    let route_decision = build_route_decision(
        ArtifactHeader::new(
            ArtifactKind::RouteDecision,
            id::random_hex_id(6)?,
            session_id.to_string(),
            target_ref.to_string(),
            ProducerKind::Router,
            now_rfc3339(),
            ConfidenceLabel::High,
            90,
            default_router_policy_refs(&surface_map.suggested_modules),
        )?,
        mode,
        &surface_map,
        inputs,
    );
    Ok(RouteCommandOutput {
        surface_map,
        route_decision,
        persisted: None,
    })
}

fn main() {
    if let Err(err) = run() {
        eprintln!("{}", format_error_output(&err));
        std::process::exit(1);
    }
}

fn hint_for_error(text: &str) -> Option<String> {
    if text.contains("unknown dispatch role") {
        return Some(format!(
            "run `mpcr protocol dispatch --role domain:core-correctness` or choose from: {}",
            protocol::dispatch_list().join(", ")
        ));
    }
    if text.contains("unknown Worker policy")
        || text.contains("unknown Module policy")
        || text.contains("unknown Escalation policy")
        || text.contains("unknown Mode policy")
    {
        return Some("run `mpcr protocol list` to discover valid mode, worker, module, escalation, and dispatch ids".to_string());
    }
    if text.contains("session does not exist yet") {
        return Some("initialize the session with `mpcr reviewer register --target-ref <ref> --session-dir <path>`".to_string());
    }
    if text.contains("was not found in the session") || text.contains("was not found") {
        return Some("inspect the active reviewer tree with `mpcr session reports --recursive --session-dir <path>`".to_string());
    }
    if text.contains("route_decision pointer could not be resolved")
        || text.contains("no current route_decision is persisted")
    {
        return Some("persist routing first with `mpcr route --persist ...` before applying a route revision".to_string());
    }
    if text.contains("protocol dispatch with --reviewer-id also requires a session locator") {
        return Some("rerun with `--session-dir <path>` so the dispatch prompt can resolve the reviewer tree".to_string());
    }
    None
}

fn format_error_output(err: &anyhow::Error) -> String {
    let mut message = err.to_string().trim().to_string();
    if !message.starts_with("error:") {
        message = format!("error: {message}");
    }
    if message.contains("\nhint:") {
        return message;
    }
    if let Some(hint) = hint_for_error(&message) {
        return format!("{message}\nhint: {hint}");
    }
    message
}

fn run() -> anyhow::Result<()> {
    let cli = Cli::parse();
    let json = cli.json;
    let json_pretty = cli.json_pretty;
    match cli.command {
        Commands::Route(args) => {
            anyhow::ensure!(
                args.max_worker_count > 0,
                "error: max-worker-count must be at least 1"
            );
            let locator = resolve_session_locator(&args.session)?;
            let inputs = RouteInputs {
                changed_files: args.changed_file,
                public_interfaces: args.public_interface,
                behavior_facing_artifacts: args.behavior_facing_artifact,
                execution_capability: args.execution_capability,
                max_worker_count: args.max_worker_count,
                orchestrator_read_budget_lines: args.orchestrator_read_budget_lines,
                orchestrator_read_budget_snippets: args.orchestrator_read_budget_snippets,
                history_signals: Default::default(),
            };
            let session_id = if args.persist {
                ensure_session(&locator, &args.target_ref)?.session_id
            } else {
                id::random_id8()?
            };
            let mut output = build_route_output(args.mode, &args.target_ref, &session_id, &inputs)?;
            if args.persist {
                let persisted = persist_route_artifacts(PersistRouteArtifactsParams {
                    session: locator,
                    target_ref: args.target_ref,
                    surface_map: output.surface_map.clone(),
                    route_decision: output.route_decision.clone(),
                })?;
                output.persisted = Some(persisted);
            }
            emit_text_or_json(json, json_pretty, &output, || {
                Ok(toml::to_string_pretty(&output)?)
            })?;
        }
        Commands::Id { command } => match command {
            IdCommands::Id8 => {
                let value = id::random_id8()?;
                if cli.json || cli.json_pretty {
                    emit_json(&serde_json::json!({ "id8": value }), cli.json_pretty)?;
                } else {
                    println!("{value}");
                }
            }
            IdCommands::Hex { bytes } => {
                let value = id::random_hex_id(bytes)?;
                if cli.json || cli.json_pretty {
                    emit_json(&serde_json::json!({ "hex": value }), cli.json_pretty)?;
                } else {
                    println!("{value}");
                }
            }
        },
        Commands::Lock { command } => match command {
            LockCommands::Acquire {
                session,
                owner,
                max_retries,
            } => {
                let locator = resolve_session_locator(&session)?;
                let guard = lock::acquire_lock(
                    locator.session_dir(),
                    owner.clone(),
                    LockConfig {
                        max_retries,
                        ..LockConfig::default()
                    },
                )?;
                let output = serde_json::json!({
                    "status": "ok",
                    "lock_file": lock::lock_file_path(locator.session_dir()),
                    "owner": owner
                });
                std::mem::forget(guard);
                emit_text_or_json(json, json_pretty, &output, || Ok("ok".to_string()))?;
            }
            LockCommands::Release { session, owner } => {
                let locator = resolve_session_locator(&session)?;
                lock::release_lock(locator.session_dir(), owner)?;
                emit_text_or_json(
                    json,
                    json_pretty,
                    &serde_json::json!({"status":"ok"}),
                    || Ok("ok".to_string()),
                )?;
            }
        },
        Commands::Session { command } => match command {
            SessionCommands::Show { session } => {
                let locator = resolve_session_locator(&session)?;
                let ledger = load_session(&locator)?;
                emit_text_or_json(json, json_pretty, &ledger, || {
                    Ok(toml::to_string_pretty(&ledger)?)
                })?;
            }
            SessionCommands::Reports {
                session,
                view,
                recursive,
                include_report_contents,
                include_leaf_children,
                concatenate,
            } => {
                let locator = resolve_session_locator(&session)?;
                let reports = collect_reports(
                    &locator,
                    view,
                    recursive,
                    include_leaf_children,
                    include_report_contents,
                    concatenate,
                )?;
                emit_text_or_json(json, json_pretty, &reports, || {
                    Ok(format_reports_output(&reports))
                })?;
            }
            SessionCommands::Artifacts { session, kind } => {
                let locator = resolve_session_locator(&session)?;
                let ledger = load_session(&locator)?;
                let artifacts = list_artifacts(&ledger, kind);
                emit_text_or_json(json, json_pretty, &artifacts, || {
                    Ok(format_artifact_list(&artifacts))
                })?;
            }
            SessionCommands::Cleanup { session } => {
                let locator = resolve_session_locator(&session)?;
                let scratch_dir = cleanup_session(&locator)?;
                emit_text_or_json(
                    json,
                    json_pretty,
                    &serde_json::json!({ "scratch_dir": scratch_dir }),
                    || Ok(format!("removed {}", scratch_dir.display())),
                )?;
            }
            SessionCommands::Metrics { session } => {
                let locator = resolve_session_locator(&session)?;
                let ledger = load_session(&locator)?;
                emit_text_or_json(json, json_pretty, &ledger.telemetry, || {
                    Ok(toml::to_string_pretty(&ledger.telemetry)?)
                })?;
            }
            SessionCommands::ApplyRouteRevision {
                session,
                artifact_file,
            } => {
                let locator = resolve_session_locator(&session)?;
                let result = apply_route_revision_artifact(ApplyRouteRevisionParams {
                    session: locator,
                    artifact_file,
                })?;
                emit_text_or_json(json, json_pretty, &result, || {
                    Ok(toml::to_string_pretty(&result)?)
                })?;
            }
        },
        Commands::Reviewer { command } => match command {
            ReviewerCommands::Register {
                session,
                target_ref,
                reviewer_id,
            } => {
                let locator = resolve_session_locator(&session)?;
                let result = register_reviewer(RegisterReviewerParams {
                    session: locator,
                    target_ref,
                    reviewer_id,
                    role: None,
                    role_kind: None,
                })?;
                emit_text_or_json(json, json_pretty, &result, || {
                    Ok(toml::to_string_pretty(&result)?)
                })?;
            }
            ReviewerCommands::SpawnChildren {
                session,
                parent_id,
                count,
                role_id,
                worker_kind,
                domain_id,
                language,
                module_id,
                focus_surface,
                claimed_scope,
                delegated_scope,
            } => {
                let locator = resolve_session_locator(&session)?;
                let role = role_slug_from_spawn_args(
                    role_id.as_deref(),
                    worker_kind,
                    domain_id,
                    language.as_deref(),
                );
                let result = spawn_child_reviewers(SpawnChildReviewersParams {
                    session: locator,
                    parent_id,
                    count,
                    role_id: Some(role),
                    worker_kind,
                    domain_id,
                    language,
                    module_ids: module_id,
                    focus_surfaces: focus_surface,
                    claimed_scope,
                    delegated_scope,
                })?;
                emit_text_or_json(json, json_pretty, &result, || {
                    Ok(toml::to_string_pretty(&result)?)
                })?;
            }
            ReviewerCommands::CloseChildren {
                session,
                parent_id,
                set_status,
            } => {
                let locator = resolve_session_locator(&session)?;
                let result = close_child_reviews(CloseChildReviewsParams {
                    session: locator,
                    parent_id,
                    status: set_status,
                })?;
                emit_text_or_json(json, json_pretty, &result, || {
                    Ok(toml::to_string_pretty(&result)?)
                })?;
            }
            ReviewerCommands::Update {
                session,
                reviewer_id,
                status,
                phase,
            } => {
                let locator = resolve_session_locator(&session)?;
                let result = update_review(UpdateReviewParams {
                    session: locator,
                    reviewer_id,
                    status,
                    phase,
                })?;
                emit_text_or_json(json, json_pretty, &result, || {
                    Ok(toml::to_string_pretty(&result)?)
                })?;
            }
            ReviewerCommands::Note {
                session,
                reviewer_id,
                content,
            } => {
                let locator = resolve_session_locator(&session)?;
                let result = append_reviewer_note(AppendReviewerNoteParams {
                    session: locator,
                    reviewer_id,
                    content,
                })?;
                emit_text_or_json(json, json_pretty, &result, || {
                    Ok(toml::to_string_pretty(&result)?)
                })?;
            }
            ReviewerCommands::CompleteChild {
                session,
                reviewer_id,
                artifact_file,
            } => {
                let locator = resolve_session_locator(&session)?;
                let result = complete_child_review(ReviewerArtifactParams {
                    session: locator,
                    reviewer_id,
                    artifact_file,
                })?;
                emit_text_or_json(json, json_pretty, &result, || {
                    Ok(toml::to_string_pretty(&result)?)
                })?;
            }
            ReviewerCommands::Finalize {
                session,
                reviewer_id,
                artifact_file,
            } => {
                let locator = resolve_session_locator(&session)?;
                let result = finalize_review(ReviewerArtifactParams {
                    session: locator,
                    reviewer_id,
                    artifact_file,
                })?;
                emit_text_or_json(json, json_pretty, &result, || {
                    Ok(toml::to_string_pretty(&result)?)
                })?;
            }
        },
        Commands::Applicator { command } => match command {
            ApplicatorCommands::SetStatus { session, status } => {
                let locator = resolve_session_locator(&session)?;
                let result = set_applicator_status(SetApplicatorStatusParams {
                    session: locator,
                    status,
                })?;
                emit_text_or_json(
                    json,
                    json_pretty,
                    &serde_json::json!({"status": result}),
                    || Ok(format!("{result:?}").to_lowercase()),
                )?;
            }
            ApplicatorCommands::Note { session, content } => {
                let locator = resolve_session_locator(&session)?;
                let result = append_applicator_note(AppendApplicatorNoteParams {
                    session: locator,
                    content,
                })?;
                emit_text_or_json(json, json_pretty, &result, || {
                    Ok(toml::to_string_pretty(&result)?)
                })?;
            }
            ApplicatorCommands::Wait { session } => {
                let locator = resolve_session_locator(&session)?;
                let result = applicator_wait(locator)?;
                emit_text_or_json(json, json_pretty, &result, || {
                    Ok(toml::to_string_pretty(&result)?)
                })?;
            }
            ApplicatorCommands::Finalize {
                session,
                artifact_file,
            } => {
                let locator = resolve_session_locator(&session)?;
                let result = finalize_application(ApplicatorArtifactParams {
                    session: locator,
                    artifact_file,
                })?;
                emit_text_or_json(json, json_pretty, &result, || {
                    Ok(toml::to_string_pretty(&result)?)
                })?;
            }
            ApplicatorCommands::Verify {
                session,
                artifact_file,
            } => {
                let locator = resolve_session_locator(&session)?;
                let result = mpcr::session::verify_application(ApplicatorArtifactParams {
                    session: locator,
                    artifact_file,
                })?;
                emit_text_or_json(json, json_pretty, &result, || {
                    Ok(toml::to_string_pretty(&result)?)
                })?;
            }
        },
        Commands::Protocol { command } => match command {
            ProtocolCommands::List => {
                let result = protocol::list()?;
                emit_text_or_json(json, json_pretty, &result, || {
                    Ok(render_protocol_list(&result))
                })?;
            }
            ProtocolCommands::Mode { mode, view } => {
                let output = protocol::mode(
                    &toml::Value::try_from(mode).map_or_else(
                        |_| "reviewer".to_string(),
                        |value| value.to_string().trim_matches('"').to_string(),
                    ),
                    view,
                )?;
                emit_text_or_json(json, json_pretty, &output, || {
                    Ok(render_protocol_output(&output))
                })?;
            }
            ProtocolCommands::Worker { kind, view } => {
                let output = protocol::worker(
                    &toml::Value::try_from(kind).map_or_else(
                        |_| "review-composite".to_string(),
                        |value| value.to_string().trim_matches('"').to_string(),
                    ),
                    view,
                )?;
                emit_text_or_json(json, json_pretty, &output, || {
                    Ok(render_protocol_output(&output))
                })?;
            }
            ProtocolCommands::Module { id, view } => {
                let output = protocol::module(
                    &toml::Value::try_from(id).map_or_else(
                        |_| "core-correctness".to_string(),
                        |value| value.to_string().trim_matches('"').to_string(),
                    ),
                    view,
                )?;
                emit_text_or_json(json, json_pretty, &output, || {
                    Ok(render_protocol_output(&output))
                })?;
            }
            ProtocolCommands::Escalation { id, view } => {
                let output = protocol::escalation(
                    &toml::Value::try_from(id).map_or_else(
                        |_| "reopen".to_string(),
                        |value| value.to_string().trim_matches('"').to_string(),
                    ),
                    view,
                )?;
                emit_text_or_json(json, json_pretty, &output, || {
                    Ok(render_protocol_output(&output))
                })?;
            }
            ProtocolCommands::Dispatch {
                session,
                reviewer_id,
                role,
                view,
            } => {
                let locator = if session.is_empty() {
                    None
                } else {
                    Some(resolve_session_locator(&session)?)
                };
                let output =
                    protocol::dispatch(&role, locator.as_ref(), reviewer_id.as_deref(), view)?;
                emit_text_or_json(json, json_pretty, &output, || {
                    Ok(render_dispatch_output(&output))
                })?;
            }
        },
        Commands::Render(args) => {
            let artifact = parse_artifact_file(&args.artifact_file)?;
            match args.format {
                RenderFormat::Markdown => {
                    let markdown = render_artifact_markdown(&artifact)?;
                    if let Some(ref output) = args.output {
                        fs::write(&output, &markdown)
                            .with_context(|| format!("write {}", output.display()))?;
                    }
                    if json || json_pretty {
                        emit_json(
                            &serde_json::json!({
                                "artifact_kind": artifact.kind(),
                                "markdown": markdown,
                                "output": args.output.clone(),
                            }),
                            json_pretty,
                        )?;
                    } else {
                        println!("{markdown}");
                    }
                }
            }
        }
        Commands::Validate(args) => {
            let summary = validate_artifact_file(
                &args.artifact_file,
                args.kind,
                args.layer,
                args.session_dir.as_deref(),
            )?;
            if json || json_pretty {
                emit_json(&summary, json_pretty)?;
            } else {
                println!("{}", toml::to_string_pretty(&summary)?);
            }
            if args.layer == ValidationLayer::Hard && !summary.errors.is_empty() {
                return Err(anyhow::anyhow!(
                    "error: hard validation failed: {}",
                    summary.errors.join("; ")
                ));
            }
        }
        Commands::Fullcycle { command } => match command {
            FullcycleCommands::Plan { session, output } => {
                let locator = resolve_session_locator(&session)?;
                let plan = fullcycle_plan::build_plan(&locator)?;
                let document = ArtifactDocument::ConvergenceState(plan.clone());
                let toml_output = document.to_toml_string()?;
                if let Some(output) = output {
                    fs::write(&output, toml_output.as_bytes())
                        .with_context(|| format!("write {}", output.display()))?;
                }
                emit_text_or_json(json, json_pretty, &plan, || Ok(toml_output))?;
            }
            FullcycleCommands::State { session } => {
                let locator = resolve_session_locator(&session)?;
                let state = fullcycle_plan::load_state(&locator)?.ok_or_else(|| {
                    anyhow::anyhow!("error: no convergence_state is currently persisted")
                })?;
                emit_text_or_json(json, json_pretty, &state, || {
                    Ok(toml::to_string_pretty(&state)?)
                })?;
            }
            FullcycleCommands::Checkpoint {
                session,
                artifact_file,
            } => {
                let locator = resolve_session_locator(&session)?;
                let result = checkpoint_convergence_state(ApplicatorArtifactParams {
                    session: locator,
                    artifact_file,
                })?;
                emit_text_or_json(json, json_pretty, &result, || {
                    Ok(toml::to_string_pretty(&result)?)
                })?;
            }
        },
        Commands::Analyze { command } => match command {
            AnalyzeCommands::ListChecks => {
                let checks = analyze::available_checks();
                emit_text_or_json(json, json_pretty, &checks, || {
                    Ok(checks
                        .iter()
                        .map(|(name, desc)| format!("{name}\t{desc}"))
                        .collect::<Vec<_>>()
                        .join("\n"))
                })?;
            }
            AnalyzeCommands::Run { files } => {
                let file_map = read_files(&files)?;
                let report = analyze::run_all(&file_map)?;
                emit_text_or_json(json, json_pretty, &report, || {
                    Ok(serde_json::to_string_pretty(&report)?)
                })?;
            }
            AnalyzeCommands::Check { name, files } => {
                let file_map = read_files(&files)?;
                let output = analyze::run_check_output(&file_map, &name)?;
                emit_text_or_json(json, json_pretty, &output, || {
                    Ok(serde_json::to_string_pretty(&output)?)
                })?;
            }
        },
    }
    Ok(())
}
