//! Compact v2 session ledger and reviewer/applicator operations.
#![allow(clippy::module_name_repetitions)]
#![allow(missing_docs)]

use crate::artifacts::{
    now_rfc3339, parse_artifact_file, validate_session_id, ArtifactDocument, ArtifactKind,
    LEGACY_REJECTION_MESSAGE, SESSION_SCHEMA_VERSION,
};
use crate::id;
use crate::lock::{self, LockConfig};
use crate::metrics::{record_artifact, TelemetryLedger};
use crate::paths;
use crate::render::render_artifact_markdown;
use crate::validate::{validate_artifact_document, ValidationLayer};
use anyhow::Context;
use clap::ValueEnum;
use serde::{Deserialize, Serialize};
use std::fs;
use std::path::{Path, PathBuf};

const ACTIVE_ARTIFACT_FORMAT: &str = "mpcr_artifact.v1";

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
/// Points to a canonical artifact stored under the session day directory.
pub struct ArtifactPointer {
    pub artifact_id: String,
    pub artifact_kind: ArtifactKind,
    pub path: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub rendered_path: Option<String>,
    pub created_at: String,
}

#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
/// Current artifact pointers held by the compact session ledger.
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
/// Lightweight reviewer status persisted in the compact session ledger.
pub enum ReviewProcessStatus {
    Registered,
    InProgress,
    Completed,
    Cancelled,
    Error,
    Blocked,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, ValueEnum)]
#[serde(rename_all = "snake_case")]
/// Applicator status persisted in the compact session ledger.
pub enum ApplicatorStatus {
    Waiting,
    Reviewing,
    Applying,
    Verifying,
    Completed,
    Blocked,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
/// Minimal reviewer process record.
pub struct ReviewProcess {
    pub reviewer_id: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub parent_id: Option<String>,
    pub status: ReviewProcessStatus,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub phase: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub artifact_id: Option<String>,
    pub opened_at: String,
    pub updated_at: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
/// Minimal applicator state.
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
/// Actor that authored a session note.
pub enum NoteActorKind {
    Reviewer,
    Applicator,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
/// Compact note entry persisted in the session ledger.
pub struct SessionNote {
    pub actor_kind: NoteActorKind,
    pub actor_id: String,
    pub created_at: String,
    pub content: String,
}

#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
/// Compact counters persisted in the session ledger.
pub struct SessionCounters {
    pub artifact_count: u64,
    pub rendered_count: u64,
    pub reviewer_count: u64,
    pub note_count: u64,
}

#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
/// Convergence pointers persisted in the session ledger.
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
/// Compact v2 session ledger.
pub struct SessionLedger {
    pub schema_version: String,
    pub session_id: String,
    pub session_date: String,
    pub repo_root: String,
    pub target_ref: String,
    pub created_at: String,
    pub updated_at: String,
    pub active_artifact_format: String,
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

#[derive(Debug, Clone)]
/// Session locator used by CLI commands.
pub struct SessionLocator {
    session_dir: PathBuf,
}

impl SessionLocator {
    /// Create a locator from an explicit session directory.
    #[must_use]
    pub fn from_session_dir(session_dir: PathBuf) -> Self {
        Self { session_dir }
    }

    /// Resolved session directory.
    #[must_use]
    pub fn session_dir(&self) -> &Path {
        &self.session_dir
    }
}

#[derive(Debug, Clone)]
/// Parameters for `reviewer register`.
pub struct RegisterReviewerParams {
    pub session: SessionLocator,
    pub target_ref: String,
    pub reviewer_id: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
/// Result payload for `reviewer register`.
pub struct RegisterReviewerResult {
    pub session_dir: String,
    pub session_id: String,
    pub reviewer_id: String,
    pub target_ref: String,
}

#[derive(Debug, Clone)]
/// Parameters for `reviewer spawn-children`.
pub struct SpawnChildReviewersParams {
    pub session: SessionLocator,
    pub parent_id: String,
    pub count: u8,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
/// Result payload for `reviewer spawn-children`.
pub struct SpawnChildReviewersResult {
    pub child_ids: Vec<String>,
}

#[derive(Debug, Clone)]
/// Parameters for `reviewer close-children`.
pub struct CloseChildReviewsParams {
    pub session: SessionLocator,
    pub parent_id: String,
    pub status: ReviewProcessStatus,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
/// Result payload for `reviewer close-children`.
pub struct CloseChildReviewsResult {
    pub closed_ids: Vec<String>,
}

#[derive(Debug, Clone)]
/// Parameters for `reviewer update`.
pub struct UpdateReviewParams {
    pub session: SessionLocator,
    pub reviewer_id: String,
    pub status: ReviewProcessStatus,
    pub phase: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
/// Result payload for `reviewer update`.
pub struct UpdateReviewResult {
    pub reviewer_id: String,
    pub status: ReviewProcessStatus,
    pub phase: Option<String>,
}

#[derive(Debug, Clone)]
/// Parameters for `reviewer note`.
pub struct AppendReviewerNoteParams {
    pub session: SessionLocator,
    pub reviewer_id: String,
    pub content: String,
}

#[derive(Debug, Clone)]
/// Parameters for `applicator note`.
pub struct AppendApplicatorNoteParams {
    pub session: SessionLocator,
    pub content: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
/// Result payload for note append operations.
pub struct AppendNoteResult {
    pub note_count: usize,
}

#[derive(Debug, Clone)]
/// Parameters for reviewer artifact finalization.
pub struct ReviewerArtifactParams {
    pub session: SessionLocator,
    pub reviewer_id: String,
    pub artifact_file: PathBuf,
}

#[derive(Debug, Clone)]
/// Parameters for applicator artifact finalization.
pub struct ApplicatorArtifactParams {
    pub session: SessionLocator,
    pub artifact_file: PathBuf,
}

#[derive(Debug, Clone)]
/// Parameters for persisted routing outputs.
pub struct PersistRouteArtifactsParams {
    pub session: SessionLocator,
    pub target_ref: String,
    pub surface_map: crate::artifacts::SurfaceMapArtifact,
    pub route_decision: crate::artifacts::RouteDecisionArtifact,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
/// Result payload for persisted route outputs.
pub struct PersistRouteArtifactsResult {
    pub surface_map: PersistArtifactResult,
    pub route_decision: PersistArtifactResult,
}

#[derive(Debug, Clone)]
/// Parameters for applying a persisted route revision to the current route.
pub struct ApplyRouteRevisionParams {
    pub session: SessionLocator,
    pub artifact_file: PathBuf,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
/// Result payload for route revision application.
pub struct ApplyRouteRevisionResult {
    pub route_revision: PersistArtifactResult,
    pub route_decision: PersistArtifactResult,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
/// Result for persisted artifact flows.
pub struct PersistArtifactResult {
    pub artifact_id: String,
    pub artifact_kind: ArtifactKind,
    pub path: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub rendered_path: Option<String>,
    #[serde(default)]
    pub warnings: Vec<String>,
}

#[derive(Debug, Clone)]
/// Parameters for applicator status updates.
pub struct SetApplicatorStatusParams {
    pub session: SessionLocator,
    pub status: ApplicatorStatus,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
/// Result payload for `applicator wait`.
pub struct ApplicatorWaitResult {
    pub status: ApplicatorStatus,
    pub parent_review_ready: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub parent_review: Option<ArtifactPointer>,
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

fn write_session_file(session: &SessionLedger, session_dir: &Path) -> anyhow::Result<()> {
    let body = toml::to_string_pretty(session)?;
    atomic_write(&session_dir.join("_session.toml"), &body)
}

fn read_session_file(session_dir: &Path) -> anyhow::Result<Option<String>> {
    let path = session_dir.join("_session.toml");
    match fs::read_to_string(&path) {
        Ok(body) => Ok(Some(body)),
        Err(err) if err.kind() == std::io::ErrorKind::NotFound => Ok(None),
        Err(err) => Err(err).with_context(|| format!("read {}", path.display())),
    }
}

fn read_existing_session(locator: &SessionLocator) -> anyhow::Result<Option<SessionLedger>> {
    if locator.session_dir().join("_session.json").exists() {
        return Err(anyhow::anyhow!(LEGACY_REJECTION_MESSAGE));
    }
    let Some(body) = read_session_file(locator.session_dir())? else {
        return Ok(None);
    };
    if body.contains("schema_version = \"1.")
        || body.contains("proof_packet.v2")
        || body.contains("parent_review_report")
    {
        return Err(anyhow::anyhow!(LEGACY_REJECTION_MESSAGE));
    }
    let session: SessionLedger = toml::from_str(&body)
        .map_err(|err| anyhow::anyhow!("error: parse session ledger: {err}"))?;
    if session.schema_version != SESSION_SCHEMA_VERSION {
        return Err(anyhow::anyhow!(LEGACY_REJECTION_MESSAGE));
    }
    validate_session_id(&session.session_id)?;
    Ok(Some(session))
}

fn new_session(locator: &SessionLocator, target_ref: &str) -> anyhow::Result<SessionLedger> {
    let session_id = id::random_id8()?;
    validate_session_id(&session_id)?;
    let repo_root = derive_repo_root(locator.session_dir())?;
    let created_at = now_rfc3339();
    Ok(SessionLedger {
        schema_version: SESSION_SCHEMA_VERSION.to_string(),
        session_id,
        session_date: derive_session_date(locator.session_dir())?,
        repo_root: repo_root.to_string_lossy().into_owned(),
        target_ref: target_ref.to_string(),
        created_at: created_at.clone(),
        updated_at: created_at.clone(),
        active_artifact_format: ACTIVE_ARTIFACT_FORMAT.to_string(),
        current: CurrentArtifacts::default(),
        artifacts: Vec::new(),
        reviews: Vec::new(),
        applicator: ApplicatorState {
            updated_at: created_at.clone(),
            ..ApplicatorState::default()
        },
        notes: Vec::new(),
        counters: SessionCounters::default(),
        telemetry: TelemetryLedger::default(),
        convergence: ConvergencePointers::default(),
    })
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
}

fn lock_owner() -> String {
    match id::random_id8() {
        Ok(owner) => owner,
        Err(_err) => "lock0001".to_string(),
    }
}

fn with_locked_session<T>(
    locator: &SessionLocator,
    action: impl FnOnce(&mut SessionLedger) -> anyhow::Result<T>,
) -> anyhow::Result<T> {
    paths::ensure_session_layout(locator.session_dir())?;
    let owner = lock_owner();
    let _guard = lock::acquire_lock(locator.session_dir(), owner, LockConfig::default())?;
    let mut session = match read_existing_session(locator)? {
        Some(session) => session,
        None => {
            return Err(anyhow::anyhow!(
                "error: session does not exist yet; run `mpcr reviewer register` first"
            ))
        }
    };
    let result = action(&mut session)?;
    session.updated_at = now_rfc3339();
    recompute_counters(&mut session);
    write_session_file(&session, locator.session_dir())?;
    Ok(result)
}

fn with_target_session<T>(
    locator: &SessionLocator,
    target_ref: &str,
    action: impl FnOnce(&mut SessionLedger) -> anyhow::Result<T>,
) -> anyhow::Result<T> {
    paths::ensure_session_layout(locator.session_dir())?;
    let owner = lock_owner();
    let _guard = lock::acquire_lock(locator.session_dir(), owner, LockConfig::default())?;
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
    write_session_file(&session, locator.session_dir())?;
    Ok(result)
}

fn create_or_load_session(
    locator: &SessionLocator,
    target_ref: &str,
) -> anyhow::Result<SessionLedger> {
    paths::ensure_session_layout(locator.session_dir())?;
    let owner = lock_owner();
    let _guard = lock::acquire_lock(locator.session_dir(), owner, LockConfig::default())?;
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
    write_session_file(&session, locator.session_dir())?;
    Ok(session)
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
    let artifact_path = paths::artifact_path(
        session_dir,
        artifact.kind(),
        artifact.header().artifact_id.as_str(),
    );
    let artifact_body = artifact.to_toml_string()?;
    atomic_write(&artifact_path, &artifact_body)?;

    let rendered_path = if artifact.kind().supports_rendered_output() {
        let markdown = render_artifact_markdown(artifact)?;
        let path = paths::rendered_path(
            session_dir,
            artifact.kind(),
            artifact.header().artifact_id.as_str(),
        );
        atomic_write(&path, &markdown)?;
        Some(paths::repo_relative_path(&repo_root, &path)?)
    } else {
        None
    };

    let pointer = ArtifactPointer {
        artifact_id: artifact.header().artifact_id.clone(),
        artifact_kind: artifact.kind(),
        path: paths::repo_relative_path(&repo_root, &artifact_path)?,
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
    if artifact.kind() == ArtifactKind::ConvergenceState {
        if let ArtifactDocument::ConvergenceState(convergence) = artifact {
            session.convergence.current_artifact_id = Some(pointer.artifact_id.clone());
            session.convergence.cycle_index = convergence.cycle_index;
            session.convergence.stop_condition = Some(convergence.stop_condition.clone());
        }
    }
    record_artifact(&mut session.telemetry, artifact);

    Ok(PersistArtifactResult {
        artifact_id: pointer.artifact_id,
        artifact_kind: pointer.artifact_kind,
        path: pointer.path,
        rendered_path,
        warnings: soft.warnings,
    })
}

/// Load the active compact session ledger.
///
/// # Errors
/// Returns an error if the session is missing, malformed, or legacy.
pub fn load_session(locator: &SessionLocator) -> anyhow::Result<SessionLedger> {
    read_existing_session(locator)?.ok_or_else(|| {
        anyhow::anyhow!("error: session does not exist yet; run `mpcr reviewer register` first")
    })
}

/// Ensure the active v2 session exists for the requested target ref.
pub fn ensure_session(locator: &SessionLocator, target_ref: &str) -> anyhow::Result<SessionLedger> {
    create_or_load_session(locator, target_ref)
}

/// Register or reuse the active v2 session and add a reviewer process.
pub fn register_reviewer(params: RegisterReviewerParams) -> anyhow::Result<RegisterReviewerResult> {
    let mut session = create_or_load_session(&params.session, &params.target_ref)?;
    let reviewer_id = match params.reviewer_id {
        Some(reviewer_id) => reviewer_id,
        None => id::random_id8()?,
    };
    validate_session_id(&reviewer_id)?;
    if !session
        .reviews
        .iter()
        .any(|review| review.reviewer_id == reviewer_id)
    {
        let now = now_rfc3339();
        session.reviews.push(ReviewProcess {
            reviewer_id: reviewer_id.clone(),
            parent_id: None,
            status: ReviewProcessStatus::Registered,
            phase: None,
            artifact_id: None,
            opened_at: now.clone(),
            updated_at: now,
        });
        session.updated_at = now_rfc3339();
        recompute_counters(&mut session);
        write_session_file(&session, params.session.session_dir())?;
    }

    Ok(RegisterReviewerResult {
        session_dir: params.session.session_dir().to_string_lossy().into_owned(),
        session_id: session.session_id,
        reviewer_id,
        target_ref: session.target_ref,
    })
}

/// Spawn bounded child reviewers under a parent reviewer.
pub fn spawn_child_reviewers(
    params: SpawnChildReviewersParams,
) -> anyhow::Result<SpawnChildReviewersResult> {
    with_locked_session(&params.session, |session| {
        anyhow::ensure!(
            session
                .reviews
                .iter()
                .any(|review| review.reviewer_id == params.parent_id && review.parent_id.is_none()),
            "error: parent reviewer `{}` was not found",
            params.parent_id
        );
        let now = now_rfc3339();
        let mut child_ids = Vec::new();
        for _ in 0..params.count {
            let reviewer_id = id::random_id8()?;
            session.reviews.push(ReviewProcess {
                reviewer_id: reviewer_id.clone(),
                parent_id: Some(params.parent_id.clone()),
                status: ReviewProcessStatus::Registered,
                phase: None,
                artifact_id: None,
                opened_at: now.clone(),
                updated_at: now.clone(),
            });
            child_ids.push(reviewer_id);
        }
        Ok(SpawnChildReviewersResult { child_ids })
    })
}

/// Close child reviewers under a parent.
pub fn close_child_reviews(
    params: CloseChildReviewsParams,
) -> anyhow::Result<CloseChildReviewsResult> {
    with_locked_session(&params.session, |session| {
        let now = now_rfc3339();
        let mut closed_ids = Vec::new();
        for review in &mut session.reviews {
            if review.parent_id.as_deref() == Some(params.parent_id.as_str())
                && review.status != ReviewProcessStatus::Completed
            {
                review.status = params.status;
                review.updated_at = now.clone();
                closed_ids.push(review.reviewer_id.clone());
            }
        }
        Ok(CloseChildReviewsResult { closed_ids })
    })
}

/// Update a reviewer process record.
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
        Ok(UpdateReviewResult {
            reviewer_id: review.reviewer_id.clone(),
            status: review.status,
            phase: review.phase.clone(),
        })
    })
}

/// Append a reviewer note to the session ledger.
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
            content: params.content.clone(),
        });
        Ok(AppendNoteResult {
            note_count: session.notes.len(),
        })
    })
}

/// Append an applicator note to the session ledger.
pub fn append_applicator_note(
    params: AppendApplicatorNoteParams,
) -> anyhow::Result<AppendNoteResult> {
    with_locked_session(&params.session, |session| {
        session.notes.push(SessionNote {
            actor_kind: NoteActorKind::Applicator,
            actor_id: session.session_id.clone(),
            created_at: now_rfc3339(),
            content: params.content.clone(),
        });
        Ok(AppendNoteResult {
            note_count: session.notes.len(),
        })
    })
}

/// Persist a canonical child-findings artifact and attach it to a reviewer.
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
        let review = &mut session.reviews[review_index];
        review.status = ReviewProcessStatus::Completed;
        review.phase = Some("child-findings-finalized".to_string());
        review.artifact_id = Some(result.artifact_id.clone());
        review.updated_at = now_rfc3339();
        Ok(result)
    })
}

/// Persist a canonical parent-review artifact and attach it to a reviewer.
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
        let review = &mut session.reviews[review_index];
        review.status = ReviewProcessStatus::Completed;
        review.phase = Some("parent-review-finalized".to_string());
        review.artifact_id = Some(result.artifact_id.clone());
        review.updated_at = now_rfc3339();
        Ok(result)
    })
}

/// Update the applicator status.
pub fn set_applicator_status(
    params: SetApplicatorStatusParams,
) -> anyhow::Result<ApplicatorStatus> {
    with_locked_session(&params.session, |session| {
        session.applicator.status = params.status;
        session.applicator.updated_at = now_rfc3339();
        Ok(session.applicator.status)
    })
}

/// Read the current parent-review availability for the applicator flow.
pub fn applicator_wait(params: SessionLocator) -> anyhow::Result<ApplicatorWaitResult> {
    let session = load_session(&params)?;
    Ok(ApplicatorWaitResult {
        status: session.applicator.status,
        parent_review_ready: session.current.parent_review.is_some(),
        parent_review: session.current.parent_review,
    })
}

/// Persist a canonical application-result artifact.
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

/// Persist a canonical verification-result artifact.
pub fn verify_application(
    params: ApplicatorArtifactParams,
) -> anyhow::Result<PersistArtifactResult> {
    let artifact = parse_artifact_file(&params.artifact_file)?;
    let verification_result = match artifact {
        ArtifactDocument::VerificationResult(verification_result) => verification_result,
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
            &ArtifactDocument::VerificationResult(verification_result.clone()),
        )?;
        session.applicator.status = if verification_result.failed_items.is_empty() {
            ApplicatorStatus::Completed
        } else {
            ApplicatorStatus::Blocked
        };
        session.applicator.updated_at = now_rfc3339();
        session.applicator.verification_result_id = Some(result.artifact_id.clone());
        Ok(result)
    })
}

/// Persist routing outputs into the compact session ledger.
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

/// Persist a route revision artifact and recompute the active route.
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
            .clone()
            .ok_or_else(|| anyhow::anyhow!("error: no current route_decision is persisted"))?;
        let current_route_path =
            paths::resolve_repo_relative(&PathBuf::from(&session.repo_root), &current_route.path);
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

/// Persist a canonical convergence-state artifact.
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

/// List stored artifact refs, optionally filtered by `kind`.
pub fn list_artifacts(session: &SessionLedger, kind: Option<ArtifactKind>) -> Vec<ArtifactPointer> {
    session
        .artifacts
        .iter()
        .filter(|artifact| kind.is_none_or(|expected| artifact.artifact_kind == expected))
        .cloned()
        .collect()
}

/// Remove scratch files for the current repo root.
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

#[cfg(test)]
mod tests {
    use super::*;
    use crate::artifacts::{
        ApplicationResultArtifact, ArtifactHeader, ConfidenceLabel, ExecutionCapability, Mode,
        PolicyCategory, PolicyRef, PolicyView, ProducerKind, SurfaceId, VerificationItemRecord,
        VerificationResultArtifact, VerificationStatus,
    };
    use crate::paths::session_paths;
    use crate::router::{
        build_route_decision, build_route_revision, build_surface_map, default_router_policy_refs,
    };
    use crate::router_types::{RouteInputs, RouteRevisionRequest};
    use anyhow::ensure;
    use time::{Date, Month};

    fn session_locator() -> anyhow::Result<SessionLocator> {
        let temp = std::env::temp_dir().join(format!("mpcr-session-test-{}", id::random_id8()?));
        let _ = fs::remove_dir_all(&temp);
        fs::create_dir_all(&temp)?;
        let date = Date::from_calendar_date(2026, Month::March, 8)?;
        let session_dir = session_paths(&temp, date).session_dir;
        paths::ensure_session_layout(&session_dir)?;
        Ok(SessionLocator::from_session_dir(session_dir))
    }

    fn header(
        kind: ArtifactKind,
        session_id: &str,
        target_ref: &str,
    ) -> anyhow::Result<ArtifactHeader> {
        ArtifactHeader::new(
            kind,
            "abc123def456".to_string(),
            session_id.to_string(),
            target_ref.to_string(),
            ProducerKind::ApplicatorVerifier,
            "2026-03-08T00:00:00Z".to_string(),
            ConfidenceLabel::High,
            90,
            vec![PolicyRef {
                category: PolicyCategory::Mode,
                id: "reviewer".to_string(),
                version: "2026.03.08".to_string(),
                view: PolicyView::Checklist,
            }],
        )
    }

    fn route_artifacts(
        session_id: &str,
        target_ref: &str,
    ) -> anyhow::Result<(
        crate::artifacts::SurfaceMapArtifact,
        crate::artifacts::RouteDecisionArtifact,
    )> {
        let inputs = RouteInputs {
            changed_files: vec!["tests/unit/foo_test.rs".to_string()],
            public_interfaces: Vec::new(),
            behavior_facing_artifacts: Vec::new(),
            execution_capability: ExecutionCapability::BoundedHelpers,
            max_worker_count: 4,
            orchestrator_read_budget_lines: 120,
            orchestrator_read_budget_snippets: 12,
            history_signals: Default::default(),
        };
        let surface_map = build_surface_map(
            ArtifactHeader::new(
                ArtifactKind::SurfaceMap,
                id::random_hex_id(6)?,
                session_id.to_string(),
                target_ref.to_string(),
                ProducerKind::Router,
                "2026-03-08T00:00:00Z".to_string(),
                ConfidenceLabel::High,
                90,
                vec![PolicyRef {
                    category: PolicyCategory::Worker,
                    id: "surface-mapper".to_string(),
                    version: "2026.03.08".to_string(),
                    view: PolicyView::Checklist,
                }],
            )?,
            &inputs,
        );
        let route_decision = build_route_decision(
            ArtifactHeader::new(
                ArtifactKind::RouteDecision,
                id::random_hex_id(6)?,
                session_id.to_string(),
                target_ref.to_string(),
                ProducerKind::Router,
                "2026-03-08T00:00:01Z".to_string(),
                ConfidenceLabel::High,
                90,
                default_router_policy_refs(&surface_map.suggested_modules),
            )?,
            Mode::Reviewer,
            &surface_map,
            &inputs,
        );
        Ok((surface_map, route_decision))
    }

    #[test]
    fn session_stores_refs_only_and_rejects_legacy() -> anyhow::Result<()> {
        let locator = session_locator()?;
        fs::write(
            locator.session_dir().join("_session.toml"),
            "schema_version = \"1.2.0\"\n",
        )?;
        let err = load_session(&locator).expect_err("legacy session should be rejected");
        ensure!(err
            .to_string()
            .contains("legacy v1 session/report/artifact"));
        Ok(())
    }

    #[test]
    fn register_and_verify_artifact_persistence_are_compact() -> anyhow::Result<()> {
        let locator = session_locator()?;
        let registered = register_reviewer(RegisterReviewerParams {
            session: locator.clone(),
            target_ref: "refs/heads/main".to_string(),
            reviewer_id: Some("review01".to_string()),
        })?;

        let artifact =
            ArtifactDocument::VerificationResult(crate::artifacts::VerificationResultArtifact {
                header: header(
                    ArtifactKind::VerificationResult,
                    &registered.session_id,
                    "refs/heads/main",
                )?,
                verified_items: vec![VerificationItemRecord {
                    finding_id: "F001".to_string(),
                    status: VerificationStatus::Yes,
                    notes: "covered by regression".to_string(),
                }],
                failed_items: Vec::new(),
                partial_items: Vec::new(),
                residual_risks: Vec::new(),
            });
        let artifact_file = locator.session_dir().join("verification_result.toml");
        fs::write(&artifact_file, artifact.to_toml_string()?)?;
        let persisted = verify_application(ApplicatorArtifactParams {
            session: locator.clone(),
            artifact_file,
        })?;
        ensure!(persisted.rendered_path.is_some());

        let session = load_session(&locator)?;
        let encoded = toml::to_string_pretty(&session)?;
        ensure!(!encoded.contains("covered by regression"));
        ensure!(encoded.contains("verification_result"));
        ensure!(session.telemetry.verification_outcome.get("yes") == Some(&1));
        Ok(())
    }

    #[test]
    fn route_artifacts_persist_and_route_revision_updates_current_pointers() -> anyhow::Result<()> {
        let locator = session_locator()?;
        let session = ensure_session(&locator, "refs/heads/main")?;
        let (surface_map, route_decision) =
            route_artifacts(&session.session_id, "refs/heads/main")?;
        let persisted = persist_route_artifacts(PersistRouteArtifactsParams {
            session: locator.clone(),
            target_ref: "refs/heads/main".to_string(),
            surface_map: surface_map.clone(),
            route_decision: route_decision.clone(),
        })?;
        ensure!(persisted.surface_map.artifact_kind == ArtifactKind::SurfaceMap);
        ensure!(persisted.route_decision.artifact_kind == ArtifactKind::RouteDecision);

        let revision = build_route_revision(
            ArtifactHeader::new(
                ArtifactKind::RouteRevision,
                id::random_hex_id(6)?,
                session.session_id.clone(),
                "refs/heads/main".to_string(),
                ProducerKind::Router,
                "2026-03-08T00:00:02Z".to_string(),
                ConfidenceLabel::High,
                90,
                default_router_policy_refs(&route_decision.selected_modules),
            )?,
            &route_decision,
            route_decision.header.artifact_id.clone(),
            &RouteRevisionRequest {
                discovered_surfaces: vec![SurfaceId::AuthAccess],
                added_modules: vec![crate::artifacts::ModuleId::AuthAccess],
                raise_rigor: false,
                widen_architecture: true,
            },
        );
        let revision_file = locator.session_dir().join("route_revision.toml");
        fs::write(
            &revision_file,
            ArtifactDocument::RouteRevision(revision).to_toml_string()?,
        )?;
        let applied = apply_route_revision_artifact(ApplyRouteRevisionParams {
            session: locator.clone(),
            artifact_file: revision_file,
        })?;
        ensure!(applied.route_revision.artifact_kind == ArtifactKind::RouteRevision);

        let updated = load_session(&locator)?;
        ensure!(updated.current.surface_map.is_some());
        ensure!(updated.current.route_decision.is_some());
        ensure!(updated.current.route_revision.is_some());
        let current_route = updated
            .current
            .route_decision
            .clone()
            .ok_or_else(|| anyhow::anyhow!("missing route_decision pointer"))?;
        let current_route_path =
            paths::resolve_repo_relative(&PathBuf::from(updated.repo_root), &current_route.path);
        let current_route = match parse_artifact_file(&current_route_path)? {
            ArtifactDocument::RouteDecision(route) => route,
            _ => return Err(anyhow::anyhow!("current route pointer did not resolve")),
        };
        ensure!(current_route
            .selected_modules
            .contains(&crate::artifacts::ModuleId::AuthAccess));
        ensure!(
            current_route.execution_architecture == crate::artifacts::ExecutionArchitecture::Hybrid
        );
        Ok(())
    }

    #[test]
    fn applicator_status_progresses_forward_only() -> anyhow::Result<()> {
        let locator = session_locator()?;
        let registered = register_reviewer(RegisterReviewerParams {
            session: locator.clone(),
            target_ref: "refs/heads/main".to_string(),
            reviewer_id: Some("review01".to_string()),
        })?;

        let application_result = ArtifactDocument::ApplicationResult(ApplicationResultArtifact {
            header: header(
                ArtifactKind::ApplicationResult,
                &registered.session_id,
                "refs/heads/main",
            )?,
            source_finding_ids: vec!["F001".to_string()],
            dispositions: Vec::new(),
            modified_files: vec!["src/lib.rs".to_string()],
            verification_needed: Vec::new(),
            decline_codes: Vec::new(),
        });
        let application_file = locator.session_dir().join("application_result.toml");
        fs::write(&application_file, application_result.to_toml_string()?)?;
        finalize_application(ApplicatorArtifactParams {
            session: locator.clone(),
            artifact_file: application_file,
        })?;
        ensure!(load_session(&locator)?.applicator.status == ApplicatorStatus::Verifying);

        let verification_result =
            ArtifactDocument::VerificationResult(VerificationResultArtifact {
                header: header(
                    ArtifactKind::VerificationResult,
                    &registered.session_id,
                    "refs/heads/main",
                )?,
                verified_items: vec![VerificationItemRecord {
                    finding_id: "F001".to_string(),
                    status: VerificationStatus::Yes,
                    notes: "verified".to_string(),
                }],
                failed_items: Vec::new(),
                partial_items: Vec::new(),
                residual_risks: Vec::new(),
            });
        let verification_file = locator.session_dir().join("verification_result.toml");
        fs::write(&verification_file, verification_result.to_toml_string()?)?;
        verify_application(ApplicatorArtifactParams {
            session: locator.clone(),
            artifact_file: verification_file,
        })?;
        ensure!(load_session(&locator)?.applicator.status == ApplicatorStatus::Completed);

        let blocked_locator = session_locator()?;
        let blocked_registered = register_reviewer(RegisterReviewerParams {
            session: blocked_locator.clone(),
            target_ref: "refs/heads/main".to_string(),
            reviewer_id: Some("review02".to_string()),
        })?;
        let blocked_application = ArtifactDocument::ApplicationResult(ApplicationResultArtifact {
            header: header(
                ArtifactKind::ApplicationResult,
                &blocked_registered.session_id,
                "refs/heads/main",
            )?,
            source_finding_ids: vec!["F002".to_string()],
            dispositions: Vec::new(),
            modified_files: vec!["src/lib.rs".to_string()],
            verification_needed: Vec::new(),
            decline_codes: Vec::new(),
        });
        let blocked_application_file = blocked_locator
            .session_dir()
            .join("application_result.toml");
        fs::write(
            &blocked_application_file,
            blocked_application.to_toml_string()?,
        )?;
        finalize_application(ApplicatorArtifactParams {
            session: blocked_locator.clone(),
            artifact_file: blocked_application_file,
        })?;

        let blocked_verification =
            ArtifactDocument::VerificationResult(VerificationResultArtifact {
                header: header(
                    ArtifactKind::VerificationResult,
                    &blocked_registered.session_id,
                    "refs/heads/main",
                )?,
                verified_items: Vec::new(),
                failed_items: vec![VerificationItemRecord {
                    finding_id: "F002".to_string(),
                    status: VerificationStatus::No,
                    notes: "failed".to_string(),
                }],
                partial_items: Vec::new(),
                residual_risks: Vec::new(),
            });
        let blocked_verification_file = blocked_locator
            .session_dir()
            .join("verification_result.toml");
        fs::write(
            &blocked_verification_file,
            blocked_verification.to_toml_string()?,
        )?;
        verify_application(ApplicatorArtifactParams {
            session: blocked_locator.clone(),
            artifact_file: blocked_verification_file,
        })?;
        ensure!(load_session(&blocked_locator)?.applicator.status == ApplicatorStatus::Blocked);
        Ok(())
    }
}
