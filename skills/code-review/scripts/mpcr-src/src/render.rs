//! Deterministic markdown rendering from machine artifacts.

use crate::artifacts::{
    ApplicationResultArtifact, ArtifactDocument, ArtifactHeader, ChildFindingsArtifact,
    ConvergenceStateArtifact, CoverageSummary, DefendedCheckRecord, FindingRecord,
    ParentReviewArtifact, ResidualRiskRecord, RiskSurfaceRecord, RouteDecisionArtifact,
    RouteRevisionArtifact, SurfaceMapArtifact, VerificationItemRecord, VerificationResultArtifact,
};

fn push_header(markdown: &mut String, title: &str, header: &ArtifactHeader) {
    markdown.push_str(&format!("# {title}\n\n"));
    markdown.push_str(&format!(
        "- Artifact: `{}` (`{}`)\n- Session: `{}`\n- Target ref: `{}`\n- Producer: `{}`\n- Policy version: `{}`\n- Created at: `{}`\n\n",
        header.artifact_id,
        header.artifact_kind,
        header.session_id,
        header.target_ref,
        toml::Value::try_from(header.producer_kind)
            .map_or_else(|_| "unknown".to_string(), |value| value.to_string().trim_matches('"').to_string()),
        header.policy_version,
        header.created_at
    ));
}

fn push_string_list(markdown: &mut String, heading: &str, items: &[String], empty_label: &str) {
    markdown.push_str(&format!("## {heading}\n\n"));
    if items.is_empty() {
        markdown.push_str(&format!("- {empty_label}\n\n"));
        return;
    }
    for item in items {
        markdown.push_str(&format!("- {item}\n"));
    }
    markdown.push('\n');
}

fn push_surface_summary(markdown: &mut String, heading: &str, surfaces: &[RiskSurfaceRecord]) {
    markdown.push_str(&format!("## {heading}\n\n"));
    if surfaces.is_empty() {
        markdown.push_str("- none\n\n");
        return;
    }
    for surface in surfaces {
        markdown.push_str(&format!(
            "- `{}` weight {}: {}\n",
            toml::Value::try_from(surface.surface_id).map_or_else(
                |_| "unknown".to_string(),
                |value| value.to_string().trim_matches('"').to_string()
            ),
            surface.weight,
            surface.reason
        ));
    }
    markdown.push('\n');
}

fn push_findings(markdown: &mut String, heading: &str, findings: &[FindingRecord]) {
    markdown.push_str(&format!("## {heading}\n\n"));
    if findings.is_empty() {
        markdown.push_str("- none\n\n");
        return;
    }
    for finding in findings {
        markdown.push_str(&format!(
            "### {} [{}]\n\n- Severity: `{}`\n- Claim: {}\n- Scenario: {}\n- Evidence: {}\n- Recommendation: {}\n- Verification: {}\n- Anchors: {}\n- Fingerprint: `{}`\n\n",
            finding.title,
            finding.finding_id,
            toml::Value::try_from(finding.severity)
                .map_or_else(|_| "unknown".to_string(), |value| value.to_string().trim_matches('"').to_string()),
            finding.claim,
            finding.scenario,
            finding.evidence,
            finding.recommendation,
            finding.verification,
            finding.anchors.join(", "),
            finding.fingerprint
        ));
    }
}

fn push_defended_checks(markdown: &mut String, heading: &str, checks: &[DefendedCheckRecord]) {
    markdown.push_str(&format!("## {heading}\n\n"));
    if checks.is_empty() {
        markdown.push_str("- none\n\n");
        return;
    }
    for check in checks {
        markdown.push_str(&format!(
            "- `{}` {}: {} | counterexample: {}\n",
            check.check_id, check.method, check.claim, check.attempted_counterexample
        ));
    }
    markdown.push('\n');
}

fn push_residual_risks(markdown: &mut String, risks: &[ResidualRiskRecord]) {
    markdown.push_str("## Residual Risks\n\n");
    if risks.is_empty() {
        markdown.push_str("- none\n\n");
        return;
    }
    for risk in risks {
        markdown.push_str(&format!(
            "- `{}`: {} | impact: {} | next action: {}\n",
            risk.risk_id, risk.summary, risk.impact, risk.next_action
        ));
    }
    markdown.push('\n');
}

fn push_coverage(markdown: &mut String, coverage: &CoverageSummary) {
    markdown.push_str("## Coverage Summary\n\n");
    push_string_list(markdown, "Changed Files", &coverage.changed_files, "none");
    markdown.push_str("## Surfaces Covered\n\n");
    if coverage.surfaces_covered.is_empty() {
        markdown.push_str("- none\n\n");
    } else {
        for surface in &coverage.surfaces_covered {
            markdown.push_str(&format!(
                "- `{}`\n",
                toml::Value::try_from(*surface).map_or_else(
                    |_| "unknown".to_string(),
                    |value| value.to_string().trim_matches('"').to_string()
                )
            ));
        }
        markdown.push('\n');
    }
    markdown.push_str("## Modules Loaded\n\n");
    if coverage.modules_loaded.is_empty() {
        markdown.push_str("- none\n\n");
    } else {
        for module_id in &coverage.modules_loaded {
            markdown.push_str(&format!(
                "- `{}`\n",
                toml::Value::try_from(*module_id).map_or_else(
                    |_| "unknown".to_string(),
                    |value| value.to_string().trim_matches('"').to_string()
                )
            ));
        }
        markdown.push('\n');
    }
    push_string_list(markdown, "Tests Run", &coverage.tests_run, "none");
    markdown.push_str("## Test Gaps\n\n");
    match &coverage.tests_not_run_reason {
        Some(reason) => markdown.push_str(&format!("- {reason}\n\n")),
        None => markdown.push_str("- none\n\n"),
    }
    push_string_list(markdown, "Limitations", &coverage.limitations, "none");
}

fn render_parent_review(artifact: &ParentReviewArtifact) -> String {
    let mut markdown = String::new();
    push_header(&mut markdown, "Parent Review", &artifact.header);
    markdown.push_str(&format!(
        "## Verdict\n\n- Final verdict: `{}`\n\n",
        toml::Value::try_from(artifact.final_verdict).map_or_else(
            |_| "unknown".to_string(),
            |value| value.to_string().trim_matches('"').to_string()
        )
    ));
    markdown.push_str(&format!(
        "## Ship Readiness\n\n- Verdict: `{}`\n- Blocking items: {}\n- Required now count: {}\n- Follow-up count: {}\n\n",
        toml::Value::try_from(artifact.ship_readiness.verdict)
            .map_or_else(|_| "unknown".to_string(), |value| value.to_string().trim_matches('"').to_string()),
        if artifact.ship_readiness.blocking_items.is_empty() {
            "none".to_string()
        } else {
            artifact.ship_readiness.blocking_items.join(", ")
        },
        artifact.ship_readiness.required_now_count,
        artifact.ship_readiness.follow_up_count
    ));
    push_findings(&mut markdown, "Required Now", &artifact.required_now);
    push_findings(&mut markdown, "Follow Up", &artifact.follow_up);
    push_defended_checks(
        &mut markdown,
        "Defended Summary",
        &artifact.defended_summary,
    );
    push_residual_risks(&mut markdown, &artifact.residual_risks);
    push_coverage(&mut markdown, &artifact.coverage_summary);
    markdown
}

fn render_application_result(artifact: &ApplicationResultArtifact) -> String {
    let mut markdown = String::new();
    push_header(&mut markdown, "Application Result", &artifact.header);
    markdown.push_str("## Dispositions\n\n");
    if artifact.dispositions.is_empty() {
        markdown.push_str("- none\n\n");
    } else {
        for disposition in &artifact.dispositions {
            markdown.push_str(&format!(
                "- `{}` => `{}`: {}\n",
                disposition.finding_id,
                toml::Value::try_from(disposition.disposition).map_or_else(
                    |_| "unknown".to_string(),
                    |value| value.to_string().trim_matches('"').to_string()
                ),
                disposition.detail
            ));
        }
        markdown.push('\n');
    }
    push_string_list(
        &mut markdown,
        "Modified Files",
        &artifact.modified_files,
        "none",
    );
    push_string_list(
        &mut markdown,
        "Verification Needed",
        &artifact.verification_needed,
        "none",
    );
    markdown.push_str("## Decline Codes\n\n");
    if artifact.decline_codes.is_empty() {
        markdown.push_str("- none\n\n");
    } else {
        for code in &artifact.decline_codes {
            markdown.push_str(&format!(
                "- `{}`\n",
                toml::Value::try_from(*code).map_or_else(
                    |_| "unknown".to_string(),
                    |value| value.to_string().trim_matches('"').to_string()
                )
            ));
        }
        markdown.push('\n');
    }
    markdown
}

fn push_verification_items(markdown: &mut String, heading: &str, items: &[VerificationItemRecord]) {
    markdown.push_str(&format!("## {heading}\n\n"));
    if items.is_empty() {
        markdown.push_str("- none\n\n");
        return;
    }
    for item in items {
        markdown.push_str(&format!(
            "- `{}` => `{}`: {}\n",
            item.finding_id,
            toml::Value::try_from(item.status).map_or_else(
                |_| "unknown".to_string(),
                |value| value.to_string().trim_matches('"').to_string()
            ),
            item.notes
        ));
    }
    markdown.push('\n');
}

fn render_verification_result(artifact: &VerificationResultArtifact) -> String {
    let mut markdown = String::new();
    push_header(&mut markdown, "Verification Result", &artifact.header);
    push_verification_items(&mut markdown, "Verified Items", &artifact.verified_items);
    push_verification_items(&mut markdown, "Failed Items", &artifact.failed_items);
    push_verification_items(&mut markdown, "Partial Items", &artifact.partial_items);
    push_residual_risks(&mut markdown, &artifact.residual_risks);
    markdown
}

fn render_route_decision(artifact: &RouteDecisionArtifact) -> String {
    let mut markdown = String::new();
    push_header(&mut markdown, "Route Decision", &artifact.header);
    markdown.push_str(&format!(
        "## Route\n\n- Mode: `{}`\n- Architecture: `{}`\n- Rigor: `{}`\n- Planned workers: {}\n- Max workers: {}\n\n",
        toml::Value::try_from(artifact.mode)
            .map_or_else(|_| "unknown".to_string(), |value| value.to_string().trim_matches('"').to_string()),
        toml::Value::try_from(artifact.execution_architecture)
            .map_or_else(|_| "unknown".to_string(), |value| value.to_string().trim_matches('"').to_string()),
        toml::Value::try_from(artifact.rigor_level)
            .map_or_else(|_| "unknown".to_string(), |value| value.to_string().trim_matches('"').to_string()),
        artifact.resource_budget.planned_worker_count,
        artifact.resource_budget.max_worker_count
    ));
    push_surface_summary(&mut markdown, "Risk Surfaces", &artifact.risk_surfaces);
    push_string_list(
        &mut markdown,
        "Stop Conditions",
        &artifact.stop_conditions,
        "none",
    );
    markdown
}

fn render_surface_map(artifact: &SurfaceMapArtifact) -> String {
    let mut markdown = String::new();
    push_header(&mut markdown, "Surface Map", &artifact.header);
    push_string_list(
        &mut markdown,
        "Changed Files",
        &artifact.changed_files,
        "none",
    );
    push_string_list(
        &mut markdown,
        "Public Interfaces",
        &artifact.public_interfaces,
        "none",
    );
    push_string_list(
        &mut markdown,
        "Behavior-Facing Artifacts",
        &artifact.behavior_facing_artifacts,
        "none",
    );
    push_surface_summary(&mut markdown, "Risk Surfaces", &artifact.risk_surfaces);
    markdown.push_str(&format!(
        "## Staleness\n\n- Required: `{}`\n\n",
        artifact.staleness_required
    ));
    markdown
}

fn render_child_findings(artifact: &ChildFindingsArtifact) -> String {
    let mut markdown = String::new();
    push_header(&mut markdown, "Child Findings", &artifact.header);
    push_findings(&mut markdown, "Findings", &artifact.findings);
    push_defended_checks(&mut markdown, "Defended Checks", &artifact.defended_checks);
    push_residual_risks(&mut markdown, &artifact.residual_risks);
    push_string_list(
        &mut markdown,
        "Route Revision Refs",
        &artifact.route_revision_refs,
        "none",
    );
    markdown
}

fn render_convergence_state(artifact: &ConvergenceStateArtifact) -> String {
    let mut markdown = String::new();
    push_header(&mut markdown, "Convergence State", &artifact.header);
    markdown.push_str(&format!(
        "## Convergence\n\n- Cycle index: {}\n- Severity floor: `{}`\n- Behavior staleness reopens: `{}`\n- Terminal cleanup allowed: `{}`\n- Stop condition: {}\n\n",
        artifact.cycle_index,
        toml::Value::try_from(artifact.reopen_threshold.severity_floor)
            .map_or_else(|_| "unknown".to_string(), |value| value.to_string().trim_matches('"').to_string()),
        artifact.reopen_threshold.behavior_staleness_reopens,
        artifact.terminal_cleanup_allowed,
        artifact.stop_condition
    ));
    markdown.push_str("## Reopen Triggers\n\n");
    if artifact.reopen_triggers.is_empty() {
        markdown.push_str("- none\n\n");
    } else {
        for trigger in &artifact.reopen_triggers {
            markdown.push_str(&format!(
                "- `{}` => `{}`\n",
                trigger.reference_id,
                toml::Value::try_from(trigger.reopen_reason_code).map_or_else(
                    |_| "unknown".to_string(),
                    |value| value.to_string().trim_matches('"').to_string()
                )
            ));
        }
        markdown.push('\n');
    }
    push_string_list(
        &mut markdown,
        "Focus Files",
        &artifact.next_route_inputs.focus_files,
        "none",
    );
    markdown
}

fn render_route_revision(artifact: &RouteRevisionArtifact) -> String {
    let mut markdown = String::new();
    push_header(&mut markdown, "Route Revision", &artifact.header);
    push_surface_summary(
        &mut markdown,
        "Discovered Surfaces",
        &artifact.discovered_surfaces,
    );
    markdown.push_str(&format!(
        "## Revision\n\n- Reason: {}\n- Source artifact: `{}`\n\n",
        artifact.reason_code, artifact.source_artifact_id
    ));
    markdown
}

/// Render a canonical artifact into deterministic markdown.
///
/// # Errors
/// Returns an error if a supported artifact cannot be rendered.
pub fn render_artifact_markdown(artifact: &ArtifactDocument) -> anyhow::Result<String> {
    let markdown = match artifact {
        ArtifactDocument::RouteDecision(artifact) => render_route_decision(artifact),
        ArtifactDocument::SurfaceMap(artifact) => render_surface_map(artifact),
        ArtifactDocument::ChildFindings(artifact) => render_child_findings(artifact),
        ArtifactDocument::ParentReview(artifact) => render_parent_review(artifact),
        ArtifactDocument::ApplicationResult(artifact) => render_application_result(artifact),
        ArtifactDocument::VerificationResult(artifact) => render_verification_result(artifact),
        ArtifactDocument::ConvergenceState(artifact) => render_convergence_state(artifact),
        ArtifactDocument::RouteRevision(artifact) => render_route_revision(artifact),
    };
    Ok(markdown)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::artifacts::{
        ArtifactHeader, ArtifactKind, ConfidenceLabel, PolicyCategory, PolicyRef, PolicyView,
        ProducerKind, ReviewVerdict, ShipReadinessSummary, ShipReadinessVerdict,
    };
    use anyhow::ensure;

    fn header(kind: ArtifactKind) -> anyhow::Result<ArtifactHeader> {
        ArtifactHeader::new(
            kind,
            "abc123def456".to_string(),
            "sess0001".to_string(),
            "refs/heads/main".to_string(),
            ProducerKind::Renderer,
            "2026-03-08T00:00:00Z".to_string(),
            ConfidenceLabel::High,
            90,
            vec![PolicyRef {
                category: PolicyCategory::Mode,
                id: "reviewer".to_string(),
                version: "2026.03.08".to_string(),
                view: PolicyView::Checklist,
            }],
        )
    }

    #[test]
    fn parent_review_render_is_deterministic() -> anyhow::Result<()> {
        let artifact = ArtifactDocument::ParentReview(ParentReviewArtifact {
            header: header(ArtifactKind::ParentReview)?,
            source_artifact_ids: vec!["feed00cafe12".to_string()],
            final_verdict: ReviewVerdict::Approve,
            ship_readiness: ShipReadinessSummary {
                verdict: ShipReadinessVerdict::Ship,
                axes: vec!["correctness".to_string()],
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
                surfaces_covered: Vec::new(),
                modules_loaded: Vec::new(),
                tests_run: Vec::new(),
                tests_not_run_reason: None,
                limitations: Vec::new(),
            },
        });
        let rendered_once = render_artifact_markdown(&artifact)?;
        let rendered_twice = render_artifact_markdown(&artifact)?;
        ensure!(rendered_once == rendered_twice);
        ensure!(rendered_once.contains("## Verdict"));
        ensure!(rendered_once.contains("## Coverage Summary"));
        Ok(())
    }
}
