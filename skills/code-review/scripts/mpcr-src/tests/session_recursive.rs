#![allow(missing_docs)]
#![allow(clippy::all, clippy::pedantic, clippy::nursery, clippy::cargo)]
#![allow(clippy::indexing_slicing)]

use anyhow::ensure;
use mpcr::artifacts::{
    ArtifactDocument, ArtifactHeader, ArtifactKind, ChildFindingsArtifact, ConfidenceLabel,
    CoverageSummary, ModuleId, ParentReviewArtifact, PolicyCategory, PolicyRef, PolicyView,
    ProducerKind, ReviewVerdict, ShipReadinessSummary, ShipReadinessVerdict, SurfaceId, WorkerKind,
};
use mpcr::paths::{self, session_paths, StorageFormat};
use mpcr::session::{
    collect_reports, complete_child_review, load_session, register_reviewer, spawn_child_reviewers,
    update_review, RegisterReviewerParams, ReportView, ReviewProcessStatus, ReviewerArtifactParams,
    SessionLedger, SessionLocator, SpawnChildReviewersParams, UpdateReviewParams,
};
use serde_json::Value;
use std::fs;
use std::path::PathBuf;
use tempfile::tempdir;
use time::{Date, Month};

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
    ensure!(concatenated.contains("Agent `root0001`"));
    ensure!(concatenated.contains(&format!("Agent `{child_id}`")));

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
    ensure!(concatenated.contains("Agent `root0003`"));
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
