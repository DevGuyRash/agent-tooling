#![allow(missing_docs)]
#![allow(clippy::indexing_slicing)]

use anyhow::{ensure, Context};
use mpcr::artifacts::{
    ArtifactDocument, ArtifactHeader, ArtifactKind, ConfidenceLabel, PolicyCategory, PolicyRef,
    PolicyView, ProducerKind, VerificationItemRecord, VerificationStatus,
};
use mpcr::paths::session_paths;
use mpcr::session::{
    register_reviewer, verify_application, ApplicatorArtifactParams, RegisterReviewerParams,
    SessionLocator,
};
use serde_json::Value;
use std::fs;
use std::process::{Command, Output};
use tempfile::tempdir;
use time::{Date, Month};

fn run_cmd(args: &[&str]) -> anyhow::Result<Output> {
    Command::new(env!("CARGO_BIN_EXE_mpcr"))
        .args(args)
        .output()
        .with_context(|| format!("run {}", args.join(" ")))
}

fn header(kind: ArtifactKind, session_id: &str) -> anyhow::Result<ArtifactHeader> {
    ArtifactHeader::new(
        kind,
        "abc123def456".to_string(),
        session_id.to_string(),
        "refs/heads/main".to_string(),
        ProducerKind::ApplicatorVerifier,
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

#[test]
fn protocol_surface_is_v2_only() -> anyhow::Result<()> {
    let list = run_cmd(&["protocol", "list"])?;
    ensure!(list.status.success());
    let list_stdout = String::from_utf8_lossy(&list.stdout);
    ensure!(list_stdout.contains("mode reviewer"));
    ensure!(list_stdout.contains("worker review-composite"));
    ensure!(list_stdout.contains("module core-correctness"));
    ensure!(list_stdout.contains("escalation reopen"));

    let help = run_cmd(&["protocol", "--help"])?;
    ensure!(help.status.success());
    let stdout = String::from_utf8_lossy(&help.stdout);
    ensure!(stdout.contains("mode"));
    ensure!(stdout.contains("worker"));
    ensure!(stdout.contains("module"));
    ensure!(stdout.contains("escalation"));
    ensure!(!stdout.contains("reviewer --phase"));
    ensure!(!stdout.contains("dispatch"));

    let legacy = run_cmd(&["protocol", "reviewer"])?;
    ensure!(!legacy.status.success());
    ensure!(String::from_utf8_lossy(&legacy.stderr).contains("unrecognized subcommand"));
    Ok(())
}

#[test]
fn route_cli_emits_surface_map_and_route_decision() -> anyhow::Result<()> {
    let repo_root = tempdir()?;
    let date = Date::from_calendar_date(2026, Month::March, 8)?;
    let session_dir = session_paths(repo_root.path(), date).session_dir;
    let session_dir_arg = session_dir.to_string_lossy().into_owned();
    let output = run_cmd(&[
        "--json",
        "route",
        "--session-dir",
        &session_dir_arg,
        "--mode",
        "reviewer",
        "--target-ref",
        "refs/heads/main",
        "--execution-capability",
        "single_process",
        "--max-worker-count",
        "2",
        "--orchestrator-read-budget-lines",
        "120",
        "--orchestrator-read-budget-snippets",
        "12",
        "--changed-file",
        "src/api.rs",
        "--behavior-facing-artifact",
        "docs/api.md",
    ])?;
    ensure!(output.status.success());
    let value: Value = serde_json::from_slice(&output.stdout)?;
    ensure!(value
        .get("surface_map")
        .and_then(Value::as_object)
        .is_some());
    ensure!(value
        .get("route_decision")
        .and_then(Value::as_object)
        .is_some());
    ensure!(value
        .get("route_decision")
        .and_then(|route| route.get("selected_modules"))
        .and_then(Value::as_array)
        .is_some_and(|modules| modules
            .iter()
            .any(|module| module.as_str() == Some("docs-staleness"))));
    Ok(())
}

#[test]
fn route_cli_marks_generic_source_changes_as_behavior_change() -> anyhow::Result<()> {
    let repo_root = tempdir()?;
    let date = Date::from_calendar_date(2026, Month::March, 8)?;
    let session_dir = session_paths(repo_root.path(), date).session_dir;
    let session_dir_arg = session_dir.to_string_lossy().into_owned();
    let output = run_cmd(&[
        "--json",
        "route",
        "--session-dir",
        &session_dir_arg,
        "--mode",
        "reviewer",
        "--target-ref",
        "refs/heads/main",
        "--execution-capability",
        "single_process",
        "--max-worker-count",
        "2",
        "--orchestrator-read-budget-lines",
        "120",
        "--orchestrator-read-budget-snippets",
        "12",
        "--changed-file",
        "src/orders.js",
        "--changed-file",
        "README.md",
    ])?;
    ensure!(output.status.success());
    let value: Value = serde_json::from_slice(&output.stdout)?;
    ensure!(value
        .get("surface_map")
        .and_then(|surface_map| surface_map.get("risk_surfaces"))
        .and_then(Value::as_array)
        .is_some_and(|surfaces| surfaces.iter().any(|surface| {
            surface.get("surface_id").and_then(Value::as_str) == Some("behavior-change")
        })));
    Ok(())
}

#[test]
fn route_cli_does_not_treat_embedded_test_or_spec_substrings_as_test_files() -> anyhow::Result<()> {
    let repo_root = tempdir()?;
    let date = Date::from_calendar_date(2026, Month::March, 8)?;
    let session_dir = session_paths(repo_root.path(), date).session_dir;
    let session_dir_arg = session_dir.to_string_lossy().into_owned();

    for changed_file in ["src/contest.rs", "app/species_controller.rb"] {
        let output = run_cmd(&[
            "--json",
            "route",
            "--session-dir",
            &session_dir_arg,
            "--mode",
            "reviewer",
            "--target-ref",
            "refs/heads/main",
            "--execution-capability",
            "single_process",
            "--max-worker-count",
            "2",
            "--orchestrator-read-budget-lines",
            "120",
            "--orchestrator-read-budget-snippets",
            "12",
            "--changed-file",
            changed_file,
        ])?;
        ensure!(output.status.success());
        let value: Value = serde_json::from_slice(&output.stdout)?;
        let surfaces = value
            .get("surface_map")
            .and_then(|surface_map| surface_map.get("risk_surfaces"))
            .and_then(Value::as_array)
            .ok_or_else(|| anyhow::anyhow!("missing risk surfaces for {changed_file}"))?;
        ensure!(surfaces.iter().any(|surface| {
            surface.get("surface_id").and_then(Value::as_str) == Some("behavior-change")
        }));
        ensure!(!surfaces.iter().any(|surface| {
            surface.get("surface_id").and_then(Value::as_str) == Some("test-coverage")
        }));
    }

    Ok(())
}

#[test]
fn route_cli_still_marks_real_test_files_as_test_coverage() -> anyhow::Result<()> {
    let repo_root = tempdir()?;
    let date = Date::from_calendar_date(2026, Month::March, 8)?;
    let session_dir = session_paths(repo_root.path(), date).session_dir;
    let session_dir_arg = session_dir.to_string_lossy().into_owned();

    for changed_file in [
        "src/orders_test.rs",
        "app/models/user_spec.rb",
        "tests/router_behavior.rs",
        "__tests__/router.test.ts",
    ] {
        let output = run_cmd(&[
            "--json",
            "route",
            "--session-dir",
            &session_dir_arg,
            "--mode",
            "reviewer",
            "--target-ref",
            "refs/heads/main",
            "--execution-capability",
            "single_process",
            "--max-worker-count",
            "2",
            "--orchestrator-read-budget-lines",
            "120",
            "--orchestrator-read-budget-snippets",
            "12",
            "--changed-file",
            changed_file,
        ])?;
        ensure!(output.status.success());
        let value: Value = serde_json::from_slice(&output.stdout)?;
        let surfaces = value
            .get("surface_map")
            .and_then(|surface_map| surface_map.get("risk_surfaces"))
            .and_then(Value::as_array)
            .ok_or_else(|| anyhow::anyhow!("missing risk surfaces for {changed_file}"))?;
        ensure!(surfaces.iter().any(|surface| {
            surface.get("surface_id").and_then(Value::as_str) == Some("test-coverage")
        }));
    }

    Ok(())
}

#[test]
fn route_persist_writes_artifacts_and_updates_session_pointers() -> anyhow::Result<()> {
    let repo_root = tempdir()?;
    let date = Date::from_calendar_date(2026, Month::March, 8)?;
    let session_dir = session_paths(repo_root.path(), date).session_dir;
    let session_dir_arg = session_dir.to_string_lossy().into_owned();
    let output = run_cmd(&[
        "--json",
        "route",
        "--session-dir",
        &session_dir_arg,
        "--mode",
        "reviewer",
        "--target-ref",
        "refs/heads/main",
        "--execution-capability",
        "parallel_subagents",
        "--max-worker-count",
        "4",
        "--orchestrator-read-budget-lines",
        "120",
        "--orchestrator-read-budget-snippets",
        "12",
        "--changed-file",
        "src/api.rs",
        "--behavior-facing-artifact",
        "docs/api.md",
        "--persist",
    ])?;
    ensure!(output.status.success());
    let routed: Value = serde_json::from_slice(&output.stdout)?;
    let surface_rel = routed
        .get("persisted")
        .and_then(|persisted| persisted.get("surface_map"))
        .and_then(|artifact| artifact.get("path"))
        .and_then(Value::as_str)
        .ok_or_else(|| anyhow::anyhow!("missing persisted surface_map path"))?;
    let route_rel = routed
        .get("persisted")
        .and_then(|persisted| persisted.get("route_decision"))
        .and_then(|artifact| artifact.get("path"))
        .and_then(Value::as_str)
        .ok_or_else(|| anyhow::anyhow!("missing persisted route_decision path"))?;
    ensure!(repo_root.path().join(surface_rel).exists());
    ensure!(repo_root.path().join(route_rel).exists());

    let show = run_cmd(&[
        "--json",
        "session",
        "show",
        "--session-dir",
        &session_dir_arg,
    ])?;
    ensure!(show.status.success());
    let session_value: Value = serde_json::from_slice(&show.stdout)?;
    ensure!(
        session_value
            .get("current")
            .and_then(|current| current.get("surface_map"))
            .and_then(|artifact| artifact.get("path"))
            .and_then(Value::as_str)
            == Some(surface_rel)
    );
    ensure!(
        session_value
            .get("current")
            .and_then(|current| current.get("route_decision"))
            .and_then(|artifact| artifact.get("path"))
            .and_then(Value::as_str)
            == Some(route_rel)
    );
    ensure!(session_value
        .get("artifacts")
        .and_then(Value::as_array)
        .is_some_and(|artifacts| artifacts.len() >= 2));
    Ok(())
}

#[test]
fn validate_rejects_legacy_artifact_with_required_message() -> anyhow::Result<()> {
    let dir = tempdir()?;
    let artifact_file = dir.path().join("legacy.toml");
    fs::write(
        &artifact_file,
        "schema_version = \"proof_packet.v2\"\nartifact_kind = \"parent_review_report\"\n",
    )?;
    let output = run_cmd(&[
        "validate",
        "--artifact-file",
        artifact_file.to_string_lossy().as_ref(),
        "--kind",
        "parent-review",
        "--layer",
        "hard",
    ])?;
    ensure!(!output.status.success());
    let stderr = String::from_utf8_lossy(&output.stderr);
    ensure!(stderr.contains("error: legacy v1 session/report/artifact is not supported in v2"));
    ensure!(stderr.contains("hint: start a fresh v2 session"));
    Ok(())
}

#[test]
fn session_metrics_reports_categorical_counts() -> anyhow::Result<()> {
    let repo_root = tempdir()?;
    let date = Date::from_calendar_date(2026, Month::March, 8)?;
    let session_dir = session_paths(repo_root.path(), date).session_dir;
    let locator = SessionLocator::from_session_dir(session_dir.clone());

    let register = register_reviewer(RegisterReviewerParams {
        session: locator.clone(),
        target_ref: "refs/heads/main".to_string(),
        reviewer_id: Some("review01".to_string()),
    })?;

    let artifact =
        ArtifactDocument::VerificationResult(mpcr::artifacts::VerificationResultArtifact {
            header: header(ArtifactKind::VerificationResult, &register.session_id)?,
            verified_items: vec![VerificationItemRecord {
                finding_id: "F001".to_string(),
                status: VerificationStatus::Yes,
                notes: "verified".to_string(),
            }],
            failed_items: Vec::new(),
            partial_items: Vec::new(),
            residual_risks: Vec::new(),
        });
    let artifact_file = session_dir.join("verification_result.toml");
    fs::write(&artifact_file, artifact.to_toml_string()?)?;
    verify_application(ApplicatorArtifactParams {
        session: locator,
        artifact_file,
    })?;

    let output = run_cmd(&[
        "--json",
        "session",
        "metrics",
        "--session-dir",
        session_dir.to_string_lossy().as_ref(),
    ])?;
    ensure!(output.status.success());
    let value: Value = serde_json::from_slice(&output.stdout)?;
    ensure!(
        value
            .get("verification_outcome")
            .and_then(Value::as_object)
            .and_then(|map| map.get("yes"))
            .and_then(Value::as_u64)
            == Some(1)
    );
    ensure!(value
        .get("grouped_precision")
        .and_then(Value::as_array)
        .is_some_and(|rows| rows.iter().any(|row| {
            row.get("worker_kind").and_then(Value::as_str) == Some("applicator-verifier")
                && row.get("outcome_type").and_then(Value::as_str) == Some("verification_yes")
                && row.get("count").and_then(Value::as_u64) == Some(1)
        })));
    Ok(())
}
