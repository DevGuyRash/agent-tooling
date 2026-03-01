//! Deterministic validation for review report artifacts.
//!
//! Reports remain markdown files, but they MUST embed a machine-readable block:
//! a fenced `toml` block is canonical and a fenced `json` block is accepted as
//! a fallback. YAML is intentionally unsupported.

#![allow(clippy::module_name_repetitions)]

use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};

const CHILD_SCHEMA_VERSION: &str = "proof_packet.v2";
const PARENT_SCHEMA_VERSION: &str = "proof_packet.v2";
const CHILD_ARTIFACT_KIND: &str = "child_proof_packet";
const PARENT_ARTIFACT_KIND: &str = "parent_review_report";

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
/// Validation contract to apply to an embedded machine block.
pub enum ReportValidationKind {
    /// Worker proof packet written by `reviewer complete-child`.
    ChildProofPacket,
    /// Parent synthesized review report written by `reviewer finalize`.
    ParentReviewReport,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
/// Wire format extracted from a fenced machine block.
pub enum MachineBlockFormat {
    /// Canonical format.
    Toml,
    /// Compatibility fallback.
    Json,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
/// Severity tallies used for cross-checking report contents.
pub struct SeverityExpectation {
    /// Expected blocker count.
    pub blocker: u64,
    /// Expected major count.
    pub major: u64,
    /// Expected minor count.
    pub minor: u64,
    /// Expected nit count.
    pub nit: u64,
}

#[derive(Debug, Clone, Serialize)]
/// Structured validation issue for JSON output and aggregated errors.
pub struct ReportValidationIssue {
    /// Stable issue code.
    pub code: String,
    /// Human-readable description.
    pub detail: String,
}

#[derive(Debug, Clone, Serialize)]
/// Successful validation summary returned by CLI and used in tests.
pub struct ReportValidationSummary {
    /// Validation contract that passed.
    pub kind: ReportValidationKind,
    /// Embedded machine block format that was used.
    pub format: MachineBlockFormat,
    /// Number of findings validated from the machine block.
    pub findings: usize,
    /// Number of defended proofs validated from the machine block.
    pub defended_proofs: usize,
    /// Number of residual-risk entries in the machine block.
    pub residual_risks: usize,
}

#[derive(Debug)]
struct MachineBlock {
    format: MachineBlockFormat,
    content: String,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct CoverageSection {
    files_reviewed: Vec<String>,
    domains_in_scope: Vec<String>,
    domains_out_of_scope: Vec<String>,
    tests_run: Vec<String>,
    tests_not_run_reason: String,
    limitations: Vec<String>,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct DomainLedgerRow {
    domain: String,
    scope: DomainScope,
    rationale: String,
    theorems: u64,
    disproofs: u64,
    findings: u64,
    defended: u64,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
enum DomainScope {
    InScope,
    OutOfScope,
    Unknown,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct TheoremRecord {
    id: String,
    domain: String,
    claim: String,
    anchors: Vec<String>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
enum DisproofResult {
    Defended,
    Finding,
    Inconclusive,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct DisproofAttemptRecord {
    id: String,
    theorem_id: String,
    scenario: String,
    result: DisproofResult,
    evidence: String,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
enum SeverityLabel {
    Blocker,
    Major,
    Minor,
    Nit,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
enum ConfidenceLabel {
    High,
    Medium,
    Low,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct FindingRecord {
    id: String,
    theorem_id: String,
    domain: String,
    severity: SeverityLabel,
    anchor: String,
    claim: String,
    disproof: String,
    evidence: String,
    recommendation: String,
    verification: String,
    confidence_label: ConfidenceLabel,
    confidence_score: u8,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct DefendedProofRecord {
    theorem_id: String,
    anchor: String,
    disproof_attempt: String,
    outcome: String,
    confidence_label: ConfidenceLabel,
    confidence_score: u8,
    rationale: String,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct ResidualRiskRecord {
    area: String,
    gap: String,
    impact: String,
    next_action: String,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct ChildProofPacketDoc {
    schema_version: String,
    artifact_kind: String,
    role_slug: String,
    role_title: String,
    reviewer_id: String,
    session_id: String,
    target_ref: String,
    overall_verdict: String,
    overall_confidence_label: ConfidenceLabel,
    overall_confidence_score: u8,
    coverage: CoverageSection,
    #[serde(default)]
    domain_ledger: Vec<DomainLedgerRow>,
    #[serde(default)]
    theorems: Vec<TheoremRecord>,
    #[serde(default)]
    disproof_attempts: Vec<DisproofAttemptRecord>,
    #[serde(default)]
    findings: Vec<FindingRecord>,
    #[serde(default)]
    defended_proofs: Vec<DefendedProofRecord>,
    #[serde(default)]
    residual_risks: Vec<ResidualRiskRecord>,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct ParentCounts {
    blocker: u64,
    major: u64,
    minor: u64,
    nit: u64,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct ShipReadinessSection {
    verdict: String,
    confidence_label: ConfidenceLabel,
    confidence_score: u8,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct ShipReadinessAxis {
    axis: String,
    status: String,
    notes: String,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct SourcePacketRecord {
    reviewer_id: String,
    session_id: String,
    artifact_ref: String,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct ParentFindingRecord {
    id: String,
    severity: SeverityLabel,
    anchor: String,
    claim: String,
    disproof: String,
    evidence: String,
    recommendation: String,
    verification: String,
    source_packets: Vec<String>,
    confidence_label: ConfidenceLabel,
    confidence_score: u8,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct DefendedSummaryRecord {
    theorem_id: String,
    source_packets: Vec<String>,
    summary: String,
    confidence_label: ConfidenceLabel,
    confidence_score: u8,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct ValidationSummarySection {
    packets_validated: u64,
    packets_rejected: u64,
    retry_count: u64,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct ParentReviewReportDoc {
    schema_version: String,
    artifact_kind: String,
    reviewer_id: String,
    session_id: String,
    target_ref: String,
    verdict: String,
    counts: ParentCounts,
    ship_readiness: ShipReadinessSection,
    #[serde(default)]
    ship_readiness_axes: Vec<ShipReadinessAxis>,
    #[serde(default)]
    source_packets: Vec<SourcePacketRecord>,
    #[serde(default)]
    merged_findings: Vec<ParentFindingRecord>,
    #[serde(default)]
    defended_summary: Vec<DefendedSummaryRecord>,
    #[serde(default)]
    residual_risks: Vec<ResidualRiskRecord>,
    validation_summary: ValidationSummarySection,
}

#[must_use]
fn issue(code: &str, detail: impl Into<String>) -> ReportValidationIssue {
    ReportValidationIssue {
        code: code.to_string(),
        detail: detail.into(),
    }
}

fn format_issues(issues: &[ReportValidationIssue]) -> anyhow::Error {
    let mut rendered = String::from("report validation failed:");
    for item in issues {
        rendered.push_str("\n- ");
        rendered.push_str(&item.code);
        rendered.push_str(": ");
        rendered.push_str(&item.detail);
    }
    anyhow::anyhow!(rendered)
}

fn is_blank(value: &str) -> bool {
    value.trim().is_empty()
}

fn validate_non_blank(
    issues: &mut Vec<ReportValidationIssue>,
    code: &str,
    label: &str,
    value: &str,
) {
    if is_blank(value) {
        issues.push(issue(code, format!("{label} must be non-empty")));
    }
}

fn validate_anchor(issues: &mut Vec<ReportValidationIssue>, code: &str, label: &str, anchor: &str) {
    let Some((path, line)) = anchor.rsplit_once(':') else {
        issues.push(issue(
            code,
            format!("{label} must use `file:line` format, got `{anchor}`"),
        ));
        return;
    };
    if is_blank(path) {
        issues.push(issue(code, format!("{label} has empty file path in `{anchor}`")));
    }
    if line.parse::<u64>().ok().filter(|value| *value > 0).is_none() {
        issues.push(issue(
            code,
            format!("{label} must reference a positive line number, got `{anchor}`"),
        ));
    }
}

fn validate_confidence(
    issues: &mut Vec<ReportValidationIssue>,
    code: &str,
    label: ConfidenceLabel,
    score: u8,
    context: &str,
) {
    let valid = match label {
        ConfidenceLabel::High => (80..=100).contains(&score),
        ConfidenceLabel::Medium => (50..=79).contains(&score),
        ConfidenceLabel::Low => score <= 49,
    };
    if !valid {
        issues.push(issue(
            code,
            format!("{context} confidence `{label:?}` does not match score {score}"),
        ));
    }
}

fn markdown_has_heading(markdown: &str, heading: &str) -> bool {
    markdown.lines().any(|line| line.trim() == heading)
}

fn markdown_first_major_heading(markdown: &str) -> Option<String> {
    let mut seen_title = false;
    for line in markdown.lines() {
        let trimmed = line.trim();
        if trimmed.starts_with("# ") && !seen_title {
            seen_title = true;
            continue;
        }
        if trimmed.starts_with("## ") {
            return Some(trimmed.to_string());
        }
    }
    None
}

fn validate_code_excerpt_budget(markdown: &str, issues: &mut Vec<ReportValidationIssue>) {
    let mut in_code_block = false;
    let mut current_block_is_machine = false;
    let mut block_lines = 0usize;
    let mut block_count = 0usize;
    for line in markdown.lines() {
        let trimmed = line.trim();
        if trimmed.starts_with("```") {
            if in_code_block {
                if !current_block_is_machine && block_lines > 10 {
                    issues.push(issue(
                        "code_excerpt_budget",
                        format!("code block {block_count} has {block_lines} lines (max 10)"),
                    ));
                }
                in_code_block = false;
                current_block_is_machine = false;
                block_lines = 0;
                continue;
            }
            in_code_block = true;
            let label = trimmed.trim_start_matches("```").trim().to_ascii_lowercase();
            current_block_is_machine = matches!(label.as_str(), "toml" | "json" | "yaml" | "yml");
            if !current_block_is_machine {
                block_count += 1;
            }
            continue;
        }
        if in_code_block && !current_block_is_machine {
            block_lines += 1;
        }
    }
    if block_count > 3 {
        issues.push(issue(
            "code_excerpt_budget",
            format!("report contains {block_count} fenced code blocks (max 3)"),
        ));
    }
}

fn extract_machine_blocks(markdown: &str) -> anyhow::Result<Vec<MachineBlock>> {
    let mut blocks = Vec::new();
    let lines: Vec<&str> = markdown.lines().collect();
    let mut idx = 0usize;
    while idx < lines.len() {
        let trimmed = lines[idx].trim();
        let Some(label) = trimmed.strip_prefix("```") else {
            idx += 1;
            continue;
        };
        let normalized = label.trim().to_ascii_lowercase();
        let format = match normalized.as_str() {
            "toml" => Some(MachineBlockFormat::Toml),
            "json" => Some(MachineBlockFormat::Json),
            "yaml" | "yml" => {
                return Err(anyhow::anyhow!(
                    "report validation failed:\n- unsupported_format: yaml machine blocks are not supported; use ```toml or ```json"
                ));
            }
            _ => None,
        };
        let Some(format) = format else {
            idx += 1;
            continue;
        };
        let start = idx + 1;
        idx += 1;
        while idx < lines.len() && lines[idx].trim() != "```" {
            idx += 1;
        }
        if idx >= lines.len() {
            return Err(anyhow::anyhow!(
                "report validation failed:\n- unterminated_machine_block: missing closing fence for machine-readable block"
            ));
        }
        let content = lines[start..idx].join("\n");
        blocks.push(MachineBlock { format, content });
        idx += 1;
    }
    Ok(blocks)
}

fn extract_machine_block(markdown: &str) -> anyhow::Result<MachineBlock> {
    let blocks = extract_machine_blocks(markdown)?;
    if let Some(block) = blocks
        .into_iter()
        .find(|block| block.format == MachineBlockFormat::Toml)
    {
        return Ok(block);
    }
    let blocks = extract_machine_blocks(markdown)?;
    if let Some(block) = blocks
        .into_iter()
        .find(|block| block.format == MachineBlockFormat::Json)
    {
        return Ok(block);
    }
    Err(anyhow::anyhow!(
        "report validation failed:\n- missing_machine_block: expected a fenced ```toml block or fallback ```json block"
    ))
}

fn parse_child_doc(block: &MachineBlock) -> anyhow::Result<ChildProofPacketDoc> {
    match block.format {
        MachineBlockFormat::Toml => toml::from_str(&block.content)
            .map_err(|err| anyhow::anyhow!("parse child toml machine block: {err}")),
        MachineBlockFormat::Json => serde_json::from_str(&block.content)
            .map_err(|err| anyhow::anyhow!("parse child json machine block: {err}")),
    }
}

fn parse_parent_doc(block: &MachineBlock) -> anyhow::Result<ParentReviewReportDoc> {
    match block.format {
        MachineBlockFormat::Toml => toml::from_str(&block.content)
            .map_err(|err| anyhow::anyhow!("parse parent toml machine block: {err}")),
        MachineBlockFormat::Json => serde_json::from_str(&block.content)
            .map_err(|err| anyhow::anyhow!("parse parent json machine block: {err}")),
    }
}

fn validate_child_markdown_shape(markdown: &str, issues: &mut Vec<ReportValidationIssue>) {
    for heading in [
        "## Proof Packet:",
        "### Domain Ledger",
        "### Coverage",
        "### Findings",
        "### Defended Proofs",
        "### Residual Risk",
    ] {
        if heading.ends_with(':') {
            if !markdown.lines().any(|line| line.trim_start().starts_with(heading)) {
                issues.push(issue(
                    "missing_heading",
                    format!("child report is missing heading prefix `{heading}`"),
                ));
            }
            continue;
        }
        if !markdown_has_heading(markdown, heading) {
            issues.push(issue(
                "missing_heading",
                format!("child report is missing heading `{heading}`"),
            ));
        }
    }
    if !markdown.contains("OUTPUT_COMPLETE") {
        issues.push(issue(
            "missing_output_complete",
            "child report is missing OUTPUT_COMPLETE truncation marker",
        ));
    }
    validate_code_excerpt_budget(markdown, issues);
}

fn validate_parent_markdown_shape(markdown: &str, issues: &mut Vec<ReportValidationIssue>) {
    let first_heading = markdown_first_major_heading(markdown);
    if first_heading
        .as_deref()
        .is_none_or(|heading| !heading.contains("Ship-Readiness"))
    {
        issues.push(issue(
            "ship_readiness_order",
            "parent report must place Ship-Readiness as the first major section after metadata",
        ));
    }
    let has_findings = markdown_has_heading(markdown, "## Findings")
        || markdown_has_heading(markdown, "## 6. Findings");
    if !has_findings {
        issues.push(issue(
            "missing_heading",
            "parent report is missing Findings section",
        ));
    }
    let has_defended = markdown_has_heading(markdown, "## Defended Proofs")
        || markdown_has_heading(markdown, "## 7. Defended Proofs");
    if !has_defended {
        issues.push(issue(
            "missing_heading",
            "parent report is missing Defended Proofs section",
        ));
    }
    let has_risk = markdown_has_heading(markdown, "## Residual Risk")
        || markdown_has_heading(markdown, "## 8. Residual Risk");
    if !has_risk {
        issues.push(issue(
            "missing_heading",
            "parent report is missing Residual Risk section",
        ));
    }
    validate_code_excerpt_budget(markdown, issues);
}

fn security_adjacent_role(role_slug: &str) -> bool {
    matches!(
        role_slug,
        "security-adversary"
            | "auth-access-prover"
            | "crypto-secrets-auditor"
            | "injection-hunter"
            | "data-integrity-prover"
            | "data-privacy-guardian"
    )
}

fn validate_child_doc(
    markdown: &str,
    doc: &ChildProofPacketDoc,
    expected_counts: Option<SeverityExpectation>,
    format: MachineBlockFormat,
) -> anyhow::Result<ReportValidationSummary> {
    let mut issues = Vec::new();
    validate_child_markdown_shape(markdown, &mut issues);

    if doc.schema_version != CHILD_SCHEMA_VERSION {
        issues.push(issue(
            "schema_version",
            format!(
                "child packet schema_version must be `{CHILD_SCHEMA_VERSION}`, got `{}`",
                doc.schema_version
            ),
        ));
    }
    if doc.artifact_kind != CHILD_ARTIFACT_KIND {
        issues.push(issue(
            "artifact_kind",
            format!(
                "child packet artifact_kind must be `{CHILD_ARTIFACT_KIND}`, got `{}`",
                doc.artifact_kind
            ),
        ));
    }
    for (code, label, value) in [
        ("role_slug", "role_slug", doc.role_slug.as_str()),
        ("role_title", "role_title", doc.role_title.as_str()),
        ("reviewer_id", "reviewer_id", doc.reviewer_id.as_str()),
        ("session_id", "session_id", doc.session_id.as_str()),
        ("target_ref", "target_ref", doc.target_ref.as_str()),
        ("overall_verdict", "overall_verdict", doc.overall_verdict.as_str()),
    ] {
        validate_non_blank(&mut issues, code, label, value);
    }
    validate_confidence(
        &mut issues,
        "overall_confidence",
        doc.overall_confidence_label,
        doc.overall_confidence_score,
        "overall child packet",
    );

    if doc.coverage.files_reviewed.is_empty() {
        issues.push(issue(
            "coverage_files",
            "coverage.files_reviewed must contain at least one file",
        ));
    }
    for domain in &doc.coverage.domains_in_scope {
        validate_non_blank(
            &mut issues,
            "coverage_domain_in_scope",
            "coverage.domains_in_scope",
            domain,
        );
    }
    for domain in &doc.coverage.domains_out_of_scope {
        validate_non_blank(
            &mut issues,
            "coverage_domain_out_of_scope",
            "coverage.domains_out_of_scope",
            domain,
        );
    }
    for test_cmd in &doc.coverage.tests_run {
        validate_non_blank(
            &mut issues,
            "coverage_tests_run",
            "coverage.tests_run",
            test_cmd,
        );
    }
    validate_non_blank(
        &mut issues,
        "coverage_tests_not_run_reason",
        "coverage.tests_not_run_reason",
        &doc.coverage.tests_not_run_reason,
    );
    for limitation in &doc.coverage.limitations {
        validate_non_blank(
            &mut issues,
            "coverage_limitations",
            "coverage.limitations",
            limitation,
        );
    }
    if doc.domain_ledger.is_empty() {
        issues.push(issue(
            "domain_ledger",
            "domain_ledger must contain at least one row",
        ));
    }

    let mut ledger_domains = BTreeMap::new();
    for row in &doc.domain_ledger {
        validate_non_blank(&mut issues, "domain", "domain_ledger.domain", &row.domain);
        validate_non_blank(
            &mut issues,
            "domain_rationale",
            "domain_ledger.rationale",
            &row.rationale,
        );
        if ledger_domains.insert(row.domain.clone(), row.scope).is_some() {
            issues.push(issue(
                "duplicate_domain",
                format!("duplicate domain ledger row for `{}`", row.domain),
            ));
        }
    }

    let mut theorem_domains: BTreeMap<&str, u64> = BTreeMap::new();
    let mut theorem_ids = BTreeSet::new();
    for theorem in &doc.theorems {
        validate_non_blank(&mut issues, "theorem_id", "theorems.id", &theorem.id);
        validate_non_blank(&mut issues, "theorem_claim", "theorems.claim", &theorem.claim);
        if theorem.anchors.is_empty() {
            issues.push(issue(
                "theorem_anchor",
                format!("theorem `{}` must list at least one anchor", theorem.id),
            ));
        }
        for anchor in &theorem.anchors {
            validate_anchor(&mut issues, "theorem_anchor", "theorems.anchor", anchor);
        }
        if !theorem_ids.insert(theorem.id.clone()) {
            issues.push(issue(
                "duplicate_theorem_id",
                format!("duplicate theorem id `{}`", theorem.id),
            ));
        }
        if !ledger_domains.contains_key(theorem.domain.as_str()) {
            issues.push(issue(
                "theorem_domain",
                format!(
                    "theorem `{}` references unknown domain `{}`",
                    theorem.id, theorem.domain
                ),
            ));
        }
        *theorem_domains.entry(&theorem.domain).or_default() += 1;
    }

    let mut disproof_counts_by_domain: BTreeMap<&str, u64> = BTreeMap::new();
    let mut disproof_counts_by_theorem: BTreeMap<&str, u64> = BTreeMap::new();
    let mut disproof_ids = BTreeSet::new();
    let mut disproof_findings = 0u64;
    let mut disproof_defended = 0u64;
    for disproof in &doc.disproof_attempts {
        validate_non_blank(&mut issues, "disproof_id", "disproof_attempts.id", &disproof.id);
        validate_non_blank(
            &mut issues,
            "disproof_scenario",
            "disproof_attempts.scenario",
            &disproof.scenario,
        );
        validate_non_blank(
            &mut issues,
            "disproof_evidence",
            "disproof_attempts.evidence",
            &disproof.evidence,
        );
        if !disproof_ids.insert(disproof.id.clone()) {
            issues.push(issue(
                "duplicate_disproof_id",
                format!("duplicate disproof attempt id `{}`", disproof.id),
            ));
        }
        match disproof.result {
            DisproofResult::Finding => disproof_findings += 1,
            DisproofResult::Defended => disproof_defended += 1,
            DisproofResult::Inconclusive => {}
        }
        let theorem = doc
            .theorems
            .iter()
            .find(|theorem| theorem.id == disproof.theorem_id);
        let Some(theorem) = theorem else {
            issues.push(issue(
                "disproof_theorem",
                format!(
                    "disproof attempt `{}` references unknown theorem `{}`",
                    disproof.id, disproof.theorem_id
                ),
            ));
            continue;
        };
        *disproof_counts_by_domain.entry(&theorem.domain).or_default() += 1;
        *disproof_counts_by_theorem
            .entry(disproof.theorem_id.as_str())
            .or_default() += 1;
    }

    let mut findings_by_domain: BTreeMap<&str, u64> = BTreeMap::new();
    let mut computed_counts = SeverityExpectation {
        blocker: 0,
        major: 0,
        minor: 0,
        nit: 0,
    };
    let mut finding_ids = BTreeSet::new();
    for finding in &doc.findings {
        for (code, label, value) in [
            ("finding_id", "findings.id", finding.id.as_str()),
            ("finding_claim", "findings.claim", finding.claim.as_str()),
            ("finding_disproof", "findings.disproof", finding.disproof.as_str()),
            ("finding_evidence", "findings.evidence", finding.evidence.as_str()),
            (
                "finding_recommendation",
                "findings.recommendation",
                finding.recommendation.as_str(),
            ),
            (
                "finding_verification",
                "findings.verification",
                finding.verification.as_str(),
            ),
        ] {
            validate_non_blank(&mut issues, code, label, value);
        }
        validate_anchor(&mut issues, "finding_anchor", "findings.anchor", &finding.anchor);
        validate_confidence(
            &mut issues,
            "finding_confidence",
            finding.confidence_label,
            finding.confidence_score,
            &format!("finding `{}`", finding.id),
        );
        if !finding_ids.insert(finding.id.clone()) {
            issues.push(issue(
                "duplicate_finding_id",
                format!("duplicate finding id `{}`", finding.id),
            ));
        }
        if !theorem_ids.contains(&finding.theorem_id) {
            issues.push(issue(
                "finding_theorem",
                format!(
                    "finding `{}` references unknown theorem `{}`",
                    finding.id, finding.theorem_id
                ),
            ));
        }
        if !ledger_domains.contains_key(finding.domain.as_str()) {
            issues.push(issue(
                "finding_domain",
                format!(
                    "finding `{}` references unknown domain `{}`",
                    finding.id, finding.domain
                ),
            ));
        }
        *findings_by_domain.entry(&finding.domain).or_default() += 1;
        match finding.severity {
            SeverityLabel::Blocker => computed_counts.blocker += 1,
            SeverityLabel::Major => computed_counts.major += 1,
            SeverityLabel::Minor => computed_counts.minor += 1,
            SeverityLabel::Nit => computed_counts.nit += 1,
        }
    }

    let mut defended_counts_by_domain: BTreeMap<&str, u64> = BTreeMap::new();
    let mut defended_theorem_ids = BTreeSet::new();
    for defended in &doc.defended_proofs {
        validate_anchor(
            &mut issues,
            "defended_anchor",
            "defended_proofs.anchor",
            &defended.anchor,
        );
        validate_non_blank(
            &mut issues,
            "defended_disproof_attempt",
            "defended_proofs.disproof_attempt",
            &defended.disproof_attempt,
        );
        validate_non_blank(
            &mut issues,
            "defended_rationale",
            "defended_proofs.rationale",
            &defended.rationale,
        );
        if defended.outcome != "Defended" {
            issues.push(issue(
                "defended_outcome",
                format!(
                    "defended proof for theorem `{}` must use outcome `Defended`, got `{}`",
                    defended.theorem_id, defended.outcome
                ),
            ));
        }
        validate_confidence(
            &mut issues,
            "defended_confidence",
            defended.confidence_label,
            defended.confidence_score,
            &format!("defended proof `{}`", defended.theorem_id),
        );
        let theorem = doc
            .theorems
            .iter()
            .find(|theorem| theorem.id == defended.theorem_id);
        let Some(theorem) = theorem else {
            issues.push(issue(
                "defended_theorem",
                format!(
                    "defended proof references unknown theorem `{}`",
                    defended.theorem_id
                ),
            ));
            continue;
        };
        if !defended_theorem_ids.insert(defended.theorem_id.clone()) {
            issues.push(issue(
                "duplicate_defended_theorem",
                format!(
                    "defended proof duplicates theorem `{}`",
                    defended.theorem_id
                ),
            ));
        }
        *defended_counts_by_domain.entry(&theorem.domain).or_default() += 1;
    }

    for risk in &doc.residual_risks {
        validate_non_blank(&mut issues, "risk_area", "residual_risks.area", &risk.area);
        validate_non_blank(&mut issues, "risk_gap", "residual_risks.gap", &risk.gap);
        validate_non_blank(&mut issues, "risk_impact", "residual_risks.impact", &risk.impact);
        validate_non_blank(
            &mut issues,
            "risk_next_action",
            "residual_risks.next_action",
            &risk.next_action,
        );
    }

    for row in &doc.domain_ledger {
        let theorem_count = theorem_domains.get(row.domain.as_str()).copied().map_or(0, |v| v);
        let disproof_count = disproof_counts_by_domain
            .get(row.domain.as_str())
            .copied()
            .map_or(0, |v| v);
        let finding_count = findings_by_domain
            .get(row.domain.as_str())
            .copied()
            .map_or(0, |v| v);
        let defended_count = defended_counts_by_domain
            .get(row.domain.as_str())
            .copied()
            .map_or(0, |v| v);
        if row.theorems != theorem_count {
            issues.push(issue(
                "ledger_theorems",
                format!(
                    "domain `{}` ledger says {} theorems but machine data has {}",
                    row.domain, row.theorems, theorem_count
                ),
            ));
        }
        if row.disproofs != disproof_count {
            issues.push(issue(
                "ledger_disproofs",
                format!(
                    "domain `{}` ledger says {} disproofs but machine data has {}",
                    row.domain, row.disproofs, disproof_count
                ),
            ));
        }
        if row.findings != finding_count {
            issues.push(issue(
                "ledger_findings",
                format!(
                    "domain `{}` ledger says {} findings but machine data has {}",
                    row.domain, row.findings, finding_count
                ),
            ));
        }
        if row.defended != defended_count {
            issues.push(issue(
                "ledger_defended",
                format!(
                    "domain `{}` ledger says {} defended proofs but machine data has {}",
                    row.domain, row.defended, defended_count
                ),
            ));
        }
        if row.scope == DomainScope::InScope && theorem_count < 2 {
            issues.push(issue(
                "in_scope_theorem_depth",
                format!(
                    "domain `{}` is In-scope and must have at least 2 theorems, found {}",
                    row.domain, theorem_count
                ),
            ));
        }
    }

    for theorem in &doc.theorems {
        let attempts = disproof_counts_by_theorem
            .get(theorem.id.as_str())
            .copied()
            .map_or(0, |v| v);
        if attempts == 0 {
            issues.push(issue(
                "missing_disproof_attempts",
                format!("theorem `{}` must have at least one disproof attempt", theorem.id),
            ));
        }
        if security_adjacent_role(doc.role_slug.as_str()) && attempts < 3 {
            issues.push(issue(
                "security_disproof_depth",
                format!(
                    "security-adjacent role `{}` requires at least 3 disproof attempts per theorem; `{}` has {}",
                    doc.role_slug, theorem.id, attempts
                ),
            ));
        }
    }

    if u64::try_from(doc.findings.len())
        .ok()
        .is_some_and(|count| count > disproof_findings)
    {
        issues.push(issue(
            "finding_without_disproof",
            format!(
                "machine data has {} findings but only {} disproof attempts marked FINDING",
                doc.findings.len(),
                disproof_findings
            ),
        ));
    }
    if u64::try_from(doc.defended_proofs.len())
        .ok()
        .is_some_and(|count| count > disproof_defended)
    {
        issues.push(issue(
            "defended_without_disproof",
            format!(
                "machine data has {} defended proofs but only {} disproof attempts marked DEFENDED",
                doc.defended_proofs.len(),
                disproof_defended
            ),
        ));
    }

    if let Some(expected) = expected_counts {
        if expected.blocker != computed_counts.blocker
            || expected.major != computed_counts.major
            || expected.minor != computed_counts.minor
            || expected.nit != computed_counts.nit
        {
            issues.push(issue(
                "severity_counts",
                format!(
                    "expected counts blocker={} major={} minor={} nit={} but machine data computed blocker={} major={} minor={} nit={}",
                    expected.blocker,
                    expected.major,
                    expected.minor,
                    expected.nit,
                    computed_counts.blocker,
                    computed_counts.major,
                    computed_counts.minor,
                    computed_counts.nit
                ),
            ));
        }
    }

    if !issues.is_empty() {
        return Err(format_issues(&issues));
    }

    Ok(ReportValidationSummary {
        kind: ReportValidationKind::ChildProofPacket,
        format,
        findings: doc.findings.len(),
        defended_proofs: doc.defended_proofs.len(),
        residual_risks: doc.residual_risks.len(),
    })
}

fn validate_parent_doc(
    markdown: &str,
    doc: &ParentReviewReportDoc,
    expected_counts: Option<SeverityExpectation>,
    format: MachineBlockFormat,
) -> anyhow::Result<ReportValidationSummary> {
    let mut issues = Vec::new();
    validate_parent_markdown_shape(markdown, &mut issues);

    if doc.schema_version != PARENT_SCHEMA_VERSION {
        issues.push(issue(
            "schema_version",
            format!(
                "parent report schema_version must be `{PARENT_SCHEMA_VERSION}`, got `{}`",
                doc.schema_version
            ),
        ));
    }
    if doc.artifact_kind != PARENT_ARTIFACT_KIND {
        issues.push(issue(
            "artifact_kind",
            format!(
                "parent report artifact_kind must be `{PARENT_ARTIFACT_KIND}`, got `{}`",
                doc.artifact_kind
            ),
        ));
    }
    for (code, label, value) in [
        ("reviewer_id", "reviewer_id", doc.reviewer_id.as_str()),
        ("session_id", "session_id", doc.session_id.as_str()),
        ("target_ref", "target_ref", doc.target_ref.as_str()),
        ("verdict", "verdict", doc.verdict.as_str()),
        (
            "ship_verdict",
            "ship_readiness.verdict",
            doc.ship_readiness.verdict.as_str(),
        ),
    ] {
        validate_non_blank(&mut issues, code, label, value);
    }
    validate_confidence(
        &mut issues,
        "ship_confidence",
        doc.ship_readiness.confidence_label,
        doc.ship_readiness.confidence_score,
        "ship-readiness",
    );
    if !matches!(
        doc.ship_readiness.verdict.as_str(),
        "SHIP" | "SHIP_WITH_FIXES" | "DO_NOT_SHIP"
    ) {
        issues.push(issue(
            "ship_verdict",
            format!(
                "ship_readiness.verdict must be SHIP|SHIP_WITH_FIXES|DO_NOT_SHIP, got `{}`",
                doc.ship_readiness.verdict
            ),
        ));
    }

    if doc.source_packets.is_empty() {
        issues.push(issue(
            "source_packets",
            "parent report must reference at least one source packet",
        ));
    }

    let mut source_packet_keys = BTreeSet::new();
    for packet in &doc.source_packets {
        validate_non_blank(
            &mut issues,
            "source_packet_reviewer",
            "source_packets.reviewer_id",
            &packet.reviewer_id,
        );
        validate_non_blank(
            &mut issues,
            "source_packet_session",
            "source_packets.session_id",
            &packet.session_id,
        );
        validate_non_blank(
            &mut issues,
            "source_packet_ref",
            "source_packets.artifact_ref",
            &packet.artifact_ref,
        );
        source_packet_keys.insert(packet.artifact_ref.as_str());
    }

    let expected_axes = BTreeSet::from([
        "Acceptance criteria",
        "Complexity budget",
        "Correctness",
        "Safety",
        "Test coverage",
    ]);
    let actual_axes: BTreeSet<&str> = doc
        .ship_readiness_axes
        .iter()
        .map(|axis| axis.axis.as_str())
        .collect();
    if actual_axes != expected_axes {
        issues.push(issue(
            "ship_axes",
            format!(
                "ship_readiness_axes must cover {:?}, got {:?}",
                expected_axes, actual_axes
            ),
        ));
    }
    for axis in &doc.ship_readiness_axes {
        validate_non_blank(&mut issues, "ship_axis_notes", "ship_readiness_axes.notes", &axis.notes);
        if !matches!(axis.status.as_str(), "PASS" | "CONDITIONAL" | "FAIL") {
            issues.push(issue(
                "ship_axis_status",
                format!(
                    "ship_readiness axis `{}` must use PASS|CONDITIONAL|FAIL, got `{}`",
                    axis.axis, axis.status
                ),
            ));
        }
    }

    let mut computed_counts = SeverityExpectation {
        blocker: 0,
        major: 0,
        minor: 0,
        nit: 0,
    };
    let mut finding_ids = BTreeSet::new();
    for finding in &doc.merged_findings {
        validate_non_blank(&mut issues, "merged_finding_id", "merged_findings.id", &finding.id);
        validate_anchor(
            &mut issues,
            "merged_finding_anchor",
            "merged_findings.anchor",
            &finding.anchor,
        );
        for (code, label, value) in [
            ("merged_finding_claim", "merged_findings.claim", finding.claim.as_str()),
            (
                "merged_finding_disproof",
                "merged_findings.disproof",
                finding.disproof.as_str(),
            ),
            (
                "merged_finding_evidence",
                "merged_findings.evidence",
                finding.evidence.as_str(),
            ),
            (
                "merged_finding_recommendation",
                "merged_findings.recommendation",
                finding.recommendation.as_str(),
            ),
            (
                "merged_finding_verification",
                "merged_findings.verification",
                finding.verification.as_str(),
            ),
        ] {
            validate_non_blank(&mut issues, code, label, value);
        }
        if !finding_ids.insert(finding.id.clone()) {
            issues.push(issue(
                "duplicate_merged_finding",
                format!("duplicate merged finding id `{}`", finding.id),
            ));
        }
        if finding.source_packets.is_empty() {
            issues.push(issue(
                "merged_finding_sources",
                format!("merged finding `{}` must reference at least one source packet", finding.id),
            ));
        }
        for source in &finding.source_packets {
            if !source_packet_keys.contains(source.as_str()) {
                issues.push(issue(
                    "merged_finding_sources",
                    format!(
                        "merged finding `{}` references unknown source packet `{}`",
                        finding.id, source
                    ),
                ));
            }
        }
        validate_confidence(
            &mut issues,
            "merged_finding_confidence",
            finding.confidence_label,
            finding.confidence_score,
            &format!("merged finding `{}`", finding.id),
        );
        match finding.severity {
            SeverityLabel::Blocker => computed_counts.blocker += 1,
            SeverityLabel::Major => computed_counts.major += 1,
            SeverityLabel::Minor => computed_counts.minor += 1,
            SeverityLabel::Nit => computed_counts.nit += 1,
        }
    }

    for defended in &doc.defended_summary {
        validate_non_blank(
            &mut issues,
            "defended_summary_theorem",
            "defended_summary.theorem_id",
            &defended.theorem_id,
        );
        validate_non_blank(
            &mut issues,
            "defended_summary_text",
            "defended_summary.summary",
            &defended.summary,
        );
        if defended.source_packets.is_empty() {
            issues.push(issue(
                "defended_summary_sources",
                format!(
                    "defended summary `{}` must reference at least one source packet",
                    defended.theorem_id
                ),
            ));
        }
        for source in &defended.source_packets {
            if !source_packet_keys.contains(source.as_str()) {
                issues.push(issue(
                    "defended_summary_sources",
                    format!(
                        "defended summary `{}` references unknown source packet `{}`",
                        defended.theorem_id, source
                    ),
                ));
            }
        }
        validate_confidence(
            &mut issues,
            "defended_summary_confidence",
            defended.confidence_label,
            defended.confidence_score,
            &format!("defended summary `{}`", defended.theorem_id),
        );
    }

    for risk in &doc.residual_risks {
        validate_non_blank(&mut issues, "risk_area", "residual_risks.area", &risk.area);
        validate_non_blank(&mut issues, "risk_gap", "residual_risks.gap", &risk.gap);
        validate_non_blank(&mut issues, "risk_impact", "residual_risks.impact", &risk.impact);
        validate_non_blank(
            &mut issues,
            "risk_next_action",
            "residual_risks.next_action",
            &risk.next_action,
        );
    }

    if doc.validation_summary.packets_validated == 0 {
        issues.push(issue(
            "validation_summary",
            "validation_summary.packets_validated must be > 0",
        ));
    }
    if doc.validation_summary.packets_rejected
        > doc.validation_summary.packets_validated + doc.validation_summary.retry_count
    {
        issues.push(issue(
            "validation_summary",
            format!(
                "validation_summary is inconsistent: packets_rejected={} exceeds packets_validated+retry_count={}+{}",
                doc.validation_summary.packets_rejected,
                doc.validation_summary.packets_validated,
                doc.validation_summary.retry_count
            ),
        ));
    }
    let counts = SeverityExpectation {
        blocker: doc.counts.blocker,
        major: doc.counts.major,
        minor: doc.counts.minor,
        nit: doc.counts.nit,
    };
    if counts.blocker != computed_counts.blocker
        || counts.major != computed_counts.major
        || counts.minor != computed_counts.minor
        || counts.nit != computed_counts.nit
    {
        issues.push(issue(
            "parent_counts",
            format!(
                "parent counts blocker={} major={} minor={} nit={} do not match merged findings blocker={} major={} minor={} nit={}",
                counts.blocker,
                counts.major,
                counts.minor,
                counts.nit,
                computed_counts.blocker,
                computed_counts.major,
                computed_counts.minor,
                computed_counts.nit
            ),
        ));
    }
    if let Some(expected) = expected_counts {
        if counts.blocker != expected.blocker
            || counts.major != expected.major
            || counts.minor != expected.minor
            || counts.nit != expected.nit
        {
            issues.push(issue(
                "expected_parent_counts",
                format!(
                    "parent report counts blocker={} major={} minor={} nit={} do not match expected CLI counts blocker={} major={} minor={} nit={}",
                    counts.blocker,
                    counts.major,
                    counts.minor,
                    counts.nit,
                    expected.blocker,
                    expected.major,
                    expected.minor,
                    expected.nit
                ),
            ));
        }
    }

    if !issues.is_empty() {
        return Err(format_issues(&issues));
    }

    Ok(ReportValidationSummary {
        kind: ReportValidationKind::ParentReviewReport,
        format,
        findings: doc.merged_findings.len(),
        defended_proofs: doc.defended_summary.len(),
        residual_risks: doc.residual_risks.len(),
    })
}

/// Validate markdown report content against the requested report contract.
///
/// # Errors
/// Returns an error if the machine-readable block is missing, malformed, or
/// fails structural validation.
pub fn validate_report_markdown(
    markdown: &str,
    kind: ReportValidationKind,
    expected_counts: Option<SeverityExpectation>,
) -> anyhow::Result<ReportValidationSummary> {
    let block = extract_machine_block(markdown)?;
    match kind {
        ReportValidationKind::ChildProofPacket => {
            let doc = parse_child_doc(&block)?;
            validate_child_doc(markdown, &doc, expected_counts, block.format)
        }
        ReportValidationKind::ParentReviewReport => {
            let doc = parse_parent_doc(&block)?;
            validate_parent_doc(markdown, &doc, expected_counts, block.format)
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use anyhow::ensure;

    const VALID_CHILD_TOML: &str = r#"# Proof Packet

```toml
schema_version = "proof_packet.v2"
artifact_kind = "child_proof_packet"
role_slug = "security-adversary"
role_title = "Security Adversary"
reviewer_id = "deadbeef"
session_id = "sess0001"
target_ref = "refs/heads/main"
overall_verdict = "REQUEST_CHANGES"
overall_confidence_label = "HIGH"
overall_confidence_score = 91

[coverage]
files_reviewed = ["src/lib.rs"]
domains_in_scope = ["Security"]
domains_out_of_scope = []
tests_run = ["cargo test --lib"]
tests_not_run_reason = "All scoped tests were run."
limitations = ["No production traffic replay"]

[[domain_ledger]]
domain = "Security"
scope = "IN_SCOPE"
rationale = "Untrusted input reaches privileged operations."
theorems = 2
disproofs = 6
findings = 1
defended = 1

[[theorems]]
id = "T1"
domain = "Security"
claim = "Input validation blocks path traversal."
anchors = ["src/lib.rs:10"]

[[theorems]]
id = "T2"
domain = "Security"
claim = "Secrets are not logged on error paths."
anchors = ["src/lib.rs:22"]

[[disproof_attempts]]
id = "D1"
theorem_id = "T1"
scenario = "Attempt ../ traversal."
result = "FINDING"
evidence = "Trace reaches join without canonicalization."

[[disproof_attempts]]
id = "D2"
theorem_id = "T1"
scenario = "Encoded traversal."
result = "FINDING"
evidence = "Encoded variant also reaches join."

[[disproof_attempts]]
id = "D3"
theorem_id = "T1"
scenario = "Mixed separator traversal."
result = "FINDING"
evidence = "Windows path separator bypass."

[[disproof_attempts]]
id = "D4"
theorem_id = "T2"
scenario = "Log auth failure with secret."
result = "DEFENDED"
evidence = "Redaction strips token value."

[[disproof_attempts]]
id = "D5"
theorem_id = "T2"
scenario = "Nested error path."
result = "DEFENDED"
evidence = "Formatter uses placeholder."

[[disproof_attempts]]
id = "D6"
theorem_id = "T2"
scenario = "Boundary length token."
result = "DEFENDED"
evidence = "Hash only, no raw token output."

[[findings]]
id = "F1"
theorem_id = "T1"
domain = "Security"
severity = "MAJOR"
anchor = "src/lib.rs:10"
claim = "Traversal should be rejected before filesystem access."
disproof = "Input ../secret escapes root."
evidence = "normalize_path is not called."
recommendation = "Canonicalize and bound the path before open."
verification = "Add traversal regression test."
confidence_label = "HIGH"
confidence_score = 90

[[defended_proofs]]
theorem_id = "T2"
anchor = "src/lib.rs:22"
disproof_attempt = "Auth failure logging."
outcome = "Defended"
confidence_label = "MEDIUM"
confidence_score = 66
rationale = "Multiple error paths redact the token."

[[residual_risks]]
area = "Secret handling"
gap = "Did not replay production log sinks."
impact = "A custom sink may log more context."
next_action = "Add sink integration test."
```

## Proof Packet: Security Adversary

### Domain Ledger
| Domain | Scope | Theorems | Disproofs | Findings | Defended |
|--------|-------|----------|-----------|----------|----------|
| Security | In-scope | 2 | 6 | 1 | 1 |

### Coverage
- Files reviewed: `src/lib.rs`
- Domains covered: Security

### Findings
- **Severity:** MAJOR
- **Anchor:** `src/lib.rs:10`
- **Claim:** Traversal should be rejected before filesystem access.
- **Disproof:** Input ../secret escapes root.
- **Evidence:** normalize_path is not called.
- **Recommendation:** Canonicalize and bound the path before open.
- **Verification:** Add traversal regression test.

### Defended Proofs
- **Theorem:** T2
- **Disproof attempt:** Auth failure logging.
- **Outcome:** Defended
- **Confidence:** MEDIUM

### Residual Risk
- Did not replay production log sinks.

OUTPUT_COMPLETE
"#;

    const VALID_CHILD_JSON: &str = r#"# Proof Packet

```json
{
  "schema_version": "proof_packet.v2",
  "artifact_kind": "child_proof_packet",
  "role_slug": "security-adversary",
  "role_title": "Security Adversary",
  "reviewer_id": "feedface",
  "session_id": "sess0001",
  "target_ref": "refs/heads/main",
  "overall_verdict": "REQUEST_CHANGES",
  "overall_confidence_label": "HIGH",
  "overall_confidence_score": 90,
  "coverage": {
    "files_reviewed": ["src/lib.rs"],
    "domains_in_scope": ["Security"],
    "domains_out_of_scope": [],
    "tests_run": ["cargo test security::path_traversal"],
    "tests_not_run_reason": "No integration environment was provisioned.",
    "limitations": ["Did not replay production log sinks."]
  },
  "domain_ledger": [
    {
      "domain": "Security",
      "scope": "IN_SCOPE",
      "rationale": "The patch touches filesystem path handling and secret logging.",
      "theorems": 2,
      "disproofs": 6,
      "findings": 1,
      "defended": 1
    }
  ],
  "theorems": [
    {
      "id": "T1",
      "domain": "Security",
      "claim": "Path normalization keeps reads inside the configured workspace root.",
      "anchors": ["src/lib.rs:10", "src/lib.rs:14"]
    },
    {
      "id": "T2",
      "domain": "Security",
      "claim": "Auth failures never log raw credentials.",
      "anchors": ["src/lib.rs:22"]
    }
  ],
  "disproof_attempts": [
    {
      "id": "D1",
      "theorem_id": "T1",
      "scenario": "Attempt ../ traversal.",
      "result": "FINDING",
      "evidence": "Trace reaches join without canonicalization."
    },
    {
      "id": "D2",
      "theorem_id": "T1",
      "scenario": "Encoded traversal.",
      "result": "FINDING",
      "evidence": "Encoded variant also reaches join."
    },
    {
      "id": "D3",
      "theorem_id": "T1",
      "scenario": "Mixed separator traversal.",
      "result": "FINDING",
      "evidence": "Windows path separator bypass."
    },
    {
      "id": "D4",
      "theorem_id": "T2",
      "scenario": "Log auth failure with secret.",
      "result": "DEFENDED",
      "evidence": "Redaction strips token value."
    },
    {
      "id": "D5",
      "theorem_id": "T2",
      "scenario": "Nested error path.",
      "result": "DEFENDED",
      "evidence": "Formatter uses placeholder."
    },
    {
      "id": "D6",
      "theorem_id": "T2",
      "scenario": "Boundary length token.",
      "result": "DEFENDED",
      "evidence": "Hash only, no raw token output."
    }
  ],
  "findings": [
    {
      "id": "F1",
      "theorem_id": "T1",
      "domain": "Security",
      "severity": "MAJOR",
      "anchor": "src/lib.rs:10",
      "claim": "Traversal should be rejected before filesystem access.",
      "disproof": "Input ../secret escapes root.",
      "evidence": "normalize_path is not called.",
      "recommendation": "Canonicalize and bound the path before open.",
      "verification": "Add traversal regression test.",
      "confidence_label": "HIGH",
      "confidence_score": 90
    }
  ],
  "defended_proofs": [
    {
      "theorem_id": "T2",
      "anchor": "src/lib.rs:22",
      "disproof_attempt": "Auth failure logging.",
      "outcome": "Defended",
      "confidence_label": "MEDIUM",
      "confidence_score": 66,
      "rationale": "Multiple error paths redact the token."
    }
  ],
  "residual_risks": [
    {
      "area": "Secret handling",
      "gap": "Did not replay production log sinks.",
      "impact": "A custom sink may log more context.",
      "next_action": "Add sink integration test."
    }
  ]
}
```

## Proof Packet: Security Adversary

### Domain Ledger
| Domain | Scope | Theorems | Disproofs | Findings | Defended |
|--------|-------|----------|-----------|----------|----------|
| Security | In-scope | 2 | 6 | 1 | 1 |

### Coverage
- Files reviewed: `src/lib.rs`
- Domains covered: Security

### Findings
- **Severity:** MAJOR
- **Anchor:** `src/lib.rs:10`
- **Claim:** Traversal should be rejected before filesystem access.
- **Disproof:** Input ../secret escapes root.
- **Evidence:** normalize_path is not called.
- **Recommendation:** Canonicalize and bound the path before open.
- **Verification:** Add traversal regression test.

### Defended Proofs
- **Theorem:** T2
- **Disproof attempt:** Auth failure logging.
- **Outcome:** Defended
- **Confidence:** MEDIUM

### Residual Risk
- Did not replay production log sinks.

OUTPUT_COMPLETE
"#;

const VALID_PARENT_TOML: &str = r#"# Code Review Report

```toml
schema_version = "proof_packet.v2"
artifact_kind = "parent_review_report"
reviewer_id = "deadbeef"
session_id = "sess0001"
target_ref = "refs/heads/main"
verdict = "REQUEST_CHANGES"

[counts]
blocker = 0
major = 1
minor = 0
nit = 0

[ship_readiness]
verdict = "DO_NOT_SHIP"
confidence_label = "HIGH"
confidence_score = 90

[[ship_readiness_axes]]
axis = "Correctness"
status = "FAIL"
notes = "Traversal bug is still open."

[[ship_readiness_axes]]
axis = "Safety"
status = "FAIL"
notes = "Path escape risk remains."

[[ship_readiness_axes]]
axis = "Complexity budget"
status = "PASS"
notes = "Fix scope is local."

[[ship_readiness_axes]]
axis = "Test coverage"
status = "CONDITIONAL"
notes = "Regression test is missing."

[[ship_readiness_axes]]
axis = "Acceptance criteria"
status = "FAIL"
notes = "Safe path handling criterion is unmet."

[[source_packets]]
reviewer_id = "feedface"
session_id = "sess0001"
artifact_ref = "child:feedface:sess0001"

[[merged_findings]]
id = "MF1"
severity = "MAJOR"
anchor = "src/lib.rs:10"
claim = "Traversal should be rejected before filesystem access."
disproof = "Input ../secret escapes root."
evidence = "normalize_path is not called."
recommendation = "Canonicalize and bound the path before open."
verification = "Add traversal regression test."
source_packets = ["child:feedface:sess0001"]
confidence_label = "HIGH"
confidence_score = 92

[[defended_summary]]
theorem_id = "T2"
source_packets = ["child:feedface:sess0001"]
summary = "Token redaction held across tested error paths."
confidence_label = "MEDIUM"
confidence_score = 68

[[residual_risks]]
area = "Log sinks"
gap = "Production sink parity was not validated."
impact = "Custom sinks may diverge from test behavior."
next_action = "Run integration sink test."

[validation_summary]
packets_validated = 1
packets_rejected = 0
retry_count = 0
```

## Ship-Readiness
**Verdict:** DO_NOT_SHIP

## Findings
- Major traversal issue remains.

## Defended Proofs
- Token redaction held across tested paths.

## Residual Risk
- Production log sink parity remains unverified.
"#;

    const VALID_PARENT_JSON: &str = r#"# Code Review Report

```json
{
  "schema_version": "proof_packet.v2",
  "artifact_kind": "parent_review_report",
  "reviewer_id": "deadbeef",
  "session_id": "sess0001",
  "target_ref": "refs/heads/main",
  "verdict": "REQUEST_CHANGES",
  "counts": {
    "blocker": 0,
    "major": 1,
    "minor": 0,
    "nit": 0
  },
  "ship_readiness": {
    "verdict": "DO_NOT_SHIP",
    "confidence_label": "HIGH",
    "confidence_score": 90
  },
  "ship_readiness_axes": [
    {
      "axis": "Correctness",
      "status": "FAIL",
      "notes": "Traversal bug is still open."
    },
    {
      "axis": "Safety",
      "status": "FAIL",
      "notes": "Path escape risk remains."
    },
    {
      "axis": "Complexity budget",
      "status": "PASS",
      "notes": "Fix scope is local."
    },
    {
      "axis": "Test coverage",
      "status": "CONDITIONAL",
      "notes": "Regression test is missing."
    },
    {
      "axis": "Acceptance criteria",
      "status": "FAIL",
      "notes": "Safe path handling criterion is unmet."
    }
  ],
  "source_packets": [
    {
      "reviewer_id": "feedface",
      "session_id": "sess0001",
      "artifact_ref": "child:feedface:sess0001"
    }
  ],
  "merged_findings": [
    {
      "id": "MF1",
      "severity": "MAJOR",
      "anchor": "src/lib.rs:10",
      "claim": "Traversal should be rejected before filesystem access.",
      "disproof": "Input ../secret escapes root.",
      "evidence": "normalize_path is not called.",
      "recommendation": "Canonicalize and bound the path before open.",
      "verification": "Add traversal regression test.",
      "source_packets": ["child:feedface:sess0001"],
      "confidence_label": "HIGH",
      "confidence_score": 92
    }
  ],
  "defended_summary": [
    {
      "theorem_id": "T2",
      "source_packets": ["child:feedface:sess0001"],
      "summary": "Token redaction held across tested error paths.",
      "confidence_label": "MEDIUM",
      "confidence_score": 68
    }
  ],
  "residual_risks": [
    {
      "area": "Log sinks",
      "gap": "Production sink parity was not validated.",
      "impact": "Custom sinks may diverge from test behavior.",
      "next_action": "Run integration sink test."
    }
  ],
  "validation_summary": {
    "packets_validated": 1,
    "packets_rejected": 0,
    "retry_count": 0
  }
}
```

## Ship-Readiness
**Verdict:** DO_NOT_SHIP

## Findings
- Major traversal issue remains.

## Defended Proofs
- Token redaction held across tested paths.

## Residual Risk
- Production log sink parity remains unverified.
"#;

    #[test]
    fn child_toml_packet_passes() -> anyhow::Result<()> {
        let summary = validate_report_markdown(
            VALID_CHILD_TOML,
            ReportValidationKind::ChildProofPacket,
            Some(SeverityExpectation {
                blocker: 0,
                major: 1,
                minor: 0,
                nit: 0,
            }),
        )?;
        ensure!(summary.format == MachineBlockFormat::Toml);
        ensure!(summary.findings == 1);
        Ok(())
    }

    #[test]
    fn child_json_packet_passes() -> anyhow::Result<()> {
        let summary = validate_report_markdown(
            VALID_CHILD_JSON,
            ReportValidationKind::ChildProofPacket,
            None,
        )?;
        ensure!(summary.format == MachineBlockFormat::Json);
        Ok(())
    }

    #[test]
    fn yaml_machine_block_fails() -> anyhow::Result<()> {
        let markdown = VALID_CHILD_TOML.replacen("```toml", "```yaml", 1);
        let err = match validate_report_markdown(
            &markdown,
            ReportValidationKind::ChildProofPacket,
            None,
        ) {
            Ok(_) => return Err(anyhow::anyhow!("yaml should fail")),
            Err(err) => err,
        };
        ensure!(err.to_string().contains("unsupported_format"));
        Ok(())
    }

    #[test]
    fn missing_confidence_fails() -> anyhow::Result<()> {
        let markdown = VALID_CHILD_TOML.replace("confidence_score = 90\n", "");
        let err = match validate_report_markdown(
            &markdown,
            ReportValidationKind::ChildProofPacket,
            None,
        ) {
            Ok(_) => return Err(anyhow::anyhow!("missing confidence should fail")),
            Err(err) => err,
        };
        ensure!(err.to_string().contains("parse child toml machine block"));
        Ok(())
    }

    #[test]
    fn parent_toml_report_passes() -> anyhow::Result<()> {
        let summary = validate_report_markdown(
            VALID_PARENT_TOML,
            ReportValidationKind::ParentReviewReport,
            Some(SeverityExpectation {
                blocker: 0,
                major: 1,
                minor: 0,
                nit: 0,
            }),
        )?;
        ensure!(summary.findings == 1);
        Ok(())
    }

    #[test]
    fn parent_json_report_passes() -> anyhow::Result<()> {
        let summary = validate_report_markdown(
            VALID_PARENT_JSON,
            ReportValidationKind::ParentReviewReport,
            Some(SeverityExpectation {
                blocker: 0,
                major: 1,
                minor: 0,
                nit: 0,
            }),
        )?;
        ensure!(summary.format == MachineBlockFormat::Json);
        ensure!(summary.findings == 1);
        Ok(())
    }

    #[test]
    fn parent_count_mismatch_fails() -> anyhow::Result<()> {
        let err = match validate_report_markdown(
            VALID_PARENT_TOML,
            ReportValidationKind::ParentReviewReport,
            Some(SeverityExpectation {
                blocker: 0,
                major: 0,
                minor: 0,
                nit: 0,
            }),
        ) {
            Ok(_) => return Err(anyhow::anyhow!("count mismatch should fail")),
            Err(err) => err,
        };
        ensure!(err.to_string().contains("expected_parent_counts"));
        Ok(())
    }
}
