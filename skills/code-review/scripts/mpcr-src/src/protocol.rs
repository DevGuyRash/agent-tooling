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
}

#[derive(Debug, Deserialize)]
/// TOML structure for `templates.toml`.
struct TemplatesFile {
    scales: HashMap<String, NamedSection>,
}

#[derive(Debug, Deserialize)]
/// TOML structure for `dispatch.toml`.
struct DispatchFile {
    roles: HashMap<String, NamedSection>,
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
    let file: PhasesFile = toml::from_str(REVIEWER_TOML)
        .map_err(|e| anyhow::anyhow!("parse reviewer.toml: {e}"))?;
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

/// Retrieve a report template at the given scale.
///
/// # Errors
/// Returns an error if the embedded TOML cannot be parsed or the scale is not found.
pub fn report_template(scale: &str) -> anyhow::Result<ProtocolOutput> {
    let file: TemplatesFile = toml::from_str(TEMPLATES_TOML)
        .map_err(|e| anyhow::anyhow!("parse templates.toml: {e}"))?;
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
    let file: DispatchFile = toml::from_str(DISPATCH_TOML)
        .map_err(|e| anyhow::anyhow!("parse dispatch.toml: {e}"))?;
    let key = role.to_ascii_lowercase().replace('-', "_");
    let entry = file
        .roles
        .get(&key)
        .ok_or_else(|| anyhow::anyhow!("unknown dispatch role: {role}"))?;
    Ok(ProtocolOutput {
        title: entry.title.clone(),
        content: entry.content.clone(),
    })
}

/// List all available protocol entries.
///
/// # Errors
/// Returns an error if any embedded TOML cannot be parsed.
pub fn list_entries() -> anyhow::Result<Vec<ProtocolListEntry>> {
    let mut entries = Vec::new();

    let reviewer: PhasesFile = toml::from_str(REVIEWER_TOML)
        .map_err(|e| anyhow::anyhow!("parse reviewer.toml: {e}"))?;
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
        key: "domains".to_string(),
        title: "Universal Domains".to_string(),
        command: "mpcr protocol domains".to_string(),
    });

    let templates: TemplatesFile = toml::from_str(TEMPLATES_TOML)
        .map_err(|e| anyhow::anyhow!("parse templates.toml: {e}"))?;
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

    let dispatch_file: DispatchFile = toml::from_str(DISPATCH_TOML)
        .map_err(|e| anyhow::anyhow!("parse dispatch.toml: {e}"))?;
    let mut dispatch_keys: Vec<_> = dispatch_file.roles.keys().cloned().collect();
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

    Ok(entries)
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
        for role in ["scope_mapper", "red_team", "systems_auditor"] {
            let out = dispatch(role)?;
            ensure!(!out.content.is_empty(), "empty dispatch for {role}");
        }
        Ok(())
    }

    #[test]
    fn list_entries_returns_all() -> anyhow::Result<()> {
        let entries = list_entries()?;
        // At least: 6 reviewer + 4 applicator + 2 orchestrator + 3 templates + 3 dispatch = 18
        ensure!(entries.len() >= 18, "expected >= 18 entries, got {}", entries.len());
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
