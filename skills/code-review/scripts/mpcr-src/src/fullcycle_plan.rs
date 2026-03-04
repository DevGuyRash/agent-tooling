#![allow(clippy::module_name_repetitions)]
#![allow(missing_docs)]

use crate::report_validation::{extract_parent_report_telemetry, ParentReportTelemetry};
use crate::session::{
    load_session, upsert_session_extra_json, InitiatorStatus, ReviewEntry, ReviewerStatus,
    SessionLocator, UpsertSessionExtraJsonParams,
};
use clap::ValueEnum;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::collections::BTreeSet;
use std::path::PathBuf;
use time::OffsetDateTime;

const FULLCYCLE_STATE_KEY: &str = "fullcycle_state";
const STALE_TOKENS: &[&str] = &[
    "stale",
    "drift",
    "operator guidance",
    "docs mismatch",
    "documentation mismatch",
];

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, ValueEnum)]
#[serde(rename_all = "snake_case")]
pub enum DetailLevel {
    Auto,
    Compact,
    Standard,
    Full,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub struct FullcycleState {
    pub schema_version: String,
    pub target_ref: String,
    pub session_id: Option<String>,
    pub cycle_index: usize,
    pub cycle_phase: String,
    pub continue_required: bool,
    pub stop_reason: Option<String>,
    pub no_progress_streak: u64,
    pub baseline_workers: u8,
    pub worker_ceiling: u8,
    pub recommended_workers: u8,
    pub probe_stage: String,
    pub net_new_actionable: usize,
    pub net_new_staleness_actionable: usize,
    pub dedup_fingerprint_count: usize,
    pub malformed_packets: u64,
    pub retry_count: u64,
    pub child_error_count: usize,
    pub artifact_format_policy: String,
    pub updated_at: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct FullcyclePlanOutput {
    pub mode: &'static str,
    pub target_ref: String,
    pub session_dir: String,
    pub session_id: Option<String>,
    pub cycle_index: usize,
    pub state: String,
    pub continue_required: bool,
    pub stop_reason: Option<String>,
    pub baseline_workers: u8,
    pub worker_ceiling: u8,
    pub recommended_workers: u8,
    pub probe_stage: String,
    pub probe_rationale: String,
    pub stale_checks_required: Vec<String>,
    pub net_new_actionable: usize,
    pub net_new_staleness_actionable: usize,
    pub dedup_fingerprint_count: usize,
    pub retry_count: u64,
    pub child_error_count: usize,
    pub no_progress_streak: u64,
    pub artifact_format_policy: &'static str,
    pub capability_warnings: Vec<String>,
    pub next_commands: Vec<String>,
    pub notes: Vec<String>,
}

#[derive(Debug, Clone)]
pub struct BuildParams {
    pub session: SessionLocator,
    pub target_ref: String,
    pub requested_session_id: Option<String>,
    pub worker_budget_override: Option<u8>,
    pub detail: DetailLevel,
    pub now: OffsetDateTime,
    pub loop_mode: bool,
}

fn report_path(session_dir: &SessionLocator, repo_root: &str, report_file: &str) -> PathBuf {
    let repo_path = PathBuf::from(repo_root);
    let rel = PathBuf::from(report_file);
    if rel.is_absolute() {
        rel
    } else if rel.components().count() > 1 {
        repo_path.join(rel)
    } else {
        session_dir.session_dir().join(rel)
    }
}

fn normalized_fingerprint(severity: &str, anchor: &str, claim: &str) -> String {
    let normalized_claim = claim
        .to_ascii_lowercase()
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ");
    format!("{severity}|{anchor}|{normalized_claim}")
}

fn stale_like(text: &str) -> bool {
    let lower = text.to_ascii_lowercase();
    STALE_TOKENS.iter().any(|token| lower.contains(token))
}

fn find_latest_parent<'a>(
    session: &'a crate::session::SessionFile,
    target_ref: &str,
    requested_session_id: Option<&str>,
) -> anyhow::Result<Vec<&'a ReviewEntry>> {
    let mut parents: Vec<&ReviewEntry> = session
        .reviews
        .iter()
        .filter(|entry| {
            entry.parent_id.is_none()
                && entry.target_ref == target_ref
                && requested_session_id.is_none_or(|sid| entry.session_id == sid)
        })
        .collect();
    parents.sort_by(|a, b| a.started_at.cmp(&b.started_at));
    if requested_session_id.is_none() {
        let mut unique_sessions = parents
            .iter()
            .map(|entry| entry.session_id.as_str())
            .collect::<BTreeSet<_>>();
        if unique_sessions.len() > 1 {
            let available = unique_sessions
                .iter()
                .copied()
                .collect::<Vec<_>>()
                .join(", ");
            return Err(anyhow::anyhow!(
                "ambiguous sessions for target_ref `{target_ref}`; pass --session-id (available: {available})"
            ));
        }
        unique_sessions.clear();
    }
    Ok(parents)
}

fn worker_ceiling() -> u8 {
    let parsed = std::env::var("MPCR_MAX_WORKERS")
        .ok()
        .and_then(|raw| raw.parse::<u8>().ok())
        .unwrap_or(8);
    if parsed >= 8 {
        8
    } else if parsed >= 6 {
        6
    } else {
        4
    }
}

fn detail_auto(
    requested: DetailLevel,
    continue_required: bool,
    recommended_workers: u8,
    retry_count: u64,
    stale_actionable: usize,
    no_progress_streak: u64,
) -> DetailLevel {
    if requested != DetailLevel::Auto {
        return requested;
    }
    if no_progress_streak >= 2 || retry_count > 0 || stale_actionable > 0 {
        return DetailLevel::Full;
    }
    if continue_required || recommended_workers > 4 {
        return DetailLevel::Standard;
    }
    DetailLevel::Compact
}

fn load_previous_state(session: &crate::session::SessionFile) -> Option<FullcycleState> {
    let raw = session.extra.get(FULLCYCLE_STATE_KEY)?;
    serde_json::from_value(raw.clone()).ok()
}

fn scoped_previous_state(
    session: &crate::session::SessionFile,
    target_ref: &str,
    session_id: Option<&str>,
) -> Option<FullcycleState> {
    let state = load_previous_state(session)?;
    if state.target_ref != target_ref {
        return None;
    }
    if state.session_id.as_deref() != session_id {
        return None;
    }
    Some(state)
}

fn build_next_commands(
    target_ref: &str,
    session_id: Option<&str>,
    continue_required: bool,
    phase: &str,
) -> Vec<String> {
    let sid_flag = session_id
        .map(|sid| format!(" --session-id {sid}"))
        .unwrap_or_default();
    if !continue_required {
        return vec![format!(
            "mpcr session reports closed --target-ref {target_ref}{sid_flag} --include-report-contents --json"
        )];
    }
    match phase {
        "bootstrap_review" => vec![
            format!("mpcr reviewer register --target-ref {target_ref}{sid_flag} --print-env"),
            "mpcr protocol orchestrator".to_string(),
            "mpcr protocol fullcycle".to_string(),
        ],
        "application" => vec![
            "mpcr protocol applicator --phase INGESTION".to_string(),
            format!(
                "mpcr applicator set-status --reviewer-id <ID8> --session-id <ID8> --initiator-status APPLYING"
            ),
            format!(
                "mpcr applicator set-status --reviewer-id <ID8> --session-id <ID8> --initiator-status APPLIED"
            ),
        ],
        "scoped_rereview" => vec![
            "mpcr protocol convergence-planning".to_string(),
            format!("mpcr reviewer register --target-ref {target_ref}{sid_flag} --print-env"),
            "mpcr protocol reviewer --phase INGESTION".to_string(),
        ],
        _ => vec!["mpcr protocol fullcycle".to_string()],
    }
}

fn telemetry_from_report(
    session_locator: &SessionLocator,
    session: &crate::session::SessionFile,
    entry: &ReviewEntry,
) -> Option<ParentReportTelemetry> {
    let report_file = entry.report_file.as_deref()?;
    let report = std::fs::read_to_string(report_path(
        session_locator,
        &session.repo_root,
        report_file,
    ))
    .ok();
    let report = report?;
    extract_parent_report_telemetry(&report).ok()
}

/// Build the next deterministic full-cycle plan and persisted state snapshot.
///
/// # Errors
/// Returns an error if the session cannot be loaded or parent lineage cannot be resolved.
#[allow(clippy::too_many_lines)]
pub fn build_plan(params: &BuildParams) -> anyhow::Result<(FullcyclePlanOutput, FullcycleState)> {
    let session = load_session(&params.session)?;
    let parents = find_latest_parent(
        &session,
        &params.target_ref,
        params.requested_session_id.as_deref(),
    )?;
    let parent_session_id = parents.last().map(|entry| entry.session_id.clone());
    let effective_session_id = parent_session_id
        .as_deref()
        .or(params.requested_session_id.as_deref());
    let resolved_session_id = effective_session_id.map(str::to_owned);
    let previous = scoped_previous_state(&session, &params.target_ref, effective_session_id);
    let finished_parents: Vec<&ReviewEntry> = parents
        .iter()
        .copied()
        .filter(|entry| entry.status == ReviewerStatus::Finished)
        .collect();
    let cycle_index = finished_parents.len();

    let latest_finished = finished_parents.last().copied();
    let prev_finished = if finished_parents.len() > 1 {
        finished_parents.get(finished_parents.len() - 2).copied()
    } else {
        None
    };

    let latest_telemetry =
        latest_finished.and_then(|entry| telemetry_from_report(&params.session, &session, entry));
    let prev_telemetry =
        prev_finished.and_then(|entry| telemetry_from_report(&params.session, &session, entry));

    let mut latest_fingerprints = BTreeSet::new();
    let mut latest_actionable_fingerprints = BTreeSet::new();
    let mut previous_actionable_fingerprints = BTreeSet::new();
    let mut stale_actionable = 0usize;
    let retry_count = latest_telemetry.as_ref().map_or(0, |t| t.retry_count);
    let malformed_packets = latest_telemetry.as_ref().map_or(0, |t| t.packets_rejected);

    if let Some(ref telemetry) = latest_telemetry {
        for finding in &telemetry.merged_findings {
            let fp = normalized_fingerprint(&finding.severity, &finding.anchor, &finding.claim);
            latest_fingerprints.insert(fp.clone());
            if finding.is_actionable {
                latest_actionable_fingerprints.insert(fp);
            }
            if finding.is_actionable && stale_like(&finding.claim) {
                stale_actionable += 1;
            }
        }
        stale_actionable += telemetry
            .residual_risks
            .iter()
            .filter(|area| stale_like(area))
            .count();
    }
    if let Some(ref telemetry) = prev_telemetry {
        for finding in &telemetry.merged_findings {
            let fp = normalized_fingerprint(&finding.severity, &finding.anchor, &finding.claim);
            if finding.is_actionable {
                previous_actionable_fingerprints.insert(fp);
            }
        }
    }

    let net_new_actionable = latest_actionable_fingerprints
        .difference(&previous_actionable_fingerprints)
        .count();
    let dedup_fingerprint_count = latest_fingerprints.len();

    let child_error_count = parents.last().map_or(0, |parent| {
        session
            .reviews
            .iter()
            .filter(|entry| {
                entry.parent_id.as_deref() == Some(parent.reviewer_id.as_str())
                    && entry.session_id == parent.session_id
                    && entry.status == ReviewerStatus::Error
            })
            .count()
    });

    let (continue_required, phase, stop_reason) = if parents.is_empty() {
        (true, "bootstrap_review".to_string(), None)
    } else if parents
        .last()
        .is_some_and(|entry| !entry.status.is_terminal())
    {
        (true, "wait_review_completion".to_string(), None)
    } else if let Some(latest) = latest_finished {
        let actionable = latest.counts.blocker + latest.counts.major;
        if actionable == 0 && stale_actionable == 0 {
            (
                false,
                "converged".to_string(),
                Some("converged".to_string()),
            )
        } else if latest.initiator_status != InitiatorStatus::Applied {
            (true, "application".to_string(), None)
        } else {
            (true, "scoped_rereview".to_string(), None)
        }
    } else {
        (true, "bootstrap_review".to_string(), None)
    };

    let ceiling = worker_ceiling();
    let recommended_workers = params.worker_budget_override.map_or(
        if child_error_count == 0
            && retry_count == 0
            && continue_required
            && cycle_index >= 2
            && ceiling >= 8
        {
            8
        } else if child_error_count == 0
            && retry_count == 0
            && continue_required
            && cycle_index >= 1
            && ceiling >= 6
        {
            6
        } else {
            4
        },
        |override_budget| override_budget.min(ceiling).max(4),
    );
    let probe_stage = if recommended_workers >= 8 {
        "probe_8"
    } else if recommended_workers >= 6 {
        "probe_6"
    } else {
        "baseline"
    };
    let probe_rationale = if params.worker_budget_override.is_some() {
        "worker override applied; capped by runtime ceiling".to_string()
    } else if recommended_workers == 4 {
        "baseline 4 workers is default safe operating point".to_string()
    } else {
        "health signals are stable; probing upward is cautionary but encouraged".to_string()
    };

    let no_progress_streak = {
        let prev = previous
            .as_ref()
            .map_or(0, |state| state.no_progress_streak);
        if continue_required && net_new_actionable == 0 && stale_actionable == 0 {
            prev.saturating_add(1)
        } else {
            0
        }
    };

    let selected_detail = detail_auto(
        params.detail,
        continue_required,
        recommended_workers,
        retry_count,
        stale_actionable,
        no_progress_streak,
    );
    let stale_checks_required = vec![
        "cycle_start".to_string(),
        "post_apply".to_string(),
        "scoped_rereview".to_string(),
        "convergence_gate".to_string(),
    ];

    let mut notes = vec![];
    let mut capability_warnings = vec![];
    if params.loop_mode {
        notes.push("loop-plan enforces recursive convergence; no hard cycle cap.".to_string());
    }
    if continue_required && net_new_actionable == 0 && stale_actionable == 0 {
        capability_warnings.push(
            "no net-new actionable findings detected this cycle; monitor no-progress streak"
                .to_string(),
        );
    }
    if selected_detail == DetailLevel::Full {
        notes.push(
            "detail escalated to full due instability or convergence risk signals.".to_string(),
        );
    }

    let plan = FullcyclePlanOutput {
        mode: if params.loop_mode {
            "read_only_loop_planner"
        } else {
            "read_only_planner"
        },
        target_ref: params.target_ref.clone(),
        session_dir: params.session.session_dir().to_string_lossy().to_string(),
        session_id: resolved_session_id.clone(),
        cycle_index,
        state: phase.clone(),
        continue_required,
        stop_reason: stop_reason.clone(),
        baseline_workers: 4,
        worker_ceiling: ceiling,
        recommended_workers,
        probe_stage: probe_stage.to_string(),
        probe_rationale,
        stale_checks_required,
        net_new_actionable,
        net_new_staleness_actionable: stale_actionable,
        dedup_fingerprint_count,
        retry_count,
        child_error_count,
        no_progress_streak,
        artifact_format_policy: "proof_toml_first_cli_json_ok",
        capability_warnings,
        next_commands: build_next_commands(
            &params.target_ref,
            resolved_session_id.as_deref(),
            continue_required,
            &phase,
        ),
        notes,
    };

    let state = FullcycleState {
        schema_version: "fullcycle_state.v1".to_string(),
        target_ref: params.target_ref.clone(),
        session_id: resolved_session_id,
        cycle_index,
        cycle_phase: phase,
        continue_required,
        stop_reason,
        no_progress_streak,
        baseline_workers: 4,
        worker_ceiling: ceiling,
        recommended_workers,
        probe_stage: probe_stage.to_string(),
        net_new_actionable,
        net_new_staleness_actionable: stale_actionable,
        dedup_fingerprint_count,
        malformed_packets,
        retry_count,
        child_error_count,
        artifact_format_policy: "proof_toml_first_cli_json_ok".to_string(),
        updated_at: params
            .now
            .format(&time::format_description::well_known::Rfc3339)?,
    };
    Ok((plan, state))
}

/// Serialize a [`FullcycleState`] into JSON.
///
/// # Errors
/// Returns an error if the state cannot be serialized into JSON.
pub fn state_to_json(state: &FullcycleState) -> anyhow::Result<Value> {
    Ok(serde_json::to_value(state)?)
}

/// Persist full-cycle state into session `extra` metadata.
///
/// # Errors
/// Returns an error if session metadata cannot be updated or serialized.
pub fn persist_state(
    session: SessionLocator,
    lock_owner: String,
    state: &FullcycleState,
) -> anyhow::Result<()> {
    upsert_session_extra_json(&UpsertSessionExtraJsonParams {
        session,
        key: FULLCYCLE_STATE_KEY.to_string(),
        value: state_to_json(state)?,
        lock_owner,
    })
}

/// Load full-cycle state payload from session `extra` metadata.
///
/// # Errors
/// Returns an error if the session artifact cannot be loaded.
pub fn load_state(session: &SessionLocator) -> anyhow::Result<Option<Value>> {
    let session_data = load_session(session)?;
    Ok(session_data.extra.get(FULLCYCLE_STATE_KEY).cloned())
}

#[must_use]
pub fn default_checkpoint_payload(state: &FullcycleState) -> Value {
    json!(state)
}
