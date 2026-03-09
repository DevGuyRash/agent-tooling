//! Canonical v2 artifact contracts, controlled vocabularies, and identity helpers.
#![allow(clippy::module_name_repetitions)]
#![allow(missing_docs)]

use anyhow::Context;
use clap::ValueEnum;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::fmt::{Display, Formatter};
use std::path::Path;
use time::format_description::well_known::Rfc3339;
use time::OffsetDateTime;

/// Canonical artifact schema version for all v2 machine artifacts.
pub const ARTIFACT_SCHEMA_VERSION: &str = "mpcr_artifact.v1";
/// Canonical session schema version for the compact v2 ledger.
pub const SESSION_SCHEMA_VERSION: &str = "mpcr_session.v2";
/// Stable policy bundle version shipped with this refactor.
pub const POLICY_BUNDLE_VERSION: &str = "2026.03.08";
/// Required error text when the CLI encounters any v1 state.
pub const LEGACY_REJECTION_MESSAGE: &str =
    "error: legacy v1 session/report/artifact is not supported in v2\nhint: start a fresh v2 session";

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize, ValueEnum)]
#[serde(rename_all = "snake_case")]
/// Canonical artifact kinds used by the v2 system.
pub enum ArtifactKind {
    RouteDecision,
    SurfaceMap,
    ChildFindings,
    ParentReview,
    ApplicationResult,
    VerificationResult,
    ConvergenceState,
    RouteRevision,
}

impl ArtifactKind {
    /// All canonical artifact kinds in stable order.
    #[must_use]
    pub const fn all() -> [Self; 8] {
        [
            Self::RouteDecision,
            Self::SurfaceMap,
            Self::ChildFindings,
            Self::ParentReview,
            Self::ApplicationResult,
            Self::VerificationResult,
            Self::ConvergenceState,
            Self::RouteRevision,
        ]
    }

    /// Directory-safe name matching the serialized form.
    #[must_use]
    pub const fn dir_name(self) -> &'static str {
        match self {
            Self::RouteDecision => "route_decision",
            Self::SurfaceMap => "surface_map",
            Self::ChildFindings => "child_findings",
            Self::ParentReview => "parent_review",
            Self::ApplicationResult => "application_result",
            Self::VerificationResult => "verification_result",
            Self::ConvergenceState => "convergence_state",
            Self::RouteRevision => "route_revision",
        }
    }

    /// Whether the canonical session layout stores rendered markdown for this kind.
    #[must_use]
    pub const fn supports_rendered_output(self) -> bool {
        matches!(
            self,
            Self::ParentReview | Self::ApplicationResult | Self::VerificationResult
        )
    }
}

impl Display for ArtifactKind {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> std::fmt::Result {
        formatter.write_str(self.dir_name())
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize, ValueEnum)]
#[serde(rename_all = "kebab-case")]
/// Review workflow modes.
pub enum Mode {
    Reviewer,
    Applicator,
    FullCycle,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize, ValueEnum)]
#[serde(rename_all = "kebab-case")]
/// Execution architecture selected by the router.
pub enum ExecutionArchitecture {
    Direct,
    Hybrid,
    Delegated,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize, ValueEnum)]
#[serde(rename_all = "snake_case")]
#[value(rename_all = "snake_case")]
/// Execution capability profile available to the workflow.
pub enum ExecutionCapability {
    SingleProcess,
    BoundedHelpers,
    ParallelSubagents,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize, ValueEnum)]
#[serde(rename_all = "snake_case")]
/// Review rigor levels.
pub enum RigorLevel {
    Lite,
    Standard,
    Forensic,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize, ValueEnum)]
#[serde(rename_all = "kebab-case")]
/// Executable worker roles.
pub enum WorkerKind {
    ReviewComposite,
    ApplyComposite,
    SurfaceMapper,
    InvariantChallenger,
    ExploitTracer,
    ContractComparer,
    CongruenceChecker,
    SimplificationChecker,
    ReleaseRiskAssessor,
    ApplicatorWorker,
    ApplicatorVerifier,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize, ValueEnum)]
#[serde(rename_all = "kebab-case")]
/// Any producer capable of emitting runtime artifacts.
pub enum ProducerKind {
    Router,
    ConvergencePlanner,
    Renderer,
    Validator,
    ReviewComposite,
    ApplyComposite,
    SurfaceMapper,
    InvariantChallenger,
    ExploitTracer,
    ContractComparer,
    CongruenceChecker,
    SimplificationChecker,
    ReleaseRiskAssessor,
    ApplicatorWorker,
    ApplicatorVerifier,
}

impl ProducerKind {
    /// Convert a worker role into the corresponding producer role.
    #[must_use]
    pub const fn from_worker(worker: WorkerKind) -> Self {
        match worker {
            WorkerKind::ReviewComposite => Self::ReviewComposite,
            WorkerKind::ApplyComposite => Self::ApplyComposite,
            WorkerKind::SurfaceMapper => Self::SurfaceMapper,
            WorkerKind::InvariantChallenger => Self::InvariantChallenger,
            WorkerKind::ExploitTracer => Self::ExploitTracer,
            WorkerKind::ContractComparer => Self::ContractComparer,
            WorkerKind::CongruenceChecker => Self::CongruenceChecker,
            WorkerKind::SimplificationChecker => Self::SimplificationChecker,
            WorkerKind::ReleaseRiskAssessor => Self::ReleaseRiskAssessor,
            WorkerKind::ApplicatorWorker => Self::ApplicatorWorker,
            WorkerKind::ApplicatorVerifier => Self::ApplicatorVerifier,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize, ValueEnum)]
#[serde(rename_all = "kebab-case")]
/// Semantic risk surfaces used by the adaptive router.
pub enum SurfaceId {
    PublicApi,
    AuthAccess,
    InputValidation,
    PrivilegeBoundary,
    Persistence,
    Migration,
    DataIntegrity,
    Concurrency,
    StateMachine,
    DocsStaleness,
    OperatorGuidance,
    ConfigSurface,
    PerformanceHotpath,
    DependencyBuild,
    TestCoverage,
    Observability,
    Privacy,
}

impl SurfaceId {
    /// Default router weight for the surface.
    #[must_use]
    pub const fn default_weight(self) -> u8 {
        match self {
            Self::PublicApi => 4,
            Self::AuthAccess => 5,
            Self::InputValidation => 4,
            Self::PrivilegeBoundary => 5,
            Self::Persistence => 4,
            Self::Migration => 5,
            Self::DataIntegrity => 5,
            Self::Concurrency => 5,
            Self::StateMachine => 4,
            Self::DocsStaleness => 2,
            Self::OperatorGuidance => 3,
            Self::ConfigSurface => 3,
            Self::PerformanceHotpath => 4,
            Self::DependencyBuild => 3,
            Self::TestCoverage => 2,
            Self::Observability => 2,
            Self::Privacy => 4,
        }
    }

    /// Stable ordering of all surfaces.
    #[must_use]
    pub const fn all() -> [Self; 17] {
        [
            Self::PublicApi,
            Self::AuthAccess,
            Self::InputValidation,
            Self::PrivilegeBoundary,
            Self::Persistence,
            Self::Migration,
            Self::DataIntegrity,
            Self::Concurrency,
            Self::StateMachine,
            Self::DocsStaleness,
            Self::OperatorGuidance,
            Self::ConfigSurface,
            Self::PerformanceHotpath,
            Self::DependencyBuild,
            Self::TestCoverage,
            Self::Observability,
            Self::Privacy,
        ]
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize, ValueEnum)]
#[serde(rename_all = "kebab-case")]
/// Concern modules the router may load.
pub enum ModuleId {
    CoreCorrectness,
    AuthAccess,
    InputValidation,
    Persistence,
    DataIntegrity,
    Concurrency,
    DocsStaleness,
    OperatorGuidance,
    Performance,
    Dependency,
    Privacy,
    Observability,
    Tests,
    ScopeCreep,
    ShipReadiness,
}

impl ModuleId {
    /// Stable ordering of all modules.
    #[must_use]
    pub const fn all() -> [Self; 15] {
        [
            Self::CoreCorrectness,
            Self::AuthAccess,
            Self::InputValidation,
            Self::Persistence,
            Self::DataIntegrity,
            Self::Concurrency,
            Self::DocsStaleness,
            Self::OperatorGuidance,
            Self::Performance,
            Self::Dependency,
            Self::Privacy,
            Self::Observability,
            Self::Tests,
            Self::ScopeCreep,
            Self::ShipReadiness,
        ]
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize, ValueEnum)]
#[serde(rename_all = "kebab-case")]
/// Escalation categories that may be held back until triggered.
pub enum EscalationId {
    SecurityEscalation,
    Reopen,
    MalformedOutput,
    ScopeCreep,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize, ValueEnum)]
#[serde(rename_all = "snake_case")]
/// Review severity labels.
pub enum Severity {
    Blocker,
    Major,
    Minor,
    Nit,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize, ValueEnum)]
#[serde(rename_all = "snake_case")]
/// Confidence labels tied to required score bands.
pub enum ConfidenceLabel {
    High,
    Medium,
    Low,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize, ValueEnum)]
#[serde(rename_all = "snake_case")]
/// Applicator dispositions for review findings.
pub enum Disposition {
    Applied,
    Declined,
    Deferred,
    AlreadyAddressed,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize, ValueEnum)]
#[serde(rename_all = "snake_case")]
/// Structured reasons for declined findings.
pub enum DeclineReasonCode {
    InvalidAnchor,
    NonReproducible,
    Duplicate,
    Hallucinated,
    OutOfScope,
    AlreadyAddressed,
    SeverityNotSupported,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize, ValueEnum)]
#[serde(rename_all = "snake_case")]
/// Structured reasons for duplicate findings.
pub enum DuplicateReasonCode {
    SameAnchorSameClaim,
    SameSurfaceSameRootCause,
    SubsumedByHigherSeverity,
    SupersededAfterFix,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize, ValueEnum)]
#[serde(rename_all = "snake_case")]
/// Convergence reopen reason codes.
pub enum ReopenReasonCode {
    BlockerRemaining,
    MajorRemaining,
    BehaviorStaleness,
    VerificationFailed,
    FixRegression,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize, ValueEnum)]
#[serde(rename_all = "snake_case")]
/// Review verdicts.
pub enum ReviewVerdict {
    Approve,
    RequestChanges,
    Block,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize, ValueEnum)]
#[serde(rename_all = "snake_case")]
/// Ship-readiness verdicts derived from the parent review.
pub enum ShipReadinessVerdict {
    Ship,
    ShipWithFixes,
    DoNotShip,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize, ValueEnum)]
#[serde(rename_all = "snake_case")]
/// Policy store categories used in `loaded_policy_refs`.
pub enum PolicyCategory {
    Mode,
    Worker,
    Module,
    Escalation,
}

impl Display for PolicyCategory {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> std::fmt::Result {
        let text = match self {
            Self::Mode => "mode",
            Self::Worker => "worker",
            Self::Module => "module",
            Self::Escalation => "escalation",
        };
        formatter.write_str(text)
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize, ValueEnum)]
#[serde(rename_all = "snake_case")]
/// Progressive-disclosure views for policy retrieval.
pub enum PolicyView {
    Brief,
    Checklist,
    Schema,
    Examples,
    Full,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize, ValueEnum)]
#[serde(rename_all = "snake_case")]
/// Applicator verification statuses.
pub enum VerificationStatus {
    Yes,
    No,
    Partial,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
/// Provenance reference to a policy pack loaded at runtime.
pub struct PolicyRef {
    pub category: PolicyCategory,
    pub id: String,
    pub version: String,
    pub view: PolicyView,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
/// Common header included in every canonical v2 artifact.
pub struct ArtifactHeader {
    pub schema_version: String,
    pub artifact_kind: ArtifactKind,
    pub artifact_id: String,
    pub session_id: String,
    pub target_ref: String,
    pub producer_kind: ProducerKind,
    pub policy_version: String,
    pub created_at: String,
    pub confidence_label: ConfidenceLabel,
    pub confidence_score: u8,
    #[serde(default)]
    pub loaded_policy_refs: Vec<PolicyRef>,
}

impl ArtifactHeader {
    /// Build a new header using the canonical defaults.
    ///
    /// # Errors
    /// Returns an error if the identifiers or timestamp are invalid.
    pub fn new(
        artifact_kind: ArtifactKind,
        artifact_id: String,
        session_id: String,
        target_ref: String,
        producer_kind: ProducerKind,
        created_at: String,
        confidence_label: ConfidenceLabel,
        confidence_score: u8,
        loaded_policy_refs: Vec<PolicyRef>,
    ) -> anyhow::Result<Self> {
        validate_artifact_id(&artifact_id)?;
        validate_session_id(&session_id)?;
        validate_created_at(&created_at)?;
        validate_confidence(confidence_label, confidence_score)?;
        Ok(Self {
            schema_version: ARTIFACT_SCHEMA_VERSION.to_string(),
            artifact_kind,
            artifact_id,
            session_id,
            target_ref,
            producer_kind,
            policy_version: POLICY_BUNDLE_VERSION.to_string(),
            created_at,
            confidence_label,
            confidence_score,
            loaded_policy_refs,
        })
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
/// Risk-surface record emitted by the router and surface mapper.
pub struct RiskSurfaceRecord {
    pub surface_id: SurfaceId,
    pub weight: u8,
    pub reason: String,
    #[serde(default)]
    pub evidence_refs: Vec<String>,
    pub behavior_facing: bool,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
/// Planned worker execution entry.
pub struct WorkerPlanRecord {
    pub worker_kind: WorkerKind,
    #[serde(default)]
    pub module_ids: Vec<ModuleId>,
    #[serde(default)]
    pub focus_surfaces: Vec<SurfaceId>,
    pub required: bool,
    pub parallelizable: bool,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
/// Canonical finding record.
pub struct FindingRecord {
    pub finding_id: String,
    pub module_id: ModuleId,
    #[serde(default)]
    pub surface_ids: Vec<SurfaceId>,
    pub severity: Severity,
    pub title: String,
    pub claim: String,
    pub scenario: String,
    pub evidence: String,
    pub recommendation: String,
    pub verification: String,
    #[serde(default)]
    pub anchors: Vec<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub symbol_hint: Option<String>,
    pub anchor_cluster: String,
    pub fingerprint: String,
    pub reopen_eligible: bool,
    pub confidence_label: ConfidenceLabel,
    pub confidence_score: u8,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
/// Defended check record capturing checks that held under challenge.
pub struct DefendedCheckRecord {
    pub check_id: String,
    pub module_id: ModuleId,
    #[serde(default)]
    pub surface_ids: Vec<SurfaceId>,
    pub method: String,
    pub claim: String,
    pub attempted_counterexample: String,
    pub evidence: String,
    #[serde(default)]
    pub anchors: Vec<String>,
    pub confidence_label: ConfidenceLabel,
    pub confidence_score: u8,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
/// Residual risk record retained after synthesis or verification.
pub struct ResidualRiskRecord {
    pub risk_id: String,
    #[serde(default)]
    pub surface_ids: Vec<SurfaceId>,
    pub summary: String,
    pub impact: String,
    pub next_action: String,
    pub reopen_eligible: bool,
    pub confidence_label: ConfidenceLabel,
    pub confidence_score: u8,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
/// Applicator disposition record.
pub struct DispositionRecord {
    pub finding_id: String,
    pub disposition: Disposition,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub decline_reason_code: Option<DeclineReasonCode>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub duplicate_reason_code: Option<DuplicateReasonCode>,
    pub detail: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub tracking_ref: Option<String>,
    pub verification_needed: bool,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
/// Verification item result.
pub struct VerificationItemRecord {
    pub finding_id: String,
    pub status: VerificationStatus,
    pub notes: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
/// Capability-profile subrecord for route decisions.
pub struct CapabilityProfile {
    pub execution_capability: ExecutionCapability,
    pub max_worker_count: u8,
    pub orchestrator_read_budget_lines: u16,
    pub orchestrator_read_budget_snippets: u16,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
/// Resource-budget subrecord for route decisions.
pub struct ResourceBudget {
    pub planned_worker_count: u8,
    pub max_worker_count: u8,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
/// Ship-readiness summary embedded in the parent review.
pub struct ShipReadinessSummary {
    pub verdict: ShipReadinessVerdict,
    #[serde(default)]
    pub axes: Vec<String>,
    #[serde(default)]
    pub blocking_items: Vec<String>,
    pub required_now_count: usize,
    pub follow_up_count: usize,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
/// Coverage summary embedded in the parent review.
pub struct CoverageSummary {
    #[serde(default)]
    pub changed_files: Vec<String>,
    #[serde(default)]
    pub surfaces_covered: Vec<SurfaceId>,
    #[serde(default)]
    pub modules_loaded: Vec<ModuleId>,
    #[serde(default)]
    pub tests_run: Vec<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub tests_not_run_reason: Option<String>,
    #[serde(default)]
    pub limitations: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
/// Reopen threshold embedded in the convergence-state artifact.
pub struct ReopenThreshold {
    pub severity_floor: Severity,
    pub behavior_staleness_reopens: bool,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
/// Reopen trigger entry used by convergence planning.
pub struct ReopenTriggerRecord {
    pub reference_id: String,
    pub reopen_reason_code: ReopenReasonCode,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
/// Next routing focus used by convergence planning.
pub struct NextRouteInputs {
    #[serde(default)]
    pub focus_files: Vec<String>,
    #[serde(default)]
    pub focus_surfaces: Vec<SurfaceId>,
    #[serde(default)]
    pub recommended_modules: Vec<ModuleId>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
/// Route-decision artifact contract.
pub struct RouteDecisionArtifact {
    #[serde(flatten)]
    pub header: ArtifactHeader,
    pub mode: Mode,
    pub execution_architecture: ExecutionArchitecture,
    pub rigor_level: RigorLevel,
    pub capability_profile: CapabilityProfile,
    pub resource_budget: ResourceBudget,
    #[serde(default)]
    pub risk_surfaces: Vec<RiskSurfaceRecord>,
    #[serde(default)]
    pub selected_modules: Vec<ModuleId>,
    #[serde(default)]
    pub worker_plan: Vec<WorkerPlanRecord>,
    #[serde(default)]
    pub heldback_escalations: Vec<EscalationId>,
    #[serde(default)]
    pub stop_conditions: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
/// Surface-map artifact contract.
pub struct SurfaceMapArtifact {
    #[serde(flatten)]
    pub header: ArtifactHeader,
    #[serde(default)]
    pub changed_files: Vec<String>,
    #[serde(default)]
    pub public_interfaces: Vec<String>,
    #[serde(default)]
    pub behavior_facing_artifacts: Vec<String>,
    #[serde(default)]
    pub risk_surfaces: Vec<RiskSurfaceRecord>,
    #[serde(default)]
    pub suggested_modules: Vec<ModuleId>,
    pub staleness_required: bool,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
/// Child-findings artifact contract.
pub struct ChildFindingsArtifact {
    #[serde(flatten)]
    pub header: ArtifactHeader,
    pub worker_kind: WorkerKind,
    #[serde(default)]
    pub module_ids: Vec<ModuleId>,
    #[serde(default)]
    pub findings: Vec<FindingRecord>,
    #[serde(default)]
    pub defended_checks: Vec<DefendedCheckRecord>,
    #[serde(default)]
    pub residual_risks: Vec<ResidualRiskRecord>,
    #[serde(default)]
    pub route_revision_refs: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
/// Parent-review artifact contract.
pub struct ParentReviewArtifact {
    #[serde(flatten)]
    pub header: ArtifactHeader,
    #[serde(default)]
    pub source_artifact_ids: Vec<String>,
    pub final_verdict: ReviewVerdict,
    pub ship_readiness: ShipReadinessSummary,
    #[serde(default)]
    pub required_now: Vec<FindingRecord>,
    #[serde(default)]
    pub follow_up: Vec<FindingRecord>,
    #[serde(default)]
    pub defended_summary: Vec<DefendedCheckRecord>,
    #[serde(default)]
    pub residual_risks: Vec<ResidualRiskRecord>,
    pub coverage_summary: CoverageSummary,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
/// Application-result artifact contract.
pub struct ApplicationResultArtifact {
    #[serde(flatten)]
    pub header: ArtifactHeader,
    #[serde(default)]
    pub source_finding_ids: Vec<String>,
    #[serde(default)]
    pub dispositions: Vec<DispositionRecord>,
    #[serde(default)]
    pub modified_files: Vec<String>,
    #[serde(default)]
    pub verification_needed: Vec<String>,
    #[serde(default)]
    pub decline_codes: Vec<DeclineReasonCode>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
/// Verification-result artifact contract.
pub struct VerificationResultArtifact {
    #[serde(flatten)]
    pub header: ArtifactHeader,
    #[serde(default)]
    pub verified_items: Vec<VerificationItemRecord>,
    #[serde(default)]
    pub failed_items: Vec<VerificationItemRecord>,
    #[serde(default)]
    pub partial_items: Vec<VerificationItemRecord>,
    #[serde(default)]
    pub residual_risks: Vec<ResidualRiskRecord>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
/// Convergence-state artifact contract.
pub struct ConvergenceStateArtifact {
    #[serde(flatten)]
    pub header: ArtifactHeader,
    pub cycle_index: usize,
    pub reopen_threshold: ReopenThreshold,
    #[serde(default)]
    pub reopen_triggers: Vec<ReopenTriggerRecord>,
    pub terminal_cleanup_allowed: bool,
    pub next_route_inputs: NextRouteInputs,
    pub stop_condition: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
/// Route-revision artifact contract.
pub struct RouteRevisionArtifact {
    #[serde(flatten)]
    pub header: ArtifactHeader,
    #[serde(default)]
    pub discovered_surfaces: Vec<RiskSurfaceRecord>,
    #[serde(default)]
    pub added_modules: Vec<ModuleId>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub rigor_change: Option<RigorLevel>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub architecture_change: Option<ExecutionArchitecture>,
    pub reason_code: String,
    pub source_artifact_id: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
/// Parsed canonical artifact.
pub enum ArtifactDocument {
    RouteDecision(RouteDecisionArtifact),
    SurfaceMap(SurfaceMapArtifact),
    ChildFindings(ChildFindingsArtifact),
    ParentReview(ParentReviewArtifact),
    ApplicationResult(ApplicationResultArtifact),
    VerificationResult(VerificationResultArtifact),
    ConvergenceState(ConvergenceStateArtifact),
    RouteRevision(RouteRevisionArtifact),
}

impl ArtifactDocument {
    /// Kind of the contained artifact.
    #[must_use]
    pub const fn kind(&self) -> ArtifactKind {
        match self {
            Self::RouteDecision(_) => ArtifactKind::RouteDecision,
            Self::SurfaceMap(_) => ArtifactKind::SurfaceMap,
            Self::ChildFindings(_) => ArtifactKind::ChildFindings,
            Self::ParentReview(_) => ArtifactKind::ParentReview,
            Self::ApplicationResult(_) => ArtifactKind::ApplicationResult,
            Self::VerificationResult(_) => ArtifactKind::VerificationResult,
            Self::ConvergenceState(_) => ArtifactKind::ConvergenceState,
            Self::RouteRevision(_) => ArtifactKind::RouteRevision,
        }
    }

    /// Common header for the contained artifact.
    #[must_use]
    pub const fn header(&self) -> &ArtifactHeader {
        match self {
            Self::RouteDecision(artifact) => &artifact.header,
            Self::SurfaceMap(artifact) => &artifact.header,
            Self::ChildFindings(artifact) => &artifact.header,
            Self::ParentReview(artifact) => &artifact.header,
            Self::ApplicationResult(artifact) => &artifact.header,
            Self::VerificationResult(artifact) => &artifact.header,
            Self::ConvergenceState(artifact) => &artifact.header,
            Self::RouteRevision(artifact) => &artifact.header,
        }
    }

    /// Serialize the document as pretty TOML.
    ///
    /// # Errors
    /// Returns an error if serialization fails.
    pub fn to_toml_string(&self) -> anyhow::Result<String> {
        let body = match self {
            Self::RouteDecision(artifact) => toml::to_string_pretty(artifact)?,
            Self::SurfaceMap(artifact) => toml::to_string_pretty(artifact)?,
            Self::ChildFindings(artifact) => toml::to_string_pretty(artifact)?,
            Self::ParentReview(artifact) => toml::to_string_pretty(artifact)?,
            Self::ApplicationResult(artifact) => toml::to_string_pretty(artifact)?,
            Self::VerificationResult(artifact) => toml::to_string_pretty(artifact)?,
            Self::ConvergenceState(artifact) => toml::to_string_pretty(artifact)?,
            Self::RouteRevision(artifact) => toml::to_string_pretty(artifact)?,
        };
        Ok(body)
    }
}

#[derive(Debug, Deserialize)]
struct ArtifactProbe {
    schema_version: String,
    artifact_kind: ArtifactKind,
}

/// Parse a canonical artifact file into a typed document.
///
/// # Errors
/// Returns an error if the file cannot be read, parsed, or is legacy state.
pub fn parse_artifact_file(path: &Path) -> anyhow::Result<ArtifactDocument> {
    let body = std::fs::read_to_string(path)
        .with_context(|| format!("read artifact file {}", path.display()))?;
    parse_artifact_str(&body)
}

/// Parse a canonical artifact string into a typed document.
///
/// # Errors
/// Returns an error if the TOML cannot be parsed or is legacy state.
pub fn parse_artifact_str(body: &str) -> anyhow::Result<ArtifactDocument> {
    if body.contains("proof_packet.v2") || body.contains("parent_review_report") {
        return Err(anyhow::anyhow!(LEGACY_REJECTION_MESSAGE));
    }
    let probe: ArtifactProbe =
        toml::from_str(body).map_err(|err| anyhow::anyhow!("error: parse artifact TOML: {err}"))?;
    if probe.schema_version != ARTIFACT_SCHEMA_VERSION {
        return Err(anyhow::anyhow!(LEGACY_REJECTION_MESSAGE));
    }
    match probe.artifact_kind {
        ArtifactKind::RouteDecision => Ok(ArtifactDocument::RouteDecision(toml::from_str(body)?)),
        ArtifactKind::SurfaceMap => Ok(ArtifactDocument::SurfaceMap(toml::from_str(body)?)),
        ArtifactKind::ChildFindings => Ok(ArtifactDocument::ChildFindings(toml::from_str(body)?)),
        ArtifactKind::ParentReview => Ok(ArtifactDocument::ParentReview(toml::from_str(body)?)),
        ArtifactKind::ApplicationResult => {
            Ok(ArtifactDocument::ApplicationResult(toml::from_str(body)?))
        }
        ArtifactKind::VerificationResult => {
            Ok(ArtifactDocument::VerificationResult(toml::from_str(body)?))
        }
        ArtifactKind::ConvergenceState => {
            Ok(ArtifactDocument::ConvergenceState(toml::from_str(body)?))
        }
        ArtifactKind::RouteRevision => Ok(ArtifactDocument::RouteRevision(toml::from_str(body)?)),
    }
}

/// Validate the v2 `session_id` format.
///
/// # Errors
/// Returns an error if the identifier is invalid.
pub fn validate_session_id(session_id: &str) -> anyhow::Result<()> {
    let valid_len = session_id.len() == 8;
    let valid_chars = session_id
        .chars()
        .all(|value| value.is_ascii_alphanumeric());
    anyhow::ensure!(
        valid_len && valid_chars,
        "error: session_id must be 8 lowercase hex or 8 ASCII alphanumeric characters"
    );
    Ok(())
}

/// Validate the v2 `artifact_id` format.
///
/// # Errors
/// Returns an error if the identifier is invalid.
pub fn validate_artifact_id(artifact_id: &str) -> anyhow::Result<()> {
    anyhow::ensure!(
        artifact_id.len() == 12
            && artifact_id
                .chars()
                .all(|value| value.is_ascii_hexdigit() && !value.is_ascii_uppercase()),
        "error: artifact_id must be 12 lowercase hex characters"
    );
    Ok(())
}

/// Validate an RFC3339 UTC timestamp.
///
/// # Errors
/// Returns an error if the timestamp is invalid or not UTC.
pub fn validate_created_at(created_at: &str) -> anyhow::Result<()> {
    let parsed = OffsetDateTime::parse(created_at, &Rfc3339)
        .map_err(|err| anyhow::anyhow!("error: created_at must be RFC3339 UTC: {err}"))?;
    anyhow::ensure!(
        parsed.offset().whole_seconds() == 0,
        "error: created_at must be an RFC3339 UTC timestamp"
    );
    Ok(())
}

/// Validate the confidence band for a label/score pair.
///
/// # Errors
/// Returns an error if the score does not match the required band.
pub fn validate_confidence(label: ConfidenceLabel, score: u8) -> anyhow::Result<()> {
    let valid = match label {
        ConfidenceLabel::High => (80..=100).contains(&score),
        ConfidenceLabel::Medium => (50..=79).contains(&score),
        ConfidenceLabel::Low => score <= 49,
    };
    anyhow::ensure!(
        valid,
        "error: confidence score {score} does not match label {:?}",
        label
    );
    Ok(())
}

/// Normalize a repo-relative path using `/` separators.
#[must_use]
pub fn normalize_repo_relative_path(path: &str) -> String {
    path.trim().trim_start_matches("./").replace('\\', "/")
}

/// Validate an anchor string against the canonical formats.
///
/// # Errors
/// Returns an error if the anchor is malformed.
pub fn validate_anchor(anchor: &str) -> anyhow::Result<()> {
    let (path, suffix) = anchor.rsplit_once(':').ok_or_else(|| {
        anyhow::anyhow!("error: anchor `{anchor}` must contain a trailing line segment")
    })?;
    anyhow::ensure!(
        !path.is_empty() && !suffix.is_empty(),
        "error: anchor `{anchor}` must use `path/to/file:line` or `path/to/file:start-end`"
    );
    anyhow::ensure!(
        !path.contains('\\'),
        "error: anchor `{anchor}` must use repo-relative `/` separators"
    );
    if let Some((start, end)) = suffix.split_once('-') {
        let start_line: usize = start
            .parse()
            .map_err(|_| anyhow::anyhow!("error: invalid anchor start line in `{anchor}`"))?;
        let end_line: usize = end
            .parse()
            .map_err(|_| anyhow::anyhow!("error: invalid anchor end line in `{anchor}`"))?;
        anyhow::ensure!(
            start_line > 0 && end_line >= start_line,
            "error: invalid anchor range `{anchor}`"
        );
    } else {
        let line: usize = suffix
            .parse()
            .map_err(|_| anyhow::anyhow!("error: invalid anchor line in `{anchor}`"))?;
        anyhow::ensure!(line > 0, "error: invalid anchor line in `{anchor}`");
    }
    Ok(())
}

/// Compute the anchor cluster required for deduplication.
///
/// # Errors
/// Returns an error if no anchors are present or the first anchor is invalid.
pub fn compute_anchor_cluster(
    anchors: &[String],
    symbol_hint: Option<&str>,
) -> anyhow::Result<String> {
    let first_anchor = anchors
        .first()
        .ok_or_else(|| anyhow::anyhow!("error: finding anchors[] must not be empty"))?;
    validate_anchor(first_anchor)?;
    let (path, suffix) = first_anchor
        .rsplit_once(':')
        .ok_or_else(|| anyhow::anyhow!("error: invalid anchor `{first_anchor}`"))?;
    let normalized_path = normalize_repo_relative_path(path);
    if let Some(symbol) = symbol_hint.filter(|value| !value.trim().is_empty()) {
        return Ok(format!("{normalized_path}#{symbol}"));
    }
    let start_line = suffix
        .split('-')
        .next()
        .ok_or_else(|| anyhow::anyhow!("error: invalid anchor `{first_anchor}`"))?
        .parse::<usize>()
        .map_err(|_| anyhow::anyhow!("error: invalid anchor `{first_anchor}`"))?;
    let bucket = (start_line.saturating_sub(1)) / 10;
    Ok(format!("{normalized_path}#bucket:{bucket}"))
}

/// Compute the canonical 16-hex finding fingerprint.
#[must_use]
pub fn compute_fingerprint(
    claim: &str,
    module_id: ModuleId,
    surface_ids: &[SurfaceId],
    anchor_cluster: &str,
) -> String {
    let normalized_claim = claim
        .to_ascii_lowercase()
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ");
    let mut sorted_surfaces = surface_ids.to_vec();
    sorted_surfaces.sort_unstable();
    let joined_surfaces = sorted_surfaces
        .iter()
        .map(|value| {
            toml::Value::try_from(*value).map_or_else(
                |_| String::new(),
                |toml_value| toml_value.to_string().trim_matches('"').to_string(),
            )
        })
        .collect::<Vec<_>>()
        .join(",");
    let material = format!(
        "{normalized_claim}|{}|{joined_surfaces}|{anchor_cluster}",
        toml::Value::try_from(module_id).map_or_else(
            |_| String::new(),
            |value| value.to_string().trim_matches('"').to_string()
        )
    );
    let digest = Sha256::digest(material.as_bytes());
    digest[..8]
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect::<String>()
}

/// Recompute and validate the dedupe identity fields on a finding.
///
/// # Errors
/// Returns an error if the stored identity is inconsistent.
pub fn validate_finding_identity(finding: &FindingRecord) -> anyhow::Result<()> {
    validate_confidence(finding.confidence_label, finding.confidence_score)?;
    for anchor in &finding.anchors {
        validate_anchor(anchor)?;
    }
    let expected_cluster =
        compute_anchor_cluster(&finding.anchors, finding.symbol_hint.as_deref())?;
    anyhow::ensure!(
        finding.anchor_cluster == expected_cluster,
        "error: finding `{}` has inconsistent anchor_cluster",
        finding.finding_id
    );
    let expected_fingerprint = compute_fingerprint(
        &finding.claim,
        finding.module_id,
        &finding.surface_ids,
        &finding.anchor_cluster,
    );
    anyhow::ensure!(
        finding.fingerprint == expected_fingerprint,
        "error: finding `{}` has inconsistent fingerprint",
        finding.finding_id
    );
    Ok(())
}

/// Build a canonical UTC timestamp string.
#[must_use]
pub fn now_rfc3339() -> String {
    match OffsetDateTime::now_utc().format(&Rfc3339) {
        Ok(timestamp) => timestamp,
        Err(_err) => "1970-01-01T00:00:00Z".to_string(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use anyhow::ensure;

    fn sample_header(kind: ArtifactKind) -> anyhow::Result<ArtifactHeader> {
        ArtifactHeader::new(
            kind,
            "abc123def456".to_string(),
            "sess0001".to_string(),
            "refs/heads/main".to_string(),
            ProducerKind::Router,
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

    #[test]
    fn ids_anchors_and_fingerprints_follow_prd_contracts() -> anyhow::Result<()> {
        validate_session_id("sess0001")?;
        validate_artifact_id("abc123def456")?;
        validate_anchor("src/lib.rs:12")?;
        validate_anchor("src/lib.rs:12-18")?;

        let anchor_cluster = compute_anchor_cluster(&["src/lib.rs:12".to_string()], None)?;
        ensure!(anchor_cluster == "src/lib.rs#bucket:1");
        let with_symbol = compute_anchor_cluster(&["src/lib.rs:12".to_string()], Some("handler"))?;
        ensure!(with_symbol == "src/lib.rs#handler");

        let fingerprint = compute_fingerprint(
            "Invariant must hold",
            ModuleId::CoreCorrectness,
            &[SurfaceId::PublicApi, SurfaceId::Concurrency],
            &anchor_cluster,
        );
        ensure!(fingerprint.len() == 16);
        ensure!(fingerprint.chars().all(|value| value.is_ascii_hexdigit()));
        Ok(())
    }

    #[test]
    fn artifacts_round_trip_through_toml() -> anyhow::Result<()> {
        let finding = FindingRecord {
            finding_id: "F001".to_string(),
            module_id: ModuleId::CoreCorrectness,
            surface_ids: vec![SurfaceId::PublicApi],
            severity: Severity::Major,
            title: "Public contract drift".to_string(),
            claim: "The new return type breaks callers.".to_string(),
            scenario: "A caller still expects the old schema.".to_string(),
            evidence: "Changed handler now emits a renamed field.".to_string(),
            recommendation: "Preserve compatibility or version the contract.".to_string(),
            verification: "Run the old client fixture against the new binary.".to_string(),
            anchors: vec!["src/api.rs:14-22".to_string()],
            symbol_hint: Some("get_widget".to_string()),
            anchor_cluster: "src/api.rs#get_widget".to_string(),
            fingerprint: compute_fingerprint(
                "The new return type breaks callers.",
                ModuleId::CoreCorrectness,
                &[SurfaceId::PublicApi],
                "src/api.rs#get_widget",
            ),
            reopen_eligible: true,
            confidence_label: ConfidenceLabel::High,
            confidence_score: 88,
        };
        validate_finding_identity(&finding)?;

        let artifact = ParentReviewArtifact {
            header: sample_header(ArtifactKind::ParentReview)?,
            source_artifact_ids: vec!["feed00cafe12".to_string()],
            final_verdict: ReviewVerdict::RequestChanges,
            ship_readiness: ShipReadinessSummary {
                verdict: ShipReadinessVerdict::ShipWithFixes,
                axes: vec!["correctness".to_string()],
                blocking_items: vec!["Public contract drift".to_string()],
                required_now_count: 1,
                follow_up_count: 0,
            },
            required_now: vec![finding],
            follow_up: Vec::new(),
            defended_summary: Vec::new(),
            residual_risks: Vec::new(),
            coverage_summary: CoverageSummary {
                changed_files: vec!["src/api.rs".to_string()],
                surfaces_covered: vec![SurfaceId::PublicApi],
                modules_loaded: vec![ModuleId::CoreCorrectness, ModuleId::ShipReadiness],
                tests_run: vec!["cargo test api_contract".to_string()],
                tests_not_run_reason: None,
                limitations: Vec::new(),
            },
        };

        let doc = ArtifactDocument::ParentReview(artifact.clone());
        let encoded = doc.to_toml_string()?;
        let parsed = parse_artifact_str(&encoded)?;
        ensure!(parsed == ArtifactDocument::ParentReview(artifact));
        Ok(())
    }
}
