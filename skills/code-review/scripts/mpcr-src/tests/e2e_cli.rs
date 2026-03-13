#![allow(missing_docs)]
#![allow(clippy::indexing_slicing)]

use anyhow::{ensure, Context};
use mpcr::artifacts::{
    compute_anchor_cluster, compute_fingerprint, ApplicationResultArtifact, ArtifactDocument,
    ArtifactHeader, ArtifactKind, ChildFindingsArtifact, ConfidenceLabel, CoverageSummary,
    Disposition, DispositionRecord, FindingRecord, ModuleId, ParentReviewArtifact, PolicyCategory,
    PolicyRef, PolicyView, ProducerKind, ResidualRiskRecord, ReviewVerdict, Severity,
    ShipReadinessSummary, ShipReadinessVerdict, SurfaceId, VerificationItemRecord,
    VerificationResultArtifact, VerificationStatus, WorkerKind,
};
use mpcr::paths::session_paths;
use serde_json::Value;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, Output};
use tempfile::tempdir;
use time::{Date, Month};

struct ReviewFixture {
    _repo_root: tempfile::TempDir,
    repo_root_path: PathBuf,
    session_dir: PathBuf,
    session_dir_arg: String,
    session_id: String,
    root_id: String,
    child_id: String,
    finding_id: String,
}

fn run_cmd(args: &[String]) -> anyhow::Result<Output> {
    Command::new(env!("CARGO_BIN_EXE_mpcr"))
        .args(args.iter().map(String::as_str))
        .output()
        .with_context(|| format!("run {}", args.join(" ")))
}

fn run_ok(args: &[String]) -> anyhow::Result<Output> {
    let output = run_cmd(args)?;
    ensure!(
        output.status.success(),
        "command failed: {}\nstdout:\n{}\nstderr:\n{}",
        args.join(" "),
        String::from_utf8_lossy(&output.stdout),
        String::from_utf8_lossy(&output.stderr)
    );
    Ok(output)
}

fn run_json(args: &[String]) -> anyhow::Result<Value> {
    let output = run_ok(args)?;
    serde_json::from_slice(&output.stdout).context("parse JSON output")
}

fn session_fixture() -> anyhow::Result<(tempfile::TempDir, PathBuf, PathBuf, String)> {
    let repo_root = tempdir()?;
    let repo_root_path = repo_root.path().to_path_buf();
    let date = Date::from_calendar_date(2026, Month::March, 8)?;
    let session_dir = session_paths(repo_root.path(), date).session_dir;
    let session_dir_arg = session_dir.to_string_lossy().into_owned();
    Ok((repo_root, repo_root_path, session_dir, session_dir_arg))
}

fn policy_ref(mode_id: &str) -> PolicyRef {
    PolicyRef {
        category: PolicyCategory::Mode,
        id: mode_id.to_string(),
        version: "2026.03.08".to_string(),
        view: PolicyView::Checklist,
    }
}

fn header(
    kind: ArtifactKind,
    artifact_id: &str,
    session_id: &str,
    producer: ProducerKind,
    mode_id: &str,
) -> anyhow::Result<ArtifactHeader> {
    ArtifactHeader::new(
        kind,
        artifact_id.to_string(),
        session_id.to_string(),
        "refs/heads/main".to_string(),
        producer,
        "2026-03-08T00:00:00Z".to_string(),
        ConfidenceLabel::High,
        90,
        vec![policy_ref(mode_id)],
    )
}

fn major_finding(finding_id: &str) -> anyhow::Result<FindingRecord> {
    let anchors = vec!["src/lib.rs:12-14".to_string()];
    let anchor_cluster = compute_anchor_cluster(&anchors, Some("critical_path"))?;
    Ok(FindingRecord {
        finding_id: finding_id.to_string(),
        module_id: ModuleId::CoreCorrectness,
        surface_ids: vec![SurfaceId::PublicApi],
        severity: Severity::Major,
        title: "behavior change escapes review boundary".to_string(),
        claim: "the changed behavior can bypass the intended review boundary".to_string(),
        scenario: "a caller reaches the updated path without the expected guard".to_string(),
        evidence:
            "the changed control flow on src/lib.rs reaches the public path without the prior gate"
                .to_string(),
        recommendation: "restore the guard or constrain the exposed path".to_string(),
        verification: "exercise the guarded path and assert the bypass no longer occurs"
            .to_string(),
        anchors,
        symbol_hint: Some("critical_path".to_string()),
        anchor_cluster: anchor_cluster.clone(),
        fingerprint: compute_fingerprint(
            "the changed behavior can bypass the intended review boundary",
            ModuleId::CoreCorrectness,
            &[SurfaceId::PublicApi],
            &anchor_cluster,
        ),
        reopen_eligible: true,
        confidence_label: ConfidenceLabel::High,
        confidence_score: 90,
        evidence_strength: Some(ConfidenceLabel::High),
        false_positive_risk: Some(ConfidenceLabel::Low),
        actionable: Some(true),
        duplicate_suspect: Some(false),
    })
}

fn child_findings_doc(
    session_id: &str,
    artifact_id: &str,
    finding_id: &str,
) -> anyhow::Result<ArtifactDocument> {
    Ok(ArtifactDocument::ChildFindings(ChildFindingsArtifact {
        header: header(
            ArtifactKind::ChildFindings,
            artifact_id,
            session_id,
            ProducerKind::LanguageResearch,
            "reviewer",
        )?,
        worker_kind: WorkerKind::DomainReviewer,
        role_id: Some("domain:core-correctness".to_string()),
        language: Some("rust".to_string()),
        module_ids: vec![ModuleId::CoreCorrectness],
        claimed_scope: vec!["own module `core-correctness`".to_string()],
        delegated_scope: vec!["do not delegate the same domain investigation again".to_string()],
        research_refs: vec!["rust".to_string()],
        findings: vec![major_finding(finding_id)?],
        defended_checks: Vec::new(),
        residual_risks: vec![ResidualRiskRecord {
            risk_id: "R001".to_string(),
            surface_ids: vec![SurfaceId::DocsStaleness],
            summary: "docs must be updated with the restored boundary".to_string(),
            impact: "operators could rely on stale examples".to_string(),
            next_action: "refresh the behavior-facing examples after the code change lands"
                .to_string(),
            reopen_eligible: true,
            confidence_label: ConfidenceLabel::Medium,
            confidence_score: 70,
        }],
        route_revision_refs: Vec::new(),
    }))
}

fn language_research_doc(
    session_id: &str,
    artifact_id: &str,
    language: &str,
    claimed_scope: &str,
) -> anyhow::Result<ArtifactDocument> {
    Ok(ArtifactDocument::ChildFindings(ChildFindingsArtifact {
        header: header(
            ArtifactKind::ChildFindings,
            artifact_id,
            session_id,
            ProducerKind::DomainReviewer,
            "reviewer",
        )?,
        worker_kind: WorkerKind::LanguageResearch,
        role_id: Some(format!("language-research:{language}")),
        language: Some(language.to_string()),
        module_ids: Vec::new(),
        claimed_scope: vec![claimed_scope.to_string()],
        delegated_scope: vec!["do not redo parent domain review".to_string()],
        research_refs: vec![language.to_string()],
        findings: Vec::new(),
        defended_checks: Vec::new(),
        residual_risks: Vec::new(),
        route_revision_refs: Vec::new(),
    }))
}

fn parent_review_doc(
    session_id: &str,
    artifact_id: &str,
    child_artifact_id: &str,
    finding_id: &str,
) -> anyhow::Result<ArtifactDocument> {
    Ok(ArtifactDocument::ParentReview(ParentReviewArtifact {
        header: header(
            ArtifactKind::ParentReview,
            artifact_id,
            session_id,
            ProducerKind::FinalSynthesizer,
            "reviewer",
        )?,
        source_artifact_ids: vec![child_artifact_id.to_string()],
        final_verdict: ReviewVerdict::RequestChanges,
        ship_readiness: ShipReadinessSummary {
            verdict: ShipReadinessVerdict::ShipWithFixes,
            axes: vec!["correctness".to_string(), "docs".to_string()],
            blocking_items: vec!["restore boundary guard".to_string()],
            required_now_count: 1,
            follow_up_count: 0,
        },
        required_now: vec![major_finding(finding_id)?],
        follow_up: Vec::new(),
        defended_summary: Vec::new(),
        residual_risks: vec![ResidualRiskRecord {
            risk_id: "R002".to_string(),
            surface_ids: vec![SurfaceId::DocsStaleness],
            summary: "behavior-facing docs still need refresh".to_string(),
            impact: "operators may follow stale examples".to_string(),
            next_action: "update docs after code fix verification".to_string(),
            reopen_eligible: true,
            confidence_label: ConfidenceLabel::Medium,
            confidence_score: 70,
        }],
        coverage_summary: CoverageSummary {
            changed_files: vec!["src/lib.rs".to_string(), "docs/guide.md".to_string()],
            surfaces_covered: vec![SurfaceId::PublicApi, SurfaceId::DocsStaleness],
            modules_loaded: vec![
                ModuleId::CoreCorrectness,
                ModuleId::DocsStaleness,
                ModuleId::ShipReadiness,
            ],
            tests_run: vec!["cargo test".to_string()],
            tests_not_run_reason: None,
            limitations: Vec::new(),
        },
    }))
}

fn parent_review_doc_with_sources(
    session_id: &str,
    artifact_id: &str,
    source_artifact_ids: Vec<String>,
    finding_id: &str,
) -> anyhow::Result<ArtifactDocument> {
    Ok(ArtifactDocument::ParentReview(ParentReviewArtifact {
        header: header(
            ArtifactKind::ParentReview,
            artifact_id,
            session_id,
            ProducerKind::FinalSynthesizer,
            "reviewer",
        )?,
        source_artifact_ids,
        final_verdict: ReviewVerdict::RequestChanges,
        ship_readiness: ShipReadinessSummary {
            verdict: ShipReadinessVerdict::ShipWithFixes,
            axes: vec!["correctness".to_string(), "docs".to_string()],
            blocking_items: vec!["restore boundary guard".to_string()],
            required_now_count: 1,
            follow_up_count: 0,
        },
        required_now: vec![major_finding(finding_id)?],
        follow_up: Vec::new(),
        defended_summary: Vec::new(),
        residual_risks: vec![ResidualRiskRecord {
            risk_id: "R010".to_string(),
            surface_ids: vec![SurfaceId::DocsStaleness],
            summary: "research and docs updates still need final follow-through".to_string(),
            impact: "operator guidance can lag the restored implementation boundary".to_string(),
            next_action: "merge the code fix and refresh the public docs examples".to_string(),
            reopen_eligible: true,
            confidence_label: ConfidenceLabel::Medium,
            confidence_score: 70,
        }],
        coverage_summary: CoverageSummary {
            changed_files: vec!["src/lib.rs".to_string(), "docs/guide.md".to_string()],
            surfaces_covered: vec![SurfaceId::PublicApi, SurfaceId::DocsStaleness],
            modules_loaded: vec![
                ModuleId::CoreCorrectness,
                ModuleId::DocsStaleness,
                ModuleId::ShipReadiness,
            ],
            tests_run: vec!["cargo test".to_string()],
            tests_not_run_reason: None,
            limitations: Vec::new(),
        },
    }))
}

fn application_result_doc(
    session_id: &str,
    artifact_id: &str,
    finding_id: &str,
) -> anyhow::Result<ArtifactDocument> {
    Ok(ArtifactDocument::ApplicationResult(
        ApplicationResultArtifact {
            header: header(
                ArtifactKind::ApplicationResult,
                artifact_id,
                session_id,
                ProducerKind::ApplicatorWorker,
                "applicator",
            )?,
            source_finding_ids: vec![finding_id.to_string()],
            dispositions: vec![DispositionRecord {
                finding_id: finding_id.to_string(),
                disposition: Disposition::Applied,
                decline_reason_code: None,
                duplicate_reason_code: None,
                detail: "guard restored and public path tightened".to_string(),
                tracking_ref: Some("apply-001".to_string()),
                verification_needed: true,
                evidence_strength: Some(ConfidenceLabel::High),
                false_positive_risk: Some(ConfidenceLabel::Low),
                duplicate_suspect: Some(false),
                stop_recommendation: Some("continue_to_verification".to_string()),
            }],
            modified_files: vec!["src/lib.rs".to_string(), "docs/guide.md".to_string()],
            verification_needed: vec![finding_id.to_string()],
            decline_codes: Vec::new(),
        },
    ))
}

fn verification_result_doc(
    session_id: &str,
    artifact_id: &str,
    finding_id: &str,
    success: bool,
) -> anyhow::Result<ArtifactDocument> {
    let (verified_items, failed_items) = if success {
        (
            vec![VerificationItemRecord {
                finding_id: finding_id.to_string(),
                status: VerificationStatus::Yes,
                notes: "guard behavior verified".to_string(),
            }],
            Vec::new(),
        )
    } else {
        (
            Vec::new(),
            vec![VerificationItemRecord {
                finding_id: finding_id.to_string(),
                status: VerificationStatus::No,
                notes: "regression path still reproduces".to_string(),
            }],
        )
    };
    Ok(ArtifactDocument::VerificationResult(
        VerificationResultArtifact {
            header: header(
                ArtifactKind::VerificationResult,
                artifact_id,
                session_id,
                ProducerKind::ApplicatorVerifier,
                "applicator",
            )?,
            verified_items,
            failed_items,
            partial_items: Vec::new(),
            residual_risks: Vec::new(),
        },
    ))
}

fn write_doc(path: &Path, doc: &ArtifactDocument) -> anyhow::Result<()> {
    fs::write(path, doc.to_toml_string()?).with_context(|| format!("write {}", path.display()))
}

fn establish_review_fixture(route_mode: &str) -> anyhow::Result<ReviewFixture> {
    let (repo_root, repo_root_path, session_dir, session_dir_arg) = session_fixture()?;
    let route = run_json(&vec![
        "--json".to_string(),
        "route".to_string(),
        "--session-dir".to_string(),
        session_dir_arg.clone(),
        "--mode".to_string(),
        route_mode.to_string(),
        "--target-ref".to_string(),
        "refs/heads/main".to_string(),
        "--execution-capability".to_string(),
        "parallel_subagents".to_string(),
        "--max-worker-count".to_string(),
        "4".to_string(),
        "--orchestrator-read-budget-lines".to_string(),
        "120".to_string(),
        "--orchestrator-read-budget-snippets".to_string(),
        "12".to_string(),
        "--changed-file".to_string(),
        "src/lib.rs".to_string(),
        "--changed-file".to_string(),
        "docs/guide.md".to_string(),
        "--behavior-facing-artifact".to_string(),
        "docs/guide.md".to_string(),
        "--persist".to_string(),
    ])?;
    ensure!(route["route_decision"]["worker_plan"]
        .as_array()
        .is_some_and(|workers| workers
            .iter()
            .any(|worker| { worker["worker_kind"].as_str() == Some("language-detector") })));

    let register = run_json(&vec![
        "--json".to_string(),
        "reviewer".to_string(),
        "register".to_string(),
        "--session-dir".to_string(),
        session_dir_arg.clone(),
        "--target-ref".to_string(),
        "refs/heads/main".to_string(),
        "--reviewer-id".to_string(),
        "root0001".to_string(),
    ])?;
    let session_id = register["session_id"]
        .as_str()
        .ok_or_else(|| anyhow::anyhow!("missing session id"))?
        .to_string();
    let root_id = register["reviewer_id"]
        .as_str()
        .ok_or_else(|| anyhow::anyhow!("missing reviewer id"))?
        .to_string();

    run_ok(&vec![
        "--json".to_string(),
        "reviewer".to_string(),
        "update".to_string(),
        "--session-dir".to_string(),
        session_dir_arg.clone(),
        "--reviewer-id".to_string(),
        root_id.clone(),
        "--status".to_string(),
        "in-progress".to_string(),
        "--phase".to_string(),
        "coordinating-review".to_string(),
    ])?;

    let spawn = run_json(&vec![
        "--json".to_string(),
        "reviewer".to_string(),
        "spawn-children".to_string(),
        "--session-dir".to_string(),
        session_dir_arg.clone(),
        "--parent-id".to_string(),
        root_id.clone(),
        "--count".to_string(),
        "1".to_string(),
        "--role-id".to_string(),
        "domain:core-correctness".to_string(),
        "--worker-kind".to_string(),
        "domain-reviewer".to_string(),
        "--domain-id".to_string(),
        "core-correctness".to_string(),
        "--module-id".to_string(),
        "core-correctness".to_string(),
        "--focus-surface".to_string(),
        "public-api".to_string(),
        "--claimed-scope".to_string(),
        "own core-correctness investigation".to_string(),
        "--delegated-scope".to_string(),
        "do not repeat parent synthesis".to_string(),
    ])?;
    let child_id = spawn["child_ids"]
        .as_array()
        .and_then(|values| values.first())
        .and_then(Value::as_str)
        .ok_or_else(|| anyhow::anyhow!("missing child id"))?
        .to_string();

    Ok(ReviewFixture {
        _repo_root: repo_root,
        repo_root_path,
        session_dir,
        session_dir_arg,
        session_id,
        root_id,
        child_id,
        finding_id: "F001".to_string(),
    })
}

fn finalize_review_via_cli(fixture: &ReviewFixture) -> anyhow::Result<()> {
    let dispatch = run_json(&vec![
        "--json".to_string(),
        "protocol".to_string(),
        "dispatch".to_string(),
        "--session-dir".to_string(),
        fixture.session_dir_arg.clone(),
        "--reviewer-id".to_string(),
        fixture.child_id.clone(),
        "--role".to_string(),
        "domain:core-correctness".to_string(),
        "--view".to_string(),
        "checklist".to_string(),
    ])?;
    ensure!(dispatch["agent_dir"].as_str().is_some());
    ensure!(dispatch["report_path"].as_str().is_some());
    ensure!(dispatch["module_ids"]
        .as_array()
        .is_some_and(|modules| modules
            .iter()
            .any(|module| module.as_str() == Some("core-correctness"))));

    let child_doc = child_findings_doc(&fixture.session_id, "a1b2c3d4e5f6", &fixture.finding_id)?;
    let child_file = fixture.session_dir.join("reviewer-child-findings.toml");
    write_doc(&child_file, &child_doc)?;
    run_ok(&vec![
        "validate".to_string(),
        "--artifact-file".to_string(),
        child_file.to_string_lossy().into_owned(),
        "--kind".to_string(),
        "child-findings".to_string(),
        "--layer".to_string(),
        "hard".to_string(),
        "--session-dir".to_string(),
        fixture.session_dir_arg.clone(),
    ])?;
    let child_result = run_json(&vec![
        "--json".to_string(),
        "reviewer".to_string(),
        "complete-child".to_string(),
        "--session-dir".to_string(),
        fixture.session_dir_arg.clone(),
        "--reviewer-id".to_string(),
        fixture.child_id.clone(),
        "--artifact-file".to_string(),
        child_file.to_string_lossy().into_owned(),
    ])?;
    let child_artifact_id = child_result["artifact_id"]
        .as_str()
        .ok_or_else(|| anyhow::anyhow!("missing child artifact id"))?
        .to_string();

    let parent_doc = parent_review_doc(
        &fixture.session_id,
        "b1c2d3e4f5a6",
        &child_artifact_id,
        &fixture.finding_id,
    )?;
    let parent_file = fixture.session_dir.join("reviewer-parent-review.toml");
    write_doc(&parent_file, &parent_doc)?;
    run_ok(&vec![
        "validate".to_string(),
        "--artifact-file".to_string(),
        parent_file.to_string_lossy().into_owned(),
        "--kind".to_string(),
        "parent-review".to_string(),
        "--layer".to_string(),
        "hard".to_string(),
        "--session-dir".to_string(),
        fixture.session_dir_arg.clone(),
    ])?;
    run_ok(&vec![
        "--json".to_string(),
        "reviewer".to_string(),
        "finalize".to_string(),
        "--session-dir".to_string(),
        fixture.session_dir_arg.clone(),
        "--reviewer-id".to_string(),
        fixture.root_id.clone(),
        "--artifact-file".to_string(),
        parent_file.to_string_lossy().into_owned(),
    ])?;
    Ok(())
}

fn drive_applicator_via_cli(
    fixture: &ReviewFixture,
    verification_success: bool,
) -> anyhow::Result<()> {
    let wait = run_json(&vec![
        "--json".to_string(),
        "applicator".to_string(),
        "wait".to_string(),
        "--session-dir".to_string(),
        fixture.session_dir_arg.clone(),
    ])?;
    ensure!(wait["parent_review_ready"].as_bool() == Some(true));

    run_ok(&vec![
        "--json".to_string(),
        "applicator".to_string(),
        "set-status".to_string(),
        "--session-dir".to_string(),
        fixture.session_dir_arg.clone(),
        "--status".to_string(),
        "reviewing".to_string(),
    ])?;

    let app_doc = application_result_doc(&fixture.session_id, "c1d2e3f4a5b6", &fixture.finding_id)?;
    let app_file = fixture.session_dir.join("application-result.toml");
    write_doc(&app_file, &app_doc)?;
    run_ok(&vec![
        "validate".to_string(),
        "--artifact-file".to_string(),
        app_file.to_string_lossy().into_owned(),
        "--kind".to_string(),
        "application-result".to_string(),
        "--layer".to_string(),
        "hard".to_string(),
        "--session-dir".to_string(),
        fixture.session_dir_arg.clone(),
    ])?;
    run_ok(&vec![
        "--json".to_string(),
        "applicator".to_string(),
        "finalize".to_string(),
        "--session-dir".to_string(),
        fixture.session_dir_arg.clone(),
        "--artifact-file".to_string(),
        app_file.to_string_lossy().into_owned(),
    ])?;

    let verify_doc = verification_result_doc(
        &fixture.session_id,
        "d1e2f3a4b5c6",
        &fixture.finding_id,
        verification_success,
    )?;
    let verify_file = fixture.session_dir.join("verification-result.toml");
    write_doc(&verify_file, &verify_doc)?;
    run_ok(&vec![
        "validate".to_string(),
        "--artifact-file".to_string(),
        verify_file.to_string_lossy().into_owned(),
        "--kind".to_string(),
        "verification-result".to_string(),
        "--layer".to_string(),
        "hard".to_string(),
        "--session-dir".to_string(),
        fixture.session_dir_arg.clone(),
    ])?;
    run_ok(&vec![
        "--json".to_string(),
        "applicator".to_string(),
        "verify".to_string(),
        "--session-dir".to_string(),
        fixture.session_dir_arg.clone(),
        "--artifact-file".to_string(),
        verify_file.to_string_lossy().into_owned(),
    ])?;
    Ok(())
}

#[test]
fn reviewer_e2e_cli_builds_recursive_report_tree() -> anyhow::Result<()> {
    let fixture = establish_review_fixture("reviewer")?;
    finalize_review_via_cli(&fixture)?;

    let reports = run_json(&vec![
        "--json".to_string(),
        "session".to_string(),
        "reports".to_string(),
        "--session-dir".to_string(),
        fixture.session_dir_arg.clone(),
        "--recursive".to_string(),
        "--include-leaf-children".to_string(),
        "--include-report-contents".to_string(),
        "--concatenate".to_string(),
    ])?;
    ensure!(reports["reports"]
        .as_array()
        .is_some_and(|reports| reports.len() >= 2));
    ensure!(reports["concatenated_report"]
        .as_str()
        .is_some_and(|body| body.contains(&fixture.root_id) && body.contains(&fixture.child_id)));
    let child_report_entry = reports["reports"]
        .as_array()
        .and_then(|reports| {
            reports
                .iter()
                .find(|report| report["reviewer_id"].as_str() == Some(fixture.child_id.as_str()))
        })
        .ok_or_else(|| anyhow::anyhow!("missing child report entry"))?;
    ensure!(child_report_entry["counters"]["local_findings"].as_u64() == Some(1));
    ensure!(child_report_entry["counters"]["recursive_findings"].as_u64() == Some(1));
    let root_report_entry = reports["reports"]
        .as_array()
        .and_then(|reports| {
            reports
                .iter()
                .find(|report| report["reviewer_id"].as_str() == Some(fixture.root_id.as_str()))
        })
        .ok_or_else(|| anyhow::anyhow!("missing root report entry"))?;
    ensure!(root_report_entry["counters"]["recursive_findings"].as_u64() == Some(1));
    ensure!(root_report_entry["counters"]["recursive_report_count"].as_u64() == Some(2));

    let artifacts = run_json(&vec![
        "--json".to_string(),
        "session".to_string(),
        "artifacts".to_string(),
        "--session-dir".to_string(),
        fixture.session_dir_arg.clone(),
        "--kind".to_string(),
        "parent-review".to_string(),
    ])?;
    ensure!(artifacts
        .as_array()
        .is_some_and(|artifacts| artifacts.len() == 1));

    let session = run_json(&vec![
        "--json".to_string(),
        "session".to_string(),
        "show".to_string(),
        "--session-dir".to_string(),
        fixture.session_dir_arg.clone(),
    ])?;
    let final_report_path = session["final_report_path"]
        .as_str()
        .ok_or_else(|| anyhow::anyhow!("missing final report path"))?;
    ensure!(fixture.repo_root_path.join(final_report_path).exists());
    let final_report = fs::read_to_string(fixture.repo_root_path.join(final_report_path))?;
    ensure!(final_report.contains(&format!("Agent `{}`", fixture.root_id)));
    ensure!(final_report.contains(&format!("Agent `{}`", fixture.child_id)));
    ensure!(session["counters"]["total_agents"].as_u64() == Some(2));
    ensure!(session["counters"]["completed_agents"].as_u64() == Some(2));
    ensure!(session["counters"]["report_count"].as_u64() == Some(2));
    ensure!(session["counters"]["artifact_count"].as_u64() == Some(4));
    let root_ledger_path = session["reviews"]
        .as_array()
        .and_then(|reviews| {
            reviews
                .iter()
                .find(|review| review["reviewer_id"].as_str() == Some(fixture.root_id.as_str()))
        })
        .and_then(|review| review["agent_ledger_json"].as_str())
        .ok_or_else(|| anyhow::anyhow!("missing root agent ledger path"))?;
    let child_agent_dir = session["reviews"]
        .as_array()
        .and_then(|reviews| {
            reviews
                .iter()
                .find(|review| review["reviewer_id"].as_str() == Some(fixture.child_id.as_str()))
        })
        .and_then(|review| review["agent_dir"].as_str())
        .ok_or_else(|| anyhow::anyhow!("missing child agent dir"))?;
    ensure!(fixture
        .repo_root_path
        .join(child_agent_dir)
        .join("report.md")
        .exists());
    let child_ledger_path = session["reviews"]
        .as_array()
        .and_then(|reviews| {
            reviews
                .iter()
                .find(|review| review["reviewer_id"].as_str() == Some(fixture.child_id.as_str()))
        })
        .and_then(|review| review["agent_ledger_json"].as_str())
        .ok_or_else(|| anyhow::anyhow!("missing child agent ledger path"))?;
    let child_ledger: Value = serde_json::from_str(&fs::read_to_string(
        fixture.repo_root_path.join(child_ledger_path),
    )?)?;
    ensure!(child_ledger["status"].as_str() == Some("completed"));
    ensure!(child_ledger["report_path"].as_str().is_some());
    ensure!(child_ledger["counters"]["local_artifact_count"].as_u64() == Some(1));
    ensure!(child_ledger["counters"]["recursive_artifact_count"].as_u64() == Some(1));
    ensure!(child_ledger["counters"]["child_count"].as_u64() == Some(0));
    ensure!(child_ledger["counters"]["descendant_count"].as_u64() == Some(0));
    ensure!(child_ledger["counters"]["local_report_count"].as_u64() == Some(1));
    ensure!(child_ledger["counters"]["recursive_report_count"].as_u64() == Some(1));
    ensure!(child_ledger["counters"]["local_findings"].as_u64() == Some(1));
    ensure!(child_ledger["counters"]["recursive_findings"].as_u64() == Some(1));
    ensure!(child_ledger["counters"]["local_severity_totals"]["major"].as_u64() == Some(1));
    let root_ledger: Value = serde_json::from_str(&fs::read_to_string(
        fixture.repo_root_path.join(root_ledger_path),
    )?)?;
    ensure!(root_ledger["status"].as_str() == Some("completed"));
    ensure!(root_ledger["counters"]["local_artifact_count"].as_u64() == Some(1));
    ensure!(
        root_ledger["counters"]["recursive_artifact_count"].as_u64()
            == session["counters"]["artifact_count"].as_u64()
    );
    ensure!(root_ledger["counters"]["child_count"].as_u64() == Some(1));
    ensure!(root_ledger["counters"]["descendant_count"].as_u64() == Some(1));
    ensure!(root_ledger["counters"]["local_report_count"].as_u64() == Some(1));
    ensure!(root_ledger["counters"]["recursive_report_count"].as_u64() == Some(2));
    ensure!(root_ledger["counters"]["local_findings"].as_u64() == Some(0));
    ensure!(root_ledger["counters"]["recursive_findings"].as_u64() == Some(1));
    ensure!(root_ledger["counters"]["recursive_severity_totals"]["major"].as_u64() == Some(1));
    let final_summary_json = session["final_summary_json_path"]
        .as_str()
        .ok_or_else(|| anyhow::anyhow!("missing final summary json path"))?;
    let final_summary: Value = serde_json::from_str(&fs::read_to_string(
        fixture.repo_root_path.join(final_summary_json),
    )?)?;
    ensure!(final_summary["total_agents"].as_u64() == Some(2));
    ensure!(final_summary["completed_agents"].as_u64() == Some(2));
    ensure!(final_summary["report_count"].as_u64() == Some(2));
    Ok(())
}

#[test]
fn recursive_fanout_fanin_e2e_cli_updates_nested_ledgers() -> anyhow::Result<()> {
    let (repo_root, repo_root_path, session_dir, session_dir_arg) = session_fixture()?;
    let route = run_json(&vec![
        "--json".to_string(),
        "route".to_string(),
        "--session-dir".to_string(),
        session_dir_arg.clone(),
        "--mode".to_string(),
        "reviewer".to_string(),
        "--target-ref".to_string(),
        "refs/heads/main".to_string(),
        "--execution-capability".to_string(),
        "parallel_subagents".to_string(),
        "--max-worker-count".to_string(),
        "6".to_string(),
        "--orchestrator-read-budget-lines".to_string(),
        "120".to_string(),
        "--orchestrator-read-budget-snippets".to_string(),
        "12".to_string(),
        "--changed-file".to_string(),
        "src/lib.rs".to_string(),
        "--changed-file".to_string(),
        "docs/guide.md".to_string(),
        "--behavior-facing-artifact".to_string(),
        "docs/guide.md".to_string(),
        "--persist".to_string(),
    ])?;
    ensure!(route["route_decision"]["worker_plan"]
        .as_array()
        .is_some_and(|workers| workers.len() >= 4));

    let register = run_json(&vec![
        "--json".to_string(),
        "reviewer".to_string(),
        "register".to_string(),
        "--session-dir".to_string(),
        session_dir_arg.clone(),
        "--target-ref".to_string(),
        "refs/heads/main".to_string(),
        "--reviewer-id".to_string(),
        "root0101".to_string(),
    ])?;
    let session_id = register["session_id"]
        .as_str()
        .ok_or_else(|| anyhow::anyhow!("missing session id"))?
        .to_string();
    let root_id = register["reviewer_id"]
        .as_str()
        .ok_or_else(|| anyhow::anyhow!("missing root reviewer id"))?
        .to_string();
    run_ok(&vec![
        "--json".to_string(),
        "reviewer".to_string(),
        "update".to_string(),
        "--session-dir".to_string(),
        session_dir_arg.clone(),
        "--reviewer-id".to_string(),
        root_id.clone(),
        "--status".to_string(),
        "in-progress".to_string(),
        "--phase".to_string(),
        "coordinating-multi-branch-review".to_string(),
    ])?;

    let domain_spawn = run_json(&vec![
        "--json".to_string(),
        "reviewer".to_string(),
        "spawn-children".to_string(),
        "--session-dir".to_string(),
        session_dir_arg.clone(),
        "--parent-id".to_string(),
        root_id.clone(),
        "--count".to_string(),
        "1".to_string(),
        "--role-id".to_string(),
        "domain:core-correctness".to_string(),
        "--worker-kind".to_string(),
        "domain-reviewer".to_string(),
        "--domain-id".to_string(),
        "core-correctness".to_string(),
        "--module-id".to_string(),
        "core-correctness".to_string(),
        "--focus-surface".to_string(),
        "public-api".to_string(),
        "--claimed-scope".to_string(),
        "own boundary investigation".to_string(),
        "--delegated-scope".to_string(),
        "do not repeat root synthesis".to_string(),
    ])?;
    let domain_child_id = domain_spawn["child_ids"]
        .as_array()
        .and_then(|values| values.first())
        .and_then(Value::as_str)
        .ok_or_else(|| anyhow::anyhow!("missing domain child id"))?
        .to_string();

    let research_spawn = run_json(&vec![
        "--json".to_string(),
        "reviewer".to_string(),
        "spawn-children".to_string(),
        "--session-dir".to_string(),
        session_dir_arg.clone(),
        "--parent-id".to_string(),
        root_id.clone(),
        "--count".to_string(),
        "1".to_string(),
        "--role-id".to_string(),
        "language-research:rust".to_string(),
        "--worker-kind".to_string(),
        "language-research".to_string(),
        "--language".to_string(),
        "rust".to_string(),
        "--focus-surface".to_string(),
        "public-api".to_string(),
        "--claimed-scope".to_string(),
        "collect rust guidance for this review".to_string(),
        "--delegated-scope".to_string(),
        "do not repeat root synthesis".to_string(),
    ])?;
    let research_child_id = research_spawn["child_ids"]
        .as_array()
        .and_then(|values| values.first())
        .and_then(Value::as_str)
        .ok_or_else(|| anyhow::anyhow!("missing research child id"))?
        .to_string();

    let grandchild_spawn = run_json(&vec![
        "--json".to_string(),
        "reviewer".to_string(),
        "spawn-children".to_string(),
        "--session-dir".to_string(),
        session_dir_arg.clone(),
        "--parent-id".to_string(),
        domain_child_id.clone(),
        "--count".to_string(),
        "1".to_string(),
        "--role-id".to_string(),
        "language-research:rust".to_string(),
        "--worker-kind".to_string(),
        "language-research".to_string(),
        "--language".to_string(),
        "rust".to_string(),
        "--focus-surface".to_string(),
        "public-api".to_string(),
        "--claimed-scope".to_string(),
        "collect rust guidance for the boundary helper".to_string(),
        "--delegated-scope".to_string(),
        "do not redo parent boundary investigation".to_string(),
    ])?;
    let grandchild_id = grandchild_spawn["child_ids"]
        .as_array()
        .and_then(|values| values.first())
        .and_then(Value::as_str)
        .ok_or_else(|| anyhow::anyhow!("missing grandchild id"))?
        .to_string();

    let domain_dispatch = run_json(&vec![
        "--json".to_string(),
        "protocol".to_string(),
        "dispatch".to_string(),
        "--session-dir".to_string(),
        session_dir_arg.clone(),
        "--reviewer-id".to_string(),
        domain_child_id.clone(),
        "--role".to_string(),
        "domain:core-correctness".to_string(),
        "--view".to_string(),
        "checklist".to_string(),
    ])?;
    ensure!(domain_dispatch["content"]
        .as_str()
        .is_some_and(|content| content.contains("keep the orchestrator thin")));
    ensure!(domain_dispatch["content"]
        .as_str()
        .is_some_and(|content| content.contains("claim the parent scope first")));

    let research_dispatch = run_json(&vec![
        "--json".to_string(),
        "protocol".to_string(),
        "dispatch".to_string(),
        "--session-dir".to_string(),
        session_dir_arg.clone(),
        "--reviewer-id".to_string(),
        research_child_id.clone(),
        "--role".to_string(),
        "language-research:rust".to_string(),
        "--view".to_string(),
        "checklist".to_string(),
    ])?;
    ensure!(research_dispatch["agent_dir"].as_str().is_some());
    ensure!(research_dispatch["lineage"]
        .as_array()
        .is_some_and(|lineage| lineage.len() == 2));

    let grandchild_dispatch = run_json(&vec![
        "--json".to_string(),
        "protocol".to_string(),
        "dispatch".to_string(),
        "--session-dir".to_string(),
        session_dir_arg.clone(),
        "--reviewer-id".to_string(),
        grandchild_id.clone(),
        "--role".to_string(),
        "language-research:rust".to_string(),
        "--view".to_string(),
        "checklist".to_string(),
    ])?;
    ensure!(grandchild_dispatch["lineage"]
        .as_array()
        .is_some_and(|lineage| lineage.len() == 3));

    let grandchild_doc = language_research_doc(
        &session_id,
        "ea11bb22cc33",
        "rust",
        "collect rust guidance for the boundary helper",
    )?;
    let grandchild_file = session_dir.join("grandchild-language-research.toml");
    write_doc(&grandchild_file, &grandchild_doc)?;
    run_ok(&vec![
        "validate".to_string(),
        "--artifact-file".to_string(),
        grandchild_file.to_string_lossy().into_owned(),
        "--kind".to_string(),
        "child-findings".to_string(),
        "--layer".to_string(),
        "hard".to_string(),
        "--session-dir".to_string(),
        session_dir_arg.clone(),
    ])?;
    let grandchild_result = run_json(&vec![
        "--json".to_string(),
        "reviewer".to_string(),
        "complete-child".to_string(),
        "--session-dir".to_string(),
        session_dir_arg.clone(),
        "--reviewer-id".to_string(),
        grandchild_id.clone(),
        "--artifact-file".to_string(),
        grandchild_file.to_string_lossy().into_owned(),
    ])?;
    let grandchild_artifact_id = grandchild_result["artifact_id"]
        .as_str()
        .ok_or_else(|| anyhow::anyhow!("missing grandchild artifact id"))?
        .to_string();

    let research_doc = language_research_doc(
        &session_id,
        "dd44ee55ff66",
        "rust",
        "collect rust guidance for this review",
    )?;
    let research_file = session_dir.join("research-child-findings.toml");
    write_doc(&research_file, &research_doc)?;
    run_ok(&vec![
        "validate".to_string(),
        "--artifact-file".to_string(),
        research_file.to_string_lossy().into_owned(),
        "--kind".to_string(),
        "child-findings".to_string(),
        "--layer".to_string(),
        "hard".to_string(),
        "--session-dir".to_string(),
        session_dir_arg.clone(),
    ])?;
    let research_result = run_json(&vec![
        "--json".to_string(),
        "reviewer".to_string(),
        "complete-child".to_string(),
        "--session-dir".to_string(),
        session_dir_arg.clone(),
        "--reviewer-id".to_string(),
        research_child_id.clone(),
        "--artifact-file".to_string(),
        research_file.to_string_lossy().into_owned(),
    ])?;
    let research_artifact_id = research_result["artifact_id"]
        .as_str()
        .ok_or_else(|| anyhow::anyhow!("missing research artifact id"))?
        .to_string();

    let domain_doc = child_findings_doc(&session_id, "aa77bb88cc99", "F100")?;
    let domain_file = session_dir.join("domain-child-findings.toml");
    write_doc(&domain_file, &domain_doc)?;
    run_ok(&vec![
        "validate".to_string(),
        "--artifact-file".to_string(),
        domain_file.to_string_lossy().into_owned(),
        "--kind".to_string(),
        "child-findings".to_string(),
        "--layer".to_string(),
        "hard".to_string(),
        "--session-dir".to_string(),
        session_dir_arg.clone(),
    ])?;
    let domain_result = run_json(&vec![
        "--json".to_string(),
        "reviewer".to_string(),
        "complete-child".to_string(),
        "--session-dir".to_string(),
        session_dir_arg.clone(),
        "--reviewer-id".to_string(),
        domain_child_id.clone(),
        "--artifact-file".to_string(),
        domain_file.to_string_lossy().into_owned(),
    ])?;
    let domain_artifact_id = domain_result["artifact_id"]
        .as_str()
        .ok_or_else(|| anyhow::anyhow!("missing domain artifact id"))?
        .to_string();

    let parent_doc = parent_review_doc_with_sources(
        &session_id,
        "ff0011223344",
        vec![
            domain_artifact_id.clone(),
            research_artifact_id.clone(),
            grandchild_artifact_id.clone(),
        ],
        "F100",
    )?;
    let parent_file = session_dir.join("root-parent-review.toml");
    write_doc(&parent_file, &parent_doc)?;
    run_ok(&vec![
        "validate".to_string(),
        "--artifact-file".to_string(),
        parent_file.to_string_lossy().into_owned(),
        "--kind".to_string(),
        "parent-review".to_string(),
        "--layer".to_string(),
        "hard".to_string(),
        "--session-dir".to_string(),
        session_dir_arg.clone(),
    ])?;
    run_ok(&vec![
        "--json".to_string(),
        "reviewer".to_string(),
        "finalize".to_string(),
        "--session-dir".to_string(),
        session_dir_arg.clone(),
        "--reviewer-id".to_string(),
        root_id.clone(),
        "--artifact-file".to_string(),
        parent_file.to_string_lossy().into_owned(),
    ])?;

    let reports = run_json(&vec![
        "--json".to_string(),
        "session".to_string(),
        "reports".to_string(),
        "--session-dir".to_string(),
        session_dir_arg.clone(),
        "--recursive".to_string(),
        "--include-report-contents".to_string(),
        "--concatenate".to_string(),
    ])?;
    ensure!(reports["reports"]
        .as_array()
        .is_some_and(|reports| reports.len() == 4));
    ensure!(reports["concatenated_report"].as_str().is_some_and(|body| {
        body.contains(&root_id)
            && body.contains(&domain_child_id)
            && body.contains(&research_child_id)
            && body.contains(&grandchild_id)
    }));

    let session = run_json(&vec![
        "--json".to_string(),
        "session".to_string(),
        "show".to_string(),
        "--session-dir".to_string(),
        session_dir_arg.clone(),
    ])?;
    ensure!(session["counters"]["total_agents"].as_u64() == Some(4));
    ensure!(session["counters"]["completed_agents"].as_u64() == Some(4));
    ensure!(session["counters"]["report_count"].as_u64() == Some(4));
    ensure!(session["counters"]["artifact_count"].as_u64() == Some(6));
    ensure!(session["counters"]["severity_totals"]["major"].as_u64() == Some(1));

    let root_ledger_path = session["reviews"]
        .as_array()
        .and_then(|reviews| {
            reviews
                .iter()
                .find(|review| review["reviewer_id"].as_str() == Some(root_id.as_str()))
        })
        .and_then(|review| review["agent_ledger_json"].as_str())
        .ok_or_else(|| anyhow::anyhow!("missing root ledger"))?;
    let domain_ledger_path = session["reviews"]
        .as_array()
        .and_then(|reviews| {
            reviews
                .iter()
                .find(|review| review["reviewer_id"].as_str() == Some(domain_child_id.as_str()))
        })
        .and_then(|review| review["agent_ledger_json"].as_str())
        .ok_or_else(|| anyhow::anyhow!("missing domain child ledger"))?;
    let research_ledger_path = session["reviews"]
        .as_array()
        .and_then(|reviews| {
            reviews
                .iter()
                .find(|review| review["reviewer_id"].as_str() == Some(research_child_id.as_str()))
        })
        .and_then(|review| review["agent_ledger_json"].as_str())
        .ok_or_else(|| anyhow::anyhow!("missing research child ledger"))?;
    let grandchild_ledger_path = session["reviews"]
        .as_array()
        .and_then(|reviews| {
            reviews
                .iter()
                .find(|review| review["reviewer_id"].as_str() == Some(grandchild_id.as_str()))
        })
        .and_then(|review| review["agent_ledger_json"].as_str())
        .ok_or_else(|| anyhow::anyhow!("missing grandchild ledger"))?;

    let root_ledger: Value =
        serde_json::from_str(&fs::read_to_string(repo_root_path.join(root_ledger_path))?)?;
    ensure!(root_ledger["counters"]["child_count"].as_u64() == Some(2));
    ensure!(root_ledger["counters"]["descendant_count"].as_u64() == Some(3));
    ensure!(root_ledger["counters"]["recursive_artifact_count"].as_u64() == Some(6));
    ensure!(root_ledger["counters"]["recursive_report_count"].as_u64() == Some(4));
    ensure!(root_ledger["counters"]["recursive_findings"].as_u64() == Some(1));

    let domain_ledger: Value = serde_json::from_str(&fs::read_to_string(
        repo_root_path.join(domain_ledger_path),
    )?)?;
    ensure!(domain_ledger["counters"]["child_count"].as_u64() == Some(1));
    ensure!(domain_ledger["counters"]["descendant_count"].as_u64() == Some(1));
    ensure!(domain_ledger["counters"]["recursive_artifact_count"].as_u64() == Some(2));
    ensure!(domain_ledger["counters"]["recursive_report_count"].as_u64() == Some(2));
    ensure!(domain_ledger["counters"]["local_findings"].as_u64() == Some(1));
    ensure!(domain_ledger["counters"]["recursive_findings"].as_u64() == Some(1));

    let research_ledger: Value = serde_json::from_str(&fs::read_to_string(
        repo_root_path.join(research_ledger_path),
    )?)?;
    ensure!(research_ledger["role_kind"].as_str() == Some("language_research"));
    ensure!(research_ledger["counters"]["recursive_artifact_count"].as_u64() == Some(1));
    ensure!(research_ledger["counters"]["recursive_findings"].as_u64() == Some(0));

    let grandchild_ledger: Value = serde_json::from_str(&fs::read_to_string(
        repo_root_path.join(grandchild_ledger_path),
    )?)?;
    ensure!(grandchild_ledger["counters"]["child_count"].as_u64() == Some(0));
    ensure!(grandchild_ledger["counters"]["descendant_count"].as_u64() == Some(0));
    ensure!(grandchild_ledger["counters"]["recursive_artifact_count"].as_u64() == Some(1));
    ensure!(grandchild_ledger["counters"]["recursive_report_count"].as_u64() == Some(1));

    let grandchild_agent_dir = session["reviews"]
        .as_array()
        .and_then(|reviews| {
            reviews
                .iter()
                .find(|review| review["reviewer_id"].as_str() == Some(grandchild_id.as_str()))
        })
        .and_then(|review| review["agent_dir"].as_str())
        .ok_or_else(|| anyhow::anyhow!("missing grandchild agent dir"))?;
    ensure!(grandchild_agent_dir.contains(&format!(
        "/children/{domain_child_id}/children/{grandchild_id}"
    )));
    ensure!(repo_root_path
        .join(grandchild_agent_dir)
        .join("report.md")
        .exists());

    let final_report_path = session["final_report_path"]
        .as_str()
        .ok_or_else(|| anyhow::anyhow!("missing final report path"))?;
    let final_report = fs::read_to_string(repo_root_path.join(final_report_path))?;
    ensure!(final_report.contains(&format!("Agent `{root_id}`")));
    ensure!(final_report.contains(&format!("Agent `{domain_child_id}`")));
    ensure!(final_report.contains(&format!("Agent `{research_child_id}`")));
    ensure!(final_report.contains(&format!("Agent `{grandchild_id}`")));

    let final_summary_json = session["final_summary_json_path"]
        .as_str()
        .ok_or_else(|| anyhow::anyhow!("missing final summary json path"))?;
    let final_summary: Value = serde_json::from_str(&fs::read_to_string(
        repo_root_path.join(final_summary_json),
    )?)?;
    ensure!(final_summary["total_agents"].as_u64() == Some(4));
    ensure!(final_summary["completed_agents"].as_u64() == Some(4));
    ensure!(final_summary["report_count"].as_u64() == Some(4));

    drop(repo_root);
    Ok(())
}

#[test]
fn applicator_e2e_cli_persists_application_and_verification() -> anyhow::Result<()> {
    let fixture = establish_review_fixture("reviewer")?;
    finalize_review_via_cli(&fixture)?;
    drive_applicator_via_cli(&fixture, true)?;

    let session = run_json(&vec![
        "--json".to_string(),
        "session".to_string(),
        "show".to_string(),
        "--session-dir".to_string(),
        fixture.session_dir_arg.clone(),
    ])?;
    ensure!(session["applicator"]["status"].as_str() == Some("completed"));
    ensure!(session["applicator"]["application_result_id"]
        .as_str()
        .is_some());
    ensure!(session["applicator"]["verification_result_id"]
        .as_str()
        .is_some());
    ensure!(session["counters"]["artifact_count"].as_u64() == Some(6));
    ensure!(session["counters"]["applied_findings"].as_u64() == Some(1));
    ensure!(session["counters"]["declined_findings"].as_u64() == Some(0));
    let root_ledger_path = session["reviews"]
        .as_array()
        .and_then(|reviews| {
            reviews
                .iter()
                .find(|review| review["reviewer_id"].as_str() == Some(fixture.root_id.as_str()))
        })
        .and_then(|review| review["agent_ledger_json"].as_str())
        .ok_or_else(|| anyhow::anyhow!("missing root agent ledger path"))?;
    let child_ledger_path = session["reviews"]
        .as_array()
        .and_then(|reviews| {
            reviews
                .iter()
                .find(|review| review["reviewer_id"].as_str() == Some(fixture.child_id.as_str()))
        })
        .and_then(|review| review["agent_ledger_json"].as_str())
        .ok_or_else(|| anyhow::anyhow!("missing child agent ledger path"))?;

    let artifacts = run_json(&vec![
        "--json".to_string(),
        "session".to_string(),
        "artifacts".to_string(),
        "--session-dir".to_string(),
        fixture.session_dir_arg.clone(),
        "--kind".to_string(),
        "application-result".to_string(),
    ])?;
    ensure!(artifacts
        .as_array()
        .is_some_and(|artifacts| artifacts.len() == 1));

    let metrics = run_json(&vec![
        "--json".to_string(),
        "session".to_string(),
        "metrics".to_string(),
        "--session-dir".to_string(),
        fixture.session_dir_arg.clone(),
    ])?;
    ensure!(metrics["verification_outcome"]["yes"].as_u64() == Some(1));
    let root_ledger: Value = serde_json::from_str(&fs::read_to_string(
        fixture.repo_root_path.join(root_ledger_path),
    )?)?;
    ensure!(
        root_ledger["counters"]["recursive_artifact_count"].as_u64()
            == session["counters"]["artifact_count"].as_u64()
    );
    ensure!(root_ledger["counters"]["recursive_applied_findings"].as_u64() == Some(1));
    ensure!(root_ledger["counters"]["recursive_declined_findings"].as_u64() == Some(0));
    let child_ledger: Value = serde_json::from_str(&fs::read_to_string(
        fixture.repo_root_path.join(child_ledger_path),
    )?)?;
    ensure!(child_ledger["counters"]["recursive_applied_findings"].as_u64() == Some(0));
    let final_summary_json = session["final_summary_json_path"]
        .as_str()
        .ok_or_else(|| anyhow::anyhow!("missing final summary json path"))?;
    let final_summary: Value = serde_json::from_str(&fs::read_to_string(
        fixture.repo_root_path.join(final_summary_json),
    )?)?;
    ensure!(final_summary["applied_findings"].as_u64() == Some(1));
    Ok(())
}

#[test]
fn fullcycle_e2e_cli_plans_checkpoints_and_loads_state() -> anyhow::Result<()> {
    let fixture = establish_review_fixture("full-cycle")?;
    finalize_review_via_cli(&fixture)?;
    drive_applicator_via_cli(&fixture, false)?;

    let plan_file = fixture.session_dir.join("convergence-state.toml");
    let plan = run_json(&vec![
        "--json".to_string(),
        "fullcycle".to_string(),
        "plan".to_string(),
        "--session-dir".to_string(),
        fixture.session_dir_arg.clone(),
        "--output".to_string(),
        plan_file.to_string_lossy().into_owned(),
    ])?;
    ensure!(plan["stop_condition"].as_str() == Some("reopen_required"));
    ensure!(plan["reopen_triggers"]
        .as_array()
        .is_some_and(|triggers| !triggers.is_empty()));
    ensure!(plan_file.exists());

    let checkpoint = run_json(&vec![
        "--json".to_string(),
        "fullcycle".to_string(),
        "checkpoint".to_string(),
        "--session-dir".to_string(),
        fixture.session_dir_arg.clone(),
        "--artifact-file".to_string(),
        plan_file.to_string_lossy().into_owned(),
    ])?;
    ensure!(checkpoint["artifact_kind"].as_str() == Some("convergence_state"));

    let state = run_json(&vec![
        "--json".to_string(),
        "fullcycle".to_string(),
        "state".to_string(),
        "--session-dir".to_string(),
        fixture.session_dir_arg.clone(),
    ])?;
    ensure!(state["stop_condition"].as_str() == Some("reopen_required"));
    ensure!(state["cycle_index"].as_u64().is_some());

    let artifacts = run_json(&vec![
        "--json".to_string(),
        "session".to_string(),
        "artifacts".to_string(),
        "--session-dir".to_string(),
        fixture.session_dir_arg.clone(),
        "--kind".to_string(),
        "convergence-state".to_string(),
    ])?;
    ensure!(artifacts
        .as_array()
        .is_some_and(|artifacts| artifacts.len() == 1));
    let session = run_json(&vec![
        "--json".to_string(),
        "session".to_string(),
        "show".to_string(),
        "--session-dir".to_string(),
        fixture.session_dir_arg.clone(),
    ])?;
    ensure!(session["counters"]["artifact_count"].as_u64() == Some(7));
    ensure!(session["counters"]["reopen_triggers"].as_u64() == Some(3));
    let root_ledger_path = session["reviews"]
        .as_array()
        .and_then(|reviews| {
            reviews
                .iter()
                .find(|review| review["reviewer_id"].as_str() == Some(fixture.root_id.as_str()))
        })
        .and_then(|review| review["agent_ledger_json"].as_str())
        .ok_or_else(|| anyhow::anyhow!("missing root agent ledger path"))?;
    let child_ledger_path = session["reviews"]
        .as_array()
        .and_then(|reviews| {
            reviews
                .iter()
                .find(|review| review["reviewer_id"].as_str() == Some(fixture.child_id.as_str()))
        })
        .and_then(|review| review["agent_ledger_json"].as_str())
        .ok_or_else(|| anyhow::anyhow!("missing child agent ledger path"))?;
    let root_ledger: Value = serde_json::from_str(&fs::read_to_string(
        fixture.repo_root_path.join(root_ledger_path),
    )?)?;
    ensure!(
        root_ledger["counters"]["recursive_artifact_count"].as_u64()
            == session["counters"]["artifact_count"].as_u64()
    );
    ensure!(root_ledger["counters"]["recursive_applied_findings"].as_u64() == Some(1));
    ensure!(root_ledger["counters"]["recursive_reopen_triggers"].as_u64() == Some(3));
    let child_ledger: Value = serde_json::from_str(&fs::read_to_string(
        fixture.repo_root_path.join(child_ledger_path),
    )?)?;
    ensure!(child_ledger["counters"]["recursive_reopen_triggers"].as_u64() == Some(0));
    let final_summary_json = session["final_summary_json_path"]
        .as_str()
        .ok_or_else(|| anyhow::anyhow!("missing final summary json path"))?;
    let final_summary: Value = serde_json::from_str(&fs::read_to_string(
        fixture.repo_root_path.join(final_summary_json),
    )?)?;
    ensure!(final_summary["reopen_triggers"].as_u64() == Some(3));
    Ok(())
}
