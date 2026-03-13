//! Session ledger, recursive agent ledgers, and review/apply operations.
#![allow(clippy::module_name_repetitions)]
#![allow(missing_docs)]

use crate::artifacts::{
    now_rfc3339, parse_artifact_file, validate_session_id, ArtifactDocument, ArtifactKind,
    DeclineReasonCode, Disposition, ModuleId, Severity, SurfaceId, WorkerKind,
    LEGACY_REJECTION_MESSAGE, SESSION_SCHEMA_VERSION,
};
use crate::id;
use crate::lock::{self, LockConfig};
use crate::metrics::{record_artifact, TelemetryLedger};
use crate::paths::{self, StorageFormat};
use crate::render::render_artifact_markdown;
use crate::validate::{validate_artifact_document, ValidationLayer};
use anyhow::Context;
use clap::ValueEnum;
use serde::de::DeserializeOwned;
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, HashMap, HashSet};
use std::fs;
use std::path::{Path, PathBuf};

const ACTIVE_ARTIFACT_FORMAT: &str = "mpcr_artifact.v1";
const AGENT_SCHEMA_VERSION: &str = "mpcr_agent.v1";

fn module_id_text(module_id: ModuleId) -> String {
    match module_id {
        ModuleId::CoreCorrectness => "core-correctness",
        ModuleId::AuthAccess => "auth-access",
        ModuleId::InputValidation => "input-validation",
        ModuleId::Persistence => "persistence",
        ModuleId::DataIntegrity => "data-integrity",
        ModuleId::Concurrency => "concurrency",
        ModuleId::DocsStaleness => "docs-staleness",
        ModuleId::OperatorGuidance => "operator-guidance",
        ModuleId::Performance => "performance",
        ModuleId::Dependency => "dependency",
        ModuleId::Privacy => "privacy",
        ModuleId::Observability => "observability",
        ModuleId::Tests => "tests",
        ModuleId::ScopeCreep => "scope-creep",
        ModuleId::ShipReadiness => "ship-readiness",
    }
    .to_string()
}

fn severity_text(severity: Severity) -> String {
    match severity {
        Severity::Blocker => "blocker",
        Severity::Major => "major",
        Severity::Minor => "minor",
        Severity::Nit => "nit",
    }
    .to_string()
}

fn surface_text(surface: SurfaceId) -> String {
    match surface {
        SurfaceId::BehaviorChange => "behavior-change",
        SurfaceId::PublicApi => "public-api",
        SurfaceId::AuthAccess => "auth-access",
        SurfaceId::InputValidation => "input-validation",
        SurfaceId::PrivilegeBoundary => "privilege-boundary",
        SurfaceId::Persistence => "persistence",
        SurfaceId::Migration => "migration",
        SurfaceId::DataIntegrity => "data-integrity",
        SurfaceId::Concurrency => "concurrency",
        SurfaceId::StateMachine => "state-machine",
        SurfaceId::DocsStaleness => "docs-staleness",
        SurfaceId::OperatorGuidance => "operator-guidance",
        SurfaceId::ConfigSurface => "config-surface",
        SurfaceId::PerformanceHotpath => "performance-hotpath",
        SurfaceId::DependencyBuild => "dependency-build",
        SurfaceId::TestCoverage => "test-coverage",
        SurfaceId::Observability => "observability",
        SurfaceId::Privacy => "privacy",
    }
    .to_string()
}

fn status_text(status: ReviewProcessStatus) -> String {
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
    .to_string()
}

fn default_review_role() -> String {
    "domain:unassigned".to_string()
}

fn default_storage_status() -> StorageStatus {
    StorageStatus::default()
}

fn default_role_kind() -> AgentRoleKind {
    AgentRoleKind::DomainReviewer
}

fn infer_role_kind(role: &str) -> AgentRoleKind {
    if role.starts_with("language-detector") {
        AgentRoleKind::LanguageDetector
    } else if role.starts_with("language-research:") {
        AgentRoleKind::LanguageResearch
    } else if role.starts_with("final-synthesis") {
        AgentRoleKind::FinalSynthesis
    } else if role.starts_with("applicator-worker") {
        AgentRoleKind::ApplicatorWorker
    } else if role.starts_with("applicator-verifier") {
        AgentRoleKind::ApplicatorVerifier
    } else {
        AgentRoleKind::DomainReviewer
    }
}

fn module_ids_for_role(role: &str) -> Vec<ModuleId> {
    let Some(module_slug) = role.strip_prefix("domain:") else {
        return Vec::new();
    };
    ModuleId::all()
        .into_iter()
        .filter(|module_id| module_id_text(*module_id) == module_slug)
        .collect()
}

fn review_lineage(
    session: &SessionLedger,
    parent_id: Option<&str>,
    reviewer_id: &str,
) -> Vec<String> {
    let mut lineage = if let Some(parent_id) = parent_id {
        if let Some(parent) = session
            .reviews
            .iter()
            .find(|review| review.reviewer_id == parent_id)
        {
            let mut inherited = parent.lineage.clone();
            if inherited.last().map(String::as_str) != Some(parent.reviewer_id.as_str()) {
                inherited.push(parent.reviewer_id.clone());
            }
            inherited
        } else {
            vec![parent_id.to_string()]
        }
    } else {
        Vec::new()
    };
    if lineage.last().map(String::as_str) != Some(reviewer_id) {
        lineage.push(reviewer_id.to_string());
    }
    lineage
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ArtifactPointer {
    pub artifact_id: String,
    pub artifact_kind: ArtifactKind,
    pub path: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub json_path: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub toml_path: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub rendered_path: Option<String>,
    pub created_at: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum AgentRoleKind {
    DomainReviewer,
    LanguageDetector,
    LanguageResearch,
    FinalSynthesis,
    ApplicatorWorker,
    ApplicatorVerifier,
    Helper,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct LanguageResearchRef {
    pub language: String,
    pub agent_id: String,
    pub report_path: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct StorageStatus {
    pub primary_format: StorageFormat,
    #[serde(default)]
    pub available_formats: Vec<StorageFormat>,
    #[serde(default)]
    pub degraded_warnings: Vec<String>,
}

impl Default for StorageStatus {
    fn default() -> Self {
        Self {
            primary_format: StorageFormat::Json,
            available_formats: vec![StorageFormat::Json],
            degraded_warnings: Vec::new(),
        }
    }
}

#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct CurrentArtifacts {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub route_decision: Option<ArtifactPointer>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub surface_map: Option<ArtifactPointer>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub child_findings: Option<ArtifactPointer>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub parent_review: Option<ArtifactPointer>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub application_result: Option<ArtifactPointer>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub verification_result: Option<ArtifactPointer>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub convergence_state: Option<ArtifactPointer>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub route_revision: Option<ArtifactPointer>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, ValueEnum)]
#[serde(rename_all = "snake_case")]
pub enum ReviewProcessStatus {
    Registered,
    InProgress,
    Delegating,
    WaitingOnChildren,
    Synthesizing,
    Completed,
    Cancelled,
    Error,
    Blocked,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, ValueEnum)]
#[serde(rename_all = "snake_case")]
pub enum ApplicatorStatus {
    Waiting,
    Reviewing,
    Applying,
    Verifying,
    Completed,
    Blocked,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ReviewProcess {
    pub reviewer_id: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub parent_id: Option<String>,
    #[serde(default = "default_review_role")]
    pub role: String,
    #[serde(default = "default_role_kind")]
    pub role_kind: AgentRoleKind,
    pub status: ReviewProcessStatus,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub phase: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub artifact_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub report_path: Option<String>,
    #[serde(default)]
    pub agent_dir: String,
    #[serde(default)]
    pub agent_ledger_json: String,
    #[serde(default)]
    pub agent_ledger_toml: String,
    #[serde(default)]
    pub child_ids: Vec<String>,
    #[serde(default)]
    pub module_ids: Vec<ModuleId>,
    #[serde(default)]
    pub focus_surfaces: Vec<SurfaceId>,
    #[serde(default)]
    pub claimed_scope: Vec<String>,
    #[serde(default)]
    pub delegated_scope: Vec<String>,
    #[serde(default)]
    pub lineage: Vec<String>,
    #[serde(default)]
    pub research_refs: Vec<LanguageResearchRef>,
    #[serde(default = "default_storage_status")]
    pub storage: StorageStatus,
    pub opened_at: String,
    pub updated_at: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ApplicatorState {
    pub status: ApplicatorStatus,
    pub updated_at: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub application_result_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub verification_result_id: Option<String>,
}

impl Default for ApplicatorState {
    fn default() -> Self {
        Self {
            status: ApplicatorStatus::Waiting,
            updated_at: now_rfc3339(),
            application_result_id: None,
            verification_result_id: None,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum NoteActorKind {
    Reviewer,
    Applicator,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct SessionNote {
    pub actor_kind: NoteActorKind,
    pub actor_id: String,
    pub created_at: String,
    pub content: String,
}

#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct SessionCounters {
    pub artifact_count: u64,
    pub rendered_count: u64,
    pub reviewer_count: u64,
    pub note_count: u64,
    pub total_agents: u64,
    pub active_agents: u64,
    pub completed_agents: u64,
    pub report_count: u64,
    pub research_workers: u64,
    pub applied_findings: u64,
    pub declined_findings: u64,
    pub low_signal_rejections: u64,
    pub duplicate_rejections: u64,
    pub reopen_triggers: u64,
    #[serde(default)]
    pub severity_totals: BTreeMap<String, u64>,
    #[serde(default)]
    pub domain_totals: BTreeMap<String, u64>,
}

#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct AgentCounters {
    pub local_artifact_count: u64,
    pub recursive_artifact_count: u64,
    pub local_report_count: u64,
    pub recursive_report_count: u64,
    pub child_count: u64,
    pub descendant_count: u64,
    pub local_findings: u64,
    pub recursive_findings: u64,
    pub local_applied_findings: u64,
    pub recursive_applied_findings: u64,
    pub local_declined_findings: u64,
    pub recursive_declined_findings: u64,
    pub local_low_signal_rejections: u64,
    pub recursive_low_signal_rejections: u64,
    pub local_duplicate_rejections: u64,
    pub recursive_duplicate_rejections: u64,
    pub local_reopen_triggers: u64,
    pub recursive_reopen_triggers: u64,
    pub local_research_ref_count: u64,
    pub recursive_research_ref_count: u64,
    #[serde(default)]
    pub local_severity_totals: BTreeMap<String, u64>,
    #[serde(default)]
    pub recursive_severity_totals: BTreeMap<String, u64>,
}

#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct ConvergencePointers {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub current_artifact_id: Option<String>,
    pub cycle_index: usize,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub stop_condition: Option<String>,
    #[serde(default)]
    pub terminal_cleanup_consumed: bool,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct SessionLedger {
    pub schema_version: String,
    pub session_id: String,
    pub session_date: String,
    pub repo_root: String,
    pub target_ref: String,
    pub created_at: String,
    pub updated_at: String,
    pub active_artifact_format: String,
    #[serde(default = "default_storage_status")]
    pub storage: StorageStatus,
    #[serde(default)]
    pub agents_root: String,
    #[serde(default)]
    pub final_report_path: Option<String>,
    #[serde(default)]
    pub final_summary_json_path: Option<String>,
    #[serde(default)]
    pub final_summary_toml_path: Option<String>,
    #[serde(default)]
    pub detected_languages: Vec<String>,
    #[serde(default)]
    pub language_research_refs: Vec<LanguageResearchRef>,
    pub current: CurrentArtifacts,
    #[serde(default)]
    pub artifacts: Vec<ArtifactPointer>,
    #[serde(default)]
    pub reviews: Vec<ReviewProcess>,
    #[serde(default)]
    pub applicator: ApplicatorState,
    #[serde(default)]
    pub notes: Vec<SessionNote>,
    #[serde(default)]
    pub counters: SessionCounters,
    #[serde(default)]
    pub telemetry: TelemetryLedger,
    #[serde(default)]
    pub convergence: ConvergencePointers,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct AgentLedger {
    pub schema_version: String,
    pub session_id: String,
    pub reviewer_id: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub parent_id: Option<String>,
    pub role: String,
    pub role_kind: AgentRoleKind,
    pub status: ReviewProcessStatus,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub phase: Option<String>,
    pub agent_dir: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub report_path: Option<String>,
    #[serde(default)]
    pub child_ids: Vec<String>,
    #[serde(default)]
    pub module_ids: Vec<ModuleId>,
    #[serde(default)]
    pub focus_surfaces: Vec<SurfaceId>,
    #[serde(default)]
    pub claimed_scope: Vec<String>,
    #[serde(default)]
    pub delegated_scope: Vec<String>,
    #[serde(default)]
    pub lineage: Vec<String>,
    #[serde(default)]
    pub research_refs: Vec<LanguageResearchRef>,
    #[serde(default)]
    pub artifacts: Vec<ArtifactPointer>,
    #[serde(default = "default_storage_status")]
    pub storage: StorageStatus,
    #[serde(default)]
    pub counters: AgentCounters,
    pub opened_at: String,
    pub updated_at: String,
}

#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct AgentChildrenManifest {
    #[serde(default)]
    pub child_ids: Vec<String>,
}

#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct AgentPointerManifest {
    #[serde(default)]
    pub artifacts: Vec<ArtifactPointer>,
}

#[derive(Debug, Clone)]
pub struct SessionLocator {
    session_dir: PathBuf,
}

impl SessionLocator {
    #[must_use]
    pub fn from_session_dir(session_dir: PathBuf) -> Self {
        Self { session_dir }
    }

    #[must_use]
    pub fn session_dir(&self) -> &Path {
        &self.session_dir
    }
}

#[derive(Debug, Clone)]
pub struct RegisterReviewerParams {
    pub session: SessionLocator,
    pub target_ref: String,
    pub reviewer_id: Option<String>,
    pub role: Option<String>,
    pub role_kind: Option<AgentRoleKind>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct RegisterReviewerResult {
    pub session_dir: String,
    pub session_id: String,
    pub reviewer_id: String,
    pub target_ref: String,
    pub agent_dir: String,
    pub agent_ledger_json: String,
    pub agent_ledger_toml: String,
    pub session_format_primary: StorageFormat,
}

#[derive(Debug, Clone)]
pub struct SpawnChildReviewersParams {
    pub session: SessionLocator,
    pub parent_id: String,
    pub count: u8,
    pub role_id: Option<String>,
    pub worker_kind: Option<WorkerKind>,
    pub domain_id: Option<ModuleId>,
    pub language: Option<String>,
    pub module_ids: Vec<ModuleId>,
    pub focus_surfaces: Vec<SurfaceId>,
    pub claimed_scope: Vec<String>,
    pub delegated_scope: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct SpawnChildReviewersResult {
    pub child_ids: Vec<String>,
    pub child_agent_dirs: Vec<String>,
    pub child_agent_ledgers_json: Vec<String>,
    pub child_agent_ledgers_toml: Vec<String>,
    pub session_format_primary: StorageFormat,
}

#[derive(Debug, Clone)]
pub struct CloseChildReviewsParams {
    pub session: SessionLocator,
    pub parent_id: String,
    pub status: ReviewProcessStatus,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct CloseChildReviewsResult {
    pub closed_ids: Vec<String>,
}

#[derive(Debug, Clone)]
pub struct UpdateReviewParams {
    pub session: SessionLocator,
    pub reviewer_id: String,
    pub status: ReviewProcessStatus,
    pub phase: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct UpdateReviewResult {
    pub reviewer_id: String,
    pub status: ReviewProcessStatus,
    pub phase: Option<String>,
}

#[derive(Debug, Clone)]
pub struct AppendReviewerNoteParams {
    pub session: SessionLocator,
    pub reviewer_id: String,
    pub content: String,
}

#[derive(Debug, Clone)]
pub struct AppendApplicatorNoteParams {
    pub session: SessionLocator,
    pub content: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct AppendNoteResult {
    pub note_count: usize,
}

#[derive(Debug, Clone)]
pub struct ReviewerArtifactParams {
    pub session: SessionLocator,
    pub reviewer_id: String,
    pub artifact_file: PathBuf,
}

#[derive(Debug, Clone)]
pub struct ApplicatorArtifactParams {
    pub session: SessionLocator,
    pub artifact_file: PathBuf,
}

#[derive(Debug, Clone)]
pub struct PersistRouteArtifactsParams {
    pub session: SessionLocator,
    pub target_ref: String,
    pub surface_map: crate::artifacts::SurfaceMapArtifact,
    pub route_decision: crate::artifacts::RouteDecisionArtifact,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct PersistRouteArtifactsResult {
    pub surface_map: PersistArtifactResult,
    pub route_decision: PersistArtifactResult,
}

#[derive(Debug, Clone)]
pub struct ApplyRouteRevisionParams {
    pub session: SessionLocator,
    pub artifact_file: PathBuf,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct ApplyRouteRevisionResult {
    pub route_revision: PersistArtifactResult,
    pub route_decision: PersistArtifactResult,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct PersistArtifactResult {
    pub artifact_id: String,
    pub artifact_kind: ArtifactKind,
    pub path: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub json_path: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub toml_path: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub rendered_path: Option<String>,
    #[serde(default)]
    pub warnings: Vec<String>,
}

#[derive(Debug, Clone)]
pub struct SetApplicatorStatusParams {
    pub session: SessionLocator,
    pub status: ApplicatorStatus,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct ApplicatorWaitResult {
    pub status: ApplicatorStatus,
    pub parent_review_ready: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub parent_review: Option<ArtifactPointer>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, ValueEnum)]
#[serde(rename_all = "kebab-case")]
pub enum ReportView {
    All,
    Open,
    Closed,
    InProgress,
    Final,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct ReportEntry {
    pub reviewer_id: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub parent_id: Option<String>,
    pub role: String,
    pub role_kind: AgentRoleKind,
    pub status: ReviewProcessStatus,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub phase: Option<String>,
    pub agent_dir: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub report_path: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub artifact_id: Option<String>,
    pub child_count: usize,
    #[serde(default)]
    pub lineage: Vec<String>,
    #[serde(default)]
    pub warnings: Vec<String>,
    #[serde(default)]
    pub counters: AgentCounters,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub report_contents: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct ReportsResult {
    pub view: ReportView,
    pub recursive: bool,
    pub include_leaf_children: bool,
    #[serde(default)]
    pub reports: Vec<ReportEntry>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub concatenated_report: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub final_report_path: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct FinalSummary {
    pub session_id: String,
    pub target_ref: String,
    pub total_agents: u64,
    pub active_agents: u64,
    pub completed_agents: u64,
    pub report_count: u64,
    pub applied_findings: u64,
    pub declined_findings: u64,
    pub low_signal_rejections: u64,
    pub duplicate_rejections: u64,
    pub reopen_triggers: u64,
    #[serde(default)]
    pub severity_totals: BTreeMap<String, u64>,
    #[serde(default)]
    pub domain_totals: BTreeMap<String, u64>,
}

fn derive_repo_root(session_dir: &Path) -> anyhow::Result<PathBuf> {
    session_dir
        .parent()
        .and_then(Path::parent)
        .and_then(Path::parent)
        .and_then(Path::parent)
        .map(Path::to_path_buf)
        .ok_or_else(|| {
            anyhow::anyhow!(
                "error: could not derive repo root from {}",
                session_dir.display()
            )
        })
}

fn derive_session_date(session_dir: &Path) -> anyhow::Result<String> {
    session_dir
        .file_name()
        .map(|value| value.to_string_lossy().into_owned())
        .ok_or_else(|| anyhow::anyhow!("error: invalid session dir {}", session_dir.display()))
}

fn atomic_write(path: &Path, body: &str) -> anyhow::Result<()> {
    let parent = path
        .parent()
        .ok_or_else(|| anyhow::anyhow!("error: path {} has no parent", path.display()))?;
    fs::create_dir_all(parent).with_context(|| format!("create dir {}", parent.display()))?;
    let temp_path = path.with_extension("tmp");
    fs::write(&temp_path, body).with_context(|| format!("write {}", temp_path.display()))?;
    fs::rename(&temp_path, path)
        .with_context(|| format!("rename {} -> {}", temp_path.display(), path.display()))?;
    Ok(())
}

fn read_optional_text(path: &Path) -> anyhow::Result<Option<String>> {
    match fs::read_to_string(path) {
        Ok(body) => Ok(Some(body)),
        Err(err) if err.kind() == std::io::ErrorKind::NotFound => Ok(None),
        Err(err) => Err(err).with_context(|| format!("read {}", path.display())),
    }
}

fn parse_json<T: DeserializeOwned>(body: &str, label: &str) -> anyhow::Result<T> {
    serde_json::from_str(body).map_err(|err| anyhow::anyhow!("error: parse {label} JSON: {err}"))
}

fn parse_toml<T: DeserializeOwned>(body: &str, label: &str) -> anyhow::Result<T> {
    toml::from_str(body).map_err(|err| anyhow::anyhow!("error: parse {label} TOML: {err}"))
}

fn to_json_string<T: Serialize>(value: &T, label: &str) -> anyhow::Result<String> {
    serde_json::to_string_pretty(value)
        .map_err(|err| anyhow::anyhow!("error: serialize {label} JSON: {err}"))
}

fn to_toml_string<T: Serialize>(value: &T, label: &str) -> anyhow::Result<String> {
    toml::to_string_pretty(value)
        .map_err(|err| anyhow::anyhow!("error: serialize {label} TOML: {err}"))
}

fn storage_status(
    primary_format: StorageFormat,
    json_available: bool,
    toml_available: bool,
    degraded_warnings: Vec<String>,
) -> StorageStatus {
    let mut available_formats = Vec::new();
    if json_available {
        available_formats.push(StorageFormat::Json);
    }
    if toml_available {
        available_formats.push(StorageFormat::Toml);
    }
    StorageStatus {
        primary_format,
        available_formats,
        degraded_warnings,
    }
}

fn dual_write(
    json_path: &Path,
    toml_path: &Path,
    json_body: &str,
    toml_body: &str,
    label: &str,
) -> anyhow::Result<StorageStatus> {
    let json_result = atomic_write(json_path, json_body);
    let toml_result = atomic_write(toml_path, toml_body);
    match (json_result, toml_result) {
        (Ok(()), Ok(())) => Ok(storage_status(StorageFormat::Json, true, true, Vec::new())),
        (Ok(()), Err(toml_err)) => Ok(storage_status(
            StorageFormat::Json,
            true,
            false,
            vec![format!("{label}: TOML mirror write failed: {toml_err}")],
        )),
        (Err(json_err), Ok(())) => {
            let retry = atomic_write(json_path, json_body);
            match retry {
                Ok(()) => Ok(storage_status(
                    StorageFormat::Json,
                    true,
                    true,
                    vec![format!(
                        "{label}: JSON primary write failed but recovered after retry: {json_err}"
                    )],
                )),
                Err(retry_err) => Ok(storage_status(
                    StorageFormat::Toml,
                    false,
                    true,
                    vec![
                        format!("{label}: JSON primary write failed: {json_err}"),
                        format!("{label}: JSON retry failed: {retry_err}"),
                    ],
                )),
            }
        }
        (Err(json_err), Err(toml_err)) => Err(anyhow::anyhow!(
            "error: failed to persist {label}; JSON error: {json_err}; TOML error: {toml_err}"
        )),
    }
}

fn parse_session_body(body: &str, format: StorageFormat) -> anyhow::Result<SessionLedger> {
    if body.contains("proof_packet.v2")
        || body.contains("parent_review_report")
        || body.contains("schema_version = \"1.")
        || body.contains("\"schema_version\":\"1.")
    {
        return Err(anyhow::anyhow!(LEGACY_REJECTION_MESSAGE));
    }
    let session: SessionLedger = match format {
        StorageFormat::Json => parse_json(body, "session ledger")?,
        StorageFormat::Toml => parse_toml(body, "session ledger")?,
    };
    if session.schema_version != SESSION_SCHEMA_VERSION {
        return Err(anyhow::anyhow!(LEGACY_REJECTION_MESSAGE));
    }
    validate_session_id(&session.session_id)?;
    Ok(session)
}

fn session_paths_for(session: &SessionLedger) -> anyhow::Result<paths::SessionPaths> {
    let repo_root = PathBuf::from(&session.repo_root);
    let date = time::Date::parse(
        &session.session_date,
        &time::format_description::parse("[year]-[month]-[day]")?,
    )?;
    Ok(paths::session_paths(&repo_root, date))
}

fn new_session(locator: &SessionLocator, target_ref: &str) -> anyhow::Result<SessionLedger> {
    let session_id = id::random_id8()?;
    validate_session_id(&session_id)?;
    let repo_root = derive_repo_root(locator.session_dir())?;
    let created_at = now_rfc3339();
    let session_paths = session_paths_for(&SessionLedger {
        schema_version: SESSION_SCHEMA_VERSION.to_string(),
        session_id: session_id.clone(),
        session_date: derive_session_date(locator.session_dir())?,
        repo_root: repo_root.to_string_lossy().into_owned(),
        target_ref: target_ref.to_string(),
        created_at: created_at.clone(),
        updated_at: created_at.clone(),
        active_artifact_format: ACTIVE_ARTIFACT_FORMAT.to_string(),
        storage: StorageStatus::default(),
        agents_root: String::new(),
        final_report_path: None,
        final_summary_json_path: None,
        final_summary_toml_path: None,
        detected_languages: Vec::new(),
        language_research_refs: Vec::new(),
        current: CurrentArtifacts::default(),
        artifacts: Vec::new(),
        reviews: Vec::new(),
        applicator: ApplicatorState::default(),
        notes: Vec::new(),
        counters: SessionCounters::default(),
        telemetry: TelemetryLedger::default(),
        convergence: ConvergencePointers::default(),
    })?;
    Ok(SessionLedger {
        schema_version: SESSION_SCHEMA_VERSION.to_string(),
        session_id,
        session_date: derive_session_date(locator.session_dir())?,
        repo_root: repo_root.to_string_lossy().into_owned(),
        target_ref: target_ref.to_string(),
        created_at: created_at.clone(),
        updated_at: created_at,
        active_artifact_format: ACTIVE_ARTIFACT_FORMAT.to_string(),
        storage: storage_status(StorageFormat::Json, true, true, Vec::new()),
        agents_root: paths::repo_relative_path(&repo_root, &session_paths.agents_dir)?,
        final_report_path: Some(paths::repo_relative_path(
            &repo_root,
            &session_paths.final_report_file,
        )?),
        final_summary_json_path: Some(paths::repo_relative_path(
            &repo_root,
            &session_paths.final_summary_json_file,
        )?),
        final_summary_toml_path: Some(paths::repo_relative_path(
            &repo_root,
            &session_paths.final_summary_toml_file,
        )?),
        detected_languages: Vec::new(),
        language_research_refs: Vec::new(),
        current: CurrentArtifacts::default(),
        artifacts: Vec::new(),
        reviews: Vec::new(),
        applicator: ApplicatorState::default(),
        notes: Vec::new(),
        counters: SessionCounters::default(),
        telemetry: TelemetryLedger::default(),
        convergence: ConvergencePointers::default(),
    })
}

fn write_session_file(session: &mut SessionLedger, session_dir: &Path) -> anyhow::Result<()> {
    session.storage.degraded_warnings.clear();
    let json_path = paths::session_file(session_dir, StorageFormat::Json);
    let toml_path = paths::session_file(session_dir, StorageFormat::Toml);
    let json_body = to_json_string(session, "_session")?;
    let toml_body = to_toml_string(session, "_session")?;
    session.storage = dual_write(&json_path, &toml_path, &json_body, &toml_body, "_session")?;
    let json_body = to_json_string(session, "_session")?;
    let toml_body = to_toml_string(session, "_session")?;
    if session
        .storage
        .available_formats
        .contains(&StorageFormat::Json)
    {
        atomic_write(&json_path, &json_body)?;
    }
    if session
        .storage
        .available_formats
        .contains(&StorageFormat::Toml)
    {
        atomic_write(&toml_path, &toml_body)?;
    }
    Ok(())
}

fn read_existing_session(locator: &SessionLocator) -> anyhow::Result<Option<SessionLedger>> {
    let json_path = paths::session_file(locator.session_dir(), StorageFormat::Json);
    let toml_path = paths::session_file(locator.session_dir(), StorageFormat::Toml);
    let json_body = read_optional_text(&json_path)?;
    let toml_body = read_optional_text(&toml_path)?;
    match (json_body, toml_body) {
        (None, None) => Ok(None),
        (Some(body), None) => {
            let mut session = parse_session_body(&body, StorageFormat::Json)?;
            session.storage = storage_status(StorageFormat::Json, true, false, Vec::new());
            Ok(Some(session))
        }
        (None, Some(body)) => {
            let mut session = parse_session_body(&body, StorageFormat::Toml)?;
            session.storage = storage_status(StorageFormat::Toml, false, true, Vec::new());
            Ok(Some(session))
        }
        (Some(json_body), Some(toml_body)) => {
            let mut session = parse_session_body(&json_body, StorageFormat::Json)?;
            let toml_session = parse_session_body(&toml_body, StorageFormat::Toml)?;
            let mut warnings = Vec::new();
            if serde_json::to_value(&session)? != serde_json::to_value(&toml_session)? {
                warnings.push(
                    "_session: JSON and TOML diverged; JSON was treated as authoritative"
                        .to_string(),
                );
            }
            session.storage = storage_status(StorageFormat::Json, true, true, warnings);
            Ok(Some(session))
        }
    }
}

fn resolve_pointer_path(session: &SessionLedger, pointer: &ArtifactPointer) -> Option<PathBuf> {
    let repo_root = PathBuf::from(&session.repo_root);
    for candidate in [
        pointer.json_path.as_deref(),
        Some(pointer.path.as_str()),
        pointer.toml_path.as_deref(),
    ] {
        let Some(candidate) = candidate else {
            continue;
        };
        if candidate.is_empty() {
            continue;
        }
        let resolved = paths::resolve_repo_relative(&repo_root, candidate);
        if resolved.exists() {
            return Some(resolved);
        }
    }
    None
}

fn update_language_detection(session: &mut SessionLedger) {
    let mut languages = HashSet::new();
    for pointer in &session.artifacts {
        if pointer.artifact_kind != ArtifactKind::RouteDecision {
            continue;
        }
        let Some(path) = resolve_pointer_path(session, pointer) else {
            continue;
        };
        let Ok(ArtifactDocument::RouteDecision(route)) = parse_artifact_file(&path) else {
            continue;
        };
        for worker in route.worker_plan {
            if let Some(language) = worker.language {
                languages.insert(language);
            }
        }
    }
    let mut detected = languages.into_iter().collect::<Vec<_>>();
    detected.sort();
    session.detected_languages = detected;
}

#[derive(Debug, Clone, Default)]
struct CounterTally {
    artifact_count: u64,
    report_count: u64,
    findings: u64,
    applied_findings: u64,
    declined_findings: u64,
    low_signal_rejections: u64,
    duplicate_rejections: u64,
    reopen_triggers: u64,
    research_ref_count: u64,
    severity_totals: BTreeMap<String, u64>,
}

fn merge_counter_tallies(target: &mut CounterTally, source: &CounterTally) {
    target.artifact_count += source.artifact_count;
    target.report_count += source.report_count;
    target.findings += source.findings;
    target.applied_findings += source.applied_findings;
    target.declined_findings += source.declined_findings;
    target.low_signal_rejections += source.low_signal_rejections;
    target.duplicate_rejections += source.duplicate_rejections;
    target.reopen_triggers += source.reopen_triggers;
    target.research_ref_count += source.research_ref_count;
    for (severity, count) in &source.severity_totals {
        *target.severity_totals.entry(severity.clone()).or_insert(0) += count;
    }
}

fn counter_tally_from_artifact(document: &ArtifactDocument) -> CounterTally {
    let mut tally = CounterTally {
        artifact_count: 1,
        ..CounterTally::default()
    };
    match document {
        ArtifactDocument::ChildFindings(artifact) => {
            tally.findings = artifact.findings.len() as u64;
            for finding in &artifact.findings {
                *tally
                    .severity_totals
                    .entry(severity_text(finding.severity))
                    .or_insert(0) += 1;
            }
        }
        ArtifactDocument::ApplicationResult(artifact) => {
            for disposition in &artifact.dispositions {
                match disposition.disposition {
                    Disposition::Applied => tally.applied_findings += 1,
                    Disposition::Declined
                    | Disposition::Deferred
                    | Disposition::AlreadyAddressed => {
                        tally.declined_findings += 1;
                    }
                }
                if matches!(
                    disposition.decline_reason_code,
                    Some(
                        DeclineReasonCode::InvalidAnchor
                            | DeclineReasonCode::NonReproducible
                            | DeclineReasonCode::Hallucinated
                            | DeclineReasonCode::OutOfScope
                    )
                ) {
                    tally.low_signal_rejections += 1;
                }
                if disposition.duplicate_reason_code.is_some()
                    || disposition.decline_reason_code == Some(DeclineReasonCode::Duplicate)
                    || disposition.duplicate_suspect == Some(true)
                {
                    tally.duplicate_rejections += 1;
                }
            }
        }
        ArtifactDocument::ConvergenceState(artifact) => {
            tally.reopen_triggers = artifact.reopen_triggers.len() as u64;
        }
        ArtifactDocument::ParentReview(_)
        | ArtifactDocument::VerificationResult(_)
        | ArtifactDocument::RouteDecision(_)
        | ArtifactDocument::SurfaceMap(_)
        | ArtifactDocument::RouteRevision(_) => {}
    }
    tally
}

fn build_artifact_tally_cache(session: &SessionLedger) -> HashMap<String, CounterTally> {
    let mut tallies = HashMap::new();
    for pointer in &session.artifacts {
        let Some(path) = resolve_pointer_path(session, pointer) else {
            continue;
        };
        let Ok(document) = parse_artifact_file(&path) else {
            continue;
        };
        tallies.insert(
            pointer.artifact_id.clone(),
            counter_tally_from_artifact(&document),
        );
    }
    tallies
}

fn primary_root_reviewer_id(session: &SessionLedger) -> Option<String> {
    session
        .reviews
        .iter()
        .filter(|review| review.parent_id.is_none())
        .min_by(|left, right| {
            left.opened_at
                .cmp(&right.opened_at)
                .then_with(|| left.reviewer_id.cmp(&right.reviewer_id))
        })
        .map(|review| review.reviewer_id.clone())
}

fn build_session_overlay_tally(
    session: &SessionLedger,
    artifact_tallies: &HashMap<String, CounterTally>,
) -> CounterTally {
    let claimed_ids = session
        .reviews
        .iter()
        .filter_map(|review| review.artifact_id.as_deref())
        .collect::<HashSet<_>>();
    let mut overlay = CounterTally::default();
    for pointer in &session.artifacts {
        if claimed_ids.contains(pointer.artifact_id.as_str()) {
            continue;
        }
        if let Some(tally) = artifact_tallies.get(&pointer.artifact_id) {
            merge_counter_tallies(&mut overlay, tally);
        }
    }
    overlay
}

fn build_agent_counter_map(session: &SessionLedger) -> HashMap<String, AgentCounters> {
    let artifact_tallies = build_artifact_tally_cache(session);
    let session_overlay = build_session_overlay_tally(session, &artifact_tallies);
    let primary_root = primary_root_reviewer_id(session);
    let mut children_by_parent: HashMap<&str, Vec<&ReviewProcess>> = HashMap::new();
    for review in &session.reviews {
        if let Some(parent_id) = review.parent_id.as_deref() {
            children_by_parent
                .entry(parent_id)
                .or_default()
                .push(review);
        }
    }
    for children in children_by_parent.values_mut() {
        children.sort_by(|left, right| {
            left.opened_at
                .cmp(&right.opened_at)
                .then_with(|| left.reviewer_id.cmp(&right.reviewer_id))
        });
    }
    let mut roots = session
        .reviews
        .iter()
        .filter(|review| review.parent_id.is_none())
        .collect::<Vec<_>>();
    roots.sort_by(|left, right| {
        left.opened_at
            .cmp(&right.opened_at)
            .then_with(|| left.reviewer_id.cmp(&right.reviewer_id))
    });

    fn visit(
        review: &ReviewProcess,
        children_by_parent: &HashMap<&str, Vec<&ReviewProcess>>,
        artifact_tallies: &HashMap<String, CounterTally>,
        primary_root: Option<&str>,
        session_overlay: &CounterTally,
        counters_by_id: &mut HashMap<String, AgentCounters>,
    ) -> (CounterTally, u64) {
        let mut local = CounterTally {
            report_count: u64::from(review.report_path.is_some()),
            research_ref_count: review.research_refs.len() as u64,
            ..CounterTally::default()
        };
        if let Some(artifact_id) = review.artifact_id.as_deref() {
            if let Some(tally) = artifact_tallies.get(artifact_id) {
                merge_counter_tallies(&mut local, tally);
            }
        }
        let mut recursive = local.clone();
        let mut descendant_count = 0;
        if let Some(children) = children_by_parent.get(review.reviewer_id.as_str()) {
            for child in children {
                let (child_recursive, child_descendants) = visit(
                    child,
                    children_by_parent,
                    artifact_tallies,
                    primary_root,
                    session_overlay,
                    counters_by_id,
                );
                merge_counter_tallies(&mut recursive, &child_recursive);
                descendant_count += 1 + child_descendants;
            }
        }
        if primary_root == Some(review.reviewer_id.as_str()) {
            merge_counter_tallies(&mut recursive, session_overlay);
        }
        counters_by_id.insert(
            review.reviewer_id.clone(),
            AgentCounters {
                local_artifact_count: local.artifact_count,
                recursive_artifact_count: recursive.artifact_count,
                local_report_count: local.report_count,
                recursive_report_count: recursive.report_count,
                child_count: review.child_ids.len() as u64,
                descendant_count,
                local_findings: local.findings,
                recursive_findings: recursive.findings,
                local_applied_findings: local.applied_findings,
                recursive_applied_findings: recursive.applied_findings,
                local_declined_findings: local.declined_findings,
                recursive_declined_findings: recursive.declined_findings,
                local_low_signal_rejections: local.low_signal_rejections,
                recursive_low_signal_rejections: recursive.low_signal_rejections,
                local_duplicate_rejections: local.duplicate_rejections,
                recursive_duplicate_rejections: recursive.duplicate_rejections,
                local_reopen_triggers: local.reopen_triggers,
                recursive_reopen_triggers: recursive.reopen_triggers,
                local_research_ref_count: local.research_ref_count,
                recursive_research_ref_count: recursive.research_ref_count,
                local_severity_totals: local.severity_totals.clone(),
                recursive_severity_totals: recursive.severity_totals.clone(),
            },
        );
        (recursive, descendant_count)
    }

    let mut counters_by_id = HashMap::new();
    for root in roots {
        visit(
            root,
            &children_by_parent,
            &artifact_tallies,
            primary_root.as_deref(),
            &session_overlay,
            &mut counters_by_id,
        );
    }
    counters_by_id
}

fn recompute_counters(session: &mut SessionLedger) {
    session.counters.artifact_count = session.artifacts.len() as u64;
    session.counters.rendered_count = session
        .artifacts
        .iter()
        .filter(|artifact| artifact.rendered_path.is_some())
        .count() as u64;
    session.counters.reviewer_count = session.reviews.len() as u64;
    session.counters.note_count = session.notes.len() as u64;
    session.counters.total_agents = session.reviews.len() as u64;
    session.counters.active_agents = session
        .reviews
        .iter()
        .filter(|review| {
            matches!(
                review.status,
                ReviewProcessStatus::Registered
                    | ReviewProcessStatus::InProgress
                    | ReviewProcessStatus::Delegating
                    | ReviewProcessStatus::WaitingOnChildren
                    | ReviewProcessStatus::Synthesizing
                    | ReviewProcessStatus::Blocked
            )
        })
        .count() as u64;
    session.counters.completed_agents = session
        .reviews
        .iter()
        .filter(|review| review.status == ReviewProcessStatus::Completed)
        .count() as u64;
    session.counters.report_count = session
        .reviews
        .iter()
        .filter(|review| review.report_path.is_some())
        .count() as u64;
    session.counters.research_workers = session
        .reviews
        .iter()
        .filter(|review| review.role_kind == AgentRoleKind::LanguageResearch)
        .count() as u64;
    session.counters.applied_findings = 0;
    session.counters.declined_findings = 0;
    session.counters.low_signal_rejections = 0;
    session.counters.duplicate_rejections = 0;
    session.counters.reopen_triggers = 0;
    session.counters.severity_totals.clear();
    session.counters.domain_totals.clear();

    for review in &session.reviews {
        for module_id in &review.module_ids {
            *session
                .counters
                .domain_totals
                .entry(module_id_text(*module_id))
                .or_insert(0) += 1;
        }
    }

    for pointer in &session.artifacts {
        let Some(path) = resolve_pointer_path(session, pointer) else {
            continue;
        };
        let Ok(document) = parse_artifact_file(&path) else {
            continue;
        };
        match document {
            ArtifactDocument::ChildFindings(artifact) => {
                for finding in artifact.findings {
                    *session
                        .counters
                        .severity_totals
                        .entry(severity_text(finding.severity))
                        .or_insert(0) += 1;
                }
            }
            ArtifactDocument::ApplicationResult(artifact) => {
                for disposition in artifact.dispositions {
                    match disposition.disposition {
                        Disposition::Applied => session.counters.applied_findings += 1,
                        Disposition::Declined
                        | Disposition::Deferred
                        | Disposition::AlreadyAddressed => {
                            session.counters.declined_findings += 1;
                        }
                    }
                    if matches!(
                        disposition.decline_reason_code,
                        Some(
                            DeclineReasonCode::InvalidAnchor
                                | DeclineReasonCode::NonReproducible
                                | DeclineReasonCode::Hallucinated
                                | DeclineReasonCode::OutOfScope
                        )
                    ) {
                        session.counters.low_signal_rejections += 1;
                    }
                    if disposition.duplicate_reason_code.is_some()
                        || disposition.decline_reason_code == Some(DeclineReasonCode::Duplicate)
                        || disposition.duplicate_suspect == Some(true)
                    {
                        session.counters.duplicate_rejections += 1;
                    }
                }
            }
            ArtifactDocument::ConvergenceState(artifact) => {
                session.counters.reopen_triggers += artifact.reopen_triggers.len() as u64;
            }
            _ => {}
        }
    }

    update_language_detection(session);
}

fn lock_owner() -> String {
    match id::random_id8() {
        Ok(owner) => owner,
        Err(_err) => "lock0001".to_string(),
    }
}

fn upsert_current_pointer(current: &mut CurrentArtifacts, pointer: &ArtifactPointer) {
    match pointer.artifact_kind {
        ArtifactKind::RouteDecision => current.route_decision = Some(pointer.clone()),
        ArtifactKind::SurfaceMap => current.surface_map = Some(pointer.clone()),
        ArtifactKind::ChildFindings => current.child_findings = Some(pointer.clone()),
        ArtifactKind::ParentReview => current.parent_review = Some(pointer.clone()),
        ArtifactKind::ApplicationResult => current.application_result = Some(pointer.clone()),
        ArtifactKind::VerificationResult => current.verification_result = Some(pointer.clone()),
        ArtifactKind::ConvergenceState => current.convergence_state = Some(pointer.clone()),
        ArtifactKind::RouteRevision => current.route_revision = Some(pointer.clone()),
    }
}

fn ensure_review_paths(
    repo_root: &Path,
    session_dir: &Path,
    review: &mut ReviewProcess,
    parent_agent_dir: Option<&Path>,
) -> anyhow::Result<PathBuf> {
    let agent_dir = if !review.agent_dir.is_empty() {
        paths::resolve_repo_relative(repo_root, &review.agent_dir)
    } else if let Some(parent_agent_dir) = parent_agent_dir {
        paths::child_agent_dir(parent_agent_dir, &review.reviewer_id)
    } else {
        paths::root_agent_dir(session_dir, &review.reviewer_id)
    };
    paths::ensure_agent_layout(&agent_dir)?;
    review.agent_dir = paths::repo_relative_path(repo_root, &agent_dir)?;
    review.agent_ledger_json = paths::repo_relative_path(
        repo_root,
        &paths::agent_ledger_path(&agent_dir, StorageFormat::Json),
    )?;
    review.agent_ledger_toml = paths::repo_relative_path(
        repo_root,
        &paths::agent_ledger_path(&agent_dir, StorageFormat::Toml),
    )?;
    review.report_path = Some(paths::repo_relative_path(
        repo_root,
        &paths::agent_report_path(&agent_dir),
    )?);
    Ok(agent_dir)
}

fn artifact_pointer_for_review(
    session: &SessionLedger,
    review: &ReviewProcess,
) -> Option<ArtifactPointer> {
    review.artifact_id.as_ref().and_then(|artifact_id| {
        session
            .artifacts
            .iter()
            .find(|pointer| &pointer.artifact_id == artifact_id)
            .cloned()
    })
}

fn push_markdown_section(markdown: &mut String, title: &str, items: &[String], empty: &str) {
    markdown.push_str(&format!("## {title}\n\n"));
    if items.is_empty() {
        markdown.push_str(&format!("- {empty}\n\n"));
        return;
    }
    for item in items {
        markdown.push_str(&format!("- {item}\n"));
    }
    markdown.push('\n');
}

fn render_agent_report(review: &ReviewProcess, artifact: Option<&ArtifactDocument>) -> String {
    let mut markdown = String::new();
    markdown.push_str("# Agent Report\n\n");
    markdown.push_str(&format!(
        "- Reviewer: `{}`\n- Role: `{}`\n- Role kind: `{}`\n- Status: `{}`\n\n",
        review.reviewer_id,
        review.role,
        match review.role_kind {
            AgentRoleKind::DomainReviewer => "domain-reviewer",
            AgentRoleKind::LanguageDetector => "language-detector",
            AgentRoleKind::LanguageResearch => "language-research",
            AgentRoleKind::FinalSynthesis => "final-synthesis",
            AgentRoleKind::ApplicatorWorker => "applicator-worker",
            AgentRoleKind::ApplicatorVerifier => "applicator-verifier",
            AgentRoleKind::Helper => "helper",
        },
        status_text(review.status)
    ));
    if let Some(phase) = &review.phase {
        markdown.push_str(&format!("- Phase: `{phase}`\n\n"));
    }
    push_markdown_section(
        &mut markdown,
        "Scope",
        &review
            .module_ids
            .iter()
            .map(|module_id| format!("module `{}`", module_id_text(*module_id)))
            .chain(
                review
                    .focus_surfaces
                    .iter()
                    .map(|surface| format!("surface `{}`", surface_text(*surface))),
            )
            .chain(
                review
                    .claimed_scope
                    .iter()
                    .map(|scope| format!("claimed scope `{scope}`")),
            )
            .chain(
                review
                    .delegated_scope
                    .iter()
                    .map(|scope| format!("delegated scope `{scope}`")),
            )
            .collect::<Vec<_>>(),
        "scope pending",
    );
    push_markdown_section(
        &mut markdown,
        "Assumptions",
        &review
            .research_refs
            .iter()
            .map(|reference| {
                format!(
                    "research ref `{}` from `{}`",
                    reference.language, reference.agent_id
                )
            })
            .collect::<Vec<_>>(),
        "no explicit assumptions recorded",
    );
    match artifact {
        Some(ArtifactDocument::ChildFindings(child)) => {
            push_markdown_section(
                &mut markdown,
                "Invariants Or Theorems Checked",
                &child
                    .defended_checks
                    .iter()
                    .map(|check| format!("{}: {}", check.method, check.claim))
                    .collect::<Vec<_>>(),
                "no defended checks recorded",
            );
            push_markdown_section(
                &mut markdown,
                "Evidence",
                &child
                    .findings
                    .iter()
                    .map(|finding| finding.evidence.clone())
                    .collect::<Vec<_>>(),
                "no evidence recorded",
            );
            push_markdown_section(
                &mut markdown,
                "Findings",
                &child
                    .findings
                    .iter()
                    .map(|finding| {
                        format!(
                            "[{}] {}: {}",
                            severity_text(finding.severity),
                            finding.title,
                            finding.claim
                        )
                    })
                    .collect::<Vec<_>>(),
                "no findings recorded",
            );
            push_markdown_section(
                &mut markdown,
                "Defended Non-Findings",
                &child
                    .defended_checks
                    .iter()
                    .map(|check| format!("{}: {}", check.check_id, check.claim))
                    .collect::<Vec<_>>(),
                "no defended non-findings recorded",
            );
            push_markdown_section(
                &mut markdown,
                "Residual Risks",
                &child
                    .residual_risks
                    .iter()
                    .map(|risk| format!("{}: {}", risk.risk_id, risk.summary))
                    .collect::<Vec<_>>(),
                "no residual risks recorded",
            );
        }
        Some(ArtifactDocument::ParentReview(parent)) => {
            push_markdown_section(
                &mut markdown,
                "Invariants Or Theorems Checked",
                &parent
                    .defended_summary
                    .iter()
                    .map(|check| format!("{}: {}", check.check_id, check.claim))
                    .collect::<Vec<_>>(),
                "no defended checks recorded",
            );
            push_markdown_section(
                &mut markdown,
                "Findings",
                &parent
                    .required_now
                    .iter()
                    .chain(parent.follow_up.iter())
                    .map(|finding| {
                        format!(
                            "[{}] {}: {}",
                            severity_text(finding.severity),
                            finding.title,
                            finding.claim
                        )
                    })
                    .collect::<Vec<_>>(),
                "no findings recorded",
            );
            push_markdown_section(
                &mut markdown,
                "Residual Risks",
                &parent
                    .residual_risks
                    .iter()
                    .map(|risk| format!("{}: {}", risk.risk_id, risk.summary))
                    .collect::<Vec<_>>(),
                "no residual risks recorded",
            );
        }
        Some(other) => {
            push_markdown_section(
                &mut markdown,
                "Evidence",
                &[format!("artifact kind `{}` persisted", other.kind())],
                "no artifact finalized yet",
            );
        }
        None => {
            push_markdown_section(&mut markdown, "Evidence", &[], "no artifact finalized yet");
        }
    }
    push_markdown_section(
        &mut markdown,
        "Child Handoffs",
        &review.child_ids,
        "no child handoffs recorded",
    );
    markdown.push_str("## Push Or Stop Recommendation\n\n- Continue only for high-confidence, actionable evidence; stop on duplicate, low-signal, already-addressed, or out-of-scope concerns.\n");
    markdown
}

fn sync_agent_files_with_counters(
    session: &SessionLedger,
    review: &ReviewProcess,
    counters_by_id: &HashMap<String, AgentCounters>,
) -> anyhow::Result<StorageStatus> {
    let repo_root = PathBuf::from(&session.repo_root);
    let session_dir = session_paths_for(session)?.session_dir;
    let parent_agent_dir = review.parent_id.as_deref().and_then(|parent_id| {
        session
            .reviews
            .iter()
            .find(|candidate| candidate.reviewer_id == parent_id)
            .map(|parent| paths::resolve_repo_relative(&repo_root, &parent.agent_dir))
    });
    let mut review_copy = review.clone();
    let agent_dir = ensure_review_paths(
        &repo_root,
        &session_dir,
        &mut review_copy,
        parent_agent_dir.as_deref(),
    )?;
    let pointer = artifact_pointer_for_review(session, review);
    let artifact = pointer
        .as_ref()
        .and_then(|pointer| resolve_pointer_path(session, pointer))
        .map(|path| parse_artifact_file(&path))
        .transpose()?;

    atomic_write(
        &paths::agent_report_path(&agent_dir),
        &render_agent_report(&review_copy, artifact.as_ref()),
    )?;

    let pointer_manifest = AgentPointerManifest {
        artifacts: pointer.into_iter().collect(),
    };
    let mut ledger = AgentLedger {
        schema_version: AGENT_SCHEMA_VERSION.to_string(),
        session_id: session.session_id.clone(),
        reviewer_id: review_copy.reviewer_id.clone(),
        parent_id: review_copy.parent_id.clone(),
        role: review_copy.role.clone(),
        role_kind: review_copy.role_kind.clone(),
        status: review_copy.status,
        phase: review_copy.phase.clone(),
        agent_dir: review_copy.agent_dir.clone(),
        report_path: review_copy.report_path.clone(),
        child_ids: review_copy.child_ids.clone(),
        module_ids: review_copy.module_ids.clone(),
        focus_surfaces: review_copy.focus_surfaces.clone(),
        claimed_scope: review_copy.claimed_scope.clone(),
        delegated_scope: review_copy.delegated_scope.clone(),
        lineage: review_copy.lineage.clone(),
        research_refs: review_copy.research_refs.clone(),
        artifacts: pointer_manifest.artifacts.clone(),
        storage: review_copy.storage.clone(),
        counters: counters_by_id
            .get(&review_copy.reviewer_id)
            .map_or_else(AgentCounters::default, Clone::clone),
        opened_at: review_copy.opened_at.clone(),
        updated_at: review_copy.updated_at.clone(),
    };
    let ledger_json = to_json_string(&ledger, "_agent")?;
    let ledger_toml = to_toml_string(&ledger, "_agent")?;
    let storage = dual_write(
        &paths::agent_ledger_path(&agent_dir, StorageFormat::Json),
        &paths::agent_ledger_path(&agent_dir, StorageFormat::Toml),
        &ledger_json,
        &ledger_toml,
        "_agent",
    )?;
    ledger.storage = storage.clone();
    atomic_write(
        &paths::agent_ledger_path(&agent_dir, StorageFormat::Json),
        &to_json_string(&ledger, "_agent")?,
    )?;
    if storage.available_formats.contains(&StorageFormat::Toml) {
        atomic_write(
            &paths::agent_ledger_path(&agent_dir, StorageFormat::Toml),
            &to_toml_string(&ledger, "_agent")?,
        )?;
    }
    atomic_write(
        &paths::agent_children_path(&agent_dir, StorageFormat::Json),
        &to_json_string(
            &AgentChildrenManifest {
                child_ids: review.child_ids.clone(),
            },
            "children",
        )?,
    )?;
    atomic_write(
        &paths::agent_children_path(&agent_dir, StorageFormat::Toml),
        &to_toml_string(
            &AgentChildrenManifest {
                child_ids: review.child_ids.clone(),
            },
            "children",
        )?,
    )?;
    atomic_write(
        &paths::agent_artifacts_manifest_path(&agent_dir, StorageFormat::Json),
        &to_json_string(&pointer_manifest, "_artifacts")?,
    )?;
    atomic_write(
        &paths::agent_artifacts_manifest_path(&agent_dir, StorageFormat::Toml),
        &to_toml_string(&pointer_manifest, "_artifacts")?,
    )?;
    Ok(storage)
}

fn sync_agent_files(
    session: &SessionLedger,
    review: &ReviewProcess,
) -> anyhow::Result<StorageStatus> {
    let counters_by_id = build_agent_counter_map(session);
    sync_agent_files_with_counters(session, review, &counters_by_id)
}

fn refresh_all_agent_files(session: &mut SessionLedger) -> anyhow::Result<()> {
    let counters_by_id = build_agent_counter_map(session);
    let ordered_ids = ordered_reviews_postorder(session)
        .into_iter()
        .map(|review| review.reviewer_id.clone())
        .collect::<Vec<_>>();
    for reviewer_id in ordered_ids {
        let Some(index) = session
            .reviews
            .iter()
            .position(|review| review.reviewer_id == reviewer_id)
        else {
            continue;
        };
        let storage = {
            let snapshot = session.reviews[index].clone();
            sync_agent_files_with_counters(session, &snapshot, &counters_by_id)?
        };
        session.reviews[index].storage = storage;
    }
    Ok(())
}

fn ordered_reviews<'a>(session: &'a SessionLedger, recursive: bool) -> Vec<&'a ReviewProcess> {
    let mut roots = session
        .reviews
        .iter()
        .filter(|review| review.parent_id.is_none())
        .collect::<Vec<_>>();
    roots.sort_by(|left, right| {
        left.opened_at
            .cmp(&right.opened_at)
            .then_with(|| left.reviewer_id.cmp(&right.reviewer_id))
    });
    if !recursive {
        return roots;
    }
    let mut children_by_parent: HashMap<&str, Vec<&ReviewProcess>> = HashMap::new();
    for review in &session.reviews {
        if let Some(parent_id) = review.parent_id.as_deref() {
            children_by_parent
                .entry(parent_id)
                .or_default()
                .push(review);
        }
    }
    for children in children_by_parent.values_mut() {
        children.sort_by(|left, right| {
            left.opened_at
                .cmp(&right.opened_at)
                .then_with(|| left.reviewer_id.cmp(&right.reviewer_id))
        });
    }
    fn visit<'a>(
        review: &'a ReviewProcess,
        ordered: &mut Vec<&'a ReviewProcess>,
        children_by_parent: &HashMap<&'a str, Vec<&'a ReviewProcess>>,
    ) {
        ordered.push(review);
        if let Some(children) = children_by_parent.get(review.reviewer_id.as_str()) {
            for child in children {
                visit(child, ordered, children_by_parent);
            }
        }
    }
    let mut ordered = Vec::new();
    for root in roots {
        visit(root, &mut ordered, &children_by_parent);
    }
    ordered
}

fn ordered_reviews_postorder<'a>(session: &'a SessionLedger) -> Vec<&'a ReviewProcess> {
    let mut roots = session
        .reviews
        .iter()
        .filter(|review| review.parent_id.is_none())
        .collect::<Vec<_>>();
    roots.sort_by(|left, right| {
        left.opened_at
            .cmp(&right.opened_at)
            .then_with(|| left.reviewer_id.cmp(&right.reviewer_id))
    });

    let mut children_by_parent: HashMap<&str, Vec<&ReviewProcess>> = HashMap::new();
    for review in &session.reviews {
        if let Some(parent_id) = review.parent_id.as_deref() {
            children_by_parent
                .entry(parent_id)
                .or_default()
                .push(review);
        }
    }
    for children in children_by_parent.values_mut() {
        children.sort_by(|left, right| {
            left.opened_at
                .cmp(&right.opened_at)
                .then_with(|| left.reviewer_id.cmp(&right.reviewer_id))
        });
    }

    fn visit<'a>(
        review: &'a ReviewProcess,
        ordered: &mut Vec<&'a ReviewProcess>,
        children_by_parent: &HashMap<&'a str, Vec<&'a ReviewProcess>>,
    ) {
        if let Some(children) = children_by_parent.get(review.reviewer_id.as_str()) {
            for child in children {
                visit(child, ordered, children_by_parent);
            }
        }
        ordered.push(review);
    }

    let mut ordered = Vec::new();
    for root in roots {
        visit(root, &mut ordered, &children_by_parent);
    }
    ordered
}

fn review_matches_view(review: &ReviewProcess, view: ReportView) -> bool {
    match view {
        ReportView::All => true,
        ReportView::Open => matches!(
            review.status,
            ReviewProcessStatus::Registered
                | ReviewProcessStatus::InProgress
                | ReviewProcessStatus::Delegating
                | ReviewProcessStatus::WaitingOnChildren
                | ReviewProcessStatus::Synthesizing
                | ReviewProcessStatus::Blocked
        ),
        ReportView::Closed => matches!(
            review.status,
            ReviewProcessStatus::Completed
                | ReviewProcessStatus::Cancelled
                | ReviewProcessStatus::Error
        ),
        ReportView::InProgress => matches!(
            review.status,
            ReviewProcessStatus::InProgress
                | ReviewProcessStatus::Delegating
                | ReviewProcessStatus::WaitingOnChildren
                | ReviewProcessStatus::Synthesizing
        ),
        ReportView::Final => {
            review.parent_id.is_none() && review.status == ReviewProcessStatus::Completed
        }
    }
}

fn build_reports_result(
    session: &SessionLedger,
    view: ReportView,
    recursive: bool,
    include_leaf_children: bool,
    include_report_contents: bool,
    concatenate: bool,
) -> anyhow::Result<ReportsResult> {
    let repo_root = PathBuf::from(&session.repo_root);
    let counters_by_id = build_agent_counter_map(session);
    let mut reports = Vec::new();
    let traversal_is_recursive = recursive || include_leaf_children;
    for review in ordered_reviews(session, traversal_is_recursive) {
        if include_leaf_children && !recursive {
            let keep = review.parent_id.is_none() || review.child_ids.is_empty();
            if !keep {
                continue;
            }
        }
        if !review_matches_view(review, view) {
            continue;
        }
        let report_contents = if include_report_contents {
            review.report_path.as_ref().and_then(|path| {
                fs::read_to_string(paths::resolve_repo_relative(&repo_root, path)).ok()
            })
        } else {
            None
        };
        reports.push(ReportEntry {
            reviewer_id: review.reviewer_id.clone(),
            parent_id: review.parent_id.clone(),
            role: review.role.clone(),
            role_kind: review.role_kind.clone(),
            status: review.status,
            phase: review.phase.clone(),
            agent_dir: review.agent_dir.clone(),
            report_path: review.report_path.clone(),
            artifact_id: review.artifact_id.clone(),
            child_count: review.child_ids.len(),
            lineage: review.lineage.clone(),
            warnings: review.storage.degraded_warnings.clone(),
            counters: counters_by_id
                .get(&review.reviewer_id)
                .map_or_else(AgentCounters::default, Clone::clone),
            report_contents,
        });
    }
    let concatenated_report = if concatenate {
        let mut sections = vec![format!(
            "# Final Report\n\n- Session: `{}`\n- Target ref: `{}`\n",
            session.session_id, session.target_ref
        )];
        for review in ordered_reviews_postorder(session) {
            if !review_matches_view(review, view) {
                continue;
            }
            if include_leaf_children && !recursive {
                let keep = review.parent_id.is_none() || review.child_ids.is_empty();
                if !keep {
                    continue;
                }
            }
            if let Some(path) = &review.report_path {
                let absolute = paths::resolve_repo_relative(&repo_root, path);
                if let Ok(body) = fs::read_to_string(&absolute) {
                    sections.push(format!(
                        "\n---\n\n## Agent `{}`\n\n{}",
                        review.reviewer_id, body
                    ));
                }
            }
        }
        Some(sections.join("\n"))
    } else {
        None
    };
    Ok(ReportsResult {
        view,
        recursive,
        include_leaf_children,
        reports,
        concatenated_report,
        final_report_path: session.final_report_path.clone(),
    })
}

fn refresh_final_outputs(session: &mut SessionLedger) -> anyhow::Result<()> {
    let repo_root = PathBuf::from(&session.repo_root);
    let session_paths = session_paths_for(session)?;
    let reports = build_reports_result(session, ReportView::All, true, false, false, true)?;
    if let Some(report) = &reports.concatenated_report {
        atomic_write(&session_paths.final_report_file, report)?;
    }
    let summary = FinalSummary {
        session_id: session.session_id.clone(),
        target_ref: session.target_ref.clone(),
        total_agents: session.counters.total_agents,
        active_agents: session.counters.active_agents,
        completed_agents: session.counters.completed_agents,
        report_count: session.counters.report_count,
        applied_findings: session.counters.applied_findings,
        declined_findings: session.counters.declined_findings,
        low_signal_rejections: session.counters.low_signal_rejections,
        duplicate_rejections: session.counters.duplicate_rejections,
        reopen_triggers: session.counters.reopen_triggers,
        severity_totals: session.counters.severity_totals.clone(),
        domain_totals: session.counters.domain_totals.clone(),
    };
    dual_write(
        &session_paths.final_summary_json_file,
        &session_paths.final_summary_toml_file,
        &to_json_string(&summary, "final summary")?,
        &to_toml_string(&summary, "final summary")?,
        "final_summary",
    )?;
    session.final_report_path = Some(paths::repo_relative_path(
        &repo_root,
        &session_paths.final_report_file,
    )?);
    session.final_summary_json_path = Some(paths::repo_relative_path(
        &repo_root,
        &session_paths.final_summary_json_file,
    )?);
    session.final_summary_toml_path = Some(paths::repo_relative_path(
        &repo_root,
        &session_paths.final_summary_toml_file,
    )?);
    Ok(())
}

fn with_locked_session<T>(
    locator: &SessionLocator,
    action: impl FnOnce(&mut SessionLedger) -> anyhow::Result<T>,
) -> anyhow::Result<T> {
    paths::ensure_session_layout(locator.session_dir())?;
    let _guard = lock::acquire_lock(locator.session_dir(), lock_owner(), LockConfig::default())?;
    let mut session = read_existing_session(locator)?.ok_or_else(|| {
        anyhow::anyhow!("error: session does not exist yet; run `mpcr reviewer register` first")
    })?;
    let result = action(&mut session)?;
    session.updated_at = now_rfc3339();
    recompute_counters(&mut session);
    refresh_all_agent_files(&mut session)?;
    refresh_final_outputs(&mut session)?;
    write_session_file(&mut session, locator.session_dir())?;
    Ok(result)
}

fn with_target_session<T>(
    locator: &SessionLocator,
    target_ref: &str,
    action: impl FnOnce(&mut SessionLedger) -> anyhow::Result<T>,
) -> anyhow::Result<T> {
    paths::ensure_session_layout(locator.session_dir())?;
    let _guard = lock::acquire_lock(locator.session_dir(), lock_owner(), LockConfig::default())?;
    let mut session = match read_existing_session(locator)? {
        Some(session) => {
            anyhow::ensure!(
                session.target_ref == target_ref,
                "error: session target_ref `{}` does not match `{target_ref}`",
                session.target_ref
            );
            session
        }
        None => new_session(locator, target_ref)?,
    };
    let result = action(&mut session)?;
    session.updated_at = now_rfc3339();
    recompute_counters(&mut session);
    refresh_all_agent_files(&mut session)?;
    refresh_final_outputs(&mut session)?;
    write_session_file(&mut session, locator.session_dir())?;
    Ok(result)
}

fn create_or_load_session(
    locator: &SessionLocator,
    target_ref: &str,
) -> anyhow::Result<SessionLedger> {
    paths::ensure_session_layout(locator.session_dir())?;
    let _guard = lock::acquire_lock(locator.session_dir(), lock_owner(), LockConfig::default())?;
    let mut session = match read_existing_session(locator)? {
        Some(session) => session,
        None => new_session(locator, target_ref)?,
    };
    anyhow::ensure!(
        session.target_ref == target_ref,
        "error: session target_ref `{}` does not match `{target_ref}`",
        session.target_ref
    );
    session.updated_at = now_rfc3339();
    recompute_counters(&mut session);
    refresh_all_agent_files(&mut session)?;
    refresh_final_outputs(&mut session)?;
    write_session_file(&mut session, locator.session_dir())?;
    Ok(session)
}

fn persist_artifact(
    session: &mut SessionLedger,
    session_dir: &Path,
    artifact: &ArtifactDocument,
) -> anyhow::Result<PersistArtifactResult> {
    anyhow::ensure!(
        artifact.header().session_id == session.session_id,
        "error: artifact session_id `{}` does not match active session `{}`",
        artifact.header().session_id,
        session.session_id
    );
    anyhow::ensure!(
        artifact.header().target_ref == session.target_ref,
        "error: artifact target_ref `{}` does not match active target `{}`",
        artifact.header().target_ref,
        session.target_ref
    );
    let hard = validate_artifact_document(artifact, ValidationLayer::Hard, Some(session_dir))?;
    if !hard.errors.is_empty() {
        return Err(anyhow::anyhow!(
            "error: hard validation failed: {}",
            hard.errors.join("; ")
        ));
    }
    let soft = validate_artifact_document(artifact, ValidationLayer::Soft, Some(session_dir))?;
    let repo_root = PathBuf::from(&session.repo_root);
    let json_path = paths::artifact_path(
        session_dir,
        artifact.kind(),
        artifact.header().artifact_id.as_str(),
        StorageFormat::Json,
    );
    let toml_path = paths::artifact_path(
        session_dir,
        artifact.kind(),
        artifact.header().artifact_id.as_str(),
        StorageFormat::Toml,
    );
    let artifact_storage = dual_write(
        &json_path,
        &toml_path,
        &artifact.to_json_string()?,
        &artifact.to_toml_string()?,
        "artifact",
    )?;
    let rendered_path = if artifact.kind().supports_rendered_output() {
        let path = paths::rendered_path(
            session_dir,
            artifact.kind(),
            artifact.header().artifact_id.as_str(),
        );
        atomic_write(&path, &render_artifact_markdown(artifact)?)?;
        Some(paths::repo_relative_path(&repo_root, &path)?)
    } else {
        None
    };
    let pointer = ArtifactPointer {
        artifact_id: artifact.header().artifact_id.clone(),
        artifact_kind: artifact.kind(),
        path: match artifact_storage.primary_format {
            StorageFormat::Json => paths::repo_relative_path(&repo_root, &json_path)?,
            StorageFormat::Toml => paths::repo_relative_path(&repo_root, &toml_path)?,
        },
        json_path: json_path
            .exists()
            .then(|| paths::repo_relative_path(&repo_root, &json_path))
            .transpose()?,
        toml_path: toml_path
            .exists()
            .then(|| paths::repo_relative_path(&repo_root, &toml_path))
            .transpose()?,
        rendered_path: rendered_path.clone(),
        created_at: artifact.header().created_at.clone(),
    };
    if let Some(existing) = session
        .artifacts
        .iter_mut()
        .find(|existing| existing.artifact_id == pointer.artifact_id)
    {
        *existing = pointer.clone();
    } else {
        session.artifacts.push(pointer.clone());
        session.artifacts.sort_by(|left, right| {
            left.created_at
                .cmp(&right.created_at)
                .then_with(|| left.artifact_id.cmp(&right.artifact_id))
        });
    }
    upsert_current_pointer(&mut session.current, &pointer);
    if let ArtifactDocument::ConvergenceState(convergence) = artifact {
        session.convergence.current_artifact_id = Some(pointer.artifact_id.clone());
        session.convergence.cycle_index = convergence.cycle_index;
        session.convergence.stop_condition = Some(convergence.stop_condition.clone());
    }
    record_artifact(&mut session.telemetry, artifact);
    Ok(PersistArtifactResult {
        artifact_id: pointer.artifact_id,
        artifact_kind: pointer.artifact_kind,
        path: pointer.path.clone(),
        json_path: pointer.json_path.clone(),
        toml_path: pointer.toml_path.clone(),
        rendered_path,
        warnings: soft
            .warnings
            .into_iter()
            .chain(artifact_storage.degraded_warnings)
            .collect(),
    })
}

pub fn load_session(locator: &SessionLocator) -> anyhow::Result<SessionLedger> {
    read_existing_session(locator)?.ok_or_else(|| {
        anyhow::anyhow!("error: session does not exist yet; run `mpcr reviewer register` first")
    })
}

pub fn ensure_session(locator: &SessionLocator, target_ref: &str) -> anyhow::Result<SessionLedger> {
    create_or_load_session(locator, target_ref)
}

pub fn register_reviewer(params: RegisterReviewerParams) -> anyhow::Result<RegisterReviewerResult> {
    let mut registered = None;
    with_target_session(&params.session, &params.target_ref, |session| {
        let reviewer_id = params.reviewer_id.clone().map_or_else(id::random_id8, Ok)?;
        validate_session_id(&reviewer_id)?;
        let repo_root = PathBuf::from(&session.repo_root);
        let requested_role = match &params.role {
            Some(role) => role.clone(),
            None => default_review_role(),
        };
        let requested_role_kind = match params.role_kind {
            Some(role_kind) => role_kind,
            None => infer_role_kind(&requested_role),
        };
        let position = if let Some(position) = session
            .reviews
            .iter()
            .position(|review| review.reviewer_id == reviewer_id)
        {
            position
        } else {
            let now = now_rfc3339();
            session.reviews.push(ReviewProcess {
                reviewer_id: reviewer_id.clone(),
                parent_id: None,
                role: requested_role.clone(),
                role_kind: requested_role_kind,
                status: ReviewProcessStatus::Registered,
                phase: None,
                artifact_id: None,
                report_path: None,
                agent_dir: String::new(),
                agent_ledger_json: String::new(),
                agent_ledger_toml: String::new(),
                child_ids: Vec::new(),
                module_ids: module_ids_for_role(&requested_role),
                focus_surfaces: Vec::new(),
                claimed_scope: Vec::new(),
                delegated_scope: Vec::new(),
                lineage: review_lineage(session, None, &reviewer_id),
                research_refs: Vec::new(),
                storage: StorageStatus::default(),
                opened_at: now.clone(),
                updated_at: now,
            });
            session.reviews.len() - 1
        };
        let agent_dir = {
            let review = &mut session.reviews[position];
            ensure_review_paths(&repo_root, params.session.session_dir(), review, None)?
        };
        let storage = {
            let snapshot = session.reviews[position].clone();
            sync_agent_files(session, &snapshot)?
        };
        session.reviews[position].storage = storage;
        registered = Some(RegisterReviewerResult {
            session_dir: params.session.session_dir().to_string_lossy().into_owned(),
            session_id: session.session_id.clone(),
            reviewer_id: reviewer_id.clone(),
            target_ref: session.target_ref.clone(),
            agent_dir: paths::repo_relative_path(&repo_root, &agent_dir)?,
            agent_ledger_json: session.reviews[position].agent_ledger_json.clone(),
            agent_ledger_toml: session.reviews[position].agent_ledger_toml.clone(),
            session_format_primary: session.storage.primary_format,
        });
        Ok(())
    })?;
    registered.ok_or_else(|| anyhow::anyhow!("error: reviewer registration did not complete"))
}

pub fn spawn_child_reviewers(
    params: SpawnChildReviewersParams,
) -> anyhow::Result<SpawnChildReviewersResult> {
    let mut result = None;
    with_locked_session(&params.session, |session| {
        let repo_root = PathBuf::from(&session.repo_root);
        let parent_index = session
            .reviews
            .iter()
            .position(|review| review.reviewer_id == params.parent_id)
            .ok_or_else(|| {
                anyhow::anyhow!(
                    "error: parent reviewer `{}` was not found",
                    params.parent_id
                )
            })?;
        let parent_agent_dir = if session.reviews[parent_index].agent_dir.is_empty() {
            ensure_review_paths(
                &repo_root,
                params.session.session_dir(),
                &mut session.reviews[parent_index],
                None,
            )?
        } else {
            paths::resolve_repo_relative(&repo_root, &session.reviews[parent_index].agent_dir)
        };
        let parent_role = session.reviews[parent_index].role.clone();
        let now = now_rfc3339();
        let mut child_ids = Vec::new();
        let mut child_agent_dirs = Vec::new();
        let mut child_agent_ledgers_json = Vec::new();
        let mut child_agent_ledgers_toml = Vec::new();
        for _index in 0..params.count {
            let reviewer_id = id::random_id8()?;
            let role = params
                .role_id
                .clone()
                .or_else(|| {
                    params
                        .domain_id
                        .map(|domain_id| format!("domain:{}", module_id_text(domain_id)))
                })
                .or_else(|| {
                    params
                        .language
                        .as_ref()
                        .map(|language| match params.worker_kind {
                            Some(WorkerKind::LanguageDetector) => {
                                format!("language-detector:{language}")
                            }
                            Some(WorkerKind::LanguageResearch) => {
                                format!("language-research:{language}")
                            }
                            _ => format!("language:{language}"),
                        })
                })
                .map_or_else(|| parent_role.clone(), |role| role);
            session.reviews.push(ReviewProcess {
                reviewer_id: reviewer_id.clone(),
                parent_id: Some(params.parent_id.clone()),
                role: role.clone(),
                role_kind: infer_role_kind(&role),
                status: ReviewProcessStatus::Registered,
                phase: None,
                artifact_id: None,
                report_path: None,
                agent_dir: String::new(),
                agent_ledger_json: String::new(),
                agent_ledger_toml: String::new(),
                child_ids: Vec::new(),
                module_ids: if params.module_ids.is_empty() {
                    module_ids_for_role(&role)
                } else {
                    params.module_ids.clone()
                },
                focus_surfaces: params.focus_surfaces.clone(),
                claimed_scope: if params.claimed_scope.is_empty() {
                    vec![format!("parent:{parent_role}")]
                } else {
                    params.claimed_scope.clone()
                },
                delegated_scope: params.delegated_scope.clone(),
                lineage: review_lineage(session, Some(&params.parent_id), &reviewer_id),
                research_refs: session.language_research_refs.clone(),
                storage: StorageStatus::default(),
                opened_at: now.clone(),
                updated_at: now.clone(),
            });
            let child_index = session.reviews.len() - 1;
            let agent_dir = {
                let review = &mut session.reviews[child_index];
                ensure_review_paths(
                    &repo_root,
                    params.session.session_dir(),
                    review,
                    Some(&parent_agent_dir),
                )?
            };
            let storage = {
                let snapshot = session.reviews[child_index].clone();
                sync_agent_files(session, &snapshot)?
            };
            session.reviews[child_index].storage = storage;
            session.reviews[parent_index]
                .child_ids
                .push(reviewer_id.clone());
            child_ids.push(reviewer_id);
            child_agent_dirs.push(paths::repo_relative_path(&repo_root, &agent_dir)?);
            child_agent_ledgers_json.push(session.reviews[child_index].agent_ledger_json.clone());
            child_agent_ledgers_toml.push(session.reviews[child_index].agent_ledger_toml.clone());
        }
        let parent_storage = {
            let snapshot = session.reviews[parent_index].clone();
            sync_agent_files(session, &snapshot)?
        };
        session.reviews[parent_index].storage = parent_storage;
        result = Some(SpawnChildReviewersResult {
            child_ids,
            child_agent_dirs,
            child_agent_ledgers_json,
            child_agent_ledgers_toml,
            session_format_primary: session.storage.primary_format,
        });
        Ok(())
    })?;
    result.ok_or_else(|| anyhow::anyhow!("error: child reviewer spawn did not complete"))
}

pub fn close_child_reviews(
    params: CloseChildReviewsParams,
) -> anyhow::Result<CloseChildReviewsResult> {
    with_locked_session(&params.session, |session| {
        let now = now_rfc3339();
        let mut closed_ids = Vec::new();
        let parent_index = session
            .reviews
            .iter()
            .position(|review| review.reviewer_id == params.parent_id);
        for index in 0..session.reviews.len() {
            if session.reviews[index].parent_id.as_deref() != Some(params.parent_id.as_str())
                || session.reviews[index].status == ReviewProcessStatus::Completed
            {
                continue;
            }
            session.reviews[index].status = params.status;
            session.reviews[index].updated_at = now.clone();
            let storage = {
                let snapshot = session.reviews[index].clone();
                sync_agent_files(session, &snapshot)?
            };
            session.reviews[index].storage = storage;
            closed_ids.push(session.reviews[index].reviewer_id.clone());
        }
        if let Some(parent_index) = parent_index {
            let storage = {
                let snapshot = session.reviews[parent_index].clone();
                sync_agent_files(session, &snapshot)?
            };
            session.reviews[parent_index].storage = storage;
        }
        Ok(CloseChildReviewsResult { closed_ids })
    })
}

pub fn update_review(params: UpdateReviewParams) -> anyhow::Result<UpdateReviewResult> {
    with_locked_session(&params.session, |session| {
        let review = session
            .reviews
            .iter_mut()
            .find(|review| review.reviewer_id == params.reviewer_id)
            .ok_or_else(|| {
                anyhow::anyhow!("error: reviewer `{}` was not found", params.reviewer_id)
            })?;
        review.status = params.status;
        review.phase = params.phase.clone();
        review.updated_at = now_rfc3339();
        let reviewer_id = review.reviewer_id.clone();
        let storage = {
            let snapshot = review.clone();
            sync_agent_files(session, &snapshot)?
        };
        let review = session
            .reviews
            .iter_mut()
            .find(|review| review.reviewer_id == reviewer_id)
            .ok_or_else(|| {
                anyhow::anyhow!("error: reviewer `{}` was not found", params.reviewer_id)
            })?;
        review.storage = storage;
        Ok(UpdateReviewResult {
            reviewer_id: review.reviewer_id.clone(),
            status: review.status,
            phase: review.phase.clone(),
        })
    })
}

pub fn append_reviewer_note(params: AppendReviewerNoteParams) -> anyhow::Result<AppendNoteResult> {
    with_locked_session(&params.session, |session| {
        anyhow::ensure!(
            session
                .reviews
                .iter()
                .any(|review| review.reviewer_id == params.reviewer_id),
            "error: reviewer `{}` was not found",
            params.reviewer_id
        );
        session.notes.push(SessionNote {
            actor_kind: NoteActorKind::Reviewer,
            actor_id: params.reviewer_id.clone(),
            created_at: now_rfc3339(),
            content: params.content,
        });
        Ok(AppendNoteResult {
            note_count: session.notes.len(),
        })
    })
}

pub fn append_applicator_note(
    params: AppendApplicatorNoteParams,
) -> anyhow::Result<AppendNoteResult> {
    with_locked_session(&params.session, |session| {
        session.notes.push(SessionNote {
            actor_kind: NoteActorKind::Applicator,
            actor_id: session.session_id.clone(),
            created_at: now_rfc3339(),
            content: params.content,
        });
        Ok(AppendNoteResult {
            note_count: session.notes.len(),
        })
    })
}

pub fn complete_child_review(
    params: ReviewerArtifactParams,
) -> anyhow::Result<PersistArtifactResult> {
    let artifact = parse_artifact_file(&params.artifact_file)?;
    anyhow::ensure!(
        artifact.kind() == ArtifactKind::ChildFindings,
        "error: reviewer complete-child expects a child_findings artifact"
    );
    with_locked_session(&params.session, |session| {
        let review_index = session
            .reviews
            .iter()
            .position(|review| review.reviewer_id == params.reviewer_id)
            .ok_or_else(|| {
                anyhow::anyhow!("error: reviewer `{}` was not found", params.reviewer_id)
            })?;
        let result = persist_artifact(session, params.session.session_dir(), &artifact)?;
        {
            let review = &mut session.reviews[review_index];
            review.status = ReviewProcessStatus::Completed;
            review.phase = Some("child-findings-finalized".to_string());
            review.artifact_id = Some(result.artifact_id.clone());
            review.updated_at = now_rfc3339();
        }
        let storage = {
            let snapshot = session.reviews[review_index].clone();
            sync_agent_files(session, &snapshot)?
        };
        session.reviews[review_index].storage = storage;
        Ok(result)
    })
}

pub fn finalize_review(params: ReviewerArtifactParams) -> anyhow::Result<PersistArtifactResult> {
    let artifact = parse_artifact_file(&params.artifact_file)?;
    anyhow::ensure!(
        artifact.kind() == ArtifactKind::ParentReview,
        "error: reviewer finalize expects a parent_review artifact"
    );
    with_locked_session(&params.session, |session| {
        let review_index = session
            .reviews
            .iter()
            .position(|review| review.reviewer_id == params.reviewer_id)
            .ok_or_else(|| {
                anyhow::anyhow!("error: reviewer `{}` was not found", params.reviewer_id)
            })?;
        let result = persist_artifact(session, params.session.session_dir(), &artifact)?;
        {
            let review = &mut session.reviews[review_index];
            review.status = ReviewProcessStatus::Completed;
            review.phase = Some("parent-review-finalized".to_string());
            review.artifact_id = Some(result.artifact_id.clone());
            review.updated_at = now_rfc3339();
        }
        let storage = {
            let snapshot = session.reviews[review_index].clone();
            sync_agent_files(session, &snapshot)?
        };
        session.reviews[review_index].storage = storage;
        Ok(result)
    })
}

pub fn set_applicator_status(
    params: SetApplicatorStatusParams,
) -> anyhow::Result<ApplicatorStatus> {
    with_locked_session(&params.session, |session| {
        session.applicator.status = params.status;
        session.applicator.updated_at = now_rfc3339();
        Ok(session.applicator.status)
    })
}

pub fn applicator_wait(params: SessionLocator) -> anyhow::Result<ApplicatorWaitResult> {
    let session = load_session(&params)?;
    Ok(ApplicatorWaitResult {
        status: session.applicator.status,
        parent_review_ready: session.current.parent_review.is_some(),
        parent_review: session.current.parent_review,
    })
}

pub fn finalize_application(
    params: ApplicatorArtifactParams,
) -> anyhow::Result<PersistArtifactResult> {
    let artifact = parse_artifact_file(&params.artifact_file)?;
    anyhow::ensure!(
        artifact.kind() == ArtifactKind::ApplicationResult,
        "error: applicator finalize expects an application_result artifact"
    );
    with_locked_session(&params.session, |session| {
        let result = persist_artifact(session, params.session.session_dir(), &artifact)?;
        session.applicator.status = ApplicatorStatus::Verifying;
        session.applicator.updated_at = now_rfc3339();
        session.applicator.application_result_id = Some(result.artifact_id.clone());
        Ok(result)
    })
}

pub fn verify_application(
    params: ApplicatorArtifactParams,
) -> anyhow::Result<PersistArtifactResult> {
    let artifact = parse_artifact_file(&params.artifact_file)?;
    let verification = match artifact {
        ArtifactDocument::VerificationResult(verification) => verification,
        _ => {
            return Err(anyhow::anyhow!(
                "error: applicator verify expects a verification_result artifact"
            ))
        }
    };
    with_locked_session(&params.session, |session| {
        let result = persist_artifact(
            session,
            params.session.session_dir(),
            &ArtifactDocument::VerificationResult(verification.clone()),
        )?;
        session.applicator.status = if verification.failed_items.is_empty() {
            ApplicatorStatus::Completed
        } else {
            ApplicatorStatus::Blocked
        };
        session.applicator.updated_at = now_rfc3339();
        session.applicator.verification_result_id = Some(result.artifact_id.clone());
        Ok(result)
    })
}

pub fn persist_route_artifacts(
    params: PersistRouteArtifactsParams,
) -> anyhow::Result<PersistRouteArtifactsResult> {
    let PersistRouteArtifactsParams {
        session,
        target_ref,
        surface_map,
        route_decision,
    } = params;
    with_target_session(&session, &target_ref, |ledger| {
        let surface_map = persist_artifact(
            ledger,
            session.session_dir(),
            &ArtifactDocument::SurfaceMap(surface_map.clone()),
        )?;
        let route_decision = persist_artifact(
            ledger,
            session.session_dir(),
            &ArtifactDocument::RouteDecision(route_decision.clone()),
        )?;
        Ok(PersistRouteArtifactsResult {
            surface_map,
            route_decision,
        })
    })
}

pub fn apply_route_revision_artifact(
    params: ApplyRouteRevisionParams,
) -> anyhow::Result<ApplyRouteRevisionResult> {
    let artifact = parse_artifact_file(&params.artifact_file)?;
    let route_revision = match artifact {
        ArtifactDocument::RouteRevision(route_revision) => route_revision,
        _ => {
            return Err(anyhow::anyhow!(
                "error: session apply-route-revision expects a route_revision artifact"
            ))
        }
    };
    with_locked_session(&params.session, |session| {
        let current_route = session
            .current
            .route_decision
            .as_ref()
            .ok_or_else(|| anyhow::anyhow!("error: no current route_decision is persisted"))?;
        let current_route_path = resolve_pointer_path(session, current_route).ok_or_else(|| {
            anyhow::anyhow!("error: route_decision pointer could not be resolved")
        })?;
        let current_route = match parse_artifact_file(&current_route_path)? {
            ArtifactDocument::RouteDecision(route) => route,
            _ => {
                return Err(anyhow::anyhow!(
                    "error: current route_decision pointer did not resolve to a route_decision artifact"
                ))
            }
        };
        let revision_request = crate::router_types::RouteRevisionRequest {
            discovered_surfaces: route_revision
                .discovered_surfaces
                .iter()
                .map(|surface| surface.surface_id)
                .collect(),
            added_modules: route_revision.added_modules.clone(),
            raise_rigor: route_revision.rigor_change.is_some(),
            widen_architecture: route_revision.architecture_change.is_some(),
        };
        let mut revised_route =
            crate::router::apply_route_revision(&current_route, &revision_request);
        revised_route.header = crate::artifacts::ArtifactHeader::new(
            ArtifactKind::RouteDecision,
            id::random_hex_id(6)?,
            session.session_id.clone(),
            session.target_ref.clone(),
            crate::artifacts::ProducerKind::Router,
            now_rfc3339(),
            current_route.header.confidence_label,
            current_route.header.confidence_score,
            crate::router::default_router_policy_refs(&revised_route.selected_modules),
        )?;
        let route_revision = persist_artifact(
            session,
            params.session.session_dir(),
            &ArtifactDocument::RouteRevision(route_revision.clone()),
        )?;
        let route_decision = persist_artifact(
            session,
            params.session.session_dir(),
            &ArtifactDocument::RouteDecision(revised_route),
        )?;
        Ok(ApplyRouteRevisionResult {
            route_revision,
            route_decision,
        })
    })
}

pub fn checkpoint_convergence_state(
    params: ApplicatorArtifactParams,
) -> anyhow::Result<PersistArtifactResult> {
    let artifact = parse_artifact_file(&params.artifact_file)?;
    anyhow::ensure!(
        artifact.kind() == ArtifactKind::ConvergenceState,
        "error: fullcycle checkpoint expects a convergence_state artifact"
    );
    with_locked_session(&params.session, |session| {
        let result = persist_artifact(session, params.session.session_dir(), &artifact)?;
        if let ArtifactDocument::ConvergenceState(convergence) = artifact {
            if convergence.stop_condition == "terminal_cleanup"
                && convergence.terminal_cleanup_allowed
            {
                session.convergence.terminal_cleanup_consumed = true;
            }
        }
        Ok(result)
    })
}

pub fn list_artifacts(session: &SessionLedger, kind: Option<ArtifactKind>) -> Vec<ArtifactPointer> {
    session
        .artifacts
        .iter()
        .filter(|artifact| kind.is_none_or(|expected| artifact.artifact_kind == expected))
        .cloned()
        .collect()
}

pub fn collect_reports(
    locator: &SessionLocator,
    view: ReportView,
    recursive: bool,
    include_leaf_children: bool,
    include_report_contents: bool,
    concatenate: bool,
) -> anyhow::Result<ReportsResult> {
    let session = load_session(locator)?;
    build_reports_result(
        &session,
        view,
        recursive,
        include_leaf_children,
        include_report_contents,
        concatenate,
    )
}

pub fn cleanup_session(locator: &SessionLocator) -> anyhow::Result<PathBuf> {
    let session = load_session(locator)?;
    let repo_root = PathBuf::from(session.repo_root);
    let scratch_dir = paths::scratch_dir(&repo_root);
    if scratch_dir.exists() {
        fs::remove_dir_all(&scratch_dir)
            .with_context(|| format!("remove scratch dir {}", scratch_dir.display()))?;
    }
    Ok(scratch_dir)
}
