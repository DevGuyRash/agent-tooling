#![allow(missing_docs)]
#![allow(clippy::indexing_slicing)]

use anyhow::{ensure, Context};
use mpcr::artifacts::{
    now_rfc3339, parse_artifact_file, ApplicationResultArtifact, ArtifactDocument, ArtifactHeader,
    ArtifactKind, ConfidenceLabel, CoverageSummary, Disposition, DispositionRecord, ModuleId,
    ParentReviewArtifact, PolicyCategory, PolicyRef, PolicyView, ProducerKind, ReviewVerdict,
    ShipReadinessSummary, ShipReadinessVerdict, SurfaceId, VerificationItemRecord,
    VerificationStatus,
};
use mpcr::paths::session_paths;
use mpcr::router::{build_route_revision, default_router_policy_refs};
use mpcr::router_types::RouteRevisionRequest;
use mpcr::session::{
    finalize_application, register_reviewer, verify_application, ApplicatorArtifactParams,
    RegisterReviewerParams, SessionLocator,
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

fn parent_review_doc(session_id: &str) -> anyhow::Result<ArtifactDocument> {
    Ok(ArtifactDocument::ParentReview(ParentReviewArtifact {
        header: ArtifactHeader::new(
            ArtifactKind::ParentReview,
            "def456abc789".to_string(),
            session_id.to_string(),
            "refs/heads/main".to_string(),
            ProducerKind::FinalSynthesizer,
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

fn write_route_revision_doc(
    repo_root: &std::path::Path,
    session_dir: &std::path::Path,
    session_id: &str,
    route_rel: &str,
) -> anyhow::Result<std::path::PathBuf> {
    let route_path = repo_root.join(route_rel);
    let ArtifactDocument::RouteDecision(route) = parse_artifact_file(&route_path)? else {
        anyhow::bail!("persisted route artifact did not parse as route_decision");
    };
    let revision = RouteRevisionRequest {
        discovered_surfaces: vec![SurfaceId::AuthAccess],
        added_modules: Vec::new(),
        raise_rigor: false,
        widen_architecture: false,
    };
    let artifact = build_route_revision(
        ArtifactHeader::new(
            ArtifactKind::RouteRevision,
            "feedfacecafe".to_string(),
            session_id.to_string(),
            "refs/heads/main".to_string(),
            ProducerKind::Router,
            now_rfc3339(),
            ConfidenceLabel::High,
            90,
            default_router_policy_refs(&route.selected_modules),
        )?,
        &route,
        route.header.artifact_id.clone(),
        &revision,
    );
    let artifact_file = session_dir.join("route-revision.toml");
    fs::write(
        &artifact_file,
        ArtifactDocument::RouteRevision(artifact).to_toml_string()?,
    )?;
    Ok(artifact_file)
}

#[test]
fn protocol_surface_includes_dispatch_and_static_discovery() -> anyhow::Result<()> {
    let list = run_cmd(&["protocol", "list"])?;
    ensure!(list.status.success());
    let list_stdout = String::from_utf8_lossy(&list.stdout);
    ensure!(list_stdout.contains("mode reviewer"));
    ensure!(list_stdout.contains("worker review-composite"));
    ensure!(list_stdout.contains("worker orchestrator-root"));
    ensure!(list_stdout.contains("worker domain:core-correctness"));
    ensure!(list_stdout.contains("worker apply-composite"));
    ensure!(list_stdout.contains("module core-correctness"));
    ensure!(list_stdout.contains("escalation reopen"));

    let help = run_cmd(&["protocol", "--help"])?;
    ensure!(help.status.success());
    let stdout = String::from_utf8_lossy(&help.stdout);
    ensure!(stdout.contains("mode"));
    ensure!(stdout.contains("worker"));
    ensure!(stdout.contains("module"));
    ensure!(stdout.contains("escalation"));
    ensure!(stdout.contains("dispatch"));
    ensure!(!stdout.contains("reviewer --phase"));

    let dispatch = run_cmd(&["protocol", "dispatch", "--role", "domain:core-correctness"])?;
    ensure!(dispatch.status.success());
    let dispatch_stdout = String::from_utf8_lossy(&dispatch.stdout);
    ensure!(dispatch_stdout.contains("# Dispatch domain:core-correctness"));
    ensure!(dispatch_stdout.contains("## Operating Rules"));
    ensure!(dispatch_stdout.contains("## Referenced Pack Lookups"));
    ensure!(dispatch_stdout.contains("`mpcr protocol mode --mode reviewer --view checklist`"));
    ensure!(
        dispatch_stdout.contains("`mpcr protocol worker --kind domain-reviewer --view checklist`")
    );
    ensure!(
        dispatch_stdout.contains("`mpcr protocol module --id core-correctness --view checklist`")
    );
    ensure!(dispatch_stdout.contains("\n## reviewer\n"));
    ensure!(dispatch_stdout.contains("\n## domain-reviewer\n"));
    ensure!(dispatch_stdout.contains("\n## core-correctness\n"));

    let root_dispatch = run_cmd(&["protocol", "dispatch", "--role", "orchestrator-root"])?;
    ensure!(root_dispatch.status.success());
    let root_dispatch_stdout = String::from_utf8_lossy(&root_dispatch.stdout);
    ensure!(root_dispatch_stdout.contains("# Dispatch orchestrator-root"));
    ensure!(root_dispatch_stdout.contains("worker orchestrator-root"));

    let apply_dispatch = run_cmd(&["protocol", "dispatch", "--role", "apply-composite"])?;
    ensure!(apply_dispatch.status.success());
    ensure!(String::from_utf8_lossy(&apply_dispatch.stdout).contains("# Dispatch apply-composite"));

    let legacy = run_cmd(&["protocol", "reviewer"])?;
    ensure!(!legacy.status.success());
    ensure!(String::from_utf8_lossy(&legacy.stderr).contains("unrecognized subcommand"));
    Ok(())
}

#[test]
fn help_surfaces_explain_opaque_target_refs_and_canonical_session_leafs() -> anyhow::Result<()> {
    let route_help = run_cmd(&["route", "--help"])?;
    ensure!(route_help.status.success());
    let route_stdout = String::from_utf8_lossy(&route_help.stdout);
    ensure!(route_stdout.contains("literal HEAD"));
    ensure!(route_stdout.contains("Each repo/date leaf can hold only one target-ref string"));

    let register_help = run_cmd(&["reviewer", "register", "--help"])?;
    ensure!(register_help.status.success());
    let register_stdout = String::from_utf8_lossy(&register_help.stdout);
    ensure!(register_stdout.contains("literal HEAD"));
    ensure!(register_stdout.contains("root orchestration anchor"));

    let spawn_routed_help = run_cmd(&["reviewer", "spawn-routed", "--help"])?;
    ensure!(spawn_routed_help.status.success());
    let spawn_routed_stdout = String::from_utf8_lossy(&spawn_routed_help.stdout);
    ensure!(spawn_routed_stdout.contains("Each repo/date leaf can hold only one target-ref string"));
    Ok(())
}

#[test]
fn protocol_surfaces_require_end_to_end_claim_challenge() -> anyhow::Result<()> {
    let reviewer = run_cmd(&[
        "protocol",
        "mode",
        "--mode",
        "reviewer",
        "--view",
        "checklist",
    ])?;
    ensure!(reviewer.status.success());
    let reviewer_stdout = String::from_utf8_lossy(&reviewer.stdout);
    ensure!(reviewer_stdout.contains("introducing condition"));
    ensure!(reviewer_stdout.contains("effect or closure path"));

    let review_composite = run_cmd(&[
        "protocol",
        "worker",
        "--kind",
        "review-composite",
        "--view",
        "checklist",
    ])?;
    ensure!(review_composite.status.success());
    let review_composite_stdout = String::from_utf8_lossy(&review_composite.stdout);
    ensure!(review_composite_stdout.contains("introducing condition"));
    ensure!(review_composite_stdout.contains("effect or closure path"));

    let verifier = run_cmd(&[
        "protocol",
        "worker",
        "--kind",
        "applicator-verifier",
        "--view",
        "checklist",
    ])?;
    ensure!(verifier.status.success());
    let verifier_stdout = String::from_utf8_lossy(&verifier.stdout);
    ensure!(verifier_stdout.contains("post-change code"));
    ensure!(verifier_stdout.contains("effect or closure path"));

    let reopen = run_cmd(&[
        "protocol",
        "escalation",
        "--id",
        "reopen",
        "--view",
        "checklist",
    ])?;
    ensure!(reopen.status.success());
    let reopen_stdout = String::from_utf8_lossy(&reopen.stdout);
    ensure!(reopen_stdout.contains("introducing condition"));
    ensure!(reopen_stdout.contains("effect or closure path"));
    Ok(())
}

#[test]
fn applicator_route_cli_uses_apply_composite_for_direct_and_budget_limited_routes(
) -> anyhow::Result<()> {
    let repo_root = tempdir()?;
    let date = Date::from_calendar_date(2026, Month::March, 8)?;
    let session_dir = session_paths(repo_root.path(), date).session_dir;
    let session_dir_arg = session_dir.to_string_lossy().into_owned();

    let single_process = run_cmd(&[
        "--json",
        "route",
        "--session-dir",
        &session_dir_arg,
        "--mode",
        "applicator",
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
        "src/auth.rs",
    ])?;
    ensure!(single_process.status.success());
    let single_value: Value = serde_json::from_slice(&single_process.stdout)?;
    ensure!(
        single_value
            .get("route_decision")
            .and_then(|route| route.get("execution_architecture"))
            .and_then(Value::as_str)
            == Some("direct")
    );
    ensure!(single_value
        .get("route_decision")
        .and_then(|route| route.get("worker_plan"))
        .and_then(Value::as_array)
        .is_some_and(|workers| {
            workers.len() == 1
                && workers[0].get("worker_kind").and_then(Value::as_str) == Some("apply-composite")
                && workers[0].get("role_id").and_then(Value::as_str) == Some("apply-composite")
        }));

    let budget_limited = run_cmd(&[
        "--json",
        "route",
        "--session-dir",
        &session_dir_arg,
        "--mode",
        "applicator",
        "--target-ref",
        "refs/heads/main",
        "--execution-capability",
        "bounded_helpers",
        "--max-worker-count",
        "1",
        "--orchestrator-read-budget-lines",
        "120",
        "--orchestrator-read-budget-snippets",
        "12",
        "--changed-file",
        "src/auth.rs",
    ])?;
    ensure!(budget_limited.status.success());
    let budget_value: Value = serde_json::from_slice(&budget_limited.stdout)?;
    ensure!(
        budget_value
            .get("route_decision")
            .and_then(|route| route.get("execution_architecture"))
            .and_then(Value::as_str)
            == Some("direct")
    );
    ensure!(
        budget_value
            .get("route_decision")
            .and_then(|route| route.get("resource_budget"))
            .and_then(|budget| budget.get("planned_worker_count"))
            .and_then(Value::as_u64)
            == Some(1)
    );
    ensure!(budget_value
        .get("route_decision")
        .and_then(|route| route.get("worker_plan"))
        .and_then(Value::as_array)
        .is_some_and(|workers| {
            workers.len() == 1
                && workers[0].get("worker_kind").and_then(Value::as_str) == Some("apply-composite")
        }));
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
    ensure!(value.get("session_dir").and_then(Value::as_str) == Some(session_dir_arg.as_str()));
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
    ensure!(value
        .get("route_decision")
        .and_then(|route| route.get("selected_modules"))
        .and_then(Value::as_array)
        .is_some_and(|modules| modules.len() == 15));
    ensure!(value
        .get("route_decision")
        .and_then(|route| route.get("worker_plan"))
        .and_then(Value::as_array)
        .is_some_and(|workers| workers.iter().any(|worker| {
            worker.get("worker_kind").and_then(Value::as_str) == Some("language-detector")
        })));
    ensure!(value
        .get("route_decision")
        .and_then(|route| route.get("worker_plan"))
        .and_then(Value::as_array)
        .is_some_and(|workers| workers.iter().any(|worker| {
            worker.get("worker_kind").and_then(Value::as_str) == Some("final-synthesizer")
        })));
    Ok(())
}

#[test]
fn reviewer_register_invalid_custom_id_names_the_reviewer_field() -> anyhow::Result<()> {
    let repo_root = tempdir()?;
    let date = Date::from_calendar_date(2026, Month::March, 8)?;
    let session_dir = session_paths(repo_root.path(), date).session_dir;
    let session_dir_arg = session_dir.to_string_lossy().into_owned();

    let output = run_cmd(&[
        "reviewer",
        "register",
        "--session-dir",
        &session_dir_arg,
        "--target-ref",
        "refs/heads/main",
        "--reviewer-id",
        "root-audit-01",
    ])?;
    ensure!(!output.status.success());
    let stderr = String::from_utf8_lossy(&output.stderr);
    ensure!(stderr.contains("reviewer_id must be 8 lowercase alphanumeric characters"));
    ensure!(!stderr.contains("session_id must be 8 lowercase alphanumeric characters"));
    ensure!(
        !session_dir.exists(),
        "invalid reviewer IDs must fail before creating a canonical session scaffold"
    );
    Ok(())
}

#[test]
fn route_target_ref_mismatch_error_points_to_fresh_session_paths() -> anyhow::Result<()> {
    let repo_root = tempdir()?;
    let date = Date::from_calendar_date(2026, Month::March, 8)?;
    let session_dir = session_paths(repo_root.path(), date).session_dir;
    let session_dir_arg = session_dir.to_string_lossy().into_owned();

    let first = run_cmd(&[
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
        "--persist",
    ])?;
    ensure!(first.status.success());

    let second = run_cmd(&[
        "route",
        "--session-dir",
        &session_dir_arg,
        "--mode",
        "reviewer",
        "--target-ref",
        "refs/heads/other",
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
        "--persist",
    ])?;
    ensure!(!second.status.success());
    let stderr = String::from_utf8_lossy(&second.stderr);
    ensure!(stderr.contains("session target_ref"));
    ensure!(stderr.contains("same exact target-ref string"));
    ensure!(stderr.contains("canonical session leaf"));
    ensure!(stderr.contains("clean that leaf or choose another date"));
    Ok(())
}

#[test]
fn reviewer_spawn_routed_materializes_missing_route_workers() -> anyhow::Result<()> {
    let repo_root = tempdir()?;
    let date = Date::from_calendar_date(2026, Month::March, 8)?;
    let session_dir = session_paths(repo_root.path(), date).session_dir;
    let session_dir_arg = session_dir.to_string_lossy().into_owned();

    let route = run_cmd(&[
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
        "8",
        "--orchestrator-read-budget-lines",
        "120",
        "--orchestrator-read-budget-snippets",
        "12",
        "--changed-file",
        "src/lib.rs",
        "--persist",
    ])?;
    ensure!(route.status.success());
    let route_json: Value = serde_json::from_slice(&route.stdout)?;
    let planned_count = route_json["route_decision"]["worker_plan"]
        .as_array()
        .map_or(0, Vec::len);
    ensure!(planned_count > 0);

    let register = run_cmd(&[
        "--json",
        "reviewer",
        "register",
        "--session-dir",
        &session_dir_arg,
        "--target-ref",
        "refs/heads/main",
        "--reviewer-id",
        "root0013",
    ])?;
    ensure!(register.status.success());

    let spawn = run_cmd(&[
        "--json",
        "reviewer",
        "spawn-routed",
        "--session-dir",
        &session_dir_arg,
        "--parent-id",
        "root0013",
    ])?;
    ensure!(spawn.status.success());
    let spawn_json: Value = serde_json::from_slice(&spawn.stdout)?;
    ensure!(spawn_json["spawned"]
        .as_array()
        .is_some_and(|items| items.len() == planned_count));
    ensure!(spawn_json["skipped_existing_roles"]
        .as_array()
        .is_some_and(Vec::is_empty));
    ensure!(spawn_json["spawned"].as_array().is_some_and(|items| {
        items
            .iter()
            .any(|item| item["role_id"].as_str() == Some("language-detector"))
            && items
                .iter()
                .any(|item| item["role_id"].as_str() == Some("final-synthesis"))
    }));

    let second = run_cmd(&[
        "--json",
        "reviewer",
        "spawn-routed",
        "--session-dir",
        &session_dir_arg,
        "--parent-id",
        "root0013",
    ])?;
    ensure!(second.status.success());
    let second_json: Value = serde_json::from_slice(&second.stdout)?;
    ensure!(second_json["spawned"].as_array().is_some_and(Vec::is_empty));
    ensure!(second_json["skipped_existing_roles"]
        .as_array()
        .is_some_and(|items| items.len() == planned_count));
    Ok(())
}

#[test]
fn reviewer_spawn_routed_respawns_workers_after_route_revision_scope_change() -> anyhow::Result<()>
{
    let repo_root = tempdir()?;
    let date = Date::from_calendar_date(2026, Month::March, 8)?;
    let session_dir = session_paths(repo_root.path(), date).session_dir;
    let session_dir_arg = session_dir.to_string_lossy().into_owned();

    let route = run_cmd(&[
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
        "8",
        "--orchestrator-read-budget-lines",
        "120",
        "--orchestrator-read-budget-snippets",
        "12",
        "--changed-file",
        "src/lib.rs",
        "--persist",
    ])?;
    ensure!(route.status.success());
    let route_json: Value = serde_json::from_slice(&route.stdout)?;
    let planned_count = route_json["route_decision"]["worker_plan"]
        .as_array()
        .map_or(0, Vec::len);
    ensure!(planned_count > 0);
    let route_rel = route_json["persisted"]["route_decision"]["path"]
        .as_str()
        .ok_or_else(|| anyhow::anyhow!("missing persisted route_decision path"))?;

    let register = run_cmd(&[
        "--json",
        "reviewer",
        "register",
        "--session-dir",
        &session_dir_arg,
        "--target-ref",
        "refs/heads/main",
        "--reviewer-id",
        "root0015",
    ])?;
    ensure!(register.status.success());
    let register_json: Value = serde_json::from_slice(&register.stdout)?;
    let root_id = register_json["reviewer_id"]
        .as_str()
        .ok_or_else(|| anyhow::anyhow!("missing reviewer id"))?;

    let first_spawn = run_cmd(&[
        "--json",
        "reviewer",
        "spawn-routed",
        "--session-dir",
        &session_dir_arg,
        "--parent-id",
        root_id,
    ])?;
    ensure!(first_spawn.status.success());

    let session_id = register_json["session_id"]
        .as_str()
        .ok_or_else(|| anyhow::anyhow!("missing session id"))?;
    let revision_file =
        write_route_revision_doc(repo_root.path(), &session_dir, session_id, route_rel)?;
    let apply = run_cmd(&[
        "--json",
        "session",
        "apply-route-revision",
        "--session-dir",
        &session_dir_arg,
        "--artifact-file",
        revision_file.to_string_lossy().as_ref(),
    ])?;
    ensure!(apply.status.success());

    let second_spawn = run_cmd(&[
        "--json",
        "reviewer",
        "spawn-routed",
        "--session-dir",
        &session_dir_arg,
        "--parent-id",
        root_id,
    ])?;
    ensure!(second_spawn.status.success());
    let second_json: Value = serde_json::from_slice(&second_spawn.stdout)?;
    ensure!(second_json["spawned"]
        .as_array()
        .is_some_and(|items| items.len() == planned_count));
    ensure!(second_json["skipped_existing_roles"]
        .as_array()
        .is_some_and(Vec::is_empty));
    Ok(())
}

#[test]
fn reviewer_spawn_routed_rejects_child_parent_ids() -> anyhow::Result<()> {
    let repo_root = tempdir()?;
    let date = Date::from_calendar_date(2026, Month::March, 8)?;
    let session_dir = session_paths(repo_root.path(), date).session_dir;
    let session_dir_arg = session_dir.to_string_lossy().into_owned();

    let route = run_cmd(&[
        "--json",
        "route",
        "--mode",
        "reviewer",
        "--repo-root",
        &repo_root.path().to_string_lossy(),
        "--date",
        "2026-03-08",
        "--target-ref",
        "refs/heads/main",
        "--execution-capability",
        "single_process",
        "--max-worker-count",
        "4",
        "--orchestrator-read-budget-lines",
        "200",
        "--orchestrator-read-budget-snippets",
        "20",
        "--changed-file",
        "src/lib.rs",
        "--persist",
    ])?;
    ensure!(route.status.success());

    let register = run_cmd(&[
        "--json",
        "reviewer",
        "register",
        "--session-dir",
        &session_dir_arg,
        "--target-ref",
        "refs/heads/main",
        "--reviewer-id",
        "root0014",
    ])?;
    ensure!(register.status.success());

    let child = run_cmd(&[
        "--json",
        "reviewer",
        "spawn-children",
        "--session-dir",
        &session_dir_arg,
        "--parent-id",
        "root0014",
        "--count",
        "1",
        "--role-id",
        "domain:core-correctness",
        "--worker-kind",
        "domain-reviewer",
        "--module-id",
        "core-correctness",
    ])?;
    ensure!(child.status.success());
    let child_json: Value = serde_json::from_slice(&child.stdout)?;
    let child_id = child_json["child_ids"][0]
        .as_str()
        .ok_or_else(|| anyhow::anyhow!("missing child reviewer id"))?;

    let spawn = run_cmd(&[
        "reviewer",
        "spawn-routed",
        "--session-dir",
        &session_dir_arg,
        "--parent-id",
        child_id,
    ])?;
    ensure!(!spawn.status.success());
    let stderr = String::from_utf8_lossy(&spawn.stderr);
    ensure!(stderr.contains("requires a root reviewer parent_id"));

    let reports = run_cmd(&[
        "--json",
        "session",
        "reports",
        "--session-dir",
        &session_dir_arg,
        "--recursive",
    ])?;
    ensure!(reports.status.success());
    let reports_json: Value = serde_json::from_slice(&reports.stdout)?;
    ensure!(reports_json["reports"]
        .as_array()
        .is_some_and(|items| items.len() == 2));
    Ok(())
}

#[test]
fn recursive_plaintext_reports_render_hierarchy_and_parent_links() -> anyhow::Result<()> {
    let repo_root = tempdir()?;
    let date = Date::from_calendar_date(2026, Month::March, 8)?;
    let session_dir = session_paths(repo_root.path(), date).session_dir;
    let session_dir_arg = session_dir.to_string_lossy().into_owned();

    let register = run_cmd(&[
        "--json",
        "reviewer",
        "register",
        "--session-dir",
        &session_dir_arg,
        "--target-ref",
        "refs/heads/main",
        "--reviewer-id",
        "root0099",
    ])?;
    ensure!(register.status.success());
    let register_json: Value = serde_json::from_slice(&register.stdout)?;
    let root_id = register_json["reviewer_id"]
        .as_str()
        .ok_or_else(|| anyhow::anyhow!("missing root reviewer id"))?;

    let spawn = run_cmd(&[
        "--json",
        "reviewer",
        "spawn-children",
        "--session-dir",
        &session_dir_arg,
        "--parent-id",
        root_id,
        "--count",
        "1",
        "--role-id",
        "domain:core-correctness",
        "--worker-kind",
        "domain-reviewer",
        "--domain-id",
        "core-correctness",
        "--module-id",
        "core-correctness",
        "--focus-surface",
        "public-api",
        "--claimed-scope",
        "own domain `core-correctness`",
        "--delegated-scope",
        "do not delegate the same domain investigation again",
    ])?;
    ensure!(spawn.status.success());
    let spawn_json: Value = serde_json::from_slice(&spawn.stdout)?;
    let child_id = spawn_json["child_ids"]
        .as_array()
        .and_then(|values| values.first())
        .and_then(Value::as_str)
        .ok_or_else(|| anyhow::anyhow!("missing child reviewer id"))?;

    let reports = run_cmd(&[
        "session",
        "reports",
        "--session-dir",
        &session_dir_arg,
        "--recursive",
    ])?;
    ensure!(reports.status.success());
    let stdout = String::from_utf8_lossy(&reports.stdout);
    let root_line = stdout
        .lines()
        .find(|line| line.starts_with(&format!("{root_id} ")))
        .ok_or_else(|| anyhow::anyhow!("missing root line in session reports output"))?;
    ensure!(!root_line.starts_with("  - "));
    let child_line = stdout
        .lines()
        .find(|line| line.contains(&format!("- {child_id} ")))
        .ok_or_else(|| anyhow::anyhow!("missing child line in session reports output"))?;
    ensure!(child_line.starts_with("  - "));
    ensure!(child_line.contains(&format!("parent={root_id}")));
    Ok(())
}

#[test]
fn route_cli_normalizes_relative_session_dirs_and_persisted_output_exposes_session_dir(
) -> anyhow::Result<()> {
    let repo_root = tempdir()?;
    let relative_session_dir = ".local/reports/code_reviews/2026-03-08";
    let output = Command::new(env!("CARGO_BIN_EXE_mpcr"))
        .current_dir(repo_root.path())
        .args([
            "--json",
            "route",
            "--session-dir",
            relative_session_dir,
            "--mode",
            "reviewer",
            "--target-ref",
            "refs/heads/main",
            "--execution-capability",
            "single_process",
            "--max-worker-count",
            "1",
            "--orchestrator-read-budget-lines",
            "120",
            "--orchestrator-read-budget-snippets",
            "8",
            "--changed-file",
            "src/lib.rs",
            "--persist",
        ])
        .output()
        .context("run relative route command")?;
    ensure!(output.status.success());
    let value: Value = serde_json::from_slice(&output.stdout)?;
    let absolute_session_dir = repo_root.path().join(relative_session_dir);
    ensure!(
        value.get("session_dir").and_then(Value::as_str)
            == Some(absolute_session_dir.to_string_lossy().as_ref())
    );
    ensure!(
        value
            .get("persisted")
            .and_then(|persisted| persisted.get("session_dir"))
            .and_then(Value::as_str)
            == Some(absolute_session_dir.to_string_lossy().as_ref())
    );
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
    ensure!(routed.get("session_dir").and_then(Value::as_str) == Some(session_dir_arg.as_str()));
    ensure!(
        routed
            .get("persisted")
            .and_then(|persisted| persisted.get("session_dir"))
            .and_then(Value::as_str)
            == Some(session_dir_arg.as_str())
    );
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
fn validate_accepts_snake_case_artifact_kind_spelling() -> anyhow::Result<()> {
    let repo_root = tempdir()?;
    let date = Date::from_calendar_date(2026, Month::March, 8)?;
    let session_dir = session_paths(repo_root.path(), date).session_dir;
    let session_dir_arg = session_dir.to_string_lossy().into_owned();
    let route = run_cmd(&[
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
        "1",
        "--orchestrator-read-budget-lines",
        "120",
        "--orchestrator-read-budget-snippets",
        "8",
        "--changed-file",
        "src/lib.rs",
        "--persist",
    ])?;
    ensure!(route.status.success());
    let routed: Value = serde_json::from_slice(&route.stdout)?;
    let artifact_rel = routed
        .get("persisted")
        .and_then(|persisted| persisted.get("route_decision"))
        .and_then(|artifact| artifact.get("json_path"))
        .and_then(Value::as_str)
        .ok_or_else(|| anyhow::anyhow!("missing persisted route_decision json_path"))?;
    let artifact_path = repo_root.path().join(artifact_rel);
    let output = run_cmd(&[
        "validate",
        "--session-dir",
        &session_dir_arg,
        "--artifact-file",
        artifact_path.to_string_lossy().as_ref(),
        "--kind",
        "route_decision",
        "--layer",
        "hard",
    ])?;
    ensure!(output.status.success());
    Ok(())
}

#[test]
fn fullcycle_plan_rejects_incomplete_cycle_artifacts() -> anyhow::Result<()> {
    let repo_root = tempdir()?;
    let date = Date::from_calendar_date(2026, Month::March, 8)?;
    let session_dir = session_paths(repo_root.path(), date).session_dir;
    let session_dir_arg = session_dir.to_string_lossy().into_owned();
    let route = run_cmd(&[
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
        "1",
        "--orchestrator-read-budget-lines",
        "120",
        "--orchestrator-read-budget-snippets",
        "8",
        "--changed-file",
        "src/lib.rs",
        "--persist",
    ])?;
    ensure!(route.status.success());
    let output_file = session_dir.join("convergence-state.json");
    let output = run_cmd(&[
        "--json",
        "fullcycle",
        "plan",
        "--session-dir",
        &session_dir_arg,
        "--output",
        output_file.to_string_lossy().as_ref(),
    ])?;
    ensure!(!output.status.success());
    let stderr = String::from_utf8_lossy(&output.stderr);
    ensure!(stderr.contains("fullcycle plan requires a finalized"));
    ensure!(stderr.contains("parent_review"));
    ensure!(!output_file.exists());
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
fn session_cleanup_cli_removes_session_dir() -> anyhow::Result<()> {
    let repo_root = tempdir()?;
    let date = Date::from_calendar_date(2026, Month::March, 8)?;
    let session_dir = session_paths(repo_root.path(), date).session_dir;
    let session_dir_arg = session_dir.to_string_lossy().into_owned();

    let route = run_cmd(&[
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
        "src/lib.rs",
        "--persist",
    ])?;
    ensure!(route.status.success());
    ensure!(session_dir.exists());

    let cleanup = run_cmd(&[
        "--json",
        "session",
        "cleanup",
        "--session-dir",
        &session_dir_arg,
    ])?;
    ensure!(cleanup.status.success());
    let cleanup_json: Value = serde_json::from_slice(&cleanup.stdout)?;
    ensure!(cleanup_json["removed_session_dir"].as_bool() == Some(true));
    ensure!(!session_dir.exists());
    Ok(())
}

#[test]
fn session_cleanup_cli_removes_partial_or_corrupt_session_dir() -> anyhow::Result<()> {
    let repo_root = tempdir()?;
    let partial_date = Date::from_calendar_date(2026, Month::March, 9)?;
    let partial_session_dir = session_paths(repo_root.path(), partial_date).session_dir;
    let partial_session_dir_arg = partial_session_dir.to_string_lossy().into_owned();
    fs::create_dir_all(&partial_session_dir)?;
    fs::write(partial_session_dir.join("stale.tmp"), "stale")?;

    let partial_cleanup = run_cmd(&[
        "--json",
        "session",
        "cleanup",
        "--session-dir",
        &partial_session_dir_arg,
    ])?;
    ensure!(partial_cleanup.status.success());
    let partial_cleanup_json: Value = serde_json::from_slice(&partial_cleanup.stdout)?;
    ensure!(partial_cleanup_json["removed_session_dir"].as_bool() == Some(true));
    ensure!(!partial_session_dir.exists());

    let corrupt_date = Date::from_calendar_date(2026, Month::March, 10)?;
    let corrupt_session_dir = session_paths(repo_root.path(), corrupt_date).session_dir;
    let corrupt_session_dir_arg = corrupt_session_dir.to_string_lossy().into_owned();
    fs::create_dir_all(&corrupt_session_dir)?;
    fs::write(corrupt_session_dir.join("_session.json"), "{not valid json")?;

    let corrupt_cleanup = run_cmd(&[
        "--json",
        "session",
        "cleanup",
        "--session-dir",
        &corrupt_session_dir_arg,
    ])?;
    ensure!(corrupt_cleanup.status.success());
    let corrupt_cleanup_json: Value = serde_json::from_slice(&corrupt_cleanup.stdout)?;
    ensure!(corrupt_cleanup_json["removed_session_dir"].as_bool() == Some(true));
    ensure!(!corrupt_session_dir.exists());
    Ok(())
}

#[test]
fn reviewer_finalize_requires_spawned_routed_workers() -> anyhow::Result<()> {
    let repo_root = tempdir()?;
    let date = Date::from_calendar_date(2026, Month::March, 8)?;
    let session_dir = session_paths(repo_root.path(), date).session_dir;
    let session_dir_arg = session_dir.to_string_lossy().into_owned();

    let route = run_cmd(&[
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
        "8",
        "--orchestrator-read-budget-lines",
        "120",
        "--orchestrator-read-budget-snippets",
        "12",
        "--changed-file",
        "src/lib.rs",
        "--persist",
    ])?;
    ensure!(route.status.success());

    let register = run_cmd(&[
        "--json",
        "reviewer",
        "register",
        "--session-dir",
        &session_dir_arg,
        "--target-ref",
        "refs/heads/main",
        "--reviewer-id",
        "root0006",
    ])?;
    ensure!(register.status.success());
    let register_json: Value = serde_json::from_slice(&register.stdout)?;
    let session_id = register_json
        .get("session_id")
        .and_then(Value::as_str)
        .ok_or_else(|| anyhow::anyhow!("missing session id"))?;

    let parent_file = session_dir.join("parent-review.toml");
    fs::write(
        &parent_file,
        parent_review_doc(session_id)?.to_toml_string()?,
    )?;

    let finalize = run_cmd(&[
        "reviewer",
        "finalize",
        "--session-dir",
        &session_dir_arg,
        "--reviewer-id",
        "root0006",
        "--artifact-file",
        &parent_file.to_string_lossy(),
    ])?;
    ensure!(!finalize.status.success());
    let stderr = String::from_utf8_lossy(&finalize.stderr);
    ensure!(stderr
        .contains("cannot finalize parent_review before every required routed worker is spawned"));
    ensure!(stderr.contains("language-detector"));
    Ok(())
}

#[test]
fn reviewer_register_default_role_dispatches_end_to_end() -> anyhow::Result<()> {
    let repo_root = tempdir()?;
    let date = Date::from_calendar_date(2026, Month::March, 8)?;
    let session_dir = session_paths(repo_root.path(), date).session_dir;
    let session_dir_arg = session_dir.to_string_lossy().into_owned();

    let register = run_cmd(&[
        "--json",
        "reviewer",
        "register",
        "--session-dir",
        &session_dir_arg,
        "--target-ref",
        "refs/heads/main",
        "--reviewer-id",
        "root0016",
    ])?;
    ensure!(register.status.success());
    let register_json: Value = serde_json::from_slice(&register.stdout)?;
    ensure!(register_json["reviewer_id"].as_str() == Some("root0016"));

    let dispatch = run_cmd(&[
        "--json",
        "protocol",
        "dispatch",
        "--session-dir",
        &session_dir_arg,
        "--role",
        "orchestrator-root",
        "--reviewer-id",
        "root0016",
        "--view",
        "checklist",
    ])?;
    ensure!(dispatch.status.success());
    let dispatch_json: Value = serde_json::from_slice(&dispatch.stdout)?;
    ensure!(dispatch_json["role"].as_str() == Some("orchestrator-root"));
    ensure!(dispatch_json["reviewer_id"].as_str() == Some("root0016"));
    ensure!(dispatch_json["role_kind"].as_str() == Some("helper"));
    ensure!(dispatch_json["agent_dir"].as_str().is_some());
    ensure!(dispatch_json["content"]
        .as_str()
        .is_some_and(|content| content.contains("worker orchestrator-root")));
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
        role: None,
        role_kind: None,
    })?;

    let artifact = ArtifactDocument::ApplicationResult(ApplicationResultArtifact {
        header: ArtifactHeader::new(
            ArtifactKind::ApplicationResult,
            "abc123fff456".to_string(),
            register.session_id.clone(),
            "refs/heads/main".to_string(),
            ProducerKind::ApplicatorWorker,
            "2026-03-08T00:00:00Z".to_string(),
            ConfidenceLabel::High,
            90,
            vec![PolicyRef {
                category: PolicyCategory::Mode,
                id: "applicator".to_string(),
                version: "2026.03.08".to_string(),
                view: PolicyView::Checklist,
            }],
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
    let application_file = session_dir.join("application_result.toml");
    fs::write(&application_file, artifact.to_toml_string()?)?;
    finalize_application(ApplicatorArtifactParams {
        session: locator.clone(),
        artifact_file: application_file,
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
