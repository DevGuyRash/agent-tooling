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
use std::collections::{BTreeMap, BTreeSet, HashMap, HashSet, VecDeque};
use std::fs;
use std::io::{ErrorKind, Write};
use std::path::{Path, PathBuf};
use time::format_description::well_known::Rfc3339;
use time::{Date, OffsetDateTime};

const SESSION_SCHEMA_VERSION: &str = "1.1.0";

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
    /// Overengineering guard supplemental phase.
    OverengineeringGuard,
    /// Complexity analysis supplemental phase.
    ComplexityAnalysis,
    /// Ship-readiness assessment supplemental phase.
    ShipReadiness,
    /// Review completed (worker self-signaling).
    Completed,
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
            Self::OverengineeringGuard,
            Self::ComplexityAnalysis,
            Self::ShipReadiness,
            Self::Completed,
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
            Self::OverengineeringGuard => {
                PossibleValue::new("OVERENGINEERING_GUARD").help("Overengineering guard analysis")
            }
            Self::ComplexityAnalysis => {
                PossibleValue::new("COMPLEXITY_ANALYSIS").help("Complexity analysis phase")
            }
            Self::ShipReadiness => {
                PossibleValue::new("SHIP_READINESS").help("Ship-readiness assessment")
            }
            Self::Completed => {
                PossibleValue::new("COMPLETED").help("Review completed by worker")
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
            s if s.eq_ignore_ascii_case("OVERENGINEERING_GUARD") => Ok(Self::OverengineeringGuard),
            s if s.eq_ignore_ascii_case("COMPLEXITY_ANALYSIS") => Ok(Self::ComplexityAnalysis),
            s if s.eq_ignore_ascii_case("SHIP_READINESS") => Ok(Self::ShipReadiness),
            s if s.eq_ignore_ascii_case("COMPLETED") => Ok(Self::Completed),
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
    /// Worker proof packet summary attached to child completion.
    ProofPacket,
    /// System note when parent finalization auto-closes unresolved children.
    AutoClosedByParentFinalize,
}

impl NoteType {
    const fn allowed_for_role(&self, role: NoteRole) -> bool {
        match role {
            NoteRole::Reviewer => matches!(
                self,
                Self::EscalationTrigger
                    | Self::DomainObservation
                    | Self::BlockerPreview
                    | Self::Question
                    | Self::Handoff
                    | Self::ErrorDetail
                    | Self::ProofPacket
                    | Self::AutoClosedByParentFinalize
            ),
            NoteRole::Applicator => matches!(
                self,
                Self::ErrorDetail
                    | Self::Applied
                    | Self::Declined
                    | Self::Deferred
                    | Self::ClarificationNeeded
                    | Self::AlreadyAddressed
                    | Self::Acknowledged
            ),
        }
    }
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
            Self::ProofPacket,
            Self::AutoClosedByParentFinalize,
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
            Self::ProofPacket => {
                PossibleValue::new("proof_packet").help("Worker proof packet summary")
            }
            Self::AutoClosedByParentFinalize => {
                PossibleValue::new("auto_closed_by_parent_finalize")
                    .help("Child auto-closed by parent finalization")
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
            s if s.eq_ignore_ascii_case("proof_packet")
                || s.eq_ignore_ascii_case("PROOF_PACKET") =>
            {
                Ok(Self::ProofPacket)
            }
            s if s.eq_ignore_ascii_case("auto_closed_by_parent_finalize")
                || s.eq_ignore_ascii_case("AUTO_CLOSED_BY_PARENT_FINALIZE") =>
            {
                Ok(Self::AutoClosedByParentFinalize)
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
    /// Embedded child review summaries owned by this parent reviewer entry.
    #[serde(default)]
    pub child_reviews: Vec<ChildReviewEntry>,
    /// Unknown fields preserved for forward compatibility.
    #[serde(flatten)]
    pub extra: serde_json::Map<String, serde_json::Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
/// Embedded summary for a child review entry nested under its parent.
pub struct ChildReviewEntry {
    /// 8-character child reviewer id.
    pub reviewer_id: String,
    /// 8-character session id.
    pub session_id: String,
    /// Target reference being reviewed (branch, PR ref, commit, etc).
    pub target_ref: String,
    /// Applicator-owned progress state for consuming this child review.
    pub initiator_status: InitiatorStatus,
    /// Reviewer-owned progress state for the child.
    pub status: ReviewerStatus,
    /// Parent reviewer id for lineage.
    pub parent_id: Option<String>,
    /// RFC3339 timestamp (UTC) when the child was registered.
    pub started_at: String,
    /// RFC3339 timestamp (UTC) of the last child update.
    pub updated_at: String,
    /// RFC3339 timestamp (UTC) when the child was finalized (if finished).
    pub finished_at: Option<String>,
    /// Optional reviewer phase marker.
    pub current_phase: Option<ReviewPhase>,
    /// Optional final verdict.
    pub verdict: Option<ReviewVerdict>,
    /// Severity counts extracted from the report.
    pub counts: SeverityCounts,
    /// Report path relative to the repo root (if finalized).
    pub report_file: Option<String>,
    /// Number of notes attached to the child review entry.
    pub notes_count: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
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
    /// Unknown top-level fields preserved for forward compatibility.
    #[serde(flatten)]
    pub extra: serde_json::Map<String, Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct SessionFileDisk {
    pub schema_version: String,
    pub session_date: String,
    pub repo_root: String,
    pub reviewers: Vec<String>,
    pub reviews: Vec<ReviewEntryDisk>,
    #[serde(flatten)]
    pub extra: serde_json::Map<String, Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct ReviewEntryDisk {
    pub reviewer_id: String,
    pub session_id: String,
    pub target_ref: String,
    pub initiator_status: InitiatorStatus,
    pub status: ReviewerStatus,
    pub parent_id: Option<String>,
    pub started_at: String,
    pub updated_at: String,
    pub finished_at: Option<String>,
    pub current_phase: Option<ReviewPhase>,
    pub verdict: Option<ReviewVerdict>,
    pub counts: SeverityCounts,
    pub report_file: Option<String>,
    #[serde(default)]
    pub notes: Vec<SessionNote>,
    #[serde(default)]
    pub child_reviews: Vec<Self>,
    #[serde(flatten)]
    pub extra: serde_json::Map<String, serde_json::Value>,
}

impl ReviewEntryDisk {
    fn from_review_entry(entry: &ReviewEntry) -> Self {
        Self {
            reviewer_id: entry.reviewer_id.clone(),
            session_id: entry.session_id.clone(),
            target_ref: entry.target_ref.clone(),
            initiator_status: entry.initiator_status,
            status: entry.status,
            parent_id: entry.parent_id.clone(),
            started_at: entry.started_at.clone(),
            updated_at: entry.updated_at.clone(),
            finished_at: entry.finished_at.clone(),
            current_phase: entry.current_phase,
            verdict: entry.verdict,
            counts: entry.counts.clone(),
            report_file: entry.report_file.clone(),
            notes: entry.notes.clone(),
            child_reviews: Vec::new(),
            extra: entry.extra.clone(),
        }
    }

    fn to_review_entry(&self) -> ReviewEntry {
        ReviewEntry {
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
            notes: self.notes.clone(),
            child_reviews: Vec::new(),
            extra: self.extra.clone(),
        }
    }
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
    /// Include leaf child reviews in top-level rows (default keeps parent-centric view).
    pub include_leaf_children: bool,
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
    /// Embedded child review summaries for parent entries.
    pub child_reviews: Vec<ChildReviewEntry>,
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

fn ensure_path_contained(path: &Path, boundary: &Path) -> anyhow::Result<PathBuf> {
    if let Ok(canonical) = path.canonicalize() {
        let canonical_boundary = boundary
            .canonicalize()
            .ok()
            .as_deref()
            .map_or_else(|| boundary.to_path_buf(), Path::to_path_buf);
        anyhow::ensure!(
            canonical.starts_with(&canonical_boundary),
            "path escapes boundary after symlink resolution: {} not under {}",
            canonical.display(),
            canonical_boundary.display()
        );
        return Ok(canonical);
    }
    if let Some(parent) = path.parent() {
        if let Ok(canonical_parent) = parent.canonicalize() {
            let canonical_boundary = boundary
                .canonicalize()
                .ok()
                .as_deref()
                .map_or_else(|| boundary.to_path_buf(), Path::to_path_buf);
            let canonical = canonical_parent.join(
                path.file_name()
                    .map_or_else(|| std::ffi::OsStr::new(""), std::convert::identity),
            );
            anyhow::ensure!(
                canonical.starts_with(&canonical_boundary),
                "path escapes boundary after symlink resolution: {} not under {}",
                canonical.display(),
                canonical_boundary.display()
            );
            return Ok(canonical);
        }
    }
    anyhow::ensure!(
        path.starts_with(boundary),
        "path escapes boundary: {} not under {}",
        path.display(),
        boundary.display()
    );
    Ok(path.to_path_buf())
}

fn resolve_report_file_path(
    repo_root: &Path,
    session_dir: &Path,
    report_file: &str,
) -> anyhow::Result<PathBuf> {
    let report_file_path = Path::new(report_file);

    if report_file_path
        .components()
        .any(|c| matches!(c, std::path::Component::ParentDir))
    {
        anyhow::bail!("report_file must not contain '..' components: {report_file}");
    }

    if report_file_path.is_absolute() {
        return ensure_path_contained(report_file_path, repo_root);
    }

    // New format: `report_file` is a repo-root-relative path like
    // `.local/reports/code_reviews/YYYY-MM-DD/{...}.md` (preferred for portability across working dirs).
    if report_file_path.components().count() > 1 {
        return ensure_path_contained(&repo_root.join(report_file_path), repo_root);
    }

    // Legacy format: `report_file` is just the filename within the session directory.
    ensure_path_contained(&session_dir.join(report_file_path), session_dir)
}

fn upsert_child_review(parent_entry: &mut ReviewEntry, child_entry: &ReviewEntry) {
    let next = ChildReviewEntry::from_review_entry(child_entry);
    if let Some(existing) = parent_entry.child_reviews.iter_mut().find(|child| {
        child.reviewer_id == child_entry.reviewer_id && child.session_id == child_entry.session_id
    }) {
        *existing = next;
        return;
    }
    parent_entry.child_reviews.push(next);
}

type ParentReviewKey = (String, String, String);
type ChildReviewKey = (String, String);
type ReviewKey = (String, String);

fn review_key(entry: &ReviewEntry) -> ReviewKey {
    (entry.reviewer_id.clone(), entry.session_id.clone())
}

fn choose_newer_entry(existing: &ReviewEntry, candidate: &ReviewEntry) -> bool {
    if candidate.updated_at > existing.updated_at {
        return true;
    }
    if candidate.updated_at < existing.updated_at {
        return false;
    }
    candidate.notes.len() > existing.notes.len()
}

fn flatten_reviews_disk(
    entries: &[ReviewEntryDisk],
    flat_reviews: &mut BTreeMap<ReviewKey, ReviewEntry>,
) {
    for entry in entries {
        let candidate = entry.to_review_entry();
        let key = review_key(&candidate);
        match flat_reviews.get(&key) {
            Some(existing) if !choose_newer_entry(existing, &candidate) => {}
            _ => {
                flat_reviews.insert(key, candidate);
            }
        }
        flatten_reviews_disk(&entry.child_reviews, flat_reviews);
    }
}

fn flatten_session_file_disk(session: SessionFileDisk) -> SessionFile {
    let mut flat_reviews: BTreeMap<ReviewKey, ReviewEntry> = BTreeMap::new();
    flatten_reviews_disk(&session.reviews, &mut flat_reviews);

    let mut reviewers: BTreeSet<String> = session.reviewers.into_iter().collect();
    for entry in flat_reviews.values() {
        reviewers.insert(entry.reviewer_id.clone());
    }

    let mut flattened = SessionFile {
        schema_version: session.schema_version,
        session_date: session.session_date,
        repo_root: session.repo_root,
        reviewers: reviewers.into_iter().collect(),
        reviews: flat_reviews.into_values().collect(),
        extra: session.extra,
    };
    reconcile_parent_child_reviews(&mut flattened);
    flattened
}

fn dedupe_flat_reviews(reviews: &[ReviewEntry]) -> BTreeMap<ReviewKey, ReviewEntry> {
    let mut by_key: BTreeMap<ReviewKey, ReviewEntry> = BTreeMap::new();
    for entry in reviews {
        let mut candidate = entry.clone();
        candidate.child_reviews = Vec::new();
        let key = review_key(&candidate);
        match by_key.get(&key) {
            Some(existing) if !choose_newer_entry(existing, &candidate) => {}
            _ => {
                by_key.insert(key, candidate);
            }
        }
    }
    by_key
}

fn build_disk_review_node(
    key: &ReviewKey,
    reviews_by_key: &BTreeMap<ReviewKey, ReviewEntry>,
    children_by_parent: &BTreeMap<ParentReviewKey, Vec<ReviewKey>>,
    visiting: &mut BTreeSet<ReviewKey>,
) -> anyhow::Result<ReviewEntryDisk> {
    if !visiting.insert(key.clone()) {
        return Err(anyhow::anyhow!(
            "cycle detected while building child review tree"
        ));
    }

    let entry = reviews_by_key
        .get(key)
        .ok_or_else(|| anyhow::anyhow!("review entry missing while building child review tree"))?;
    let parent_key = (
        entry.reviewer_id.clone(),
        entry.session_id.clone(),
        entry.target_ref.clone(),
    );

    let mut child_keys = children_by_parent
        .get(&parent_key)
        .cloned()
        .map_or_else(Vec::new, std::convert::identity);
    child_keys.sort();
    child_keys.dedup();

    let mut child_reviews = Vec::with_capacity(child_keys.len());
    for child_key in child_keys {
        child_reviews.push(build_disk_review_node(
            &child_key,
            reviews_by_key,
            children_by_parent,
            visiting,
        )?);
    }

    visiting.remove(key);

    let mut node = ReviewEntryDisk::from_review_entry(entry);
    node.child_reviews = child_reviews;
    Ok(node)
}

fn canonicalize_session_for_write(session: &SessionFile) -> anyhow::Result<SessionFileDisk> {
    let reviews_by_key = dedupe_flat_reviews(&session.reviews);

    let mut children_by_parent: BTreeMap<ParentReviewKey, Vec<ReviewKey>> = BTreeMap::new();
    for (child_key, entry) in &reviews_by_key {
        let Some(parent_id) = entry.parent_id.as_deref() else {
            continue;
        };
        let parent_exists = reviews_by_key.values().any(|candidate| {
            candidate.reviewer_id == parent_id
                && candidate.session_id == entry.session_id
                && candidate.target_ref == entry.target_ref
        });
        if !parent_exists {
            continue;
        }
        children_by_parent
            .entry((
                parent_id.to_string(),
                entry.session_id.clone(),
                entry.target_ref.clone(),
            ))
            .or_default()
            .push(child_key.clone());
    }

    let mut root_keys = Vec::new();
    for (key, entry) in &reviews_by_key {
        let is_root = entry.parent_id.as_deref().is_none_or(|parent_id| {
            !reviews_by_key.values().any(|candidate| {
                candidate.reviewer_id == parent_id
                    && candidate.session_id == entry.session_id
                    && candidate.target_ref == entry.target_ref
            })
        });
        if is_root {
            root_keys.push(key.clone());
        }
    }
    root_keys.sort();
    root_keys.dedup();

    let mut reviews = Vec::with_capacity(root_keys.len());
    let mut visiting = BTreeSet::new();
    for key in root_keys {
        reviews.push(build_disk_review_node(
            &key,
            &reviews_by_key,
            &children_by_parent,
            &mut visiting,
        )?);
    }

    let mut reviewers: BTreeSet<String> = session.reviewers.iter().cloned().collect();
    for entry in reviews_by_key.values() {
        reviewers.insert(entry.reviewer_id.clone());
    }

    Ok(SessionFileDisk {
        schema_version: SESSION_SCHEMA_VERSION.to_string(),
        session_date: session.session_date.clone(),
        repo_root: session.repo_root.clone(),
        reviewers: reviewers.into_iter().collect(),
        reviews,
        extra: session.extra.clone(),
    })
}

fn sync_child_review_to_parent(
    session: &mut SessionFile,
    reviewer_id: &str,
    session_id: &str,
) -> anyhow::Result<()> {
    let Some(child_index) = session
        .reviews
        .iter()
        .position(|r| r.reviewer_id == reviewer_id && r.session_id == session_id)
    else {
        return Err(anyhow::anyhow!(
            "review entry not found for reviewer_id/session_id"
        ));
    };

    let child_entry = session
        .reviews
        .get(child_index)
        .ok_or_else(|| anyhow::anyhow!("review entry index invalid"))?
        .clone();
    let Some(parent_id) = child_entry.parent_id.as_deref() else {
        return Ok(());
    };

    let parent_index = session.reviews.iter().position(|r| {
        r.reviewer_id == parent_id
            && r.session_id == child_entry.session_id
            && r.target_ref == child_entry.target_ref
    });
    let Some(parent_index) = parent_index else {
        return Err(anyhow::anyhow!(
            "parent review entry not found for child reviewer_id/session_id"
        ));
    };

    let parent_entry = session
        .reviews
        .get_mut(parent_index)
        .ok_or_else(|| anyhow::anyhow!("parent review entry index invalid"))?;
    upsert_child_review(parent_entry, &child_entry);
    Ok(())
}

fn reconcile_parent_child_reviews(session: &mut SessionFile) {
    let mut children_by_parent: BTreeMap<
        ParentReviewKey,
        BTreeMap<ChildReviewKey, ChildReviewEntry>,
    > = BTreeMap::new();

    for entry in &session.reviews {
        let Some(parent_id) = entry.parent_id.as_deref() else {
            continue;
        };
        let parent_key = (
            parent_id.to_string(),
            entry.session_id.clone(),
            entry.target_ref.clone(),
        );
        let child_key = (entry.reviewer_id.clone(), entry.session_id.clone());
        children_by_parent
            .entry(parent_key)
            .or_default()
            .insert(child_key, ChildReviewEntry::from_review_entry(entry));
    }

    for entry in &mut session.reviews {
        let parent_key = (
            entry.reviewer_id.clone(),
            entry.session_id.clone(),
            entry.target_ref.clone(),
        );
        entry.child_reviews = children_by_parent
            .remove(&parent_key)
            .map_or_else(Vec::new, |children| children.into_values().collect());
    }
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
        let report_path = self.report_file.as_ref().and_then(|file| {
            resolve_report_file_path(repo_root, session_dir, file)
                .ok()
                .map(|p| p.to_string_lossy().to_string())
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
                match resolve_report_file_path(repo_root, session_dir, file) {
                    Ok(path) => match fs::read_to_string(&path) {
                        Ok(contents) => {
                            report_contents = Some(contents);
                        }
                        Err(err) => {
                            report_error =
                                Some(format!("read report file {}: {err}", path.display()));
                        }
                    },
                    Err(err) => {
                        report_error = Some(format!("invalid report path: {err}"));
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
            child_reviews: self.child_reviews.clone(),
        }
    }
}

impl ChildReviewEntry {
    fn from_review_entry(entry: &ReviewEntry) -> Self {
        Self {
            reviewer_id: entry.reviewer_id.clone(),
            session_id: entry.session_id.clone(),
            target_ref: entry.target_ref.clone(),
            initiator_status: entry.initiator_status,
            status: entry.status,
            parent_id: entry.parent_id.clone(),
            started_at: entry.started_at.clone(),
            updated_at: entry.updated_at.clone(),
            finished_at: entry.finished_at.clone(),
            current_phase: entry.current_phase,
            verdict: entry.verdict,
            counts: entry.counts.clone(),
            report_file: entry.report_file.clone(),
            notes_count: entry.notes.len(),
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
    let mut total_reviews = 0usize;
    let repo_root = Path::new(&session.repo_root);
    let mut reviews = Vec::new();
    for entry in &session.reviews {
        // Reports are parent-centric: hide leaf child rows. Keep roots and non-leaf
        // child nodes so descendant trees remain visible in multi-level hierarchies.
        if !options.include_leaf_children
            && entry.parent_id.is_some()
            && entry.child_reviews.is_empty()
        {
            continue;
        }
        total_reviews = total_reviews.saturating_add(1);
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
    let parsed: SessionFileDisk =
        serde_json::from_str(&raw).with_context(|| format!("parse JSON {}", path.display()))?;
    Ok(flatten_session_file_disk(parsed))
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
    let mut session_to_write = session.clone();
    reconcile_parent_child_reviews(&mut session_to_write);
    validate_session_consistency(&session_to_write)?;
    let session_disk = canonicalize_session_for_write(&session_to_write)?;
    let body =
        serde_json::to_string_pretty(&session_disk).context("serialize session JSON")? + "\n";
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

fn validate_finished_entry(entry: &ReviewEntry) -> anyhow::Result<()> {
    if entry.status != ReviewerStatus::Finished {
        return Ok(());
    }

    if entry.report_file.is_none() {
        return Err(anyhow::anyhow!(
            "review {}:{} is FINISHED but report_file is missing",
            entry.reviewer_id,
            entry.session_id
        ));
    }
    if entry.verdict.is_none() {
        return Err(anyhow::anyhow!(
            "review {}:{} is FINISHED but verdict is missing",
            entry.reviewer_id,
            entry.session_id
        ));
    }
    if entry.finished_at.is_none() {
        return Err(anyhow::anyhow!(
            "review {}:{} is FINISHED but finished_at is missing",
            entry.reviewer_id,
            entry.session_id
        ));
    }
    Ok(())
}

const MAX_EXTRA_KEYS: usize = 32;

fn validate_session_consistency(session: &SessionFile) -> anyhow::Result<()> {
    if session.extra.len() > MAX_EXTRA_KEYS {
        return Err(anyhow::anyhow!(
            "session file has {} unknown top-level fields (max {}); possible data corruption",
            session.extra.len(),
            MAX_EXTRA_KEYS,
        ));
    }
    for entry in &session.reviews {
        validate_finished_entry(entry)?;
    }
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

/// Parameters for [`purge_reviews`].
pub struct PurgeReviewsParams {
    /// Session directory locator.
    pub session: SessionLocator,
    /// Trusted repository root used for resolving repo-relative report paths.
    pub repo_root: PathBuf,
    /// Only purge reviews matching this reviewer id.
    pub reviewer_id: Option<String>,
    /// Only purge reviews matching this session id.
    pub session_id: Option<String>,
    /// Only purge reviews matching this target ref.
    pub target_ref: Option<String>,
    /// Only purge reviews with these reviewer statuses.
    pub reviewer_statuses: Vec<ReviewerStatus>,
    /// Only purge reviews with these initiator statuses.
    pub initiator_statuses: Vec<InitiatorStatus>,
    /// Only purge reviews with these verdicts.
    pub verdicts: Vec<ReviewVerdict>,
    /// Only purge reviews started at or after this RFC3339 timestamp.
    pub after: Option<String>,
    /// Only purge reviews started at or before this RFC3339 timestamp.
    pub before: Option<String>,
    /// When true, also purge child entries whose parent matches the filters.
    pub include_children: bool,
    /// When true, delete report markdown files from disk.
    pub delete_report_files: bool,
    /// When true, only preview what would be purged without modifying anything.
    pub dry_run: bool,
}

/// A single purged review entry in the result.
#[derive(Debug, Clone, Serialize)]
pub struct PurgedReview {
    /// Reviewer id of the purged entry.
    pub reviewer_id: String,
    /// Session id of the purged entry.
    pub session_id: String,
    /// Report file that was (or would be) deleted.
    pub report_file: Option<String>,
    /// Whether the report file was actually deleted from disk.
    pub report_deleted: bool,
    /// Whether deleting the report file was attempted but failed.
    pub delete_failed: bool,
}

/// Result returned by [`purge_reviews`].
#[derive(Debug, Clone, Serialize)]
pub struct PurgeReviewsResult {
    /// Number of review entries that matched all filters.
    pub matched: usize,
    /// Number of review entries actually removed (0 in dry-run).
    pub purged: usize,
    /// Number of report files deleted from disk (0 in dry-run).
    pub files_deleted: usize,
    /// Whether this was a dry-run preview.
    pub dry_run: bool,
    /// Individual purged review details.
    pub reviews: Vec<PurgedReview>,
}

fn plan_purge_results(
    session: &SessionFile,
    purge_ids: &[(String, String)],
    repo_root: &Path,
    params: &PurgeReviewsParams,
) -> (Vec<PurgedReview>, Vec<PathBuf>) {
    let mut reviews = Vec::with_capacity(purge_ids.len());
    let mut files_to_delete = Vec::new();
    for (rid, sid) in purge_ids {
        let entry = session
            .reviews
            .iter()
            .find(|e| e.reviewer_id == *rid && e.session_id == *sid);
        let report_file = entry.and_then(|e| e.report_file.clone());

        if !params.dry_run && params.delete_report_files {
            if let Some(ref rf) = report_file {
                if let Ok(path) =
                    resolve_report_file_path(repo_root, params.session.session_dir(), rf)
                {
                    if path.exists() {
                        files_to_delete.push(path);
                    }
                }
            }
        }

        reviews.push(PurgedReview {
            reviewer_id: rid.clone(),
            session_id: sid.clone(),
            report_file,
            report_deleted: false,
            delete_failed: false,
        });
    }
    (reviews, files_to_delete)
}

fn infer_repo_root_from_session_dir(session_dir: &Path) -> Option<PathBuf> {
    let canonical_session_dir = session_dir.canonicalize().ok()?;
    let code_reviews_dir = canonical_session_dir.parent()?;
    if code_reviews_dir.file_name()? != "code_reviews" {
        return None;
    }
    let reports_dir = code_reviews_dir.parent()?;
    if reports_dir.file_name()? != "reports" {
        return None;
    }
    let local_dir = reports_dir.parent()?;
    if local_dir.file_name()? != ".local" {
        return None;
    }
    Some(local_dir.parent()?.to_path_buf())
}

/// Purge (permanently remove) review entries and optionally their report files.
///
/// Matching entries are removed from `_session.json`. When `include_children` is true,
/// child entries whose `parent_id` matches a purged parent are also removed. When
/// `delete_report_files` is true, report markdown files referenced by purged entries
/// are deleted from disk.
///
/// # Errors
/// Returns an error if the session cannot be read/written or identifiers are invalid.
#[allow(clippy::too_many_lines)] // Reason: purge coordinates filtering, child collection, deletion, and atomic session write.
pub fn purge_reviews(params: &PurgeReviewsParams) -> anyhow::Result<PurgeReviewsResult> {
    if let Some(ref id) = params.reviewer_id {
        validate_id8(id, "reviewer_id")?;
    }
    if let Some(ref id) = params.session_id {
        validate_id8(id, "session_id")?;
    }

    let lock_owner = mpcr_lock_owner();
    let _guard = lock::acquire_lock(
        params.session.session_dir(),
        lock_owner.clone(),
        LockConfig::default(),
    )?;
    let mut session = read_session_file(params.session.session_dir())?;
    let repo_root_for_cleanup = infer_repo_root_from_session_dir(params.session.session_dir())
        .map_or_else(|| params.repo_root.clone(), std::convert::identity);
    let repo_root = repo_root_for_cleanup.as_path();

    // Determine which top-level entries match the filters.
    let parsed_after = params
        .after
        .as_deref()
        .map(|s| OffsetDateTime::parse(s, &Rfc3339))
        .transpose()
        .map_err(|e| anyhow::anyhow!("invalid --after timestamp: {e}"))?;
    let parsed_before = params
        .before
        .as_deref()
        .map(|s| OffsetDateTime::parse(s, &Rfc3339))
        .transpose()
        .map_err(|e| anyhow::anyhow!("invalid --before timestamp: {e}"))?;

    let mut matched_ids: Vec<ReviewKey> = Vec::new();
    for entry in &session.reviews {
        if !entry_matches_purge_filters(entry, params, parsed_after, parsed_before)? {
            continue;
        }
        matched_ids.push((entry.reviewer_id.clone(), entry.session_id.clone()));
    }

    // When include_children is set, collect descendants using an indexed parent->children map.
    let mut child_ids: Vec<ReviewKey> = Vec::new();
    if params.include_children {
        let mut children_by_parent: HashMap<ReviewKey, Vec<ReviewKey>> = HashMap::new();
        for entry in &session.reviews {
            if let Some(parent_id) = &entry.parent_id {
                let parent_key = (parent_id.clone(), entry.session_id.clone());
                children_by_parent
                    .entry(parent_key)
                    .or_default()
                    .push((entry.reviewer_id.clone(), entry.session_id.clone()));
            }
        }

        let mut queue: VecDeque<ReviewKey> = matched_ids.iter().cloned().collect();
        let mut visited: HashSet<ReviewKey> = queue.iter().cloned().collect();
        while let Some(parent_key) = queue.pop_front() {
            if let Some(children) = children_by_parent.get(&parent_key) {
                for child_key in children {
                    if visited.insert(child_key.clone()) {
                        child_ids.push(child_key.clone());
                        queue.push_back(child_key.clone());
                    }
                }
            }
        }
    }

    let all_purge_ids: Vec<ReviewKey> = matched_ids
        .iter()
        .chain(child_ids.iter())
        .cloned()
        .collect();
    let all_purge_set: HashSet<ReviewKey> = all_purge_ids.iter().cloned().collect();

    let (mut reviews, files_to_delete) =
        plan_purge_results(&session, &all_purge_ids, repo_root, params);

    let matched = all_purge_ids.len();
    let purged;
    let mut files_deleted = 0usize;
    if params.dry_run {
        purged = 0;
    } else {
        // Remove matched entries from session.
        session
            .reviews
            .retain(|e| !all_purge_set.contains(&(e.reviewer_id.clone(), e.session_id.clone())));

        // Remove purged children from parent child_reviews arrays.
        for entry in &mut session.reviews {
            entry.child_reviews.retain(|c| {
                !all_purge_set.contains(&(c.reviewer_id.clone(), c.session_id.clone()))
            });
        }

        // Remove purged reviewer ids from the reviewers list if they have no remaining entries.
        session
            .reviewers
            .retain(|rid| session.reviews.iter().any(|e| e.reviewer_id == *rid));

        purged = matched;
        write_session_file_atomic(params.session.session_dir(), &lock_owner, &session)?;

        // Delete report files AFTER the session has been atomically persisted.
        let mut review_indices_by_path: HashMap<PathBuf, Vec<usize>> = HashMap::new();
        for (index, review) in reviews.iter().enumerate() {
            if let Some(path) = review.report_file.as_deref().and_then(|rf| {
                resolve_report_file_path(repo_root, params.session.session_dir(), rf).ok()
            }) {
                review_indices_by_path.entry(path).or_default().push(index);
            }
        }

        let unique_files_to_delete: BTreeSet<PathBuf> = files_to_delete.iter().cloned().collect();
        for path in unique_files_to_delete {
            let delete_ok = std::fs::remove_file(&path).is_ok();
            if delete_ok {
                files_deleted += 1;
            }

            if let Some(indices) = review_indices_by_path.get(&path) {
                for index in indices {
                    if let Some(review) = reviews.get_mut(*index) {
                        if delete_ok {
                            review.report_deleted = true;
                        } else {
                            review.delete_failed = true;
                        }
                    }
                }
            }
        }
    }

    Ok(PurgeReviewsResult {
        matched,
        purged,
        files_deleted,
        dry_run: params.dry_run,
        reviews,
    })
}

fn mpcr_lock_owner() -> String {
    format!("mpcr_purge_{}", std::process::id())
}

fn entry_matches_purge_filters(
    entry: &ReviewEntry,
    params: &PurgeReviewsParams,
    parsed_after: Option<OffsetDateTime>,
    parsed_before: Option<OffsetDateTime>,
) -> anyhow::Result<bool> {
    if let Some(ref reviewer_id) = params.reviewer_id {
        if entry.reviewer_id != *reviewer_id {
            return Ok(false);
        }
    }
    if let Some(ref session_id) = params.session_id {
        if entry.session_id != *session_id {
            return Ok(false);
        }
    }
    if let Some(ref target_ref) = params.target_ref {
        if entry.target_ref != *target_ref {
            return Ok(false);
        }
    }
    if !params.reviewer_statuses.is_empty() && !params.reviewer_statuses.contains(&entry.status) {
        return Ok(false);
    }
    if !params.initiator_statuses.is_empty()
        && !params.initiator_statuses.contains(&entry.initiator_status)
    {
        return Ok(false);
    }
    if !params.verdicts.is_empty() {
        match entry.verdict {
            Some(v) if params.verdicts.contains(&v) => {}
            _ => return Ok(false),
        }
    }
    if let Some(filter_time) = parsed_after {
        let entry_time = OffsetDateTime::parse(&entry.started_at, &Rfc3339)
            .map_err(|e| anyhow::anyhow!("invalid entry started_at: {e}"))?;
        if entry_time < filter_time {
            return Ok(false);
        }
    }
    if let Some(filter_time) = parsed_before {
        let entry_time = OffsetDateTime::parse(&entry.started_at, &Rfc3339)
            .map_err(|e| anyhow::anyhow!("invalid entry started_at: {e}"))?;
        if entry_time > filter_time {
            return Ok(false);
        }
    }
    Ok(true)
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
            child_reviews: vec![],
            extra: serde_json::Map::default(),
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
    fn session_file_deserializes_without_child_reviews() -> anyhow::Result<()> {
        let raw = r#"{
  "schema_version": "1.0.0",
  "session_date": "2026-01-11",
  "repo_root": "/tmp/repo",
  "reviewers": ["deadbeef"],
  "reviews": [
    {
      "reviewer_id": "deadbeef",
      "session_id": "sess0001",
      "target_ref": "refs/heads/main",
      "initiator_status": "REQUESTING",
      "status": "INITIALIZING",
      "parent_id": null,
      "started_at": "2026-01-11T00:00:00Z",
      "updated_at": "2026-01-11T00:00:00Z",
      "finished_at": null,
      "current_phase": null,
      "verdict": null,
      "counts": {"blocker":0,"major":0,"minor":0,"nit":0},
      "report_file": null,
      "notes": []
    }
  ]
}"#;
        let session: SessionFile = serde_json::from_str(raw)?;
        ensure!(session.reviews.len() == 1);
        let review = session
            .reviews
            .first()
            .ok_or_else(|| anyhow::anyhow!("review missing"))?;
        ensure!(review.child_reviews.is_empty());
        Ok(())
    }

    #[test]
    fn close_child_reviews_updates_parent_embedded_state() -> anyhow::Result<()> {
        let dir = tempdir()?;
        let session_dir = dir.path().join("session");
        let session = SessionFile {
            schema_version: SESSION_SCHEMA_VERSION.to_string(),
            session_date: "2026-01-11".to_string(),
            repo_root: dir.path().to_string_lossy().to_string(),
            reviewers: vec!["deadbeef".to_string(), "cafebabe".to_string()],
            reviews: vec![
                ReviewEntry {
                    reviewer_id: "deadbeef".to_string(),
                    session_id: "sess0001".to_string(),
                    target_ref: "refs/heads/main".to_string(),
                    initiator_status: InitiatorStatus::Requesting,
                    status: ReviewerStatus::InProgress,
                    parent_id: None,
                    started_at: "2026-01-11T00:00:00Z".to_string(),
                    updated_at: "2026-01-11T01:00:00Z".to_string(),
                    finished_at: None,
                    current_phase: Some(ReviewPhase::Ingestion),
                    verdict: None,
                    counts: SeverityCounts::zero(),
                    report_file: None,
                    notes: Vec::new(),
                    child_reviews: Vec::new(),
                    extra: serde_json::Map::default(),
                },
                ReviewEntry {
                    reviewer_id: "cafebabe".to_string(),
                    session_id: "sess0001".to_string(),
                    target_ref: "refs/heads/main".to_string(),
                    initiator_status: InitiatorStatus::Requesting,
                    status: ReviewerStatus::InProgress,
                    parent_id: Some("deadbeef".to_string()),
                    started_at: "2026-01-11T00:00:00Z".to_string(),
                    updated_at: "2026-01-11T01:00:00Z".to_string(),
                    finished_at: None,
                    current_phase: Some(ReviewPhase::DomainCoverage),
                    verdict: None,
                    counts: SeverityCounts::zero(),
                    report_file: None,
                    notes: Vec::new(),
                    child_reviews: Vec::new(),
                    extra: serde_json::Map::default(),
                },
            ],
            extra: serde_json::Map::new(),
        };
        write_session(&session_dir, &session)?;

        let result = close_child_reviews(CloseChildReviewsParams {
            session: SessionLocator::new(session_dir.clone()),
            parent_reviewer_id: "deadbeef".to_string(),
            session_id: "sess0001".to_string(),
            target_ref: None,
            only_statuses: vec![ReviewerStatus::InProgress],
            set_status: ReviewerStatus::Cancelled,
            clear_phase: true,
            now: OffsetDateTime::now_utc(),
        })?;
        ensure!(result.updated_children == 1);

        let parsed = read_session_file(&session_dir)?;
        let parent = parsed
            .reviews
            .iter()
            .find(|review| review.reviewer_id == "deadbeef")
            .ok_or_else(|| anyhow::anyhow!("parent missing"))?;
        ensure!(parent.child_reviews.len() == 1);
        let child = parent
            .child_reviews
            .first()
            .ok_or_else(|| anyhow::anyhow!("child missing"))?;
        ensure!(child.status == ReviewerStatus::Cancelled);
        ensure!(child.current_phase.is_none());
        Ok(())
    }

    #[test]
    fn write_session_file_atomic_reconciles_parent_child_reviews() -> anyhow::Result<()> {
        let dir = tempdir()?;
        let session_dir = dir.path().join("session");
        let session = SessionFile {
            schema_version: SESSION_SCHEMA_VERSION.to_string(),
            session_date: "2026-01-11".to_string(),
            repo_root: dir.path().to_string_lossy().to_string(),
            reviewers: vec![
                "deadbeef".to_string(),
                "cafebabe".to_string(),
                "badc0ffe".to_string(),
            ],
            reviews: vec![
                ReviewEntry {
                    reviewer_id: "deadbeef".to_string(),
                    session_id: "sess0001".to_string(),
                    target_ref: "refs/heads/main".to_string(),
                    initiator_status: InitiatorStatus::Requesting,
                    status: ReviewerStatus::InProgress,
                    parent_id: None,
                    started_at: "2026-01-11T00:00:00Z".to_string(),
                    updated_at: "2026-01-11T01:00:00Z".to_string(),
                    finished_at: None,
                    current_phase: Some(ReviewPhase::Ingestion),
                    verdict: None,
                    counts: SeverityCounts::zero(),
                    report_file: None,
                    notes: Vec::new(),
                    child_reviews: vec![ChildReviewEntry {
                        reviewer_id: "badc0ffe".to_string(),
                        session_id: "sess0001".to_string(),
                        target_ref: "refs/heads/main".to_string(),
                        initiator_status: InitiatorStatus::Observing,
                        status: ReviewerStatus::Blocked,
                        parent_id: Some("deadbeef".to_string()),
                        started_at: "2026-01-11T00:00:00Z".to_string(),
                        updated_at: "2026-01-11T01:00:00Z".to_string(),
                        finished_at: None,
                        current_phase: Some(ReviewPhase::Synthesis),
                        verdict: None,
                        counts: SeverityCounts::zero(),
                        report_file: None,
                        notes_count: 0,
                    }],
                    extra: serde_json::Map::default(),
                },
                ReviewEntry {
                    reviewer_id: "cafebabe".to_string(),
                    session_id: "sess0001".to_string(),
                    target_ref: "refs/heads/main".to_string(),
                    initiator_status: InitiatorStatus::Requesting,
                    status: ReviewerStatus::InProgress,
                    parent_id: Some("deadbeef".to_string()),
                    started_at: "2026-01-11T00:00:00Z".to_string(),
                    updated_at: "2026-01-11T01:00:00Z".to_string(),
                    finished_at: None,
                    current_phase: Some(ReviewPhase::DomainCoverage),
                    verdict: None,
                    counts: SeverityCounts::zero(),
                    report_file: None,
                    notes: vec![SessionNote {
                        role: NoteRole::Reviewer,
                        timestamp: "2026-01-11T01:30:00Z".to_string(),
                        note_type: NoteType::DomainObservation,
                        content: Value::String("domain coverage".to_string()),
                    }],
                    child_reviews: Vec::new(),
                    extra: serde_json::Map::default(),
                },
            ],
            extra: serde_json::Map::new(),
        };

        write_session_file_atomic(&session_dir, "deadbeef", &session)?;
        let parsed = read_session_file(&session_dir)?;
        let parent = parsed
            .reviews
            .iter()
            .find(|review| review.reviewer_id == "deadbeef")
            .ok_or_else(|| anyhow::anyhow!("parent missing"))?;
        ensure!(parent.child_reviews.len() == 1);
        let child = parent
            .child_reviews
            .first()
            .ok_or_else(|| anyhow::anyhow!("child missing"))?;
        ensure!(child.reviewer_id == "cafebabe");
        ensure!(child.status == ReviewerStatus::InProgress);
        ensure!(child.current_phase == Some(ReviewPhase::DomainCoverage));
        ensure!(child.notes_count == 1);
        Ok(())
    }

    #[test]
    fn update_parent_rebuilds_embedded_child_reviews() -> anyhow::Result<()> {
        let dir = tempdir()?;
        let session_dir = dir.path().join("session");
        let session = SessionFile {
            schema_version: SESSION_SCHEMA_VERSION.to_string(),
            session_date: "2026-01-11".to_string(),
            repo_root: dir.path().to_string_lossy().to_string(),
            reviewers: vec!["deadbeef".to_string(), "cafebabe".to_string()],
            reviews: vec![
                ReviewEntry {
                    reviewer_id: "deadbeef".to_string(),
                    session_id: "sess0001".to_string(),
                    target_ref: "refs/heads/main".to_string(),
                    initiator_status: InitiatorStatus::Requesting,
                    status: ReviewerStatus::InProgress,
                    parent_id: None,
                    started_at: "2026-01-11T00:00:00Z".to_string(),
                    updated_at: "2026-01-11T01:00:00Z".to_string(),
                    finished_at: None,
                    current_phase: Some(ReviewPhase::Ingestion),
                    verdict: None,
                    counts: SeverityCounts::zero(),
                    report_file: None,
                    notes: Vec::new(),
                    child_reviews: Vec::new(),
                    extra: serde_json::Map::default(),
                },
                ReviewEntry {
                    reviewer_id: "cafebabe".to_string(),
                    session_id: "sess0001".to_string(),
                    target_ref: "refs/heads/main".to_string(),
                    initiator_status: InitiatorStatus::Requesting,
                    status: ReviewerStatus::Initializing,
                    parent_id: Some("deadbeef".to_string()),
                    started_at: "2026-01-11T00:00:00Z".to_string(),
                    updated_at: "2026-01-11T01:00:00Z".to_string(),
                    finished_at: None,
                    current_phase: None,
                    verdict: None,
                    counts: SeverityCounts::zero(),
                    report_file: None,
                    notes: Vec::new(),
                    child_reviews: Vec::new(),
                    extra: serde_json::Map::default(),
                },
            ],
            extra: serde_json::Map::new(),
        };
        write_session(&session_dir, &session)?;

        let params = UpdateReviewParams {
            session: SessionLocator::new(session_dir.clone()),
            reviewer_id: "deadbeef".to_string(),
            session_id: "sess0001".to_string(),
            status: Some(ReviewerStatus::Blocked),
            phase: None,
            now: OffsetDateTime::now_utc(),
        };
        update_review(&params)?;

        let parsed = read_session_file(&session_dir)?;
        let parent = parsed
            .reviews
            .iter()
            .find(|review| review.reviewer_id == "deadbeef")
            .ok_or_else(|| anyhow::anyhow!("parent missing"))?;
        ensure!(parent.status == ReviewerStatus::Blocked);
        ensure!(parent.child_reviews.len() == 1);
        let child = parent
            .child_reviews
            .first()
            .ok_or_else(|| anyhow::anyhow!("child missing"))?;
        ensure!(child.reviewer_id == "cafebabe");
        ensure!(child.status == ReviewerStatus::Initializing);
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
            schema_version: SESSION_SCHEMA_VERSION.to_string(),
            session_date: "2026-01-11".to_string(),
            repo_root: dir.path().to_string_lossy().to_string(),
            reviewers: Vec::new(),
            reviews: Vec::new(),
            extra: serde_json::Map::new(),
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
    fn update_review_rejects_finished_without_report_artifacts() -> anyhow::Result<()> {
        let dir = tempdir()?;
        let session_dir = dir.path().join("session");
        let entry = ReviewEntry {
            reviewer_id: "deadbeef".to_string(),
            session_id: "sess0001".to_string(),
            target_ref: "refs/heads/main".to_string(),
            initiator_status: InitiatorStatus::Requesting,
            status: ReviewerStatus::InProgress,
            parent_id: None,
            started_at: "2026-01-11T00:00:00Z".to_string(),
            updated_at: "2026-01-11T01:00:00Z".to_string(),
            finished_at: None,
            current_phase: Some(ReviewPhase::Synthesis),
            verdict: None,
            counts: SeverityCounts::zero(),
            report_file: None,
            notes: Vec::new(),
            child_reviews: Vec::new(),
            extra: serde_json::Map::default(),
        };
        let session = SessionFile {
            schema_version: SESSION_SCHEMA_VERSION.to_string(),
            session_date: "2026-01-11".to_string(),
            repo_root: dir.path().to_string_lossy().to_string(),
            reviewers: vec!["deadbeef".to_string()],
            reviews: vec![entry],
            extra: serde_json::Map::new(),
        };
        write_session(&session_dir, &session)?;

        let params = UpdateReviewParams {
            session: SessionLocator::new(session_dir),
            reviewer_id: "deadbeef".to_string(),
            session_id: "sess0001".to_string(),
            status: Some(ReviewerStatus::Finished),
            phase: None,
            now: OffsetDateTime::now_utc(),
        };
        let Err(err) = update_review(&params) else {
            bail!("finished without report artifacts should fail");
        };
        ensure!(err
            .to_string()
            .contains("FINISHED but report_file is missing"));
        Ok(())
    }

    #[test]
    fn update_review_rejects_terminal_status_change() -> anyhow::Result<()> {
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
            finished_at: Some("2026-01-11T01:30:00Z".to_string()),
            current_phase: Some(ReviewPhase::ReportWriting),
            verdict: Some(ReviewVerdict::Approve),
            counts: SeverityCounts::zero(),
            report_file: Some("report.md".to_string()),
            notes: Vec::new(),
            child_reviews: Vec::new(),
            extra: serde_json::Map::default(),
        };
        let session = SessionFile {
            schema_version: SESSION_SCHEMA_VERSION.to_string(),
            session_date: "2026-01-11".to_string(),
            repo_root: dir.path().to_string_lossy().to_string(),
            reviewers: vec!["deadbeef".to_string()],
            reviews: vec![entry],
            extra: serde_json::Map::new(),
        };
        write_session(&session_dir, &session)?;

        let params = UpdateReviewParams {
            session: SessionLocator::new(session_dir.clone()),
            reviewer_id: "deadbeef".to_string(),
            session_id: "sess0001".to_string(),
            status: Some(ReviewerStatus::Cancelled),
            phase: None,
            now: OffsetDateTime::now_utc(),
        };
        let Err(err) = update_review(&params) else {
            bail!("terminal-to-terminal mutation should fail");
        };
        ensure!(err
            .to_string()
            .contains("cannot change terminal review status"));

        let parsed = read_session_file(&session_dir)?;
        let persisted = parsed
            .reviews
            .iter()
            .find(|r| r.reviewer_id == "deadbeef" && r.session_id == "sess0001")
            .ok_or_else(|| anyhow::anyhow!("review entry missing after failed update"))?;
        ensure!(persisted.status == ReviewerStatus::Finished);
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
            child_reviews: Vec::new(),
            extra: serde_json::Map::default(),
        };
        let session = SessionFile {
            schema_version: SESSION_SCHEMA_VERSION.to_string(),
            session_date: "2026-01-11".to_string(),
            repo_root: dir.path().to_string_lossy().to_string(),
            reviewers: vec!["deadbeef".to_string()],
            reviews: vec![entry],
            extra: serde_json::Map::new(),
        };
        write_session(&session_dir, &session)?;

        let params = FinalizeReviewParams {
            session: SessionLocator::new(session_dir),
            reviewer_id: "deadbeef".to_string(),
            session_id: "sess0001".to_string(),
            verdict: ReviewVerdict::Approve,
            counts: SeverityCounts::zero(),
            report_input: FinalizeReportInput::Markdown("report\n".to_string()),
            copy_input_report: false,
            auto_close_open_children: true,
            auto_close_children_status: ReviewerStatus::Cancelled,
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
            child_reviews: Vec::new(),
            extra: serde_json::Map::default(),
        };
        let session = SessionFile {
            schema_version: SESSION_SCHEMA_VERSION.to_string(),
            session_date: "2026-01-11".to_string(),
            repo_root: dir.path().to_string_lossy().to_string(),
            reviewers: vec!["deadbeef".to_string()],
            reviews: vec![entry],
            extra: serde_json::Map::new(),
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

    #[test]
    fn infer_repo_root_from_session_dir_extracts_default_layout_root() -> anyhow::Result<()> {
        let dir = tempdir()?;
        let repo_root = dir.path().join("repo");
        let session_dir = repo_root
            .join(".local")
            .join("reports")
            .join("code_reviews")
            .join("2026-01-11");
        fs::create_dir_all(&session_dir)?;
        let actual = infer_repo_root_from_session_dir(&session_dir)
            .ok_or_else(|| anyhow::anyhow!("failed to infer repo root"))?;
        ensure!(actual == repo_root);
        Ok(())
    }

    #[test]
    fn infer_repo_root_from_session_dir_returns_none_for_non_default_layout() -> anyhow::Result<()>
    {
        let dir = tempdir()?;
        let session_dir = dir.path().join("session");
        fs::create_dir_all(&session_dir)?;
        ensure!(infer_repo_root_from_session_dir(&session_dir).is_none());
        Ok(())
    }

    #[test]
    fn write_session_file_atomic_preserves_review_unknown_fields() -> anyhow::Result<()> {
        let dir = tempdir()?;
        let session_dir = dir.path().join("session");
        fs::create_dir_all(&session_dir)?;

        let raw_session = serde_json::json!({
            "schema_version": SESSION_SCHEMA_VERSION,
            "session_date": "2026-01-11",
            "repo_root": dir.path().to_string_lossy(),
            "reviewers": ["deadbeef"],
            "reviews": [{
                "reviewer_id": "deadbeef",
                "session_id": "sess0001",
                "target_ref": "refs/heads/main",
                "initiator_status": "REQUESTING",
                "status": "IN_PROGRESS",
                "parent_id": null,
                "started_at": "2026-01-11T00:00:00Z",
                "updated_at": "2026-01-11T01:00:00Z",
                "finished_at": null,
                "current_phase": "INGESTION",
                "verdict": null,
                "counts": {"blocker":0,"major":0,"minor":0,"nit":0},
                "report_file": null,
                "notes": [],
                "future_extension": {"token": "abc123"}
            }]
        });
        fs::write(
            session_dir.join("_session.json"),
            format!("{}\n", serde_json::to_string_pretty(&raw_session)?),
        )?;

        let session = read_session_file(&session_dir)?;
        write_session_file_atomic(&session_dir, "deadbeef", &session)?;

        let written: Value =
            serde_json::from_str(&fs::read_to_string(session_dir.join("_session.json"))?)?;
        let reviews = written
            .get("reviews")
            .and_then(Value::as_array)
            .ok_or_else(|| anyhow::anyhow!("missing reviews"))?;
        let future_extension = reviews
            .first()
            .and_then(|review| review.get("future_extension"))
            .ok_or_else(|| anyhow::anyhow!("missing review future_extension"))?;
        ensure!(future_extension["token"] == "abc123");
        Ok(())
    }

    #[test]
    fn resolve_report_rejects_parent_dir_components() -> anyhow::Result<()> {
        let repo = Path::new("/repo");
        let sess = Path::new("/repo/.sessions/s1");
        let err = match resolve_report_file_path(repo, sess, "../../../etc/passwd") {
            Ok(path) => bail!(
                "should reject path with '..' components, got {}",
                path.display()
            ),
            Err(err) => err,
        };
        let msg = err.to_string();
        ensure!(
            msg.contains(".."),
            "error should mention '..' components: {msg}"
        );
        Ok(())
    }

    #[test]
    fn resolve_report_rejects_hidden_parent_dir() -> anyhow::Result<()> {
        let repo = Path::new("/repo");
        let sess = Path::new("/repo/.sessions/s1");
        let err = match resolve_report_file_path(repo, sess, "subdir/../../escape.md") {
            Ok(path) => bail!(
                "should reject path with embedded '..' component, got {}",
                path.display()
            ),
            Err(err) => err,
        };
        let msg = err.to_string();
        ensure!(
            msg.contains(".."),
            "error should mention '..' components: {msg}"
        );
        Ok(())
    }

    #[test]
    fn resolve_report_allows_valid_repo_relative_path() -> anyhow::Result<()> {
        let repo = Path::new("/repo");
        let sess = Path::new("/repo/.sessions/s1");
        let result = resolve_report_file_path(repo, sess, ".local/reports/review.md")?;
        ensure!(result == PathBuf::from("/repo/.local/reports/review.md"));
        Ok(())
    }

    #[test]
    fn resolve_report_allows_simple_filename() -> anyhow::Result<()> {
        let repo = Path::new("/repo");
        let sess = Path::new("/repo/.sessions/s1");
        let result = resolve_report_file_path(repo, sess, "report.md")?;
        ensure!(result == PathBuf::from("/repo/.sessions/s1/report.md"));
        Ok(())
    }

    #[test]
    fn resolve_report_allows_absolute_path_under_repo_root() -> anyhow::Result<()> {
        let repo = Path::new("/repo");
        let sess = Path::new("/repo/.sessions/s1");
        let result = resolve_report_file_path(repo, sess, "/repo/reports/review.md")?;
        ensure!(result == PathBuf::from("/repo/reports/review.md"));
        Ok(())
    }

    #[test]
    fn resolve_report_rejects_absolute_path_outside_repo_root() {
        let repo = Path::new("/repo");
        let sess = Path::new("/repo/.sessions/s1");
        let result = resolve_report_file_path(repo, sess, "/tmp/report.md");
        assert!(
            result.is_err(),
            "absolute path outside repo root should be rejected"
        );
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
    /// Optional parent reviewer id (id8) for handoff/chaining.
    pub parent_id: Option<String>,
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
        if parent_id == &reviewer_id {
            return Err(anyhow::anyhow!("parent_id must not equal reviewer_id"));
        }
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
            schema_version: SESSION_SCHEMA_VERSION.to_string(),
            session_date: params.session_date.to_string(),
            repo_root: repo_root.to_string_lossy().to_string(),
            reviewers: vec![],
            reviews: vec![],
            extra: serde_json::Map::new(),
        }
    };

    let session_id_was_explicit = params.session_id.is_some();

    let session_id = match params.session_id {
        Some(session_id) => {
            validate_id8(&session_id, "session_id")?;
            session_id
        }
        None => {
            if let Some(ref parent_id) = params.parent_id {
                // Preserve idempotency for child reviewer registration: if this reviewer already has
                // an entry for this (target_ref, parent_id), reuse its session_id before inferring
                // from parent entries.
                let mut existing_child_session_ids: Vec<&str> = Vec::new();
                for entry in &session.reviews {
                    if entry.reviewer_id == reviewer_id
                        && entry.target_ref == params.target_ref
                        && entry.parent_id.as_deref() == Some(parent_id.as_str())
                    {
                        existing_child_session_ids.push(entry.session_id.as_str());
                    }
                }
                existing_child_session_ids.sort_unstable();
                existing_child_session_ids.dedup();
                if existing_child_session_ids.len() == 1 {
                    let Some(&session_id) = existing_child_session_ids.first() else {
                        return Err(anyhow::anyhow!(
                            "internal error: child session_id set unexpectedly empty"
                        ));
                    };
                    session_id.to_string()
                } else {
                    if !existing_child_session_ids.is_empty() {
                        let available = existing_child_session_ids.join(", ");
                        return Err(anyhow::anyhow!(
                            "review entry is ambiguous for reviewer_id/parent_id/target_ref; pass --session-id (available session_ids: {available})"
                        ));
                    }

                    let mut parent_session_ids: Vec<&str> = Vec::new();
                    for entry in &session.reviews {
                        if entry.reviewer_id == parent_id.as_str()
                            && entry.target_ref == params.target_ref
                        {
                            parent_session_ids.push(entry.session_id.as_str());
                        }
                    }
                    parent_session_ids.sort_unstable();
                    parent_session_ids.dedup();

                    match parent_session_ids.len() {
                        0 => {
                            return Err(anyhow::anyhow!(
                                "parent review entry not found for parent_id/target_ref (run `mpcr reviewer register` for the parent first)"
                            ));
                        }
                        1 => {
                            let Some(&session_id) = parent_session_ids.first() else {
                                return Err(anyhow::anyhow!(
                                    "internal error: parent session_id set unexpectedly empty"
                                ));
                            };
                            session_id.to_string()
                        }
                        _ => {
                            let available = parent_session_ids.join(", ");
                            return Err(anyhow::anyhow!(
                                "parent review entry is ambiguous for parent_id/target_ref; pass --session-id (available session_ids: {available})"
                            ));
                        }
                    }
                }
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
            }
        }
    };

    if let Some(ref parent_id) = params.parent_id {
        let parent_exists = session.reviews.iter().any(|r| {
            r.reviewer_id == parent_id.as_str()
                && r.session_id == session_id
                && r.target_ref == params.target_ref
        });
        if !parent_exists {
            return Err(anyhow::anyhow!(
                "parent review entry not found for parent_id/session_id/target_ref (run `mpcr reviewer register` for the parent first)"
            ));
        }
    }

    if let Some(existing_index) = session
        .reviews
        .iter()
        .position(|r| r.reviewer_id == reviewer_id && r.session_id == session_id)
    {
        let mut should_sync_parent = false;
        let existing = session
            .reviews
            .get_mut(existing_index)
            .ok_or_else(|| anyhow::anyhow!("review entry index invalid"))?;
        let mut changed = false;

        if existing.target_ref != params.target_ref {
            return Err(anyhow::anyhow!(
                "review entry already exists for reviewer_id/session_id but target_ref differs"
            ));
        }

        if let Some(ref requested_parent_id) = params.parent_id {
            match existing.parent_id.as_deref() {
                None => {
                    existing.parent_id = Some(requested_parent_id.clone());
                    existing.updated_at = format_ts(params.now)?;
                    changed = true;
                    should_sync_parent = true;
                }
                Some(existing_parent_id) if existing_parent_id == requested_parent_id.as_str() => {}
                Some(_) => {
                    return Err(anyhow::anyhow!(
                        "review entry already exists for reviewer_id/session_id but parent_id differs"
                    ));
                }
            }
        }

        let parent_id_for_result = existing.parent_id.clone();

        if !session.reviewers.iter().any(|r| r == &reviewer_id) {
            session.reviewers.push(reviewer_id.clone());
            changed = true;
        }
        if should_sync_parent {
            sync_child_review_to_parent(&mut session, &reviewer_id, &session_id)?;
            changed = true;
        }
        if changed {
            write_session_file_atomic(params.session.session_dir(), &reviewer_id, &session)?;
        }

        return Ok(RegisterReviewerResult {
            reviewer_id,
            parent_id: parent_id_for_result,
            session_id,
            session_dir: params.session.session_dir().to_string_lossy().to_string(),
            session_file: params.session.session_file().to_string_lossy().to_string(),
        });
    }

    if session_id_was_explicit {
        if let Some(existing_target_ref) = session.reviews.iter().find_map(|r| {
            (r.session_id == session_id && r.target_ref != params.target_ref)
                .then_some(r.target_ref.as_str())
        }) {
            return Err(anyhow::anyhow!(
                "session_id already exists for a different target_ref (existing={existing_target_ref}, requested={})",
                params.target_ref
            ));
        }
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
    let parent_id_for_result = params.parent_id.clone();

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
        child_reviews: vec![],
        extra: serde_json::Map::default(),
    });

    if parent_id_for_result.is_some() {
        sync_child_review_to_parent(&mut session, &reviewer_id, &session_id)?;
    }

    write_session_file_atomic(params.session.session_dir(), &reviewer_id, &session)?;

    Ok(RegisterReviewerResult {
        reviewer_id,
        parent_id: parent_id_for_result,
        session_id,
        session_dir: params.session.session_dir().to_string_lossy().to_string(),
        session_file: params.session.session_file().to_string_lossy().to_string(),
    })
}

#[derive(Debug, Clone)]
/// Parameters for [`spawn_child_reviewers`].
pub struct SpawnChildReviewersParams {
    /// Session directory locator.
    pub session: SessionLocator,
    /// Target ref under review (branch/PR/commit/etc).
    pub target_ref: String,
    /// Session id (id8) that children join.
    pub session_id: String,
    /// Parent reviewer id (id8) recorded into each child entry.
    pub parent_reviewer_id: String,
    /// Number of child reviewer entries to create.
    pub count: usize,
    /// Timestamp used for `started_at` / `updated_at`.
    pub now: OffsetDateTime,
}

const MAX_SPAWN_CHILDREN: usize = 32;

#[derive(Debug, Clone, Serialize)]
#[serde(deny_unknown_fields)]
/// A child reviewer entry spawned by [`spawn_child_reviewers`].
pub struct SpawnedChildReviewer {
    /// The child's reviewer id (id8).
    pub reviewer_id: String,
    /// The parent reviewer id (id8) recorded on this entry.
    pub parent_id: String,
}

#[derive(Debug, Clone, Serialize)]
#[serde(deny_unknown_fields)]
/// Result returned by [`spawn_child_reviewers`].
pub struct SpawnChildReviewersResult {
    /// The parent reviewer id used for all spawned children (id8).
    pub parent_id: String,
    /// The session id used for all spawned children (id8).
    pub session_id: String,
    /// The target ref used for all spawned children.
    pub target_ref: String,
    /// Session directory as a string.
    pub session_dir: String,
    /// Session file path as a string.
    pub session_file: String,
    /// Spawned child reviewer identifiers.
    pub children: Vec<SpawnedChildReviewer>,
}

/// Spawn child reviewer entries under a single parent reviewer id.
///
/// This is intended for deterministic multi-agent orchestration:
/// an orchestrator registers first, then spawns child reviewer entries that:
/// - join the same `session_id` and `target_ref`
/// - record `parent_id` for lineage
/// - start in `INITIALIZING` so each child can transition independently
///
/// # Errors
/// Returns an error if the parent entry cannot be found, identifiers are invalid,
/// the session cannot be read or written, or the lock cannot be acquired.
pub fn spawn_child_reviewers(
    params: SpawnChildReviewersParams,
) -> anyhow::Result<SpawnChildReviewersResult> {
    validate_id8(&params.session_id, "session_id")?;
    validate_id8(&params.parent_reviewer_id, "parent_reviewer_id")?;
    if params.count == 0 {
        return Err(anyhow::anyhow!("count must be >= 1"));
    }
    if params.count > MAX_SPAWN_CHILDREN {
        return Err(anyhow::anyhow!("count must be <= {MAX_SPAWN_CHILDREN}"));
    }

    let session_file = params.session.session_file();
    if !session_file.exists() {
        return Err(anyhow::anyhow!(
            "session file not found: {} (run `mpcr reviewer register` first)",
            session_file.display()
        ));
    }

    let lock_owner = params.parent_reviewer_id.clone();
    let _guard = lock::acquire_lock(
        params.session.session_dir(),
        lock_owner.clone(),
        LockConfig::default(),
    )?;

    let mut session = read_session_file(params.session.session_dir())?;

    let parent_entry = session.reviews.iter().find(|r| {
        let reviewer_matches = r.reviewer_id == params.parent_reviewer_id;
        let session_matches = r.session_id == params.session_id;
        let target_matches = r.target_ref == params.target_ref;
        reviewer_matches && session_matches && target_matches
    });
    let Some(parent_entry) = parent_entry else {
        return Err(anyhow::anyhow!(
            "parent review entry not found for reviewer_id/session_id/target_ref (run `mpcr reviewer register` for the parent first)"
        ));
    };
    if parent_entry.status.is_terminal() {
        return Err(anyhow::anyhow!(
            "parent review {} is already terminal ({:?}) and cannot spawn new children",
            params.parent_reviewer_id,
            parent_entry.status,
        ));
    }
    // Children always start with REQUESTING regardless of parent's initiator_status.
    // This ensures children are discoverable/actionable by applicators.
    let initiator_status = InitiatorStatus::Requesting;

    if !session
        .reviewers
        .iter()
        .any(|r| r == params.parent_reviewer_id.as_str())
    {
        session.reviewers.push(params.parent_reviewer_id.clone());
    }

    let mut used_ids: HashSet<String> = session.reviewers.iter().cloned().collect();
    for entry in &session.reviews {
        used_ids.insert(entry.reviewer_id.clone());
    }

    let started_at = format_ts(params.now)?;

    let mut children_ids = Vec::with_capacity(params.count);
    while children_ids.len() < params.count {
        let candidate = id::random_id8()?;
        if used_ids.insert(candidate.clone()) {
            children_ids.push(candidate);
        }
    }

    let mut children = Vec::with_capacity(params.count);
    let mut child_refs = Vec::with_capacity(params.count);
    for reviewer_id in children_ids {
        session.reviewers.push(reviewer_id.clone());
        session.reviews.push(ReviewEntry {
            reviewer_id: reviewer_id.clone(),
            session_id: params.session_id.clone(),
            target_ref: params.target_ref.clone(),
            initiator_status,
            status: ReviewerStatus::Initializing,
            parent_id: Some(params.parent_reviewer_id.clone()),
            started_at: started_at.clone(),
            updated_at: started_at.clone(),
            finished_at: None,
            current_phase: None,
            verdict: None,
            counts: SeverityCounts::zero(),
            report_file: None,
            notes: vec![],
            child_reviews: vec![],
            extra: serde_json::Map::default(),
        });
        child_refs.push((reviewer_id.clone(), params.session_id.clone()));
        children.push(SpawnedChildReviewer {
            reviewer_id,
            parent_id: params.parent_reviewer_id.clone(),
        });
    }

    for (reviewer_id, session_id) in child_refs {
        sync_child_review_to_parent(&mut session, &reviewer_id, &session_id)?;
    }

    write_session_file_atomic(params.session.session_dir(), &lock_owner, &session)?;

    Ok(SpawnChildReviewersResult {
        parent_id: params.parent_reviewer_id,
        session_id: params.session_id,
        target_ref: params.target_ref,
        session_dir: params.session.session_dir().to_string_lossy().to_string(),
        session_file: params.session.session_file().to_string_lossy().to_string(),
        children,
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

    if entry.status.is_terminal() {
        if let Some(new_status) = params.status {
            if new_status != entry.status {
                anyhow::bail!(
                    "cannot change terminal review status {:?} to {:?}",
                    entry.status,
                    new_status
                );
            }
        }
    }

    if let Some(status) = params.status {
        entry.status = status;
    }
    if let Some(phase) = params.phase {
        entry.current_phase = phase;
    }
    entry.updated_at = format_ts(params.now)?;

    sync_child_review_to_parent(&mut session, &params.reviewer_id, &params.session_id)?;

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
/// Report source passed to [`finalize_review`].
pub enum FinalizeReportInput {
    /// Read report markdown from in-memory content (stdin path in CLI).
    Markdown(String),
    /// Move/copy report markdown from an existing file path.
    File(PathBuf),
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
    /// Report input source for finalization.
    pub report_input: FinalizeReportInput,
    /// Preserve the input report file when `report_input` is [`FinalizeReportInput::File`].
    pub copy_input_report: bool,
    /// Auto-close unresolved child reviews under this reviewer before finalizing.
    pub auto_close_open_children: bool,
    /// Status used when auto-closing unresolved children.
    pub auto_close_children_status: ReviewerStatus,
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

fn write_markdown_report_file(
    report_path: &Path,
    mut report_markdown: String,
) -> anyhow::Result<()> {
    if !report_markdown.ends_with('\n') {
        report_markdown.push('\n');
    }
    let mut f = std::fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(report_path)
        .with_context(|| format!("create report file {}", report_path.display()))?;
    f.write_all(report_markdown.as_bytes())
        .with_context(|| format!("write report file {}", report_path.display()))?;
    f.flush()
        .with_context(|| format!("flush report file {}", report_path.display()))?;
    Ok(())
}

fn same_file_path(a: &Path, b: &Path) -> bool {
    if a == b {
        return true;
    }
    let a_can = a.canonicalize().ok();
    let b_can = b.canonicalize().ok();
    matches!((a_can, b_can), (Some(a_can), Some(b_can)) if a_can == b_can)
}

fn copy_file(src: &Path, dst: &Path) -> anyhow::Result<()> {
    fs::copy(src, dst).with_context(|| {
        format!(
            "copy report input from {} to {}",
            src.display(),
            dst.display()
        )
    })?;
    Ok(())
}

fn move_file(src: &Path, dst: &Path) -> anyhow::Result<()> {
    match fs::rename(src, dst) {
        Ok(()) => Ok(()),
        Err(err) if err.kind() == ErrorKind::CrossesDevices => {
            copy_file(src, dst)?;
            fs::remove_file(src)
                .with_context(|| format!("remove moved report input {}", src.display()))?;
            Ok(())
        }
        Err(err) => Err(err).with_context(|| {
            format!(
                "move report input from {} to {}",
                src.display(),
                dst.display()
            )
        }),
    }
}

fn validate_auto_close_status(status: ReviewerStatus) -> anyhow::Result<()> {
    match status {
        ReviewerStatus::Cancelled | ReviewerStatus::Error => Ok(()),
        _ => Err(anyhow::anyhow!(
            "auto-close child status must be CANCELLED or ERROR"
        )),
    }
}

/// Finalize a review entry: write the report file and update `_session.json`.
///
/// The entire operation is performed under a single session lock to prevent
/// concurrent mutations between read, report write, and session update.
///
/// # Errors
/// Returns an error if identifiers are invalid, report files cannot be written,
/// or the session cannot be read or written.
#[allow(clippy::too_many_lines)] // Reason: finalize coordinates lock/read/write and child lifecycle in one transactional flow.
pub fn finalize_review(params: FinalizeReviewParams) -> anyhow::Result<FinalizeReviewResult> {
    validate_id8(&params.reviewer_id, "reviewer_id")?;
    validate_id8(&params.session_id, "session_id")?;
    validate_auto_close_status(params.auto_close_children_status)?;

    // Hold a single lock across read, report write, and session update to
    // prevent concurrent mutations between steps.
    let lock_owner = params.reviewer_id.clone();
    let _guard = lock::acquire_lock(
        params.session.session_dir(),
        lock_owner,
        LockConfig::default(),
    )?;

    // Step 1: read the session file and compute the report filename.
    let mut session = read_session_file(params.session.session_dir())?;
    let repo_root = PathBuf::from(&session.repo_root);
    {
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
    }
    let open_child_ids: Vec<String> = session
        .reviews
        .iter()
        .filter(|child| {
            child.parent_id.as_deref() == Some(params.reviewer_id.as_str())
                && child.session_id == params.session_id
                && !child.status.is_terminal()
        })
        .map(|child| child.reviewer_id.clone())
        .collect();
    if !open_child_ids.is_empty() && !params.auto_close_open_children {
        let list = open_child_ids.join(",");
        return Err(anyhow::anyhow!(
            "cannot finalize while child reviews are open (run `mpcr reviewer close-children` first): {list}"
        ));
    }
    let (started_at, target_ref) = {
        let entry = session
            .reviews
            .iter()
            .find(|r| r.reviewer_id == params.reviewer_id && r.session_id == params.session_id)
            .ok_or_else(|| anyhow::anyhow!("review entry not found for reviewer_id/session_id"))?;
        (parse_ts(&entry.started_at)?, entry.target_ref.clone())
    };

    let filename = report_file_name(started_at, &target_ref, &params.reviewer_id)?;
    let report_path = params.session.session_dir().join(&filename);

    // Step 2: write/move report file (still under the lock).
    match params.report_input {
        FinalizeReportInput::Markdown(report_markdown) => {
            write_markdown_report_file(&report_path, report_markdown)?;
        }
        FinalizeReportInput::File(source_path) => {
            if !source_path.exists() {
                return Err(anyhow::anyhow!(
                    "report input file does not exist: {}",
                    source_path.display()
                ));
            }

            if same_file_path(&source_path, &report_path) {
                if !report_path.exists() {
                    return Err(anyhow::anyhow!(
                        "report input file does not exist: {}",
                        source_path.display()
                    ));
                }
            } else {
                if report_path.exists() {
                    return Err(anyhow::anyhow!(
                        "report file already exists at destination: {}",
                        report_path.display()
                    ));
                }
                if params.copy_input_report {
                    copy_file(&source_path, &report_path)?;
                } else {
                    move_file(&source_path, &report_path)?;
                }
            }
        }
    }

    let report_file = strip_repo_root_best_effort(&repo_root, &report_path)
        .map_or(filename, |rel| rel.to_string_lossy().to_string());

    // Step 3: update session entry (still under the same lock).
    if !open_child_ids.is_empty() {
        let updated_at = format_ts(params.now)?;
        let note_timestamp = updated_at.clone();
        let note_content = Value::String(format!(
            "auto-closed by parent finalize reviewer_id={} session_id={}",
            params.reviewer_id, params.session_id
        ));
        for entry in &mut session.reviews {
            if entry.parent_id.as_deref() != Some(params.reviewer_id.as_str()) {
                continue;
            }
            if entry.session_id != params.session_id || entry.target_ref != target_ref {
                continue;
            }
            if entry.status.is_terminal() {
                continue;
            }

            entry.status = params.auto_close_children_status;
            entry.current_phase = None;
            entry.updated_at.clone_from(&updated_at);
            entry.notes.push(SessionNote {
                role: NoteRole::Reviewer,
                timestamp: note_timestamp.clone(),
                note_type: NoteType::AutoClosedByParentFinalize,
                content: note_content.clone(),
            });
        }
        for reviewer_id in &open_child_ids {
            sync_child_review_to_parent(&mut session, reviewer_id, &params.session_id)?;
        }
    }

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

    sync_child_review_to_parent(&mut session, &params.reviewer_id, &params.session_id)?;

    write_session_file_atomic(params.session.session_dir(), &params.reviewer_id, &session)?;

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
    if !params.note_type.allowed_for_role(params.role) {
        let note_type_name = serde_json::to_string(&params.note_type).map_or_else(
            |_| "unknown".to_string(),
            |raw| raw.trim_matches('"').to_string(),
        );
        return Err(anyhow::anyhow!(
            "note_type `{}` is not allowed for role `{}`",
            note_type_name,
            match params.role {
                NoteRole::Reviewer => "reviewer",
                NoteRole::Applicator => "applicator",
            }
        ));
    }

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

    sync_child_review_to_parent(&mut session, &params.reviewer_id, &params.session_id)?;

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

    sync_child_review_to_parent(&mut session, &params.reviewer_id, &params.session_id)?;

    write_session_file_atomic(params.session.session_dir(), &lock_owner, &session)?;
    Ok(())
}

#[derive(Debug, Clone)]
/// Parameters for [`close_child_reviews`].
pub struct CloseChildReviewsParams {
    /// Session directory locator.
    pub session: SessionLocator,
    /// Parent reviewer id (id8) whose child entries should be updated.
    pub parent_reviewer_id: String,
    /// Session id (id8) that children must belong to.
    pub session_id: String,
    /// Optional target ref filter.
    pub target_ref: Option<String>,
    /// Child statuses eligible for update.
    pub only_statuses: Vec<ReviewerStatus>,
    /// Reviewer-owned status to set on matching children.
    pub set_status: ReviewerStatus,
    /// Clear child `current_phase` when true.
    pub clear_phase: bool,
    /// Timestamp written to `updated_at`.
    pub now: OffsetDateTime,
}

#[derive(Debug, Clone, Serialize)]
#[serde(deny_unknown_fields)]
/// Child identifier emitted by [`close_child_reviews`].
pub struct ClosedChildReview {
    /// Child reviewer id.
    pub reviewer_id: String,
    /// Child session id.
    pub session_id: String,
}

#[derive(Debug, Clone, Serialize)]
#[serde(deny_unknown_fields)]
/// Result returned by [`close_child_reviews`].
pub struct CloseChildReviewsResult {
    /// Parent reviewer id used for the operation.
    pub parent_id: String,
    /// Session id used for the operation.
    pub session_id: String,
    /// Optional target ref filter used for the operation.
    pub target_ref: Option<String>,
    /// Number of child entries matching all filters.
    pub matching_children: usize,
    /// Number of child entries updated by this operation.
    pub updated_children: usize,
    /// Updated child identifiers.
    pub children: Vec<ClosedChildReview>,
}

/// Bulk-close child reviews under a parent reviewer.
///
/// # Errors
/// Returns an error if identifiers are invalid, the parent entry is missing,
/// or the session cannot be read/written.
pub fn close_child_reviews(
    params: CloseChildReviewsParams,
) -> anyhow::Result<CloseChildReviewsResult> {
    validate_id8(&params.parent_reviewer_id, "parent_reviewer_id")?;
    validate_id8(&params.session_id, "session_id")?;
    validate_auto_close_status(params.set_status)?;

    let lock_owner = params.parent_reviewer_id.clone();
    let _guard = lock::acquire_lock(
        params.session.session_dir(),
        lock_owner.clone(),
        LockConfig::default(),
    )?;
    let mut session = read_session_file(params.session.session_dir())?;

    let parent_reviewer_id = params.parent_reviewer_id.as_str();
    let session_id = params.session_id.as_str();
    let parent_exists = session.reviews.iter().any(|entry| {
        entry.reviewer_id == parent_reviewer_id
            && entry.session_id == session_id
            && params
                .target_ref
                .as_ref()
                .is_none_or(|target_ref| entry.target_ref == *target_ref)
    });
    if !parent_exists {
        return Err(anyhow::anyhow!(
            "parent review entry not found for reviewer_id/session_id/target_ref"
        ));
    }

    let updated_at = format_ts(params.now)?;
    let mut matching_children = 0usize;
    let mut updated_ids = Vec::new();

    for entry in &mut session.reviews {
        if entry.parent_id.as_deref() != Some(params.parent_reviewer_id.as_str()) {
            continue;
        }
        if entry.session_id != params.session_id {
            continue;
        }
        if let Some(target_ref) = params.target_ref.as_deref() {
            if entry.target_ref != target_ref {
                continue;
            }
        }
        if !params.only_statuses.is_empty() && !params.only_statuses.contains(&entry.status) {
            continue;
        }

        matching_children += 1;

        let changed = entry.status != params.set_status
            || (params.clear_phase && entry.current_phase.is_some());
        if !changed {
            continue;
        }

        entry.status = params.set_status;
        if params.clear_phase {
            entry.current_phase = None;
        }
        entry.updated_at.clone_from(&updated_at);
        updated_ids.push((entry.reviewer_id.clone(), entry.session_id.clone()));
    }

    let mut children = Vec::with_capacity(updated_ids.len());
    for (reviewer_id, session_id) in updated_ids {
        sync_child_review_to_parent(&mut session, &reviewer_id, &session_id)?;
        children.push(ClosedChildReview {
            reviewer_id,
            session_id,
        });
    }

    write_session_file_atomic(params.session.session_dir(), &lock_owner, &session)?;

    Ok(CloseChildReviewsResult {
        parent_id: params.parent_reviewer_id,
        session_id: params.session_id,
        target_ref: params.target_ref,
        matching_children,
        updated_children: children.len(),
        children,
    })
}
