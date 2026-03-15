//! Hard and soft validation for canonical v2 artifacts.
#![allow(missing_docs)]

use crate::artifacts::{
    parse_artifact_file, validate_anchor, validate_artifact_id, validate_confidence,
    validate_created_at, validate_finding_identity, validate_session_id, ApplicationResultArtifact,
    ArtifactDocument, ArtifactHeader, ArtifactKind, ChildFindingsArtifact,
    ConvergenceStateArtifact, CoverageSummary, Disposition, FindingRecord, ModuleId,
    ParentReviewArtifact, RouteDecisionArtifact, RouteRevisionArtifact, Severity,
    SurfaceMapArtifact, VerificationResultArtifact,
};
use crate::render::render_artifact_markdown;
use crate::session::{load_session, SessionLocator};
use serde::Serialize;
use std::collections::{BTreeMap, BTreeSet};
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
        if let Err(err) = crate::paths::validate_repo_relative_str(path) {
            errors.push(format!("repo-relative path `{path}` is invalid: {err}"));
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

fn soft_validate_findings(findings: &[FindingRecord], warnings: &mut Vec<String>) {
    for finding in findings {
        if !matches!(
            finding.severity,
            crate::artifacts::Severity::Blocker | crate::artifacts::Severity::Major
        ) {
            continue;
        }
        if finding.evidence_strength.is_none() {
            warnings.push(format!(
                "high-severity finding `{}` is missing evidence_strength",
                finding.finding_id
            ));
        }
        if finding.false_positive_risk.is_none() {
            warnings.push(format!(
                "high-severity finding `{}` is missing false_positive_risk",
                finding.finding_id
            ));
        }
        if finding.actionable.is_none() {
            warnings.push(format!(
                "high-severity finding `{}` is missing actionable",
                finding.finding_id
            ));
        }
        if finding.duplicate_suspect == Some(true) {
            warnings.push(format!(
                "high-severity finding `{}` is marked duplicate_suspect=true",
                finding.finding_id
            ));
        }
        if finding.false_positive_risk == Some(crate::artifacts::ConfidenceLabel::High) {
            warnings.push(format!(
                "high-severity finding `{}` carries false_positive_risk=high",
                finding.finding_id
            ));
        }
        if finding.evidence_strength == Some(crate::artifacts::ConfidenceLabel::Low) {
            warnings.push(format!(
                "high-severity finding `{}` carries evidence_strength=low",
                finding.finding_id
            ));
        }
    }
}

fn current_parent_review_findings(
    session_dir: &Path,
) -> anyhow::Result<BTreeMap<String, FindingRecord>> {
    let locator = SessionLocator::from_session_dir(session_dir.to_path_buf());
    let session = load_session(&locator)?;
    let Some(pointer) = session.current.parent_review.as_ref() else {
        return Ok(BTreeMap::new());
    };
    let repo_root = std::path::PathBuf::from(&session.repo_root);
    let mut resolved = None;
    for candidate in [
        pointer.json_path.as_deref(),
        Some(pointer.path.as_str()),
        pointer.toml_path.as_deref(),
    ] {
        let Some(candidate) = candidate else {
            continue;
        };
        let Ok(path) = crate::paths::resolve_repo_relative(&repo_root, candidate) else {
            continue;
        };
        if path.exists() {
            resolved = Some(path);
            break;
        }
    }
    let Some(path) = resolved else {
        return Ok(BTreeMap::new());
    };
    let ArtifactDocument::ParentReview(parent_review) = parse_artifact_file(&path)? else {
        return Ok(BTreeMap::new());
    };
    let mut findings = BTreeMap::new();
    for finding in parent_review
        .required_now
        .into_iter()
        .chain(parent_review.follow_up.into_iter())
    {
        findings.insert(finding.finding_id.clone(), finding);
    }
    Ok(findings)
}

fn soft_validate_application_result(
    artifact: &ApplicationResultArtifact,
    session_dir: Option<&Path>,
    warnings: &mut Vec<String>,
) {
    let disposition_ids = artifact
        .dispositions
        .iter()
        .map(|disposition| disposition.finding_id.as_str())
        .collect::<Vec<_>>();
    let unique_disposition_ids = disposition_ids.iter().copied().collect::<BTreeSet<_>>();
    if unique_disposition_ids.len() != disposition_ids.len() {
        warnings.push(
            "application_result contains duplicate disposition finding_id values".to_string(),
        );
    }

    let source_ids = artifact
        .source_finding_ids
        .iter()
        .map(String::as_str)
        .collect::<BTreeSet<_>>();
    let missing = source_ids
        .iter()
        .filter(|finding_id| !unique_disposition_ids.contains(**finding_id))
        .copied()
        .collect::<Vec<_>>();
    if !missing.is_empty() {
        warnings.push(format!(
            "application_result is missing dispositions for source findings: {}",
            missing.join(", ")
        ));
    }

    for disposition in &artifact.dispositions {
        if disposition.detail.trim().len() < 12 {
            warnings.push(format!(
                "disposition `{}` detail is too terse to explain the decision",
                disposition.finding_id
            ));
        }
        if matches!(
            disposition.disposition,
            Disposition::Declined | Disposition::AlreadyAddressed
        ) && disposition.decline_reason_code.is_none()
        {
            warnings.push(format!(
                "disposition `{}` is `{}` but decline_reason_code is missing",
                disposition.finding_id,
                toml::Value::try_from(disposition.disposition)
                    .map_or_else(|_| "unknown".to_string(), |value| value.to_string())
                    .trim_matches('"')
            ));
        }
        if (disposition.duplicate_suspect == Some(true)
            || disposition.decline_reason_code
                == Some(crate::artifacts::DeclineReasonCode::Duplicate))
            && disposition.duplicate_reason_code.is_none()
        {
            warnings.push(format!(
                "disposition `{}` suggests a duplicate outcome but duplicate_reason_code is missing",
                disposition.finding_id
            ));
        }
        if disposition.verification_needed && disposition.stop_recommendation.is_none() {
            warnings.push(format!(
                "disposition `{}` requires verification but stop_recommendation is missing",
                disposition.finding_id
            ));
        }
        if disposition.disposition == Disposition::Applied && disposition.tracking_ref.is_none() {
            warnings.push(format!(
                "applied disposition `{}` is missing tracking_ref",
                disposition.finding_id
            ));
        }
    }

    let Some(session_dir) = session_dir else {
        return;
    };
    let Ok(parent_findings) = current_parent_review_findings(session_dir) else {
        return;
    };
    for disposition in &artifact.dispositions {
        let Some(source) = parent_findings.get(&disposition.finding_id) else {
            continue;
        };
        if !matches!(source.severity, Severity::Blocker | Severity::Major) {
            continue;
        }
        if disposition.evidence_strength.is_none() {
            warnings.push(format!(
                "high-severity source finding `{}` is missing disposition evidence_strength",
                disposition.finding_id
            ));
        }
        if disposition.false_positive_risk.is_none() {
            warnings.push(format!(
                "high-severity source finding `{}` is missing disposition false_positive_risk",
                disposition.finding_id
            ));
        }
        if disposition.duplicate_suspect.is_none() {
            warnings.push(format!(
                "high-severity source finding `{}` is missing disposition duplicate_suspect",
                disposition.finding_id
            ));
        }
        if disposition.stop_recommendation.is_none() {
            warnings.push(format!(
                "high-severity source finding `{}` is missing disposition stop_recommendation",
                disposition.finding_id
            ));
        }
        if matches!(
            disposition.disposition,
            Disposition::Declined | Disposition::AlreadyAddressed
        ) && disposition.detail.trim().split_whitespace().count() < 4
        {
            warnings.push(format!(
                "high-severity source finding `{}` has a decline/already-addressed detail that is too thin",
                disposition.finding_id
            ));
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
    let disposition_ids = artifact
        .dispositions
        .iter()
        .map(|disposition| disposition.finding_id.clone())
        .collect::<Vec<_>>();
    let unique_disposition_ids = disposition_ids.iter().cloned().collect::<BTreeSet<_>>();
    if unique_disposition_ids.len() != disposition_ids.len() {
        errors.push("dispositions must not contain duplicate finding_id values".to_string());
    }
    let source_ids = artifact
        .source_finding_ids
        .iter()
        .cloned()
        .collect::<BTreeSet<_>>();
    if source_ids != unique_disposition_ids {
        errors.push(
            "source_finding_ids must match the finding_id values present in dispositions"
                .to_string(),
        );
    }
}

fn validate_verification_result(
    artifact: &VerificationResultArtifact,
    session_dir: Option<&Path>,
    errors: &mut Vec<String>,
) {
    if let Err(err) = validate_header(&artifact.header, ArtifactKind::VerificationResult) {
        errors.push(err.to_string());
    }
    let verification_ids = artifact
        .verified_items
        .iter()
        .chain(&artifact.failed_items)
        .chain(&artifact.partial_items)
        .map(|item| item.finding_id.clone())
        .collect::<Vec<_>>();
    let unique_verification_ids = verification_ids.iter().cloned().collect::<BTreeSet<_>>();
    if unique_verification_ids.len() != verification_ids.len() {
        errors.push(
            "verification_result finding_ids must be unique across verified_items, failed_items, and partial_items"
                .to_string(),
        );
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
    if let Some(session_dir) = session_dir {
        match load_session(&SessionLocator::from_session_dir(session_dir.to_path_buf())) {
            Ok(session) => {
                let expected_ids = match resolve_application_verification_ids(
                    &session,
                    session_dir,
                    &unique_verification_ids,
                ) {
                    Ok(expected_ids) => expected_ids,
                    Err(err) => {
                        errors.push(err);
                        return;
                    }
                };
                if unique_verification_ids != expected_ids {
                    errors.push(format!(
                        "verification_result finding_ids {:?} did not match application_result.verification_needed {:?}",
                        unique_verification_ids.into_iter().collect::<Vec<_>>(),
                        expected_ids.into_iter().collect::<Vec<_>>()
                    ));
                }
            }
            Err(err) => {
                errors.push(format!(
                    "session-aware verification validation failed: {err}"
                ));
            }
        }
    }
}

fn resolve_application_verification_ids(
    _session: &crate::session::SessionLedger,
    session_dir: &Path,
    verification_ids: &BTreeSet<String>,
) -> Result<BTreeSet<String>, String> {
    let Some(current_pointer) = _session.current.application_result.as_ref() else {
        return Err(
            "verification_result requires a finalized application_result in the session store"
                .to_string(),
        );
    };

    let current_result = load_application_result_by_pointer(session_dir, current_pointer)
        .map_err(|err| format!("current application_result pointer could not be parsed: {err}"))?;
    let current_ids = verification_needed_ids(&current_result);
    if &current_ids == verification_ids {
        return Ok(current_ids);
    }

    let mut matched_ids = None;
    let mut saw_application_result = false;
    let mut application_result_count = 0usize;
    for pointer in &_session.artifacts {
        if pointer.artifact_kind != ArtifactKind::ApplicationResult {
            continue;
        }
        saw_application_result = true;
        application_result_count += 1;
        let application_result =
            load_application_result_by_pointer(session_dir, pointer).map_err(|err| {
                format!(
                    "application_result artifact `{}` could not be parsed: {err}",
                    pointer.artifact_id
                )
            })?;
        let candidate_ids = verification_needed_ids(&application_result);
        if &candidate_ids != verification_ids {
            continue;
        }
        match &matched_ids {
            Some(existing) if existing != &candidate_ids => {}
            _ => matched_ids = Some(candidate_ids),
        }
    }

    if let Some(matched_ids) = matched_ids {
        Ok(matched_ids)
    } else if application_result_count <= 1 {
        Err(format!(
            "verification_result finding_ids {:?} did not match application_result.verification_needed {:?}",
            verification_ids.iter().cloned().collect::<Vec<_>>(),
            current_ids.into_iter().collect::<Vec<_>>()
        ))
    } else if saw_application_result {
        Err(format!(
            "verification_result finding_ids {:?} did not match any application_result.verification_needed in the session store",
            verification_ids.iter().cloned().collect::<Vec<_>>()
        ))
    } else {
        Err(
            "verification_result requires a finalized application_result in the session store"
                .to_string(),
        )
    }
}

fn load_application_result_by_pointer(
    session_dir: &Path,
    pointer: &crate::session::ArtifactPointer,
) -> anyhow::Result<ApplicationResultArtifact> {
    let application_path = crate::paths::existing_artifact_path(
        session_dir,
        ArtifactKind::ApplicationResult,
        &pointer.artifact_id,
    )
    .ok_or_else(|| {
        anyhow::anyhow!(
            "artifact `{}` was not found in the session store",
            pointer.artifact_id
        )
    })?;

    match parse_artifact_file(&application_path)? {
        ArtifactDocument::ApplicationResult(application_result) => Ok(application_result),
        _ => Err(anyhow::anyhow!(
            "artifact `{}` did not resolve to an application_result artifact",
            pointer.artifact_id
        )),
    }
}

fn verification_needed_ids(application_result: &ApplicationResultArtifact) -> BTreeSet<String> {
    application_result
        .verification_needed
        .iter()
        .cloned()
        .collect::<BTreeSet<_>>()
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

fn soft_validate_document(
    artifact: &ArtifactDocument,
    session_dir: Option<&Path>,
    warnings: &mut Vec<String>,
) {
    let markdown = match render_artifact_markdown(artifact) {
        Ok(markdown) => markdown,
        Err(err) => {
            warnings.push(format!("render warning: {err}"));
            return;
        }
    };
    match artifact {
        ArtifactDocument::ChildFindings(child_findings) => {
            soft_validate_findings(&child_findings.findings, warnings);
        }
        ArtifactDocument::ParentReview(parent_review) => {
            soft_validate_findings(&parent_review.required_now, warnings);
            soft_validate_findings(&parent_review.follow_up, warnings);
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
        ArtifactDocument::ApplicationResult(application_result) => {
            soft_validate_application_result(application_result, session_dir, warnings);
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
                validate_verification_result(artifact, session_dir, &mut errors)
            }
            ArtifactDocument::ConvergenceState(artifact) => {
                validate_convergence_state(artifact, session_dir, &mut errors)
            }
            ArtifactDocument::RouteRevision(artifact) => {
                validate_route_revision(artifact, session_dir, &mut errors)
            }
        },
        ValidationLayer::Soft => soft_validate_document(artifact, session_dir, &mut warnings),
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
        compute_anchor_cluster, compute_fingerprint, ArtifactHeader, ArtifactKind,
        CapabilityProfile, ConfidenceLabel, CoverageSummary, Disposition, DispositionRecord,
        ExecutionArchitecture, ExecutionCapability, Mode, PolicyCategory, PolicyRef, PolicyView,
        ProducerKind, ResourceBudget, ReviewVerdict, RiskSurfaceRecord, ShipReadinessSummary,
        ShipReadinessVerdict, SurfaceId, WorkerKind, WorkerPlanRecord,
    };
    use crate::paths::session_paths;
    use crate::session::{
        finalize_application, finalize_review, register_reviewer, ApplicatorArtifactParams,
        RegisterReviewerParams, ReviewerArtifactParams, SessionLocator,
    };
    use anyhow::ensure;
    use std::fs;
    use tempfile::tempdir;
    use time::{Date, Month};

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
    fn soft_validation_warns_for_low_signal_major_findings() -> anyhow::Result<()> {
        let artifact = ArtifactDocument::ParentReview(ParentReviewArtifact {
            header: header(ArtifactKind::ParentReview)?,
            source_artifact_ids: Vec::new(),
            final_verdict: ReviewVerdict::RequestChanges,
            ship_readiness: ShipReadinessSummary {
                verdict: ShipReadinessVerdict::ShipWithFixes,
                axes: Vec::new(),
                blocking_items: vec!["major issue".to_string()],
                required_now_count: 1,
                follow_up_count: 0,
            },
            required_now: vec![FindingRecord {
                finding_id: "F300".to_string(),
                module_id: ModuleId::CoreCorrectness,
                surface_ids: vec![SurfaceId::PublicApi],
                severity: crate::artifacts::Severity::Major,
                title: "major issue".to_string(),
                claim: "major issue remains".to_string(),
                scenario: "major issue reproduced".to_string(),
                evidence: "major issue evidence".to_string(),
                recommendation: "fix it".to_string(),
                verification: "rerun tests".to_string(),
                anchors: vec!["src/lib.rs:30".to_string()],
                symbol_hint: None,
                anchor_cluster: "src/lib.rs".to_string(),
                fingerprint: "fp300".to_string(),
                reopen_eligible: true,
                confidence_label: ConfidenceLabel::High,
                confidence_score: 90,
                evidence_strength: Some(ConfidenceLabel::Low),
                false_positive_risk: Some(ConfidenceLabel::High),
                actionable: None,
                duplicate_suspect: Some(true),
            }],
            follow_up: Vec::new(),
            defended_summary: Vec::new(),
            residual_risks: Vec::new(),
            coverage_summary: CoverageSummary {
                changed_files: vec!["src/lib.rs".to_string()],
                surfaces_covered: vec![SurfaceId::PublicApi],
                modules_loaded: vec![ModuleId::CoreCorrectness],
                tests_run: Vec::new(),
                tests_not_run_reason: Some("not run".to_string()),
                limitations: Vec::new(),
            },
        });
        let summary = validate_artifact_document(&artifact, ValidationLayer::Soft, None)?;
        ensure!(summary.errors.is_empty());
        ensure!(summary
            .warnings
            .iter()
            .any(|warning| warning.contains("false_positive_risk=high")));
        ensure!(summary
            .warnings
            .iter()
            .any(|warning| warning.contains("duplicate_suspect=true")));
        ensure!(summary
            .warnings
            .iter()
            .any(|warning| warning.contains("evidence_strength=low")));
        Ok(())
    }

    #[test]
    fn hard_validation_rejects_application_result_mismatched_dispositions() -> anyhow::Result<()> {
        let artifact = ArtifactDocument::ApplicationResult(ApplicationResultArtifact {
            header: header(ArtifactKind::ApplicationResult)?,
            source_finding_ids: vec!["F001".to_string(), "F002".to_string()],
            dispositions: vec![DispositionRecord {
                finding_id: "F001".to_string(),
                disposition: Disposition::Applied,
                decline_reason_code: None,
                duplicate_reason_code: None,
                detail: "applied the fix with tests".to_string(),
                tracking_ref: Some("apply-001".to_string()),
                verification_needed: true,
                evidence_strength: Some(ConfidenceLabel::High),
                false_positive_risk: Some(ConfidenceLabel::Low),
                duplicate_suspect: Some(false),
                stop_recommendation: Some("continue_to_verification".to_string()),
            }],
            modified_files: vec!["src/lib.rs".to_string()],
            verification_needed: vec!["F001".to_string()],
            decline_codes: Vec::new(),
        });
        let summary = validate_artifact_document(&artifact, ValidationLayer::Hard, None)?;
        ensure!(summary
            .errors
            .iter()
            .any(|error| error.contains("source_finding_ids must match")));
        Ok(())
    }

    #[test]
    fn hard_validation_rejects_verification_result_without_application_result() -> anyhow::Result<()>
    {
        let repo_root = tempdir()?;
        let date = Date::from_calendar_date(2026, Month::March, 8)?;
        let session_dir = session_paths(repo_root.path(), date).session_dir;
        fs::create_dir_all(&session_dir)?;
        let locator = SessionLocator::from_session_dir(session_dir.clone());
        let registered = register_reviewer(RegisterReviewerParams {
            session: locator,
            target_ref: "refs/heads/main".to_string(),
            reviewer_id: Some("root0008".to_string()),
            role: Some("final-synthesis".to_string()),
            role_kind: None,
        })?;

        let artifact = ArtifactDocument::VerificationResult(VerificationResultArtifact {
            header: ArtifactHeader::new(
                ArtifactKind::VerificationResult,
                "abc001def234".to_string(),
                registered.session_id,
                "refs/heads/main".to_string(),
                ProducerKind::ApplicatorVerifier,
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
            verified_items: vec![crate::artifacts::VerificationItemRecord {
                finding_id: "F001".to_string(),
                status: crate::artifacts::VerificationStatus::Yes,
                notes: "verified".to_string(),
            }],
            failed_items: Vec::new(),
            partial_items: Vec::new(),
            residual_risks: Vec::new(),
        });
        let summary =
            validate_artifact_document(&artifact, ValidationLayer::Hard, Some(&session_dir))?;
        ensure!(summary
            .errors
            .iter()
            .any(|error| error.contains("requires a finalized application_result")));
        Ok(())
    }

    #[test]
    fn hard_validation_rejects_verification_result_ids_outside_application_result(
    ) -> anyhow::Result<()> {
        let repo_root = tempdir()?;
        let date = Date::from_calendar_date(2026, Month::March, 8)?;
        let session_dir = session_paths(repo_root.path(), date).session_dir;
        fs::create_dir_all(&session_dir)?;
        let locator = SessionLocator::from_session_dir(session_dir.clone());
        let registered = register_reviewer(RegisterReviewerParams {
            session: locator.clone(),
            target_ref: "refs/heads/main".to_string(),
            reviewer_id: Some("root0009".to_string()),
            role: Some("final-synthesis".to_string()),
            role_kind: None,
        })?;

        let application_result = ArtifactDocument::ApplicationResult(ApplicationResultArtifact {
            header: ArtifactHeader::new(
                ArtifactKind::ApplicationResult,
                "abc001abc234".to_string(),
                registered.session_id.clone(),
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
            dispositions: vec![DispositionRecord {
                finding_id: "F001".to_string(),
                disposition: Disposition::Applied,
                decline_reason_code: None,
                duplicate_reason_code: None,
                detail: "applied".to_string(),
                tracking_ref: Some("apply-001".to_string()),
                verification_needed: true,
                evidence_strength: Some(ConfidenceLabel::High),
                false_positive_risk: Some(ConfidenceLabel::Low),
                duplicate_suspect: Some(false),
                stop_recommendation: Some("continue_to_verification".to_string()),
            }],
            modified_files: vec!["src/lib.rs".to_string()],
            verification_needed: vec!["F001".to_string()],
            decline_codes: Vec::new(),
        });
        let application_file = session_dir.join("application_result.toml");
        fs::write(&application_file, application_result.to_toml_string()?)?;
        finalize_application(ApplicatorArtifactParams {
            session: locator,
            artifact_file: application_file,
        })?;

        let verification_result =
            ArtifactDocument::VerificationResult(VerificationResultArtifact {
                header: ArtifactHeader::new(
                    ArtifactKind::VerificationResult,
                    "abc002def345".to_string(),
                    registered.session_id,
                    "refs/heads/main".to_string(),
                    ProducerKind::ApplicatorVerifier,
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
                verified_items: vec![crate::artifacts::VerificationItemRecord {
                    finding_id: "F999".to_string(),
                    status: crate::artifacts::VerificationStatus::Yes,
                    notes: "verified".to_string(),
                }],
                failed_items: Vec::new(),
                partial_items: Vec::new(),
                residual_risks: Vec::new(),
            });
        let summary = validate_artifact_document(
            &verification_result,
            ValidationLayer::Hard,
            Some(&session_dir),
        )?;
        ensure!(summary
            .errors
            .iter()
            .any(|error| error.contains("did not match application_result.verification_needed")));
        Ok(())
    }

    #[test]
    fn hard_validation_matches_verification_result_to_historical_application_cycle(
    ) -> anyhow::Result<()> {
        let repo_root = tempdir()?;
        let date = Date::from_calendar_date(2026, Month::March, 8)?;
        let session_dir = session_paths(repo_root.path(), date).session_dir;
        fs::create_dir_all(&session_dir)?;
        let locator = SessionLocator::from_session_dir(session_dir.clone());
        let registered = register_reviewer(RegisterReviewerParams {
            session: locator.clone(),
            target_ref: "refs/heads/main".to_string(),
            reviewer_id: Some("root0010".to_string()),
            role: Some("final-synthesis".to_string()),
            role_kind: None,
        })?;

        let application_one = ArtifactDocument::ApplicationResult(ApplicationResultArtifact {
            header: ArtifactHeader::new(
                ArtifactKind::ApplicationResult,
                "abc010abc234".to_string(),
                registered.session_id.clone(),
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
            dispositions: vec![DispositionRecord {
                finding_id: "F001".to_string(),
                disposition: Disposition::Applied,
                decline_reason_code: None,
                duplicate_reason_code: None,
                detail: "applied".to_string(),
                tracking_ref: Some("apply-001".to_string()),
                verification_needed: true,
                evidence_strength: Some(ConfidenceLabel::High),
                false_positive_risk: Some(ConfidenceLabel::Low),
                duplicate_suspect: Some(false),
                stop_recommendation: Some("continue_to_verification".to_string()),
            }],
            modified_files: vec!["src/lib.rs".to_string()],
            verification_needed: vec!["F001".to_string()],
            decline_codes: Vec::new(),
        });
        let application_one_file = session_dir.join("application_result_one.toml");
        fs::write(&application_one_file, application_one.to_toml_string()?)?;
        finalize_application(ApplicatorArtifactParams {
            session: locator.clone(),
            artifact_file: application_one_file,
        })?;

        let verification_one = ArtifactDocument::VerificationResult(VerificationResultArtifact {
            header: ArtifactHeader::new(
                ArtifactKind::VerificationResult,
                "abc011def345".to_string(),
                registered.session_id.clone(),
                "refs/heads/main".to_string(),
                ProducerKind::ApplicatorVerifier,
                "2026-03-08T00:01:00Z".to_string(),
                ConfidenceLabel::High,
                90,
                vec![PolicyRef {
                    category: PolicyCategory::Mode,
                    id: "applicator".to_string(),
                    version: "2026.03.08".to_string(),
                    view: PolicyView::Checklist,
                }],
            )?,
            verified_items: vec![crate::artifacts::VerificationItemRecord {
                finding_id: "F001".to_string(),
                status: crate::artifacts::VerificationStatus::Yes,
                notes: "verified".to_string(),
            }],
            failed_items: Vec::new(),
            partial_items: Vec::new(),
            residual_risks: Vec::new(),
        });
        let verification_one_file = session_dir.join("verification_result_one.toml");
        fs::write(&verification_one_file, verification_one.to_toml_string()?)?;
        let verification_one_path = verification_one_file.clone();
        crate::session::verify_application(ApplicatorArtifactParams {
            session: locator.clone(),
            artifact_file: verification_one_file,
        })?;

        let application_two = ArtifactDocument::ApplicationResult(ApplicationResultArtifact {
            header: ArtifactHeader::new(
                ArtifactKind::ApplicationResult,
                "abc012abc456".to_string(),
                registered.session_id,
                "refs/heads/main".to_string(),
                ProducerKind::ApplicatorWorker,
                "2026-03-08T00:02:00Z".to_string(),
                ConfidenceLabel::High,
                90,
                vec![PolicyRef {
                    category: PolicyCategory::Mode,
                    id: "applicator".to_string(),
                    version: "2026.03.08".to_string(),
                    view: PolicyView::Checklist,
                }],
            )?,
            source_finding_ids: vec!["F002".to_string()],
            dispositions: vec![DispositionRecord {
                finding_id: "F002".to_string(),
                disposition: Disposition::Applied,
                decline_reason_code: None,
                duplicate_reason_code: None,
                detail: "applied".to_string(),
                tracking_ref: Some("apply-002".to_string()),
                verification_needed: true,
                evidence_strength: Some(ConfidenceLabel::High),
                false_positive_risk: Some(ConfidenceLabel::Low),
                duplicate_suspect: Some(false),
                stop_recommendation: Some("continue_to_verification".to_string()),
            }],
            modified_files: vec!["src/lib.rs".to_string()],
            verification_needed: vec!["F002".to_string()],
            decline_codes: Vec::new(),
        });
        let application_two_file = session_dir.join("application_result_two.toml");
        fs::write(&application_two_file, application_two.to_toml_string()?)?;
        finalize_application(ApplicatorArtifactParams {
            session: locator,
            artifact_file: application_two_file,
        })?;

        let summary = validate_artifact_file(
            &verification_one_path,
            ArtifactKind::VerificationResult,
            ValidationLayer::Hard,
            Some(&session_dir),
        )?;
        ensure!(summary.errors.is_empty());
        Ok(())
    }

    #[test]
    fn soft_validation_warns_for_high_severity_application_disposition_metadata(
    ) -> anyhow::Result<()> {
        let repo_root = tempdir()?;
        let date = Date::from_calendar_date(2026, Month::March, 8)?;
        let session_dir = session_paths(repo_root.path(), date).session_dir;
        fs::create_dir_all(&session_dir)?;
        let locator = SessionLocator::from_session_dir(session_dir.clone());
        let registered = register_reviewer(RegisterReviewerParams {
            session: locator.clone(),
            target_ref: "refs/heads/main".to_string(),
            reviewer_id: Some("root0007".to_string()),
            role: Some("final-synthesis".to_string()),
            role_kind: None,
        })?;

        let finding_anchors = vec!["src/lib.rs:30".to_string()];
        let anchor_cluster = compute_anchor_cluster(&finding_anchors, None)?;
        let fingerprint = compute_fingerprint(
            "major issue remains",
            ModuleId::CoreCorrectness,
            &[SurfaceId::PublicApi],
            &anchor_cluster,
        );

        let parent_review = ArtifactDocument::ParentReview(ParentReviewArtifact {
            header: ArtifactHeader::new(
                ArtifactKind::ParentReview,
                "def456abc789".to_string(),
                registered.session_id.clone(),
                "refs/heads/main".to_string(),
                ProducerKind::FinalSynthesizer,
                "2026-03-08T00:00:00Z".to_string(),
                ConfidenceLabel::High,
                90,
                vec![PolicyRef {
                    category: PolicyCategory::Mode,
                    id: "reviewer".to_string(),
                    version: "2026.03.08".to_string(),
                    view: PolicyView::Checklist,
                }],
            )?,
            source_artifact_ids: Vec::new(),
            final_verdict: ReviewVerdict::RequestChanges,
            ship_readiness: ShipReadinessSummary {
                verdict: ShipReadinessVerdict::ShipWithFixes,
                axes: vec!["correctness".to_string()],
                blocking_items: vec!["major issue".to_string()],
                required_now_count: 1,
                follow_up_count: 0,
            },
            required_now: vec![FindingRecord {
                finding_id: "F900".to_string(),
                module_id: ModuleId::CoreCorrectness,
                surface_ids: vec![SurfaceId::PublicApi],
                severity: Severity::Major,
                title: "major issue".to_string(),
                claim: "major issue remains".to_string(),
                scenario: "major issue reproduced".to_string(),
                evidence: "major issue evidence".to_string(),
                recommendation: "fix it".to_string(),
                verification: "rerun tests".to_string(),
                anchors: finding_anchors,
                symbol_hint: None,
                anchor_cluster,
                fingerprint,
                reopen_eligible: true,
                confidence_label: ConfidenceLabel::High,
                confidence_score: 90,
                evidence_strength: Some(ConfidenceLabel::High),
                false_positive_risk: Some(ConfidenceLabel::Low),
                actionable: Some(true),
                duplicate_suspect: Some(false),
            }],
            follow_up: Vec::new(),
            defended_summary: Vec::new(),
            residual_risks: Vec::new(),
            coverage_summary: CoverageSummary {
                changed_files: vec!["src/lib.rs".to_string()],
                surfaces_covered: vec![SurfaceId::PublicApi],
                modules_loaded: vec![ModuleId::CoreCorrectness],
                tests_run: Vec::new(),
                tests_not_run_reason: Some("not run".to_string()),
                limitations: Vec::new(),
            },
        });
        let parent_file = session_dir.join("parent_review.toml");
        fs::write(&parent_file, parent_review.to_toml_string()?)?;
        finalize_review(ReviewerArtifactParams {
            session: locator.clone(),
            reviewer_id: "root0007".to_string(),
            artifact_file: parent_file,
        })?;

        let artifact = ArtifactDocument::ApplicationResult(ApplicationResultArtifact {
            header: header(ArtifactKind::ApplicationResult)?,
            source_finding_ids: vec!["F900".to_string()],
            dispositions: vec![DispositionRecord {
                finding_id: "F900".to_string(),
                disposition: Disposition::Declined,
                decline_reason_code: Some(crate::artifacts::DeclineReasonCode::NonReproducible),
                duplicate_reason_code: None,
                detail: "not repro".to_string(),
                tracking_ref: None,
                verification_needed: false,
                evidence_strength: None,
                false_positive_risk: None,
                duplicate_suspect: None,
                stop_recommendation: None,
            }],
            modified_files: Vec::new(),
            verification_needed: Vec::new(),
            decline_codes: vec![crate::artifacts::DeclineReasonCode::NonReproducible],
        });
        let summary =
            validate_artifact_document(&artifact, ValidationLayer::Soft, Some(&session_dir))?;
        ensure!(summary
            .warnings
            .iter()
            .any(|warning| warning.contains("missing disposition evidence_strength")));
        ensure!(summary
            .warnings
            .iter()
            .any(|warning| warning.contains("detail that is too thin")));
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

    #[test]
    fn hard_validation_accepts_direct_apply_composite_route() -> anyhow::Result<()> {
        let artifact = ArtifactDocument::RouteDecision(RouteDecisionArtifact {
            header: header(ArtifactKind::RouteDecision)?,
            mode: Mode::Applicator,
            execution_architecture: ExecutionArchitecture::Direct,
            rigor_level: crate::artifacts::RigorLevel::Standard,
            capability_profile: CapabilityProfile {
                execution_capability: ExecutionCapability::SingleProcess,
                max_worker_count: 1,
                orchestrator_read_budget_lines: 80,
                orchestrator_read_budget_snippets: 6,
            },
            resource_budget: ResourceBudget {
                planned_worker_count: 1,
                max_worker_count: 1,
            },
            risk_surfaces: vec![RiskSurfaceRecord {
                surface_id: SurfaceId::AuthAccess,
                weight: 5,
                reason: "auth".to_string(),
                evidence_refs: vec!["src/auth.rs".to_string()],
                behavior_facing: false,
            }],
            selected_modules: vec![ModuleId::CoreCorrectness, ModuleId::ShipReadiness],
            worker_plan: vec![WorkerPlanRecord {
                worker_kind: WorkerKind::ApplyComposite,
                role_id: Some("apply-composite".to_string()),
                language: None,
                module_ids: vec![ModuleId::CoreCorrectness, ModuleId::ShipReadiness],
                focus_surfaces: vec![SurfaceId::AuthAccess],
                claimed_scope: Vec::new(),
                delegated_scope: Vec::new(),
                required: true,
                parallelizable: false,
            }],
            heldback_escalations: Vec::new(),
            stop_conditions: Vec::new(),
        });
        let summary = validate_artifact_document(&artifact, ValidationLayer::Hard, None)?;
        ensure!(summary.errors.is_empty());
        Ok(())
    }

    #[test]
    fn hard_validation_rejects_repo_path_traversal() -> anyhow::Result<()> {
        let selected_modules = canonical_review_modules();
        let mut worker_plan = vec![WorkerPlanRecord {
            worker_kind: WorkerKind::LanguageDetector,
            role_id: Some("language-detector".to_string()),
            language: None,
            module_ids: Vec::new(),
            focus_surfaces: vec![SurfaceId::AuthAccess],
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
                focus_surfaces: vec![SurfaceId::AuthAccess],
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
            focus_surfaces: vec![SurfaceId::AuthAccess],
            claimed_scope: vec!["synthesize descendant reports".to_string()],
            delegated_scope: vec!["do not reopen low-signal duplicate findings".to_string()],
            required: true,
            parallelizable: false,
        });

        let artifact = ArtifactDocument::RouteDecision(RouteDecisionArtifact {
            header: header(ArtifactKind::RouteDecision)?,
            mode: Mode::Reviewer,
            execution_architecture: ExecutionArchitecture::Hybrid,
            rigor_level: crate::artifacts::RigorLevel::Standard,
            capability_profile: CapabilityProfile {
                execution_capability: ExecutionCapability::BoundedHelpers,
                max_worker_count: 4,
                orchestrator_read_budget_lines: 120,
                orchestrator_read_budget_snippets: 8,
            },
            resource_budget: ResourceBudget {
                planned_worker_count: 4,
                max_worker_count: 4,
            },
            risk_surfaces: vec![RiskSurfaceRecord {
                surface_id: SurfaceId::AuthAccess,
                weight: 5,
                reason: "auth".to_string(),
                evidence_refs: vec!["../../tmp/pwn".to_string()],
                behavior_facing: false,
            }],
            selected_modules,
            worker_plan,
            heldback_escalations: Vec::new(),
            stop_conditions: Vec::new(),
        });
        let summary = validate_artifact_document(&artifact, ValidationLayer::Hard, None)?;
        ensure!(
            summary
                .errors
                .iter()
                .any(|error| error.contains("must not contain `..`")),
            "expected traversal validation error, got {:?}",
            summary.errors
        );
        Ok(())
    }
}
