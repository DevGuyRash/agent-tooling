//! Static `mpcr protocol ...` retrieval for structured v2 policy objects.
#![allow(missing_docs)]

use crate::artifacts::{PolicyCategory, PolicyView};
use crate::policy_store::{
    generate_applicator_fallback, generate_fullcycle_fallback, generate_orchestrator_fallback,
    generate_reviewer_fallback, PolicyListEntry, PolicyStore,
};
use serde::Serialize;
use std::fs;
use std::path::Path;

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
/// Text protocol response for one static policy lookup.
pub struct ProtocolOutput {
    pub category: PolicyCategory,
    pub id: String,
    pub view: PolicyView,
    pub content: String,
}

/// Return the structured protocol list in stable order.
pub fn list() -> anyhow::Result<Vec<PolicyListEntry>> {
    Ok(PolicyStore::load()?.list())
}

/// Return one static mode policy view.
pub fn mode(mode: &str, view: PolicyView) -> anyhow::Result<ProtocolOutput> {
    let store = PolicyStore::load()?;
    Ok(ProtocolOutput {
        category: PolicyCategory::Mode,
        id: mode.to_string(),
        view,
        content: store.render(PolicyCategory::Mode, mode, view)?,
    })
}

/// Return one static worker policy view.
pub fn worker(kind: &str, view: PolicyView) -> anyhow::Result<ProtocolOutput> {
    let store = PolicyStore::load()?;
    Ok(ProtocolOutput {
        category: PolicyCategory::Worker,
        id: kind.to_string(),
        view,
        content: store.render(PolicyCategory::Worker, kind, view)?,
    })
}

/// Return one static module policy view.
pub fn module(id: &str, view: PolicyView) -> anyhow::Result<ProtocolOutput> {
    let store = PolicyStore::load()?;
    Ok(ProtocolOutput {
        category: PolicyCategory::Module,
        id: id.to_string(),
        view,
        content: store.render(PolicyCategory::Module, id, view)?,
    })
}

/// Return one static escalation policy view.
pub fn escalation(id: &str, view: PolicyView) -> anyhow::Result<ProtocolOutput> {
    let store = PolicyStore::load()?;
    Ok(ProtocolOutput {
        category: PolicyCategory::Escalation,
        id: id.to_string(),
        view,
        content: store.render(PolicyCategory::Escalation, id, view)?,
    })
}

/// Generated reviewer fallback doc.
pub fn reviewer_fallback_doc() -> anyhow::Result<String> {
    generate_reviewer_fallback(&PolicyStore::load()?)
}

/// Generated applicator fallback doc.
pub fn applicator_fallback_doc() -> anyhow::Result<String> {
    generate_applicator_fallback(&PolicyStore::load()?)
}

/// Generated full-cycle fallback doc.
pub fn fullcycle_fallback_doc() -> anyhow::Result<String> {
    generate_fullcycle_fallback(&PolicyStore::load()?)
}

/// Generated orchestrator fallback doc.
pub fn orchestrator_fallback_doc() -> anyhow::Result<String> {
    generate_orchestrator_fallback(&PolicyStore::load()?)
}

/// Materialize generated fallback docs under the skill `references/` directory.
pub fn materialize_fallback_docs(skill_root: &Path) -> anyhow::Result<()> {
    let references_dir = skill_root.join("references");
    fs::create_dir_all(&references_dir)?;
    fs::write(
        references_dir.join("reviewer-fallback.md"),
        reviewer_fallback_doc()?,
    )?;
    fs::write(
        references_dir.join("applicator-fallback.md"),
        applicator_fallback_doc()?,
    )?;
    fs::write(
        references_dir.join("fullcycle-fallback.md"),
        fullcycle_fallback_doc()?,
    )?;
    fs::write(
        references_dir.join("orchestrator-fallback.md"),
        orchestrator_fallback_doc()?,
    )?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use anyhow::ensure;
    use tempfile::tempdir;

    #[test]
    fn list_and_lookup_are_static() -> anyhow::Result<()> {
        let entries = list()?;
        ensure!(entries.iter().any(|entry| entry.id == "reviewer"));
        let output = mode("reviewer", PolicyView::Brief)?;
        ensure!(output.content.contains("reviewer"));
        let worker_output = worker("review-composite", PolicyView::Checklist)?;
        ensure!(worker_output.content.contains("## Must"));
        Ok(())
    }

    #[test]
    fn materialize_fallback_docs_writes_generated_files() -> anyhow::Result<()> {
        let skill_root = tempdir()?;
        materialize_fallback_docs(skill_root.path())?;
        ensure!(skill_root
            .path()
            .join("references/reviewer-fallback.md")
            .exists());
        ensure!(skill_root
            .path()
            .join("references/applicator-fallback.md")
            .exists());
        ensure!(skill_root
            .path()
            .join("references/fullcycle-fallback.md")
            .exists());
        ensure!(skill_root
            .path()
            .join("references/orchestrator-fallback.md")
            .exists());
        Ok(())
    }
}
