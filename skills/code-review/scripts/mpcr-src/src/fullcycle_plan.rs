//! Convergence-state planning for the full-cycle workflow.
#![allow(missing_docs)]

use crate::artifacts::{
    now_rfc3339, parse_artifact_file, ArtifactDocument, ArtifactHeader, ArtifactKind,
    ConfidenceLabel, ConvergenceStateArtifact, NextRouteInputs, PolicyCategory, PolicyRef,
    PolicyView, ProducerKind, ReopenReasonCode, ReopenThreshold, ReopenTriggerRecord,
    RouteDecisionArtifact, Severity, SurfaceId, POLICY_BUNDLE_VERSION,
};
use crate::id;
use crate::paths;
use crate::session::{load_session, SessionLedger, SessionLocator};
use std::path::PathBuf;

fn policy_refs() -> Vec<PolicyRef> {
    vec![
        PolicyRef {
            category: PolicyCategory::Mode,
            id: "full-cycle".to_string(),
            version: POLICY_BUNDLE_VERSION.to_string(),
            view: PolicyView::Checklist,
        },
        PolicyRef {
            category: PolicyCategory::Escalation,
            id: "reopen".to_string(),
            version: POLICY_BUNDLE_VERSION.to_string(),
            view: PolicyView::Checklist,
        },
    ]
}

fn resolve_artifact_path(session: &SessionLedger, repo_relative: &str) -> anyhow::Result<PathBuf> {
    let repo_root = PathBuf::from(&session.repo_root);
    paths::resolve_repo_relative(&repo_root, repo_relative)
}

fn load_current_artifact(
    session: &SessionLedger,
    pointer: &Option<crate::session::ArtifactPointer>,
) -> anyhow::Result<Option<ArtifactDocument>> {
    pointer
        .as_ref()
        .map(|pointer| {
            let path = resolve_artifact_path(session, &pointer.path)?;
            parse_artifact_file(&path)
        })
        .transpose()
}

fn collect_parent_reopen_triggers(
    parent_review: &crate::artifacts::ParentReviewArtifact,
) -> Vec<ReopenTriggerRecord> {
    let mut triggers = Vec::new();
    for finding in &parent_review.required_now {
        match finding.severity {
            Severity::Blocker => triggers.push(ReopenTriggerRecord {
                reference_id: finding.finding_id.clone(),
                reopen_reason_code: ReopenReasonCode::BlockerRemaining,
            }),
            Severity::Major => triggers.push(ReopenTriggerRecord {
                reference_id: finding.finding_id.clone(),
                reopen_reason_code: ReopenReasonCode::MajorRemaining,
            }),
            _ => {
                if finding.reopen_eligible
                    && finding.surface_ids.contains(&SurfaceId::DocsStaleness)
                {
                    triggers.push(ReopenTriggerRecord {
                        reference_id: finding.finding_id.clone(),
                        reopen_reason_code: ReopenReasonCode::BehaviorStaleness,
                    });
                }
            }
        }
    }
    for risk in &parent_review.residual_risks {
        if risk.reopen_eligible && risk.surface_ids.contains(&SurfaceId::DocsStaleness) {
            triggers.push(ReopenTriggerRecord {
                reference_id: risk.risk_id.clone(),
                reopen_reason_code: ReopenReasonCode::BehaviorStaleness,
            });
        }
    }
    triggers
}

fn collect_verification_triggers(
    verification_result: &crate::artifacts::VerificationResultArtifact,
) -> Vec<ReopenTriggerRecord> {
    let mut triggers = Vec::new();
    for item in &verification_result.failed_items {
        triggers.push(ReopenTriggerRecord {
            reference_id: item.finding_id.clone(),
            reopen_reason_code: ReopenReasonCode::VerificationFailed,
        });
    }
    for risk in &verification_result.residual_risks {
        let reason = if risk.surface_ids.contains(&SurfaceId::DocsStaleness) {
            ReopenReasonCode::BehaviorStaleness
        } else if risk.summary.to_ascii_lowercase().contains("regression")
            || risk.impact.to_ascii_lowercase().contains("regression")
        {
            ReopenReasonCode::FixRegression
        } else {
            continue;
        };
        if risk.reopen_eligible {
            triggers.push(ReopenTriggerRecord {
                reference_id: risk.risk_id.clone(),
                reopen_reason_code: reason,
            });
        }
    }
    triggers
}

fn next_route_inputs(
    parent_review: Option<&crate::artifacts::ParentReviewArtifact>,
    route_decision: Option<&RouteDecisionArtifact>,
    application_result: Option<&crate::artifacts::ApplicationResultArtifact>,
) -> NextRouteInputs {
    let focus_files = match application_result
        .map(|result| result.modified_files.clone())
        .filter(|files| !files.is_empty())
        .or_else(|| parent_review.map(|review| review.coverage_summary.changed_files.clone()))
    {
        Some(files) => files,
        None => Vec::new(),
    };
    let focus_surfaces = match parent_review {
        Some(review) => review.coverage_summary.surfaces_covered.clone(),
        None => Vec::new(),
    };
    let recommended_modules = match route_decision
        .map(|route| route.selected_modules.clone())
        .or_else(|| parent_review.map(|review| review.coverage_summary.modules_loaded.clone()))
    {
        Some(modules) => modules,
        None => Vec::new(),
    };
    NextRouteInputs {
        focus_files,
        focus_surfaces,
        recommended_modules,
    }
}

/// Build the next convergence-state artifact from the current session pointers.
pub fn build_plan(locator: &SessionLocator) -> anyhow::Result<ConvergenceStateArtifact> {
    let session = load_session(locator)?;
    let current_parent = load_current_artifact(&session, &session.current.parent_review)?;
    let current_route = load_current_artifact(&session, &session.current.route_decision)?;
    let current_application = load_current_artifact(&session, &session.current.application_result)?;
    let current_verification =
        load_current_artifact(&session, &session.current.verification_result)?;
    let current_convergence = load_current_artifact(&session, &session.current.convergence_state)?;

    let parent_review = match current_parent.as_ref() {
        Some(ArtifactDocument::ParentReview(parent_review)) => Some(parent_review),
        _ => None,
    };
    let route_decision = match current_route.as_ref() {
        Some(ArtifactDocument::RouteDecision(route_decision)) => Some(route_decision),
        _ => None,
    };
    let application_result = match current_application.as_ref() {
        Some(ArtifactDocument::ApplicationResult(application_result)) => Some(application_result),
        _ => None,
    };
    let verification_result = match current_verification.as_ref() {
        Some(ArtifactDocument::VerificationResult(verification_result)) => {
            Some(verification_result)
        }
        _ => None,
    };
    let prior_convergence = match current_convergence.as_ref() {
        Some(ArtifactDocument::ConvergenceState(convergence_state)) => Some(convergence_state),
        _ => None,
    };

    let mut reopen_triggers = Vec::new();
    if let Some(parent_review) = parent_review {
        reopen_triggers.extend(collect_parent_reopen_triggers(parent_review));
    }
    if let Some(verification_result) = verification_result {
        reopen_triggers.extend(collect_verification_triggers(verification_result));
    }

    let stop_condition = if !reopen_triggers.is_empty() {
        "reopen_required".to_string()
    } else if !session.convergence.terminal_cleanup_consumed
        && parent_review.is_some_and(|review| {
            review
                .required_now
                .iter()
                .any(|finding| matches!(finding.severity, Severity::Minor | Severity::Nit))
                || review
                    .follow_up
                    .iter()
                    .any(|finding| matches!(finding.severity, Severity::Minor | Severity::Nit))
        })
    {
        "terminal_cleanup".to_string()
    } else {
        "converged".to_string()
    };

    let header = ArtifactHeader::new(
        ArtifactKind::ConvergenceState,
        id::random_hex_id(6)?,
        session.session_id.clone(),
        session.target_ref.clone(),
        ProducerKind::ConvergencePlanner,
        now_rfc3339(),
        ConfidenceLabel::High,
        90,
        policy_refs(),
    )?;

    Ok(ConvergenceStateArtifact {
        header,
        cycle_index: prior_convergence.map_or(session.convergence.cycle_index + 1, |convergence| {
            convergence.cycle_index + 1
        }),
        reopen_threshold: ReopenThreshold {
            severity_floor: Severity::Major,
            behavior_staleness_reopens: true,
        },
        reopen_triggers,
        terminal_cleanup_allowed: stop_condition == "terminal_cleanup"
            && !session.convergence.terminal_cleanup_consumed,
        next_route_inputs: next_route_inputs(parent_review, route_decision, application_result),
        stop_condition,
    })
}

/// Load the persisted convergence-state artifact referenced by the session, if any.
pub fn load_state(locator: &SessionLocator) -> anyhow::Result<Option<ConvergenceStateArtifact>> {
    let session = load_session(locator)?;
    let Some(ref pointer) = session.current.convergence_state else {
        return Ok(None);
    };
    let path = resolve_artifact_path(&session, &pointer.path)?;
    match parse_artifact_file(&path)? {
        ArtifactDocument::ConvergenceState(state) => Ok(Some(state)),
        _ => Ok(None),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::artifacts::{
        compute_anchor_cluster, compute_fingerprint, ArtifactDocument, FindingRecord, ModuleId,
        ParentReviewArtifact, PolicyCategory, ReviewVerdict, Severity, ShipReadinessSummary,
        ShipReadinessVerdict, VerificationItemRecord, VerificationResultArtifact,
    };
    use crate::paths::session_paths;
    use crate::session::{
        checkpoint_convergence_state, register_reviewer, ApplicatorArtifactParams,
        RegisterReviewerParams,
    };
    use anyhow::ensure;
    use std::fs;
    use time::{Date, Month};

    fn locator() -> anyhow::Result<SessionLocator> {
        let temp = std::env::temp_dir().join(format!("mpcr-fullcycle-test-{}", id::random_id8()?));
        let _ = fs::remove_dir_all(&temp);
        fs::create_dir_all(&temp)?;
        let date = Date::from_calendar_date(2026, Month::March, 8)?;
        Ok(SessionLocator::from_session_dir(
            session_paths(&temp, date).session_dir,
        ))
    }

    fn header(kind: ArtifactKind, session_id: &str) -> anyhow::Result<ArtifactHeader> {
        ArtifactHeader::new(
            kind,
            id::random_hex_id(6)?,
            session_id.to_string(),
            "refs/heads/main".to_string(),
            ProducerKind::ApplicatorVerifier,
            "2026-03-08T00:00:00Z".to_string(),
            ConfidenceLabel::High,
            90,
            vec![PolicyRef {
                category: PolicyCategory::Mode,
                id: "full-cycle".to_string(),
                version: POLICY_BUNDLE_VERSION.to_string(),
                view: PolicyView::Checklist,
            }],
        )
    }

    fn minor_finding() -> anyhow::Result<FindingRecord> {
        let anchors = vec!["src/lib.rs:12".to_string()];
        let anchor_cluster = compute_anchor_cluster(&anchors, None)?;
        Ok(FindingRecord {
            finding_id: "F100".to_string(),
            module_id: ModuleId::CoreCorrectness,
            surface_ids: vec![SurfaceId::PublicApi],
            severity: Severity::Minor,
            title: "minor cleanup".to_string(),
            claim: "minor cleanup remains".to_string(),
            scenario: "small follow-up remains".to_string(),
            evidence: "cleanup follow-up".to_string(),
            recommendation: "clean it up".to_string(),
            verification: "rerun tests".to_string(),
            anchors: anchors.clone(),
            symbol_hint: None,
            anchor_cluster: anchor_cluster.clone(),
            fingerprint: compute_fingerprint(
                "minor cleanup remains",
                ModuleId::CoreCorrectness,
                &[SurfaceId::PublicApi],
                &anchor_cluster,
            ),
            reopen_eligible: false,
            confidence_label: ConfidenceLabel::High,
            confidence_score: 90,
            evidence_strength: Some(ConfidenceLabel::High),
            false_positive_risk: Some(ConfidenceLabel::Low),
            actionable: Some(true),
            duplicate_suspect: Some(false),
        })
    }

    #[test]
    fn plan_reopens_for_failed_verification() -> anyhow::Result<()> {
        let locator = locator()?;
        fs::create_dir_all(locator.session_dir())?;
        let registered = register_reviewer(RegisterReviewerParams {
            session: locator.clone(),
            target_ref: "refs/heads/main".to_string(),
            reviewer_id: Some("parent01".to_string()),
            role: None,
            role_kind: None,
        })?;

        let parent_review = ArtifactDocument::ParentReview(ParentReviewArtifact {
            header: header(ArtifactKind::ParentReview, &registered.session_id)?,
            source_artifact_ids: Vec::new(),
            final_verdict: ReviewVerdict::RequestChanges,
            ship_readiness: ShipReadinessSummary {
                verdict: ShipReadinessVerdict::ShipWithFixes,
                axes: Vec::new(),
                blocking_items: Vec::new(),
                required_now_count: 0,
                follow_up_count: 0,
            },
            required_now: Vec::new(),
            follow_up: Vec::new(),
            defended_summary: Vec::new(),
            residual_risks: Vec::new(),
            coverage_summary: crate::artifacts::CoverageSummary {
                changed_files: vec!["src/lib.rs".to_string()],
                surfaces_covered: vec![SurfaceId::PublicApi],
                modules_loaded: vec![ModuleId::CoreCorrectness],
                tests_run: Vec::new(),
                tests_not_run_reason: None,
                limitations: Vec::new(),
            },
        });
        let parent_file = locator.session_dir().join("parent_review.toml");
        fs::write(&parent_file, parent_review.to_toml_string()?)?;
        crate::session::finalize_review(crate::session::ReviewerArtifactParams {
            session: locator.clone(),
            reviewer_id: "parent01".to_string(),
            artifact_file: parent_file,
        })?;

        let verification = ArtifactDocument::VerificationResult(VerificationResultArtifact {
            header: header(ArtifactKind::VerificationResult, &registered.session_id)?,
            verified_items: Vec::new(),
            failed_items: vec![VerificationItemRecord {
                finding_id: "F001".to_string(),
                status: crate::artifacts::VerificationStatus::No,
                notes: "regression failed".to_string(),
            }],
            partial_items: Vec::new(),
            residual_risks: Vec::new(),
        });
        let verify_file = locator.session_dir().join("verification_result.toml");
        fs::write(&verify_file, verification.to_toml_string()?)?;
        crate::session::verify_application(ApplicatorArtifactParams {
            session: locator.clone(),
            artifact_file: verify_file,
        })?;

        let plan = build_plan(&locator)?;
        ensure!(plan.stop_condition == "reopen_required");
        ensure!(!plan.reopen_triggers.is_empty());
        let plan_file = locator.session_dir().join("convergence_state.toml");
        fs::write(
            &plan_file,
            ArtifactDocument::ConvergenceState(plan.clone()).to_toml_string()?,
        )?;
        let persisted = checkpoint_convergence_state(ApplicatorArtifactParams {
            session: locator.clone(),
            artifact_file: plan_file,
        })?;
        ensure!(persisted.artifact_kind == ArtifactKind::ConvergenceState);
        ensure!(load_state(&locator)?.is_some());
        Ok(())
    }

    #[test]
    fn terminal_cleanup_is_one_shot() -> anyhow::Result<()> {
        let locator = locator()?;
        fs::create_dir_all(locator.session_dir())?;
        let registered = register_reviewer(RegisterReviewerParams {
            session: locator.clone(),
            target_ref: "refs/heads/main".to_string(),
            reviewer_id: Some("parent02".to_string()),
            role: None,
            role_kind: None,
        })?;

        let parent_review = ArtifactDocument::ParentReview(ParentReviewArtifact {
            header: header(ArtifactKind::ParentReview, &registered.session_id)?,
            source_artifact_ids: Vec::new(),
            final_verdict: ReviewVerdict::RequestChanges,
            ship_readiness: ShipReadinessSummary {
                verdict: ShipReadinessVerdict::ShipWithFixes,
                axes: Vec::new(),
                blocking_items: Vec::new(),
                required_now_count: 0,
                follow_up_count: 1,
            },
            required_now: Vec::new(),
            follow_up: vec![minor_finding()?],
            defended_summary: Vec::new(),
            residual_risks: Vec::new(),
            coverage_summary: crate::artifacts::CoverageSummary {
                changed_files: vec!["src/lib.rs".to_string()],
                surfaces_covered: vec![SurfaceId::PublicApi],
                modules_loaded: vec![ModuleId::CoreCorrectness],
                tests_run: Vec::new(),
                tests_not_run_reason: None,
                limitations: Vec::new(),
            },
        });
        let parent_file = locator.session_dir().join("parent_review.toml");
        fs::write(&parent_file, parent_review.to_toml_string()?)?;
        crate::session::finalize_review(crate::session::ReviewerArtifactParams {
            session: locator.clone(),
            reviewer_id: "parent02".to_string(),
            artifact_file: parent_file,
        })?;

        let first_plan = build_plan(&locator)?;
        ensure!(first_plan.stop_condition == "terminal_cleanup");
        let plan_file = locator.session_dir().join("convergence_state.toml");
        fs::write(
            &plan_file,
            ArtifactDocument::ConvergenceState(first_plan.clone()).to_toml_string()?,
        )?;
        checkpoint_convergence_state(ApplicatorArtifactParams {
            session: locator.clone(),
            artifact_file: plan_file,
        })?;

        let second_plan = build_plan(&locator)?;
        ensure!(second_plan.stop_condition == "converged");
        ensure!(!second_plan.terminal_cleanup_allowed);
        Ok(())
    }
}
