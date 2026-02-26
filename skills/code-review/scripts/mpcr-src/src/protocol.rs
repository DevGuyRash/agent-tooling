//! Embedded protocol data for just-in-time phase guidance.
//!
//! Protocol content is compiled into the binary from TOML files in `protocols/`.
//! The CLI (`mpcr protocol ...`) serves phase-appropriate snippets so that
//! agents never need to hold the full protocol specification in context.

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

// ── Embedded TOML sources (compiled in) ──────────────────────────────────────

const REVIEWER_TOML: &str = include_str!("../protocols/reviewer.toml");
const APPLICATOR_TOML: &str = include_str!("../protocols/applicator.toml");
const ORCHESTRATOR_TOML: &str = include_str!("../protocols/orchestrator.toml");
const TEMPLATES_TOML: &str = include_str!("../protocols/templates.toml");
const DISPATCH_TOML: &str = include_str!("../protocols/dispatch.toml");
const SESSION_TOML: &str = include_str!("../protocols/session.toml");

// ── Deserialization types ────────────────────────────────────────────────────

#[derive(Debug, Deserialize)]
/// A single phase entry with title and content guidance.
pub struct PhaseEntry {
    /// Human-readable phase title.
    pub title: String,
    /// Phase-appropriate guidance text.
    pub content: String,
}

#[derive(Debug, Deserialize)]
/// TOML structure for files with a `[phases.<NAME>]` table.
struct PhasesFile {
    phases: HashMap<String, PhaseEntry>,
}

#[derive(Debug, Deserialize)]
/// A named section with title and content.
struct NamedSection {
    title: String,
    content: String,
}

#[derive(Debug, Deserialize)]
/// TOML structure for `orchestrator.toml`.
struct OrchestratorFile {
    orchestrator: NamedSection,
    domains: NamedSection,
    #[serde(default)]
    fullcycle: Option<NamedSection>,
    #[serde(default)]
    invocation_aliases: Option<NamedSection>,
    #[serde(default)]
    workflow_selection: Option<NamedSection>,
    #[serde(default)]
    quality_gate: Option<NamedSection>,
    #[serde(default)]
    change_classification: Option<NamedSection>,
    #[serde(default)]
    analyze: Option<NamedSection>,
}

#[derive(Debug, Deserialize)]
/// TOML structure for `templates.toml`.
struct TemplatesFile {
    scales: HashMap<String, NamedSection>,
}

/// Common sections shared across all dispatch roles.
#[derive(Debug, Deserialize)]
struct DispatchCommon {
    worker_preamble: String,
    task_steps: String,
    output_format: String,
}

/// TOML structure for `dispatch.toml`.
#[derive(Debug, Deserialize)]
struct DispatchFile {
    #[serde(default)]
    common: Option<DispatchCommon>,
    roles: HashMap<String, DispatchRole>,
}

/// A single dispatch role entry. Supports factored (domain_focus only) or
/// legacy (full content in `content`).
#[derive(Debug, Deserialize)]
struct DispatchRole {
    title: String,
    #[serde(default)]
    content: Option<String>,
    #[serde(default)]
    domain_focus: Option<String>,
    #[serde(default)]
    methodology: Option<String>,
    #[serde(default)]
    task_override: Option<String>,
    #[serde(default)]
    output_override: Option<String>,
}

// ── Output types ─────────────────────────────────────────────────────────────

#[derive(Debug, Serialize)]
/// JSON output for a protocol query.
pub struct ProtocolOutput {
    /// Title of the served content.
    pub title: String,
    /// The protocol content text.
    pub content: String,
}

#[derive(Debug, Serialize)]
/// JSON output for listing available protocol entries.
pub struct ProtocolListEntry {
    /// Protocol category.
    pub category: String,
    /// Entry key (phase name, scale, role, etc.).
    pub key: String,
    /// Human-readable title.
    pub title: String,
    /// CLI invocation to retrieve this entry.
    pub command: String,
}

// ── Query functions ──────────────────────────────────────────────────────────

/// Retrieve phase guidance for a reviewer phase.
///
/// # Errors
/// Returns an error if the embedded TOML cannot be parsed or the phase is not found.
pub fn reviewer_phase(phase: &str) -> anyhow::Result<ProtocolOutput> {
    let file: PhasesFile =
        toml::from_str(REVIEWER_TOML).map_err(|e| anyhow::anyhow!("parse reviewer.toml: {e}"))?;
    let key = phase.to_ascii_uppercase();
    let entry = file
        .phases
        .get(&key)
        .ok_or_else(|| anyhow::anyhow!("unknown reviewer phase: {phase}"))?;
    Ok(ProtocolOutput {
        title: entry.title.clone(),
        content: entry.content.clone(),
    })
}

/// Retrieve phase guidance for an applicator phase.
///
/// # Errors
/// Returns an error if the embedded TOML cannot be parsed or the phase is not found.
pub fn applicator_phase(phase: &str) -> anyhow::Result<ProtocolOutput> {
    let file: PhasesFile = toml::from_str(APPLICATOR_TOML)
        .map_err(|e| anyhow::anyhow!("parse applicator.toml: {e}"))?;
    let key = phase.to_ascii_uppercase();
    let entry = file
        .phases
        .get(&key)
        .ok_or_else(|| anyhow::anyhow!("unknown applicator phase: {phase}"))?;
    Ok(ProtocolOutput {
        title: entry.title.clone(),
        content: entry.content.clone(),
    })
}

/// Retrieve orchestrator guidance.
///
/// # Errors
/// Returns an error if the embedded TOML cannot be parsed.
pub fn orchestrator() -> anyhow::Result<ProtocolOutput> {
    let file: OrchestratorFile = toml::from_str(ORCHESTRATOR_TOML)
        .map_err(|e| anyhow::anyhow!("parse orchestrator.toml: {e}"))?;
    Ok(ProtocolOutput {
        title: file.orchestrator.title,
        content: file.orchestrator.content,
    })
}

/// Retrieve the Universal Domains reference table.
///
/// # Errors
/// Returns an error if the embedded TOML cannot be parsed.
pub fn domains() -> anyhow::Result<ProtocolOutput> {
    let file: OrchestratorFile = toml::from_str(ORCHESTRATOR_TOML)
        .map_err(|e| anyhow::anyhow!("parse orchestrator.toml: {e}"))?;
    Ok(ProtocolOutput {
        title: file.domains.title,
        content: file.domains.content,
    })
}

/// Retrieve full-cycle orchestration guidance.
///
/// # Errors
/// Returns an error if the embedded TOML cannot be parsed or the section is absent.
pub fn fullcycle() -> anyhow::Result<ProtocolOutput> {
    let file: OrchestratorFile = toml::from_str(ORCHESTRATOR_TOML)
        .map_err(|e| anyhow::anyhow!("parse orchestrator.toml: {e}"))?;
    let section = file
        .fullcycle
        .ok_or_else(|| anyhow::anyhow!("fullcycle section not found in orchestrator.toml"))?;
    Ok(ProtocolOutput {
        title: section.title,
        content: section.content,
    })
}

/// Retrieve a named optional section from orchestrator.toml.
fn orchestrator_section(
    extractor: fn(&OrchestratorFile) -> &Option<NamedSection>,
    name: &str,
) -> anyhow::Result<ProtocolOutput> {
    let file: OrchestratorFile = toml::from_str(ORCHESTRATOR_TOML)
        .map_err(|e| anyhow::anyhow!("parse orchestrator.toml: {e}"))?;
    let section = extractor(&file)
        .as_ref()
        .ok_or_else(|| anyhow::anyhow!("{name} section not found in orchestrator.toml"))?;
    Ok(ProtocolOutput {
        title: section.title.clone(),
        content: section.content.clone(),
    })
}

/// Retrieve the invocation aliases reference.
pub fn invocation_aliases() -> anyhow::Result<ProtocolOutput> {
    orchestrator_section(|f| &f.invocation_aliases, "invocation_aliases")
}

/// Retrieve the workflow selection guidance.
pub fn workflow_selection() -> anyhow::Result<ProtocolOutput> {
    orchestrator_section(|f| &f.workflow_selection, "workflow_selection")
}

/// Retrieve the quality gate rubric.
pub fn quality_gate() -> anyhow::Result<ProtocolOutput> {
    orchestrator_section(|f| &f.quality_gate, "quality_gate")
}

/// Retrieve the change classification table.
pub fn change_classification() -> anyhow::Result<ProtocolOutput> {
    orchestrator_section(|f| &f.change_classification, "change_classification")
}

/// Retrieve the static analysis integration guidance.
pub fn analyze_guidance() -> anyhow::Result<ProtocolOutput> {
    orchestrator_section(|f| &f.analyze, "analyze")
}

/// Retrieve a report template at the given scale.
///
/// # Errors
/// Returns an error if the embedded TOML cannot be parsed or the scale is not found.
pub fn report_template(scale: &str) -> anyhow::Result<ProtocolOutput> {
    let file: TemplatesFile =
        toml::from_str(TEMPLATES_TOML).map_err(|e| anyhow::anyhow!("parse templates.toml: {e}"))?;
    let key = scale.to_ascii_lowercase();
    let entry = file
        .scales
        .get(&key)
        .ok_or_else(|| anyhow::anyhow!("unknown template scale: {scale}"))?;
    Ok(ProtocolOutput {
        title: entry.title.clone(),
        content: entry.content.clone(),
    })
}

/// Retrieve a subagent dispatch prompt template for the given role.
///
/// # Errors
/// Returns an error if the embedded TOML cannot be parsed or the role is not found.
pub fn dispatch(role: &str) -> anyhow::Result<ProtocolOutput> {
    let file: DispatchFile =
        toml::from_str(DISPATCH_TOML).map_err(|e| anyhow::anyhow!("parse dispatch.toml: {e}"))?;
    let key = role.to_ascii_lowercase().replace('-', "_");
    let entry = file
        .roles
        .get(&key)
        .ok_or_else(|| {
            let mut valid: Vec<_> = file.roles.keys().map(|k| k.replace('_', "-")).collect();
            valid.sort();
            anyhow::anyhow!(
                "unknown dispatch role: {role}\n\nValid roles:\n  {}\n\nHint: run `mpcr protocol dispatch-list` to list all roles.",
                valid.join("\n  ")
            )
        })?;

    let assembled = if let Some(ref full) = entry.content {
        full.clone()
    } else if let (Some(ref common), Some(ref domain_focus)) = (&file.common, &entry.domain_focus) {
        let task = match entry.task_override.as_deref() {
            Some(t) => t,
            None => &common.task_steps,
        };
        let output = match entry.output_override.as_deref() {
            Some(o) => o,
            None => &common.output_format,
        };
        let methodology_block = entry
            .methodology
            .as_deref()
            .map_or(String::new(), |m| format!("\n## Methodology\n{}\n", m));
        let mut assembled = format!(
            "{}\n\n## Domain focus\n{}\n{}\n## Task\n{}\n\n## Output format\n{}",
            common.worker_preamble, domain_focus, methodology_block, task, output
        );
        assembled = assembled.replace("<ROLE_SLUG>", &key.replace('_', "-"));
        assembled = assembled.replace("<ROLE_TITLE>", &entry.title);
        assembled
    } else {
        return Err(anyhow::anyhow!("dispatch role {role}: missing both content and domain_focus+common"));
    };

    Ok(ProtocolOutput {
        title: entry.title.clone(),
        content: assembled,
    })
}

/// List all available dispatch roles.
pub fn dispatch_list() -> anyhow::Result<Vec<String>> {
    let file: DispatchFile =
        toml::from_str(DISPATCH_TOML).map_err(|e| anyhow::anyhow!("parse dispatch.toml: {e}"))?;
    let mut roles: Vec<String> = file.roles.keys().map(|k| k.replace('_', "-")).collect();
    roles.sort();
    Ok(roles)
}

/// List all available protocol entries.
///
/// # Errors
/// Returns an error if any embedded TOML cannot be parsed.
pub fn list_entries() -> anyhow::Result<Vec<ProtocolListEntry>> {
    let mut entries = Vec::new();

    let reviewer: PhasesFile =
        toml::from_str(REVIEWER_TOML).map_err(|e| anyhow::anyhow!("parse reviewer.toml: {e}"))?;
    let mut reviewer_keys: Vec<_> = reviewer.phases.keys().cloned().collect();
    reviewer_keys.sort();
    for key in reviewer_keys {
        if let Some(phase) = reviewer.phases.get(&key) {
            entries.push(ProtocolListEntry {
                category: "reviewer".to_string(),
                key: key.clone(),
                title: phase.title.clone(),
                command: format!("mpcr protocol reviewer --phase {key}"),
            });
        }
    }

    let applicator: PhasesFile = toml::from_str(APPLICATOR_TOML)
        .map_err(|e| anyhow::anyhow!("parse applicator.toml: {e}"))?;
    let mut applicator_keys: Vec<_> = applicator.phases.keys().cloned().collect();
    applicator_keys.sort();
    for key in applicator_keys {
        if let Some(phase) = applicator.phases.get(&key) {
            entries.push(ProtocolListEntry {
                category: "applicator".to_string(),
                key: key.clone(),
                title: phase.title.clone(),
                command: format!("mpcr protocol applicator --phase {key}"),
            });
        }
    }

    entries.push(ProtocolListEntry {
        category: "orchestrator".to_string(),
        key: "orchestrator".to_string(),
        title: "Multi-Agent Orchestration".to_string(),
        command: "mpcr protocol orchestrator".to_string(),
    });
    entries.push(ProtocolListEntry {
        category: "orchestrator".to_string(),
        key: "fullcycle".to_string(),
        title: "Full-Cycle Convergence".to_string(),
        command: "mpcr protocol fullcycle".to_string(),
    });
    let orchestrator: OrchestratorFile = toml::from_str(ORCHESTRATOR_TOML)
        .map_err(|e| anyhow::anyhow!("parse orchestrator.toml: {e}"))?;
    entries.push(ProtocolListEntry {
        category: "orchestrator".to_string(),
        key: "domains".to_string(),
        title: orchestrator.domains.title,
        command: "mpcr protocol domains".to_string(),
    });
    for (key, cmd, section) in [
        ("invocation-aliases", "mpcr protocol invocation-aliases", &orchestrator.invocation_aliases),
        ("workflow-selection", "mpcr protocol workflow-selection", &orchestrator.workflow_selection),
        ("quality-gate", "mpcr protocol quality-gate", &orchestrator.quality_gate),
        ("change-classification", "mpcr protocol change-classification", &orchestrator.change_classification),
        ("analyze", "mpcr protocol analyze-guidance", &orchestrator.analyze),
    ] {
        if let Some(ref s) = section {
            entries.push(ProtocolListEntry {
                category: "orchestrator".to_string(),
                key: key.to_string(),
                title: s.title.clone(),
                command: cmd.to_string(),
            });
        }
    }

    let templates: TemplatesFile =
        toml::from_str(TEMPLATES_TOML).map_err(|e| anyhow::anyhow!("parse templates.toml: {e}"))?;
    let mut template_keys: Vec<_> = templates.scales.keys().cloned().collect();
    template_keys.sort();
    for key in template_keys {
        if let Some(scale) = templates.scales.get(&key) {
            entries.push(ProtocolListEntry {
                category: "report-template".to_string(),
                key: key.clone(),
                title: scale.title.clone(),
                command: format!("mpcr protocol report-template --scale {key}"),
            });
        }
    }

    let dispatch_file: DispatchFile =
        toml::from_str(DISPATCH_TOML).map_err(|e| anyhow::anyhow!("parse dispatch.toml: {e}"))?;
    let mut dispatch_keys: Vec<String> = dispatch_file.roles.keys().cloned().collect();
    dispatch_keys.sort();
    for key in dispatch_keys {
        if let Some(role) = dispatch_file.roles.get(&key) {
            let cli_key = key.replace('_', "-");
            entries.push(ProtocolListEntry {
                category: "dispatch".to_string(),
                key: key.clone(),
                title: role.title.clone(),
                command: format!("mpcr protocol dispatch --role {cli_key}"),
            });
        }
    }

    let session_file: PhasesFile =
        toml::from_str(SESSION_TOML).map_err(|e| anyhow::anyhow!("parse session.toml: {e}"))?;
    let mut session_keys: Vec<_> = session_file.phases.keys().cloned().collect();
    session_keys.sort();
    for key in session_keys {
        if let Some(phase) = session_file.phases.get(&key) {
            entries.push(ProtocolListEntry {
                category: "session".to_string(),
                key: key.clone(),
                title: phase.title.clone(),
                command: format!("mpcr protocol session --phase {key}"),
            });
        }
    }
    Ok(entries)
}

/// Retrieve phase guidance for a session management phase.
///
/// # Errors
/// Returns an error if the embedded TOML cannot be parsed or the phase is not found.
pub fn session_phase(phase: &str) -> anyhow::Result<ProtocolOutput> {
    let file: PhasesFile =
        toml::from_str(SESSION_TOML).map_err(|e| anyhow::anyhow!("parse session.toml: {e}"))?;
    let key = phase.to_ascii_uppercase();
    let entry = file
        .phases
        .get(&key)
        .ok_or_else(|| anyhow::anyhow!("unknown session phase: {phase}"))?;
    Ok(ProtocolOutput {
        title: entry.title.clone(),
        content: entry.content.clone(),
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use anyhow::ensure;

    #[test]
    fn reviewer_phases_parse() -> anyhow::Result<()> {
        let phases = [
            "INGESTION",
            "DOMAIN_COVERAGE",
            "THEOREM_GENERATION",
            "ADVERSARIAL_PROOFS",
            "SYNTHESIS",
            "REPORT_WRITING",
        ];
        for phase in phases {
            let out = reviewer_phase(phase)?;
            ensure!(!out.title.is_empty(), "empty title for {phase}");
            ensure!(!out.content.is_empty(), "empty content for {phase}");
        }
        Ok(())
    }

    #[test]
    fn applicator_phases_parse() -> anyhow::Result<()> {
        let phases = ["INGESTION", "DISPOSITION", "APPLICATION", "FINALIZATION"];
        for phase in phases {
            let out = applicator_phase(phase)?;
            ensure!(!out.title.is_empty(), "empty title for {phase}");
            ensure!(!out.content.is_empty(), "empty content for {phase}");
        }
        Ok(())
    }

    #[test]
    fn orchestrator_parses() -> anyhow::Result<()> {
        let out = orchestrator()?;
        ensure!(!out.content.is_empty());
        Ok(())
    }

    #[test]
    fn domains_parses() -> anyhow::Result<()> {
        let out = domains()?;
        ensure!(out.content.contains("Architecture"));
        ensure!(out.content.contains("Security"));
        Ok(())
    }

    #[test]
    fn report_templates_parse() -> anyhow::Result<()> {
        for scale in ["compact", "standard", "full"] {
            let out = report_template(scale)?;
            ensure!(!out.content.is_empty(), "empty template for {scale}");
        }
        Ok(())
    }

    #[test]
    fn dispatch_templates_parse() -> anyhow::Result<()> {
        let roles = [
            "architecture_critic",
            "contract_guardian",
            "data_integrity_prover",
            "error_path_tracer",
            "security_adversary",
            "concurrency_prover",
            "performance_profiler",
            "observability_oncall",
            "test_strategist",
            "docs_consumer",
            "dependency_auditor",
            "supply_chain_auditor",
            "auth_access_prover",
            "crypto_secrets_auditor",
            "injection_hunter",
            "infra_runtime_auditor",
            "data_privacy_guardian",
            "domain_specialist",
            "fresh_eyes",
            "holistic_integrator",
            "applicator_worker",
            "applicator_verifier",
            "complexity_analyst",
            "overengineering_guard",
            "ship_readiness_assessor",
        ];
        for role in roles {
            let out = dispatch(role)?;
            ensure!(!out.content.is_empty(), "empty dispatch for {role}");
        }
        Ok(())
    }

    #[test]
    fn list_entries_returns_all() -> anyhow::Result<()> {
        let entries = list_entries()?;
        // 9 reviewer + 4 applicator + 3 orchestrator + 3 templates + 25 dispatch + 1 session = 45
        ensure!(
            entries.len() >= 40,
            "expected >= 37 entries, got {}",
            entries.len()
        );
        Ok(())
    }

    #[test]
    fn fullcycle_parses() -> anyhow::Result<()> {
        let out = fullcycle()?;
        ensure!(out.content.contains("Convergence"));
        ensure!(out.content.contains("fresh subagents"));
        Ok(())
    }

    #[test]
    fn unknown_phase_errors() -> anyhow::Result<()> {
        ensure!(reviewer_phase("NONEXISTENT").is_err());
        ensure!(applicator_phase("NONEXISTENT").is_err());
        ensure!(report_template("NONEXISTENT").is_err());
        ensure!(dispatch("NONEXISTENT").is_err());
        Ok(())
    }
}
