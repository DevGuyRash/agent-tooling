use mpcr::lock::{self, LockConfig};
use mpcr::session::{
    finalize_review, register_reviewer, FinalizeReviewParams, RegisterReviewerParams,
    set_initiator_status, InitiatorStatus, ReviewVerdict, SessionFile, SessionLocator,
    SetInitiatorStatusParams, SeverityCounts,
};
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

    set_initiator_status(SetInitiatorStatusParams {
        session: session.clone(),
        reviewer_id: "deadbeef".to_string(),
        session_id: "sess0001".to_string(),
        initiator_status: InitiatorStatus::Applied,
        now,
        lock_owner: "lock0001".to_string(),
    })?;

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

    let err = set_initiator_status(SetInitiatorStatusParams {
        session: session.clone(),
        reviewer_id: "deadbeef".to_string(),
        session_id: "sess0001".to_string(),
        initiator_status: InitiatorStatus::Reviewed,
        now,
        lock_owner: "not/ok".to_string(),
    })
    .expect_err("invalid lock_owner should be rejected");
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
