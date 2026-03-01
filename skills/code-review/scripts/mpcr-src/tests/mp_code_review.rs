//! Integration tests for `mpcr` session coordination primitives.

use anyhow::{bail, ensure};
use mpcr::lock::{self, LockConfig};
use mpcr::report_validation::ReportValidationKind;
use mpcr::session::{
    collect_reports, finalize_review, load_session, register_reviewer, set_initiator_status,
    FinalizeReportInput, FinalizeReviewParams, InitiatorStatus, NoteRole, NoteType,
    RegisterReviewerParams, ReportsFilters, ReportsOptions, ReportsView, ReviewEntry, ReviewPhase,
    ReviewVerdict, ReviewerStatus, SessionFile, SessionLocator, SessionNote,
    SetInitiatorStatusParams, SeverityCounts,
};
use serde_json::Value;
use std::fs;
use std::path::Path;
use time::format_description::well_known::Rfc3339;
use time::OffsetDateTime;

fn valid_parent_report(
    reviewer_id: &str,
    session_id: &str,
    target_ref: &str,
    counts: SeverityCounts,
) -> String {
    let source_ref = format!("child:feedface:{session_id}");
    let mut merged_findings = String::new();
    let mut finding_total = 0u64;
    for (severity, count) in [
        ("BLOCKER", counts.blocker),
        ("MAJOR", counts.major),
        ("MINOR", counts.minor),
        ("NIT", counts.nit),
    ] {
        for _ in 0..count {
            finding_total += 1;
            let line = 10 + finding_total;
            let id = format!("MF{finding_total}");
            merged_findings.push_str(&format!(
                r#"
[[merged_findings]]
id = "{id}"
severity = "{severity}"
anchor = "src/lib.rs:{line}"
claim = "Invariant {id} should hold."
disproof = "Concrete scenario {id} breaks the invariant."
evidence = "Trace for {id} reaches the failing branch."
recommendation = "Apply fix for {id}."
verification = "Add regression coverage for {id}."
source_packets = ["{source_ref}"]
confidence_label = "HIGH"
confidence_score = 90
"#
            ));
        }
    }
    let defended_summary = if finding_total == 0 {
        format!(
            r#"
[[defended_summary]]
theorem_id = "T1"
source_packets = ["{source_ref}"]
summary = "Cross-cutting invariants held during synthesis."
confidence_label = "MEDIUM"
confidence_score = 68
"#
        )
    } else {
        String::new()
    };
    let findings_line = if finding_total == 0 {
        "- None."
    } else {
        "- Synthesized findings remain open."
    };

    format!(
        r#"# Code Review Report

```toml
schema_version = "proof_packet.v2"
artifact_kind = "parent_review_report"
reviewer_id = "{reviewer_id}"
session_id = "{session_id}"
target_ref = "{target_ref}"
verdict = "REQUEST_CHANGES"

[counts]
blocker = {blocker}
major = {major}
minor = {minor}
nit = {nit}

[ship_readiness]
verdict = "SHIP_WITH_FIXES"
confidence_label = "HIGH"
confidence_score = 90

[[ship_readiness_axes]]
axis = "Correctness"
status = "CONDITIONAL"
notes = "One major finding remains open."

[[ship_readiness_axes]]
axis = "Safety"
status = "PASS"
notes = "No direct safety regressions were confirmed."

[[ship_readiness_axes]]
axis = "Complexity budget"
status = "PASS"
notes = "No material complexity increase is required."

[[ship_readiness_axes]]
axis = "Test coverage"
status = "CONDITIONAL"
notes = "A regression test is still needed."

[[ship_readiness_axes]]
axis = "Acceptance criteria"
status = "CONDITIONAL"
notes = "One acceptance criterion still depends on the fix."

[[source_packets]]
reviewer_id = "feedface"
session_id = "{session_id}"
artifact_ref = "child:feedface:{session_id}"
{merged_findings}
{defended_summary}

[[residual_risks]]
area = "Runtime parity"
gap = "No production traffic replay."
impact = "Integration behavior may still differ."
next_action = "Run staging verification."

[validation_summary]
packets_validated = 1
packets_rejected = 0
retry_count = 0
```

## Ship-Readiness
**Verdict:** SHIP_WITH_FIXES

## Findings
{findings_line}

## Defended Proofs
- Token redaction held across tested paths.

## Residual Risk
- Runtime parity remains unverified.
"#,
        blocker = counts.blocker,
        major = counts.major,
        minor = counts.minor,
        nit = counts.nit,
        merged_findings = merged_findings.trim_end(),
        defended_summary = defended_summary.trim_end(),
        findings_line = findings_line
    )
}

#[test]
fn id8_is_8_lower_hex_chars() -> anyhow::Result<()> {
    let id = mpcr::id::random_id8()?;
    ensure!(id.len() == 8);
    ensure!(id.chars().all(|c| matches!(c, '0'..='9' | 'a'..='f')));
    Ok(())
}

#[test]
fn lock_acquire_blocks_until_timeout_then_release() -> anyhow::Result<()> {
    let dir = tempfile::tempdir()?;
    let owner1 = "deadbeef";
    let owner2 = "cafebabe";

    let guard = lock::acquire_lock(
        dir.path(),
        owner1,
        LockConfig {
            max_retries: 0,
            ..LockConfig::default()
        },
    )?;

    let result = lock::acquire_lock(
        dir.path(),
        owner2,
        LockConfig {
            max_retries: 0,
            ..LockConfig::default()
        },
    );
    let Err(err) = result else {
        bail!("second acquire should fail");
    };
    ensure!(
        err.to_string().contains("LOCK_TIMEOUT"),
        "unexpected error: {err:?}"
    );

    guard.release()?;

    let guard2 = lock::acquire_lock(
        dir.path(),
        owner2,
        LockConfig {
            max_retries: 0,
            ..LockConfig::default()
        },
    )?;
    guard2.release()?;

    Ok(())
}

#[test]
fn register_and_finalize_writes_report_and_updates_session() -> anyhow::Result<()> {
    let repo_root = tempfile::tempdir()?;
    let now = OffsetDateTime::parse("2026-01-11T12:34:56.789Z", &Rfc3339)?;
    let session_date = now.date();
    let session = SessionLocator::from_repo_root(repo_root.path(), session_date);

    let reviewer_id = "deadbeef".to_string();
    let session_id = "sess0001".to_string();
    let target_ref = "refs/heads/main".to_string();

    let res = register_reviewer(RegisterReviewerParams {
        repo_root: repo_root.path().to_path_buf(),
        session_date,
        session: session.clone(),
        target_ref: target_ref.clone(),
        reviewer_id: Some(reviewer_id.clone()),
        session_id: Some(session_id.clone()),
        parent_id: None,
        now,
    })?;

    ensure!(Path::new(&res.session_file).exists());

    let session_json = load_session(&session)?;
    ensure!(session_json.reviewers == vec![reviewer_id.clone()]);
    ensure!(session_json.reviews.len() == 1);
    let entry = session_json
        .reviews
        .first()
        .ok_or_else(|| anyhow::anyhow!("expected review entry"))?;
    ensure!(entry.reviewer_id == reviewer_id);
    ensure!(entry.session_id == session_id);
    ensure!(entry.target_ref == target_ref);

    let fin = finalize_review(FinalizeReviewParams {
        session: session.clone(),
        reviewer_id: "deadbeef".to_string(),
        session_id: "sess0001".to_string(),
        verdict: ReviewVerdict::Approve,
        counts: SeverityCounts {
            blocker: 0,
            major: 1,
            minor: 2,
            nit: 3,
        },
        report_input: FinalizeReportInput::Markdown(valid_parent_report(
            "deadbeef",
            "sess0001",
            "refs/heads/main",
            SeverityCounts {
                blocker: 0,
                major: 1,
                minor: 2,
                nit: 3,
            },
        )),
        validation_kind: ReportValidationKind::ParentReviewReport,
        copy_input_report: false,
        auto_close_open_children: true,
        auto_close_children_status: ReviewerStatus::Cancelled,
        now,
    })?;

    ensure!(Path::new(&fin.report_path).exists());
    ensure!(
        fin.report_file
            == ".local/reports/code_reviews/2026-01-11/12-34-56-789_refs_heads_main_deadbeef.md"
    );

    let session_json2 = load_session(&session)?;
    let entry = session_json2
        .reviews
        .first()
        .ok_or_else(|| anyhow::anyhow!("expected review entry"))?;
    ensure!(
        entry.report_file.as_deref()
            == Some(
                ".local/reports/code_reviews/2026-01-11/12-34-56-789_refs_heads_main_deadbeef.md"
            )
    );
    ensure!(entry.finished_at.is_some());
    Ok(())
}

#[test]
fn register_reviewer_does_not_inherit_initiator_status_from_old_session() -> anyhow::Result<()> {
    let repo_root = tempfile::tempdir()?;
    let now = OffsetDateTime::parse("2026-01-11T12:34:56.789Z", &Rfc3339)?;
    let session_date = now.date();
    let session = SessionLocator::from_repo_root(repo_root.path(), session_date);
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

    let params = SetInitiatorStatusParams {
        session: session.clone(),
        reviewer_id: "deadbeef".to_string(),
        session_id: "sess0001".to_string(),
        initiator_status: InitiatorStatus::Applied,
        now,
        lock_owner: "lock0001".to_string(),
    };
    set_initiator_status(&params)?;

    finalize_review(FinalizeReviewParams {
        session: session.clone(),
        reviewer_id: "deadbeef".to_string(),
        session_id: "sess0001".to_string(),
        verdict: ReviewVerdict::Approve,
        counts: SeverityCounts::zero(),
        report_input: FinalizeReportInput::Markdown(valid_parent_report(
            "deadbeef",
            "sess0001",
            "refs/heads/main",
            SeverityCounts::zero(),
        )),
        validation_kind: ReportValidationKind::ParentReviewReport,
        copy_input_report: false,
        auto_close_open_children: true,
        auto_close_children_status: ReviewerStatus::Cancelled,
        now,
    })?;

    register_reviewer(RegisterReviewerParams {
        repo_root: repo_root.path().to_path_buf(),
        session_date,
        session: session.clone(),
        target_ref: "refs/heads/main".to_string(),
        reviewer_id: Some("cafebabe".to_string()),
        session_id: Some("sess0002".to_string()),
        parent_id: None,
        now,
    })?;

    let session_json = load_session(&session)?;
    let entry = session_json
        .reviews
        .iter()
        .find(|r| r.reviewer_id == "cafebabe")
        .ok_or_else(|| anyhow::anyhow!("cafebabe entry should exist"))?;
    ensure!(entry.initiator_status == InitiatorStatus::Requesting);

    Ok(())
}

#[test]
fn applicator_lock_owner_must_be_id8() -> anyhow::Result<()> {
    let repo_root = tempfile::tempdir()?;
    let now = OffsetDateTime::parse("2026-01-11T12:34:56.789Z", &Rfc3339)?;
    let session_date = now.date();
    let session = SessionLocator::from_repo_root(repo_root.path(), session_date);

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

    let params = SetInitiatorStatusParams {
        session,
        reviewer_id: "deadbeef".to_string(),
        session_id: "sess0001".to_string(),
        initiator_status: InitiatorStatus::Reviewed,
        now,
        lock_owner: "not/ok".to_string(),
    };
    let result = set_initiator_status(&params);
    let Err(err) = result else {
        bail!("invalid lock_owner should be rejected");
    };
    ensure!(
        err.to_string().contains("lock_owner"),
        "unexpected error: {err:?}"
    );

    Ok(())
}

#[test]
fn register_reviewer_is_idempotent_for_same_reviewer_and_session() -> anyhow::Result<()> {
    let repo_root = tempfile::tempdir()?;
    let now = OffsetDateTime::parse("2026-01-11T12:34:56.789Z", &Rfc3339)?;
    let session_date = now.date();
    let session = SessionLocator::from_repo_root(repo_root.path(), session_date);

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

    let session_json = load_session(&session)?;
    ensure!(session_json.reviews.len() == 1);
    Ok(())
}

fn reports_fixture(dir: &tempfile::TempDir) -> (SessionLocator, SessionFile) {
    let session_locator = SessionLocator::new(dir.path().to_path_buf());
    let started_at = "2026-01-11T00:00:00Z";
    let updated_at = "2026-01-11T01:00:00Z";
    let note = SessionNote {
        role: NoteRole::Reviewer,
        timestamp: "2026-01-11T01:30:00Z".to_string(),
        note_type: NoteType::Question,
        content: Value::String("need context".to_string()),
    };

    let in_progress = ReviewEntry {
        reviewer_id: "deadbeef".to_string(),
        session_id: "sess0001".to_string(),
        target_ref: "refs/heads/main".to_string(),
        initiator_status: InitiatorStatus::Requesting,
        status: ReviewerStatus::InProgress,
        parent_id: None,
        started_at: started_at.to_string(),
        updated_at: updated_at.to_string(),
        finished_at: None,
        current_phase: Some(ReviewPhase::Ingestion),
        verdict: None,
        counts: SeverityCounts::zero(),
        report_file: None,
        notes: vec![note],
        child_reviews: Vec::new(),
        extra: serde_json::Map::default(),
    };

    let blocked = ReviewEntry {
        reviewer_id: "cafebabe".to_string(),
        session_id: "sess0002".to_string(),
        target_ref: "refs/heads/dev".to_string(),
        initiator_status: InitiatorStatus::Observing,
        status: ReviewerStatus::Blocked,
        parent_id: None,
        started_at: started_at.to_string(),
        updated_at: updated_at.to_string(),
        finished_at: None,
        current_phase: None,
        verdict: None,
        counts: SeverityCounts::zero(),
        report_file: None,
        notes: Vec::new(),
        child_reviews: Vec::new(),
        extra: serde_json::Map::default(),
    };

    let finished = ReviewEntry {
        reviewer_id: "feedface".to_string(),
        session_id: "sess0003".to_string(),
        target_ref: "refs/heads/main".to_string(),
        initiator_status: InitiatorStatus::Received,
        status: ReviewerStatus::Finished,
        parent_id: None,
        started_at: started_at.to_string(),
        updated_at: updated_at.to_string(),
        finished_at: Some("2026-01-11T02:00:00Z".to_string()),
        current_phase: Some(ReviewPhase::ReportWriting),
        verdict: Some(ReviewVerdict::Approve),
        counts: SeverityCounts {
            blocker: 0,
            major: 1,
            minor: 0,
            nit: 0,
        },
        report_file: Some("12-00-00-000_refs_heads_main_feedface.md".to_string()),
        notes: Vec::new(),
        child_reviews: Vec::new(),
        extra: serde_json::Map::default(),
    };

    let session = SessionFile {
        schema_version: "1.2.0".to_string(),
        session_date: "2026-01-11".to_string(),
        repo_root: dir.path().to_string_lossy().to_string(),
        reviewers: vec![
            "deadbeef".to_string(),
            "cafebabe".to_string(),
            "feedface".to_string(),
        ],
        reviews: vec![in_progress, blocked, finished],
        extra: serde_json::Map::new(),
    };

    (session_locator, session)
}

#[test]
fn reports_view_counts() -> anyhow::Result<()> {
    let dir = tempfile::tempdir()?;
    let (session_locator, session) = reports_fixture(&dir);

    let open = collect_reports(
        &session,
        &session_locator,
        ReportsView::Open,
        ReportsFilters::default(),
        ReportsOptions::default(),
    )?;
    ensure!(open.total_reviews == 3);
    ensure!(open.matching_reviews == 2);

    let closed = collect_reports(
        &session,
        &session_locator,
        ReportsView::Closed,
        ReportsFilters::default(),
        ReportsOptions::default(),
    )?;
    ensure!(closed.matching_reviews == 1);

    let in_progress = collect_reports(
        &session,
        &session_locator,
        ReportsView::InProgress,
        ReportsFilters::default(),
        ReportsOptions::default(),
    )?;
    ensure!(in_progress.matching_reviews == 1);

    Ok(())
}

#[test]
fn reports_filters_basic_fields() -> anyhow::Result<()> {
    let dir = tempfile::tempdir()?;
    let (session_locator, session) = reports_fixture(&dir);

    let target_filtered = collect_reports(
        &session,
        &session_locator,
        ReportsView::Open,
        ReportsFilters {
            target_ref: Some("refs/heads/main".to_string()),
            session_id: None,
            reviewer_id: None,
            reviewer_statuses: Vec::new(),
            initiator_statuses: Vec::new(),
            verdicts: Vec::new(),
            phases: Vec::new(),
            only_with_report: false,
            only_with_notes: false,
        },
        ReportsOptions::default(),
    )?;
    ensure!(target_filtered.matching_reviews == 1);

    let status_filtered = collect_reports(
        &session,
        &session_locator,
        ReportsView::Open,
        ReportsFilters {
            target_ref: None,
            session_id: None,
            reviewer_id: None,
            reviewer_statuses: vec![ReviewerStatus::Blocked],
            initiator_statuses: Vec::new(),
            verdicts: Vec::new(),
            phases: Vec::new(),
            only_with_report: false,
            only_with_notes: false,
        },
        ReportsOptions::default(),
    )?;
    ensure!(status_filtered.matching_reviews == 1);

    let initiator_filtered = collect_reports(
        &session,
        &session_locator,
        ReportsView::Open,
        ReportsFilters {
            target_ref: None,
            session_id: None,
            reviewer_id: None,
            reviewer_statuses: Vec::new(),
            initiator_statuses: vec![InitiatorStatus::Observing],
            verdicts: Vec::new(),
            phases: Vec::new(),
            only_with_report: false,
            only_with_notes: false,
        },
        ReportsOptions::default(),
    )?;
    ensure!(initiator_filtered.matching_reviews == 1);

    let verdict_filtered = collect_reports(
        &session,
        &session_locator,
        ReportsView::Closed,
        ReportsFilters {
            target_ref: None,
            session_id: None,
            reviewer_id: None,
            reviewer_statuses: Vec::new(),
            initiator_statuses: Vec::new(),
            verdicts: vec![ReviewVerdict::Approve],
            phases: Vec::new(),
            only_with_report: false,
            only_with_notes: false,
        },
        ReportsOptions::default(),
    )?;
    ensure!(verdict_filtered.matching_reviews == 1);

    let phase_filtered = collect_reports(
        &session,
        &session_locator,
        ReportsView::Open,
        ReportsFilters {
            target_ref: None,
            session_id: None,
            reviewer_id: None,
            reviewer_statuses: Vec::new(),
            initiator_statuses: Vec::new(),
            verdicts: Vec::new(),
            phases: vec![ReviewPhase::Ingestion],
            only_with_report: false,
            only_with_notes: false,
        },
        ReportsOptions::default(),
    )?;
    ensure!(phase_filtered.matching_reviews == 1);

    Ok(())
}

#[test]
fn reports_filters_only_notes_and_report() -> anyhow::Result<()> {
    let dir = tempfile::tempdir()?;
    let (session_locator, session) = reports_fixture(&dir);

    let only_notes = collect_reports(
        &session,
        &session_locator,
        ReportsView::Open,
        ReportsFilters {
            target_ref: None,
            session_id: None,
            reviewer_id: None,
            reviewer_statuses: Vec::new(),
            initiator_statuses: Vec::new(),
            verdicts: Vec::new(),
            phases: Vec::new(),
            only_with_report: false,
            only_with_notes: true,
        },
        ReportsOptions {
            include_notes: true,
            include_report_contents: false,
            include_leaf_children: false,
        },
    )?;
    ensure!(only_notes.matching_reviews == 1);
    let notes_entry = only_notes
        .reviews
        .first()
        .ok_or_else(|| anyhow::anyhow!("expected review entry"))?;
    ensure!(
        notes_entry.notes.as_ref().is_some(),
        "expected notes to be included"
    );

    let only_report = collect_reports(
        &session,
        &session_locator,
        ReportsView::Closed,
        ReportsFilters {
            target_ref: None,
            session_id: None,
            reviewer_id: None,
            reviewer_statuses: Vec::new(),
            initiator_statuses: Vec::new(),
            verdicts: Vec::new(),
            phases: Vec::new(),
            only_with_report: true,
            only_with_notes: false,
        },
        ReportsOptions::default(),
    )?;
    ensure!(only_report.matching_reviews == 1);
    let report_entry = only_report
        .reviews
        .first()
        .ok_or_else(|| anyhow::anyhow!("expected review entry"))?;
    ensure!(
        report_entry.report_path.is_some(),
        "expected report_path to be populated"
    );

    Ok(())
}

#[test]
fn reports_include_report_contents() -> anyhow::Result<()> {
    let dir = tempfile::tempdir()?;
    let session_locator = SessionLocator::new(dir.path().to_path_buf());
    let report_file = "12-00-00-000_refs_heads_main_feedface.md";
    fs::write(dir.path().join(report_file), "final report body")?;

    let finished = ReviewEntry {
        reviewer_id: "feedface".to_string(),
        session_id: "sess0003".to_string(),
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
        report_file: Some(report_file.to_string()),
        notes: Vec::new(),
        child_reviews: Vec::new(),
        extra: serde_json::Map::default(),
    };

    let session = SessionFile {
        schema_version: "1.2.0".to_string(),
        session_date: "2026-01-11".to_string(),
        repo_root: dir.path().to_string_lossy().to_string(),
        reviewers: vec!["feedface".to_string()],
        reviews: vec![finished],
        extra: serde_json::Map::new(),
    };

    let result = collect_reports(
        &session,
        &session_locator,
        ReportsView::Closed,
        ReportsFilters::default(),
        ReportsOptions {
            include_notes: false,
            include_report_contents: true,
            include_leaf_children: false,
        },
    )?;

    ensure!(result.matching_reviews == 1);
    let entry = result
        .reviews
        .first()
        .ok_or_else(|| anyhow::anyhow!("expected report entry"))?;
    ensure!(entry.report_contents.as_deref() == Some("final report body"));
    ensure!(entry.report_error.is_none());

    Ok(())
}
