//! End-to-end CLI tests for `mpcr`.

use anyhow::ensure;
use mpcr::paths;
use mpcr::session::{
    InitiatorStatus, NoteRole, NoteType, ReviewEntry, ReviewPhase, ReviewVerdict, ReviewerStatus,
    SessionFile, SessionNote, SeverityCounts,
};
use serde_json::Value;
use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use time::{Date, Month};

fn json_field<'a>(value: &'a Value, key: &str) -> anyhow::Result<&'a Value> {
    value
        .get(key)
        .ok_or_else(|| anyhow::anyhow!("missing field `{key}`"))
}

fn json_str<'a>(value: &'a Value, key: &str) -> anyhow::Result<&'a str> {
    json_field(value, key)?
        .as_str()
        .ok_or_else(|| anyhow::anyhow!("field `{key}` is not a string"))
}

fn json_u64(value: &Value, key: &str) -> anyhow::Result<u64> {
    json_field(value, key)?
        .as_u64()
        .ok_or_else(|| anyhow::anyhow!("field `{key}` is not a u64"))
}

fn json_bool(value: &Value, key: &str) -> anyhow::Result<bool> {
    json_field(value, key)?
        .as_bool()
        .ok_or_else(|| anyhow::anyhow!("field `{key}` is not a bool"))
}

fn json_array<'a>(value: &'a Value, key: &str) -> anyhow::Result<&'a Vec<Value>> {
    json_field(value, key)?
        .as_array()
        .ok_or_else(|| anyhow::anyhow!("field `{key}` is not an array"))
}

fn json_is_null_or_missing(value: &Value, key: &str) -> bool {
    value.get(key).is_none_or(Value::is_null)
}

fn write_session_file(session_dir: &Path, session: &SessionFile) -> anyhow::Result<PathBuf> {
    fs::create_dir_all(session_dir)?;
    let path = session_dir.join("_session.json");
    let body = serde_json::to_string_pretty(session)? + "\n";
    fs::write(&path, body)?;
    Ok(path)
}

fn sample_session(session_dir: &Path) -> SessionFile {
    let started_at = "2026-01-11T00:00:00Z";
    let updated_at = "2026-01-11T01:00:00Z";
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
        started_at: started_at.to_string(),
        updated_at: updated_at.to_string(),
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
        started_at: started_at.to_string(),
        updated_at: updated_at.to_string(),
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
    };

    SessionFile {
        schema_version: "1.0.0".to_string(),
        session_date: "2026-01-11".to_string(),
        repo_root: session_dir.to_string_lossy().to_string(),
        reviewers: vec![
            "deadbeef".to_string(),
            "cafebabe".to_string(),
            "feedface".to_string(),
        ],
        reviews: vec![open, blocked, finished],
    }
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
    let reviews = json_array(session, "reviews")?;
    reviews
        .iter()
        .find(
            |review| match (review.get("reviewer_id"), review.get("session_id")) {
                (Some(Value::String(rid)), Some(Value::String(sid))) => {
                    rid == reviewer_id && sid == session_id
                }
                _ => false,
            },
        )
        .ok_or_else(|| anyhow::anyhow!("review entry not found"))
}

#[test]
fn reports_open_and_status_filters() -> anyhow::Result<()> {
    let dir = tempfile::tempdir()?;
    let session_dir = dir.path().join("session");
    let session = sample_session(&session_dir);
    write_session_file(&session_dir, &session)?;

    let open = run_reports(&session_dir, &["session", "reports", "open"])?;
    ensure!(json_u64(&open, "matching_reviews")? == 2);

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
    ensure!(json_u64(&in_progress, "matching_reviews")? == 1);

    Ok(())
}

#[test]
fn reports_closed_and_in_progress_views() -> anyhow::Result<()> {
    let dir = tempfile::tempdir()?;
    let session_dir = dir.path().join("session");
    let session = sample_session(&session_dir);
    write_session_file(&session_dir, &session)?;

    let closed = run_reports(&session_dir, &["session", "reports", "closed"])?;
    ensure!(json_u64(&closed, "matching_reviews")? == 1);
    ensure!(json_array(&closed, "reviews")?.len() == 1);

    let in_progress = run_reports(&session_dir, &["session", "reports", "in-progress"])?;
    ensure!(json_u64(&in_progress, "matching_reviews")? == 1);
    Ok(())
}

#[test]
fn id_commands_emit_hex_strings() -> anyhow::Result<()> {
    let id8 = run_cmd_json(&["id", "id8"])?;
    let id8 = id8
        .as_str()
        .ok_or_else(|| anyhow::anyhow!("id8 output was not a string"))?;
    ensure!(id8.len() == 8);
    ensure!(id8.chars().all(|c| matches!(c, '0'..='9' | 'a'..='f')));

    let hex = run_cmd_json(&["id", "hex", "--bytes", "3"])?;
    let hex = hex
        .as_str()
        .ok_or_else(|| anyhow::anyhow!("hex output was not a string"))?;
    ensure!(hex.len() == 6);
    ensure!(hex.chars().all(|c| matches!(c, '0'..='9' | 'a'..='f')));

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
    ensure!(lock_file.exists());

    run_cmd_json(&[
        "lock",
        "release",
        "--session-dir",
        &session_dir_str,
        "--owner",
        "deadbeef",
    ])?;
    ensure!(!lock_file.exists());

    Ok(())
}

#[test]
fn session_show_reads_session_file() -> anyhow::Result<()> {
    let dir = tempfile::tempdir()?;
    let session_dir = dir.path().join("session");
    let session = sample_session(&session_dir);
    write_session_file(&session_dir, &session)?;
    let session_dir_str = session_dir.to_string_lossy().to_string();

    let value = run_cmd_json(&["session", "show", "--session-dir", &session_dir_str])?;
    ensure!(json_array(&value, "reviews")?.len() == 3);
    ensure!(json_str(&value, "schema_version")? == "1.0.0");
    Ok(())
}

#[test]
fn session_show_resolves_session_dir_from_repo_root() -> anyhow::Result<()> {
    let repo_root = tempfile::tempdir()?;
    let repo_root_str = repo_root.path().to_string_lossy().to_string();
    let date = Date::from_calendar_date(2026, Month::January, 11)?;
    let session_dir = paths::session_paths(repo_root.path(), date).session_dir;
    let session = sample_session(&session_dir);
    write_session_file(&session_dir, &session)?;

    let value = run_cmd_json(&[
        "session",
        "show",
        "--repo-root",
        &repo_root_str,
        "--date",
        "2026-01-11",
    ])?;
    ensure!(json_str(&value, "schema_version")? == "1.0.0");
    ensure!(json_array(&value, "reviews")?.len() == 3);
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

    let session_dir = json_str(&out, "session_dir")?;
    let session_file = json_str(&out, "session_file")?;

    ensure!(session_dir.ends_with(".local/reports/code_reviews/2026-01-11"));
    ensure!(session_file.ends_with("_session.json"));

    let session = read_session_json(Path::new(session_dir))?;
    let entry = find_review(&session, "deadbeef", "sess0001")?;
    ensure!(json_str(entry, "status")? == "INITIALIZING");
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
    let session_dir = json_str(&out, "session_dir")?.to_string();

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
    ensure!(json_str(entry, "status")? == "IN_PROGRESS");
    ensure!(json_str(entry, "current_phase")? == "INGESTION");
    Ok(())
}

#[test]
fn reviewer_update_resolves_session_dir_from_repo_root() -> anyhow::Result<()> {
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
    let session_dir = json_str(&out, "session_dir")?.to_string();

    run_cmd_json(&[
        "reviewer",
        "update",
        "--repo-root",
        &repo_root_str,
        "--date",
        "2026-01-11",
        "--reviewer-id",
        "deadbeef",
        "--session-id",
        "sess0001",
        "--status",
        "IN_PROGRESS",
    ])?;

    let session = read_session_json(Path::new(&session_dir))?;
    let entry = find_review(&session, "deadbeef", "sess0001")?;
    ensure!(json_str(entry, "status")? == "IN_PROGRESS");
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
    let session_dir = json_str(&out, "session_dir")?.to_string();

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
    ensure!(json_field(entry, "current_phase")?.is_null());
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
    let session_dir = json_str(&out, "session_dir")?.to_string();

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
    let notes = json_array(entry, "notes")?;
    ensure!(notes.len() == 1);
    let note = notes
        .first()
        .ok_or_else(|| anyhow::anyhow!("note missing"))?;
    ensure!(json_str(note, "role")? == "reviewer");
    ensure!(json_str(note, "type")? == "question");
    ensure!(json_str(note, "content")? == "hello");
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
    let session_dir = json_str(&out, "session_dir")?.to_string();

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

    let report_name = json_str(&result, "report_file")?;
    let report_path = json_str(&result, "report_path")?;
    ensure!(Path::new(report_path).exists());
    ensure!(report_path.ends_with(report_name));
    let contents = fs::read_to_string(report_path)?;
    ensure!(contents.contains("looks good"));

    let session = read_session_json(Path::new(&session_dir))?;
    let entry = find_review(&session, "deadbeef", "sess0001")?;
    ensure!(json_str(entry, "status")? == "FINISHED");
    ensure!(json_str(entry, "current_phase")? == "REPORT_WRITING");
    ensure!(json_str(entry, "verdict")? == "APPROVE");
    let counts = json_field(entry, "counts")?;
    ensure!(json_u64(counts, "major")? == 2);
    ensure!(json_str(entry, "report_file")? == report_name);
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
    let session_dir = json_str(&out, "session_dir")?.to_string();

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

    let report_path = json_str(&result, "report_path")?;
    let contents = fs::read_to_string(report_path)?;
    ensure!(contents.contains("stdin report body"));
    Ok(())
}

#[test]
fn reviewer_register_emit_env_sh_exports_expected_vars() -> anyhow::Result<()> {
    let repo_root = tempfile::tempdir()?;
    let repo_root_str = repo_root.path().to_string_lossy().to_string();

    let output = Command::new(env!("CARGO_BIN_EXE_mpcr"))
        .args([
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
            "--emit-env",
            "sh",
        ])
        .output()?;
    if !output.status.success() {
        return Err(anyhow::anyhow!(
            "mpcr failed: {}",
            String::from_utf8_lossy(&output.stderr)
        ));
    }

    let stdout = String::from_utf8(output.stdout)?;
    ensure!(stdout.contains("export MPCR_REVIEWER_ID='deadbeef'\n"));
    ensure!(stdout.contains("export MPCR_SESSION_ID='sess0001'\n"));
    ensure!(stdout.contains("export MPCR_TARGET_REF='refs/heads/main'\n"));

    let session_date = Date::from_calendar_date(2026, Month::January, 11)?;
    let expected_session_dir = paths::session_paths(repo_root.path(), session_date)
        .session_dir
        .to_string_lossy()
        .to_string();
    ensure!(stdout.contains(&format!(
        "export MPCR_SESSION_DIR='{expected_session_dir}'\n"
    )));
    Ok(())
}

#[test]
fn reviewer_register_emit_env_sh_quotes_single_quotes_in_values() -> anyhow::Result<()> {
    let repo_root = tempfile::tempdir()?;
    let repo_root_str = repo_root.path().to_string_lossy().to_string();

    let output = Command::new(env!("CARGO_BIN_EXE_mpcr"))
        .args([
            "reviewer",
            "register",
            "--target-ref",
            "refs/heads/feat'ure",
            "--repo-root",
            &repo_root_str,
            "--date",
            "2026-01-11",
            "--reviewer-id",
            "deadbeef",
            "--session-id",
            "sess0001",
            "--emit-env",
            "sh",
        ])
        .output()?;
    if !output.status.success() {
        return Err(anyhow::anyhow!(
            "mpcr failed: {}",
            String::from_utf8_lossy(&output.stderr)
        ));
    }

    let stdout = String::from_utf8(output.stdout)?;
    ensure!(stdout.contains("export MPCR_TARGET_REF='refs/heads/feat'\"'\"'ure'\n"));
    Ok(())
}

#[test]
fn reviewer_update_uses_env_defaults_for_ids_and_session_dir() -> anyhow::Result<()> {
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
    let session_dir = json_str(&out, "session_dir")?.to_string();

    let output = Command::new(env!("CARGO_BIN_EXE_mpcr"))
        .args([
            "reviewer",
            "update",
            "--status",
            "IN_PROGRESS",
            "--phase",
            "DOMAIN_COVERAGE",
            "--json",
        ])
        .env("MPCR_REVIEWER_ID", "deadbeef")
        .env("MPCR_SESSION_ID", "sess0001")
        .env("MPCR_SESSION_DIR", &session_dir)
        .output()?;

    if !output.status.success() {
        return Err(anyhow::anyhow!(
            "mpcr failed: {}",
            String::from_utf8_lossy(&output.stderr)
        ));
    }
    let result: Value = serde_json::from_slice(&output.stdout)?;
    ensure!(json_bool(&result, "ok")?);

    let session = read_session_json(Path::new(&session_dir))?;
    let entry = find_review(&session, "deadbeef", "sess0001")?;
    ensure!(json_str(entry, "status")? == "IN_PROGRESS");
    ensure!(json_str(entry, "current_phase")? == "DOMAIN_COVERAGE");
    Ok(())
}

#[test]
fn applicator_wait_uses_env_defaults_for_session_dir_and_filters() -> anyhow::Result<()> {
    let dir = tempfile::tempdir()?;
    let session_dir = dir.path().join("session");
    let session = sample_session(&session_dir);
    write_session_file(&session_dir, &session)?;
    let session_dir_str = session_dir.to_string_lossy().to_string();

    let output = Command::new(env!("CARGO_BIN_EXE_mpcr"))
        .args(["applicator", "wait", "--json"])
        .env("MPCR_SESSION_DIR", &session_dir_str)
        .env("MPCR_TARGET_REF", "refs/heads/other")
        .output()?;

    if !output.status.success() {
        return Err(anyhow::anyhow!(
            "mpcr failed: {}",
            String::from_utf8_lossy(&output.stderr)
        ));
    }
    let result: Value = serde_json::from_slice(&output.stdout)?;
    ensure!(json_bool(&result, "ok")?);
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
    let session_dir = json_str(&out, "session_dir")?.to_string();

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
    ensure!(json_str(entry, "initiator_status")? == "RECEIVED");
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
    let session_dir = json_str(&out, "session_dir")?.to_string();

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
    let notes = json_array(entry, "notes")?;
    ensure!(notes.len() == 1);
    let note = notes
        .first()
        .ok_or_else(|| anyhow::anyhow!("note missing"))?;
    ensure!(json_str(note, "role")? == "applicator");
    ensure!(json_str(note, "type")? == "applied");
    let content = json_field(note, "content")?;
    ensure!(json_str(content, "result")? == "done");
    Ok(())
}

#[test]
fn applicator_wait_returns_for_filtered_target() -> anyhow::Result<()> {
    let dir = tempfile::tempdir()?;
    let session_dir = dir.path().join("session");
    let session = sample_session(&session_dir);
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
    ensure!(json_bool(&value, "ok")?);
    Ok(())
}

#[test]
fn reports_notes_and_verdict_filters() -> anyhow::Result<()> {
    let dir = tempfile::tempdir()?;
    let session_dir = dir.path().join("session");
    let session = sample_session(&session_dir);
    write_session_file(&session_dir, &session)?;

    let with_notes = run_reports(
        &session_dir,
        &["session", "reports", "open", "--only-with-notes"],
    )?;
    ensure!(json_u64(&with_notes, "matching_reviews")? == 1);
    let reviews = json_array(&with_notes, "reviews")?;
    let review = reviews
        .first()
        .ok_or_else(|| anyhow::anyhow!("review missing"))?;
    let notes = json_array(review, "notes")?;
    ensure!(notes.len() == 1);

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
    ensure!(json_u64(&approved, "matching_reviews")? == 1);
    let approved_reviews = json_array(&approved, "reviews")?;
    let approved_review = approved_reviews
        .first()
        .ok_or_else(|| anyhow::anyhow!("review missing"))?;
    let report_path = json_field(approved_review, "report_path")?;
    ensure!(report_path.is_string(), "expected report_path in output");

    Ok(())
}

#[test]
fn reports_empty_session() -> anyhow::Result<()> {
    let dir = tempfile::tempdir()?;
    let session_dir = dir.path().join("session");
    let session = empty_session(&session_dir);
    write_session_file(&session_dir, &session)?;

    let open = run_reports(&session_dir, &["session", "reports", "open"])?;
    ensure!(json_u64(&open, "matching_reviews")? == 0);

    let closed = run_reports(&session_dir, &["session", "reports", "closed"])?;
    ensure!(json_u64(&closed, "matching_reviews")? == 0);

    Ok(())
}

#[test]
fn reports_missing_session_file() -> anyhow::Result<()> {
    let dir = tempfile::tempdir()?;
    let session_dir = dir.path().join("session");
    let stderr = run_reports_failure(&session_dir, &["session", "reports", "open"])?;
    ensure!(!stderr.trim().is_empty());
    Ok(())
}

#[test]
fn reports_invalid_json() -> anyhow::Result<()> {
    let dir = tempfile::tempdir()?;
    let session_dir = dir.path().join("session");
    fs::create_dir_all(&session_dir)?;
    fs::write(session_dir.join("_session.json"), "{not json")?;
    let stderr = run_reports_failure(&session_dir, &["session", "reports", "open"])?;
    ensure!(!stderr.trim().is_empty());
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
    ensure!(!stderr.trim().is_empty());
    Ok(())
}

#[test]
fn reports_combined_filters() -> anyhow::Result<()> {
    let dir = tempfile::tempdir()?;
    let session_dir = dir.path().join("session");
    let session = sample_session(&session_dir);
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
    ensure!(json_u64(&filtered, "matching_reviews")? == 1);
    Ok(())
}

#[test]
fn reports_open_only_with_report() -> anyhow::Result<()> {
    let dir = tempfile::tempdir()?;
    let session_dir = dir.path().join("session");
    let session = sample_session(&session_dir);
    write_session_file(&session_dir, &session)?;

    let open = run_reports(
        &session_dir,
        &["session", "reports", "open", "--only-with-report"],
    )?;
    ensure!(json_u64(&open, "matching_reviews")? == 0);
    Ok(())
}

#[test]
fn reports_include_report_contents() -> anyhow::Result<()> {
    let dir = tempfile::tempdir()?;
    let session_dir = dir.path().join("session");
    let session = sample_session(&session_dir);
    write_session_file(&session_dir, &session)?;

    let report_path = session_dir.join("12-00-00-000_refs_heads_main_feedface.md");
    fs::write(&report_path, "final report body")?;

    let closed = run_reports(
        &session_dir,
        &["session", "reports", "closed", "--include-report-contents"],
    )?;
    ensure!(json_u64(&closed, "matching_reviews")? == 1);
    let reviews = json_array(&closed, "reviews")?;
    let review = reviews
        .first()
        .ok_or_else(|| anyhow::anyhow!("review missing"))?;
    let contents = json_str(review, "report_contents")?;
    ensure!(contents.contains("final report body"));
    ensure!(json_is_null_or_missing(review, "report_error"));
    Ok(())
}

#[test]
fn reports_include_report_contents_with_filters() -> anyhow::Result<()> {
    let dir = tempfile::tempdir()?;
    let session_dir = dir.path().join("session");
    let session = sample_session(&session_dir);
    write_session_file(&session_dir, &session)?;

    let report_path = session_dir.join("12-00-00-000_refs_heads_main_feedface.md");
    fs::write(&report_path, "filtered report body")?;

    let closed = run_reports(
        &session_dir,
        &[
            "session",
            "reports",
            "closed",
            "--include-report-contents",
            "--verdict",
            "APPROVE",
            "--reviewer-status",
            "FINISHED",
            "--reviewer-id",
            "feedface",
        ],
    )?;
    ensure!(json_u64(&closed, "matching_reviews")? == 1);
    let reviews = json_array(&closed, "reviews")?;
    let review = reviews
        .first()
        .ok_or_else(|| anyhow::anyhow!("review missing"))?;
    let contents = json_str(review, "report_contents")?;
    ensure!(contents.contains("filtered report body"));
    ensure!(json_is_null_or_missing(review, "report_error"));
    Ok(())
}

#[test]
fn reports_missing_report_file_is_graceful() -> anyhow::Result<()> {
    let dir = tempfile::tempdir()?;
    let session_dir = dir.path().join("session");
    let session = sample_session(&session_dir);
    write_session_file(&session_dir, &session)?;

    let closed = run_reports(
        &session_dir,
        &["session", "reports", "closed", "--include-report-contents"],
    )?;
    ensure!(json_u64(&closed, "matching_reviews")? == 1);
    let reviews = json_array(&closed, "reviews")?;
    let review = reviews
        .first()
        .ok_or_else(|| anyhow::anyhow!("review missing"))?;
    ensure!(json_is_null_or_missing(review, "report_contents"));
    let error = json_str(review, "report_error")?;
    ensure!(!error.trim().is_empty());
    Ok(())
}

#[test]
fn reports_include_report_contents_with_open_filters() -> anyhow::Result<()> {
    let dir = tempfile::tempdir()?;
    let session_dir = dir.path().join("session");
    let session = sample_session(&session_dir);
    write_session_file(&session_dir, &session)?;

    let open = run_reports(
        &session_dir,
        &[
            "session",
            "reports",
            "open",
            "--include-report-contents",
            "--reviewer-status",
            "IN_PROGRESS",
            "--initiator-status",
            "OBSERVING",
            "--target-ref",
            "refs/heads/main",
        ],
    )?;
    ensure!(json_u64(&open, "matching_reviews")? == 1);
    let reviews = json_array(&open, "reviews")?;
    let review = reviews
        .first()
        .ok_or_else(|| anyhow::anyhow!("review missing"))?;
    ensure!(json_is_null_or_missing(review, "report_contents"));
    ensure!(json_is_null_or_missing(review, "report_error"));
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
    ensure!(json_u64(&open, "matching_reviews")? == 1);
    let reviews = json_array(&open, "reviews")?;
    let review = reviews
        .first()
        .ok_or_else(|| anyhow::anyhow!("review missing"))?;
    let notes = json_array(review, "notes")?;
    ensure!(notes.is_empty());
    Ok(())
}

#[test]
fn reports_target_ref_filter() -> anyhow::Result<()> {
    let dir = tempfile::tempdir()?;
    let session_dir = dir.path().join("session");
    let session = sample_session(&session_dir);
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
    ensure!(json_u64(&filtered, "matching_reviews")? == 1);
    Ok(())
}

#[test]
fn reports_session_dir_is_file() -> anyhow::Result<()> {
    let dir = tempfile::tempdir()?;
    let file_path = dir.path().join("not_a_dir");
    fs::write(&file_path, "placeholder")?;
    let stderr = run_reports_failure(&file_path, &["session", "reports", "open"])?;
    ensure!(!stderr.trim().is_empty());
    Ok(())
}
