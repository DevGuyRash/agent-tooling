#![allow(missing_docs)]
#![allow(clippy::all, clippy::pedantic, clippy::nursery, clippy::cargo)]
#![allow(clippy::indexing_slicing)]

use anyhow::ensure;
use mpcr::artifacts::{
    ApplicationResultArtifact, ArtifactDocument, ArtifactHeader, ArtifactKind,
    ChildFindingsArtifact, ConfidenceLabel, CoverageSummary, Disposition, DispositionRecord,
    ExecutionCapability, ModuleId, ParentReviewArtifact, PolicyCategory, PolicyRef, PolicyView,
    ProducerKind, ReviewVerdict, RouteDecisionArtifact, ShipReadinessSummary, ShipReadinessVerdict,
    SurfaceId, VerificationItemRecord, VerificationResultArtifact, VerificationStatus, WorkerKind,
    WorkerPlanRecord,
};
use mpcr::paths::{self, session_paths, StorageFormat};
use mpcr::router::{build_route_decision, build_surface_map, default_router_policy_refs};
use mpcr::router_types::RouteInputs;
use mpcr::session::{
    cleanup_session, collect_reports, complete_child_review, finalize_application, finalize_review,
    load_session, persist_route_artifacts, register_reviewer, spawn_child_reviewers, update_review,
    verify_application, ApplicatorArtifactParams, PersistRouteArtifactsParams,
    RegisterReviewerParams, ReportView, ReviewProcessStatus, ReviewerArtifactParams, SessionLedger,
    SessionLocator, SpawnChildReviewersParams, UpdateReviewParams,
};
use serde_json::Value;
use std::fs;
use std::path::PathBuf;
use tempfile::tempdir;
use time::{Date, Month};

fn expect_error<T>(result: anyhow::Result<T>, context: &str) -> anyhow::Result<anyhow::Error> {
    match result {
        Ok(_) => Err(anyhow::anyhow!("{context}")),
        Err(err) => Ok(err),
    }
}

fn reviewer_header(
    kind: ArtifactKind,
    artifact_id: &str,
    session_id: &str,
    producer_kind: ProducerKind,
) -> anyhow::Result<ArtifactHeader> {
    ArtifactHeader::new(
        kind,
        artifact_id.to_string(),
        session_id.to_string(),
        "refs/heads/main".to_string(),
        producer_kind,
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

fn applicator_header(
    kind: ArtifactKind,
    artifact_id: &str,
    session_id: &str,
    producer_kind: ProducerKind,
) -> anyhow::Result<ArtifactHeader> {
    ArtifactHeader::new(
        kind,
        artifact_id.to_string(),
        session_id.to_string(),
        "refs/heads/main".to_string(),
        producer_kind,
        "2026-03-08T00:00:00Z".to_string(),
        ConfidenceLabel::High,
        90,
        vec![PolicyRef {
            category: PolicyCategory::Mode,
            id: "applicator".to_string(),
            version: "2026.03.08".to_string(),
            view: PolicyView::Checklist,
        }],
    )
}

fn new_session_locator() -> anyhow::Result<(tempfile::TempDir, PathBuf, SessionLocator, PathBuf)> {
    let repo_root = tempdir()?;
    let date = Date::from_calendar_date(2026, Month::March, 8)?;
    let session_dir = session_paths(repo_root.path(), date).session_dir;
    Ok((
        repo_root,
        session_dir
            .parent()
            .and_then(|path| path.parent())
            .and_then(|path| path.parent())
            .and_then(|path| path.parent())
            .map(PathBuf::from)
            .ok_or_else(|| anyhow::anyhow!("failed to derive repo root"))?,
        SessionLocator::from_session_dir(session_dir.clone()),
        session_dir,
    ))
}

fn minimal_child_findings(session_id: &str, artifact_id: &str) -> anyhow::Result<ArtifactDocument> {
    Ok(ArtifactDocument::ChildFindings(ChildFindingsArtifact {
        header: reviewer_header(
            ArtifactKind::ChildFindings,
            artifact_id,
            session_id,
            ProducerKind::DomainReviewer,
        )?,
        worker_kind: WorkerKind::DomainReviewer,
        role_id: Some("domain:core-correctness".to_string()),
        language: None,
        module_ids: vec![ModuleId::CoreCorrectness],
        claimed_scope: vec!["own module `core-correctness`".to_string()],
        delegated_scope: vec!["do not delegate the same domain investigation again".to_string()],
        research_refs: vec!["rust".to_string()],
        findings: Vec::new(),
        defended_checks: Vec::new(),
        residual_risks: Vec::new(),
        route_revision_refs: Vec::new(),
    }))
}

fn minimal_parent_review(session_id: &str, artifact_id: &str) -> anyhow::Result<ArtifactDocument> {
    Ok(ArtifactDocument::ParentReview(ParentReviewArtifact {
        header: reviewer_header(
            ArtifactKind::ParentReview,
            artifact_id,
            session_id,
            ProducerKind::FinalSynthesizer,
        )?,
        source_artifact_ids: Vec::new(),
        final_verdict: ReviewVerdict::Approve,
        ship_readiness: ShipReadinessSummary {
            verdict: ShipReadinessVerdict::Ship,
            axes: vec!["coverage".to_string()],
            blocking_items: Vec::new(),
            required_now_count: 0,
            follow_up_count: 0,
        },
        required_now: Vec::new(),
        follow_up: Vec::new(),
        defended_summary: Vec::new(),
        residual_risks: Vec::new(),
        coverage_summary: CoverageSummary {
            changed_files: vec!["src/lib.rs".to_string()],
            surfaces_covered: vec![SurfaceId::PublicApi],
            modules_loaded: vec![ModuleId::CoreCorrectness, ModuleId::ShipReadiness],
            tests_run: Vec::new(),
            tests_not_run_reason: Some("not needed for fixture".to_string()),
            limitations: Vec::new(),
        },
    }))
}

fn persist_reviewer_route(
    locator: &SessionLocator,
    target_ref: &str,
    session_id: &str,
    changed_files: &[&str],
) -> anyhow::Result<RouteDecisionArtifact> {
    let inputs = RouteInputs {
        changed_files: changed_files
            .iter()
            .map(|file| (*file).to_string())
            .collect(),
        public_interfaces: Vec::new(),
        behavior_facing_artifacts: Vec::new(),
        execution_capability: ExecutionCapability::SingleProcess,
        max_worker_count: 16,
        orchestrator_read_budget_lines: 120,
        orchestrator_read_budget_snippets: 12,
        history_signals: Default::default(),
    };
    let surface_map = build_surface_map(
        ArtifactHeader::new(
            ArtifactKind::SurfaceMap,
            "abc123def001".to_string(),
            session_id.to_string(),
            target_ref.to_string(),
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
        )?,
        &inputs,
    );
    let route_decision = build_route_decision(
        ArtifactHeader::new(
            ArtifactKind::RouteDecision,
            "abc123def002".to_string(),
            session_id.to_string(),
            target_ref.to_string(),
            ProducerKind::Router,
            "2026-03-08T00:00:00Z".to_string(),
            ConfidenceLabel::High,
            90,
            default_router_policy_refs(&surface_map.suggested_modules),
        )?,
        mpcr::artifacts::Mode::Reviewer,
        &surface_map,
        &inputs,
    );
    persist_route_artifacts(PersistRouteArtifactsParams {
        session: locator.clone(),
        target_ref: target_ref.to_string(),
        surface_map,
        route_decision: route_decision.clone(),
    })?;
    Ok(route_decision)
}

fn child_findings_for_worker(
    session_id: &str,
    artifact_id: &str,
    worker: &WorkerPlanRecord,
) -> anyhow::Result<ArtifactDocument> {
    Ok(ArtifactDocument::ChildFindings(ChildFindingsArtifact {
        header: reviewer_header(
            ArtifactKind::ChildFindings,
            artifact_id,
            session_id,
            ProducerKind::from_worker(worker.worker_kind),
        )?,
        worker_kind: worker.worker_kind,
        role_id: worker.role_id.clone(),
        language: worker.language.clone(),
        module_ids: worker.module_ids.clone(),
        claimed_scope: worker.claimed_scope.clone(),
        delegated_scope: worker.delegated_scope.clone(),
        research_refs: Vec::new(),
        findings: Vec::new(),
        defended_checks: Vec::new(),
        residual_risks: Vec::new(),
        route_revision_refs: Vec::new(),
    }))
}

#[test]
fn json_only_session_is_mirrored_back_to_toml_on_mutation() -> anyhow::Result<()> {
    let (_repo_root, _repo_root_path, locator, session_dir) = new_session_locator()?;
    let register = register_reviewer(RegisterReviewerParams {
        session: locator.clone(),
        target_ref: "refs/heads/main".to_string(),
        reviewer_id: Some("review01".to_string()),
        role: None,
        role_kind: None,
    })?;
    let json_path = paths::session_file(&session_dir, StorageFormat::Json);
    let toml_path = paths::session_file(&session_dir, StorageFormat::Toml);
    ensure!(json_path.exists());
    ensure!(toml_path.exists());
    fs::remove_file(&toml_path)?;

    update_review(UpdateReviewParams {
        session: locator,
        reviewer_id: register.reviewer_id,
        status: ReviewProcessStatus::InProgress,
        phase: Some("json-recovery".to_string()),
    })?;

    ensure!(json_path.exists());
    ensure!(toml_path.exists());
    Ok(())
}

#[test]
fn toml_only_session_is_mirrored_back_to_json_on_mutation() -> anyhow::Result<()> {
    let (_repo_root, _repo_root_path, locator, session_dir) = new_session_locator()?;
    let register = register_reviewer(RegisterReviewerParams {
        session: locator.clone(),
        target_ref: "refs/heads/main".to_string(),
        reviewer_id: Some("review02".to_string()),
        role: None,
        role_kind: None,
    })?;
    let json_path = paths::session_file(&session_dir, StorageFormat::Json);
    let toml_path = paths::session_file(&session_dir, StorageFormat::Toml);
    ensure!(json_path.exists());
    ensure!(toml_path.exists());
    fs::remove_file(&json_path)?;

    update_review(UpdateReviewParams {
        session: locator,
        reviewer_id: register.reviewer_id,
        status: ReviewProcessStatus::InProgress,
        phase: Some("toml-recovery".to_string()),
    })?;

    ensure!(json_path.exists());
    ensure!(toml_path.exists());
    Ok(())
}

#[test]
fn divergent_json_and_toml_prefer_json_and_rewrite_toml_on_mutation() -> anyhow::Result<()> {
    let (_repo_root, _repo_root_path, locator, session_dir) = new_session_locator()?;
    let register = register_reviewer(RegisterReviewerParams {
        session: locator.clone(),
        target_ref: "refs/heads/main".to_string(),
        reviewer_id: Some("review03".to_string()),
        role: None,
        role_kind: None,
    })?;
    let json_path = paths::session_file(&session_dir, StorageFormat::Json);
    let toml_path = paths::session_file(&session_dir, StorageFormat::Toml);
    let divergent_toml =
        fs::read_to_string(&toml_path)?.replace("refs/heads/main", "refs/heads/diverged");
    fs::write(&toml_path, divergent_toml)?;

    let loaded = load_session(&locator)?;
    ensure!(loaded.target_ref == "refs/heads/main");
    ensure!(loaded
        .storage
        .degraded_warnings
        .iter()
        .any(|warning| warning.contains("JSON and TOML diverged")));

    update_review(UpdateReviewParams {
        session: locator.clone(),
        reviewer_id: register.reviewer_id,
        status: ReviewProcessStatus::Delegating,
        phase: Some("repair-divergence".to_string()),
    })?;

    let repaired: SessionLedger = toml::from_str(&fs::read_to_string(&toml_path)?)?;
    ensure!(repaired.target_ref == "refs/heads/main");
    ensure!(fs::read_to_string(&json_path)?.contains("\"target_ref\": \"refs/heads/main\""));
    Ok(())
}

#[test]
fn nested_agent_dirs_and_recursive_reports_are_materialized() -> anyhow::Result<()> {
    let (_repo_root, repo_root_path, locator, _session_dir) = new_session_locator()?;
    let register = register_reviewer(RegisterReviewerParams {
        session: locator.clone(),
        target_ref: "refs/heads/main".to_string(),
        reviewer_id: Some("root0001".to_string()),
        role: Some("final-synthesis".to_string()),
        role_kind: None,
    })?;

    let child = spawn_child_reviewers(SpawnChildReviewersParams {
        session: locator.clone(),
        parent_id: register.reviewer_id.clone(),
        count: 1,
        role_id: Some("domain:core-correctness".to_string()),
        worker_kind: Some(WorkerKind::DomainReviewer),
        domain_id: Some(ModuleId::CoreCorrectness),
        language: None,
        module_ids: vec![ModuleId::CoreCorrectness],
        focus_surfaces: vec![SurfaceId::PublicApi],
        claimed_scope: vec!["own core-correctness".to_string()],
        delegated_scope: vec!["do not repeat parent synthesis".to_string()],
    })?;
    let child_id = child.child_ids[0].clone();
    let child_dir = repo_root_path.join(&child.child_agent_dirs[0]);
    ensure!(child_dir.exists());
    ensure!(child_dir
        .to_string_lossy()
        .contains("/agents/root0001/children/"));

    let grandchild = spawn_child_reviewers(SpawnChildReviewersParams {
        session: locator.clone(),
        parent_id: child_id.clone(),
        count: 1,
        role_id: Some("language-research:rust".to_string()),
        worker_kind: Some(WorkerKind::LanguageResearch),
        domain_id: None,
        language: Some("rust".to_string()),
        module_ids: Vec::new(),
        focus_surfaces: vec![SurfaceId::PublicApi],
        claimed_scope: vec!["research rust guidance".to_string()],
        delegated_scope: vec!["do not redo parent domain review".to_string()],
    })?;
    let grandchild_dir = repo_root_path.join(&grandchild.child_agent_dirs[0]);
    ensure!(grandchild_dir.exists());
    ensure!(grandchild_dir
        .to_string_lossy()
        .contains("/agents/root0001/children/"));
    ensure!(grandchild_dir.to_string_lossy().contains("/children/"));

    let reports = collect_reports(&locator, ReportView::All, true, true, true, true)?;
    ensure!(reports.reports.len() >= 3);
    let concatenated = reports
        .concatenated_report
        .ok_or_else(|| anyhow::anyhow!("missing concatenated report"))?;
    // Agents without artifacts don't get report.md (no skeleton waste), so
    // they won't appear in the concatenated report. The ledger-based
    // reports.reports still lists them.
    ensure!(!concatenated.contains("Agent `root0001`"));
    ensure!(!concatenated.contains(&format!("Agent `{child_id}`")));
    ensure!(!concatenated.contains(&format!("Agent `{}`", grandchild.child_ids[0])));

    let root_ledger: Value = serde_json::from_str(&fs::read_to_string(
        repo_root_path.join(register.agent_ledger_json),
    )?)?;
    ensure!(root_ledger["counters"]["child_count"].as_u64() == Some(1));
    ensure!(root_ledger["counters"]["descendant_count"].as_u64() == Some(2));
    ensure!(root_ledger["counters"]["local_report_count"].as_u64() == Some(1));
    ensure!(root_ledger["counters"]["recursive_report_count"].as_u64() == Some(3));

    let child_ledger: Value = serde_json::from_str(&fs::read_to_string(
        repo_root_path.join(&child.child_agent_ledgers_json[0]),
    )?)?;
    ensure!(child_ledger["counters"]["child_count"].as_u64() == Some(1));
    ensure!(child_ledger["counters"]["descendant_count"].as_u64() == Some(1));
    ensure!(child_ledger["counters"]["local_report_count"].as_u64() == Some(1));
    ensure!(child_ledger["counters"]["recursive_report_count"].as_u64() == Some(2));

    let grandchild_ledger: Value = serde_json::from_str(&fs::read_to_string(
        repo_root_path.join(&grandchild.child_agent_ledgers_json[0]),
    )?)?;
    ensure!(grandchild_ledger["counters"]["child_count"].as_u64() == Some(0));
    ensure!(grandchild_ledger["counters"]["descendant_count"].as_u64() == Some(0));
    ensure!(grandchild_ledger["counters"]["local_report_count"].as_u64() == Some(1));
    ensure!(grandchild_ledger["counters"]["recursive_report_count"].as_u64() == Some(1));
    Ok(())
}

#[test]
fn cleanup_session_preserves_shared_nonempty_scratch_root() -> anyhow::Result<()> {
    let (_repo_root, repo_root_path, locator, session_dir) = new_session_locator()?;
    register_reviewer(RegisterReviewerParams {
        session: locator.clone(),
        target_ref: "refs/heads/main".to_string(),
        reviewer_id: Some("clean001".to_string()),
        role: None,
        role_kind: None,
    })?;

    let scratch_dir = paths::scratch_dir(&repo_root_path);
    fs::create_dir_all(&scratch_dir)?;
    fs::write(scratch_dir.join("other-session.tmp"), "keep me")?;

    let cleaned = cleanup_session(&locator)?;

    ensure!(cleaned.session_dir == session_dir.to_string_lossy());
    ensure!(cleaned.scratch_dir == scratch_dir.to_string_lossy());
    ensure!(cleaned.removed_session_dir);
    ensure!(!cleaned.removed_scratch_dir);
    ensure!(!session_dir.exists());
    ensure!(scratch_dir.exists());
    ensure!(scratch_dir.join("other-session.tmp").exists());
    Ok(())
}

#[test]
fn non_recursive_concatenated_reports_exclude_descendants() -> anyhow::Result<()> {
    let (_repo_root, _repo_root_path, locator, _session_dir) = new_session_locator()?;
    let register = register_reviewer(RegisterReviewerParams {
        session: locator.clone(),
        target_ref: "refs/heads/main".to_string(),
        reviewer_id: Some("root0003".to_string()),
        role: Some("final-synthesis".to_string()),
        role_kind: None,
    })?;

    let child = spawn_child_reviewers(SpawnChildReviewersParams {
        session: locator.clone(),
        parent_id: register.reviewer_id.clone(),
        count: 1,
        role_id: Some("domain:core-correctness".to_string()),
        worker_kind: Some(WorkerKind::DomainReviewer),
        domain_id: Some(ModuleId::CoreCorrectness),
        language: None,
        module_ids: vec![ModuleId::CoreCorrectness],
        focus_surfaces: vec![SurfaceId::PublicApi],
        claimed_scope: vec!["own core-correctness".to_string()],
        delegated_scope: vec!["do not repeat parent synthesis".to_string()],
    })?;
    let child_id = child.child_ids[0].clone();

    let reports = collect_reports(&locator, ReportView::All, false, false, true, true)?;
    ensure!(reports.reports.len() == 1);
    ensure!(reports.reports[0].reviewer_id == register.reviewer_id);
    let concatenated = reports
        .concatenated_report
        .ok_or_else(|| anyhow::anyhow!("missing concatenated report"))?;
    // Root agent has no artifact yet, so no report.md → not in concatenation.
    // The ledger still has it (reports.reports[0] above).
    ensure!(!concatenated.contains("Agent `root0003`"));
    ensure!(!concatenated.contains(&format!("Agent `{child_id}`")));
    Ok(())
}

#[test]
fn completing_child_review_updates_authored_report_and_final_report() -> anyhow::Result<()> {
    let (_repo_root, repo_root_path, locator, session_dir) = new_session_locator()?;
    let register = register_reviewer(RegisterReviewerParams {
        session: locator.clone(),
        target_ref: "refs/heads/main".to_string(),
        reviewer_id: Some("root0002".to_string()),
        role: Some("final-synthesis".to_string()),
        role_kind: None,
    })?;

    let child = spawn_child_reviewers(SpawnChildReviewersParams {
        session: locator.clone(),
        parent_id: register.reviewer_id.clone(),
        count: 1,
        role_id: Some("domain:core-correctness".to_string()),
        worker_kind: Some(WorkerKind::DomainReviewer),
        domain_id: Some(ModuleId::CoreCorrectness),
        language: None,
        module_ids: vec![ModuleId::CoreCorrectness],
        focus_surfaces: vec![SurfaceId::PublicApi],
        claimed_scope: vec!["own core-correctness".to_string()],
        delegated_scope: vec!["do not repeat parent synthesis".to_string()],
    })?;
    let child_id = child.child_ids[0].clone();
    let child_artifact = minimal_child_findings(&register.session_id, "abc123def456")?;
    let child_artifact_file = session_dir.join("child-findings.toml");
    fs::write(&child_artifact_file, child_artifact.to_toml_string()?)?;
    complete_child_review(ReviewerArtifactParams {
        session: locator.clone(),
        reviewer_id: child_id.clone(),
        artifact_file: child_artifact_file,
    })?;

    let parent_artifact = minimal_parent_review(&register.session_id, "def456abc789")?;
    let parent_artifact_file = session_dir.join("parent-review.toml");
    fs::write(&parent_artifact_file, parent_artifact.to_toml_string()?)?;
    mpcr::session::finalize_review(ReviewerArtifactParams {
        session: locator.clone(),
        reviewer_id: register.reviewer_id.clone(),
        artifact_file: parent_artifact_file,
    })?;

    let session = load_session(&locator)?;
    let child_report_path = session
        .reviews
        .iter()
        .find(|review| review.reviewer_id == child_id)
        .and_then(|review| review.report_path.clone())
        .ok_or_else(|| anyhow::anyhow!("missing child report path"))?;
    let child_report = fs::read_to_string(repo_root_path.join(child_report_path))?;
    ensure!(child_report.contains("# Agent Report"));
    ensure!(child_report.contains("## Findings"));

    let final_report_path = session
        .final_report_path
        .ok_or_else(|| anyhow::anyhow!("missing final report path"))?;
    let final_report = fs::read_to_string(repo_root_path.join(final_report_path))?;
    ensure!(final_report.contains(&format!("Agent `{}`", register.reviewer_id)));
    ensure!(final_report.contains(&format!("Agent `{child_id}`")));
    ensure!(final_report.contains("### Agent Report"));
    ensure!(!final_report.contains("\n# Agent Report"));
    let root_pos = final_report
        .find(&format!("Agent `{}`", register.reviewer_id))
        .ok_or_else(|| anyhow::anyhow!("missing root agent heading"))?;
    let child_pos = final_report
        .find(&format!("Agent `{child_id}`"))
        .ok_or_else(|| anyhow::anyhow!("missing child agent heading"))?;
    ensure!(root_pos < child_pos);

    let root_ledger: Value = serde_json::from_str(&fs::read_to_string(
        repo_root_path.join(register.agent_ledger_json),
    )?)?;
    ensure!(root_ledger["counters"]["local_artifact_count"].as_u64() == Some(1));
    ensure!(root_ledger["counters"]["recursive_artifact_count"].as_u64() == Some(2));
    ensure!(root_ledger["counters"]["child_count"].as_u64() == Some(1));
    ensure!(root_ledger["counters"]["descendant_count"].as_u64() == Some(1));
    ensure!(root_ledger["counters"]["recursive_report_count"].as_u64() == Some(2));

    let child_ledger: Value = serde_json::from_str(&fs::read_to_string(
        repo_root_path.join(&child.child_agent_ledgers_json[0]),
    )?)?;
    ensure!(child_ledger["counters"]["local_artifact_count"].as_u64() == Some(1));
    ensure!(child_ledger["counters"]["recursive_artifact_count"].as_u64() == Some(1));
    ensure!(child_ledger["counters"]["local_report_count"].as_u64() == Some(1));
    ensure!(child_ledger["counters"]["recursive_report_count"].as_u64() == Some(1));
    ensure!(child_ledger["counters"]["local_findings"].as_u64() == Some(0));
    Ok(())
}

#[test]
fn concatenated_reports_demote_hand_authored_headings() -> anyhow::Result<()> {
    let (_repo_root, repo_root_path, locator, _session_dir) = new_session_locator()?;
    let register = register_reviewer(RegisterReviewerParams {
        session: locator.clone(),
        target_ref: "refs/heads/main".to_string(),
        reviewer_id: Some("root0006".to_string()),
        role: Some("final-synthesis".to_string()),
        role_kind: None,
    })?;

    let report_path = repo_root_path
        .join(register.agent_dir.clone())
        .join("report.md");
    fs::write(
        &report_path,
        "# Custom Review\n\n## Findings\n\n- Hand authored.\n",
    )?;

    let reports = collect_reports(&locator, ReportView::All, true, true, true, true)?;
    let concatenated = reports
        .concatenated_report
        .ok_or_else(|| anyhow::anyhow!("missing concatenated report"))?;
    ensure!(concatenated.contains("## Agent `root0006`"));
    ensure!(concatenated.contains("### Custom Review"));
    ensure!(concatenated.contains("#### Findings"));
    ensure!(!concatenated.contains("\n# Custom Review"));
    ensure!(!concatenated.contains("\n## Findings"));
    Ok(())
}

#[test]
fn complete_child_review_rejects_open_descendant_reviewers() -> anyhow::Result<()> {
    let (_repo_root, _repo_root_path, locator, session_dir) = new_session_locator()?;
    let register = register_reviewer(RegisterReviewerParams {
        session: locator.clone(),
        target_ref: "refs/heads/main".to_string(),
        reviewer_id: Some("root0004".to_string()),
        role: Some("final-synthesis".to_string()),
        role_kind: None,
    })?;

    let child = spawn_child_reviewers(SpawnChildReviewersParams {
        session: locator.clone(),
        parent_id: register.reviewer_id.clone(),
        count: 1,
        role_id: Some("domain:core-correctness".to_string()),
        worker_kind: Some(WorkerKind::DomainReviewer),
        domain_id: Some(ModuleId::CoreCorrectness),
        language: None,
        module_ids: vec![ModuleId::CoreCorrectness],
        focus_surfaces: vec![SurfaceId::PublicApi],
        claimed_scope: vec!["own core-correctness".to_string()],
        delegated_scope: vec!["do not repeat parent synthesis".to_string()],
    })?;
    let child_id = child.child_ids[0].clone();

    let grandchild = spawn_child_reviewers(SpawnChildReviewersParams {
        session: locator.clone(),
        parent_id: child_id.clone(),
        count: 1,
        role_id: Some("language-research:rust".to_string()),
        worker_kind: Some(WorkerKind::LanguageResearch),
        domain_id: None,
        language: Some("rust".to_string()),
        module_ids: Vec::new(),
        focus_surfaces: vec![SurfaceId::PublicApi],
        claimed_scope: vec!["collect rust guidance".to_string()],
        delegated_scope: vec!["do not redo parent domain investigation".to_string()],
    })?;
    let grandchild_id = grandchild.child_ids[0].clone();

    let child_artifact = minimal_child_findings(&register.session_id, "abc123def456")?;
    let child_artifact_file = session_dir.join("child-findings-open-descendant.toml");
    fs::write(&child_artifact_file, child_artifact.to_toml_string()?)?;
    let err = expect_error(
        complete_child_review(ReviewerArtifactParams {
            session: locator,
            reviewer_id: child_id,
            artifact_file: child_artifact_file,
        }),
        "complete_child_review should reject open descendants",
    )?;
    let err_text = format!("{err:#}");
    ensure!(err_text.contains("cannot finalize child_findings"));
    ensure!(err_text.contains(&grandchild_id));
    Ok(())
}

#[test]
fn complete_child_review_rejects_mismatched_registered_worker_contract() -> anyhow::Result<()> {
    let (_repo_root, _repo_root_path, locator, session_dir) = new_session_locator()?;
    let register = register_reviewer(RegisterReviewerParams {
        session: locator.clone(),
        target_ref: "refs/heads/main".to_string(),
        reviewer_id: Some("root0010".to_string()),
        role: Some("final-synthesis".to_string()),
        role_kind: None,
    })?;

    let child = spawn_child_reviewers(SpawnChildReviewersParams {
        session: locator.clone(),
        parent_id: register.reviewer_id,
        count: 1,
        role_id: Some("domain:core-correctness".to_string()),
        worker_kind: Some(WorkerKind::DomainReviewer),
        domain_id: Some(ModuleId::CoreCorrectness),
        language: None,
        module_ids: vec![ModuleId::CoreCorrectness],
        focus_surfaces: vec![SurfaceId::PublicApi],
        claimed_scope: vec!["own core-correctness".to_string()],
        delegated_scope: vec!["do not repeat parent synthesis".to_string()],
    })?;

    let mismatched = ArtifactDocument::ChildFindings(ChildFindingsArtifact {
        header: reviewer_header(
            ArtifactKind::ChildFindings,
            "bad123def456",
            &register.session_id,
            ProducerKind::ReviewComposite,
        )?,
        worker_kind: WorkerKind::ReviewComposite,
        role_id: Some("review-composite".to_string()),
        language: None,
        module_ids: vec![ModuleId::CoreCorrectness, ModuleId::ShipReadiness],
        claimed_scope: vec!["single-worker direct review".to_string()],
        delegated_scope: Vec::new(),
        research_refs: Vec::new(),
        findings: Vec::new(),
        defended_checks: Vec::new(),
        residual_risks: Vec::new(),
        route_revision_refs: Vec::new(),
    });
    let artifact_file = session_dir.join("child-findings-mismatched-contract.toml");
    fs::write(&artifact_file, mismatched.to_toml_string()?)?;
    let err = expect_error(
        complete_child_review(ReviewerArtifactParams {
            session: locator,
            reviewer_id: child.child_ids[0].clone(),
            artifact_file,
        }),
        "complete_child_review should reject a mismatched worker contract",
    )?;
    let err_text = format!("{err:#}");
    ensure!(err_text.contains("did not match registered reviewer"));
    Ok(())
}

#[test]
fn finalize_review_rejects_open_descendant_reviewers() -> anyhow::Result<()> {
    let (_repo_root, _repo_root_path, locator, session_dir) = new_session_locator()?;
    let register = register_reviewer(RegisterReviewerParams {
        session: locator.clone(),
        target_ref: "refs/heads/main".to_string(),
        reviewer_id: Some("root0005".to_string()),
        role: Some("final-synthesis".to_string()),
        role_kind: None,
    })?;

    let completed_child = spawn_child_reviewers(SpawnChildReviewersParams {
        session: locator.clone(),
        parent_id: register.reviewer_id.clone(),
        count: 1,
        role_id: Some("domain:core-correctness".to_string()),
        worker_kind: Some(WorkerKind::DomainReviewer),
        domain_id: Some(ModuleId::CoreCorrectness),
        language: None,
        module_ids: vec![ModuleId::CoreCorrectness],
        focus_surfaces: vec![SurfaceId::PublicApi],
        claimed_scope: vec!["own core-correctness".to_string()],
        delegated_scope: vec!["do not repeat parent synthesis".to_string()],
    })?;
    let completed_child_id = completed_child.child_ids[0].clone();

    let open_child = spawn_child_reviewers(SpawnChildReviewersParams {
        session: locator.clone(),
        parent_id: register.reviewer_id.clone(),
        count: 1,
        role_id: Some("domain:tests".to_string()),
        worker_kind: Some(WorkerKind::DomainReviewer),
        domain_id: Some(ModuleId::Tests),
        language: None,
        module_ids: vec![ModuleId::Tests],
        focus_surfaces: vec![SurfaceId::TestCoverage],
        claimed_scope: vec!["own tests".to_string()],
        delegated_scope: vec!["do not repeat parent synthesis".to_string()],
    })?;
    let open_child_id = open_child.child_ids[0].clone();

    let child_artifact = minimal_child_findings(&register.session_id, "bcd234efa567")?;
    let child_artifact_file = session_dir.join("child-findings-completed.toml");
    fs::write(&child_artifact_file, child_artifact.to_toml_string()?)?;
    complete_child_review(ReviewerArtifactParams {
        session: locator.clone(),
        reviewer_id: completed_child_id,
        artifact_file: child_artifact_file,
    })?;

    let parent_artifact = minimal_parent_review(&register.session_id, "cde345fab678")?;
    let parent_artifact_file = session_dir.join("parent-review-open-child.toml");
    fs::write(&parent_artifact_file, parent_artifact.to_toml_string()?)?;
    let err = expect_error(
        finalize_review(ReviewerArtifactParams {
            session: locator,
            reviewer_id: register.reviewer_id,
            artifact_file: parent_artifact_file,
        }),
        "finalize_review should reject open descendants",
    )?;
    let err_text = format!("{err:#}");
    ensure!(err_text.contains("cannot finalize parent_review"));
    ensure!(err_text.contains(&open_child_id));
    Ok(())
}

#[test]
fn finalize_review_rejects_cancelled_descendant_reviewers() -> anyhow::Result<()> {
    let (_repo_root, _repo_root_path, locator, session_dir) = new_session_locator()?;
    let register = register_reviewer(RegisterReviewerParams {
        session: locator.clone(),
        target_ref: "refs/heads/main".to_string(),
        reviewer_id: Some("root0011".to_string()),
        role: Some("final-synthesis".to_string()),
        role_kind: None,
    })?;

    let child = spawn_child_reviewers(SpawnChildReviewersParams {
        session: locator.clone(),
        parent_id: register.reviewer_id.clone(),
        count: 1,
        role_id: Some("domain:core-correctness".to_string()),
        worker_kind: Some(WorkerKind::DomainReviewer),
        domain_id: Some(ModuleId::CoreCorrectness),
        language: None,
        module_ids: vec![ModuleId::CoreCorrectness],
        focus_surfaces: vec![SurfaceId::PublicApi],
        claimed_scope: vec!["own core-correctness".to_string()],
        delegated_scope: vec!["do not repeat parent synthesis".to_string()],
    })?;
    let child_id = child.child_ids[0].clone();

    update_review(UpdateReviewParams {
        session: locator.clone(),
        reviewer_id: child_id.clone(),
        status: ReviewProcessStatus::Cancelled,
        phase: Some("aborted-child".to_string()),
    })?;

    let parent_artifact = minimal_parent_review(&register.session_id, "cfe456abd789")?;
    let parent_artifact_file = session_dir.join("parent-review-cancelled-child.toml");
    fs::write(&parent_artifact_file, parent_artifact.to_toml_string()?)?;
    let err = expect_error(
        finalize_review(ReviewerArtifactParams {
            session: locator,
            reviewer_id: register.reviewer_id,
            artifact_file: parent_artifact_file,
        }),
        "finalize_review should reject cancelled descendants",
    )?;
    let err_text = format!("{err:#}");
    ensure!(err_text.contains("cannot finalize parent_review"));
    ensure!(err_text.contains(&child_id));
    ensure!(err_text.contains("cancelled"));
    Ok(())
}

#[test]
fn finalize_review_requires_child_matching_latest_route_contract() -> anyhow::Result<()> {
    let (_repo_root, _repo_root_path, locator, session_dir) = new_session_locator()?;
    let register = register_reviewer(RegisterReviewerParams {
        session: locator.clone(),
        target_ref: "refs/heads/main".to_string(),
        reviewer_id: Some("root0012".to_string()),
        role: Some("final-synthesis".to_string()),
        role_kind: None,
    })?;

    let initial_route = persist_reviewer_route(
        &locator,
        "refs/heads/main",
        &register.session_id,
        &["src/api.rs"],
    )?;
    let initial_worker = initial_route
        .worker_plan
        .iter()
        .find(|worker| worker.role_id.as_deref() == Some("domain:core-correctness"))
        .cloned()
        .ok_or_else(|| anyhow::anyhow!("missing core-correctness worker"))?;
    let stale_child = spawn_child_reviewers(SpawnChildReviewersParams {
        session: locator.clone(),
        parent_id: register.reviewer_id.clone(),
        count: 1,
        role_id: initial_worker.role_id.clone(),
        worker_kind: Some(initial_worker.worker_kind),
        domain_id: Some(ModuleId::CoreCorrectness),
        language: None,
        module_ids: initial_worker.module_ids.clone(),
        focus_surfaces: initial_worker.focus_surfaces.clone(),
        claimed_scope: initial_worker.claimed_scope.clone(),
        delegated_scope: initial_worker.delegated_scope.clone(),
    })?;
    let stale_child_id = stale_child.child_ids[0].clone();

    let child_artifact =
        child_findings_for_worker(&register.session_id, "ccd234efa567", &initial_worker)?;
    let child_artifact_file = session_dir.join("child-findings-stale-contract.toml");
    fs::write(&child_artifact_file, child_artifact.to_toml_string()?)?;
    complete_child_review(ReviewerArtifactParams {
        session: locator.clone(),
        reviewer_id: stale_child_id,
        artifact_file: child_artifact_file,
    })?;

    let revised_route = persist_reviewer_route(
        &locator,
        "refs/heads/main",
        &register.session_id,
        &["src/api.rs", "src/auth.rs"],
    )?;

    for (index, worker) in revised_route.worker_plan.iter().enumerate() {
        if worker.role_id.as_deref() == Some("domain:core-correctness") {
            continue;
        }
        let spawned = spawn_child_reviewers(SpawnChildReviewersParams {
            session: locator.clone(),
            parent_id: register.reviewer_id.clone(),
            count: 1,
            role_id: worker.role_id.clone(),
            worker_kind: Some(worker.worker_kind),
            domain_id: worker.module_ids.first().copied(),
            language: worker.language.clone(),
            module_ids: worker.module_ids.clone(),
            focus_surfaces: worker.focus_surfaces.clone(),
            claimed_scope: worker.claimed_scope.clone(),
            delegated_scope: worker.delegated_scope.clone(),
        })?;
        let artifact = child_findings_for_worker(
            &register.session_id,
            &format!("{:012x}", 0xabc000 + index),
            worker,
        )?;
        let artifact_file = session_dir.join(format!("child-findings-revised-{index}.toml"));
        fs::write(&artifact_file, artifact.to_toml_string()?)?;
        complete_child_review(ReviewerArtifactParams {
            session: locator.clone(),
            reviewer_id: spawned.child_ids[0].clone(),
            artifact_file,
        })?;
    }

    let parent_artifact = minimal_parent_review(&register.session_id, "dde345fab678")?;
    let parent_artifact_file = session_dir.join("parent-review-stale-contract.toml");
    fs::write(&parent_artifact_file, parent_artifact.to_toml_string()?)?;
    let err = expect_error(
        finalize_review(ReviewerArtifactParams {
            session: locator.clone(),
            reviewer_id: register.reviewer_id.clone(),
            artifact_file: parent_artifact_file.clone(),
        }),
        "finalize_review should reject stale routed child assignments",
    )?;
    let err_text = format!("{err:#}");
    ensure!(err_text.contains("cannot finalize parent_review before every required routed worker"));
    ensure!(err_text.contains("domain:core-correctness"));

    let revised_worker = revised_route
        .worker_plan
        .iter()
        .find(|worker| worker.role_id.as_deref() == Some("domain:core-correctness"))
        .cloned()
        .ok_or_else(|| anyhow::anyhow!("missing revised core-correctness worker"))?;
    let revised_child = spawn_child_reviewers(SpawnChildReviewersParams {
        session: locator.clone(),
        parent_id: register.reviewer_id.clone(),
        count: 1,
        role_id: revised_worker.role_id.clone(),
        worker_kind: Some(revised_worker.worker_kind),
        domain_id: Some(ModuleId::CoreCorrectness),
        language: None,
        module_ids: revised_worker.module_ids.clone(),
        focus_surfaces: revised_worker.focus_surfaces.clone(),
        claimed_scope: revised_worker.claimed_scope.clone(),
        delegated_scope: revised_worker.delegated_scope.clone(),
    })?;
    let revised_child_id = revised_child.child_ids[0].clone();

    let revised_child_artifact =
        child_findings_for_worker(&register.session_id, "eed456abc789", &revised_worker)?;
    let revised_child_artifact_file = session_dir.join("child-findings-revised-contract.toml");
    fs::write(
        &revised_child_artifact_file,
        revised_child_artifact.to_toml_string()?,
    )?;
    complete_child_review(ReviewerArtifactParams {
        session: locator.clone(),
        reviewer_id: revised_child_id,
        artifact_file: revised_child_artifact_file,
    })?;

    finalize_review(ReviewerArtifactParams {
        session: locator,
        reviewer_id: register.reviewer_id,
        artifact_file: parent_artifact_file,
    })?;
    Ok(())
}

#[test]
fn finalize_review_keeps_open_stale_children_blocking_parent_close() -> anyhow::Result<()> {
    let (_repo_root, _repo_root_path, locator, session_dir) = new_session_locator()?;
    let register = register_reviewer(RegisterReviewerParams {
        session: locator.clone(),
        target_ref: "refs/heads/main".to_string(),
        reviewer_id: Some("root0016".to_string()),
        role: Some("final-synthesis".to_string()),
        role_kind: None,
    })?;

    let initial_route = persist_reviewer_route(
        &locator,
        "refs/heads/main",
        &register.session_id,
        &["src/api.rs"],
    )?;
    let initial_worker = initial_route
        .worker_plan
        .iter()
        .find(|worker| worker.role_id.as_deref() == Some("domain:core-correctness"))
        .cloned()
        .ok_or_else(|| anyhow::anyhow!("missing core-correctness worker"))?;
    let stale_child = spawn_child_reviewers(SpawnChildReviewersParams {
        session: locator.clone(),
        parent_id: register.reviewer_id.clone(),
        count: 1,
        role_id: initial_worker.role_id.clone(),
        worker_kind: Some(initial_worker.worker_kind),
        domain_id: Some(ModuleId::CoreCorrectness),
        language: None,
        module_ids: initial_worker.module_ids.clone(),
        focus_surfaces: initial_worker.focus_surfaces.clone(),
        claimed_scope: initial_worker.claimed_scope.clone(),
        delegated_scope: initial_worker.delegated_scope.clone(),
    })?;
    let stale_child_id = stale_child.child_ids[0].clone();

    let revised_route = persist_reviewer_route(
        &locator,
        "refs/heads/main",
        &register.session_id,
        &["src/api.rs", "src/auth.rs"],
    )?;
    for (index, worker) in revised_route.worker_plan.iter().enumerate() {
        let spawned = spawn_child_reviewers(SpawnChildReviewersParams {
            session: locator.clone(),
            parent_id: register.reviewer_id.clone(),
            count: 1,
            role_id: worker.role_id.clone(),
            worker_kind: Some(worker.worker_kind),
            domain_id: worker.module_ids.first().copied(),
            language: worker.language.clone(),
            module_ids: worker.module_ids.clone(),
            focus_surfaces: worker.focus_surfaces.clone(),
            claimed_scope: worker.claimed_scope.clone(),
            delegated_scope: worker.delegated_scope.clone(),
        })?;
        let artifact = child_findings_for_worker(
            &register.session_id,
            &format!("{:012x}", 0xdef000 + index),
            worker,
        )?;
        let artifact_file = session_dir.join(format!("child-findings-open-stale-{index}.toml"));
        fs::write(&artifact_file, artifact.to_toml_string()?)?;
        complete_child_review(ReviewerArtifactParams {
            session: locator.clone(),
            reviewer_id: spawned.child_ids[0].clone(),
            artifact_file,
        })?;
    }

    let parent_artifact = minimal_parent_review(&register.session_id, "def678cab901")?;
    let parent_artifact_file = session_dir.join("parent-review-open-stale.toml");
    fs::write(&parent_artifact_file, parent_artifact.to_toml_string()?)?;
    let err = expect_error(
        finalize_review(ReviewerArtifactParams {
            session: locator,
            reviewer_id: register.reviewer_id,
            artifact_file: parent_artifact_file,
        }),
        "finalize_review should still reject open stale descendants",
    )?;
    let err_text = format!("{err:#}");
    ensure!(
        err_text.contains("cannot finalize parent_review while descendant reviewers remain open")
    );
    ensure!(err_text.contains(&stale_child_id));
    Ok(())
}

#[test]
fn spawn_child_reviewers_rejects_multi_role_strings() -> anyhow::Result<()> {
    let (_repo_root, _repo_root_path, locator, _session_dir) = new_session_locator()?;
    let register = register_reviewer(RegisterReviewerParams {
        session: locator.clone(),
        target_ref: "refs/heads/main".to_string(),
        reviewer_id: Some("root0003".to_string()),
        role: None,
        role_kind: None,
    })?;

    let err = expect_error(
        spawn_child_reviewers(SpawnChildReviewersParams {
            session: locator,
            parent_id: register.reviewer_id,
            count: 1,
            role_id: Some("language-detector domain:core-correctness".to_string()),
            worker_kind: None,
            domain_id: None,
            language: None,
            module_ids: Vec::new(),
            focus_surfaces: Vec::new(),
            claimed_scope: Vec::new(),
            delegated_scope: Vec::new(),
        }),
        "expected whitespace role to be rejected",
    )?;

    ensure!(err.to_string().contains("single role slug"));
    Ok(())
}

#[test]
fn verify_application_requires_matching_application_result() -> anyhow::Result<()> {
    let (_repo_root, _repo_root_path, locator, session_dir) = new_session_locator()?;
    let register = register_reviewer(RegisterReviewerParams {
        session: locator.clone(),
        target_ref: "refs/heads/main".to_string(),
        reviewer_id: Some("root0012".to_string()),
        role: Some("final-synthesis".to_string()),
        role_kind: None,
    })?;

    let verification_only = ArtifactDocument::VerificationResult(VerificationResultArtifact {
        header: applicator_header(
            ArtifactKind::VerificationResult,
            "abc123def456",
            &register.session_id,
            ProducerKind::ApplicatorVerifier,
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
    let verification_only_file = session_dir.join("verification-only.toml");
    fs::write(&verification_only_file, verification_only.to_toml_string()?)?;
    let err = expect_error(
        verify_application(ApplicatorArtifactParams {
            session: locator.clone(),
            artifact_file: verification_only_file,
        }),
        "verify_application should require a finalized application_result",
    )?;
    ensure!(err
        .to_string()
        .contains("requires a finalized application_result"));

    let application = ArtifactDocument::ApplicationResult(ApplicationResultArtifact {
        header: applicator_header(
            ArtifactKind::ApplicationResult,
            "abc456def789",
            &register.session_id,
            ProducerKind::ApplicatorWorker,
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
    let application_file = session_dir.join("application-result.toml");
    fs::write(&application_file, application.to_toml_string()?)?;
    finalize_application(ApplicatorArtifactParams {
        session: locator.clone(),
        artifact_file: application_file,
    })?;

    let mismatched_verification =
        ArtifactDocument::VerificationResult(VerificationResultArtifact {
            header: applicator_header(
                ArtifactKind::VerificationResult,
                "def456abc123",
                &register.session_id,
                ProducerKind::ApplicatorVerifier,
            )?,
            verified_items: vec![VerificationItemRecord {
                finding_id: "F999".to_string(),
                status: VerificationStatus::Yes,
                notes: "verified".to_string(),
            }],
            failed_items: Vec::new(),
            partial_items: Vec::new(),
            residual_risks: Vec::new(),
        });
    let mismatched_file = session_dir.join("verification-mismatched.toml");
    fs::write(&mismatched_file, mismatched_verification.to_toml_string()?)?;
    let err = expect_error(
        verify_application(ApplicatorArtifactParams {
            session: locator,
            artifact_file: mismatched_file,
        }),
        "verify_application should reject finding ids outside application_result",
    )?;
    ensure!(err
        .to_string()
        .contains("did not match application_result.verification_needed"));
    Ok(())
}
