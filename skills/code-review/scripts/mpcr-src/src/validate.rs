//! Hard and soft validation for canonical v2 artifacts.
#![allow(missing_docs)]

use crate::artifacts::{
    parse_artifact_file, validate_anchor, validate_artifact_id, validate_confidence,
    validate_created_at, validate_finding_identity, validate_session_id, ApplicationResultArtifact,
    ArtifactDocument, ArtifactHeader, ArtifactKind, ChildFindingsArtifact,
    ConvergenceStateArtifact, CoverageSummary, FindingRecord, ModuleId, ParentReviewArtifact,
    RouteDecisionArtifact, RouteRevisionArtifact, SurfaceMapArtifact, VerificationResultArtifact,
};
use crate::render::render_artifact_markdown;
use serde::Serialize;
use std::path::Path;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, clap::ValueEnum)]
#[serde(rename_all = "snake_case")]
/// Validation layer requested by the caller.
pub enum ValidationLayer {
    Hard,
    Soft,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
/// Validation summary returned by hard/soft validation.
pub struct ValidationSummary {
    pub artifact_kind: ArtifactKind,
    pub layer: ValidationLayer,
    #[serde(default)]
    pub errors: Vec<String>,
    #[serde(default)]
    pub warnings: Vec<String>,
}

fn validate_header(header: &ArtifactHeader, expected_kind: ArtifactKind) -> anyhow::Result<()> {
    validate_artifact_id(&header.artifact_id)?;
    validate_session_id(&header.session_id)?;
    validate_created_at(&header.created_at)?;
    validate_confidence(header.confidence_label, header.confidence_score)?;
    anyhow::ensure!(
        header.artifact_kind == expected_kind,
        "artifact_kind `{}` did not match expected `{expected_kind}`",
        header.artifact_kind
    );
    anyhow::ensure!(
        !header.loaded_policy_refs.is_empty(),
        "loaded_policy_refs[] must not be empty"
    );
    Ok(())
}

fn validate_repo_paths(paths: &[String], errors: &mut Vec<String>) {
    for path in paths {
        if path.contains('\\') {
            errors.push(format!(
                "repo-relative path `{path}` must use `/` separators"
            ));
        }
        if path.trim().is_empty() {
            errors.push("repo-relative path must not be empty".to_string());
        }
    }
}

fn validate_coverage(coverage: &CoverageSummary, errors: &mut Vec<String>) {
    validate_repo_paths(&coverage.changed_files, errors);
    validate_repo_paths(&coverage.tests_run, errors);
    validate_repo_paths(&coverage.limitations, errors);
}

fn validate_artifact_refs(refs: &[String], session_dir: Option<&Path>, errors: &mut Vec<String>) {
    for artifact_id in refs {
        if let Err(err) = validate_artifact_id(artifact_id) {
            errors.push(err.to_string());
            continue;
        }
        if let Some(session_dir) = session_dir {
            let found = crate::artifacts::ArtifactKind::all().iter().any(|kind| {
                crate::paths::existing_artifact_path(session_dir, *kind, artifact_id).is_some()
            });
            if !found {
                errors.push(format!(
                    "artifact ref `{artifact_id}` was not found in the session store"
                ));
            }
        }
    }
}

fn validate_findings(findings: &[FindingRecord], errors: &mut Vec<String>) {
    for finding in findings {
        if let Err(err) = validate_finding_identity(finding) {
            errors.push(err.to_string());
        }
    }
}

fn canonical_review_modules() -> Vec<ModuleId> {
    let mut modules = ModuleId::all().to_vec();
    modules.sort_unstable();
    modules
}

fn validate_recursive_review_roster(artifact: &RouteDecisionArtifact, errors: &mut Vec<String>) {
    let mut selected_modules = artifact.selected_modules.clone();
    selected_modules.sort_unstable();
    selected_modules.dedup();
    let canonical_modules = canonical_review_modules();
    if selected_modules != canonical_modules {
        errors.push(
            "review and full-cycle routes must include the full canonical domain roster"
                .to_string(),
        );
    }

    if artifact.worker_plan.is_empty() {
        errors.push("review and full-cycle routes must include a worker plan".to_string());
        return;
    }

    let allowed_worker_kinds = [
        crate::artifacts::WorkerKind::LanguageDetector,
        crate::artifacts::WorkerKind::LanguageResearch,
        crate::artifacts::WorkerKind::DomainReviewer,
        crate::artifacts::WorkerKind::FinalSynthesizer,
    ];
    for worker in &artifact.worker_plan {
        if !allowed_worker_kinds.contains(&worker.worker_kind) {
            errors.push(format!(
                "review and full-cycle routes must not include legacy worker kind `{}`",
                toml::Value::try_from(worker.worker_kind).map_or_else(
                    |_| "unknown".to_string(),
                    |value| value.to_string().trim_matches('"').to_string()
                )
            ));
        }
    }

    if artifact
        .worker_plan
        .first()
        .map(|worker| worker.worker_kind)
        != Some(crate::artifacts::WorkerKind::LanguageDetector)
    {
        errors.push("review and full-cycle routes must begin with language-detector".to_string());
    }
    if artifact.worker_plan.last().map(|worker| worker.worker_kind)
        != Some(crate::artifacts::WorkerKind::FinalSynthesizer)
    {
        errors.push("review and full-cycle routes must end with final-synthesizer".to_string());
    }

    let language_detector_count = artifact
        .worker_plan
        .iter()
        .filter(|worker| worker.worker_kind == crate::artifacts::WorkerKind::LanguageDetector)
        .count();
    if language_detector_count != 1 {
        errors.push(
            "review and full-cycle routes must include exactly one language-detector".to_string(),
        );
    }

    let final_synth_count = artifact
        .worker_plan
        .iter()
        .filter(|worker| worker.worker_kind == crate::artifacts::WorkerKind::FinalSynthesizer)
        .count();
    if final_synth_count != 1 {
        errors.push(
            "review and full-cycle routes must include exactly one final-synthesizer".to_string(),
        );
    }

    let mut domain_modules = Vec::new();
    for worker in &artifact.worker_plan {
        match worker.worker_kind {
            crate::artifacts::WorkerKind::LanguageResearch => {
                if worker.language.as_deref().is_none_or(str::is_empty) {
                    errors.push("language-research workers must declare a language".to_string());
                }
            }
            crate::artifacts::WorkerKind::DomainReviewer => {
                if worker.module_ids.len() != 1 {
                    errors.push(
                        "each domain-reviewer worker must claim exactly one module".to_string(),
                    );
                    continue;
                }
                domain_modules.push(worker.module_ids[0]);
                let expected_role = format!(
                    "domain:{}",
                    toml::Value::try_from(worker.module_ids[0]).map_or_else(
                        |_| "unknown".to_string(),
                        |value| value.to_string().trim_matches('"').to_string()
                    )
                );
                if worker.role_id.as_deref() != Some(expected_role.as_str()) {
                    errors.push(format!(
                        "domain-reviewer worker for `{}` must use role_id `{expected_role}`",
                        expected_role.trim_start_matches("domain:")
                    ));
                }
            }
            _ => {}
        }
    }

    domain_modules.sort_unstable();
    domain_modules.dedup();
    if domain_modules != canonical_modules {
        errors.push(
            "review and full-cycle routes must include exactly one domain-reviewer per canonical module"
                .to_string(),
        );
    }
}

fn validate_route_decision(artifact: &RouteDecisionArtifact, errors: &mut Vec<String>) {
    if let Err(err) = validate_header(&artifact.header, ArtifactKind::RouteDecision) {
        errors.push(err.to_string());
    }
    if !artifact
        .selected_modules
        .contains(&ModuleId::CoreCorrectness)
    {
        errors.push("selected_modules must include core-correctness".to_string());
    }
    if !artifact.selected_modules.contains(&ModuleId::ShipReadiness) {
        errors.push("selected_modules must include ship-readiness".to_string());
    }
    if artifact.mode == crate::artifacts::Mode::Applicator
        && artifact.resource_budget.planned_worker_count > artifact.resource_budget.max_worker_count
    {
        errors.push("planned_worker_count must not exceed max_worker_count".to_string());
    }
    if usize::from(artifact.resource_budget.planned_worker_count) != artifact.worker_plan.len() {
        errors.push("planned_worker_count must match worker_plan length".to_string());
    }
    if artifact.mode == crate::artifacts::Mode::Applicator {
        if artifact.execution_architecture == crate::artifacts::ExecutionArchitecture::Direct {
            if artifact.worker_plan.len() != 1 {
                errors
                    .push("direct applicator architecture must use exactly one worker".to_string());
            } else if let Some(only_worker) = artifact.worker_plan.first() {
                if only_worker.worker_kind != crate::artifacts::WorkerKind::ApplyComposite {
                    errors.push(
                        "direct applicator architecture must use apply-composite".to_string(),
                    );
                }
            }
        } else {
            let worker_kinds = artifact
                .worker_plan
                .iter()
                .map(|worker| worker.worker_kind)
                .collect::<Vec<_>>();
            if worker_kinds
                != vec![
                    crate::artifacts::WorkerKind::ApplicatorWorker,
                    crate::artifacts::WorkerKind::ApplicatorVerifier,
                ]
            {
                errors.push(
                    "non-direct applicator routes must use applicator-worker and applicator-verifier"
                        .to_string(),
                );
            }
        }
    } else {
        validate_recursive_review_roster(artifact, errors);
    }
    for surface in &artifact.risk_surfaces {
        if !(1..=5).contains(&surface.weight) {
            errors.push(format!(
                "surface `{}` weight {} is outside 1..=5",
                toml::Value::try_from(surface.surface_id).map_or_else(
                    |_| "unknown".to_string(),
                    |value| value.to_string().trim_matches('"').to_string()
                ),
                surface.weight
            ));
        }
        validate_repo_paths(&surface.evidence_refs, errors);
    }
}

fn validate_surface_map(artifact: &SurfaceMapArtifact, errors: &mut Vec<String>) {
    if let Err(err) = validate_header(&artifact.header, ArtifactKind::SurfaceMap) {
        errors.push(err.to_string());
    }
    validate_repo_paths(&artifact.changed_files, errors);
    validate_repo_paths(&artifact.public_interfaces, errors);
    validate_repo_paths(&artifact.behavior_facing_artifacts, errors);
    for surface in &artifact.risk_surfaces {
        if !(1..=5).contains(&surface.weight) {
            errors.push(format!(
                "surface `{}` has invalid weight {}",
                surface.reason, surface.weight
            ));
        }
        validate_repo_paths(&surface.evidence_refs, errors);
    }
    if artifact.staleness_required
        && !artifact
            .suggested_modules
            .contains(&ModuleId::DocsStaleness)
    {
        errors.push(
            "staleness_required=true must include docs-staleness in suggested_modules".to_string(),
        );
    }
}

fn validate_child_findings(
    artifact: &ChildFindingsArtifact,
    session_dir: Option<&Path>,
    errors: &mut Vec<String>,
) {
    if let Err(err) = validate_header(&artifact.header, ArtifactKind::ChildFindings) {
        errors.push(err.to_string());
    }
    validate_findings(&artifact.findings, errors);
    for check in &artifact.defended_checks {
        for anchor in &check.anchors {
            if let Err(err) = validate_anchor(anchor) {
                errors.push(err.to_string());
            }
        }
        if let Err(err) = validate_confidence(check.confidence_label, check.confidence_score) {
            errors.push(err.to_string());
        }
    }
    for risk in &artifact.residual_risks {
        if let Err(err) = validate_confidence(risk.confidence_label, risk.confidence_score) {
            errors.push(err.to_string());
        }
    }
    validate_artifact_refs(&artifact.route_revision_refs, session_dir, errors);
}

fn validate_parent_review(
    artifact: &ParentReviewArtifact,
    session_dir: Option<&Path>,
    errors: &mut Vec<String>,
) {
    if let Err(err) = validate_header(&artifact.header, ArtifactKind::ParentReview) {
        errors.push(err.to_string());
    }
    validate_artifact_refs(&artifact.source_artifact_ids, session_dir, errors);
    validate_findings(&artifact.required_now, errors);
    validate_findings(&artifact.follow_up, errors);
    validate_coverage(&artifact.coverage_summary, errors);
    if artifact.ship_readiness.required_now_count != artifact.required_now.len() {
        errors.push("ship_readiness.required_now_count must match required_now length".to_string());
    }
    if artifact.ship_readiness.follow_up_count != artifact.follow_up.len() {
        errors.push("ship_readiness.follow_up_count must match follow_up length".to_string());
    }
}

fn validate_application_result(artifact: &ApplicationResultArtifact, errors: &mut Vec<String>) {
    if let Err(err) = validate_header(&artifact.header, ArtifactKind::ApplicationResult) {
        errors.push(err.to_string());
    }
    validate_repo_paths(&artifact.modified_files, errors);
    let mut expected_decline_codes = artifact
        .dispositions
        .iter()
        .filter_map(|disposition| disposition.decline_reason_code)
        .collect::<Vec<_>>();
    expected_decline_codes.sort_unstable();
    let mut actual_decline_codes = artifact.decline_codes.clone();
    actual_decline_codes.sort_unstable();
    if expected_decline_codes != actual_decline_codes {
        errors.push(
            "decline_codes must match the decline_reason_code values present in dispositions"
                .to_string(),
        );
    }
    let expected_verification_needed = artifact
        .dispositions
        .iter()
        .filter(|disposition| disposition.verification_needed)
        .map(|disposition| disposition.finding_id.clone())
        .collect::<Vec<_>>();
    if expected_verification_needed != artifact.verification_needed {
        errors.push(
            "verification_needed must list exactly the dispositions marked verification_needed"
                .to_string(),
        );
    }
}

fn validate_verification_result(artifact: &VerificationResultArtifact, errors: &mut Vec<String>) {
    if let Err(err) = validate_header(&artifact.header, ArtifactKind::VerificationResult) {
        errors.push(err.to_string());
    }
    for item in &artifact.verified_items {
        if item.status != crate::artifacts::VerificationStatus::Yes {
            errors.push(format!(
                "verified_items entry `{}` must use status `yes`",
                item.finding_id
            ));
        }
    }
    for item in &artifact.failed_items {
        if item.status != crate::artifacts::VerificationStatus::No {
            errors.push(format!(
                "failed_items entry `{}` must use status `no`",
                item.finding_id
            ));
        }
    }
    for item in &artifact.partial_items {
        if item.status != crate::artifacts::VerificationStatus::Partial {
            errors.push(format!(
                "partial_items entry `{}` must use status `partial`",
                item.finding_id
            ));
        }
    }
}

fn validate_convergence_state(
    artifact: &ConvergenceStateArtifact,
    session_dir: Option<&Path>,
    errors: &mut Vec<String>,
) {
    if let Err(err) = validate_header(&artifact.header, ArtifactKind::ConvergenceState) {
        errors.push(err.to_string());
    }
    if artifact.reopen_threshold.severity_floor != crate::artifacts::Severity::Major {
        errors
            .push("convergence_state.reopen_threshold.severity_floor must be `major`".to_string());
    }
    if !artifact.reopen_threshold.behavior_staleness_reopens {
        errors.push(
            "convergence_state.reopen_threshold.behavior_staleness_reopens must be true"
                .to_string(),
        );
    }
    if artifact.stop_condition.trim().is_empty() {
        errors.push("convergence_state.stop_condition must not be empty".to_string());
    }
    let _ = session_dir;
    for trigger in &artifact.reopen_triggers {
        if trigger.reference_id.trim().is_empty() {
            errors.push(
                "convergence_state.reopen_triggers[].reference_id must not be empty".to_string(),
            );
        }
    }
}

fn validate_route_revision(
    artifact: &RouteRevisionArtifact,
    session_dir: Option<&Path>,
    errors: &mut Vec<String>,
) {
    if let Err(err) = validate_header(&artifact.header, ArtifactKind::RouteRevision) {
        errors.push(err.to_string());
    }
    validate_artifact_refs(
        std::slice::from_ref(&artifact.source_artifact_id),
        session_dir,
        errors,
    );
    if artifact.reason_code.trim().is_empty() {
        errors.push("route_revision.reason_code must not be empty".to_string());
    }
}

fn check_heading_order(markdown: &str, headings: &[&str], warnings: &mut Vec<String>) {
    let mut last_index = 0usize;
    for heading in headings {
        match markdown.find(heading) {
            Some(index) if index >= last_index => last_index = index,
            Some(_) => warnings.push(format!("heading order warning for `{heading}`")),
            None => warnings.push(format!("missing heading `{heading}`")),
        }
    }
}

fn soft_validate_document(artifact: &ArtifactDocument, warnings: &mut Vec<String>) {
    let markdown = match render_artifact_markdown(artifact) {
        Ok(markdown) => markdown,
        Err(err) => {
            warnings.push(format!("render warning: {err}"));
            return;
        }
    };
    match artifact {
        ArtifactDocument::ParentReview(parent_review) => {
            check_heading_order(
                &markdown,
                &[
                    "# Parent Review",
                    "## Verdict",
                    "## Ship Readiness",
                    "## Required Now",
                    "## Follow Up",
                    "## Defended Summary",
                    "## Residual Risks",
                    "## Coverage Summary",
                ],
                warnings,
            );
            if parent_review.coverage_summary.changed_files.is_empty() {
                warnings.push("coverage_summary.changed_files is empty".to_string());
            }
        }
        ArtifactDocument::ApplicationResult(_) => {
            check_heading_order(
                &markdown,
                &[
                    "# Application Result",
                    "## Dispositions",
                    "## Modified Files",
                    "## Verification Needed",
                    "## Decline Codes",
                ],
                warnings,
            );
        }
        ArtifactDocument::VerificationResult(_) => {
            check_heading_order(
                &markdown,
                &[
                    "# Verification Result",
                    "## Verified Items",
                    "## Failed Items",
                    "## Partial Items",
                    "## Residual Risks",
                ],
                warnings,
            );
        }
        _ => {}
    }
    if markdown.lines().any(|line| line.len() > 140) {
        warnings.push("rendered markdown exceeds the soft 140-character line budget".to_string());
    }
}

/// Validate a typed artifact at the requested layer.
///
/// # Errors
/// Returns an error only if validation cannot run.
pub fn validate_artifact_document(
    artifact: &ArtifactDocument,
    layer: ValidationLayer,
    session_dir: Option<&Path>,
) -> anyhow::Result<ValidationSummary> {
    let mut errors = Vec::new();
    let mut warnings = Vec::new();
    match layer {
        ValidationLayer::Hard => match artifact {
            ArtifactDocument::RouteDecision(artifact) => {
                validate_route_decision(artifact, &mut errors)
            }
            ArtifactDocument::SurfaceMap(artifact) => validate_surface_map(artifact, &mut errors),
            ArtifactDocument::ChildFindings(artifact) => {
                validate_child_findings(artifact, session_dir, &mut errors)
            }
            ArtifactDocument::ParentReview(artifact) => {
                validate_parent_review(artifact, session_dir, &mut errors)
            }
            ArtifactDocument::ApplicationResult(artifact) => {
                validate_application_result(artifact, &mut errors)
            }
            ArtifactDocument::VerificationResult(artifact) => {
                validate_verification_result(artifact, &mut errors)
            }
            ArtifactDocument::ConvergenceState(artifact) => {
                validate_convergence_state(artifact, session_dir, &mut errors)
            }
            ArtifactDocument::RouteRevision(artifact) => {
                validate_route_revision(artifact, session_dir, &mut errors)
            }
        },
        ValidationLayer::Soft => soft_validate_document(artifact, &mut warnings),
    }
    Ok(ValidationSummary {
        artifact_kind: artifact.kind(),
        layer,
        errors,
        warnings,
    })
}

/// Parse and validate an artifact file.
pub fn validate_artifact_file(
    artifact_file: &Path,
    expected_kind: ArtifactKind,
    layer: ValidationLayer,
    session_dir_override: Option<&Path>,
) -> anyhow::Result<ValidationSummary> {
    let artifact = parse_artifact_file(artifact_file)?;
    anyhow::ensure!(
        artifact.kind() == expected_kind,
        "error: artifact kind `{}` did not match `{:?}`",
        artifact.kind(),
        expected_kind
    );
    let derived_session_dir = artifact_file
        .parent()
        .and_then(Path::parent)
        .and_then(Path::parent)
        .filter(|candidate| {
            candidate.join("_session.json").exists() || candidate.join("_session.toml").exists()
        });
    let session_dir = session_dir_override.or(derived_session_dir);
    validate_artifact_document(&artifact, layer, session_dir)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::artifacts::{
        ArtifactHeader, ArtifactKind, CapabilityProfile, ConfidenceLabel, CoverageSummary,
        ExecutionArchitecture, ExecutionCapability, Mode, PolicyCategory, PolicyRef, PolicyView,
        ProducerKind, ResourceBudget, ReviewVerdict, RiskSurfaceRecord, ShipReadinessSummary,
        ShipReadinessVerdict, SurfaceId, WorkerKind, WorkerPlanRecord,
    };
    use anyhow::ensure;

    fn header(kind: ArtifactKind) -> anyhow::Result<ArtifactHeader> {
        ArtifactHeader::new(
            kind,
            "abc123def456".to_string(),
            "sess0001".to_string(),
            "refs/heads/main".to_string(),
            ProducerKind::Validator,
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
    fn hard_validation_blocks_incomplete_recursive_review_route() -> anyhow::Result<()> {
        let artifact = ArtifactDocument::RouteDecision(RouteDecisionArtifact {
            header: header(ArtifactKind::RouteDecision)?,
            mode: Mode::Reviewer,
            execution_architecture: ExecutionArchitecture::Direct,
            rigor_level: crate::artifacts::RigorLevel::Lite,
            capability_profile: CapabilityProfile {
                execution_capability: ExecutionCapability::SingleProcess,
                max_worker_count: 1,
                orchestrator_read_budget_lines: 80,
                orchestrator_read_budget_snippets: 6,
            },
            resource_budget: ResourceBudget {
                planned_worker_count: 0,
                max_worker_count: 1,
            },
            risk_surfaces: Vec::new(),
            selected_modules: vec![ModuleId::ShipReadiness],
            worker_plan: Vec::new(),
            heldback_escalations: Vec::new(),
            stop_conditions: Vec::new(),
        });
        let summary = validate_artifact_document(&artifact, ValidationLayer::Hard, None)?;
        ensure!(!summary.errors.is_empty());
        Ok(())
    }

    #[test]
    fn hard_validation_accepts_recursive_review_roster_above_budget() -> anyhow::Result<()> {
        let selected_modules = canonical_review_modules();
        let mut worker_plan = vec![WorkerPlanRecord {
            worker_kind: WorkerKind::LanguageDetector,
            role_id: Some("language-detector".to_string()),
            language: None,
            module_ids: Vec::new(),
            focus_surfaces: vec![SurfaceId::PublicApi],
            claimed_scope: vec!["infer changed-file languages".to_string()],
            delegated_scope: Vec::new(),
            required: true,
            parallelizable: false,
        }];
        for module_id in &selected_modules {
            worker_plan.push(WorkerPlanRecord {
                worker_kind: WorkerKind::DomainReviewer,
                role_id: Some(format!(
                    "domain:{}",
                    toml::Value::try_from(*module_id).map_or_else(
                        |_| "unknown".to_string(),
                        |value| value.to_string().trim_matches('"').to_string()
                    )
                )),
                language: None,
                module_ids: vec![*module_id],
                focus_surfaces: vec![SurfaceId::PublicApi],
                claimed_scope: vec!["own assigned domain".to_string()],
                delegated_scope: vec![
                    "do not delegate the same domain investigation again".to_string()
                ],
                required: true,
                parallelizable: false,
            });
        }
        worker_plan.push(WorkerPlanRecord {
            worker_kind: WorkerKind::FinalSynthesizer,
            role_id: Some("final-synthesis".to_string()),
            language: None,
            module_ids: vec![ModuleId::ShipReadiness],
            focus_surfaces: vec![SurfaceId::PublicApi],
            claimed_scope: vec!["synthesize descendant reports".to_string()],
            delegated_scope: vec!["do not reopen low-signal duplicate findings".to_string()],
            required: true,
            parallelizable: false,
        });

        let artifact = ArtifactDocument::RouteDecision(RouteDecisionArtifact {
            header: header(ArtifactKind::RouteDecision)?,
            mode: Mode::Reviewer,
            execution_architecture: ExecutionArchitecture::Direct,
            rigor_level: crate::artifacts::RigorLevel::Lite,
            capability_profile: CapabilityProfile {
                execution_capability: ExecutionCapability::SingleProcess,
                max_worker_count: 1,
                orchestrator_read_budget_lines: 80,
                orchestrator_read_budget_snippets: 6,
            },
            resource_budget: ResourceBudget {
                planned_worker_count: u8::try_from(worker_plan.len())?,
                max_worker_count: 1,
            },
            risk_surfaces: vec![RiskSurfaceRecord {
                surface_id: SurfaceId::PublicApi,
                weight: 5,
                reason: "api".to_string(),
                evidence_refs: vec!["src/api.rs".to_string()],
                behavior_facing: true,
            }],
            selected_modules,
            worker_plan,
            heldback_escalations: Vec::new(),
            stop_conditions: Vec::new(),
        });
        let summary = validate_artifact_document(&artifact, ValidationLayer::Hard, None)?;
        ensure!(summary.errors.is_empty());
        Ok(())
    }

    #[test]
    fn soft_validation_warns_only() -> anyhow::Result<()> {
        let artifact = ArtifactDocument::ParentReview(ParentReviewArtifact {
            header: header(ArtifactKind::ParentReview)?,
            source_artifact_ids: Vec::new(),
            final_verdict: ReviewVerdict::Approve,
            ship_readiness: ShipReadinessSummary {
                verdict: ShipReadinessVerdict::Ship,
                axes: Vec::new(),
                blocking_items: Vec::new(),
                required_now_count: 0,
                follow_up_count: 0,
            },
            required_now: Vec::new(),
            follow_up: Vec::new(),
            defended_summary: Vec::new(),
            residual_risks: Vec::new(),
            coverage_summary: CoverageSummary {
                changed_files: Vec::new(),
                surfaces_covered: vec![SurfaceId::PublicApi],
                modules_loaded: vec![ModuleId::CoreCorrectness],
                tests_run: Vec::new(),
                tests_not_run_reason: Some("not run".to_string()),
                limitations: Vec::new(),
            },
        });
        let summary = validate_artifact_document(&artifact, ValidationLayer::Soft, None)?;
        ensure!(summary.errors.is_empty());
        ensure!(!summary.warnings.is_empty());
        Ok(())
    }

    #[test]
    fn hard_validation_rejects_non_direct_applicator_review_workers() -> anyhow::Result<()> {
        let artifact = ArtifactDocument::RouteDecision(RouteDecisionArtifact {
            header: header(ArtifactKind::RouteDecision)?,
            mode: Mode::Applicator,
            execution_architecture: ExecutionArchitecture::Hybrid,
            rigor_level: crate::artifacts::RigorLevel::Standard,
            capability_profile: CapabilityProfile {
                execution_capability: ExecutionCapability::BoundedHelpers,
                max_worker_count: 3,
                orchestrator_read_budget_lines: 80,
                orchestrator_read_budget_snippets: 6,
            },
            resource_budget: ResourceBudget {
                planned_worker_count: 2,
                max_worker_count: 3,
            },
            risk_surfaces: vec![RiskSurfaceRecord {
                surface_id: SurfaceId::AuthAccess,
                weight: 5,
                reason: "auth".to_string(),
                evidence_refs: vec!["src/auth.rs".to_string()],
                behavior_facing: false,
            }],
            selected_modules: vec![ModuleId::CoreCorrectness, ModuleId::ShipReadiness],
            worker_plan: vec![
                WorkerPlanRecord {
                    worker_kind: WorkerKind::SurfaceMapper,
                    role_id: None,
                    language: None,
                    module_ids: Vec::new(),
                    focus_surfaces: vec![SurfaceId::AuthAccess],
                    claimed_scope: Vec::new(),
                    delegated_scope: Vec::new(),
                    required: true,
                    parallelizable: false,
                },
                WorkerPlanRecord {
                    worker_kind: WorkerKind::ReleaseRiskAssessor,
                    role_id: None,
                    language: None,
                    module_ids: vec![ModuleId::ShipReadiness],
                    focus_surfaces: vec![SurfaceId::AuthAccess],
                    claimed_scope: Vec::new(),
                    delegated_scope: Vec::new(),
                    required: true,
                    parallelizable: false,
                },
            ],
            heldback_escalations: Vec::new(),
            stop_conditions: Vec::new(),
        });
        let summary = validate_artifact_document(&artifact, ValidationLayer::Hard, None)?;
        ensure!(!summary.errors.is_empty());
        Ok(())
    }
}
