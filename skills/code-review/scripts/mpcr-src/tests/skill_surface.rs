#![allow(missing_docs)]
#![allow(clippy::indexing_slicing)]

use anyhow::{ensure, Context};
use std::fs;
use std::path::{Path, PathBuf};

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
fn skill_router_is_v2_sized_and_v2_only() -> anyhow::Result<()> {
    let root = skill_root()?;
    let skill_md = read(&root, "SKILL.md")?;
    ensure!(skill_md.lines().count() <= 120);
    let route_pos = skill_md
        .find("mpcr route --mode")
        .ok_or_else(|| anyhow::anyhow!("SKILL.md is missing route-first bootstrap"))?;
    let mode_pos = skill_md
        .find("mpcr protocol mode --mode")
        .ok_or_else(|| anyhow::anyhow!("SKILL.md is missing mode pack guidance"))?;
    ensure!(route_pos < mode_pos);
    ensure!(skill_md.contains("auto-builds the Rust binary"));
    ensure!(skill_md.contains("cargo"));
    ensure!(skill_md.contains("mpcr route --persist"));
    ensure!(skill_md.contains("mpcr protocol mode --mode"));
    ensure!(skill_md.contains("mpcr validate --artifact-file"));
    ensure!(skill_md.contains("mpcr render --artifact-file"));
    ensure!(skill_md.contains("mpcr fullcycle plan"));
    ensure!(!skill_md.contains("proof_packet"));
    ensure!(!skill_md.contains("validate-report"));
    ensure!(!skill_md.contains("dispatch --role"));
    Ok(())
}

#[test]
fn openai_manifest_matches_v2_surface() -> anyhow::Result<()> {
    let root = skill_root()?;
    let manifest = read(&root, "agents/openai.yaml")?;
    ensure!(manifest.contains("display_name: \"Code Review\""));
    ensure!(manifest.contains("mpcr route"));
    ensure!(manifest.contains("mpcr protocol mode"));
    ensure!(manifest.contains("mpcr reviewer"));
    ensure!(manifest.contains("mpcr applicator"));
    ensure!(manifest.contains("mpcr fullcycle"));
    ensure!(!manifest.contains("dispatch"));
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
