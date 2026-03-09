//! Telemetry aggregation for compact v2 sessions.
#![allow(missing_docs)]

use crate::artifacts::{
    ApplicationResultArtifact, ArtifactDocument, ChildFindingsArtifact, ConvergenceStateArtifact,
    DeclineReasonCode, DuplicateReasonCode, ModuleId, ProducerKind, ReopenReasonCode, SurfaceId,
    VerificationStatus, WorkerKind,
};
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
/// Grouped precision row persisted in the compact telemetry ledger.
pub struct PrecisionCounterRow {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub worker_kind: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub module_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub surface_id: Option<String>,
    pub policy_version: String,
    pub outcome_type: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub reason_code: Option<String>,
    pub count: u64,
}

#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
/// Categorical telemetry persisted in the session ledger.
pub struct TelemetryLedger {
    #[serde(default)]
    pub worker_kind: BTreeMap<String, u64>,
    #[serde(default)]
    pub module_id: BTreeMap<String, u64>,
    #[serde(default)]
    pub surface_id: BTreeMap<String, u64>,
    #[serde(default)]
    pub decline_reason_code: BTreeMap<String, u64>,
    #[serde(default)]
    pub duplicate_reason_code: BTreeMap<String, u64>,
    #[serde(default)]
    pub reopen_reason_code: BTreeMap<String, u64>,
    #[serde(default)]
    pub verification_outcome: BTreeMap<String, u64>,
    #[serde(default)]
    pub policy_version: BTreeMap<String, u64>,
    #[serde(default)]
    pub grouped_precision: Vec<PrecisionCounterRow>,
}

fn increment(map: &mut BTreeMap<String, u64>, key: impl Into<String>) {
    let entry = map.entry(key.into()).or_insert(0);
    *entry += 1;
}

fn worker_key(worker: WorkerKind) -> String {
    toml::Value::try_from(worker).map_or_else(
        |_| "unknown".to_string(),
        |value| value.to_string().trim_matches('"').to_string(),
    )
}

fn module_key(module_id: ModuleId) -> String {
    toml::Value::try_from(module_id).map_or_else(
        |_| "unknown".to_string(),
        |value| value.to_string().trim_matches('"').to_string(),
    )
}

fn surface_key(surface_id: SurfaceId) -> String {
    toml::Value::try_from(surface_id).map_or_else(
        |_| "unknown".to_string(),
        |value| value.to_string().trim_matches('"').to_string(),
    )
}

fn decline_key(code: DeclineReasonCode) -> String {
    toml::Value::try_from(code).map_or_else(
        |_| "unknown".to_string(),
        |value| value.to_string().trim_matches('"').to_string(),
    )
}

fn duplicate_key(code: DuplicateReasonCode) -> String {
    toml::Value::try_from(code).map_or_else(
        |_| "unknown".to_string(),
        |value| value.to_string().trim_matches('"').to_string(),
    )
}

fn reopen_key(code: ReopenReasonCode) -> String {
    toml::Value::try_from(code).map_or_else(
        |_| "unknown".to_string(),
        |value| value.to_string().trim_matches('"').to_string(),
    )
}

fn verification_key(status: VerificationStatus) -> String {
    toml::Value::try_from(status).map_or_else(
        |_| "unknown".to_string(),
        |value| value.to_string().trim_matches('"').to_string(),
    )
}

fn producer_worker_key(producer_kind: ProducerKind) -> Option<String> {
    match producer_kind {
        ProducerKind::ReviewComposite => Some(worker_key(WorkerKind::ReviewComposite)),
        ProducerKind::ApplyComposite => Some(worker_key(WorkerKind::ApplyComposite)),
        ProducerKind::SurfaceMapper => Some(worker_key(WorkerKind::SurfaceMapper)),
        ProducerKind::InvariantChallenger => Some(worker_key(WorkerKind::InvariantChallenger)),
        ProducerKind::ExploitTracer => Some(worker_key(WorkerKind::ExploitTracer)),
        ProducerKind::ContractComparer => Some(worker_key(WorkerKind::ContractComparer)),
        ProducerKind::CongruenceChecker => Some(worker_key(WorkerKind::CongruenceChecker)),
        ProducerKind::SimplificationChecker => Some(worker_key(WorkerKind::SimplificationChecker)),
        ProducerKind::ReleaseRiskAssessor => Some(worker_key(WorkerKind::ReleaseRiskAssessor)),
        ProducerKind::ApplicatorWorker => Some(worker_key(WorkerKind::ApplicatorWorker)),
        ProducerKind::ApplicatorVerifier => Some(worker_key(WorkerKind::ApplicatorVerifier)),
        ProducerKind::Router
        | ProducerKind::ConvergencePlanner
        | ProducerKind::Renderer
        | ProducerKind::Validator => None,
    }
}

fn increment_grouped_precision(
    telemetry: &mut TelemetryLedger,
    worker_kind: Option<String>,
    module_id: Option<String>,
    surface_id: Option<String>,
    policy_version: &str,
    outcome_type: &str,
    reason_code: Option<String>,
) {
    if let Some(row) = telemetry.grouped_precision.iter_mut().find(|row| {
        row.worker_kind == worker_kind
            && row.module_id == module_id
            && row.surface_id == surface_id
            && row.policy_version == policy_version
            && row.outcome_type == outcome_type
            && row.reason_code == reason_code
    }) {
        row.count += 1;
        return;
    }
    telemetry.grouped_precision.push(PrecisionCounterRow {
        worker_kind,
        module_id,
        surface_id,
        policy_version: policy_version.to_string(),
        outcome_type: outcome_type.to_string(),
        reason_code,
        count: 1,
    });
    telemetry.grouped_precision.sort_by(|left, right| {
        left.worker_kind
            .cmp(&right.worker_kind)
            .then_with(|| left.module_id.cmp(&right.module_id))
            .then_with(|| left.surface_id.cmp(&right.surface_id))
            .then_with(|| left.policy_version.cmp(&right.policy_version))
            .then_with(|| left.outcome_type.cmp(&right.outcome_type))
            .then_with(|| left.reason_code.cmp(&right.reason_code))
    });
}

fn record_child_findings(telemetry: &mut TelemetryLedger, artifact: &ChildFindingsArtifact) {
    increment(&mut telemetry.worker_kind, worker_key(artifact.worker_kind));
    for module_id in &artifact.module_ids {
        increment(&mut telemetry.module_id, module_key(*module_id));
    }
    for finding in &artifact.findings {
        increment(&mut telemetry.module_id, module_key(finding.module_id));
        if finding.surface_ids.is_empty() {
            increment_grouped_precision(
                telemetry,
                Some(worker_key(artifact.worker_kind)),
                Some(module_key(finding.module_id)),
                None,
                &artifact.header.policy_version,
                "review_finding_emitted",
                None,
            );
        } else {
            for surface_id in &finding.surface_ids {
                increment(&mut telemetry.surface_id, surface_key(*surface_id));
                increment_grouped_precision(
                    telemetry,
                    Some(worker_key(artifact.worker_kind)),
                    Some(module_key(finding.module_id)),
                    Some(surface_key(*surface_id)),
                    &artifact.header.policy_version,
                    "review_finding_emitted",
                    None,
                );
            }
        }
    }
    for residual_risk in &artifact.residual_risks {
        for surface_id in &residual_risk.surface_ids {
            increment(&mut telemetry.surface_id, surface_key(*surface_id));
        }
    }
}

fn record_application_result(
    telemetry: &mut TelemetryLedger,
    artifact: &ApplicationResultArtifact,
) {
    for disposition in &artifact.dispositions {
        if let Some(code) = disposition.decline_reason_code {
            increment(&mut telemetry.decline_reason_code, decline_key(code));
            increment_grouped_precision(
                telemetry,
                producer_worker_key(artifact.header.producer_kind),
                None,
                None,
                &artifact.header.policy_version,
                "finding_declined",
                Some(decline_key(code)),
            );
        }
        if let Some(code) = disposition.duplicate_reason_code {
            increment(&mut telemetry.duplicate_reason_code, duplicate_key(code));
            increment_grouped_precision(
                telemetry,
                producer_worker_key(artifact.header.producer_kind),
                None,
                None,
                &artifact.header.policy_version,
                "duplicate",
                Some(duplicate_key(code)),
            );
        }
        if disposition.disposition == crate::artifacts::Disposition::Applied {
            increment_grouped_precision(
                telemetry,
                producer_worker_key(artifact.header.producer_kind),
                None,
                None,
                &artifact.header.policy_version,
                "finding_applied",
                None,
            );
        }
    }
}

fn record_convergence_state(telemetry: &mut TelemetryLedger, artifact: &ConvergenceStateArtifact) {
    for trigger in &artifact.reopen_triggers {
        increment(
            &mut telemetry.reopen_reason_code,
            reopen_key(trigger.reopen_reason_code),
        );
        increment_grouped_precision(
            telemetry,
            None,
            None,
            None,
            &artifact.header.policy_version,
            "reopen_triggered",
            Some(reopen_key(trigger.reopen_reason_code)),
        );
    }
}

/// Record telemetry for one persisted artifact.
pub fn record_artifact(telemetry: &mut TelemetryLedger, artifact: &ArtifactDocument) {
    increment(
        &mut telemetry.policy_version,
        artifact.header().policy_version.clone(),
    );
    match artifact {
        ArtifactDocument::RouteDecision(route_decision) => {
            for module_id in &route_decision.selected_modules {
                increment(&mut telemetry.module_id, module_key(*module_id));
            }
            for surface in &route_decision.risk_surfaces {
                increment(&mut telemetry.surface_id, surface_key(surface.surface_id));
            }
        }
        ArtifactDocument::SurfaceMap(surface_map) => {
            for module_id in &surface_map.suggested_modules {
                increment(&mut telemetry.module_id, module_key(*module_id));
            }
            for surface in &surface_map.risk_surfaces {
                increment(&mut telemetry.surface_id, surface_key(surface.surface_id));
            }
        }
        ArtifactDocument::ChildFindings(artifact) => record_child_findings(telemetry, artifact),
        ArtifactDocument::ParentReview(parent_review) => {
            for finding in &parent_review.required_now {
                increment(&mut telemetry.module_id, module_key(finding.module_id));
                for surface_id in &finding.surface_ids {
                    increment(&mut telemetry.surface_id, surface_key(*surface_id));
                }
            }
            for finding in &parent_review.follow_up {
                increment(&mut telemetry.module_id, module_key(finding.module_id));
                for surface_id in &finding.surface_ids {
                    increment(&mut telemetry.surface_id, surface_key(*surface_id));
                }
            }
        }
        ArtifactDocument::ApplicationResult(artifact) => {
            record_application_result(telemetry, artifact)
        }
        ArtifactDocument::VerificationResult(verification_result) => {
            for item in &verification_result.verified_items {
                increment(
                    &mut telemetry.verification_outcome,
                    verification_key(item.status),
                );
                increment_grouped_precision(
                    telemetry,
                    producer_worker_key(verification_result.header.producer_kind),
                    None,
                    None,
                    &verification_result.header.policy_version,
                    "verification_yes",
                    None,
                );
            }
            for item in &verification_result.failed_items {
                increment(
                    &mut telemetry.verification_outcome,
                    verification_key(item.status),
                );
                increment_grouped_precision(
                    telemetry,
                    producer_worker_key(verification_result.header.producer_kind),
                    None,
                    None,
                    &verification_result.header.policy_version,
                    "verification_no",
                    None,
                );
            }
            for item in &verification_result.partial_items {
                increment(
                    &mut telemetry.verification_outcome,
                    verification_key(item.status),
                );
                increment_grouped_precision(
                    telemetry,
                    producer_worker_key(verification_result.header.producer_kind),
                    None,
                    None,
                    &verification_result.header.policy_version,
                    "verification_partial",
                    None,
                );
            }
            for residual_risk in &verification_result.residual_risks {
                for surface_id in &residual_risk.surface_ids {
                    increment(&mut telemetry.surface_id, surface_key(*surface_id));
                }
            }
        }
        ArtifactDocument::ConvergenceState(artifact) => {
            record_convergence_state(telemetry, artifact)
        }
        ArtifactDocument::RouteRevision(route_revision) => {
            for module_id in &route_revision.added_modules {
                increment(&mut telemetry.module_id, module_key(*module_id));
            }
            for surface in &route_revision.discovered_surfaces {
                increment(&mut telemetry.surface_id, surface_key(surface.surface_id));
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::artifacts::{
        ArtifactHeader, ArtifactKind, ConfidenceLabel, PolicyCategory, PolicyRef, PolicyView,
        ProducerKind,
    };

    fn header(kind: crate::artifacts::ArtifactKind) -> anyhow::Result<ArtifactHeader> {
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
    fn telemetry_aggregates_by_required_categories() -> anyhow::Result<()> {
        let artifact = ArtifactDocument::RouteDecision(crate::artifacts::RouteDecisionArtifact {
            header: header(ArtifactKind::RouteDecision)?,
            mode: crate::artifacts::Mode::Reviewer,
            execution_architecture: crate::artifacts::ExecutionArchitecture::Hybrid,
            rigor_level: crate::artifacts::RigorLevel::Forensic,
            capability_profile: crate::artifacts::CapabilityProfile {
                execution_capability: crate::artifacts::ExecutionCapability::ParallelSubagents,
                max_worker_count: 6,
                orchestrator_read_budget_lines: 120,
                orchestrator_read_budget_snippets: 12,
            },
            resource_budget: crate::artifacts::ResourceBudget {
                planned_worker_count: 4,
                max_worker_count: 6,
            },
            risk_surfaces: vec![crate::artifacts::RiskSurfaceRecord {
                surface_id: SurfaceId::AuthAccess,
                weight: 5,
                reason: "auth path".to_string(),
                evidence_refs: vec!["src/auth.rs".to_string()],
                behavior_facing: false,
            }],
            selected_modules: vec![ModuleId::CoreCorrectness, ModuleId::AuthAccess],
            worker_plan: Vec::new(),
            heldback_escalations: Vec::new(),
            stop_conditions: Vec::new(),
        });

        let mut telemetry = TelemetryLedger::default();
        record_artifact(&mut telemetry, &artifact);
        anyhow::ensure!(telemetry.policy_version.get("2026.03.08") == Some(&1));
        anyhow::ensure!(telemetry.module_id.get("core-correctness") == Some(&1));
        anyhow::ensure!(telemetry.module_id.get("auth-access") == Some(&1));
        anyhow::ensure!(telemetry.surface_id.get("auth-access") == Some(&1));
        anyhow::ensure!(telemetry.grouped_precision.is_empty());
        Ok(())
    }

    #[test]
    fn decline_reasons_are_not_double_counted_and_grouped_rows_exist() -> anyhow::Result<()> {
        let artifact =
            ArtifactDocument::ApplicationResult(crate::artifacts::ApplicationResultArtifact {
                header: ArtifactHeader::new(
                    ArtifactKind::ApplicationResult,
                    "abc123def456".to_string(),
                    "sess0001".to_string(),
                    "refs/heads/main".to_string(),
                    ProducerKind::ApplicatorWorker,
                    "2026-03-08T00:00:00Z".to_string(),
                    ConfidenceLabel::High,
                    90,
                    vec![PolicyRef {
                        category: PolicyCategory::Mode,
                        id: "applicator".to_string(),
                        version: "2026.03.08".to_string(),
                        view: PolicyView::Checklist,
                    }],
                )?,
                source_finding_ids: vec!["F001".to_string()],
                dispositions: vec![crate::artifacts::DispositionRecord {
                    finding_id: "F001".to_string(),
                    disposition: crate::artifacts::Disposition::Declined,
                    decline_reason_code: Some(DeclineReasonCode::Duplicate),
                    duplicate_reason_code: Some(DuplicateReasonCode::SameAnchorSameClaim),
                    detail: "duplicate".to_string(),
                    tracking_ref: None,
                    verification_needed: false,
                }],
                modified_files: Vec::new(),
                verification_needed: Vec::new(),
                decline_codes: vec![DeclineReasonCode::Duplicate],
            });

        let mut telemetry = TelemetryLedger::default();
        record_artifact(&mut telemetry, &artifact);
        anyhow::ensure!(telemetry.decline_reason_code.get("duplicate") == Some(&1));
        anyhow::ensure!(telemetry
            .grouped_precision
            .iter()
            .any(|row| row.outcome_type == "finding_declined"
                && row.reason_code.as_deref() == Some("duplicate")
                && row.count == 1));
        Ok(())
    }
}
