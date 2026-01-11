//! Integration tests for `mpcr` session coordination primitives.

use mpcr::lock::{self, LockConfig};
use mpcr::session::{
    collect_reports, finalize_review, register_reviewer, set_initiator_status, FinalizeReviewParams,
    InitiatorStatus, NoteRole, NoteType, RegisterReviewerParams, ReportsFilters, ReportsOptions,
    ReportsView, ReviewEntry, ReviewPhase, ReviewVerdict, ReviewerStatus, SessionFile,
    SessionLocator, SessionNote, SetInitiatorStatusParams, SeverityCounts,
};
use serde_json::Value;
use std::fs;
use std::path::Path;
use time::format_description::well_known::Rfc3339;
use time::OffsetDateTime;

#[test]
fn id8_is_8_lower_hex_chars() -> anyhow::Result<()> {
    let id = mpcr::id::random_id8()?;
    assert_eq!(id.len(), 8);
    assert!(id.chars().all(|c| matches!(c, '0'..='9' | 'a'..='f')));
    Ok(())
}

#[test]
fn lock_acquire_blocks_until_timeout_then_release() -> anyhow::Result<()> {
    let dir = tempfile::tempdir()?;
    let owner1 = "deadbeef";
    let owner2 = "cafebabe";

    let guard = lock::acquire_lock(dir.path(), owner1, LockConfig { max_retries: 0 })?;

    let err = lock::acquire_lock(dir.path(), owner2, LockConfig { max_retries: 0 })
        .expect_err("second acquire should fail");
    assert!(
        err.to_string().contains("LOCK_TIMEOUT"),
        "unexpected error: {err:?}"
    );

    guard.release()?;

    let guard2 = lock::acquire_lock(dir.path(), owner2, LockConfig { max_retries: 0 })?;
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

    assert!(Path::new(&res.session_file).exists());

    let raw = fs::read_to_string(session.session_file())?;
    let session_json: SessionFile = serde_json::from_str(&raw)?;
    assert_eq!(session_json.reviewers, vec![reviewer_id.clone()]);
    assert_eq!(session_json.reviews.len(), 1);
    assert_eq!(session_json.reviews[0].reviewer_id, reviewer_id);
    assert_eq!(session_json.reviews[0].session_id, session_id);
    assert_eq!(session_json.reviews[0].target_ref, target_ref);

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
        report_markdown: "hello\n".to_string(),
        now,
    })?;

    assert!(Path::new(&fin.report_path).exists());
    assert_eq!(
        fin.report_file,
        "12-34-56-789_refs_heads_main_deadbeef.md".to_string()
    );

    let raw2 = fs::read_to_string(session.session_file())?;
    let session_json2: SessionFile = serde_json::from_str(&raw2)?;
    let entry = &session_json2.reviews[0];
    assert_eq!(
        entry.report_file.as_deref(),
        Some("12-34-56-789_refs_heads_main_deadbeef.md")
    );
    assert!(entry.finished_at.is_some());
    Ok(())
}

#[test]
fn register_reviewer_does_not_inherit_initiator_status_from_old_session() -> anyhow::Result<()> {
    let repo_root = tempfile::tempdir()?;
    let now = OffsetDateTime::parse("2026-01-11T12:34:56.789Z", &Rfc3339)?;
    let session_date = now.date();
    let session = SessionLocator::from_repo_root(repo_root.path(), session_date);
    let target_ref = "refs/heads/main".to_string();

    register_reviewer(RegisterReviewerParams {
        repo_root: repo_root.path().to_path_buf(),
        session_date,
        session: session.clone(),
        target_ref: target_ref.clone(),
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
        report_markdown: "hello\n".to_string(),
        now,
    })?;

    register_reviewer(RegisterReviewerParams {
        repo_root: repo_root.path().to_path_buf(),
        session_date,
        session: session.clone(),
        target_ref: target_ref.clone(),
        reviewer_id: Some("cafebabe".to_string()),
        session_id: Some("sess0002".to_string()),
        parent_id: None,
        now,
    })?;

    let raw = fs::read_to_string(session.session_file())?;
    let session_json: SessionFile = serde_json::from_str(&raw)?;
    let entry = session_json
        .reviews
        .iter()
        .find(|r| r.reviewer_id == "cafebabe")
        .expect("cafebabe entry should exist");
    assert_eq!(entry.initiator_status, InitiatorStatus::Requesting);

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
        session: session.clone(),
        reviewer_id: "deadbeef".to_string(),
        session_id: "sess0001".to_string(),
        initiator_status: InitiatorStatus::Reviewed,
        now,
        lock_owner: "not/ok".to_string(),
    };
    let err = set_initiator_status(&params).expect_err("invalid lock_owner should be rejected");
    assert!(
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

    let target_ref = "refs/heads/main".to_string();

    register_reviewer(RegisterReviewerParams {
        repo_root: repo_root.path().to_path_buf(),
        session_date,
        session: session.clone(),
        target_ref: target_ref.clone(),
        reviewer_id: Some("deadbeef".to_string()),
        session_id: Some("sess0001".to_string()),
        parent_id: None,
        now,
    })?;

    register_reviewer(RegisterReviewerParams {
        repo_root: repo_root.path().to_path_buf(),
        session_date,
        session: session.clone(),
        target_ref: target_ref.clone(),
        reviewer_id: Some("deadbeef".to_string()),
        session_id: Some("sess0001".to_string()),
        parent_id: None,
        now,
    })?;

    let raw = fs::read_to_string(session.session_file())?;
    let session_json: SessionFile = serde_json::from_str(&raw)?;
    assert_eq!(session_json.reviews.len(), 1);
    Ok(())
}

#[test]
fn reports_views_and_filters() -> anyhow::Result<()> {
    let dir = tempfile::tempdir()?;
    let session_locator = SessionLocator::new(dir.path().to_path_buf());
    let started_at = "2026-01-11T00:00:00Z".to_string();
    let updated_at = "2026-01-11T01:00:00Z".to_string();
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
        started_at: started_at.clone(),
        updated_at: updated_at.clone(),
        finished_at: None,
        current_phase: Some(ReviewPhase::Ingestion),
        verdict: None,
        counts: SeverityCounts::zero(),
        report_file: None,
        notes: vec![note],
    };

    let blocked = ReviewEntry {
        reviewer_id: "cafebabe".to_string(),
        session_id: "sess0002".to_string(),
        target_ref: "refs/heads/dev".to_string(),
        initiator_status: InitiatorStatus::Observing,
        status: ReviewerStatus::Blocked,
        parent_id: None,
        started_at: started_at.clone(),
        updated_at: updated_at.clone(),
        finished_at: None,
        current_phase: None,
        verdict: None,
        counts: SeverityCounts::zero(),
        report_file: None,
        notes: Vec::new(),
    };

    let finished = ReviewEntry {
        reviewer_id: "feedface".to_string(),
        session_id: "sess0003".to_string(),
        target_ref: "refs/heads/main".to_string(),
        initiator_status: InitiatorStatus::Received,
        status: ReviewerStatus::Finished,
        parent_id: None,
        started_at: started_at.clone(),
        updated_at: updated_at.clone(),
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
    };

    let session = SessionFile {
        schema_version: "1.0.0".to_string(),
        session_date: "2026-01-11".to_string(),
        repo_root: dir.path().to_string_lossy().to_string(),
        reviewers: vec![
            "deadbeef".to_string(),
            "cafebabe".to_string(),
            "feedface".to_string(),
        ],
        reviews: vec![in_progress, blocked, finished],
    };

    let open = collect_reports(
        &session,
        &session_locator,
        ReportsView::Open,
        ReportsFilters::default(),
        ReportsOptions::default(),
    );
    assert_eq!(open.total_reviews, 3);
    assert_eq!(open.matching_reviews, 2);

    let closed = collect_reports(
        &session,
        &session_locator,
        ReportsView::Closed,
        ReportsFilters::default(),
        ReportsOptions::default(),
    );
    assert_eq!(closed.matching_reviews, 1);

    let in_progress_view = collect_reports(
        &session,
        &session_locator,
        ReportsView::InProgress,
        ReportsFilters::default(),
        ReportsOptions::default(),
    );
    assert_eq!(in_progress_view.matching_reviews, 1);

    let filtered = collect_reports(
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
    );
    assert_eq!(filtered.matching_reviews, 1);

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
    );
    assert_eq!(status_filtered.matching_reviews, 1);

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
    );
    assert_eq!(initiator_filtered.matching_reviews, 1);

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
    );
    assert_eq!(verdict_filtered.matching_reviews, 1);

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
    );
    assert_eq!(phase_filtered.matching_reviews, 1);

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
        ReportsOptions { include_notes: true },
    );
    assert_eq!(only_notes.matching_reviews, 1);
    assert!(
        only_notes.reviews[0].notes.as_ref().is_some(),
        "expected notes to be included"
    );

    let only_reports = collect_reports(
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
    );
    assert_eq!(only_reports.matching_reviews, 1);
    assert!(
        only_reports.reviews[0].report_path.is_some(),
        "expected report_path to be populated"
    );

    Ok(())
}
