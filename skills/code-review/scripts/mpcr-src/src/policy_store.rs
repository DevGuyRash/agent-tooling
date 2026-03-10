//! Structured policy store and progressive-disclosure views.
#![allow(missing_docs)]

use crate::artifacts::{PolicyCategory, PolicyView};
use anyhow::Context;
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

const MODES_TOML: &str = include_str!("../protocols/v2/modes.toml");
const WORKERS_TOML: &str = include_str!("../protocols/v2/workers.toml");
const MODULES_TOML: &str = include_str!("../protocols/v2/modules.toml");
const ESCALATIONS_TOML: &str = include_str!("../protocols/v2/escalations.toml");

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
/// Structured source-of-truth policy object.
pub struct PolicyObject {
    pub id: String,
    pub version: String,
    pub summary: String,
    #[serde(default)]
    pub must: Vec<String>,
    #[serde(default)]
    pub must_not: Vec<String>,
    #[serde(default)]
    pub inputs: Vec<String>,
    #[serde(default)]
    pub outputs: Vec<String>,
    #[serde(default)]
    pub checks: Vec<String>,
    #[serde(default)]
    pub stop_when: Vec<String>,
    #[serde(default)]
    pub escalate_when: Vec<String>,
    #[serde(default)]
    pub anti_patterns: Vec<String>,
    #[serde(default)]
    pub examples: Vec<String>,
    #[serde(default)]
    pub schema: Vec<String>,
}

#[derive(Debug, Deserialize)]
struct PolicyFile {
    #[serde(rename = "policy")]
    policies: Vec<PolicyObject>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
/// One list entry for the `mpcr protocol list` surface.
pub struct PolicyListEntry {
    pub category: PolicyCategory,
    pub id: String,
    pub version: String,
}

#[derive(Debug, Clone, Default)]
/// In-memory policy store keyed by category and id.
pub struct PolicyStore {
    modes: BTreeMap<String, PolicyObject>,
    workers: BTreeMap<String, PolicyObject>,
    modules: BTreeMap<String, PolicyObject>,
    escalations: BTreeMap<String, PolicyObject>,
}

fn parse_policy_file(body: &str) -> anyhow::Result<Vec<PolicyObject>> {
    let file: PolicyFile = toml::from_str(body).context("parse policy file")?;
    Ok(file.policies)
}

fn render_section(lines: &mut Vec<String>, title: &str, items: &[String]) {
    if items.is_empty() {
        return;
    }
    lines.push(format!("## {title}"));
    for item in items {
        lines.push(format!("- {item}"));
    }
    lines.push(String::new());
}

fn enforce_budget(view: PolicyView, lines: &[String]) -> anyhow::Result<()> {
    let limit = match view {
        PolicyView::Brief => 25,
        PolicyView::Checklist => 60,
        PolicyView::Schema => 120,
        PolicyView::Examples => 80,
        PolicyView::Full => 220,
    };
    anyhow::ensure!(
        lines.len() <= limit,
        "error: rendered `{view:?}` policy view exceeded {limit} lines"
    );
    Ok(())
}

fn render_policy_view(policy: &PolicyObject, view: PolicyView) -> anyhow::Result<String> {
    let mut lines = Vec::new();
    match view {
        PolicyView::Brief => {
            lines.push(format!("# {}", policy.id));
            lines.push(format!("version: {}", policy.version));
            lines.push(policy.summary.clone());
            lines.push(String::new());
            for item in policy.must.iter().take(3) {
                lines.push(format!("- must: {item}"));
            }
        }
        PolicyView::Checklist => {
            lines.push(format!("# {}", policy.id));
            lines.push(format!("version: {}", policy.version));
            lines.push(policy.summary.clone());
            lines.push(String::new());
            render_section(&mut lines, "Must", &policy.must);
            render_section(&mut lines, "Must Not", &policy.must_not);
            render_section(&mut lines, "Checks", &policy.checks);
            render_section(&mut lines, "Stop When", &policy.stop_when);
            render_section(&mut lines, "Escalate When", &policy.escalate_when);
        }
        PolicyView::Schema => {
            lines.push(format!("# {}", policy.id));
            lines.push(format!("version: {}", policy.version));
            lines.push("## Inputs".to_string());
            for input in &policy.inputs {
                lines.push(format!("- {input}"));
            }
            lines.push(String::new());
            lines.push("## Outputs".to_string());
            for output in &policy.outputs {
                lines.push(format!("- {output}"));
            }
            lines.push(String::new());
            lines.push("## Schema".to_string());
            for field in &policy.schema {
                lines.push(format!("- {field}"));
            }
        }
        PolicyView::Examples => {
            lines.push(format!("# {}", policy.id));
            lines.push(format!("version: {}", policy.version));
            lines.push("## Examples".to_string());
            for example in policy.examples.iter().take(2) {
                lines.push(format!("- {example}"));
            }
        }
        PolicyView::Full => {
            lines.push(format!("# {}", policy.id));
            lines.push(format!("version: {}", policy.version));
            lines.push(policy.summary.clone());
            lines.push(String::new());
            render_section(&mut lines, "Must", &policy.must);
            render_section(&mut lines, "Must Not", &policy.must_not);
            render_section(&mut lines, "Inputs", &policy.inputs);
            render_section(&mut lines, "Outputs", &policy.outputs);
            render_section(&mut lines, "Checks", &policy.checks);
            render_section(&mut lines, "Stop When", &policy.stop_when);
            render_section(&mut lines, "Escalate When", &policy.escalate_when);
            render_section(&mut lines, "Anti Patterns", &policy.anti_patterns);
            render_section(
                &mut lines,
                "Examples",
                &policy.examples.iter().take(2).cloned().collect::<Vec<_>>(),
            );
            render_section(&mut lines, "Schema", &policy.schema);
        }
    }
    enforce_budget(view, &lines)?;
    Ok(lines.join("\n").trim_end().to_string())
}

impl PolicyStore {
    /// Load the structured policy store from the bundled TOML source files.
    ///
    /// # Errors
    /// Returns an error if any bundled policy file fails to parse.
    pub fn load() -> anyhow::Result<Self> {
        let mut store = Self::default();
        for policy in parse_policy_file(MODES_TOML)? {
            store.modes.insert(policy.id.clone(), policy);
        }
        for policy in parse_policy_file(WORKERS_TOML)? {
            store.workers.insert(policy.id.clone(), policy);
        }
        for policy in parse_policy_file(MODULES_TOML)? {
            store.modules.insert(policy.id.clone(), policy);
        }
        for policy in parse_policy_file(ESCALATIONS_TOML)? {
            store.escalations.insert(policy.id.clone(), policy);
        }
        Ok(store)
    }

    fn map_for_category(&self, category: PolicyCategory) -> &BTreeMap<String, PolicyObject> {
        match category {
            PolicyCategory::Mode => &self.modes,
            PolicyCategory::Worker => &self.workers,
            PolicyCategory::Module => &self.modules,
            PolicyCategory::Escalation => &self.escalations,
        }
    }

    /// Retrieve a policy object by category and id.
    pub fn get(&self, category: PolicyCategory, id: &str) -> anyhow::Result<&PolicyObject> {
        self.map_for_category(category)
            .get(id)
            .ok_or_else(|| anyhow::anyhow!("error: unknown {:?} policy `{id}`", category))
    }

    /// Render a policy into the requested view.
    pub fn render(
        &self,
        category: PolicyCategory,
        id: &str,
        view: PolicyView,
    ) -> anyhow::Result<String> {
        let policy = self.get(category, id)?;
        render_policy_view(policy, view)
    }

    /// List all available policy ids and versions in stable order.
    #[must_use]
    pub fn list(&self) -> Vec<PolicyListEntry> {
        let mut entries = Vec::new();
        for (category, map) in [
            (PolicyCategory::Mode, &self.modes),
            (PolicyCategory::Worker, &self.workers),
            (PolicyCategory::Module, &self.modules),
            (PolicyCategory::Escalation, &self.escalations),
        ] {
            for policy in map.values() {
                entries.push(PolicyListEntry {
                    category,
                    id: policy.id.clone(),
                    version: policy.version.clone(),
                });
            }
        }
        entries
    }
}

fn compose_doc(title: &str, sections: &[String]) -> String {
    let mut lines = vec![format!("# {title}"), String::new()];
    for section in sections {
        lines.push(section.clone());
        lines.push(String::new());
    }
    lines.join("\n").trim_end().to_string()
}

/// Generate the reviewer fallback doc from the structured policy store.
pub fn generate_reviewer_fallback(store: &PolicyStore) -> anyhow::Result<String> {
    let sections = vec![
        store.render(PolicyCategory::Mode, "reviewer", PolicyView::Full)?,
        "Canonical artifact examples for manual reviewer flows live at `<skills-file-root>/references/reviewer-artifact-examples.md` with machine-valid TOML under `<skills-file-root>/references/examples/`.".to_string(),
        store.render(
            PolicyCategory::Worker,
            "review-composite",
            PolicyView::Checklist,
        )?,
        store.render(
            PolicyCategory::Worker,
            "invariant-challenger",
            PolicyView::Checklist,
        )?,
        store.render(
            PolicyCategory::Worker,
            "release-risk-assessor",
            PolicyView::Checklist,
        )?,
        store.render(
            PolicyCategory::Module,
            "core-correctness",
            PolicyView::Checklist,
        )?,
        store.render(
            PolicyCategory::Module,
            "ship-readiness",
            PolicyView::Checklist,
        )?,
    ];
    Ok(compose_doc("Reviewer Fallback", &sections))
}

/// Generate the applicator fallback doc from the structured policy store.
pub fn generate_applicator_fallback(store: &PolicyStore) -> anyhow::Result<String> {
    let sections = vec![
        store.render(PolicyCategory::Mode, "applicator", PolicyView::Full)?,
        store.render(
            PolicyCategory::Worker,
            "apply-composite",
            PolicyView::Checklist,
        )?,
        store.render(
            PolicyCategory::Worker,
            "applicator-worker",
            PolicyView::Checklist,
        )?,
        store.render(
            PolicyCategory::Worker,
            "applicator-verifier",
            PolicyView::Checklist,
        )?,
        store.render(
            PolicyCategory::Escalation,
            "malformed-output",
            PolicyView::Checklist,
        )?,
    ];
    Ok(compose_doc("Applicator Fallback", &sections))
}

/// Generate the full-cycle fallback doc from the structured policy store.
pub fn generate_fullcycle_fallback(store: &PolicyStore) -> anyhow::Result<String> {
    let sections = vec![
        store.render(PolicyCategory::Mode, "full-cycle", PolicyView::Full)?,
        store.render(PolicyCategory::Escalation, "reopen", PolicyView::Checklist)?,
        store.render(
            PolicyCategory::Module,
            "docs-staleness",
            PolicyView::Checklist,
        )?,
    ];
    Ok(compose_doc("Full-Cycle Fallback", &sections))
}

/// Generate the routing/orchestrator fallback doc from the structured policy store.
pub fn generate_orchestrator_fallback(store: &PolicyStore) -> anyhow::Result<String> {
    let sections = vec![
        "Use semantic routing first. Load mode second. Load worker and module packs only for the selected route. Load escalation packs only after triggers fire. Load examples only on uncertainty, malformed output, retry, or explicit request.".to_string(),
        store.render(PolicyCategory::Worker, "surface-mapper", PolicyView::Checklist)?,
        store.render(PolicyCategory::Worker, "contract-comparer", PolicyView::Checklist)?,
        store.render(PolicyCategory::Worker, "exploit-tracer", PolicyView::Checklist)?,
        store.render(PolicyCategory::Worker, "congruence-checker", PolicyView::Checklist)?,
        store.render(PolicyCategory::Worker, "simplification-checker", PolicyView::Checklist)?,
    ];
    Ok(compose_doc("Orchestrator Fallback", &sections))
}

#[cfg(test)]
mod tests {
    use super::*;
    use anyhow::ensure;

    #[test]
    fn policy_views_respect_budgets_and_ids_are_stable() -> anyhow::Result<()> {
        let store = PolicyStore::load()?;
        let reviewer = store.get(PolicyCategory::Mode, "reviewer")?;
        ensure!(reviewer.version == "2026.03.08");
        for view in [
            PolicyView::Brief,
            PolicyView::Checklist,
            PolicyView::Schema,
            PolicyView::Examples,
            PolicyView::Full,
        ] {
            let rendered = store.render(PolicyCategory::Mode, "reviewer", view)?;
            ensure!(!rendered.is_empty());
        }
        ensure!(store.list().iter().any(|entry| entry.id == "full-cycle"));
        Ok(())
    }
}
