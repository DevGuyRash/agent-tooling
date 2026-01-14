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
    #[must_use]
    pub const fn is_terminal(self) -> bool {
        matches!(self, Self::Finished | Self::Cancelled | Self::Error)
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
            Self::Initializing => {
                PossibleValue::new("INITIALIZING").help("Registered; review not yet started")
            }
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
            Self::DomainCoverage => {
                PossibleValue::new("DOMAIN_COVERAGE").help("Domain coverage map / scoping")
            }
            Self::TheoremGeneration => {
                PossibleValue::new("THEOREM_GENERATION").help("Generate must-prove theorems")
            }
            Self::AdversarialProofs => PossibleValue::new("ADVERSARIAL_PROOFS")
                .help("Attempt disproofs / adversarial testing"),
            Self::Synthesis => {
                PossibleValue::new("SYNTHESIS").help("Synthesize findings/mitigations")
            }
            Self::ReportWriting => {
                PossibleValue::new("REPORT_WRITING").help("Write the final report")
            }
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
            Self::RequestChanges => {
                PossibleValue::new("REQUEST_CHANGES").help("Changes required before merge")
            }
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
            Self::BlockerPreview => {
                PossibleValue::new("blocker_preview").help("Early warning of a likely blocker")
            }
            Self::Question => PossibleValue::new("question").help("Request clarification"),
            Self::Handoff => PossibleValue::new("handoff").help("Context for another reviewer"),
            Self::ErrorDetail => {
                PossibleValue::new("error_detail").help("Error details / debugging info")
            }
            Self::Applied => PossibleValue::new("applied").help("Feedback was applied"),
            Self::Declined => {
                PossibleValue::new("declined").help("Feedback was declined (include reason)")
            }
            Self::Deferred => {
                PossibleValue::new("deferred").help("Feedback deferred (include tracking)")
            }
            Self::ClarificationNeeded => {
                PossibleValue::new("clarification_needed").help("Request more detail before acting")
            }
            Self::AlreadyAddressed => PossibleValue::new("already_addressed")
                .help("Already handled elsewhere (reference)"),
            Self::Acknowledged => {
                PossibleValue::new("acknowledged").help("Read/understood; no action")
            }
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
    #[must_use]
    pub const fn zero() -> Self {
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
    /// Report path relative to the repo root (set when finished).
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

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
/// Report view selector for filtering review entries.
pub enum ReportsView {
    /// Reviews not in a terminal status (`INITIALIZING`, `IN_PROGRESS`, `BLOCKED`).
    Open,
    /// Reviews in a terminal status (`FINISHED`, `CANCELLED`, `ERROR`).
    Closed,
    /// Reviews actively in progress (`IN_PROGRESS` only).
    InProgress,
}

impl ReportsView {
    fn matches_status(self, status: ReviewerStatus) -> bool {
        match self {
            Self::Open => !status.is_terminal(),
            Self::Closed => status.is_terminal(),
            Self::InProgress => status == ReviewerStatus::InProgress,
        }
    }
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
/// Optional filters applied on top of a [`ReportsView`].
pub struct ReportsFilters {
    /// Only include reviews for this target ref.
    pub target_ref: Option<String>,
    /// Only include reviews for this session id.
    pub session_id: Option<String>,
    /// Only include reviews for this reviewer id.
    pub reviewer_id: Option<String>,
    /// Only include reviews with these reviewer-owned statuses.
    pub reviewer_statuses: Vec<ReviewerStatus>,
    /// Only include reviews with these initiator-owned statuses.
    pub initiator_statuses: Vec<InitiatorStatus>,
    /// Only include reviews with these verdicts.
    pub verdicts: Vec<ReviewVerdict>,
    /// Only include reviews with these phase markers.
    pub phases: Vec<ReviewPhase>,
    /// Only include reviews that already have a report file.
    pub only_with_report: bool,
    /// Only include reviews that contain at least one note.
    pub only_with_notes: bool,
}

impl ReportsFilters {
    fn matches(&self, entry: &ReviewEntry) -> bool {
        if let Some(ref target_ref) = self.target_ref {
            if entry.target_ref != target_ref.as_str() {
                return false;
            }
        }
        if let Some(ref session_id) = self.session_id {
            if entry.session_id != session_id.as_str() {
                return false;
            }
        }
        if let Some(ref reviewer_id) = self.reviewer_id {
            if entry.reviewer_id != reviewer_id.as_str() {
                return false;
            }
        }
        if !self.reviewer_statuses.is_empty() && !self.reviewer_statuses.contains(&entry.status) {
            return false;
        }
        if !self.initiator_statuses.is_empty()
            && !self.initiator_statuses.contains(&entry.initiator_status)
        {
            return false;
        }
        if !self.verdicts.is_empty() {
            match entry.verdict {
                Some(verdict) if self.verdicts.contains(&verdict) => {}
                _ => return false,
            }
        }
        if !self.phases.is_empty() {
            match entry.current_phase {
                Some(phase) if self.phases.contains(&phase) => {}
                _ => return false,
            }
        }
        if self.only_with_report && entry.report_file.is_none() {
            return false;
        }
        if self.only_with_notes && entry.notes.is_empty() {
            return false;
        }
        true
    }
}

#[derive(Debug, Clone, Copy, Default, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
/// Options that control the shape of report listings.
pub struct ReportsOptions {
    /// Include full notes for each review entry.
    pub include_notes: bool,
    /// Include report markdown contents when available.
    pub include_report_contents: bool,
}

#[derive(Debug, Clone, Serialize)]
#[serde(deny_unknown_fields)]
/// Summary view of a review entry for reports.
pub struct ReviewSummary {
    /// Reviewer id.
    pub reviewer_id: String,
    /// Session id.
    pub session_id: String,
    /// Target reference under review.
    pub target_ref: String,
    /// Applicator-owned progress state.
    pub initiator_status: InitiatorStatus,
    /// Reviewer-owned progress state.
    pub status: ReviewerStatus,
    /// Optional parent reviewer id.
    pub parent_id: Option<String>,
    /// When the reviewer registered the entry.
    pub started_at: String,
    /// Last update timestamp.
    pub updated_at: String,
    /// Finished timestamp (if finalized).
    pub finished_at: Option<String>,
    /// Optional review phase marker.
    pub current_phase: Option<ReviewPhase>,
    /// Optional final verdict.
    pub verdict: Option<ReviewVerdict>,
    /// Severity counts from the report.
    pub counts: SeverityCounts,
    /// Report path relative to the repo root (if finalized).
    pub report_file: Option<String>,
    /// Report path (if finalized).
    #[serde(skip_serializing_if = "Option::is_none")]
    pub report_path: Option<String>,
    /// Report markdown contents (when requested and available).
    #[serde(skip_serializing_if = "Option::is_none")]
    pub report_contents: Option<String>,
    /// Report read error (when requested and the file could not be read).
    #[serde(skip_serializing_if = "Option::is_none")]
    pub report_error: Option<String>,
    /// Number of notes attached to the review entry.
    pub notes_count: usize,
    /// Optional full notes (included when requested).
    #[serde(skip_serializing_if = "Option::is_none")]
    pub notes: Option<Vec<SessionNote>>,
}

fn strip_repo_root_best_effort(repo_root: &Path, path: &Path) -> Option<PathBuf> {
    if let Ok(stripped) = path.strip_prefix(repo_root) {
        return Some(stripped.to_path_buf());
    }

    // Handle common cases where `repo_root` is canonicalized but `path` is not (symlinks, etc).
    let canonical_repo_root = repo_root.canonicalize().ok();
    let canonical_path = path.canonicalize().ok();

    if let Some(ref canonical_path) = canonical_path {
        if let Ok(stripped) = canonical_path.strip_prefix(repo_root) {
            return Some(stripped.to_path_buf());
        }
    }
    if let (Some(ref canonical_path), Some(ref canonical_repo_root)) =
        (canonical_path, canonical_repo_root)
    {
        if let Ok(stripped) = canonical_path.strip_prefix(canonical_repo_root) {
            return Some(stripped.to_path_buf());
        }
    }

    None
}

fn resolve_report_file_path(repo_root: &Path, session_dir: &Path, report_file: &str) -> PathBuf {
    let report_file_path = Path::new(report_file);
    if report_file_path.is_absolute() {
        return report_file_path.to_path_buf();
    }

    // New format: `report_file` is a repo-root-relative path like
    // `.local/reports/code_reviews/YYYY-MM-DD/{...}.md` (preferred for portability across working dirs).
    if report_file_path.components().count() > 1 {
        return repo_root.join(report_file_path);
    }

    // Legacy format: `report_file` is just the filename within the session directory.
    session_dir.join(report_file_path)
}

impl ReviewEntry {
    /// Produce a summarized view suitable for report listings.
    #[must_use]
    pub fn summary(
        &self,
        repo_root: &Path,
        session_dir: &Path,
        options: ReportsOptions,
    ) -> ReviewSummary {
        let report_path = self.report_file.as_ref().map(|file| {
            resolve_report_file_path(repo_root, session_dir, file)
                .to_string_lossy()
                .to_string()
        });
        let notes = if options.include_notes {
            Some(self.notes.clone())
        } else {
            None
        };
        let mut report_contents = None;
        let mut report_error = None;
        if options.include_report_contents {
            if let Some(ref file) = self.report_file {
                let path = resolve_report_file_path(repo_root, session_dir, file);
                match fs::read_to_string(&path) {
                    Ok(contents) => {
                        report_contents = Some(contents);
                    }
                    Err(err) => {
                        report_error = Some(format!("read report file {}: {err}", path.display()));
                    }
                }
            }
        }
        ReviewSummary {
            reviewer_id: self.reviewer_id.clone(),
            session_id: self.session_id.clone(),
            target_ref: self.target_ref.clone(),
            initiator_status: self.initiator_status,
            status: self.status,
            parent_id: self.parent_id.clone(),
            started_at: self.started_at.clone(),
            updated_at: self.updated_at.clone(),
            finished_at: self.finished_at.clone(),
            current_phase: self.current_phase,
            verdict: self.verdict,
            counts: self.counts.clone(),
            report_file: self.report_file.clone(),
            report_path,
            report_contents,
            report_error,
            notes_count: self.notes.len(),
            notes,
        }
    }
}

#[derive(Debug, Clone, Serialize)]
#[serde(deny_unknown_fields)]
/// Result payload for report listings.
pub struct ReportsResult {
    /// Session directory containing `_session.json`.
    pub session_dir: String,
    /// Full path to `_session.json`.
    pub session_file: String,
    /// View selector used for this listing.
    pub view: ReportsView,
    /// Optional filters applied to the listing.
    pub filters: ReportsFilters,
    /// Listing options used for this output.
    pub options: ReportsOptions,
    /// Total number of reviews in the session.
    pub total_reviews: usize,
    /// Number of reviews matching the view + filters.
    pub matching_reviews: usize,
    /// Matching review summaries.
    pub reviews: Vec<ReviewSummary>,
}

/// Build a report listing for the given session data.
#[must_use]
pub fn collect_reports(
    session: &SessionFile,
    locator: &SessionLocator,
    view: ReportsView,
    filters: ReportsFilters,
    options: ReportsOptions,
) -> ReportsResult {
    let total_reviews = session.reviews.len();
    let repo_root = Path::new(&session.repo_root);
    let mut reviews = Vec::new();
    for entry in &session.reviews {
        if !filters.matches(entry) {
            continue;
        }
        if !view.matches_status(entry.status) {
            continue;
        }
        reviews.push(entry.summary(repo_root, locator.session_dir(), options));
    }

    ReportsResult {
        session_dir: locator.session_dir().to_string_lossy().to_string(),
        session_file: locator.session_file().to_string_lossy().to_string(),
        view,
        filters,
        options,
        total_reviews,
        matching_reviews: reviews.len(),
        reviews,
    }
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
///
/// # Errors
/// Returns an error if the session file cannot be read or parsed.
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
    #[must_use]
    pub const fn new(session_dir: PathBuf) -> Self {
        Self { session_dir }
    }

    /// Compute the session directory from `repo_root` and `session_date`.
    #[must_use]
    pub fn from_repo_root(repo_root: &Path, session_date: Date) -> Self {
        let p = paths::session_paths(repo_root, session_date);
        Self {
            session_dir: p.session_dir,
        }
    }

    /// Borrow the session directory path.
    #[must_use]
    pub fn session_dir(&self) -> &Path {
        &self.session_dir
    }

    /// Compute the full path to `_session.json` inside this session directory.
    #[must_use]
    pub fn session_file(&self) -> PathBuf {
        session_file_path(&self.session_dir)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use anyhow::{bail, ensure};
    use serde_json::Value;
    use std::fs;
    use tempfile::tempdir;
    use time::Month;

    fn write_session(session_dir: &Path, session: &SessionFile) -> anyhow::Result<()> {
        fs::create_dir_all(session_dir)?;
        let path = session_dir.join("_session.json");
        let body = serde_json::to_string_pretty(session)? + "\n";
        fs::write(path, body)?;
        Ok(())
    }

    fn make_entry() -> ReviewEntry {
        ReviewEntry {
            reviewer_id: "deadbeef".to_string(),
            session_id: "sess0001".to_string(),
            target_ref: "refs/heads/main".to_string(),
            initiator_status: InitiatorStatus::Received,
            status: ReviewerStatus::Finished,
            parent_id: None,
            started_at: "2026-01-11T00:00:00Z".to_string(),
            updated_at: "2026-01-11T01:00:00Z".to_string(),
            finished_at: Some("2026-01-11T02:00:00Z".to_string()),
            current_phase: Some(ReviewPhase::ReportWriting),
            verdict: Some(ReviewVerdict::Approve),
            counts: SeverityCounts::zero(),
            report_file: Some(
                ".local/reports/code_reviews/2026-01-11/12-00-00-000_refs_heads_main_deadbeef.md"
                    .to_string(),
            ),
            notes: vec![SessionNote {
                role: NoteRole::Reviewer,
                timestamp: "2026-01-11T01:30:00Z".to_string(),
                note_type: NoteType::Question,
                content: Value::String("context".to_string()),
            }],
        }
    }

    #[test]
    fn reports_filters_match_status_phase_verdict() -> anyhow::Result<()> {
        let entry = make_entry();
        let filters = ReportsFilters {
            target_ref: None,
            session_id: None,
            reviewer_id: None,
            reviewer_statuses: vec![ReviewerStatus::Finished],
            initiator_statuses: vec![InitiatorStatus::Received],
            verdicts: vec![ReviewVerdict::Approve],
            phases: vec![ReviewPhase::ReportWriting],
            only_with_report: true,
            only_with_notes: true,
        };
        ensure!(filters.matches(&entry));

        let mismatched = ReportsFilters {
            target_ref: None,
            session_id: None,
            reviewer_id: None,
            reviewer_statuses: vec![ReviewerStatus::Blocked],
            initiator_statuses: Vec::new(),
            verdicts: Vec::new(),
            phases: Vec::new(),
            only_with_report: false,
            only_with_notes: false,
        };
        ensure!(!mismatched.matches(&entry));

        Ok(())
    }

    #[test]
    fn register_reviewer_errors_on_target_mismatch() -> anyhow::Result<()> {
        let repo_root = tempdir()?;
        let session_dir = tempdir()?;
        let session_date = Date::from_calendar_date(2026, Month::January, 11)?;
        let session = SessionLocator::new(session_dir.path().to_path_buf());
        let now = OffsetDateTime::now_utc();

        register_reviewer(RegisterReviewerParams {
            repo_root: repo_root.path().to_path_buf(),
            session_date,
            session: session.clone(),
            target_ref: "refs/heads/main".to_string(),
            reviewer_id: Some("deadbeef".to_string()),
            session_id: Some("sess0001".to_string()),
            parent_id: None,
            now,
        })?;

        let result = register_reviewer(RegisterReviewerParams {
            repo_root: repo_root.path().to_path_buf(),
            session_date,
            session,
            target_ref: "refs/heads/other".to_string(),
            reviewer_id: Some("deadbeef".to_string()),
            session_id: Some("sess0001".to_string()),
            parent_id: None,
            now,
        });
        let Err(err) = result else {
            bail!("mismatched target_ref should fail");
        };
        ensure!(err.to_string().contains("target_ref"));
        Ok(())
    }

    #[test]
    fn update_review_missing_entry() -> anyhow::Result<()> {
        let dir = tempdir()?;
        let session_dir = dir.path().join("session");
        let session = SessionFile {
            schema_version: "1.0.0".to_string(),
            session_date: "2026-01-11".to_string(),
            repo_root: dir.path().to_string_lossy().to_string(),
            reviewers: Vec::new(),
            reviews: Vec::new(),
        };
        write_session(&session_dir, &session)?;

        let params = UpdateReviewParams {
            session: SessionLocator::new(session_dir),
            reviewer_id: "deadbeef".to_string(),
            session_id: "sess0001".to_string(),
            status: Some(ReviewerStatus::InProgress),
            phase: None,
            now: OffsetDateTime::now_utc(),
        };
        let Err(err) = update_review(&params) else {
            bail!("missing entry should error");
        };
        ensure!(err.to_string().contains("review entry not found"));
        Ok(())
    }

    #[test]
    fn finalize_review_refuses_overwrite() -> anyhow::Result<()> {
        let dir = tempdir()?;
        let session_dir = dir.path().join("session");
        let entry = ReviewEntry {
            reviewer_id: "deadbeef".to_string(),
            session_id: "sess0001".to_string(),
            target_ref: "refs/heads/main".to_string(),
            initiator_status: InitiatorStatus::Requesting,
            status: ReviewerStatus::Finished,
            parent_id: None,
            started_at: "2026-01-11T00:00:00Z".to_string(),
            updated_at: "2026-01-11T01:00:00Z".to_string(),
            finished_at: Some("2026-01-11T02:00:00Z".to_string()),
            current_phase: Some(ReviewPhase::ReportWriting),
            verdict: Some(ReviewVerdict::Approve),
            counts: SeverityCounts::zero(),
            report_file: Some("existing.md".to_string()),
            notes: Vec::new(),
        };
        let session = SessionFile {
            schema_version: "1.0.0".to_string(),
            session_date: "2026-01-11".to_string(),
            repo_root: dir.path().to_string_lossy().to_string(),
            reviewers: vec!["deadbeef".to_string()],
            reviews: vec![entry],
        };
        write_session(&session_dir, &session)?;

        let params = FinalizeReviewParams {
            session: SessionLocator::new(session_dir),
            reviewer_id: "deadbeef".to_string(),
            session_id: "sess0001".to_string(),
            verdict: ReviewVerdict::Approve,
            counts: SeverityCounts::zero(),
            report_markdown: "report\n".to_string(),
            now: OffsetDateTime::now_utc(),
        };
        let Err(err) = finalize_review(params) else {
            bail!("should refuse overwrite");
        };
        ensure!(err.to_string().contains("report_file already set"));
        Ok(())
    }

    #[test]
    fn append_note_rejects_bad_lock_owner() -> anyhow::Result<()> {
        let dir = tempdir()?;
        let session_dir = dir.path().join("session");
        let entry = ReviewEntry {
            reviewer_id: "deadbeef".to_string(),
            session_id: "sess0001".to_string(),
            target_ref: "refs/heads/main".to_string(),
            initiator_status: InitiatorStatus::Requesting,
            status: ReviewerStatus::Initializing,
            parent_id: None,
            started_at: "2026-01-11T00:00:00Z".to_string(),
            updated_at: "2026-01-11T01:00:00Z".to_string(),
            finished_at: None,
            current_phase: None,
            verdict: None,
            counts: SeverityCounts::zero(),
            report_file: None,
            notes: Vec::new(),
        };
        let session = SessionFile {
            schema_version: "1.0.0".to_string(),
            session_date: "2026-01-11".to_string(),
            repo_root: dir.path().to_string_lossy().to_string(),
            reviewers: vec!["deadbeef".to_string()],
            reviews: vec![entry],
        };
        write_session(&session_dir, &session)?;

        let params = AppendNoteParams {
            session: SessionLocator::new(session_dir),
            reviewer_id: "deadbeef".to_string(),
            session_id: "sess0001".to_string(),
            role: NoteRole::Reviewer,
            note_type: NoteType::Question,
            content: Value::String("why?".to_string()),
            now: OffsetDateTime::now_utc(),
            lock_owner: "bad".to_string(),
        };
        let Err(err) = append_note(params) else {
            bail!("bad lock_owner should error");
        };
        ensure!(err.to_string().contains("lock_owner"));
        Ok(())
    }

    #[test]
    fn strip_repo_root_best_effort_strips_exact_prefix() -> anyhow::Result<()> {
        let dir = tempdir()?;
        let repo_root = dir.path().join("repo");
        let expected = PathBuf::from(".local")
            .join("reports")
            .join("code_reviews")
            .join("2026-01-11")
            .join("report.md");
        let report_path = repo_root.join(&expected);

        let Some(parent) = report_path.parent() else {
            bail!("report_path should have a parent");
        };
        fs::create_dir_all(parent)?;
        fs::write(&report_path, "report")?;

        let Some(actual) = strip_repo_root_best_effort(&repo_root, &report_path) else {
            bail!("expected Some(..) for exact prefix match");
        };
        ensure!(actual == expected);
        Ok(())
    }

    #[test]
    fn strip_repo_root_best_effort_strips_canonicalized_prefix() -> anyhow::Result<()> {
        let dir = tempdir()?;
        let repo_root = dir.path().join("repo");
        fs::create_dir_all(repo_root.join("subdir"))?;

        let expected = PathBuf::from(".local")
            .join("reports")
            .join("code_reviews")
            .join("2026-01-11")
            .join("report.md");
        let report_path = repo_root.join(&expected);

        let Some(parent) = report_path.parent() else {
            bail!("report_path should have a parent");
        };
        fs::create_dir_all(parent)?;
        fs::write(&report_path, "report")?;

        // Introduce non-canonical `..` components so the initial `strip_prefix` fails,
        // but canonicalization succeeds.
        let repo_root_with_dotdot = repo_root.join("subdir").join("..");
        let Some(actual) = strip_repo_root_best_effort(&repo_root_with_dotdot, &report_path) else {
            bail!("expected Some(..) via canonicalization fallback");
        };
        ensure!(actual == expected);
        Ok(())
    }

    #[test]
    fn strip_repo_root_best_effort_returns_none_for_unrelated_local_root() -> anyhow::Result<()> {
        let dir = tempdir()?;
        let real_repo_root = dir.path().join("repo");
        let other_root = dir.path().join("other");
        fs::create_dir_all(&other_root)?;

        let expected = PathBuf::from(".local")
            .join("reports")
            .join("code_reviews")
            .join("2026-01-11")
            .join("report.md");
        let report_path = real_repo_root.join(&expected);

        let Some(parent) = report_path.parent() else {
            bail!("report_path should have a parent");
        };
        fs::create_dir_all(parent)?;
        fs::write(&report_path, "report")?;

        ensure!(strip_repo_root_best_effort(&other_root, &report_path).is_none());
        Ok(())
    }

    #[test]
    fn strip_repo_root_best_effort_returns_none_without_match_or_local() -> anyhow::Result<()> {
        let dir = tempdir()?;
        let repo_root = dir.path().join("repo");
        fs::create_dir_all(&repo_root)?;

        let report_path = dir.path().join("somewhere").join("report.md");
        let Some(parent) = report_path.parent() else {
            bail!("report_path should have a parent");
        };
        fs::create_dir_all(parent)?;
        fs::write(&report_path, "report")?;

        ensure!(strip_repo_root_best_effort(&repo_root, &report_path).is_none());
        Ok(())
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
///
/// # Errors
/// Returns an error if identifiers are invalid, the session cannot be read or written,
/// or the lock cannot be acquired.
#[allow(clippy::too_many_lines)]
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

    let mut session = if params.session.session_file().exists() {
        read_session_file(params.session.session_dir())?
    } else {
        let repo_root = params
            .repo_root
            .canonicalize()
            .with_context(|| format!("canonicalize repo_root {}", params.repo_root.display()))?;
        SessionFile {
            schema_version: "1.0.0".to_string(),
            session_date: params.session_date.to_string(),
            repo_root: repo_root.to_string_lossy().to_string(),
            reviewers: vec![],
            reviews: vec![],
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

    let initiator_status = session
        .reviews
        .iter()
        .find(|r| r.target_ref == params.target_ref && r.session_id == session_id.as_str())
        .map_or(InitiatorStatus::Requesting, |existing| {
            existing.initiator_status
        });

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
///
/// # Errors
/// Returns an error if identifiers are invalid, the session cannot be read or written,
/// or the lock cannot be acquired.
pub fn update_review(params: &UpdateReviewParams) -> anyhow::Result<()> {
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
    /// Report path relative to the repo root.
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
///
/// # Errors
/// Returns an error if identifiers are invalid, report files cannot be written,
/// or the session cannot be read or written.
pub fn finalize_review(params: FinalizeReviewParams) -> anyhow::Result<FinalizeReviewResult> {
    validate_id8(&params.reviewer_id, "reviewer_id")?;
    validate_id8(&params.session_id, "session_id")?;

    // Step 1: read the session file (locked) and compute the report filename.
    let started_at;
    let target_ref;
    let repo_root;
    {
        let lock_owner = params.reviewer_id.clone();
        let _guard = lock::acquire_lock(
            params.session.session_dir(),
            lock_owner,
            LockConfig::default(),
        )?;
        let session = read_session_file(params.session.session_dir())?;
        repo_root = PathBuf::from(&session.repo_root);
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

    let report_file = strip_repo_root_best_effort(&repo_root, &report_path)
        .map_or(filename, |rel| rel.to_string_lossy().to_string());

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
        entry.report_file = Some(report_file.clone());
        entry.finished_at = Some(format_ts(params.now)?);
        entry.updated_at = format_ts(params.now)?;

        write_session_file_atomic(params.session.session_dir(), &params.reviewer_id, &session)?;
    }

    Ok(FinalizeReviewResult {
        report_file,
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
///
/// # Errors
/// Returns an error if identifiers are invalid, the session cannot be read or written,
/// or the lock cannot be acquired.
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
///
/// # Errors
/// Returns an error if identifiers are invalid, the session cannot be read or written,
/// or the lock cannot be acquired.
pub fn set_initiator_status(params: &SetInitiatorStatusParams) -> anyhow::Result<()> {
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
