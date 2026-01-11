//! Session file (`_session.json`) schema and deterministic update operations.
//!
//! This module defines the typed representation of `_session.json` and provides
//! read/modify/write helpers that:
//! - take a session lock (`_session.json.lock`)
//! - apply a scoped mutation
//! - write `_session.json` via an atomic temp-file replace
//!
//! The CLI (`mpcr`) is the intended interface for mutating session state.

use crate::id;
use crate::lock::{self, LockConfig};
use crate::paths;
use anyhow::Context;
use clap::builder::PossibleValue;
use clap::ValueEnum;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};
use time::format_description::well_known::Rfc3339;
use time::{Date, OffsetDateTime};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
/// Reviewer-owned status for a single review entry.
pub enum ReviewerStatus {
    /// Registered; review not yet started.
    Initializing,
    /// Actively reviewing.
    InProgress,
    /// Completed with verdict and report.
    Finished,
    /// Stopped before completion.
    Cancelled,
    /// Fatal error encountered; details should be captured in notes.
    Error,
    /// Waiting on an external dependency or intervention.
    Blocked,
}

impl ReviewerStatus {
    /// Whether this status is terminal (no further progress is expected).
    pub fn is_terminal(self) -> bool {
        matches!(
            self,
            ReviewerStatus::Finished | ReviewerStatus::Cancelled | ReviewerStatus::Error
        )
    }
}

impl ValueEnum for ReviewerStatus {
    fn value_variants<'a>() -> &'a [Self] {
        &[
            Self::Initializing,
            Self::InProgress,
            Self::Finished,
            Self::Cancelled,
            Self::Error,
            Self::Blocked,
        ]
    }

    fn to_possible_value(&self) -> Option<PossibleValue> {
        let pv = match self {
            Self::Initializing => PossibleValue::new("INITIALIZING")
                .help("Registered; review not yet started"),
            Self::InProgress => PossibleValue::new("IN_PROGRESS").help("Actively reviewing"),
            Self::Finished => PossibleValue::new("FINISHED").help("Completed with verdict/report"),
            Self::Cancelled => PossibleValue::new("CANCELLED").help("Stopped before completion"),
            Self::Error => PossibleValue::new("ERROR").help("Fatal error; see notes"),
            Self::Blocked => PossibleValue::new("BLOCKED").help("Waiting on external dependency"),
        };
        Some(pv)
    }
}

impl std::str::FromStr for ReviewerStatus {
    type Err = anyhow::Error;

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        match s {
            s if s.eq_ignore_ascii_case("INITIALIZING") => Ok(Self::Initializing),
            s if s.eq_ignore_ascii_case("IN_PROGRESS") => Ok(Self::InProgress),
            s if s.eq_ignore_ascii_case("FINISHED") => Ok(Self::Finished),
            s if s.eq_ignore_ascii_case("CANCELLED") => Ok(Self::Cancelled),
            s if s.eq_ignore_ascii_case("ERROR") => Ok(Self::Error),
            s if s.eq_ignore_ascii_case("BLOCKED") => Ok(Self::Blocked),
            _ => Err(anyhow::anyhow!("invalid ReviewerStatus: {s}")),
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
/// Applicator-owned status for consuming a review entry.
pub enum InitiatorStatus {
    /// Review requested; waiting for reviewers to register and progress.
    Requesting,
    /// Watching reviews in progress.
    Observing,
    /// Completed review received (report read).
    Received,
    /// Feedback assessed; deciding what to apply.
    Reviewed,
    /// Applying accepted feedback.
    Applying,
    /// Finished processing the feedback (applied / declined / deferred).
    Applied,
    /// Request cancelled.
    Cancelled,
}

impl ValueEnum for InitiatorStatus {
    fn value_variants<'a>() -> &'a [Self] {
        &[
            Self::Requesting,
            Self::Observing,
            Self::Received,
            Self::Reviewed,
            Self::Applying,
            Self::Applied,
            Self::Cancelled,
        ]
    }

    fn to_possible_value(&self) -> Option<PossibleValue> {
        let pv = match self {
            Self::Requesting => PossibleValue::new("REQUESTING").help("Review requested; waiting"),
            Self::Observing => PossibleValue::new("OBSERVING").help("Watching reviews in progress"),
            Self::Received => PossibleValue::new("RECEIVED").help("Completed reviews received"),
            Self::Reviewed => PossibleValue::new("REVIEWED").help("Feedback read and assessed"),
            Self::Applying => PossibleValue::new("APPLYING").help("Applying accepted feedback"),
            Self::Applied => PossibleValue::new("APPLIED").help("Finished processing feedback"),
            Self::Cancelled => PossibleValue::new("CANCELLED").help("Request cancelled"),
        };
        Some(pv)
    }
}

impl std::str::FromStr for InitiatorStatus {
    type Err = anyhow::Error;

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        match s {
            s if s.eq_ignore_ascii_case("REQUESTING") => Ok(Self::Requesting),
            s if s.eq_ignore_ascii_case("OBSERVING") => Ok(Self::Observing),
            s if s.eq_ignore_ascii_case("RECEIVED") => Ok(Self::Received),
            s if s.eq_ignore_ascii_case("REVIEWED") => Ok(Self::Reviewed),
            s if s.eq_ignore_ascii_case("APPLYING") => Ok(Self::Applying),
            s if s.eq_ignore_ascii_case("APPLIED") => Ok(Self::Applied),
            s if s.eq_ignore_ascii_case("CANCELLED") => Ok(Self::Cancelled),
            _ => Err(anyhow::anyhow!("invalid InitiatorStatus: {s}")),
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
/// Optional progress marker for a reviewer's workflow.
pub enum ReviewPhase {
    /// Initial ingestion of context / diff / repository constraints.
    Ingestion,
    /// Domain coverage mapping / scoping decisions.
    DomainCoverage,
    /// Must-prove theorem generation.
    TheoremGeneration,
    /// Adversarial disproof attempts and counterexample search.
    AdversarialProofs,
    /// Synthesize findings, mitigations, and residual risk.
    Synthesis,
    /// Final report writing phase.
    ReportWriting,
}

impl ValueEnum for ReviewPhase {
    fn value_variants<'a>() -> &'a [Self] {
        &[
            Self::Ingestion,
            Self::DomainCoverage,
            Self::TheoremGeneration,
            Self::AdversarialProofs,
            Self::Synthesis,
            Self::ReportWriting,
        ]
    }

    fn to_possible_value(&self) -> Option<PossibleValue> {
        let pv = match self {
            Self::Ingestion => PossibleValue::new("INGESTION").help("Initial codebase ingestion"),
            Self::DomainCoverage => PossibleValue::new("DOMAIN_COVERAGE")
                .help("Domain coverage map / scoping"),
            Self::TheoremGeneration => PossibleValue::new("THEOREM_GENERATION")
                .help("Generate must-prove theorems"),
            Self::AdversarialProofs => PossibleValue::new("ADVERSARIAL_PROOFS")
                .help("Attempt disproofs / adversarial testing"),
            Self::Synthesis => PossibleValue::new("SYNTHESIS").help("Synthesize findings/mitigations"),
            Self::ReportWriting => PossibleValue::new("REPORT_WRITING").help("Write the final report"),
        };
        Some(pv)
    }
}

impl std::str::FromStr for ReviewPhase {
    type Err = anyhow::Error;

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        match s {
            s if s.eq_ignore_ascii_case("INGESTION") => Ok(Self::Ingestion),
            s if s.eq_ignore_ascii_case("DOMAIN_COVERAGE") => Ok(Self::DomainCoverage),
            s if s.eq_ignore_ascii_case("THEOREM_GENERATION") => Ok(Self::TheoremGeneration),
            s if s.eq_ignore_ascii_case("ADVERSARIAL_PROOFS") => Ok(Self::AdversarialProofs),
            s if s.eq_ignore_ascii_case("SYNTHESIS") => Ok(Self::Synthesis),
            s if s.eq_ignore_ascii_case("REPORT_WRITING") => Ok(Self::ReportWriting),
            _ => Err(anyhow::anyhow!("invalid ReviewPhase: {s}")),
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
/// Final verdict recorded by the reviewer when finishing a review.
pub enum ReviewVerdict {
    /// Accept the change as-is.
    Approve,
    /// Request changes before merge.
    RequestChanges,
    /// Block merge due to unacceptable risk or correctness/security issues.
    Block,
}

impl ValueEnum for ReviewVerdict {
    fn value_variants<'a>() -> &'a [Self] {
        &[Self::Approve, Self::RequestChanges, Self::Block]
    }

    fn to_possible_value(&self) -> Option<PossibleValue> {
        let pv = match self {
            Self::Approve => PossibleValue::new("APPROVE").help("No changes required"),
            Self::RequestChanges => PossibleValue::new("REQUEST_CHANGES")
                .help("Changes required before merge"),
            Self::Block => PossibleValue::new("BLOCK").help("Cannot merge; must fix"),
        };
        Some(pv)
    }
}

impl std::str::FromStr for ReviewVerdict {
    type Err = anyhow::Error;

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        match s {
            s if s.eq_ignore_ascii_case("APPROVE") => Ok(Self::Approve),
            s if s.eq_ignore_ascii_case("REQUEST_CHANGES") => Ok(Self::RequestChanges),
            s if s.eq_ignore_ascii_case("BLOCK") => Ok(Self::Block),
            _ => Err(anyhow::anyhow!("invalid ReviewVerdict: {s}")),
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
/// Author role for a session note.
pub enum NoteRole {
    /// Note written by the reviewer.
    Reviewer,
    /// Note written by the feedback applicator.
    Applicator,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
/// Structured note type for session notes.
pub enum NoteType {
    /// Reviewer flag for strict scrutiny of a high-risk area.
    EscalationTrigger,
    /// Observation scoped to a particular review domain.
    DomainObservation,
    /// Early warning of a likely blocker.
    BlockerPreview,
    /// A question requiring response/clarification.
    Question,
    /// Handoff context for another reviewer.
    Handoff,
    /// Error details for a failure encountered during review coordination.
    ErrorDetail,
    /// Applicator note: feedback was applied.
    Applied,
    /// Applicator note: feedback was declined (should include reasoning).
    Declined,
    /// Applicator note: feedback deferred (should include tracking info).
    Deferred,
    /// Applicator note: clarification needed before acting.
    ClarificationNeeded,
    /// Applicator note: already addressed elsewhere (should include reference).
    AlreadyAddressed,
    /// Applicator note: acknowledged; no action needed.
    Acknowledged,
}

impl ValueEnum for NoteType {
    fn value_variants<'a>() -> &'a [Self] {
        &[
            Self::EscalationTrigger,
            Self::DomainObservation,
            Self::BlockerPreview,
            Self::Question,
            Self::Handoff,
            Self::ErrorDetail,
            Self::Applied,
            Self::Declined,
            Self::Deferred,
            Self::ClarificationNeeded,
            Self::AlreadyAddressed,
            Self::Acknowledged,
        ]
    }

    fn to_possible_value(&self) -> Option<PossibleValue> {
        let pv = match self {
            Self::EscalationTrigger => PossibleValue::new("escalation_trigger")
                .help("Flag a high-risk area requiring strict scrutiny"),
            Self::DomainObservation => PossibleValue::new("domain_observation")
                .help("Observation scoped to a review domain"),
            Self::BlockerPreview => PossibleValue::new("blocker_preview")
                .help("Early warning of a likely blocker"),
            Self::Question => PossibleValue::new("question").help("Request clarification"),
            Self::Handoff => PossibleValue::new("handoff").help("Context for another reviewer"),
            Self::ErrorDetail => PossibleValue::new("error_detail").help("Error details / debugging info"),
            Self::Applied => PossibleValue::new("applied").help("Feedback was applied"),
            Self::Declined => PossibleValue::new("declined").help("Feedback was declined (include reason)"),
            Self::Deferred => PossibleValue::new("deferred").help("Feedback deferred (include tracking)"),
            Self::ClarificationNeeded => PossibleValue::new("clarification_needed")
                .help("Request more detail before acting"),
            Self::AlreadyAddressed => PossibleValue::new("already_addressed")
                .help("Already handled elsewhere (reference)"),
            Self::Acknowledged => PossibleValue::new("acknowledged").help("Read/understood; no action"),
        };
        Some(pv)
    }
}

impl std::str::FromStr for NoteType {
    type Err = anyhow::Error;

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        // Accept canonical snake_case as written to JSON, and also tolerate screaming snake.
        match s {
            s if s.eq_ignore_ascii_case("escalation_trigger")
                || s.eq_ignore_ascii_case("ESCALATION_TRIGGER") =>
            {
                Ok(Self::EscalationTrigger)
            }
            s if s.eq_ignore_ascii_case("domain_observation")
                || s.eq_ignore_ascii_case("DOMAIN_OBSERVATION") =>
            {
                Ok(Self::DomainObservation)
            }
            s if s.eq_ignore_ascii_case("blocker_preview")
                || s.eq_ignore_ascii_case("BLOCKER_PREVIEW") =>
            {
                Ok(Self::BlockerPreview)
            }
            s if s.eq_ignore_ascii_case("question") || s.eq_ignore_ascii_case("QUESTION") => {
                Ok(Self::Question)
            }
            s if s.eq_ignore_ascii_case("handoff") || s.eq_ignore_ascii_case("HANDOFF") => {
                Ok(Self::Handoff)
            }
            s if s.eq_ignore_ascii_case("error_detail")
                || s.eq_ignore_ascii_case("ERROR_DETAIL") =>
            {
                Ok(Self::ErrorDetail)
            }
            s if s.eq_ignore_ascii_case("applied") || s.eq_ignore_ascii_case("APPLIED") => {
                Ok(Self::Applied)
            }
            s if s.eq_ignore_ascii_case("declined") || s.eq_ignore_ascii_case("DECLINED") => {
                Ok(Self::Declined)
            }
            s if s.eq_ignore_ascii_case("deferred") || s.eq_ignore_ascii_case("DEFERRED") => {
                Ok(Self::Deferred)
            }
            s if s.eq_ignore_ascii_case("clarification_needed")
                || s.eq_ignore_ascii_case("CLARIFICATION_NEEDED") =>
            {
                Ok(Self::ClarificationNeeded)
            }
            s if s.eq_ignore_ascii_case("already_addressed")
                || s.eq_ignore_ascii_case("ALREADY_ADDRESSED") =>
            {
                Ok(Self::AlreadyAddressed)
            }
            s if s.eq_ignore_ascii_case("acknowledged")
                || s.eq_ignore_ascii_case("ACKNOWLEDGED") =>
            {
                Ok(Self::Acknowledged)
            }
            _ => Err(anyhow::anyhow!("invalid NoteType: {s}")),
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
/// Severity tallies for a review report.
pub struct SeverityCounts {
    /// Number of BLOCKER findings.
    pub blocker: u64,
    /// Number of MAJOR findings.
    pub major: u64,
    /// Number of MINOR findings.
    pub minor: u64,
    /// Number of NIT findings.
    pub nit: u64,
}

impl SeverityCounts {
    /// Convenience constructor for a zeroed severity tally.
    pub fn zero() -> Self {
        Self {
            blocker: 0,
            major: 0,
            minor: 0,
            nit: 0,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
/// A structured note appended to a review entry's `notes` array.
pub struct SessionNote {
    /// Author role of this note (`reviewer` or `applicator`).
    pub role: NoteRole,
    /// RFC3339 timestamp (UTC) of when the note was recorded.
    pub timestamp: String,
    #[serde(rename = "type")]
    /// Structured note type.
    pub note_type: NoteType,
    /// Arbitrary JSON content (string by default; object/array allowed).
    pub content: Value,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
/// A single review coordination entry within a [`SessionFile`].
pub struct ReviewEntry {
    /// 8-character reviewer id.
    pub reviewer_id: String,
    /// 8-character session id (groups reviewers reviewing the same target).
    pub session_id: String,
    /// Target reference being reviewed (branch, PR ref, commit, etc).
    pub target_ref: String,
    /// Applicator-owned progress state for consuming this review.
    pub initiator_status: InitiatorStatus,
    /// Reviewer-owned progress state.
    pub status: ReviewerStatus,
    /// Optional parent reviewer id for handoff/chaining.
    pub parent_id: Option<String>,
    /// RFC3339 timestamp (UTC) when the reviewer registered this entry.
    pub started_at: String,
    /// RFC3339 timestamp (UTC) of the last update to this entry.
    pub updated_at: String,
    /// RFC3339 timestamp (UTC) when the review was finalized (if finished).
    pub finished_at: Option<String>,
    /// Optional reviewer phase marker.
    pub current_phase: Option<ReviewPhase>,
    /// Optional verdict (set when finished).
    pub verdict: Option<ReviewVerdict>,
    /// Severity counts extracted from the report.
    pub counts: SeverityCounts,
    /// Report filename within the session directory (set when finished).
    pub report_file: Option<String>,
    /// Bidirectional notes between reviewer and applicator.
    pub notes: Vec<SessionNote>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
/// Top-level session file stored as `_session.json` within a session directory.
pub struct SessionFile {
    /// Schema version string for `_session.json`.
    pub schema_version: String,
    /// Session date in `YYYY-MM-DD` form.
    pub session_date: String,
    /// Canonicalized absolute path to the repo root.
    pub repo_root: String,
    /// Unique reviewer ids that have registered.
    pub reviewers: Vec<String>,
    /// Review coordination entries.
    pub reviews: Vec<ReviewEntry>,
}

fn format_ts(now: OffsetDateTime) -> anyhow::Result<String> {
    now.format(&Rfc3339).context("format RFC3339 timestamp")
}

fn parse_ts(s: &str) -> anyhow::Result<OffsetDateTime> {
    OffsetDateTime::parse(s, &Rfc3339).context("parse RFC3339 timestamp")
}

fn session_file_path(session_dir: &Path) -> PathBuf {
    session_dir.join("_session.json")
}

fn read_session_file(session_dir: &Path) -> anyhow::Result<SessionFile> {
    let path = session_file_path(session_dir);
    let raw = fs::read_to_string(&path)
        .with_context(|| format!("read session file {}", path.display()))?;
    let parsed: SessionFile =
        serde_json::from_str(&raw).with_context(|| format!("parse JSON {}", path.display()))?;
    Ok(parsed)
}

/// Load and parse `_session.json` for the given session locator.
pub fn load_session(session: &SessionLocator) -> anyhow::Result<SessionFile> {
    read_session_file(session.session_dir())
}

fn write_session_file_atomic(
    session_dir: &Path,
    owner: &str,
    session: &SessionFile,
) -> anyhow::Result<()> {
    fs::create_dir_all(session_dir)
        .with_context(|| format!("create session dir {}", session_dir.display()))?;
    let session_file = session_file_path(session_dir);
    let tmp = session_dir.join(format!("_session.json.tmp.{owner}"));
    let body = serde_json::to_string_pretty(session).context("serialize session JSON")? + "\n";
    fs::write(&tmp, body).with_context(|| format!("write temp session file {}", tmp.display()))?;

    // Best-effort cross-platform replacement:
    // - Unix: rename() replaces destination atomically.
    // - Windows: rename() fails if dest exists; remove then rename.
    #[cfg(windows)]
    {
        if session_file.exists() {
            fs::remove_file(&session_file).with_context(|| {
                format!("remove existing session file {}", session_file.display())
            })?;
        }
    }

    fs::rename(&tmp, &session_file).with_context(|| {
        format!(
            "replace session file {} via {}",
            session_file.display(),
            tmp.display()
        )
    })?;
    Ok(())
}

fn validate_id8(id8: &str, label: &str) -> anyhow::Result<()> {
    if id8.len() != 8 {
        return Err(anyhow::anyhow!("{label} must be 8 characters"));
    }
    if !id8.chars().all(|c| c.is_ascii_alphanumeric()) {
        return Err(anyhow::anyhow!("{label} must be ASCII alphanumeric"));
    }
    Ok(())
}

#[derive(Debug, Clone)]
/// A locator for a session directory on disk.
///
/// This is primarily a convenience wrapper around a `PathBuf` that standardizes where to
/// find `_session.json` and the lock file.
pub struct SessionLocator {
    /// Path to the session directory.
    pub session_dir: PathBuf,
}

impl SessionLocator {
    /// Create a new locator from an explicit session directory path.
    pub fn new(session_dir: PathBuf) -> Self {
        Self { session_dir }
    }

    /// Compute the session directory from `repo_root` and `session_date`.
    pub fn from_repo_root(repo_root: &Path, session_date: Date) -> Self {
        let p = paths::session_paths(repo_root, session_date);
        Self {
            session_dir: p.session_dir,
        }
    }

    /// Borrow the session directory path.
    pub fn session_dir(&self) -> &Path {
        &self.session_dir
    }

    /// Compute the full path to `_session.json` inside this session directory.
    pub fn session_file(&self) -> PathBuf {
        session_file_path(&self.session_dir)
    }
}

#[derive(Debug, Clone)]
/// Parameters for [`register_reviewer`].
pub struct RegisterReviewerParams {
    /// Repo root used when creating a brand-new session file (stored as canonical path).
    pub repo_root: PathBuf,
    /// Session date used for the `session_date` field (and default path computation).
    pub session_date: Date,
    /// Session directory locator.
    pub session: SessionLocator,
    /// Target ref under review (branch/PR/commit/etc).
    pub target_ref: String,
    /// Optional override for `reviewer_id` (id8).
    pub reviewer_id: Option<String>,
    /// Optional override for `session_id` (id8).
    pub session_id: Option<String>,
    /// Optional parent reviewer id (id8) for handoff/chaining.
    pub parent_id: Option<String>,
    /// Timestamp used for `started_at` / `updated_at`.
    pub now: OffsetDateTime,
}

#[derive(Debug, Clone, Serialize)]
/// Result returned by [`register_reviewer`].
pub struct RegisterReviewerResult {
    /// The reviewer id used for the entry (id8).
    pub reviewer_id: String,
    /// The session id used for the entry (id8).
    pub session_id: String,
    /// Session directory as a string.
    pub session_dir: String,
    /// Session file path as a string.
    pub session_file: String,
}

/// Register a reviewer in the session file.
///
/// This creates the session directory and `_session.json` if needed, adds the reviewer to the
/// `reviewers` list (if missing), and appends a new entry in `reviews` unless one already exists
/// for the same `(reviewer_id, session_id)`.
pub fn register_reviewer(params: RegisterReviewerParams) -> anyhow::Result<RegisterReviewerResult> {
    let reviewer_id = match params.reviewer_id {
        Some(reviewer_id) => reviewer_id,
        None => id::random_id8()?,
    };
    validate_id8(&reviewer_id, "reviewer_id")?;

    if let Some(ref parent_id) = params.parent_id {
        validate_id8(parent_id, "parent_id")?;
    }

    fs::create_dir_all(params.session.session_dir()).with_context(|| {
        format!(
            "create session dir {}",
            params.session.session_dir().display()
        )
    })?;

    let lock_owner = reviewer_id.clone();
    let _guard = lock::acquire_lock(
        params.session.session_dir(),
        lock_owner,
        LockConfig::default(),
    )?;

    let mut session = match params.session.session_file().exists() {
        true => read_session_file(params.session.session_dir())?,
        false => {
            let repo_root = params.repo_root.canonicalize().with_context(|| {
                format!("canonicalize repo_root {}", params.repo_root.display())
            })?;
            SessionFile {
                schema_version: "1.0.0".to_string(),
                session_date: params.session_date.to_string(),
                repo_root: repo_root.to_string_lossy().to_string(),
                reviewers: vec![],
                reviews: vec![],
            }
        }
    };

    let session_id = if let Some(session_id) = params.session_id {
        validate_id8(&session_id, "session_id")?;
        session_id
    } else {
        // Join active session if one exists for this target_ref.
        let active_session = session.reviews.iter().find(|r| {
            r.target_ref == params.target_ref
                && matches!(
                    r.status,
                    ReviewerStatus::Initializing
                        | ReviewerStatus::InProgress
                        | ReviewerStatus::Blocked
                )
        });
        match active_session {
            Some(r) => r.session_id.clone(),
            None => id::random_id8()?,
        }
    };

    if let Some(existing) = session
        .reviews
        .iter()
        .find(|r| r.reviewer_id == reviewer_id && r.session_id == session_id)
    {
        if existing.target_ref != params.target_ref {
            return Err(anyhow::anyhow!(
                "review entry already exists for reviewer_id/session_id but target_ref differs"
            ));
        }

        if !session.reviewers.iter().any(|r| r == &reviewer_id) {
            session.reviewers.push(reviewer_id.clone());
            write_session_file_atomic(params.session.session_dir(), &reviewer_id, &session)?;
        }

        return Ok(RegisterReviewerResult {
            reviewer_id,
            session_id,
            session_dir: params.session.session_dir().to_string_lossy().to_string(),
            session_file: params.session.session_file().to_string_lossy().to_string(),
        });
    }

    let initiator_status = match session
        .reviews
        .iter()
        .find(|r| r.target_ref == params.target_ref && r.session_id == session_id.as_str())
    {
        Some(existing) => existing.initiator_status,
        None => InitiatorStatus::Requesting,
    };

    if !session.reviewers.iter().any(|r| r == &reviewer_id) {
        session.reviewers.push(reviewer_id.clone());
    }

    let started_at = format_ts(params.now)?;

    session.reviews.push(ReviewEntry {
        reviewer_id: reviewer_id.clone(),
        session_id: session_id.clone(),
        target_ref: params.target_ref,
        initiator_status,
        status: ReviewerStatus::Initializing,
        parent_id: params.parent_id,
        started_at: started_at.clone(),
        updated_at: started_at,
        finished_at: None,
        current_phase: None,
        verdict: None,
        counts: SeverityCounts::zero(),
        report_file: None,
        notes: vec![],
    });

    write_session_file_atomic(params.session.session_dir(), &reviewer_id, &session)?;

    Ok(RegisterReviewerResult {
        reviewer_id,
        session_id,
        session_dir: params.session.session_dir().to_string_lossy().to_string(),
        session_file: params.session.session_file().to_string_lossy().to_string(),
    })
}

#[derive(Debug, Clone)]
/// Parameters for [`update_review`].
pub struct UpdateReviewParams {
    /// Session directory locator.
    pub session: SessionLocator,
    /// Reviewer id for the entry being updated (id8).
    pub reviewer_id: String,
    /// Session id for the entry being updated (id8).
    pub session_id: String,
    /// If set, update the reviewer-owned `status`.
    pub status: Option<ReviewerStatus>,
    /// If set, update `current_phase` (use `Some(None)` to clear).
    pub phase: Option<Option<ReviewPhase>>,
    /// Timestamp written to `updated_at`.
    pub now: OffsetDateTime,
}

/// Update a review entry's reviewer-owned `status` and/or `current_phase`.
pub fn update_review(params: UpdateReviewParams) -> anyhow::Result<()> {
    validate_id8(&params.reviewer_id, "reviewer_id")?;
    validate_id8(&params.session_id, "session_id")?;

    let lock_owner = params.reviewer_id.clone();
    let _guard = lock::acquire_lock(
        params.session.session_dir(),
        lock_owner,
        LockConfig::default(),
    )?;

    let mut session = read_session_file(params.session.session_dir())?;

    let entry = session
        .reviews
        .iter_mut()
        .find(|r| r.reviewer_id == params.reviewer_id && r.session_id == params.session_id)
        .ok_or_else(|| anyhow::anyhow!("review entry not found for reviewer_id/session_id"))?;

    if let Some(status) = params.status {
        entry.status = status;
    }
    if let Some(phase) = params.phase {
        entry.current_phase = phase;
    }
    entry.updated_at = format_ts(params.now)?;

    write_session_file_atomic(params.session.session_dir(), &params.reviewer_id, &session)?;
    Ok(())
}

fn report_file_name(
    started_at: OffsetDateTime,
    target_ref: &str,
    reviewer_id: &str,
) -> anyhow::Result<String> {
    let fmt = time::format_description::parse("[hour]-[minute]-[second]-[subsecond digits:3]")
        .context("parse time format")?;
    let prefix = started_at
        .format(&fmt)
        .context("format report time prefix")?;
    let sanitized = paths::sanitize_ref(target_ref);
    Ok(format!("{prefix}_{sanitized}_{reviewer_id}.md"))
}

#[derive(Debug, Clone)]
/// Parameters for [`finalize_review`].
pub struct FinalizeReviewParams {
    /// Session directory locator.
    pub session: SessionLocator,
    /// Reviewer id for the entry being finalized (id8).
    pub reviewer_id: String,
    /// Session id for the entry being finalized (id8).
    pub session_id: String,
    /// Verdict to record.
    pub verdict: ReviewVerdict,
    /// Severity counts to record.
    pub counts: SeverityCounts,
    /// Report markdown contents to write to disk.
    pub report_markdown: String,
    /// Timestamp written to `finished_at` and `updated_at`.
    pub now: OffsetDateTime,
}

#[derive(Debug, Clone, Serialize)]
/// Result returned by [`finalize_review`].
pub struct FinalizeReviewResult {
    /// Report filename within the session directory.
    pub report_file: String,
    /// Full report path as a string.
    pub report_path: String,
}

/// Finalize a review entry: write the report file and update `_session.json`.
///
/// This performs the write in three steps:
/// 1) lock + read session entry to compute the report filename (refuses to overwrite)
/// 2) write report markdown file (outside the session lock)
/// 3) lock + update the session entry to `FINISHED` and point at the report file
pub fn finalize_review(params: FinalizeReviewParams) -> anyhow::Result<FinalizeReviewResult> {
    validate_id8(&params.reviewer_id, "reviewer_id")?;
    validate_id8(&params.session_id, "session_id")?;

    // Step 1: read the session file (locked) and compute the report filename.
    let started_at;
    let target_ref;
    {
        let lock_owner = params.reviewer_id.clone();
        let _guard = lock::acquire_lock(
            params.session.session_dir(),
            lock_owner,
            LockConfig::default(),
        )?;
        let session = read_session_file(params.session.session_dir())?;
        let entry = session
            .reviews
            .iter()
            .find(|r| r.reviewer_id == params.reviewer_id && r.session_id == params.session_id)
            .ok_or_else(|| anyhow::anyhow!("review entry not found for reviewer_id/session_id"))?;
        if entry.report_file.is_some() {
            return Err(anyhow::anyhow!(
                "report_file already set; refusing to overwrite"
            ));
        }
        started_at = parse_ts(&entry.started_at)?;
        target_ref = entry.target_ref.clone();
    }

    let filename = report_file_name(started_at, &target_ref, &params.reviewer_id)?;
    let report_path = params.session.session_dir().join(&filename);

    // Step 2: write report file (outside the session lock).
    let mut report = params.report_markdown;
    if !report.ends_with('\n') {
        report.push('\n');
    }
    let mut f = std::fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&report_path)
        .with_context(|| format!("create report file {}", report_path.display()))?;
    f.write_all(report.as_bytes())
        .with_context(|| format!("write report file {}", report_path.display()))?;
    f.flush()
        .with_context(|| format!("flush report file {}", report_path.display()))?;

    // Step 3: update session JSON (locked) to point at the report.
    {
        let lock_owner = params.reviewer_id.clone();
        let _guard = lock::acquire_lock(
            params.session.session_dir(),
            lock_owner,
            LockConfig::default(),
        )?;
        let mut session = read_session_file(params.session.session_dir())?;
        let entry = session
            .reviews
            .iter_mut()
            .find(|r| r.reviewer_id == params.reviewer_id && r.session_id == params.session_id)
            .ok_or_else(|| anyhow::anyhow!("review entry not found for reviewer_id/session_id"))?;

        entry.status = ReviewerStatus::Finished;
        entry.current_phase = Some(ReviewPhase::ReportWriting);
        entry.verdict = Some(params.verdict);
        entry.counts = params.counts;
        entry.report_file = Some(filename.clone());
        entry.finished_at = Some(format_ts(params.now)?);
        entry.updated_at = format_ts(params.now)?;

        write_session_file_atomic(params.session.session_dir(), &params.reviewer_id, &session)?;
    }

    Ok(FinalizeReviewResult {
        report_file: filename,
        report_path: report_path.to_string_lossy().to_string(),
    })
}

#[derive(Debug, Clone)]
/// Parameters for [`append_note`].
pub struct AppendNoteParams {
    /// Session directory locator.
    pub session: SessionLocator,
    /// Reviewer id for the entry being updated (id8).
    pub reviewer_id: String,
    /// Session id for the entry being updated (id8).
    pub session_id: String,
    /// Author role for the new note.
    pub role: NoteRole,
    /// Structured note type.
    pub note_type: NoteType,
    /// Note content (string by default; arbitrary JSON allowed).
    pub content: Value,
    /// Timestamp written for the note and `updated_at`.
    pub now: OffsetDateTime,
    /// Lock owner id8 used while updating `_session.json`.
    pub lock_owner: String,
}

/// Append a note to the `notes` array for a review entry.
pub fn append_note(params: AppendNoteParams) -> anyhow::Result<()> {
    validate_id8(&params.reviewer_id, "reviewer_id")?;
    validate_id8(&params.session_id, "session_id")?;
    validate_id8(&params.lock_owner, "lock_owner")?;

    let lock_owner = params.lock_owner.clone();
    let _guard = lock::acquire_lock(
        params.session.session_dir(),
        lock_owner.clone(),
        LockConfig::default(),
    )?;
    let mut session = read_session_file(params.session.session_dir())?;
    let entry = session
        .reviews
        .iter_mut()
        .find(|r| r.reviewer_id == params.reviewer_id && r.session_id == params.session_id)
        .ok_or_else(|| anyhow::anyhow!("review entry not found for reviewer_id/session_id"))?;

    entry.notes.push(SessionNote {
        role: params.role,
        timestamp: format_ts(params.now)?,
        note_type: params.note_type,
        content: params.content,
    });
    entry.updated_at = format_ts(params.now)?;

    write_session_file_atomic(params.session.session_dir(), &lock_owner, &session)?;
    Ok(())
}

#[derive(Debug, Clone)]
/// Parameters for [`set_initiator_status`].
pub struct SetInitiatorStatusParams {
    /// Session directory locator.
    pub session: SessionLocator,
    /// Reviewer id for the entry being updated (id8).
    pub reviewer_id: String,
    /// Session id for the entry being updated (id8).
    pub session_id: String,
    /// New applicator-owned status to set.
    pub initiator_status: InitiatorStatus,
    /// Timestamp written to `updated_at`.
    pub now: OffsetDateTime,
    /// Lock owner id8 used while updating `_session.json`.
    pub lock_owner: String,
}

/// Set the applicator-owned `initiator_status` field for a review entry.
pub fn set_initiator_status(params: SetInitiatorStatusParams) -> anyhow::Result<()> {
    validate_id8(&params.reviewer_id, "reviewer_id")?;
    validate_id8(&params.session_id, "session_id")?;
    validate_id8(&params.lock_owner, "lock_owner")?;

    let lock_owner = params.lock_owner.clone();
    let _guard = lock::acquire_lock(
        params.session.session_dir(),
        lock_owner.clone(),
        LockConfig::default(),
    )?;
    let mut session = read_session_file(params.session.session_dir())?;
    let entry = session
        .reviews
        .iter_mut()
        .find(|r| r.reviewer_id == params.reviewer_id && r.session_id == params.session_id)
        .ok_or_else(|| anyhow::anyhow!("review entry not found for reviewer_id/session_id"))?;

    entry.initiator_status = params.initiator_status;
    entry.updated_at = format_ts(params.now)?;

    write_session_file_atomic(params.session.session_dir(), &lock_owner, &session)?;
    Ok(())
}
