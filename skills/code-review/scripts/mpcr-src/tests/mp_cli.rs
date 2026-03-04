//! End-to-end CLI tests for `mpcr`.
#![allow(
    clippy::bool_to_int_with_if,
    clippy::format_push_string,
    clippy::needless_pass_by_value,
    clippy::too_many_lines
)]

use anyhow::ensure;
use mpcr::paths;
use mpcr::session::{
    load_session, InitiatorStatus, NoteRole, NoteType, ReviewEntry, ReviewPhase, ReviewVerdict,
    ReviewerStatus, SessionFile, SessionLocator, SessionNote, SeverityCounts,
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
    let mut body = serde_json::to_value(session)?;
    let object = body
        .as_object_mut()
        .ok_or_else(|| anyhow::anyhow!("session payload must be an object"))?;
    object.insert(
        "schema_version".to_string(),
        Value::String("1.2.0".to_string()),
    );
    object.insert(
        "storage_format".to_string(),
        Value::String("json_fallback".to_string()),
    );
    let body = serde_json::to_string_pretty(&body)? + "\n";
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
        child_reviews: Vec::new(),
        extra: serde_json::Map::default(),
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

    SessionFile {
        schema_version: "1.2.0".to_string(),
        session_date: "2026-01-11".to_string(),
        repo_root: session_dir.to_string_lossy().to_string(),
        reviewers: vec![
            "deadbeef".to_string(),
            "cafebabe".to_string(),
            "feedface".to_string(),
        ],
        reviews: vec![open, blocked, finished],
        extra: serde_json::Map::new(),
    }
}

fn empty_session(session_dir: &Path) -> SessionFile {
    SessionFile {
        schema_version: "1.2.0".to_string(),
        session_date: "2026-01-11".to_string(),
        repo_root: session_dir.to_string_lossy().to_string(),
        reviewers: Vec::new(),
        reviews: Vec::new(),
        extra: serde_json::Map::new(),
    }
}

fn findings_toml(
    counts: SeverityCounts,
    source_ref: &str,
    prefix: &str,
) -> (String, Vec<String>, usize) {
    let mut body = String::new();
    let mut ids = Vec::new();
    let mut total = 0usize;
    for (label, count) in [
        ("BLOCKER", counts.blocker),
        ("MAJOR", counts.major),
        ("MINOR", counts.minor),
        ("NIT", counts.nit),
    ] {
        for _ in 0..count {
            total += 1;
            let id = format!("{prefix}{total}");
            ids.push(id.clone());
            body.push_str(&format!(
                r#"
[[merged_findings]]
id = "{id}"
severity = "{label}"
anchor = "src/lib.rs:{line}"
claim = "Invariant {id} should hold."
disproof = "Concrete scenario {id} breaks the invariant."
evidence = "Trace for {id} reaches the failing branch."
recommendation = "Apply fix for {id}."
verification = "Add regression coverage for {id}."
source_packets = ["{source_ref}"]
confidence_label = "HIGH"
confidence_score = 90
"#,
                line = 10 + total,
            ));
        }
    }
    (body, ids, total)
}

fn valid_parent_report(
    reviewer_id: &str,
    session_id: &str,
    target_ref: &str,
    counts: SeverityCounts,
) -> String {
    let source_ref = format!("child:feedface:{session_id}");
    let (merged_findings, ids, total) = findings_toml(counts.clone(), &source_ref, "MF");
    let defended_summary = if total == 0 {
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
    let findings_line = if ids.is_empty() {
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
notes = "Open findings still require action."

[[ship_readiness_axes]]
axis = "Safety"
status = "PASS"
notes = "No direct safety regression was confirmed."

[[ship_readiness_axes]]
axis = "Complexity budget"
status = "PASS"
notes = "The fix scope remains proportionate."

[[ship_readiness_axes]]
axis = "Test coverage"
status = "CONDITIONAL"
notes = "Coverage follow-up may still be required."

[[ship_readiness_axes]]
axis = "Acceptance criteria"
status = "CONDITIONAL"
notes = "One acceptance criterion remains fix-dependent."

[[source_packets]]
reviewer_id = "feedface"
session_id = "{session_id}"
artifact_ref = "{source_ref}"
{merged_findings}
{defended_summary}
[[residual_risks]]
area = "Runtime parity"
gap = "Production traffic replay was not run."
impact = "Some environment-specific behavior may still differ."
next_action = "Run staging validation."

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
- Cross-cutting invariants were synthesized with confidence.

## Residual Risk
- Runtime parity remains unverified.
"#,
        blocker = counts.blocker,
        major = counts.major,
        minor = counts.minor,
        nit = counts.nit,
    )
}

fn valid_child_report(
    reviewer_id: &str,
    session_id: &str,
    target_ref: &str,
    counts: SeverityCounts,
) -> String {
    let findings = if counts.blocker + counts.major + counts.minor + counts.nit == 0 {
        String::new()
    } else {
        r#"
[[findings]]
id = "F1"
theorem_id = "T1"
domain = "Architecture"
severity = "MAJOR"
anchor = "src/lib.rs:10"
claim = "The abstraction should preserve invariant T1."
disproof = "A concrete scenario violates the invariant."
evidence = "Trace reaches the failing branch."
recommendation = "Inline the extra layer."
verification = "Add regression coverage."
confidence_label = "HIGH"
confidence_score = 88
"#
        .to_string()
    };
    let finding_count = if counts.blocker + counts.major + counts.minor + counts.nit == 0 {
        0
    } else {
        1
    };
    let defended_count = 1;
    let overall_verdict = if finding_count == 0 {
        "APPROVE"
    } else {
        "REQUEST_CHANGES"
    };
    format!(
        r#"# Proof Packet

```toml
schema_version = "proof_packet.v2"
artifact_kind = "child_proof_packet"
role_slug = "architecture-critic"
role_title = "Architecture Critic"
reviewer_id = "{reviewer_id}"
session_id = "{session_id}"
target_ref = "{target_ref}"
overall_verdict = "{overall_verdict}"
overall_confidence_label = "HIGH"
overall_confidence_score = 90

[coverage]
files_reviewed = ["src/lib.rs"]
domains_in_scope = ["Architecture"]
domains_out_of_scope = []
tests_run = []
tests_not_run_reason = "No focused tests were available."
limitations = ["No runtime benchmark was executed."]

[[domain_ledger]]
domain = "Architecture"
scope = "IN_SCOPE"
rationale = "The change introduces abstraction boundaries."
theorems = 2
disproofs = 2
findings = {finding_count}
defended = {defended_count}

[[theorems]]
id = "T1"
domain = "Architecture"
claim = "The new abstraction keeps control flow obvious."
anchors = ["src/lib.rs:10"]

[[theorems]]
id = "T2"
domain = "Architecture"
claim = "The new abstraction is justified by present needs."
anchors = ["src/lib.rs:22"]

[[disproof_attempts]]
id = "D1"
theorem_id = "T1"
scenario = "Trace the common-path call graph."
result = "{first_result}"
evidence = "Common path requires additional indirection."

[[disproof_attempts]]
id = "D2"
theorem_id = "T2"
scenario = "Check for a second concrete consumer."
result = "DEFENDED"
evidence = "The abstraction supports two call sites."
{findings}
[[defended_proofs]]
theorem_id = "{defended_theorem}"
anchor = "src/lib.rs:22"
disproof_attempt = "Checked for a second concrete consumer."
outcome = "Defended"
confidence_label = "MEDIUM"
confidence_score = 68
rationale = "Current call sites justify the abstraction."

[[residual_risks]]
area = "Future simplification"
gap = "The abstraction could become stale after follow-up refactors."
impact = "Maintainability may degrade over time."
next_action = "Re-evaluate after the next API change."
```

## Proof Packet: Architecture Critic

### Domain Ledger
| Domain | Scope | Theorems | Disproofs | Findings | Defended |
|--------|-------|----------|-----------|----------|----------|
| Architecture | In-scope | 2 | 2 | {finding_count} | {defended_count} |

### Coverage
- Files reviewed: `src/lib.rs`
- Domains covered: Architecture

### Findings
- Structured findings are included in the machine block.

### Defended Proofs
- Structured defended proofs are included in the machine block.

### Residual Risk
- The abstraction should be re-evaluated after the next API change.

OUTPUT_COMPLETE
"#,
        first_result = if finding_count == 0 {
            "DEFENDED"
        } else {
            "FINDING"
        },
        defended_theorem = if finding_count == 0 { "T1" } else { "T2" },
    )
}

fn session_without_notes(session_dir: &Path) -> SessionFile {
    SessionFile {
        schema_version: "1.2.0".to_string(),
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
            child_reviews: Vec::new(),
            extra: serde_json::Map::default(),
        }],
        extra: serde_json::Map::new(),
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

fn run_cmd_failure(args: &[&str]) -> anyhow::Result<String> {
    let output = Command::new(env!("CARGO_BIN_EXE_mpcr"))
        .args(args)
        .output()?;
    if output.status.success() {
        return Err(anyhow::anyhow!("mpcr unexpectedly succeeded"));
    }
    Ok(String::from_utf8_lossy(&output.stderr).to_string())
}

fn read_session_json(session_dir: &Path) -> anyhow::Result<Value> {
    let session = load_session(&SessionLocator::new(session_dir.to_path_buf()))?;
    Ok(serde_json::to_value(session)?)
}

fn read_session_raw_json(session_dir: &Path) -> anyhow::Result<Value> {
    let toml_path = session_dir.join("_session.toml");
    if toml_path.exists() {
        let raw = fs::read_to_string(toml_path)?;
        let value: toml::Value = toml::from_str(&raw)?;
        return Ok(serde_json::to_value(value)?);
    }

    let json_path = session_dir.join("_session.json");
    if json_path.exists() {
        let raw = fs::read_to_string(json_path)?;
        return Ok(serde_json::from_str(&raw)?);
    }

    Err(anyhow::anyhow!(
        "session artifact missing under {}",
        session_dir.display()
    ))
}

fn find_review<'a>(
    session: &'a Value,
    reviewer_id: &str,
    session_id: &str,
) -> anyhow::Result<&'a Value> {
    fn find_review_recursive<'a>(
        reviews: &'a [Value],
        reviewer_id: &str,
        session_id: &str,
    ) -> Option<&'a Value> {
        for review in reviews {
            let is_match = match (review.get("reviewer_id"), review.get("session_id")) {
                (Some(Value::String(rid)), Some(Value::String(sid))) => {
                    rid == reviewer_id && sid == session_id
                }
                _ => false,
            };
            if is_match {
                return Some(review);
            }
        }

        for review in reviews {
            if let Some(children) = review.get("child_reviews").and_then(Value::as_array) {
                if let Some(found) = find_review_recursive(children, reviewer_id, session_id) {
                    return Some(found);
                }
            }
        }
        None
    }

    let reviews = json_array(session, "reviews")?;
    find_review_recursive(reviews, reviewer_id, session_id)
        .ok_or_else(|| anyhow::anyhow!("review entry not found"))
}

fn find_child_review<'a>(
    parent_review: &'a Value,
    reviewer_id: &str,
    session_id: &str,
) -> anyhow::Result<&'a Value> {
    let children = json_array(parent_review, "child_reviews")?;
    children
        .iter()
        .find(
            |review| match (review.get("reviewer_id"), review.get("session_id")) {
                (Some(Value::String(rid)), Some(Value::String(sid))) => {
                    rid == reviewer_id && sid == session_id
                }
                _ => false,
            },
        )
        .ok_or_else(|| anyhow::anyhow!("child review entry not found"))
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
fn reports_hide_leaf_children_but_include_non_leaf_children() -> anyhow::Result<()> {
    let repo_root = tempfile::tempdir()?;
    let repo_root_str = repo_root.path().to_string_lossy().to_string();

    let parent = run_cmd_json(&[
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
    let session_dir = json_str(&parent, "session_dir")?.to_string();

    let spawned_child = run_cmd_json(&[
        "reviewer",
        "spawn-children",
        "--target-ref",
        "refs/heads/main",
        "--session-dir",
        &session_dir,
        "--session-id",
        "sess0001",
        "--parent-id",
        "deadbeef",
        "--count",
        "1",
    ])?;
    let child = json_array(&spawned_child, "children")?
        .first()
        .ok_or_else(|| anyhow::anyhow!("child missing"))?
        .clone();
    let child_id = json_str(&child, "reviewer_id")?.to_string();

    let spawned_grandchild = run_cmd_json(&[
        "reviewer",
        "spawn-children",
        "--target-ref",
        "refs/heads/main",
        "--session-dir",
        &session_dir,
        "--session-id",
        "sess0001",
        "--parent-id",
        &child_id,
        "--count",
        "1",
    ])?;
    let grandchild = json_array(&spawned_grandchild, "children")?
        .first()
        .ok_or_else(|| anyhow::anyhow!("grandchild missing"))?
        .clone();
    let grandchild_id = json_str(&grandchild, "reviewer_id")?;

    let reports = run_reports(Path::new(&session_dir), &["session", "reports", "open"])?;
    ensure!(json_u64(&reports, "matching_reviews")? == 2);

    let reviews = json_array(&reports, "reviews")?;
    ensure!(reviews.len() == 2);

    let parent_review = reviews
        .iter()
        .find(|review| json_str(review, "reviewer_id").ok() == Some("deadbeef"))
        .ok_or_else(|| anyhow::anyhow!("parent review missing"))?;
    ensure!(json_array(parent_review, "child_reviews")?.len() == 1);

    let child_review = reviews
        .iter()
        .find(|review| json_str(review, "reviewer_id").ok() == Some(child_id.as_str()))
        .ok_or_else(|| anyhow::anyhow!("non-leaf child review missing"))?;
    ensure!(json_array(child_review, "child_reviews")?.len() == 1);

    let has_grandchild_top_level = reviews
        .iter()
        .any(|review| json_str(review, "reviewer_id").ok() == Some(grandchild_id));
    ensure!(!has_grandchild_top_level);

    let reports_with_leaf = run_reports(
        Path::new(&session_dir),
        &["session", "reports", "open", "--include-leaf-children"],
    )?;
    ensure!(json_u64(&reports_with_leaf, "matching_reviews")? == 3);
    let reviews_with_leaf = json_array(&reports_with_leaf, "reviews")?;
    ensure!(reviews_with_leaf.len() == 3);
    let has_grandchild_with_leaf = reviews_with_leaf
        .iter()
        .any(|review| json_str(review, "reviewer_id").ok() == Some(grandchild_id));
    ensure!(has_grandchild_with_leaf);

    Ok(())
}

#[test]
fn reports_closed_include_leaf_children_for_applicator_ingestion() -> anyhow::Result<()> {
    let dir = tempfile::tempdir()?;
    let session_dir = dir.path().join("session");
    fs::create_dir_all(&session_dir)?;

    let parent_report = "parent.md";
    let child_report = "child.md";
    let grandchild_report = "grandchild.md";
    fs::write(session_dir.join(parent_report), "parent report body")?;
    fs::write(session_dir.join(child_report), "child report body")?;
    fs::write(
        session_dir.join(grandchild_report),
        "grandchild report body",
    )?;

    let parent = ReviewEntry {
        reviewer_id: "deadbeef".to_string(),
        session_id: "sess0001".to_string(),
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
        report_file: Some(parent_report.to_string()),
        notes: Vec::new(),
        child_reviews: Vec::new(),
        extra: serde_json::Map::default(),
    };
    let mut child = parent.clone();
    child.reviewer_id = "cafe1234".to_string();
    child.parent_id = Some(parent.reviewer_id.clone());
    child.report_file = Some(child_report.to_string());
    let mut grandchild = parent.clone();
    grandchild.reviewer_id = "babe5678".to_string();
    grandchild.parent_id = Some(child.reviewer_id.clone());
    grandchild.report_file = Some(grandchild_report.to_string());

    write_session_file(
        &session_dir,
        &SessionFile {
            schema_version: "1.2.0".to_string(),
            session_date: "2026-01-11".to_string(),
            repo_root: session_dir.to_string_lossy().to_string(),
            reviewers: vec![
                parent.reviewer_id.clone(),
                child.reviewer_id.clone(),
                grandchild.reviewer_id.clone(),
            ],
            reviews: vec![parent, child, grandchild],
            extra: serde_json::Map::new(),
        },
    )?;

    let closed_default = run_reports(
        &session_dir,
        &["session", "reports", "closed", "--include-report-contents"],
    )?;
    ensure!(json_u64(&closed_default, "matching_reviews")? == 2);
    let default_reviews = json_array(&closed_default, "reviews")?;
    ensure!(!default_reviews
        .iter()
        .any(|review| json_str(review, "reviewer_id").ok() == Some("babe5678")));

    let closed_with_leaf = run_reports(
        &session_dir,
        &[
            "session",
            "reports",
            "closed",
            "--include-report-contents",
            "--include-leaf-children",
        ],
    )?;
    ensure!(json_u64(&closed_with_leaf, "matching_reviews")? == 3);
    let with_leaf_reviews = json_array(&closed_with_leaf, "reviews")?;
    let grandchild_review = with_leaf_reviews
        .iter()
        .find(|review| json_str(review, "reviewer_id").ok() == Some("babe5678"))
        .ok_or_else(|| anyhow::anyhow!("grandchild review missing with leaf inclusion"))?;
    ensure!(json_str(grandchild_review, "report_contents")?.contains("grandchild report body"));

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
    let lock_file = session_dir.join("_session.toml.lock");
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
    ensure!(json_str(&value, "schema_version")? == "1.2.0");
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
    ensure!(json_str(&value, "schema_version")? == "1.2.0");
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
    ensure!(session_file.ends_with("_session.toml"));

    let session = read_session_json(Path::new(session_dir))?;
    let entry = find_review(&session, "deadbeef", "sess0001")?;
    ensure!(json_str(entry, "status")? == "INITIALIZING");
    Ok(())
}

#[test]
fn reviewer_register_clear_session_day_removes_existing_day_dir() -> anyhow::Result<()> {
    let repo_root = tempfile::tempdir()?;
    let repo_root_str = repo_root.path().to_string_lossy().to_string();
    let date = Date::from_calendar_date(2026, Month::January, 11)?;
    let session_dir = paths::session_paths(repo_root.path(), date).session_dir;
    fs::create_dir_all(&session_dir)?;
    let stale_file = session_dir.join("stale.txt");
    fs::write(&stale_file, "stale")?;
    ensure!(stale_file.exists());

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
        "--clear-session-day",
    ])?;
    let session_dir_out = json_str(&out, "session_dir")?;
    let session_file_out = json_str(&out, "session_file")?;
    ensure!(Path::new(session_dir_out).exists());
    ensure!(Path::new(session_file_out).exists());
    ensure!(
        !stale_file.exists(),
        "day cleanup should remove stale files first"
    );
    Ok(())
}

#[test]
fn reviewer_register_clear_all_session_days_removes_day_dirs_only() -> anyhow::Result<()> {
    let repo_root = tempfile::tempdir()?;
    let repo_root_str = repo_root.path().to_string_lossy().to_string();
    let code_reviews_root = repo_root
        .path()
        .join(".local")
        .join("reports")
        .join("code_reviews");
    let day_a = code_reviews_root.join("2026-01-09");
    let day_b = code_reviews_root.join("2026-01-10");
    let non_date_dir = code_reviews_root.join("keep-me");
    fs::create_dir_all(&day_a)?;
    fs::create_dir_all(&day_b)?;
    fs::create_dir_all(&non_date_dir)?;
    fs::write(day_a.join("a.txt"), "a")?;
    fs::write(day_b.join("b.txt"), "b")?;
    fs::write(non_date_dir.join("note.txt"), "keep")?;

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
        "--clear-all-session-days",
    ])?;
    let session_dir_out = json_str(&out, "session_dir")?;
    ensure!(
        Path::new(session_dir_out).exists(),
        "register should recreate today's directory after cleanup"
    );
    ensure!(!day_a.exists(), "dated dir should be removed");
    ensure!(!day_b.exists(), "dated dir should be removed");
    ensure!(
        non_date_dir.exists(),
        "non-date directories under code_reviews should remain"
    );
    Ok(())
}

#[test]
fn reviewer_register_clear_session_day_validates_ids_before_cleanup() -> anyhow::Result<()> {
    let repo_root = tempfile::tempdir()?;
    let repo_root_str = repo_root.path().to_string_lossy().to_string();
    let date = Date::from_calendar_date(2026, Month::January, 11)?;
    let session_dir = paths::session_paths(repo_root.path(), date).session_dir;
    fs::create_dir_all(&session_dir)?;
    let stale_file = session_dir.join("stale.txt");
    fs::write(&stale_file, "stale")?;

    let stderr = run_cmd_failure(&[
        "reviewer",
        "register",
        "--target-ref",
        "refs/heads/main",
        "--repo-root",
        &repo_root_str,
        "--date",
        "2026-01-11",
        "--reviewer-id",
        "nothex",
        "--session-id",
        "sess0001",
        "--clear-session-day",
    ])?;

    ensure!(stderr.contains("reviewer_id must be 8 ASCII alphanumeric characters"));
    ensure!(
        stale_file.exists(),
        "cleanup should not run before id validation"
    );
    Ok(())
}

#[test]
fn reviewer_register_rejects_cleanup_flags_for_child_registration() -> anyhow::Result<()> {
    let repo_root = tempfile::tempdir()?;
    let repo_root_str = repo_root.path().to_string_lossy().to_string();
    let date = Date::from_calendar_date(2026, Month::January, 11)?;
    let session_dir = paths::session_paths(repo_root.path(), date).session_dir;
    fs::create_dir_all(&session_dir)?;
    let stale_file = session_dir.join("stale.txt");
    fs::write(&stale_file, "stale")?;

    let stderr = run_cmd_failure(&[
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
        "--parent-id",
        "cafebabe",
        "--clear-session-day",
    ])?;

    ensure!(stderr.contains("cleanup flags are not allowed with --parent-id"));
    ensure!(
        stale_file.exists(),
        "cleanup should not run for child registration"
    );
    Ok(())
}

#[test]
fn reviewer_register_cleanup_flags_are_mutually_exclusive() -> anyhow::Result<()> {
    let repo_root = tempfile::tempdir()?;
    let repo_root_str = repo_root.path().to_string_lossy().to_string();

    let err = run_cmd_failure(&[
        "reviewer",
        "register",
        "--target-ref",
        "refs/heads/main",
        "--repo-root",
        &repo_root_str,
        "--date",
        "2026-01-11",
        "--clear-session-day",
        "--clear-all-session-days",
    ])?;
    ensure!(
        err.contains("cannot be used with"),
        "expected clap conflict error, got: {err}"
    );
    Ok(())
}

#[test]
fn reviewer_register_default_does_not_clear_existing_day_dir() -> anyhow::Result<()> {
    let repo_root = tempfile::tempdir()?;
    let repo_root_str = repo_root.path().to_string_lossy().to_string();
    let date = Date::from_calendar_date(2026, Month::January, 11)?;
    let session_dir = paths::session_paths(repo_root.path(), date).session_dir;
    fs::create_dir_all(&session_dir)?;
    let stale_file = session_dir.join("stale.txt");
    fs::write(&stale_file, "stale")?;
    ensure!(stale_file.exists());

    run_cmd_json(&[
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

    ensure!(
        stale_file.exists(),
        "without cleanup flags, existing day artifacts should remain"
    );
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
    fs::write(
        &report_file,
        valid_parent_report(
            "deadbeef",
            "sess0001",
            "refs/heads/main",
            SeverityCounts {
                blocker: 0,
                major: 2,
                minor: 0,
                nit: 0,
            },
        ),
    )?;

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
    ensure!(contents.contains("artifact_kind = \"parent_review_report\""));
    ensure!(
        !report_file.exists(),
        "source report should be moved by default"
    );

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
fn reviewer_finalize_copy_report_input_preserves_source() -> anyhow::Result<()> {
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

    let source_report = repo_root.path().join("review.md");
    fs::write(
        &source_report,
        valid_parent_report(
            "deadbeef",
            "sess0001",
            "refs/heads/main",
            SeverityCounts::zero(),
        ),
    )?;

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
        "--report-file",
        source_report.to_string_lossy().as_ref(),
        "--copy-report-input",
    ])?;

    let report_path = json_str(&result, "report_path")?;
    ensure!(Path::new(report_path).exists());
    ensure!(
        source_report.exists(),
        "source report should remain in copy mode"
    );
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
    stdin.write_all(
        valid_parent_report(
            "deadbeef",
            "sess0001",
            "refs/heads/main",
            SeverityCounts::zero(),
        )
        .as_bytes(),
    )?;
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
    ensure!(contents.contains("artifact_kind = \"parent_review_report\""));
    Ok(())
}

#[test]
fn reviewer_validate_report_allows_omitting_expected_counts() -> anyhow::Result<()> {
    let tmp = tempfile::tempdir()?;
    let report_path = tmp.path().join("child.md");
    fs::write(
        &report_path,
        valid_child_report(
            "facefeed",
            "sess4321",
            "refs/heads/main",
            SeverityCounts {
                blocker: 0,
                major: 1,
                minor: 0,
                nit: 0,
            },
        ),
    )?;
    let report_path_str = report_path
        .to_str()
        .ok_or_else(|| anyhow::anyhow!("non-UTF-8 report path"))?;

    let summary = run_cmd_json(&[
        "reviewer",
        "validate-report",
        "--kind",
        "child-proof-packet",
        "--report-file",
        report_path_str,
    ])?;
    ensure!(
        json_u64(&summary, "findings")? == 1,
        "expected one finding in validation summary"
    );
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
    ensure!(stdout.contains(&format!("export MPCR_REPO_ROOT='{repo_root_str}'\n")));
    ensure!(stdout.contains("export MPCR_DATE='2026-01-11'\n"));
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
    let expected_session_file = Path::new(&expected_session_dir)
        .join("_session.toml")
        .to_string_lossy()
        .to_string();
    ensure!(stdout.contains(&format!(
        "export MPCR_SESSION_FILE='{expected_session_file}'\n"
    )));
    ensure!(stdout.contains("export MPCR_SESSION_FORMAT='toml_primary'\n"));
    Ok(())
}

#[test]
fn reviewer_register_emit_env_sh_exports_parent_id_when_set() -> anyhow::Result<()> {
    let repo_root = tempfile::tempdir()?;
    let repo_root_str = repo_root.path().to_string_lossy().to_string();

    run_cmd_json(&[
        "reviewer",
        "register",
        "--target-ref",
        "refs/heads/main",
        "--repo-root",
        &repo_root_str,
        "--date",
        "2026-01-11",
        "--reviewer-id",
        "cafebabe",
        "--session-id",
        "sess0001",
    ])?;

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
            "--parent-id",
            "cafebabe",
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
    ensure!(stdout.contains("export MPCR_PARENT_ID='cafebabe'\n"));
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
            "--use-env",
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
        .args(["--use-env", "applicator", "wait", "--json"])
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
fn reviewer_update_does_not_read_env_without_use_env() -> anyhow::Result<()> {
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
        .env("MPCR_SESSION_DIR", "/tmp/does-not-matter")
        .output()?;

    ensure!(!output.status.success());
    let stderr = String::from_utf8_lossy(&output.stderr);
    ensure!(stderr.contains("--reviewer-id"));
    Ok(())
}

#[test]
fn reviewer_update_does_not_use_session_dir_env_without_use_env() -> anyhow::Result<()> {
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
        "a1b2c3d4",
        "--session-id",
        "s1e2s3s4",
    ])?;
    let env_session_dir = json_str(&out, "session_dir")?.to_string();

    let output = Command::new(env!("CARGO_BIN_EXE_mpcr"))
        .args([
            "reviewer",
            "update",
            "--reviewer-id",
            "a1b2c3d4",
            "--session-id",
            "s1e2s3s4",
            "--status",
            "IN_PROGRESS",
            "--phase",
            "DOMAIN_COVERAGE",
            "--json",
        ])
        .env("MPCR_SESSION_DIR", &env_session_dir)
        .output()?;
    ensure!(
        !output.status.success(),
        "MPCR_SESSION_DIR should be ignored without --use-env"
    );

    let session = read_session_json(Path::new(&env_session_dir))?;
    let entry = find_review(&session, "a1b2c3d4", "s1e2s3s4")?;
    ensure!(
        json_str(entry, "status")? == "INITIALIZING",
        "entry should remain unchanged when env session-dir is ignored"
    );
    Ok(())
}

#[test]
fn reviewer_register_print_env_json_outputs_expected_vars() -> anyhow::Result<()> {
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
        "--print-env",
    ])?;

    ensure!(json_str(&out, "MPCR_REPO_ROOT")? == repo_root_str);
    ensure!(json_str(&out, "MPCR_DATE")? == "2026-01-11");
    ensure!(json_str(&out, "MPCR_REVIEWER_ID")? == "deadbeef");
    ensure!(json_str(&out, "MPCR_SESSION_ID")? == "sess0001");
    ensure!(json_str(&out, "MPCR_TARGET_REF")? == "refs/heads/main");
    let session_dir = json_str(&out, "MPCR_SESSION_DIR")?.to_string();
    let session_file = json_str(&out, "MPCR_SESSION_FILE")?.to_string();
    ensure!(json_str(&out, "MPCR_SESSION_FORMAT")? == "toml_primary");
    ensure!(
        Path::new(&session_dir)
            .join("_session.toml")
            .to_string_lossy()
            == session_file
    );
    Ok(())
}

#[test]
fn reviewer_register_print_env_json_outputs_parent_id_when_set() -> anyhow::Result<()> {
    let repo_root = tempfile::tempdir()?;
    let repo_root_str = repo_root.path().to_string_lossy().to_string();

    run_cmd_json(&[
        "reviewer",
        "register",
        "--target-ref",
        "refs/heads/main",
        "--repo-root",
        &repo_root_str,
        "--date",
        "2026-01-11",
        "--reviewer-id",
        "cafebabe",
        "--session-id",
        "sess0001",
    ])?;

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
        "--parent-id",
        "cafebabe",
        "--print-env",
    ])?;

    ensure!(json_str(&out, "MPCR_PARENT_ID")? == "cafebabe");
    Ok(())
}

#[test]
fn reviewer_register_with_parent_id_errors_when_parent_missing() -> anyhow::Result<()> {
    let repo_root = tempfile::tempdir()?;
    let repo_root_str = repo_root.path().to_string_lossy().to_string();

    let output = Command::new(env!("CARGO_BIN_EXE_mpcr"))
        .args([
            "--json",
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
            "--parent-id",
            "cafebabe",
        ])
        .output()?;

    ensure!(!output.status.success());
    let stderr = String::from_utf8_lossy(&output.stderr);
    ensure!(stderr.contains("parent review entry not found"));
    Ok(())
}

#[test]
fn reviewer_register_with_parent_id_uses_parent_session_when_session_id_omitted(
) -> anyhow::Result<()> {
    let repo_root = tempfile::tempdir()?;
    let repo_root_str = repo_root.path().to_string_lossy().to_string();

    run_cmd_json(&[
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

    // Create another active session for the same target_ref to ensure parent-based
    // session selection is deterministic (not order-dependent on "first active session").
    run_cmd_json(&[
        "reviewer",
        "register",
        "--target-ref",
        "refs/heads/main",
        "--repo-root",
        &repo_root_str,
        "--date",
        "2026-01-11",
        "--reviewer-id",
        "cafebabe",
        "--session-id",
        "sess0002",
    ])?;

    let out = run_cmd_json(&[
        "reviewer",
        "register",
        "--target-ref",
        "refs/heads/main",
        "--repo-root",
        &repo_root_str,
        "--date",
        "2026-01-11",
        "--parent-id",
        "deadbeef",
    ])?;

    ensure!(json_str(&out, "session_id")? == "sess0001");
    ensure!(json_str(&out, "parent_id")? == "deadbeef");
    Ok(())
}

#[test]
fn reviewer_register_with_parent_id_errors_when_parent_session_is_ambiguous() -> anyhow::Result<()>
{
    let repo_root = tempfile::tempdir()?;
    let repo_root_str = repo_root.path().to_string_lossy().to_string();

    run_cmd_json(&[
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

    run_cmd_json(&[
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
        "sess0002",
    ])?;

    let output = Command::new(env!("CARGO_BIN_EXE_mpcr"))
        .args([
            "--json",
            "reviewer",
            "register",
            "--target-ref",
            "refs/heads/main",
            "--repo-root",
            &repo_root_str,
            "--date",
            "2026-01-11",
            "--parent-id",
            "deadbeef",
        ])
        .output()?;

    ensure!(!output.status.success());
    let stderr = String::from_utf8_lossy(&output.stderr);
    ensure!(stderr.contains("ambiguous"));
    ensure!(stderr.contains("--session-id"));
    Ok(())
}

#[test]
fn reviewer_register_with_parent_id_reuses_existing_child_entry_without_session_id(
) -> anyhow::Result<()> {
    let repo_root = tempfile::tempdir()?;
    let repo_root_str = repo_root.path().to_string_lossy().to_string();

    run_cmd_json(&[
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

    run_cmd_json(&[
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
        "sess0002",
    ])?;

    run_cmd_json(&[
        "reviewer",
        "register",
        "--target-ref",
        "refs/heads/main",
        "--repo-root",
        &repo_root_str,
        "--date",
        "2026-01-11",
        "--reviewer-id",
        "c001d00d",
        "--session-id",
        "sess0001",
        "--parent-id",
        "deadbeef",
    ])?;

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
        "c001d00d",
        "--parent-id",
        "deadbeef",
    ])?;

    ensure!(json_str(&out, "session_id")? == "sess0001");
    ensure!(json_str(&out, "reviewer_id")? == "c001d00d");
    ensure!(json_str(&out, "parent_id")? == "deadbeef");
    Ok(())
}

#[test]
fn reviewer_register_errors_when_session_id_reused_for_different_target_ref() -> anyhow::Result<()>
{
    let repo_root = tempfile::tempdir()?;
    let repo_root_str = repo_root.path().to_string_lossy().to_string();

    run_cmd_json(&[
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

    let output = Command::new(env!("CARGO_BIN_EXE_mpcr"))
        .args([
            "--json",
            "reviewer",
            "register",
            "--target-ref",
            "refs/heads/other",
            "--repo-root",
            &repo_root_str,
            "--date",
            "2026-01-11",
            "--reviewer-id",
            "cafebabe",
            "--session-id",
            "sess0001",
        ])
        .output()?;

    ensure!(!output.status.success());
    let stderr = String::from_utf8_lossy(&output.stderr);
    ensure!(stderr.contains("session_id already exists for a different target_ref"));
    Ok(())
}

#[test]
fn reviewer_register_updates_parent_id_for_existing_entry_when_missing() -> anyhow::Result<()> {
    let repo_root = tempfile::tempdir()?;
    let repo_root_str = repo_root.path().to_string_lossy().to_string();

    let initial = run_cmd_json(&[
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
    let session_dir = json_str(&initial, "session_dir")?.to_string();

    run_cmd_json(&[
        "reviewer",
        "register",
        "--target-ref",
        "refs/heads/main",
        "--repo-root",
        &repo_root_str,
        "--date",
        "2026-01-11",
        "--reviewer-id",
        "cafebabe",
        "--session-id",
        "sess0001",
    ])?;

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
        "--parent-id",
        "cafebabe",
        "--print-env",
    ])?;
    ensure!(json_str(&out, "MPCR_PARENT_ID")? == "cafebabe");

    let session = read_session_json(Path::new(&session_dir))?;
    let entry = find_review(&session, "deadbeef", "sess0001")?;
    ensure!(json_str(entry, "parent_id")? == "cafebabe");
    Ok(())
}

#[test]
fn reviewer_spawn_children_creates_entries_with_parent_id() -> anyhow::Result<()> {
    let repo_root = tempfile::tempdir()?;
    let repo_root_str = repo_root.path().to_string_lossy().to_string();

    let initial = run_cmd_json(&[
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
    let session_dir = json_str(&initial, "session_dir")?.to_string();

    let out = run_cmd_json(&[
        "reviewer",
        "spawn-children",
        "--target-ref",
        "refs/heads/main",
        "--session-dir",
        &session_dir,
        "--session-id",
        "sess0001",
        "--parent-id",
        "deadbeef",
        "--count",
        "3",
    ])?;

    ensure!(json_str(&out, "parent_id")? == "deadbeef");
    ensure!(json_str(&out, "session_id")? == "sess0001");
    ensure!(json_str(&out, "target_ref")? == "refs/heads/main");
    ensure!(json_str(&out, "session_dir")? == session_dir);

    let children = json_array(&out, "children")?;
    ensure!(children.len() == 3);

    let session = read_session_json(Path::new(&session_dir))?;
    let parent = find_review(&session, "deadbeef", "sess0001")?;
    let parent_children = json_array(parent, "child_reviews")?;
    ensure!(parent_children.len() == 3);
    for child in children {
        let child_id = json_str(child, "reviewer_id")?;
        ensure!(json_str(child, "parent_id")? == "deadbeef");

        let entry = find_review(&session, child_id, "sess0001")?;
        ensure!(json_str(entry, "parent_id")? == "deadbeef");
    }
    Ok(())
}

#[test]
fn session_file_stores_children_nested_under_parent_only() -> anyhow::Result<()> {
    let repo_root = tempfile::tempdir()?;
    let repo_root_str = repo_root.path().to_string_lossy().to_string();

    let initial = run_cmd_json(&[
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
    let session_dir = json_str(&initial, "session_dir")?.to_string();

    let spawned = run_cmd_json(&[
        "reviewer",
        "spawn-children",
        "--target-ref",
        "refs/heads/main",
        "--session-dir",
        &session_dir,
        "--session-id",
        "sess0001",
        "--parent-id",
        "deadbeef",
        "--count",
        "3",
    ])?;
    let children = json_array(&spawned, "children")?;

    let session = read_session_raw_json(Path::new(&session_dir))?;
    let reviews = json_array(&session, "reviews")?;
    ensure!(reviews.len() == 1);

    let parent = reviews
        .first()
        .ok_or_else(|| anyhow::anyhow!("parent review missing"))?;
    ensure!(json_str(parent, "reviewer_id")? == "deadbeef");
    let nested_children = json_array(parent, "child_reviews")?;
    ensure!(nested_children.len() == 3);

    for child in children {
        let child_id = json_str(child, "reviewer_id")?;
        let exists_top_level = reviews
            .iter()
            .any(|review| json_str(review, "reviewer_id").ok() == Some(child_id));
        ensure!(!exists_top_level);
    }

    Ok(())
}

#[test]
fn child_review_updates_are_embedded_under_parent() -> anyhow::Result<()> {
    let repo_root = tempfile::tempdir()?;
    let repo_root_str = repo_root.path().to_string_lossy().to_string();

    let parent = run_cmd_json(&[
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
    let session_dir = json_str(&parent, "session_dir")?.to_string();

    let spawned = run_cmd_json(&[
        "reviewer",
        "spawn-children",
        "--target-ref",
        "refs/heads/main",
        "--session-dir",
        &session_dir,
        "--session-id",
        "sess0001",
        "--parent-id",
        "deadbeef",
        "--count",
        "1",
    ])?;
    let children = json_array(&spawned, "children")?;
    let child = children
        .first()
        .ok_or_else(|| anyhow::anyhow!("child missing"))?;
    let child_id = json_str(child, "reviewer_id")?;

    run_cmd_json(&[
        "reviewer",
        "update",
        "--session-dir",
        &session_dir,
        "--reviewer-id",
        child_id,
        "--session-id",
        "sess0001",
        "--status",
        "IN_PROGRESS",
        "--phase",
        "INGESTION",
    ])?;

    let session = read_session_json(Path::new(&session_dir))?;
    let parent_review = find_review(&session, "deadbeef", "sess0001")?;
    let child_summary = find_child_review(parent_review, child_id, "sess0001")?;
    ensure!(json_str(child_summary, "status")? == "IN_PROGRESS");
    ensure!(json_str(child_summary, "current_phase")? == "INGESTION");

    let source_report = repo_root.path().join("child.md");
    fs::write(
        &source_report,
        valid_parent_report(
            child_id,
            "sess0001",
            "refs/heads/main",
            SeverityCounts::zero(),
        ),
    )?;
    run_cmd_json(&[
        "reviewer",
        "finalize",
        "--session-dir",
        &session_dir,
        "--reviewer-id",
        child_id,
        "--session-id",
        "sess0001",
        "--verdict",
        "APPROVE",
        "--report-file",
        source_report.to_string_lossy().as_ref(),
    ])?;

    run_cmd_json(&[
        "applicator",
        "set-status",
        "--session-dir",
        &session_dir,
        "--reviewer-id",
        child_id,
        "--session-id",
        "sess0001",
        "--initiator-status",
        "RECEIVED",
    ])?;

    let session = read_session_json(Path::new(&session_dir))?;
    let parent_review = find_review(&session, "deadbeef", "sess0001")?;
    let child_summary = find_child_review(parent_review, child_id, "sess0001")?;
    ensure!(json_str(child_summary, "status")? == "FINISHED");
    ensure!(json_str(child_summary, "verdict")? == "APPROVE");
    ensure!(json_str(child_summary, "initiator_status")? == "RECEIVED");
    ensure!(
        child_summary.get("report_file").is_some(),
        "expected embedded report_file"
    );
    Ok(())
}

#[test]
fn reviewer_close_children_cancels_open_children() -> anyhow::Result<()> {
    let repo_root = tempfile::tempdir()?;
    let repo_root_str = repo_root.path().to_string_lossy().to_string();

    let parent = run_cmd_json(&[
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
    let session_dir = json_str(&parent, "session_dir")?.to_string();

    let spawned = run_cmd_json(&[
        "reviewer",
        "spawn-children",
        "--target-ref",
        "refs/heads/main",
        "--session-dir",
        &session_dir,
        "--session-id",
        "sess0001",
        "--parent-id",
        "deadbeef",
        "--count",
        "2",
    ])?;

    let result = run_cmd_json(&[
        "reviewer",
        "close-children",
        "--session-dir",
        &session_dir,
        "--parent-id",
        "deadbeef",
        "--session-id",
        "sess0001",
        "--clear-phase",
    ])?;
    ensure!(json_u64(&result, "matching_children")? == 2);
    ensure!(json_u64(&result, "updated_children")? == 2);

    let children = json_array(&spawned, "children")?;
    let session = read_session_json(Path::new(&session_dir))?;
    for child in children {
        let child_id = json_str(child, "reviewer_id")?;
        let child_entry = find_review(&session, child_id, "sess0001")?;
        ensure!(json_str(child_entry, "status")? == "CANCELLED");
        ensure!(json_is_null_or_missing(child_entry, "current_phase"));
    }

    Ok(())
}

#[test]
fn reviewer_finalize_auto_closes_open_children() -> anyhow::Result<()> {
    let repo_root = tempfile::tempdir()?;
    let repo_root_str = repo_root.path().to_string_lossy().to_string();

    let parent = run_cmd_json(&[
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
    let session_dir = json_str(&parent, "session_dir")?.to_string();

    let spawned = run_cmd_json(&[
        "reviewer",
        "spawn-children",
        "--target-ref",
        "refs/heads/main",
        "--session-dir",
        &session_dir,
        "--session-id",
        "sess0001",
        "--parent-id",
        "deadbeef",
        "--count",
        "2",
    ])?;
    let children = json_array(&spawned, "children")?;
    let first_child = children
        .first()
        .ok_or_else(|| anyhow::anyhow!("child missing"))?;
    let first_child_id = json_str(first_child, "reviewer_id")?;

    run_cmd_json(&[
        "reviewer",
        "update",
        "--session-dir",
        &session_dir,
        "--reviewer-id",
        first_child_id,
        "--session-id",
        "sess0001",
        "--status",
        "IN_PROGRESS",
        "--phase",
        "INGESTION",
    ])?;

    let report_file = repo_root.path().join("parent.md");
    fs::write(
        &report_file,
        valid_parent_report(
            "deadbeef",
            "sess0001",
            "refs/heads/main",
            SeverityCounts {
                blocker: 0,
                major: 1,
                minor: 0,
                nit: 0,
            },
        ),
    )?;
    run_cmd_json(&[
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
        "--major",
        "1",
        "--report-file",
        report_file.to_string_lossy().as_ref(),
    ])?;

    let session = read_session_json(Path::new(&session_dir))?;
    for child in children {
        let child_id = json_str(child, "reviewer_id")?;
        let entry = find_review(&session, child_id, "sess0001")?;
        ensure!(json_str(entry, "status")? == "CANCELLED");
        let notes = json_array(entry, "notes")?;
        let has_auto_close_note = notes.iter().any(|note| {
            matches!(
                note.get("type"),
                Some(Value::String(note_type)) if note_type == "auto_closed_by_parent_finalize"
            )
        });
        ensure!(
            has_auto_close_note,
            "missing auto-close note on child {child_id}"
        );
    }

    let parent_entry = find_review(&session, "deadbeef", "sess0001")?;
    let parent_child = find_child_review(parent_entry, first_child_id, "sess0001")?;
    ensure!(json_str(parent_child, "status")? == "CANCELLED");
    Ok(())
}

#[test]
fn reviewer_finalize_fails_with_no_auto_close_children() -> anyhow::Result<()> {
    let repo_root = tempfile::tempdir()?;
    let repo_root_str = repo_root.path().to_string_lossy().to_string();

    let parent = run_cmd_json(&[
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
    let session_dir = json_str(&parent, "session_dir")?.to_string();

    run_cmd_json(&[
        "reviewer",
        "spawn-children",
        "--target-ref",
        "refs/heads/main",
        "--session-dir",
        &session_dir,
        "--session-id",
        "sess0001",
        "--parent-id",
        "deadbeef",
        "--count",
        "1",
    ])?;

    let report_file = repo_root.path().join("parent.md");
    fs::write(
        &report_file,
        valid_parent_report(
            "deadbeef",
            "sess0001",
            "refs/heads/main",
            SeverityCounts::zero(),
        ),
    )?;
    let reports_before = fs::read_dir(&session_dir)?
        .filter_map(Result::ok)
        .filter(|entry| entry.path().extension().is_some_and(|ext| ext == "md"))
        .count();
    let stderr = run_cmd_failure(&[
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
        "--report-file",
        report_file.to_string_lossy().as_ref(),
        "--no-auto-close-children",
    ])?;
    ensure!(stderr.contains("cannot finalize while child reviews are open"));
    let reports_after = fs::read_dir(&session_dir)?
        .filter_map(Result::ok)
        .filter(|entry| entry.path().extension().is_some_and(|ext| ext == "md"))
        .count();
    ensure!(reports_before == reports_after);
    ensure!(report_file.exists());
    Ok(())
}

#[test]
fn reviewer_spawn_children_rejects_count_above_limit() -> anyhow::Result<()> {
    let repo_root = tempfile::tempdir()?;
    let repo_root_str = repo_root.path().to_string_lossy().to_string();

    let parent = run_cmd_json(&[
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
    let session_dir = json_str(&parent, "session_dir")?.to_string();

    let stderr = run_cmd_failure(&[
        "reviewer",
        "spawn-children",
        "--target-ref",
        "refs/heads/main",
        "--session-dir",
        &session_dir,
        "--session-id",
        "sess0001",
        "--parent-id",
        "deadbeef",
        "--count",
        "33",
    ])?;
    ensure!(stderr.contains("count must be <= 32"));
    Ok(())
}

#[test]
fn reviewer_note_rejects_applicator_note_types() -> anyhow::Result<()> {
    let repo_root = tempfile::tempdir()?;
    let repo_root_str = repo_root.path().to_string_lossy().to_string();

    let parent = run_cmd_json(&[
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
    let session_dir = json_str(&parent, "session_dir")?.to_string();

    let stderr = run_cmd_failure(&[
        "reviewer",
        "note",
        "--session-dir",
        &session_dir,
        "--reviewer-id",
        "deadbeef",
        "--session-id",
        "sess0001",
        "--note-type",
        "applied",
        "--content",
        "should fail",
    ])?;
    ensure!(stderr.contains("not allowed for role `reviewer`"));
    Ok(())
}

#[test]
fn applicator_note_rejects_reviewer_note_types() -> anyhow::Result<()> {
    let repo_root = tempfile::tempdir()?;
    let repo_root_str = repo_root.path().to_string_lossy().to_string();

    let parent = run_cmd_json(&[
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
    let session_dir = json_str(&parent, "session_dir")?.to_string();

    let stderr = run_cmd_failure(&[
        "applicator",
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
        "should fail",
    ])?;
    ensure!(stderr.contains("not allowed for role `applicator`"));
    Ok(())
}

#[test]
fn worker_dispatch_role_allows_id_commands() -> anyhow::Result<()> {
    let output = Command::new(env!("CARGO_BIN_EXE_mpcr"))
        .arg("id")
        .arg("id8")
        .env("MPCR_DISPATCH_ROLE", "security-adversary")
        .output()?;
    ensure!(
        output.status.success(),
        "worker should be allowed to run id commands: {}",
        String::from_utf8_lossy(&output.stderr)
    );
    Ok(())
}

#[test]
fn worker_dispatch_role_allows_reviewer_update() -> anyhow::Result<()> {
    let repo_root = tempfile::tempdir()?;
    let repo_root_str = repo_root.path().to_string_lossy().to_string();
    let parent = run_cmd_json(&[
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
    let session_dir = json_str(&parent, "session_dir")?.to_string();

    let output = Command::new(env!("CARGO_BIN_EXE_mpcr"))
        .args([
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
        ])
        .env("MPCR_DISPATCH_ROLE", "security-adversary")
        .env("MPCR_REVIEWER_ID", "deadbeef")
        .env("MPCR_SESSION_ID", "sess0001")
        .env("MPCR_SESSION_DIR", &session_dir)
        .output()?;
    ensure!(output.status.success());
    Ok(())
}

#[test]
fn reviewer_complete_child_finalizes_and_attaches_proof_note() -> anyhow::Result<()> {
    let repo_root = tempfile::tempdir()?;
    let repo_root_str = repo_root.path().to_string_lossy().to_string();

    let parent = run_cmd_json(&[
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
    let session_dir = json_str(&parent, "session_dir")?.to_string();

    let spawned = run_cmd_json(&[
        "reviewer",
        "spawn-children",
        "--target-ref",
        "refs/heads/main",
        "--session-dir",
        &session_dir,
        "--session-id",
        "sess0001",
        "--parent-id",
        "deadbeef",
        "--count",
        "1",
    ])?;
    let children = json_array(&spawned, "children")?;
    let child = children
        .first()
        .ok_or_else(|| anyhow::anyhow!("child missing"))?;
    let child_id = json_str(child, "reviewer_id")?;

    let child_report = repo_root.path().join("child.md");
    fs::write(
        &child_report,
        valid_child_report(
            child_id,
            "sess0001",
            "refs/heads/main",
            SeverityCounts::zero(),
        ),
    )?;
    run_cmd_json(&[
        "reviewer",
        "complete-child",
        "--session-dir",
        &session_dir,
        "--reviewer-id",
        child_id,
        "--session-id",
        "sess0001",
        "--verdict",
        "APPROVE",
        "--report-file",
        child_report.to_string_lossy().as_ref(),
        "--proof-note",
        "## Proof Packet: child",
    ])?;

    let session = read_session_json(Path::new(&session_dir))?;
    let child_entry = find_review(&session, child_id, "sess0001")?;
    ensure!(json_str(child_entry, "status")? == "FINISHED");
    ensure!(json_str(child_entry, "current_phase")? == "REPORT_WRITING");
    ensure!(json_str(child_entry, "verdict")? == "APPROVE");
    ensure!(child_entry.get("report_file").is_some());
    let child_notes = json_array(child_entry, "notes")?;
    let has_proof_note = child_notes.iter().any(|note| {
        matches!(
            note.get("type"),
            Some(Value::String(note_type)) if note_type == "proof_packet"
        )
    });
    ensure!(has_proof_note);

    let parent_entry = find_review(&session, "deadbeef", "sess0001")?;
    let child_summary = find_child_review(parent_entry, child_id, "sess0001")?;
    ensure!(json_str(child_summary, "status")? == "FINISHED");
    ensure!(child_summary.get("report_file").is_some());
    Ok(())
}

#[test]
fn reviewer_complete_child_fails_for_non_child_entry() -> anyhow::Result<()> {
    let repo_root = tempfile::tempdir()?;
    let repo_root_str = repo_root.path().to_string_lossy().to_string();

    let parent = run_cmd_json(&[
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
    let session_dir = json_str(&parent, "session_dir")?.to_string();

    let report_file = repo_root.path().join("parent.md");
    fs::write(
        &report_file,
        valid_child_report(
            "deadbeef",
            "sess0001",
            "refs/heads/main",
            SeverityCounts::zero(),
        ),
    )?;
    let stderr = run_cmd_failure(&[
        "reviewer",
        "complete-child",
        "--session-dir",
        &session_dir,
        "--reviewer-id",
        "deadbeef",
        "--session-id",
        "sess0001",
        "--verdict",
        "APPROVE",
        "--report-file",
        report_file.to_string_lossy().as_ref(),
    ])?;
    ensure!(stderr.contains("complete-child requires a child review entry with parent_id"));
    Ok(())
}

#[test]
fn reviewer_complete_child_fails_when_parent_missing() -> anyhow::Result<()> {
    let repo_root = tempfile::tempdir()?;
    let session_dir = repo_root.path().join("session");
    let session = SessionFile {
        schema_version: "1.2.0".to_string(),
        session_date: "2026-01-11".to_string(),
        repo_root: repo_root.path().to_string_lossy().to_string(),
        reviewers: vec!["cafebabe".to_string()],
        reviews: vec![ReviewEntry {
            reviewer_id: "cafebabe".to_string(),
            session_id: "sess0001".to_string(),
            target_ref: "refs/heads/main".to_string(),
            initiator_status: InitiatorStatus::Requesting,
            status: ReviewerStatus::Initializing,
            parent_id: Some("deadbeef".to_string()),
            started_at: "2026-01-11T00:00:00Z".to_string(),
            updated_at: "2026-01-11T00:00:00Z".to_string(),
            finished_at: None,
            current_phase: None,
            verdict: None,
            counts: SeverityCounts::zero(),
            report_file: None,
            notes: Vec::new(),
            child_reviews: Vec::new(),
            extra: serde_json::Map::default(),
        }],
        extra: serde_json::Map::new(),
    };
    write_session_file(&session_dir, &session)?;

    let report_file = repo_root.path().join("child.md");
    fs::write(
        &report_file,
        valid_child_report(
            "cafebabe",
            "sess0001",
            "refs/heads/main",
            SeverityCounts::zero(),
        ),
    )?;
    let session_dir_str = session_dir.to_string_lossy().to_string();
    let stderr = run_cmd_failure(&[
        "reviewer",
        "complete-child",
        "--session-dir",
        &session_dir_str,
        "--reviewer-id",
        "cafebabe",
        "--session-id",
        "sess0001",
        "--verdict",
        "APPROVE",
        "--report-file",
        report_file.to_string_lossy().as_ref(),
    ])?;
    ensure!(stderr.contains("complete-child parent review entry not found"));
    Ok(())
}

#[test]
fn reviewer_register_with_parent_id_ignores_env_reviewer_id() -> anyhow::Result<()> {
    // When --parent-id is set (child registration), MPCR_REVIEWER_ID from env
    // should be ignored to prevent accidentally reusing the parent's identity.
    let repo_root = tempfile::tempdir()?;
    let repo_root_str = repo_root.path().to_string_lossy().to_string();

    // First, register the parent
    let parent_out = run_cmd_json(&[
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
    let session_dir = json_str(&parent_out, "session_dir")?.to_string();

    // Now, register a child with --parent-id but MPCR_REVIEWER_ID set in env
    // (simulating inheriting parent env) with --use-env. The child should get
    // a NEW reviewer_id, not reuse "deadbeef" from env.
    let output = Command::new(env!("CARGO_BIN_EXE_mpcr"))
        .args([
            "--use-env",
            "--json",
            "reviewer",
            "register",
            "--target-ref",
            "refs/heads/main",
            "--session-dir",
            &session_dir,
            "--session-id",
            "sess0001",
            "--parent-id",
            "deadbeef",
        ])
        .env("MPCR_REVIEWER_ID", "deadbeef") // Parent's ID in env
        .output()?;

    if !output.status.success() {
        return Err(anyhow::anyhow!(
            "mpcr failed: {}",
            String::from_utf8_lossy(&output.stderr)
        ));
    }

    let result: Value = serde_json::from_slice(&output.stdout)?;
    let child_reviewer_id = json_str(&result, "reviewer_id")?;

    // Child should have a DIFFERENT reviewer_id than parent
    ensure!(
        child_reviewer_id != "deadbeef",
        "child reviewer_id should be distinct from parent when --parent-id is set"
    );

    // Verify parent_id is set correctly
    ensure!(json_str(&result, "parent_id")? == "deadbeef");

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
fn applicator_set_status_updates_grandchild_without_top_level_duplicates() -> anyhow::Result<()> {
    let repo_root = tempfile::tempdir()?;
    let repo_root_str = repo_root.path().to_string_lossy().to_string();

    let parent = run_cmd_json(&[
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
    let session_dir = json_str(&parent, "session_dir")?.to_string();

    let spawned_child = run_cmd_json(&[
        "reviewer",
        "spawn-children",
        "--target-ref",
        "refs/heads/main",
        "--session-dir",
        &session_dir,
        "--session-id",
        "sess0001",
        "--parent-id",
        "deadbeef",
        "--count",
        "1",
    ])?;
    let child = json_array(&spawned_child, "children")?
        .first()
        .ok_or_else(|| anyhow::anyhow!("child missing"))?;
    let child_id = json_str(child, "reviewer_id")?.to_string();

    let spawned_grandchild = run_cmd_json(&[
        "reviewer",
        "spawn-children",
        "--target-ref",
        "refs/heads/main",
        "--session-dir",
        &session_dir,
        "--session-id",
        "sess0001",
        "--parent-id",
        &child_id,
        "--count",
        "1",
    ])?;
    let grandchild = json_array(&spawned_grandchild, "children")?
        .first()
        .ok_or_else(|| anyhow::anyhow!("grandchild missing"))?;
    let grandchild_id = json_str(grandchild, "reviewer_id")?;

    run_cmd_json(&[
        "applicator",
        "set-status",
        "--session-dir",
        &session_dir,
        "--reviewer-id",
        grandchild_id,
        "--session-id",
        "sess0001",
        "--initiator-status",
        "RECEIVED",
    ])?;

    let raw_session = read_session_raw_json(Path::new(&session_dir))?;
    let top_reviews = json_array(&raw_session, "reviews")?;
    ensure!(top_reviews.len() == 1);
    ensure!(!top_reviews
        .iter()
        .any(|entry| json_str(entry, "reviewer_id").ok() == Some(child_id.as_str())));
    ensure!(!top_reviews
        .iter()
        .any(|entry| json_str(entry, "reviewer_id").ok() == Some(grandchild_id)));

    let session = read_session_json(Path::new(&session_dir))?;
    let grandchild_entry = find_review(&session, grandchild_id, "sess0001")?;
    ensure!(json_str(grandchild_entry, "initiator_status")? == "RECEIVED");
    let child_entry = find_review(&session, &child_id, "sess0001")?;
    let nested_grandchild = find_child_review(child_entry, grandchild_id, "sess0001")?;
    ensure!(json_str(nested_grandchild, "initiator_status")? == "RECEIVED");
    Ok(())
}

#[test]
fn applicator_note_updates_grandchild_without_top_level_duplicates() -> anyhow::Result<()> {
    let repo_root = tempfile::tempdir()?;
    let repo_root_str = repo_root.path().to_string_lossy().to_string();

    let parent = run_cmd_json(&[
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
    let session_dir = json_str(&parent, "session_dir")?.to_string();

    let spawned_child = run_cmd_json(&[
        "reviewer",
        "spawn-children",
        "--target-ref",
        "refs/heads/main",
        "--session-dir",
        &session_dir,
        "--session-id",
        "sess0001",
        "--parent-id",
        "deadbeef",
        "--count",
        "1",
    ])?;
    let child = json_array(&spawned_child, "children")?
        .first()
        .ok_or_else(|| anyhow::anyhow!("child missing"))?;
    let child_id = json_str(child, "reviewer_id")?.to_string();

    let spawned_grandchild = run_cmd_json(&[
        "reviewer",
        "spawn-children",
        "--target-ref",
        "refs/heads/main",
        "--session-dir",
        &session_dir,
        "--session-id",
        "sess0001",
        "--parent-id",
        &child_id,
        "--count",
        "1",
    ])?;
    let grandchild = json_array(&spawned_grandchild, "children")?
        .first()
        .ok_or_else(|| anyhow::anyhow!("grandchild missing"))?;
    let grandchild_id = json_str(grandchild, "reviewer_id")?;

    run_cmd_json(&[
        "applicator",
        "note",
        "--session-dir",
        &session_dir,
        "--reviewer-id",
        grandchild_id,
        "--session-id",
        "sess0001",
        "--note-type",
        "applied",
        "--content",
        "child fix applied",
    ])?;

    let raw_session = read_session_raw_json(Path::new(&session_dir))?;
    let top_reviews = json_array(&raw_session, "reviews")?;
    ensure!(top_reviews.len() == 1);
    ensure!(!top_reviews
        .iter()
        .any(|entry| json_str(entry, "reviewer_id").ok() == Some(child_id.as_str())));
    ensure!(!top_reviews
        .iter()
        .any(|entry| json_str(entry, "reviewer_id").ok() == Some(grandchild_id)));

    let session = read_session_json(Path::new(&session_dir))?;
    let grandchild_entry = find_review(&session, grandchild_id, "sess0001")?;
    let notes = json_array(grandchild_entry, "notes")?;
    ensure!(notes.len() == 1);
    let note = notes
        .first()
        .ok_or_else(|| anyhow::anyhow!("note missing"))?;
    ensure!(json_str(note, "role")? == "applicator");
    ensure!(json_str(note, "type")? == "applied");
    ensure!(json_str(note, "content")? == "child fix applied");

    let child_entry = find_review(&session, &child_id, "sess0001")?;
    let nested_grandchild = find_child_review(child_entry, grandchild_id, "sess0001")?;
    ensure!(json_u64(nested_grandchild, "notes_count")? == 1);
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
    let open = run_reports(&session_dir, &["session", "reports", "open"])?;
    ensure!(json_u64(&open, "matching_reviews")? == 0);
    Ok(())
}

#[test]
fn reports_invalid_json() -> anyhow::Result<()> {
    let dir = tempfile::tempdir()?;
    let session_dir = dir.path().join("session");
    fs::create_dir_all(&session_dir)?;
    fs::write(session_dir.join("_session.toml"), "schema_version = [")?;
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

// ── Protocol subcommand tests ────────────────────────────────────────────────

fn run_protocol(args: &[&str]) -> anyhow::Result<Value> {
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

fn run_protocol_text(args: &[&str]) -> anyhow::Result<String> {
    let output = Command::new(env!("CARGO_BIN_EXE_mpcr"))
        .args(args)
        .output()?;
    if !output.status.success() {
        return Err(anyhow::anyhow!(
            "mpcr failed: {}",
            String::from_utf8_lossy(&output.stderr)
        ));
    }
    Ok(String::from_utf8(output.stdout)?)
}

fn run_protocol_failure(args: &[&str]) -> anyhow::Result<String> {
    let output = Command::new(env!("CARGO_BIN_EXE_mpcr"))
        .args(args)
        .output()?;
    if output.status.success() {
        return Err(anyhow::anyhow!("mpcr unexpectedly succeeded"));
    }
    Ok(String::from_utf8_lossy(&output.stderr).to_string())
}

#[test]
fn protocol_reviewer_ingestion_json() -> anyhow::Result<()> {
    let out = run_protocol(&["protocol", "reviewer", "--phase", "INGESTION"])?;
    ensure!(json_str(&out, "title")? == "Ingestion");
    let content = json_str(&out, "content")?;
    ensure!(content.contains("change inventory"));
    ensure!(content.contains("mpcr reviewer update"));
    Ok(())
}

#[test]
fn protocol_json_flag_emits_compact_output() -> anyhow::Result<()> {
    let output = Command::new(env!("CARGO_BIN_EXE_mpcr"))
        .args(["protocol", "reviewer", "--phase", "INGESTION", "--json"])
        .output()?;
    ensure!(output.status.success());

    let stdout = String::from_utf8(output.stdout)?;
    ensure!(
        stdout.lines().count() == 1,
        "expected compact single-line JSON"
    );
    ensure!(stdout.starts_with("{\"title\":"));
    Ok(())
}

#[test]
fn protocol_json_pretty_flag_emits_multiline_output() -> anyhow::Result<()> {
    let output = Command::new(env!("CARGO_BIN_EXE_mpcr"))
        .args([
            "protocol",
            "reviewer",
            "--phase",
            "INGESTION",
            "--json-pretty",
        ])
        .output()?;
    ensure!(output.status.success());

    let stdout = String::from_utf8(output.stdout)?;
    ensure!(stdout.lines().count() > 1, "expected pretty multiline JSON");
    ensure!(stdout.contains("\n  \"title\":"));
    Ok(())
}

#[test]
fn protocol_reviewer_all_phases() -> anyhow::Result<()> {
    let phases = [
        "INGESTION",
        "DOMAIN_COVERAGE",
        "THEOREM_GENERATION",
        "ADVERSARIAL_PROOFS",
        "SYNTHESIS",
        "REPORT_WRITING",
        "OVERENGINEERING_GUARD",
        "COMPLEXITY_ANALYSIS",
        "SHIP_READINESS",
    ];
    for phase in phases {
        let out = run_protocol(&["protocol", "reviewer", "--phase", phase])?;
        let title = json_str(&out, "title")?;
        ensure!(!title.is_empty(), "empty title for {phase}");
        let content = json_str(&out, "content")?;
        ensure!(!content.is_empty(), "empty content for {phase}");
    }
    Ok(())
}

#[test]
fn protocol_reviewer_case_insensitive() -> anyhow::Result<()> {
    let out = run_protocol(&["protocol", "reviewer", "--phase", "ingestion"])?;
    ensure!(json_str(&out, "title")? == "Ingestion");
    Ok(())
}

#[test]
fn protocol_reviewer_unknown_phase_fails() -> anyhow::Result<()> {
    let stderr = run_protocol_failure(&["protocol", "reviewer", "--phase", "NONEXISTENT"])?;
    ensure!(stderr.contains("unknown reviewer phase"));
    Ok(())
}

#[test]
fn protocol_applicator_all_phases() -> anyhow::Result<()> {
    let phases = ["INGESTION", "DISPOSITION", "APPLICATION", "FINALIZATION"];
    for phase in phases {
        let out = run_protocol(&["protocol", "applicator", "--phase", phase])?;
        let title = json_str(&out, "title")?;
        ensure!(!title.is_empty(), "empty title for {phase}");
    }
    Ok(())
}

#[test]
fn protocol_orchestrator_json() -> anyhow::Result<()> {
    let out = run_protocol(&["protocol", "orchestrator"])?;
    let content = json_str(&out, "content")?;
    ensure!(content.contains("Decomposition"));
    ensure!(content.contains("Dispatch"));
    ensure!(content.contains("Synthesis"));
    ensure!(content.contains("You SHALL NOT emit direct file:line findings yourself."));
    ensure!(content.contains("Single-agent mode still requires a dispatched worker"));
    Ok(())
}

#[test]
fn protocol_orchestrator_output_fits_context_budget() -> anyhow::Result<()> {
    let output = Command::new(env!("CARGO_BIN_EXE_mpcr"))
        .args(["protocol", "orchestrator"])
        .output()?;
    ensure!(
        output.status.success(),
        "protocol orchestrator failed: {}",
        String::from_utf8_lossy(&output.stderr)
    );
    let stdout = String::from_utf8(output.stdout)?;
    ensure!(
        stdout.len() <= 5000,
        "protocol orchestrator output exceeded 5000-byte budget: {}",
        stdout.len()
    );
    Ok(())
}

#[test]
fn protocol_domains_json() -> anyhow::Result<()> {
    let out = run_protocol(&["protocol", "domains"])?;
    let content = json_str(&out, "content")?;
    ensure!(content.contains("Architecture"));
    ensure!(content.contains("Security"));
    ensure!(content.contains("Concurrency"));
    ensure!(content.contains("Performance"));
    Ok(())
}

#[test]
fn protocol_report_template_all_scales() -> anyhow::Result<()> {
    for scale in ["compact", "standard", "full"] {
        let out = run_protocol(&["protocol", "report-template", "--scale", scale])?;
        let content = json_str(&out, "content")?;
        ensure!(content.contains("Verdict"), "missing Verdict for {scale}");
        ensure!(content.contains("Findings"), "missing Findings for {scale}");
        ensure!(
            content.contains("Defended"),
            "missing defended proofs section for {scale}"
        );
        ensure!(
            content.contains("Residual Risk") || content.contains("Risk"),
            "missing residual risk section for {scale}"
        );
    }

    for scale in ["standard", "full"] {
        let out = run_protocol(&["protocol", "report-template", "--scale", scale])?;
        let content = json_str(&out, "content")?;
        ensure!(
            content.contains("| Domain"),
            "missing domain ledger table for {scale}"
        );
    }
    Ok(())
}

#[test]
fn protocol_report_template_unknown_scale_fails() -> anyhow::Result<()> {
    let stderr = run_protocol_failure(&["protocol", "report-template", "--scale", "NONEXISTENT"])?;
    ensure!(stderr.contains("unknown template scale"));
    Ok(())
}

#[test]
fn protocol_dispatch_all_roles() -> anyhow::Result<()> {
    let worker_roles = [
        "architecture-critic",
        "contract-guardian",
        "data-integrity-prover",
        "error-path-tracer",
        "security-adversary",
        "concurrency-prover",
        "performance-profiler",
        "observability-oncall",
        "test-strategist",
        "docs-consumer",
        "dependency-auditor",
        "supply-chain-auditor",
        "auth-access-prover",
        "crypto-secrets-auditor",
        "injection-hunter",
        "infra-runtime-auditor",
        "data-privacy-guardian",
        "domain-specialist",
        "fresh-eyes",
        "holistic-integrator",
        "applicator-worker",
        "applicator-verifier",
        "complexity-analyst",
        "overengineering-guard",
        "ship-readiness-assessor",
        "scope-creep-reviewer",
        "scope-mapper-reviewer",
        "scope-mapper-applicator",
        "convergence-planner",
        "staleness-auditor",
    ];
    for role in worker_roles {
        let out = run_protocol(&["protocol", "dispatch", "--role", role])?;
        let content = json_str(&out, "content")?;
        ensure!(!content.is_empty(), "empty dispatch content for {role}");
        ensure!(
            content.contains("MPCR_DISPATCH_ROLE=") || content.contains("MPCR_APPLICATOR_ROLE="),
            "dispatch content for {role} missing role identity env var"
        );
        ensure!(
            content.contains("## Proof Packet") || content.contains("## Output"),
            "dispatch content for {role} missing output format section"
        );
        ensure!(
            content.contains("MPCR_REVIEWER_ID="),
            "dispatch content for {role} missing MPCR_REVIEWER_ID binding"
        );
        ensure!(
            content.contains("MPCR_SESSION_ID="),
            "dispatch content for {role} missing MPCR_SESSION_ID binding"
        );
        ensure!(
            content.contains("MPCR_SESSION_DIR="),
            "dispatch content for {role} missing MPCR_SESSION_DIR binding"
        );
    }
    // Explorer is a context-only role — no identity bindings or Proof Packet required.
    let explorer_out = run_protocol(&["protocol", "dispatch", "--role", "explorer"])?;
    let explorer_content = json_str(&explorer_out, "content")?;
    ensure!(!explorer_content.is_empty(), "empty dispatch for explorer");
    Ok(())
}

#[test]
fn protocol_dispatch_unknown_role_fails() -> anyhow::Result<()> {
    let stderr = run_protocol_failure(&["protocol", "dispatch", "--role", "NONEXISTENT"])?;
    ensure!(stderr.contains("error: unknown dispatch role"));
    ensure!(stderr.contains("hint: valid roles:"));
    ensure!(stderr.contains("hint: run `mpcr protocol dispatch-list`"));
    Ok(())
}

#[test]
fn protocol_dispatch_removed_stale_roles_fail() -> anyhow::Result<()> {
    for role in [
        "stale-docs-auditor",
        "stale-examples-auditor",
        "stale-references-auditor",
    ] {
        let stderr = run_protocol_failure(&["protocol", "dispatch", "--role", role])?;
        ensure!(stderr.contains("error: unknown dispatch role"));
        ensure!(stderr.contains("hint: run `mpcr protocol dispatch-list`"));
    }
    Ok(())
}

#[test]
fn protocol_list_json() -> anyhow::Result<()> {
    let out = run_protocol(&["protocol", "list"])?;
    let entries = out
        .as_array()
        .ok_or_else(|| anyhow::anyhow!("list output was not an array"))?;
    // Includes reviewer/applicator/session phases plus orchestrator, fullcycle, domains, templates, and dispatch roles.
    ensure!(entries.len() >= 40, "expected >= 40, got {}", entries.len());
    let dispatch_entry = entries
        .iter()
        .find(|e| e.get("category") == Some(&Value::String("dispatch".to_string())))
        .ok_or_else(|| anyhow::anyhow!("missing dispatch entry in protocol list"))?;
    let key = dispatch_entry
        .get("key")
        .and_then(Value::as_str)
        .ok_or_else(|| anyhow::anyhow!("dispatch entry key missing"))?;
    ensure!(
        !key.contains('_'),
        "dispatch discovery key must use canonical hyphenated slug, got {key}"
    );
    Ok(())
}

#[test]
fn protocol_list_text_output() -> anyhow::Result<()> {
    let out = run_protocol_text(&["protocol", "list"])?;
    ensure!(out.contains("reviewer"));
    ensure!(out.contains("applicator"));
    ensure!(out.contains("orchestrator"));
    ensure!(out.contains("fullcycle"));
    ensure!(out.contains("report-template"));
    ensure!(out.contains("dispatch"));
    ensure!(out.contains("session"));
    Ok(())
}

#[test]
fn protocol_reviewer_text_output() -> anyhow::Result<()> {
    let out = run_protocol_text(&["protocol", "reviewer", "--phase", "INGESTION"])?;
    // Text mode should output content directly (no JSON envelope)
    ensure!(out.contains("change inventory"));
    ensure!(!out.contains("\"title\""));
    Ok(())
}

#[test]
fn protocol_capabilities_json() -> anyhow::Result<()> {
    let out = run_protocol(&["protocol", "capabilities"])?;
    ensure!(json_str(&out, "schema_version")? == "protocol_capabilities.v1");
    let commands = out
        .get("protocol_commands")
        .and_then(Value::as_array)
        .ok_or_else(|| anyhow::anyhow!("protocol_commands missing"))?;
    let as_strs = commands
        .iter()
        .filter_map(Value::as_str)
        .collect::<Vec<_>>();
    ensure!(as_strs.contains(&"mpcr protocol orchestrator"));
    ensure!(as_strs.contains(&"mpcr protocol capabilities"));
    ensure!(json_u64(&out, "protocol_entry_count")? >= 40);
    Ok(())
}

#[test]
fn protocol_fullcycle_text_includes_execution_bridge() -> anyhow::Result<()> {
    let out = run_protocol_text(&["protocol", "fullcycle"])?;
    ensure!(out.contains("mpcr fullcycle plan"));
    ensure!(out.contains("mpcr fullcycle loop-plan"));
    ensure!(out.contains("mpcr fullcycle checkpoint"));
    ensure!(out.contains("mpcr fullcycle state"));
    Ok(())
}

#[test]
fn quoted_single_token_protocol_is_compat_split() -> anyhow::Result<()> {
    let cases: Vec<Vec<&str>> = vec![
        vec!["protocol orchestrator"],
        vec!["protocol capabilities"],
        vec!["--json", "protocol capabilities"],
        vec!["--json-pretty", "protocol orchestrator"],
        vec!["--use-env", "protocol capabilities"],
    ];
    for argv in cases {
        let output = Command::new(env!("CARGO_BIN_EXE_mpcr"))
            .args(&argv)
            .output()?;
        let shown = argv.join(" ");
        ensure!(
            output.status.success(),
            "expected compat split to succeed for `{shown}`: {}",
            String::from_utf8_lossy(&output.stderr)
        );
        let stderr = String::from_utf8(output.stderr)?;
        ensure!(
            stderr.contains("compat: interpreted single-token subcommand"),
            "compat hint missing for `{shown}`"
        );
    }
    Ok(())
}

#[test]
fn quoted_single_token_protocol_dispatch_is_split_then_validated() -> anyhow::Result<()> {
    let output = Command::new(env!("CARGO_BIN_EXE_mpcr"))
        .arg("protocol dispatch")
        .output()?;
    ensure!(
        !output.status.success(),
        "expected command to fail without --role"
    );
    let stderr = String::from_utf8(output.stderr)?;
    ensure!(
        stderr.contains("compat: interpreted single-token subcommand"),
        "compat hint missing for `protocol dispatch`"
    );
    ensure!(
        !stderr.contains("unrecognized subcommand 'protocol dispatch'"),
        "command should be compat split before clap validation"
    );
    ensure!(
        stderr.contains("--role"),
        "expected clap missing-argument guidance, got: {stderr}"
    );
    Ok(())
}

#[test]
fn fullcycle_plan_loop_state_checkpoint_flow() -> anyhow::Result<()> {
    let tmp = tempfile::tempdir()?;
    let session_dir = tmp.path().join("session");
    let session = sample_session(&session_dir);
    write_session_file(&session_dir, &session)?;
    let session_dir_str = session_dir
        .to_str()
        .ok_or_else(|| anyhow::anyhow!("non-UTF-8 path"))?;

    let plan = run_cmd_json(&[
        "fullcycle",
        "plan",
        "--session-dir",
        session_dir_str,
        "--target-ref",
        "refs/heads/main",
        "--session-id",
        "sess0003",
        "--detail",
        "compact",
    ])?;
    ensure!(json_str(&plan, "mode")? == "read_only_planner");
    ensure!(json_u64(&plan, "baseline_workers")? == 4);

    let loop_plan = run_cmd_json(&[
        "fullcycle",
        "loop-plan",
        "--session-dir",
        session_dir_str,
        "--target-ref",
        "refs/heads/main",
        "--session-id",
        "sess0003",
    ])?;
    ensure!(json_str(&loop_plan, "mode")? == "read_only_loop_planner");

    let checkpoint = run_cmd_json(&[
        "fullcycle",
        "checkpoint",
        "--session-dir",
        session_dir_str,
        "--target-ref",
        "refs/heads/main",
        "--session-id",
        "sess0003",
        "--detail",
        "auto",
    ])?;
    ensure!(checkpoint.get("schema_version").and_then(Value::as_str) == Some("fullcycle_state.v1"));

    let state = run_cmd_json(&["fullcycle", "state", "--session-dir", session_dir_str])?;
    ensure!(state.get("schema_version").and_then(Value::as_str) == Some("fullcycle_state.v1"));
    Ok(())
}

#[test]
fn fullcycle_plan_bootstrap_preserves_requested_session_scope() -> anyhow::Result<()> {
    let tmp = tempfile::tempdir()?;
    let session_dir = tmp.path().join("session");
    let session = empty_session(&session_dir);
    write_session_file(&session_dir, &session)?;
    let session_dir_str = session_dir
        .to_str()
        .ok_or_else(|| anyhow::anyhow!("non-UTF-8 path"))?;
    let plan = run_cmd_json(&[
        "fullcycle",
        "plan",
        "--session-dir",
        session_dir_str,
        "--target-ref",
        "refs/heads/main",
        "--session-id",
        "sess0007",
        "--detail",
        "compact",
    ])?;

    ensure!(json_str(&plan, "session_id")? == "sess0007");
    ensure!(json_str(&plan, "state")? == "bootstrap_review");
    ensure!(json_bool(&plan, "continue_required")?);
    let next = json_array(&plan, "next_commands")?;
    let register_cmd = next
        .first()
        .and_then(Value::as_str)
        .ok_or_else(|| anyhow::anyhow!("missing bootstrap reviewer register command"))?;
    ensure!(register_cmd.contains("--session-id sess0007"));
    Ok(())
}

#[test]
fn fullcycle_plan_net_new_actionable_ignores_minor_nit_churn() -> anyhow::Result<()> {
    let tmp = tempfile::tempdir()?;
    let session_dir = tmp.path().join("session");
    fs::create_dir_all(&session_dir)?;
    let mut session = sample_session(&session_dir);

    let previous_report_path = session_dir.join("11-00-00-000_refs_heads_main_cafed00d.md");
    fs::write(
        &previous_report_path,
        valid_parent_report(
            "cafed00d",
            "sess0003",
            "refs/heads/main",
            SeverityCounts {
                blocker: 0,
                major: 1,
                minor: 0,
                nit: 0,
            },
        ),
    )?;
    let latest_report_path = session_dir.join("12-00-00-000_refs_heads_main_feedface.md");
    fs::write(
        &latest_report_path,
        valid_parent_report(
            "feedface",
            "sess0003",
            "refs/heads/main",
            SeverityCounts {
                blocker: 0,
                major: 1,
                minor: 0,
                nit: 1,
            },
        ),
    )?;

    let previous_parent = ReviewEntry {
        reviewer_id: "cafed00d".to_string(),
        session_id: "sess0003".to_string(),
        target_ref: "refs/heads/main".to_string(),
        initiator_status: InitiatorStatus::Applied,
        status: ReviewerStatus::Finished,
        parent_id: None,
        started_at: "2026-01-11T00:30:00Z".to_string(),
        updated_at: "2026-01-11T00:45:00Z".to_string(),
        finished_at: Some("2026-01-11T00:45:00Z".to_string()),
        current_phase: Some(ReviewPhase::ReportWriting),
        verdict: Some(ReviewVerdict::RequestChanges),
        counts: SeverityCounts {
            blocker: 0,
            major: 1,
            minor: 0,
            nit: 0,
        },
        report_file: Some("11-00-00-000_refs_heads_main_cafed00d.md".to_string()),
        notes: Vec::new(),
        child_reviews: Vec::new(),
        extra: serde_json::Map::default(),
    };
    session.reviewers.push("cafed00d".to_string());
    session.reviews.push(previous_parent);

    if let Some(latest_parent) = session
        .reviews
        .iter_mut()
        .find(|entry| entry.reviewer_id == "feedface" && entry.session_id == "sess0003")
    {
        latest_parent.initiator_status = InitiatorStatus::Applied;
        latest_parent.started_at = "2026-01-11T01:00:00Z".to_string();
        latest_parent.updated_at = "2026-01-11T01:30:00Z".to_string();
        latest_parent.finished_at = Some("2026-01-11T01:30:00Z".to_string());
        latest_parent.verdict = Some(ReviewVerdict::RequestChanges);
        latest_parent.counts = SeverityCounts {
            blocker: 0,
            major: 1,
            minor: 0,
            nit: 1,
        };
        latest_parent.report_file = Some("12-00-00-000_refs_heads_main_feedface.md".to_string());
    }

    write_session_file(&session_dir, &session)?;
    let session_dir_str = session_dir
        .to_str()
        .ok_or_else(|| anyhow::anyhow!("non-UTF-8 path"))?;
    let plan = run_cmd_json(&[
        "fullcycle",
        "plan",
        "--session-dir",
        session_dir_str,
        "--target-ref",
        "refs/heads/main",
        "--session-id",
        "sess0003",
        "--detail",
        "compact",
    ])?;

    ensure!(json_u64(&plan, "net_new_actionable")? == 0);
    ensure!(json_u64(&plan, "dedup_fingerprint_count")? == 2);
    Ok(())
}

#[test]
fn fullcycle_plan_ignores_mismatched_previous_state_scope() -> anyhow::Result<()> {
    let tmp = tempfile::tempdir()?;
    let session_dir = tmp.path().join("session");
    fs::create_dir_all(&session_dir)?;
    let mut session = sample_session(&session_dir);

    let previous_report_path = session_dir.join("11-00-00-000_refs_heads_main_cafed00d.md");
    fs::write(
        &previous_report_path,
        valid_parent_report(
            "cafed00d",
            "sess0003",
            "refs/heads/main",
            SeverityCounts {
                blocker: 0,
                major: 1,
                minor: 0,
                nit: 0,
            },
        ),
    )?;
    let latest_report_path = session_dir.join("12-00-00-000_refs_heads_main_feedface.md");
    fs::write(
        &latest_report_path,
        valid_parent_report(
            "feedface",
            "sess0003",
            "refs/heads/main",
            SeverityCounts {
                blocker: 0,
                major: 1,
                minor: 0,
                nit: 0,
            },
        ),
    )?;

    let previous_parent = ReviewEntry {
        reviewer_id: "cafed00d".to_string(),
        session_id: "sess0003".to_string(),
        target_ref: "refs/heads/main".to_string(),
        initiator_status: InitiatorStatus::Applied,
        status: ReviewerStatus::Finished,
        parent_id: None,
        started_at: "2026-01-11T00:30:00Z".to_string(),
        updated_at: "2026-01-11T00:45:00Z".to_string(),
        finished_at: Some("2026-01-11T00:45:00Z".to_string()),
        current_phase: Some(ReviewPhase::ReportWriting),
        verdict: Some(ReviewVerdict::RequestChanges),
        counts: SeverityCounts {
            blocker: 0,
            major: 1,
            minor: 0,
            nit: 0,
        },
        report_file: Some("11-00-00-000_refs_heads_main_cafed00d.md".to_string()),
        notes: Vec::new(),
        child_reviews: Vec::new(),
        extra: serde_json::Map::default(),
    };
    session.reviewers.push("cafed00d".to_string());
    session.reviews.push(previous_parent);

    if let Some(latest_parent) = session
        .reviews
        .iter_mut()
        .find(|entry| entry.reviewer_id == "feedface" && entry.session_id == "sess0003")
    {
        latest_parent.initiator_status = InitiatorStatus::Applied;
        latest_parent.started_at = "2026-01-11T01:00:00Z".to_string();
        latest_parent.updated_at = "2026-01-11T01:30:00Z".to_string();
        latest_parent.finished_at = Some("2026-01-11T01:30:00Z".to_string());
        latest_parent.verdict = Some(ReviewVerdict::RequestChanges);
        latest_parent.counts = SeverityCounts {
            blocker: 0,
            major: 1,
            minor: 0,
            nit: 0,
        };
        latest_parent.report_file = Some("12-00-00-000_refs_heads_main_feedface.md".to_string());
    }

    session.extra.insert(
        "fullcycle_state".to_string(),
        serde_json::json!({
            "schema_version": "fullcycle_state.v1",
            "target_ref": "refs/heads/other",
            "session_id": "sess9999",
            "cycle_index": 9,
            "cycle_phase": "scoped_rereview",
            "continue_required": true,
            "stop_reason": Value::Null,
            "no_progress_streak": 9,
            "baseline_workers": 4,
            "worker_ceiling": 8,
            "recommended_workers": 8,
            "probe_stage": "probe_8",
            "net_new_actionable": 0,
            "net_new_staleness_actionable": 0,
            "dedup_fingerprint_count": 1,
            "malformed_packets": 0,
            "retry_count": 0,
            "child_error_count": 0,
            "artifact_format_policy": "proof_toml_first_cli_json_ok",
            "updated_at": "2026-01-11T09:00:00Z"
        }),
    );

    write_session_file(&session_dir, &session)?;
    let session_dir_str = session_dir
        .to_str()
        .ok_or_else(|| anyhow::anyhow!("non-UTF-8 path"))?;
    let plan = run_cmd_json(&[
        "fullcycle",
        "plan",
        "--session-dir",
        session_dir_str,
        "--target-ref",
        "refs/heads/main",
        "--session-id",
        "sess0003",
        "--detail",
        "compact",
    ])?;

    ensure!(json_u64(&plan, "net_new_actionable")? == 0);
    ensure!(
        json_u64(&plan, "no_progress_streak")? == 1,
        "no_progress_streak should not inherit mismatched target/session state"
    );
    Ok(())
}

#[test]
fn fullcycle_plan_respects_mpcr_max_workers_upper_bound() -> anyhow::Result<()> {
    let tmp = tempfile::tempdir()?;
    let session_dir = tmp.path().join("session");
    let session = sample_session(&session_dir);
    write_session_file(&session_dir, &session)?;
    let session_dir_str = session_dir
        .to_str()
        .ok_or_else(|| anyhow::anyhow!("non-UTF-8 path"))?;

    let run_with_cap = |cap: &str| -> anyhow::Result<Value> {
        let output = Command::new(env!("CARGO_BIN_EXE_mpcr"))
            .env("MPCR_MAX_WORKERS", cap)
            .args([
                "fullcycle",
                "plan",
                "--session-dir",
                session_dir_str,
                "--target-ref",
                "refs/heads/main",
                "--session-id",
                "sess0003",
                "--detail",
                "compact",
            ])
            .output()?;
        ensure!(
            output.status.success(),
            "fullcycle plan failed for cap `{cap}`: {}",
            String::from_utf8_lossy(&output.stderr)
        );
        Ok(serde_json::from_slice(&output.stdout)?)
    };

    let cap5 = run_with_cap("5")?;
    ensure!(json_u64(&cap5, "worker_ceiling")? == 4);
    ensure!(json_u64(&cap5, "recommended_workers")? == 4);

    let cap7 = run_with_cap("7")?;
    ensure!(json_u64(&cap7, "worker_ceiling")? == 6);
    ensure!(json_u64(&cap7, "recommended_workers")? <= 6);
    Ok(())
}

// ── Session cleanup tests ────────────────────────────────────────────────────

#[test]
fn cleanup_dry_run_does_not_modify_session() -> anyhow::Result<()> {
    let tmp = tempfile::tempdir()?;
    let session_dir = tmp.path();
    let session = sample_session(session_dir);
    write_session_file(session_dir, &session)?;

    let result = run_cmd_json(&[
        "session",
        "cleanup",
        "--session-dir",
        session_dir
            .to_str()
            .ok_or_else(|| anyhow::anyhow!("non-UTF-8 path"))?,
        "--reviewer-id",
        "feedface",
        "--dry-run",
    ])?;

    ensure!(json_bool(&result, "dry_run")?, "expected dry_run=true");
    ensure!(
        json_u64(&result, "matched")? > 0,
        "expected at least one match"
    );
    ensure!(json_u64(&result, "purged")? == 0, "expected purged=0");

    let after = read_session_json(session_dir)?;
    let reviews = json_array(&after, "reviews")?;
    ensure!(reviews.len() == 3, "session should be unmodified");
    Ok(())
}

#[test]
fn cleanup_purges_by_reviewer_id() -> anyhow::Result<()> {
    let tmp = tempfile::tempdir()?;
    let session_dir = tmp.path();
    let session = sample_session(session_dir);
    write_session_file(session_dir, &session)?;

    let result = run_cmd_json(&[
        "session",
        "cleanup",
        "--session-dir",
        session_dir
            .to_str()
            .ok_or_else(|| anyhow::anyhow!("non-UTF-8 path"))?,
        "--reviewer-id",
        "feedface",
    ])?;

    ensure!(!json_bool(&result, "dry_run")?, "expected dry_run=false");
    ensure!(json_u64(&result, "purged")? == 1, "expected purged=1");

    let after = read_session_json(session_dir)?;
    let reviews = json_array(&after, "reviews")?;
    ensure!(reviews.len() == 2, "one entry should be removed");
    ensure!(
        !reviews
            .iter()
            .filter_map(|r| r.get("reviewer_id").and_then(Value::as_str))
            .any(|id| id == "feedface"),
        "feedface should be purged"
    );
    Ok(())
}

#[test]
fn cleanup_purges_children_with_include_children() -> anyhow::Result<()> {
    let tmp = tempfile::tempdir()?;
    let session_dir = tmp.path();
    let mut session = sample_session(session_dir);

    let child = ReviewEntry {
        reviewer_id: "ch1ld001".to_string(),
        session_id: "sess0001".to_string(),
        target_ref: "refs/heads/main".to_string(),
        initiator_status: InitiatorStatus::Requesting,
        status: ReviewerStatus::Finished,
        parent_id: Some("deadbeef".to_string()),
        started_at: "2026-01-11T00:30:00Z".to_string(),
        updated_at: "2026-01-11T01:00:00Z".to_string(),
        finished_at: Some("2026-01-11T01:30:00Z".to_string()),
        current_phase: Some(ReviewPhase::ReportWriting),
        verdict: Some(ReviewVerdict::Approve),
        counts: SeverityCounts::zero(),
        report_file: None,
        notes: Vec::new(),
        child_reviews: Vec::new(),
        extra: serde_json::Map::default(),
    };
    session.reviewers.push("ch1ld001".to_string());
    session.reviews.push(child);
    write_session_file(session_dir, &session)?;

    let result = run_cmd_json(&[
        "session",
        "cleanup",
        "--session-dir",
        session_dir
            .to_str()
            .ok_or_else(|| anyhow::anyhow!("non-UTF-8 path"))?,
        "--reviewer-id",
        "deadbeef",
        "--include-children",
    ])?;

    ensure!(
        json_u64(&result, "purged")? == 2,
        "expected parent + child purged"
    );

    let after = read_session_json(session_dir)?;
    let reviews = json_array(&after, "reviews")?;
    ensure!(reviews.len() == 2, "parent and child should be removed");
    Ok(())
}

#[test]
fn cleanup_deletes_report_files() -> anyhow::Result<()> {
    let tmp = tempfile::tempdir()?;
    let session_dir = tmp.path();
    let session = sample_session(session_dir);
    write_session_file(session_dir, &session)?;

    let report_path = session_dir.join("12-00-00-000_refs_heads_main_feedface.md");
    fs::write(&report_path, "# Test report")?;
    ensure!(report_path.exists(), "report file should exist");

    let result = run_cmd_json(&[
        "session",
        "cleanup",
        "--session-dir",
        session_dir
            .to_str()
            .ok_or_else(|| anyhow::anyhow!("non-UTF-8 path"))?,
        "--reviewer-id",
        "feedface",
        "--delete-report-files",
    ])?;

    ensure!(
        json_u64(&result, "files_deleted")? == 1,
        "expected 1 file deleted"
    );
    ensure!(!report_path.exists(), "report file should be deleted");
    Ok(())
}

#[test]
fn cleanup_does_not_trust_persisted_repo_root_for_absolute_report_paths() -> anyhow::Result<()> {
    let tmp = tempfile::tempdir()?;
    let session_dir = tmp.path().join("session");
    fs::create_dir_all(&session_dir)?;

    let outside_report = tmp.path().join("outside-report.md");
    fs::write(&outside_report, "# outside report")?;
    ensure!(
        outside_report.exists(),
        "outside report should exist before cleanup"
    );

    let mut session = sample_session(&session_dir);
    session.repo_root = tmp.path().to_string_lossy().to_string();
    if let Some(review) = session
        .reviews
        .iter_mut()
        .find(|review| review.reviewer_id == "feedface")
    {
        review.report_file = Some(outside_report.to_string_lossy().to_string());
    }
    write_session_file(&session_dir, &session)?;

    let result = run_cmd_json(&[
        "session",
        "cleanup",
        "--session-dir",
        session_dir
            .to_str()
            .ok_or_else(|| anyhow::anyhow!("non-UTF-8 path"))?,
        "--reviewer-id",
        "feedface",
        "--delete-report-files",
    ])?;

    ensure!(
        json_u64(&result, "files_deleted")? == 0,
        "cleanup should not delete files outside trusted runtime repo root"
    );
    ensure!(
        outside_report.exists(),
        "outside report should not be deleted based on persisted repo_root"
    );
    Ok(())
}

#[test]
fn cleanup_deletes_repo_relative_report_with_explicit_session_dir() -> anyhow::Result<()> {
    let tmp = tempfile::tempdir()?;
    let foreign_repo_root = tmp.path().join("foreign-repo");
    let session_dir = foreign_repo_root
        .join(".local")
        .join("reports")
        .join("code_reviews")
        .join("2026-01-11");
    fs::create_dir_all(&session_dir)?;

    let mut session = sample_session(&session_dir);
    let report_rel = ".local/reports/code_reviews/2026-01-11/foreign-report.md";
    if let Some(review) = session
        .reviews
        .iter_mut()
        .find(|review| review.reviewer_id == "feedface")
    {
        review.report_file = Some(report_rel.to_string());
    }
    write_session_file(&session_dir, &session)?;

    let report_path = foreign_repo_root.join(report_rel);
    if let Some(parent) = report_path.parent() {
        fs::create_dir_all(parent)?;
    }
    fs::write(&report_path, "# foreign report")?;
    ensure!(
        report_path.exists(),
        "foreign report should exist before cleanup"
    );

    let result = run_cmd_json(&[
        "session",
        "cleanup",
        "--session-dir",
        session_dir
            .to_str()
            .ok_or_else(|| anyhow::anyhow!("non-UTF-8 path"))?,
        "--reviewer-id",
        "feedface",
        "--delete-report-files",
    ])?;

    ensure!(
        json_u64(&result, "files_deleted")? == 1,
        "cleanup should delete the report under the session-dir repo root"
    );
    ensure!(
        !report_path.exists(),
        "report should be deleted when session-dir points at another repo"
    );
    Ok(())
}

#[test]
fn cleanup_filters_by_before_timestamp() -> anyhow::Result<()> {
    let tmp = tempfile::tempdir()?;
    let session_dir = tmp.path();
    let mut session = sample_session(session_dir);

    session
        .reviews
        .get_mut(0)
        .ok_or_else(|| anyhow::anyhow!("missing review 0"))?
        .started_at = "2026-01-10T00:00:00Z".to_string();
    session
        .reviews
        .get_mut(1)
        .ok_or_else(|| anyhow::anyhow!("missing review 1"))?
        .started_at = "2026-01-12T00:00:00Z".to_string();
    session
        .reviews
        .get_mut(2)
        .ok_or_else(|| anyhow::anyhow!("missing review 2"))?
        .started_at = "2026-01-14T00:00:00Z".to_string();
    write_session_file(session_dir, &session)?;

    let result = run_cmd_json(&[
        "session",
        "cleanup",
        "--session-dir",
        session_dir
            .to_str()
            .ok_or_else(|| anyhow::anyhow!("non-UTF-8 path"))?,
        "--before",
        "2026-01-11T00:00:00Z",
    ])?;

    ensure!(json_u64(&result, "purged")? == 1, "expected 1 purged");

    let after = read_session_json(session_dir)?;
    let reviews = json_array(&after, "reviews")?;
    ensure!(reviews.len() == 2, "one entry should be removed");
    Ok(())
}

#[test]
fn cleanup_filters_by_reviewer_status() -> anyhow::Result<()> {
    let tmp = tempfile::tempdir()?;
    let session_dir = tmp.path();
    let session = sample_session(session_dir);
    write_session_file(session_dir, &session)?;

    let result = run_cmd_json(&[
        "session",
        "cleanup",
        "--session-dir",
        session_dir
            .to_str()
            .ok_or_else(|| anyhow::anyhow!("non-UTF-8 path"))?,
        "--reviewer-status",
        "BLOCKED",
    ])?;

    ensure!(json_u64(&result, "purged")? == 1, "expected 1 purged");

    let after = read_session_json(session_dir)?;
    let reviews = json_array(&after, "reviews")?;
    ensure!(reviews.len() == 2, "blocked entry should be removed");
    ensure!(
        !reviews
            .iter()
            .filter_map(|r| r.get("reviewer_id").and_then(Value::as_str))
            .any(|id| id == "cafebabe"),
        "cafebabe should be purged"
    );
    Ok(())
}

#[test]
fn cleanup_no_filters_purges_all() -> anyhow::Result<()> {
    let tmp = tempfile::tempdir()?;
    let session_dir = tmp.path();
    let session = sample_session(session_dir);
    write_session_file(session_dir, &session)?;

    let result = run_cmd_json(&[
        "session",
        "cleanup",
        "--session-dir",
        session_dir
            .to_str()
            .ok_or_else(|| anyhow::anyhow!("non-UTF-8 path"))?,
    ])?;

    ensure!(json_u64(&result, "purged")? == 3, "expected all 3 purged");

    let after = read_session_json(session_dir)?;
    let reviews = json_array(&after, "reviews")?;
    ensure!(reviews.is_empty(), "all entries should be removed");
    let reviewers = json_array(&after, "reviewers")?;
    ensure!(reviewers.is_empty(), "reviewers list should be empty");
    Ok(())
}

#[test]
fn protocol_session_cleanup_phase() -> anyhow::Result<()> {
    let result = run_cmd_json(&["protocol", "session", "--phase", "CLEANUP"])?;
    let content = json_str(&result, "content")?;
    ensure!(
        content.contains("mpcr session cleanup"),
        "cleanup guidance should mention the command"
    );
    ensure!(
        content.contains("--dry-run"),
        "cleanup guidance should mention dry-run"
    );
    Ok(())
}

// ── Worker boundary negative tests ──────────────────────────────────────────

#[test]
fn worker_dispatch_role_rejects_missing_reviewer_id() -> anyhow::Result<()> {
    let output = Command::new(env!("CARGO_BIN_EXE_mpcr"))
        .args([
            "reviewer",
            "update",
            "--session-dir",
            "/tmp",
            "--reviewer-id",
            "deadbeef",
            "--session-id",
            "sess0001",
            "--status",
            "IN_PROGRESS",
        ])
        .env("MPCR_DISPATCH_ROLE", "security-adversary")
        .env("MPCR_SESSION_ID", "sess0001")
        .output()?;
    ensure!(
        !output.status.success(),
        "should fail without MPCR_REVIEWER_ID"
    );
    let stderr = String::from_utf8_lossy(&output.stderr);
    ensure!(
        stderr.contains("MPCR_REVIEWER_ID"),
        "error should mention MPCR_REVIEWER_ID"
    );
    Ok(())
}

#[test]
fn worker_dispatch_role_rejects_missing_session_id() -> anyhow::Result<()> {
    let output = Command::new(env!("CARGO_BIN_EXE_mpcr"))
        .args([
            "reviewer",
            "update",
            "--session-dir",
            "/tmp",
            "--reviewer-id",
            "deadbeef",
            "--session-id",
            "sess0001",
            "--status",
            "IN_PROGRESS",
        ])
        .env("MPCR_DISPATCH_ROLE", "security-adversary")
        .env("MPCR_REVIEWER_ID", "deadbeef")
        .output()?;
    ensure!(
        !output.status.success(),
        "should fail without MPCR_SESSION_ID"
    );
    let stderr = String::from_utf8_lossy(&output.stderr);
    ensure!(
        stderr.contains("MPCR_SESSION_ID"),
        "error should mention MPCR_SESSION_ID"
    );
    Ok(())
}

#[test]
fn worker_dispatch_role_rejects_mismatched_reviewer_id() -> anyhow::Result<()> {
    let output = Command::new(env!("CARGO_BIN_EXE_mpcr"))
        .args([
            "reviewer",
            "update",
            "--session-dir",
            "/tmp",
            "--reviewer-id",
            "aaaaaaaa",
            "--session-id",
            "sess0001",
            "--status",
            "IN_PROGRESS",
        ])
        .env("MPCR_DISPATCH_ROLE", "security-adversary")
        .env("MPCR_REVIEWER_ID", "bbbbbbbb")
        .env("MPCR_SESSION_ID", "sess0001")
        .output()?;
    ensure!(
        !output.status.success(),
        "should fail with mismatched reviewer_id"
    );
    let stderr = String::from_utf8_lossy(&output.stderr);
    ensure!(
        stderr.contains("identity mismatch"),
        "error should mention identity mismatch"
    );
    Ok(())
}

#[test]
fn worker_dispatch_role_rejects_session_dir_mismatch() -> anyhow::Result<()> {
    let output = Command::new(env!("CARGO_BIN_EXE_mpcr"))
        .args([
            "reviewer",
            "update",
            "--session-dir",
            "/tmp/other",
            "--reviewer-id",
            "deadbeef",
            "--session-id",
            "sess0001",
            "--status",
            "IN_PROGRESS",
        ])
        .env("MPCR_DISPATCH_ROLE", "security-adversary")
        .env("MPCR_REVIEWER_ID", "deadbeef")
        .env("MPCR_SESSION_ID", "sess0001")
        .env("MPCR_SESSION_DIR", "/tmp/correct")
        .output()?;
    ensure!(
        !output.status.success(),
        "should fail with mismatched session-dir"
    );
    let stderr = String::from_utf8_lossy(&output.stderr);
    ensure!(
        stderr.contains("MPCR_SESSION_DIR"),
        "error should mention MPCR_SESSION_DIR"
    );
    Ok(())
}

#[test]
fn worker_applicator_role_rejects_missing_reviewer_id() -> anyhow::Result<()> {
    let output = Command::new(env!("CARGO_BIN_EXE_mpcr"))
        .args([
            "applicator",
            "set-status",
            "--session-dir",
            "/tmp",
            "--reviewer-id",
            "deadbeef",
            "--session-id",
            "sess0001",
            "--initiator-status",
            "REVIEWED",
        ])
        .env("MPCR_APPLICATOR_ROLE", "applicator-worker")
        .env("MPCR_SESSION_ID", "sess0001")
        .env("MPCR_SESSION_DIR", "/tmp")
        .output()?;
    ensure!(
        !output.status.success(),
        "should fail without MPCR_REVIEWER_ID in applicator worker mode"
    );
    let stderr = String::from_utf8_lossy(&output.stderr);
    ensure!(stderr.contains("MPCR_REVIEWER_ID"));
    Ok(())
}

#[test]
fn worker_applicator_role_rejects_missing_session_dir_binding() -> anyhow::Result<()> {
    let output = Command::new(env!("CARGO_BIN_EXE_mpcr"))
        .args([
            "applicator",
            "set-status",
            "--session-dir",
            "/tmp",
            "--reviewer-id",
            "deadbeef",
            "--session-id",
            "sess0001",
            "--initiator-status",
            "REVIEWED",
        ])
        .env("MPCR_APPLICATOR_ROLE", "applicator-worker")
        .env("MPCR_REVIEWER_ID", "deadbeef")
        .env("MPCR_SESSION_ID", "sess0001")
        .output()?;
    ensure!(
        !output.status.success(),
        "should fail without MPCR_SESSION_DIR in applicator worker mode"
    );
    let stderr = String::from_utf8_lossy(&output.stderr);
    ensure!(stderr.contains("MPCR_SESSION_DIR"));
    Ok(())
}

// ── Terminal-parent spawn rejection test ────────────────────────────────────

#[test]
fn spawn_children_rejects_terminal_parent() -> anyhow::Result<()> {
    let repo_root = tempfile::tempdir()?;
    let repo_root_str = repo_root.path().to_string_lossy().to_string();

    let parent = run_cmd_json(&[
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
    let session_dir = json_str(&parent, "session_dir")?.to_string();

    let report_path = repo_root.path().join("report.md");
    std::fs::write(
        &report_path,
        valid_parent_report(
            "deadbeef",
            "sess0001",
            "refs/heads/main",
            SeverityCounts::zero(),
        ),
    )?;
    let report_path_str = report_path
        .to_str()
        .ok_or_else(|| anyhow::anyhow!("non-UTF-8 report path"))?;

    run_cmd_json(&[
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
        "--report-file",
        report_path_str,
        "--blocker",
        "0",
        "--major",
        "0",
        "--minor",
        "0",
        "--nit",
        "0",
    ])?;

    let stderr = run_cmd_failure(&[
        "reviewer",
        "spawn-children",
        "--target-ref",
        "refs/heads/main",
        "--session-dir",
        &session_dir,
        "--session-id",
        "sess0001",
        "--parent-id",
        "deadbeef",
        "--count",
        "1",
    ])?;
    ensure!(
        stderr.contains("terminal"),
        "should reject spawn on terminal parent"
    );
    Ok(())
}

// ── Cross-session include-children purge test ──────────────────────────────

#[test]
#[allow(clippy::too_many_lines)] // Reason: scenario intentionally covers multi-session parent/child permutations end-to-end.
fn cleanup_include_children_does_not_cross_session_boundary() -> anyhow::Result<()> {
    let tmp = tempfile::tempdir()?;
    let session_dir = tmp.path();
    let mut session = sample_session(session_dir);

    let child_sess1 = ReviewEntry {
        reviewer_id: "ch1ld001".to_string(),
        session_id: "sess0001".to_string(),
        target_ref: "refs/heads/main".to_string(),
        initiator_status: InitiatorStatus::Requesting,
        status: ReviewerStatus::InProgress,
        parent_id: Some("deadbeef".to_string()),
        started_at: "2026-01-11T00:30:00Z".to_string(),
        updated_at: "2026-01-11T01:00:00Z".to_string(),
        finished_at: None,
        current_phase: Some(ReviewPhase::Ingestion),
        verdict: None,
        counts: SeverityCounts::zero(),
        report_file: None,
        notes: Vec::new(),
        child_reviews: Vec::new(),
        extra: serde_json::Map::default(),
    };

    let parent_sess2 = ReviewEntry {
        reviewer_id: "deadbeef".to_string(),
        session_id: "sess9999".to_string(),
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
        child_reviews: Vec::new(),
        extra: serde_json::Map::default(),
    };

    let child_sess2 = ReviewEntry {
        reviewer_id: "ch1ld002".to_string(),
        session_id: "sess9999".to_string(),
        target_ref: "refs/heads/main".to_string(),
        initiator_status: InitiatorStatus::Requesting,
        status: ReviewerStatus::InProgress,
        parent_id: Some("deadbeef".to_string()),
        started_at: "2026-01-11T00:30:00Z".to_string(),
        updated_at: "2026-01-11T01:00:00Z".to_string(),
        finished_at: None,
        current_phase: Some(ReviewPhase::Ingestion),
        verdict: None,
        counts: SeverityCounts::zero(),
        report_file: None,
        notes: Vec::new(),
        child_reviews: Vec::new(),
        extra: serde_json::Map::default(),
    };

    session.reviewers.push("ch1ld001".to_string());
    session.reviews.push(child_sess1);
    session.reviewers.push("deadbeef".to_string());
    session.reviews.push(parent_sess2);
    session.reviewers.push("ch1ld002".to_string());
    session.reviews.push(child_sess2);
    write_session_file(session_dir, &session)?;

    let result = run_cmd_json(&[
        "session",
        "cleanup",
        "--session-dir",
        session_dir
            .to_str()
            .ok_or_else(|| anyhow::anyhow!("non-UTF-8"))?,
        "--reviewer-id",
        "deadbeef",
        "--session-id",
        "sess0001",
        "--include-children",
    ])?;

    let purged = json_u64(&result, "purged")?;
    ensure!(
        purged == 2,
        "expected parent + its child purged, got {purged}"
    );

    let after = read_session_json(session_dir)?;
    let reviews = json_array(&after, "reviews")?;
    let top_level_ids: Vec<&str> = reviews
        .iter()
        .filter_map(|r| r.get("reviewer_id").and_then(|v| v.as_str()))
        .collect();
    ensure!(
        top_level_ids.contains(&"deadbeef"),
        "parent from sess9999 should survive (different session_id)"
    );
    ensure!(
        !top_level_ids.contains(&"ch1ld001"),
        "child from sess0001 should be purged"
    );

    let deadbeef_review = reviews
        .iter()
        .find(|r| r.get("reviewer_id").and_then(|v| v.as_str()) == Some("deadbeef"))
        .ok_or_else(|| anyhow::anyhow!("deadbeef/sess9999 missing"))?;
    let children = deadbeef_review
        .get("child_reviews")
        .and_then(|v| v.as_array())
        .ok_or_else(|| anyhow::anyhow!("child_reviews missing"))?;
    ensure!(
        children
            .iter()
            .filter_map(|c| c.get("reviewer_id").and_then(|v| v.as_str()))
            .any(|id| id == "ch1ld002"),
        "child from sess9999 should survive as nested child"
    );
    Ok(())
}

// ── Tests for audit-driven changes ──────────────────────────────────────────

#[test]
fn protocol_invocation_aliases() -> anyhow::Result<()> {
    let out = run_protocol(&["protocol", "invocation-aliases"])?;
    let content = json_str(&out, "content")?;
    ensure!(content.contains("code-review reviewer"));
    ensure!(content.contains("Full-cycle"));
    Ok(())
}

#[test]
fn protocol_workflow_selection() -> anyhow::Result<()> {
    let out = run_protocol(&["protocol", "workflow-selection"])?;
    let content = json_str(&out, "content")?;
    ensure!(content.contains("Applicator mode"));
    ensure!(content.contains("Reviewer mode"));
    Ok(())
}

#[test]
fn protocol_quality_gate() -> anyhow::Result<()> {
    let out = run_protocol(&["protocol", "quality-gate"])?;
    let content = json_str(&out, "content")?;
    ensure!(content.contains("Domain Ledger"));
    ensure!(content.contains("Residual Risk"));
    Ok(())
}

#[test]
fn protocol_change_classification() -> anyhow::Result<()> {
    let out = run_protocol(&["protocol", "change-classification"])?;
    let content = json_str(&out, "content")?;
    ensure!(content.contains("Trivial"));
    ensure!(content.contains("Medium"));
    ensure!(content.contains("Large"));
    Ok(())
}

#[test]
fn protocol_scope_mapping() -> anyhow::Result<()> {
    let out = run_protocol(&["protocol", "scope-mapping"])?;
    let content = json_str(&out, "content")?;
    ensure!(content.contains("Scope Map"));
    ensure!(content.contains("scope-mapper-reviewer"));
    Ok(())
}

#[test]
fn protocol_convergence_planning() -> anyhow::Result<()> {
    let out = run_protocol(&["protocol", "convergence-planning"])?;
    let content = json_str(&out, "content")?;
    ensure!(content.contains("fixed point"));
    ensure!(content.contains("convergence-planner"));
    Ok(())
}

#[test]
fn protocol_domains_includes_staleness_domain() -> anyhow::Result<()> {
    let out = run_protocol(&["protocol", "domains"])?;
    let content = json_str(&out, "content")?;
    ensure!(content.contains("Staleness"));
    ensure!(content.contains("stale docs"));
    Ok(())
}

#[test]
fn protocol_dispatch_list() -> anyhow::Result<()> {
    let out = run_protocol(&["protocol", "dispatch-list"])?;
    let roles = out
        .as_array()
        .ok_or_else(|| anyhow::anyhow!("dispatch-list output was not an array"))?;
    let role_strs: Vec<&str> = roles.iter().filter_map(|v| v.as_str()).collect();
    ensure!(role_strs.contains(&"architecture-critic"));
    ensure!(role_strs.contains(&"explorer"));
    ensure!(role_strs.contains(&"security-adversary"));
    ensure!(role_strs.contains(&"applicator-worker"));
    ensure!(role_strs.contains(&"scope-creep-reviewer"));
    ensure!(role_strs.contains(&"convergence-planner"));
    ensure!(role_strs.contains(&"staleness-auditor"));
    ensure!(!role_strs.contains(&"stale-docs-auditor"));
    ensure!(
        roles.len() >= 30,
        "expected >= 30 roles, got {}",
        roles.len()
    );
    Ok(())
}

#[test]
fn protocol_dispatch_list_json_is_compact_by_default() -> anyhow::Result<()> {
    let output = Command::new(env!("CARGO_BIN_EXE_mpcr"))
        .args(["protocol", "dispatch-list", "--json"])
        .output()?;
    ensure!(
        output.status.success(),
        "dispatch-list failed: {}",
        String::from_utf8_lossy(&output.stderr)
    );
    let stdout = String::from_utf8(output.stdout)?;
    ensure!(
        !stdout.trim_end().contains('\n'),
        "expected compact single-line JSON, got multi-line output:\n{stdout}"
    );
    let parsed: Value = serde_json::from_str(stdout.trim_end())?;
    ensure!(parsed.is_array(), "dispatch-list json should be an array");
    Ok(())
}

#[test]
fn protocol_dispatch_explorer_no_proof_packet() -> anyhow::Result<()> {
    let out = run_protocol(&["protocol", "dispatch", "--role", "explorer"])?;
    let content = json_str(&out, "content")?;
    ensure!(
        !content.contains("## Proof Packet:"),
        "explorer should not use Proof Packet output format"
    );
    ensure!(
        content.contains("context only"),
        "explorer should mention context-only role"
    );
    Ok(())
}

#[test]
fn worker_guard_allows_protocol_commands() -> anyhow::Result<()> {
    let output = Command::new(env!("CARGO_BIN_EXE_mpcr"))
        .env("MPCR_DISPATCH_ROLE", "architecture-critic")
        .env("MPCR_SESSION_DIR", "/tmp")
        .env("MPCR_REVIEWER_ID", "test1234")
        .env("MPCR_SESSION_ID", "sess1234")
        .args(["protocol", "list"])
        .output()?;
    ensure!(
        output.status.success(),
        "worker should be allowed to run protocol list: {}",
        String::from_utf8_lossy(&output.stderr)
    );
    Ok(())
}

#[test]
fn worker_guard_allows_analyze_run() -> anyhow::Result<()> {
    let fixture_dir = tempfile::tempdir()?;
    let sample = fixture_dir.path().join("sample.rs");
    let session_dir = fixture_dir.path().to_string_lossy().to_string();
    fs::write(
        &sample,
        "fn sample() {\n    let x = 1;\n    if x > 0 { println!(\"ok\"); }\n}\n",
    )?;

    let output = Command::new(env!("CARGO_BIN_EXE_mpcr"))
        .env("MPCR_DISPATCH_ROLE", "architecture-critic")
        .env("MPCR_SESSION_DIR", &session_dir)
        .env("MPCR_REVIEWER_ID", "test1234")
        .env("MPCR_SESSION_ID", "sess1234")
        .arg("analyze")
        .arg("run")
        .arg(sample.to_string_lossy().to_string())
        .output()?;
    ensure!(
        output.status.success(),
        "worker should be allowed to run analyze run: {}",
        String::from_utf8_lossy(&output.stderr)
    );
    Ok(())
}

#[test]
fn analyze_check_complexity_ignores_quoted_and_commented_control_tokens() -> anyhow::Result<()> {
    let fixture_dir = tempfile::tempdir()?;
    let sample = fixture_dir.path().join("sample.rs");
    let mut src = String::from("fn helper() {\n");
    for _ in 0..12 {
        src.push_str("    let msg = \"if branch { switch }\"; // else if in comment\n");
    }
    src.push_str("}\n");
    fs::write(&sample, src)?;

    let output = Command::new(env!("CARGO_BIN_EXE_mpcr"))
        .args([
            "analyze",
            "check",
            "--name",
            "complexity",
            &sample.to_string_lossy(),
            "--json",
        ])
        .output()?;
    ensure!(
        output.status.success(),
        "analyze check complexity failed: {}",
        String::from_utf8_lossy(&output.stderr)
    );
    let parsed: Value = serde_json::from_slice(&output.stdout)?;
    ensure!(
        parsed
            .get("kind")
            .and_then(Value::as_str)
            .is_some_and(|kind| kind == "complexity-hotspots"),
        "unexpected check output shape: {parsed}"
    );
    let hotspots = parsed
        .get("complexity_hotspots")
        .and_then(Value::as_array)
        .ok_or_else(|| anyhow::anyhow!("missing complexity_hotspots array"))?;
    ensure!(
        hotspots.is_empty(),
        "expected no complexity hotspots for quoted/comment-only branch markers, got: {hotspots:?}"
    );
    Ok(())
}

#[test]
fn worker_guard_blocks_register() -> anyhow::Result<()> {
    let output = Command::new(env!("CARGO_BIN_EXE_mpcr"))
        .env("MPCR_DISPATCH_ROLE", "architecture-critic")
        .env("MPCR_SESSION_DIR", "/tmp")
        .env("MPCR_REVIEWER_ID", "test1234")
        .env("MPCR_SESSION_ID", "sess1234")
        .args(["reviewer", "register", "--target-ref", "main"])
        .output()?;
    ensure!(
        !output.status.success(),
        "worker should NOT be allowed to run reviewer register"
    );
    let stderr = String::from_utf8_lossy(&output.stderr);
    ensure!(stderr.contains("restricts this executor"));
    Ok(())
}

#[test]
fn supplemental_phases_accepted() -> anyhow::Result<()> {
    for phase in [
        "OVERENGINEERING_GUARD",
        "COMPLEXITY_ANALYSIS",
        "SHIP_READINESS",
        "COMPLETED",
    ] {
        let result = phase.parse::<ReviewPhase>();
        ensure!(
            result.is_ok(),
            "ReviewPhase should accept {phase} but got: {:?}",
            result.err()
        );
    }
    Ok(())
}

#[test]
fn launcher_files_keep_expected_line_endings_and_ps_compat_markers() -> anyhow::Result<()> {
    let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let scripts_dir = manifest_dir
        .parent()
        .ok_or_else(|| anyhow::anyhow!("missing scripts dir parent"))?;

    let posix_launcher = fs::read_to_string(scripts_dir.join("mpcr"))?;
    ensure!(
        !posix_launcher.contains('\r'),
        "posix launcher should use LF only"
    );

    let powershell_launcher = fs::read_to_string(scripts_dir.join("mpcr.ps1"))?;
    ensure!(
        !powershell_launcher.contains('\r'),
        "powershell launcher should use LF only"
    );
    ensure!(
        powershell_launcher.contains("$PSVersionTable.PSEdition"),
        "powershell launcher should use 5.1-compatible edition check"
    );
    ensure!(
        !powershell_launcher.contains("$IsWindows"),
        "powershell launcher should avoid PowerShell Core-only $IsWindows variable"
    );

    let cmd_launcher = fs::read_to_string(scripts_dir.join("mpcr.cmd"))?;
    ensure!(
        !cmd_launcher.contains('\r'),
        "cmd launcher should use LF only"
    );
    ensure!(
        cmd_launcher.contains("set \"BASH_EXIT=%ERRORLEVEL%\""),
        "cmd launcher should capture bash exit code before fallback"
    );
    ensure!(
        cmd_launcher.contains("if \"%BASH_EXIT%\"==\"0\" exit /b 0"),
        "cmd launcher should only exit early when bash succeeds"
    );

    Ok(())
}

#[test]
fn protocol_files_use_lf_line_endings() -> anyhow::Result<()> {
    let protocols_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("protocols");
    for name in ["dispatch.toml", "session.toml"] {
        let content = fs::read_to_string(protocols_dir.join(name))?;
        ensure!(
            !content.contains('\r'),
            "protocol file should use LF-only line endings: {name}"
        );
    }
    Ok(())
}
