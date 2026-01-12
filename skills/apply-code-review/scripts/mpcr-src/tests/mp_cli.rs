//! End-to-end CLI tests for `mpcr`.

use mpcr::session::{
    InitiatorStatus, NoteRole, NoteType, ReviewEntry, ReviewPhase, ReviewVerdict, ReviewerStatus,
    SessionFile, SessionNote, SeverityCounts,
};
use serde_json::Value;
use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};

fn write_session_file(session_dir: &Path, session: &SessionFile) -> anyhow::Result<PathBuf> {
    fs::create_dir_all(session_dir)?;
    let path = session_dir.join("_session.json");
    let body = serde_json::to_string_pretty(session)? + "\n";
    fs::write(&path, body)?;
    Ok(path)
}

fn sample_session(session_dir: &Path) -> anyhow::Result<SessionFile> {
    let started_at = "2026-01-11T00:00:00Z".to_string();
    let updated_at = "2026-01-11T01:00:00Z".to_string();
    let note = SessionNote {
        role: NoteRole::Reviewer,
        timestamp: "2026-01-11T01:30:00Z".to_string(),
        note_type: NoteType::Question,
        content: Value::String("need context".to_string()),
    };

    let open = ReviewEntry {
        reviewer_id: "deadbeef".to_string(),
        session_id: "sess0001".to_string(),
        target_ref: "refs/heads/main".to_string(),
        initiator_status: InitiatorStatus::Observing,
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
        initiator_status: InitiatorStatus::Requesting,
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

    Ok(SessionFile {
        schema_version: "1.0.0".to_string(),
        session_date: "2026-01-11".to_string(),
        repo_root: session_dir.to_string_lossy().to_string(),
        reviewers: vec![
            "deadbeef".to_string(),
            "cafebabe".to_string(),
            "feedface".to_string(),
        ],
        reviews: vec![open, blocked, finished],
    })
}

fn empty_session(session_dir: &Path) -> SessionFile {
    SessionFile {
        schema_version: "1.0.0".to_string(),
        session_date: "2026-01-11".to_string(),
        repo_root: session_dir.to_string_lossy().to_string(),
        reviewers: Vec::new(),
        reviews: Vec::new(),
    }
}

fn session_without_notes(session_dir: &Path) -> SessionFile {
    SessionFile {
        schema_version: "1.0.0".to_string(),
        session_date: "2026-01-11".to_string(),
        repo_root: session_dir.to_string_lossy().to_string(),
        reviewers: vec!["deadbeef".to_string()],
        reviews: vec![ReviewEntry {
            reviewer_id: "deadbeef".to_string(),
            session_id: "sess0001".to_string(),
            target_ref: "refs/heads/main".to_string(),
            initiator_status: InitiatorStatus::Requesting,
            status: ReviewerStatus::InProgress,
            parent_id: None,
            started_at: "2026-01-11T00:00:00Z".to_string(),
            updated_at: "2026-01-11T01:00:00Z".to_string(),
            finished_at: None,
            current_phase: Some(ReviewPhase::Ingestion),
            verdict: None,
            counts: SeverityCounts::zero(),
            report_file: None,
            notes: Vec::new(),
        }],
    }
}

fn run_reports(session_dir: &Path, args: &[&str]) -> anyhow::Result<Value> {
    let output = Command::new(env!("CARGO_BIN_EXE_mpcr"))
        .args(args)
        .arg("--session-dir")
        .arg(session_dir)
        .arg("--json")
        .output()?;
    if !output.status.success() {
        return Err(anyhow::anyhow!(
            "mpcr failed: {}",
            String::from_utf8_lossy(&output.stderr)
        ));
    }
    Ok(serde_json::from_slice(&output.stdout)?)
}

fn run_reports_failure(session_dir: &Path, args: &[&str]) -> anyhow::Result<String> {
    let output = Command::new(env!("CARGO_BIN_EXE_mpcr"))
        .args(args)
        .arg("--session-dir")
        .arg(session_dir)
        .arg("--json")
        .output()?;
    if output.status.success() {
        return Err(anyhow::anyhow!("mpcr unexpectedly succeeded"));
    }
    Ok(String::from_utf8_lossy(&output.stderr).to_string())
}

fn run_cmd_json(args: &[&str]) -> anyhow::Result<Value> {
    let output = Command::new(env!("CARGO_BIN_EXE_mpcr"))
        .args(args)
        .arg("--json")
        .output()?;
    if !output.status.success() {
        return Err(anyhow::anyhow!(
            "mpcr failed: {}",
            String::from_utf8_lossy(&output.stderr)
        ));
    }
    Ok(serde_json::from_slice(&output.stdout)?)
}

fn read_session_json(session_dir: &Path) -> anyhow::Result<Value> {
    let raw = fs::read_to_string(session_dir.join("_session.json"))?;
    Ok(serde_json::from_str(&raw)?)
}

fn find_review<'a>(
    session: &'a Value,
    reviewer_id: &str,
    session_id: &str,
) -> anyhow::Result<&'a Value> {
    let reviews = session["reviews"]
        .as_array()
        .ok_or_else(|| anyhow::anyhow!("reviews not an array"))?;
    reviews
        .iter()
        .find(|review| {
            review["reviewer_id"] == reviewer_id && review["session_id"] == session_id
        })
        .ok_or_else(|| anyhow::anyhow!("review entry not found"))
}

#[test]
fn reports_open_and_status_filters() -> anyhow::Result<()> {
    let dir = tempfile::tempdir()?;
    let session_dir = dir.path().join("session");
    let session = sample_session(&session_dir)?;
    write_session_file(&session_dir, &session)?;

    let open = run_reports(&session_dir, &["session", "reports", "open"])?;
    assert_eq!(open["matching_reviews"].as_u64(), Some(2));

    let in_progress = run_reports(
        &session_dir,
        &[
            "session",
            "reports",
            "open",
            "--reviewer-status",
            "IN_PROGRESS",
        ],
    )?;
    assert_eq!(in_progress["matching_reviews"].as_u64(), Some(1));

    Ok(())
}

#[test]
fn reports_closed_and_in_progress_views() -> anyhow::Result<()> {
    let dir = tempfile::tempdir()?;
    let session_dir = dir.path().join("session");
    let session = sample_session(&session_dir)?;
    write_session_file(&session_dir, &session)?;

    let closed = run_reports(&session_dir, &["session", "reports", "closed"])?;
    assert_eq!(closed["matching_reviews"].as_u64(), Some(1));
    assert_eq!(closed["reviews"].as_array().map(Vec::len), Some(1));

    let in_progress = run_reports(&session_dir, &["session", "reports", "in-progress"])?;
    assert_eq!(in_progress["matching_reviews"].as_u64(), Some(1));
    Ok(())
}

#[test]
fn id_commands_emit_hex_strings() -> anyhow::Result<()> {
    let id8 = run_cmd_json(&["id", "id8"])?;
    let id8 = id8
        .as_str()
        .ok_or_else(|| anyhow::anyhow!("id8 output was not a string"))?;
    assert_eq!(id8.len(), 8);
    assert!(id8.chars().all(|c| matches!(c, '0'..='9' | 'a'..='f')));

    let hex = run_cmd_json(&["id", "hex", "--bytes", "3"])?;
    let hex = hex
        .as_str()
        .ok_or_else(|| anyhow::anyhow!("hex output was not a string"))?;
    assert_eq!(hex.len(), 6);
    assert!(hex.chars().all(|c| matches!(c, '0'..='9' | 'a'..='f')));

    Ok(())
}

#[test]
fn lock_acquire_release_creates_and_removes_file() -> anyhow::Result<()> {
    let dir = tempfile::tempdir()?;
    let session_dir = dir.path().join("session");
    fs::create_dir_all(&session_dir)?;
    let session_dir_str = session_dir.to_string_lossy().to_string();

    run_cmd_json(&[
        "lock",
        "acquire",
        "--session-dir",
        &session_dir_str,
        "--owner",
        "deadbeef",
        "--max-retries",
        "0",
    ])?;
    let lock_file = session_dir.join("_session.json.lock");
    assert!(lock_file.exists());

    run_cmd_json(&[
        "lock",
        "release",
        "--session-dir",
        &session_dir_str,
        "--owner",
        "deadbeef",
    ])?;
    assert!(!lock_file.exists());

    Ok(())
}

#[test]
fn session_show_reads_session_file() -> anyhow::Result<()> {
    let dir = tempfile::tempdir()?;
    let session_dir = dir.path().join("session");
    let session = sample_session(&session_dir)?;
    write_session_file(&session_dir, &session)?;
    let session_dir_str = session_dir.to_string_lossy().to_string();

    let value = run_cmd_json(&["session", "show", "--session-dir", &session_dir_str])?;
    assert_eq!(value["reviews"].as_array().map(Vec::len), Some(3));
    assert_eq!(value["schema_version"], "1.0.0");
    Ok(())
}

#[test]
fn reviewer_register_creates_session() -> anyhow::Result<()> {
    let repo_root = tempfile::tempdir()?;
    let repo_root_str = repo_root.path().to_string_lossy().to_string();

    let out = run_cmd_json(&[
        "reviewer",
        "register",
        "--target-ref",
        "refs/heads/main",
        "--repo-root",
        &repo_root_str,
        "--date",
        "2026-01-11",
        "--reviewer-id",
        "deadbeef",
        "--session-id",
        "sess0001",
    ])?;

    let session_dir = out["session_dir"]
        .as_str()
        .ok_or_else(|| anyhow::anyhow!("session_dir missing"))?;
    let session_file = out["session_file"]
        .as_str()
        .ok_or_else(|| anyhow::anyhow!("session_file missing"))?;

    assert!(session_dir.ends_with(".local/reports/code_reviews/2026-01-11"));
    assert!(session_file.ends_with("_session.json"));

    let session = read_session_json(Path::new(session_dir))?;
    let entry = find_review(&session, "deadbeef", "sess0001")?;
    assert_eq!(entry["status"], "INITIALIZING");
    Ok(())
}

#[test]
fn reviewer_update_changes_status_and_phase() -> anyhow::Result<()> {
    let repo_root = tempfile::tempdir()?;
    let repo_root_str = repo_root.path().to_string_lossy().to_string();

    let out = run_cmd_json(&[
        "reviewer",
        "register",
        "--target-ref",
        "refs/heads/main",
        "--repo-root",
        &repo_root_str,
        "--date",
        "2026-01-11",
        "--reviewer-id",
        "deadbeef",
        "--session-id",
        "sess0001",
    ])?;
    let session_dir = out["session_dir"]
        .as_str()
        .ok_or_else(|| anyhow::anyhow!("session_dir missing"))?
        .to_string();

    run_cmd_json(&[
        "reviewer",
        "update",
        "--session-dir",
        &session_dir,
        "--reviewer-id",
        "deadbeef",
        "--session-id",
        "sess0001",
        "--status",
        "IN_PROGRESS",
        "--phase",
        "INGESTION",
    ])?;

    let session = read_session_json(Path::new(&session_dir))?;
    let entry = find_review(&session, "deadbeef", "sess0001")?;
    assert_eq!(entry["status"], "IN_PROGRESS");
    assert_eq!(entry["current_phase"], "INGESTION");
    Ok(())
}

#[test]
fn reviewer_update_clear_phase() -> anyhow::Result<()> {
    let repo_root = tempfile::tempdir()?;
    let repo_root_str = repo_root.path().to_string_lossy().to_string();

    let out = run_cmd_json(&[
        "reviewer",
        "register",
        "--target-ref",
        "refs/heads/main",
        "--repo-root",
        &repo_root_str,
        "--date",
        "2026-01-11",
        "--reviewer-id",
        "deadbeef",
        "--session-id",
        "sess0001",
    ])?;
    let session_dir = out["session_dir"]
        .as_str()
        .ok_or_else(|| anyhow::anyhow!("session_dir missing"))?
        .to_string();

    run_cmd_json(&[
        "reviewer",
        "update",
        "--session-dir",
        &session_dir,
        "--reviewer-id",
        "deadbeef",
        "--session-id",
        "sess0001",
        "--status",
        "IN_PROGRESS",
        "--phase",
        "INGESTION",
    ])?;

    run_cmd_json(&[
        "reviewer",
        "update",
        "--session-dir",
        &session_dir,
        "--reviewer-id",
        "deadbeef",
        "--session-id",
        "sess0001",
        "--clear-phase",
    ])?;

    let session = read_session_json(Path::new(&session_dir))?;
    let entry = find_review(&session, "deadbeef", "sess0001")?;
    assert!(entry["current_phase"].is_null());
    Ok(())
}

#[test]
fn reviewer_note_appends_note() -> anyhow::Result<()> {
    let repo_root = tempfile::tempdir()?;
    let repo_root_str = repo_root.path().to_string_lossy().to_string();

    let out = run_cmd_json(&[
        "reviewer",
        "register",
        "--target-ref",
        "refs/heads/main",
        "--repo-root",
        &repo_root_str,
        "--date",
        "2026-01-11",
        "--reviewer-id",
        "deadbeef",
        "--session-id",
        "sess0001",
    ])?;
    let session_dir = out["session_dir"]
        .as_str()
        .ok_or_else(|| anyhow::anyhow!("session_dir missing"))?
        .to_string();

    run_cmd_json(&[
        "reviewer",
        "note",
        "--session-dir",
        &session_dir,
        "--reviewer-id",
        "deadbeef",
        "--session-id",
        "sess0001",
        "--note-type",
        "question",
        "--content",
        "hello",
    ])?;

    let session = read_session_json(Path::new(&session_dir))?;
    let entry = find_review(&session, "deadbeef", "sess0001")?;
    let notes = entry["notes"].as_array().ok_or_else(|| anyhow::anyhow!("notes missing"))?;
    assert_eq!(notes.len(), 1);
    assert_eq!(notes[0]["role"], "reviewer");
    assert_eq!(notes[0]["type"], "question");
    assert_eq!(notes[0]["content"], "hello");
    Ok(())
}

#[test]
fn reviewer_finalize_writes_report_and_updates_entry() -> anyhow::Result<()> {
    let repo_root = tempfile::tempdir()?;
    let repo_root_str = repo_root.path().to_string_lossy().to_string();

    let out = run_cmd_json(&[
        "reviewer",
        "register",
        "--target-ref",
        "refs/heads/main",
        "--repo-root",
        &repo_root_str,
        "--date",
        "2026-01-11",
        "--reviewer-id",
        "deadbeef",
        "--session-id",
        "sess0001",
    ])?;
    let session_dir = out["session_dir"]
        .as_str()
        .ok_or_else(|| anyhow::anyhow!("session_dir missing"))?
        .to_string();

    let report_file = repo_root.path().join("report.md");
    fs::write(&report_file, "looks good")?;

    let result = run_cmd_json(&[
        "reviewer",
        "finalize",
        "--session-dir",
        &session_dir,
        "--reviewer-id",
        "deadbeef",
        "--session-id",
        "sess0001",
        "--verdict",
        "APPROVE",
        "--major",
        "2",
        "--report-file",
        report_file.to_string_lossy().as_ref(),
    ])?;

    let report_name = result["report_file"]
        .as_str()
        .ok_or_else(|| anyhow::anyhow!("report_file missing"))?;
    let report_path = result["report_path"]
        .as_str()
        .ok_or_else(|| anyhow::anyhow!("report_path missing"))?;
    assert!(Path::new(report_path).exists());
    assert!(report_path.ends_with(report_name));
    let contents = fs::read_to_string(report_path)?;
    assert!(contents.contains("looks good"));

    let session = read_session_json(Path::new(&session_dir))?;
    let entry = find_review(&session, "deadbeef", "sess0001")?;
    assert_eq!(entry["status"], "FINISHED");
    assert_eq!(entry["current_phase"], "REPORT_WRITING");
    assert_eq!(entry["verdict"], "APPROVE");
    assert_eq!(entry["counts"]["major"], 2);
    assert_eq!(entry["report_file"], report_name);
    Ok(())
}

#[test]
fn reviewer_finalize_reads_report_from_stdin() -> anyhow::Result<()> {
    let repo_root = tempfile::tempdir()?;
    let repo_root_str = repo_root.path().to_string_lossy().to_string();

    let out = run_cmd_json(&[
        "reviewer",
        "register",
        "--target-ref",
        "refs/heads/main",
        "--repo-root",
        &repo_root_str,
        "--date",
        "2026-01-11",
        "--reviewer-id",
        "deadbeef",
        "--session-id",
        "sess0001",
    ])?;
    let session_dir = out["session_dir"]
        .as_str()
        .ok_or_else(|| anyhow::anyhow!("session_dir missing"))?
        .to_string();

    let mut cmd = Command::new(env!("CARGO_BIN_EXE_mpcr"));
    cmd.args([
        "reviewer",
        "finalize",
        "--session-dir",
        &session_dir,
        "--reviewer-id",
        "deadbeef",
        "--session-id",
        "sess0001",
        "--verdict",
        "REQUEST_CHANGES",
    ])
    .arg("--json")
    .stdin(Stdio::piped())
    .stdout(Stdio::piped())
    .stderr(Stdio::piped());

    let mut child = cmd.spawn()?;
    let stdin = child
        .stdin
        .as_mut()
        .ok_or_else(|| anyhow::anyhow!("stdin unavailable"))?;
    stdin.write_all(b"stdin report body")?;
    let output = child.wait_with_output()?;
    if !output.status.success() {
        return Err(anyhow::anyhow!(
            "mpcr failed: {}",
            String::from_utf8_lossy(&output.stderr)
        ));
    }
    let result: Value = serde_json::from_slice(&output.stdout)?;

    let report_path = result["report_path"]
        .as_str()
        .ok_or_else(|| anyhow::anyhow!("report_path missing"))?;
    let contents = fs::read_to_string(report_path)?;
    assert!(contents.contains("stdin report body"));
    Ok(())
}

#[test]
fn applicator_set_status_updates_initiator() -> anyhow::Result<()> {
    let repo_root = tempfile::tempdir()?;
    let repo_root_str = repo_root.path().to_string_lossy().to_string();

    let out = run_cmd_json(&[
        "reviewer",
        "register",
        "--target-ref",
        "refs/heads/main",
        "--repo-root",
        &repo_root_str,
        "--date",
        "2026-01-11",
        "--reviewer-id",
        "deadbeef",
        "--session-id",
        "sess0001",
    ])?;
    let session_dir = out["session_dir"]
        .as_str()
        .ok_or_else(|| anyhow::anyhow!("session_dir missing"))?
        .to_string();

    run_cmd_json(&[
        "applicator",
        "set-status",
        "--session-dir",
        &session_dir,
        "--reviewer-id",
        "deadbeef",
        "--session-id",
        "sess0001",
        "--initiator-status",
        "RECEIVED",
    ])?;

    let session = read_session_json(Path::new(&session_dir))?;
    let entry = find_review(&session, "deadbeef", "sess0001")?;
    assert_eq!(entry["initiator_status"], "RECEIVED");
    Ok(())
}

#[test]
fn applicator_note_appends_note() -> anyhow::Result<()> {
    let repo_root = tempfile::tempdir()?;
    let repo_root_str = repo_root.path().to_string_lossy().to_string();

    let out = run_cmd_json(&[
        "reviewer",
        "register",
        "--target-ref",
        "refs/heads/main",
        "--repo-root",
        &repo_root_str,
        "--date",
        "2026-01-11",
        "--reviewer-id",
        "deadbeef",
        "--session-id",
        "sess0001",
    ])?;
    let session_dir = out["session_dir"]
        .as_str()
        .ok_or_else(|| anyhow::anyhow!("session_dir missing"))?
        .to_string();

    run_cmd_json(&[
        "applicator",
        "note",
        "--session-dir",
        &session_dir,
        "--reviewer-id",
        "deadbeef",
        "--session-id",
        "sess0001",
        "--note-type",
        "applied",
        "--content-json",
        "--content",
        r#"{"result":"done"}"#,
    ])?;

    let session = read_session_json(Path::new(&session_dir))?;
    let entry = find_review(&session, "deadbeef", "sess0001")?;
    let notes = entry["notes"]
        .as_array()
        .ok_or_else(|| anyhow::anyhow!("notes missing"))?;
    assert_eq!(notes.len(), 1);
    assert_eq!(notes[0]["role"], "applicator");
    assert_eq!(notes[0]["type"], "applied");
    assert_eq!(notes[0]["content"]["result"], "done");
    Ok(())
}

#[test]
fn applicator_wait_returns_for_filtered_target() -> anyhow::Result<()> {
    let dir = tempfile::tempdir()?;
    let session_dir = dir.path().join("session");
    let session = sample_session(&session_dir)?;
    write_session_file(&session_dir, &session)?;
    let session_dir_str = session_dir.to_string_lossy().to_string();

    let value = run_cmd_json(&[
        "applicator",
        "wait",
        "--session-dir",
        &session_dir_str,
        "--target-ref",
        "refs/heads/other",
    ])?;
    assert_eq!(value["ok"], true);
    Ok(())
}

#[test]
fn reports_notes_and_verdict_filters() -> anyhow::Result<()> {
    let dir = tempfile::tempdir()?;
    let session_dir = dir.path().join("session");
    let session = sample_session(&session_dir)?;
    write_session_file(&session_dir, &session)?;

    let with_notes = run_reports(
        &session_dir,
        &["session", "reports", "open", "--only-with-notes"],
    )?;
    assert_eq!(with_notes["matching_reviews"].as_u64(), Some(1));
    let notes = &with_notes["reviews"][0]["notes"];
    assert!(notes.is_array());
    assert_eq!(notes.as_array().map(Vec::len), Some(1));

    let approved = run_reports(
        &session_dir,
        &[
            "session",
            "reports",
            "closed",
            "--verdict",
            "APPROVE",
            "--only-with-report",
        ],
    )?;
    assert_eq!(approved["matching_reviews"].as_u64(), Some(1));
    assert!(
        approved["reviews"][0]["report_path"].is_string(),
        "expected report_path in output"
    );

    Ok(())
}

#[test]
fn reports_empty_session() -> anyhow::Result<()> {
    let dir = tempfile::tempdir()?;
    let session_dir = dir.path().join("session");
    let session = empty_session(&session_dir);
    write_session_file(&session_dir, &session)?;

    let open = run_reports(&session_dir, &["session", "reports", "open"])?;
    assert_eq!(open["matching_reviews"].as_u64(), Some(0));

    let closed = run_reports(&session_dir, &["session", "reports", "closed"])?;
    assert_eq!(closed["matching_reviews"].as_u64(), Some(0));

    Ok(())
}

#[test]
fn reports_missing_session_file() -> anyhow::Result<()> {
    let dir = tempfile::tempdir()?;
    let session_dir = dir.path().join("session");
    let stderr = run_reports_failure(&session_dir, &["session", "reports", "open"])?;
    assert!(!stderr.trim().is_empty());
    Ok(())
}

#[test]
fn reports_invalid_json() -> anyhow::Result<()> {
    let dir = tempfile::tempdir()?;
    let session_dir = dir.path().join("session");
    fs::create_dir_all(&session_dir)?;
    fs::write(session_dir.join("_session.json"), "{not json")?;
    let stderr = run_reports_failure(&session_dir, &["session", "reports", "open"])?;
    assert!(!stderr.trim().is_empty());
    Ok(())
}

#[test]
fn reports_invalid_status_flag() -> anyhow::Result<()> {
    let dir = tempfile::tempdir()?;
    let session_dir = dir.path().join("session");
    let stderr = run_reports_failure(
        &session_dir,
        &[
            "session",
            "reports",
            "open",
            "--reviewer-status",
            "NOT_A_STATUS",
        ],
    )?;
    assert!(!stderr.trim().is_empty());
    Ok(())
}

#[test]
fn reports_combined_filters() -> anyhow::Result<()> {
    let dir = tempfile::tempdir()?;
    let session_dir = dir.path().join("session");
    let session = sample_session(&session_dir)?;
    write_session_file(&session_dir, &session)?;

    let filtered = run_reports(
        &session_dir,
        &[
            "session",
            "reports",
            "open",
            "--reviewer-status",
            "IN_PROGRESS",
            "--initiator-status",
            "OBSERVING",
            "--phase",
            "INGESTION",
            "--only-with-notes",
        ],
    )?;
    assert_eq!(filtered["matching_reviews"].as_u64(), Some(1));
    Ok(())
}

#[test]
fn reports_open_only_with_report() -> anyhow::Result<()> {
    let dir = tempfile::tempdir()?;
    let session_dir = dir.path().join("session");
    let session = sample_session(&session_dir)?;
    write_session_file(&session_dir, &session)?;

    let open = run_reports(
        &session_dir,
        &["session", "reports", "open", "--only-with-report"],
    )?;
    assert_eq!(open["matching_reviews"].as_u64(), Some(0));
    Ok(())
}

#[test]
fn reports_include_report_contents() -> anyhow::Result<()> {
    let dir = tempfile::tempdir()?;
    let session_dir = dir.path().join("session");
    let session = sample_session(&session_dir)?;
    write_session_file(&session_dir, &session)?;

    let report_path = session_dir.join("12-00-00-000_refs_heads_main_feedface.md");
    fs::write(&report_path, "final report body")?;

    let closed = run_reports(
        &session_dir,
        &["session", "reports", "closed", "--include-report-contents"],
    )?;
    assert_eq!(closed["matching_reviews"].as_u64(), Some(1));
    let contents = closed["reviews"][0]["report_contents"]
        .as_str()
        .ok_or_else(|| anyhow::anyhow!("report_contents missing"))?;
    assert!(contents.contains("final report body"));
    assert!(closed["reviews"][0]["report_error"].is_null());
    Ok(())
}

#[test]
fn reports_missing_report_file_is_graceful() -> anyhow::Result<()> {
    let dir = tempfile::tempdir()?;
    let session_dir = dir.path().join("session");
    let session = sample_session(&session_dir)?;
    write_session_file(&session_dir, &session)?;

    let closed = run_reports(
        &session_dir,
        &["session", "reports", "closed", "--include-report-contents"],
    )?;
    assert_eq!(closed["matching_reviews"].as_u64(), Some(1));
    assert!(closed["reviews"][0]["report_contents"].is_null());
    let error = closed["reviews"][0]["report_error"]
        .as_str()
        .ok_or_else(|| anyhow::anyhow!("report_error missing"))?;
    assert!(!error.trim().is_empty());
    Ok(())
}

#[test]
fn reports_include_notes_empty() -> anyhow::Result<()> {
    let dir = tempfile::tempdir()?;
    let session_dir = dir.path().join("session");
    let session = session_without_notes(&session_dir);
    write_session_file(&session_dir, &session)?;

    let open = run_reports(
        &session_dir,
        &["session", "reports", "open", "--include-notes"],
    )?;
    assert_eq!(open["matching_reviews"].as_u64(), Some(1));
    let notes = &open["reviews"][0]["notes"];
    assert!(notes.is_array());
    assert_eq!(notes.as_array().map(Vec::len), Some(0));
    Ok(())
}

#[test]
fn reports_target_ref_filter() -> anyhow::Result<()> {
    let dir = tempfile::tempdir()?;
    let session_dir = dir.path().join("session");
    let session = sample_session(&session_dir)?;
    write_session_file(&session_dir, &session)?;

    let filtered = run_reports(
        &session_dir,
        &[
            "session",
            "reports",
            "open",
            "--target-ref",
            "refs/heads/dev",
        ],
    )?;
    assert_eq!(filtered["matching_reviews"].as_u64(), Some(1));
    Ok(())
}

#[test]
fn reports_session_dir_is_file() -> anyhow::Result<()> {
    let dir = tempfile::tempdir()?;
    let file_path = dir.path().join("not_a_dir");
    fs::write(&file_path, "placeholder")?;
    let stderr = run_reports_failure(&file_path, &["session", "reports", "open"])?;
    assert!(!stderr.trim().is_empty());
    Ok(())
}
