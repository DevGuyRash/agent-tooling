#![allow(missing_docs)]
#![allow(clippy::all, clippy::pedantic, clippy::nursery, clippy::cargo)]
#![allow(clippy::indexing_slicing)]

use anyhow::{ensure, Context};
use mpcr::artifacts::ArtifactKind;
use mpcr::paths::{artifact_path, ensure_session_layout, session_paths};
use mpcr::validate::{validate_artifact_file, ValidationLayer};
use std::fs;
use std::path::{Path, PathBuf};
use tempfile::tempdir;
use time::{Date, Month};

fn skill_root() -> anyhow::Result<PathBuf> {
    let manifest = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    manifest
        .parent()
        .and_then(Path::parent)
        .map(Path::to_path_buf)
        .ok_or_else(|| anyhow::anyhow!("failed to resolve skill root"))
}

fn normalize(text: &str) -> String {
    text.replace("\r\n", "\n").trim_end().to_string()
}

fn read(root: &Path, rel: &str) -> anyhow::Result<String> {
    fs::read_to_string(root.join(rel)).with_context(|| format!("read {}", rel))
}

#[test]
fn skill_router_restores_dispatch_and_recursive_reports() -> anyhow::Result<()> {
    let root = skill_root()?;
    let skill_md = read(&root, "SKILL.md")?;
    ensure!(skill_md.lines().count() <= 140);
    let route_pos = skill_md
        .find("mpcr route --mode")
        .ok_or_else(|| anyhow::anyhow!("SKILL.md is missing route-first bootstrap"))?;
    let dispatch_pos = skill_md
        .find("mpcr protocol dispatch --role")
        .ok_or_else(|| anyhow::anyhow!("SKILL.md is missing dispatch guidance"))?;
    ensure!(route_pos < dispatch_pos);
    ensure!(skill_md.contains("auto-builds the Rust binary"));
    ensure!(skill_md.contains("cargo"));
    ensure!(skill_md.contains("mpcr route --persist"));
    ensure!(skill_md.contains("mpcr protocol mode --mode"));
    ensure!(skill_md.contains("mpcr protocol dispatch --role"));
    ensure!(skill_md.contains("_session.json"));
    ensure!(skill_md.contains("mpcr session reports"));
    ensure!(skill_md.contains("mpcr session artifacts"));
    ensure!(skill_md.contains("mpcr validate --artifact-file"));
    ensure!(skill_md.contains("mpcr render --artifact-file"));
    ensure!(skill_md.contains("mpcr fullcycle plan"));
    ensure!(!skill_md.contains("proof_packet"));
    ensure!(!skill_md.contains("validate-report"));
    Ok(())
}

#[test]
fn openai_manifest_matches_recursive_surface() -> anyhow::Result<()> {
    let root = skill_root()?;
    let manifest = read(&root, "agents/openai.yaml")?;
    ensure!(manifest.contains("display_name: \"Code Review\""));
    ensure!(manifest.contains("mpcr route"));
    ensure!(manifest.contains("mpcr protocol dispatch"));
    ensure!(manifest.contains("mpcr reviewer"));
    ensure!(manifest.contains("mpcr applicator"));
    ensure!(manifest.contains("mpcr fullcycle"));
    ensure!(manifest.contains("mpcr session reports"));
    ensure!(manifest.contains("mpcr session artifacts"));
    ensure!(!manifest.contains("proof_packet"));
    Ok(())
}

#[test]
fn fallback_docs_match_generated_policy_docs() -> anyhow::Result<()> {
    let root = skill_root()?;
    ensure!(
        normalize(&read(&root, "references/reviewer-fallback.md")?)
            == normalize(&mpcr::protocol::reviewer_fallback_doc()?)
    );
    ensure!(
        normalize(&read(&root, "references/applicator-fallback.md")?)
            == normalize(&mpcr::protocol::applicator_fallback_doc()?)
    );
    ensure!(
        normalize(&read(&root, "references/fullcycle-fallback.md")?)
            == normalize(&mpcr::protocol::fullcycle_fallback_doc()?)
    );
    ensure!(
        normalize(&read(&root, "references/orchestrator-fallback.md")?)
            == normalize(&mpcr::protocol::orchestrator_fallback_doc()?)
    );
    Ok(())
}

#[test]
fn only_structured_v2_protocol_files_remain() -> anyhow::Result<()> {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let protocols_dir = root.join("protocols");
    let mut files = Vec::new();
    for entry in fs::read_dir(&protocols_dir)? {
        let entry = entry?;
        if entry.path().is_file() {
            files.push(entry.file_name().to_string_lossy().into_owned());
        }
    }
    ensure!(
        files.is_empty(),
        "found unexpected legacy protocol files: {:?}",
        files
    );
    ensure!(protocols_dir.join("v2/modes.toml").exists());
    ensure!(protocols_dir.join("v2/workers.toml").exists());
    ensure!(protocols_dir.join("v2/modules.toml").exists());
    ensure!(protocols_dir.join("v2/escalations.toml").exists());
    Ok(())
}

#[test]
fn reviewer_artifact_examples_are_machine_valid() -> anyhow::Result<()> {
    let root = skill_root()?;
    let temp = tempdir()?;
    let date = Date::from_calendar_date(2026, Month::March, 8)?;
    let session_dir = session_paths(temp.path(), date).session_dir;
    ensure_session_layout(&session_dir)?;

    let child_example = root.join("references/examples/reviewer-child-findings.toml");
    let child_summary = validate_artifact_file(
        &child_example,
        ArtifactKind::ChildFindings,
        ValidationLayer::Hard,
        Some(&session_dir),
    )?;
    ensure!(child_summary.errors.is_empty());

    let persisted_child = artifact_path(
        &session_dir,
        ArtifactKind::ChildFindings,
        "73078a595848",
        mpcr::paths::StorageFormat::Toml,
    );
    fs::copy(&child_example, &persisted_child)?;

    let parent_example = root.join("references/examples/reviewer-parent-review.toml");
    let parent_summary = validate_artifact_file(
        &parent_example,
        ArtifactKind::ParentReview,
        ValidationLayer::Hard,
        Some(&session_dir),
    )?;
    ensure!(parent_summary.errors.is_empty());
    Ok(())
}

#[test]
fn skill_docs_reference_reviewer_artifact_examples() -> anyhow::Result<()> {
    let root = skill_root()?;
    let skill_md = read(&root, "SKILL.md")?;
    ensure!(skill_md.contains("references/reviewer-artifact-examples.md"));

    let fallback = read(&root, "references/reviewer-fallback.md")?;
    ensure!(fallback.contains("references/reviewer-artifact-examples.md"));
    ensure!(root
        .join("references/examples/reviewer-child-findings.toml")
        .exists());
    ensure!(root
        .join("references/examples/reviewer-parent-review.toml")
        .exists());
    Ok(())
}
