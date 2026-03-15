#![allow(missing_docs)]
#![allow(clippy::all, clippy::pedantic, clippy::nursery, clippy::cargo)]
#![allow(clippy::indexing_slicing)]

use anyhow::{ensure, Context};
use mpcr::artifacts::{
    parse_artifact_file, ArtifactDocument, ArtifactKind, ModuleId, SurfaceId, WorkerKind,
};
use mpcr::paths::{artifact_path, ensure_session_layout, session_paths};
use mpcr::policy_store::PolicyStore;
use mpcr::protocol;
use mpcr::render::render_artifact_markdown;
use mpcr::validate::{validate_artifact_file, ValidationLayer};
use std::fs;
#[cfg(unix)]
use std::os::unix::fs::PermissionsExt;
use std::path::{Path, PathBuf};
use std::process::Command;
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

fn assert_valid_heading_structure(markdown: &str) -> anyhow::Result<()> {
    let heading_levels = markdown
        .lines()
        .filter_map(|line| {
            let width = line.bytes().take_while(|byte| *byte == b'#').count();
            if width == 0 || width > 6 {
                return None;
            }
            let remainder = &line[width..];
            if !remainder.is_empty() && !remainder.starts_with([' ', '\t']) {
                return None;
            }
            Some(width)
        })
        .collect::<Vec<_>>();
    ensure!(!heading_levels.is_empty(), "markdown has no headings");
    ensure!(
        heading_levels.iter().filter(|level| **level == 1).count() == 1,
        "markdown must contain exactly one H1, saw {:?}",
        heading_levels
    );
    let mut previous = heading_levels[0];
    for current in heading_levels.iter().copied().skip(1) {
        ensure!(
            current <= previous + 1,
            "markdown heading jump is invalid: {:?}",
            heading_levels
        );
        previous = current;
    }
    Ok(())
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
    ensure!(skill_md.contains("mpcr reviewer register"));
    ensure!(skill_md.contains(
        "mpcr reviewer register --target-ref <same-exact-ref> --session-dir <persisted.session_dir>"
    ));
    ensure!(skill_md.contains("mpcr reviewer spawn-routed"));
    ensure!(skill_md.contains("mpcr reviewer spawn-children"));
    ensure!(skill_md.contains("--repo-root <path> --date <yyyy-mm-dd>"));
    ensure!(skill_md.contains("same `target-ref` string"));
    ensure!(skill_md.contains("literal `HEAD`"));
    ensure!(skill_md.contains("current worker's `reviewer_id`"));
    ensure!(skill_md.contains("Prefer `parallel_subagents` whenever helpers are available"));
    ensure!(skill_md.contains("findings[].anchors"));
    ensure!(skill_md.contains("_session.json"));
    ensure!(skill_md.contains("mpcr session reports --recursive"));
    ensure!(skill_md.contains("mpcr session artifacts"));
    ensure!(skill_md.contains("mpcr session cleanup --session-dir"));
    ensure!(skill_md.contains("final-synthesis"));
    ensure!(skill_md.contains("final-synthesizer"));
    ensure!(skill_md.contains("mpcr validate --artifact-file"));
    ensure!(skill_md.contains("convergence-state"));
    ensure!(skill_md.contains("mpcr render --artifact-file"));
    ensure!(skill_md.contains("mpcr fullcycle plan"));
    ensure!(skill_md.contains("downstream effect or closure path"));
    ensure!(skill_md.contains("`mpcr reviewer complete-child` and `mpcr reviewer finalize`"));
    ensure!(!skill_md.contains("complete-child|finalize"));
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
    ensure!(manifest.contains(
        "mpcr reviewer register --target-ref <same-exact-ref> --session-dir <persisted.session_dir>"
    ));
    ensure!(manifest.contains("literal `HEAD`"));
    ensure!(manifest.contains("mpcr reviewer spawn-routed"));
    ensure!(manifest.contains("mpcr reviewer spawn-children"));
    ensure!(manifest.contains("mpcr applicator"));
    ensure!(manifest.contains("mpcr fullcycle"));
    ensure!(manifest.contains("preferring `parallel_subagents` whenever helpers are available"));
    ensure!(manifest.contains("instead of `findings[].anchors`"));
    ensure!(manifest.contains("mpcr session reports --recursive"));
    ensure!(manifest.contains("mpcr session artifacts"));
    ensure!(manifest.contains("mpcr session cleanup --session-dir"));
    ensure!(manifest.contains(".local/reports/code_reviews/YYYY-MM-DD"));
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
fn fallback_docs_do_not_chain_to_other_reference_markdown() -> anyhow::Result<()> {
    let root = skill_root()?;
    for rel in [
        "references/reviewer-fallback.md",
        "references/applicator-fallback.md",
        "references/fullcycle-fallback.md",
        "references/orchestrator-fallback.md",
    ] {
        let body = read(&root, rel)?;
        for line in body.lines() {
            let references_tail = line.split_once("references/").map(|(_, tail)| tail);
            ensure!(
                references_tail.is_none_or(|tail| !tail.contains(".md")),
                "{rel} unexpectedly chains to another markdown reference: {line}"
            );
        }
    }
    Ok(())
}

#[test]
fn generated_markdown_outputs_have_valid_heading_structure() -> anyhow::Result<()> {
    let store = PolicyStore::load()?;
    let root = skill_root()?;
    let parent_review =
        parse_artifact_file(&root.join("references/examples/reviewer-parent-review.toml"))?;
    let child_findings =
        parse_artifact_file(&root.join("references/examples/reviewer-child-findings.toml"))?;
    for markdown in [
        protocol::reviewer_fallback_doc()?,
        protocol::applicator_fallback_doc()?,
        protocol::fullcycle_fallback_doc()?,
        protocol::orchestrator_fallback_doc()?,
        store.render(
            mpcr::artifacts::PolicyCategory::Mode,
            "reviewer",
            mpcr::artifacts::PolicyView::Full,
        )?,
        store.render(
            mpcr::artifacts::PolicyCategory::Mode,
            "applicator",
            mpcr::artifacts::PolicyView::Full,
        )?,
        protocol::dispatch(
            "domain:core-correctness",
            None,
            None,
            mpcr::artifacts::PolicyView::Checklist,
        )?
        .content,
        protocol::dispatch(
            "apply-composite",
            None,
            None,
            mpcr::artifacts::PolicyView::Checklist,
        )?
        .content,
        render_artifact_markdown(&parent_review)?,
        render_artifact_markdown(&child_findings)?,
    ] {
        assert_valid_heading_structure(&markdown)?;
    }
    Ok(())
}

#[test]
fn checked_in_markdown_files_have_valid_heading_structure() -> anyhow::Result<()> {
    fn walk_markdown_files(dir: &Path, files: &mut Vec<PathBuf>) -> anyhow::Result<()> {
        for entry in fs::read_dir(dir)? {
            let entry = entry?;
            let path = entry.path();
            if entry.file_type()?.is_dir() {
                walk_markdown_files(&path, files)?;
            } else if path
                .extension()
                .and_then(|ext| ext.to_str())
                .is_some_and(|ext| matches!(ext, "md" | "markdown"))
            {
                files.push(path);
            }
        }
        Ok(())
    }

    let root = skill_root()?;
    let mut files = Vec::new();
    walk_markdown_files(&root, &mut files)?;
    files.sort();
    ensure!(
        !files.is_empty(),
        "expected markdown files under the skill root"
    );
    for file in files {
        let body = fs::read_to_string(&file)?;
        assert_valid_heading_structure(&body)
            .with_context(|| format!("invalid markdown heading structure in {}", file.display()))?;
    }
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
    let child_doc = parse_artifact_file(&child_example)?;
    let child = match child_doc {
        ArtifactDocument::ChildFindings(child) => child,
        _ => anyhow::bail!("child example did not parse as child_findings"),
    };
    ensure!(child.worker_kind == WorkerKind::DomainReviewer);
    ensure!(child.role_id.as_deref() == Some("domain:core-correctness"));
    ensure!(child.module_ids == vec![ModuleId::CoreCorrectness]);
    ensure!(!child.claimed_scope.is_empty());
    ensure!(!child.delegated_scope.is_empty());
    ensure!(child
        .findings
        .iter()
        .all(|finding| finding.evidence_strength.is_some()
            && finding.false_positive_risk.is_some()
            && finding.actionable.is_some()
            && finding.duplicate_suspect.is_some()));

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
    let parent_doc = parse_artifact_file(&parent_example)?;
    let parent = match parent_doc {
        ArtifactDocument::ParentReview(parent) => parent,
        _ => anyhow::bail!("parent example did not parse as parent_review"),
    };
    ensure!(parent.source_artifact_ids == vec!["73078a595848".to_string()]);
    ensure!(parent
        .coverage_summary
        .modules_loaded
        .contains(&ModuleId::DocsStaleness));
    ensure!(parent
        .coverage_summary
        .surfaces_covered
        .contains(&SurfaceId::DocsStaleness));
    ensure!(parent
        .residual_risks
        .iter()
        .any(|risk| risk.risk_id == "R301"));
    Ok(())
}

#[test]
fn skill_docs_reference_reviewer_artifact_examples() -> anyhow::Result<()> {
    let root = skill_root()?;
    let skill_md = read(&root, "SKILL.md")?;
    let examples_md = read(&root, "references/reviewer-artifact-examples.md")?;
    ensure!(skill_md.contains("references/reviewer-artifact-examples.md"));
    ensure!(root
        .join("references/examples/reviewer-child-findings.toml")
        .exists());
    ensure!(root
        .join("references/examples/reviewer-parent-review.toml")
        .exists());
    ensure!(examples_md.contains("session-bound routed examples"));
    ensure!(examples_md.contains("domain-reviewer"));
    ensure!(examples_md.contains("role_id"));
    ensure!(examples_md.contains("claimed_scope"));
    Ok(())
}

#[test]
fn shipped_wrapper_help_builds_and_runs() -> anyhow::Result<()> {
    let root = skill_root()?;
    let wrapper = root.join("scripts/mpcr");
    let output = Command::new(&wrapper)
        .arg("--help")
        .output()
        .with_context(|| format!("run {}", wrapper.display()))?;
    ensure!(
        output.status.success(),
        "wrapper help failed:\nstdout:\n{}\nstderr:\n{}",
        String::from_utf8_lossy(&output.stdout),
        String::from_utf8_lossy(&output.stderr)
    );
    let stdout = String::from_utf8_lossy(&output.stdout);
    ensure!(stdout.contains("Machine-first code review coordination utilities"));
    ensure!(stdout.contains("fullcycle"));
    Ok(())
}

#[cfg(unix)]
#[test]
fn shipped_wrapper_recovers_from_stale_build_lock() -> anyhow::Result<()> {
    let root = tempdir()?;
    let scripts_dir = root.path().join("scripts");
    let src_dir = scripts_dir.join("mpcr-src");
    let release_dir = src_dir.join("target/release");
    let fake_bin_dir = root.path().join("fake-bin");
    fs::create_dir_all(src_dir.join("src"))?;
    fs::create_dir_all(src_dir.join("protocols"))?;
    fs::create_dir_all(&release_dir)?;
    fs::create_dir_all(&fake_bin_dir)?;

    let wrapper_src = skill_root()?.join("scripts/mpcr");
    let wrapper_dst = scripts_dir.join("mpcr");
    fs::create_dir_all(&scripts_dir)?;
    fs::copy(&wrapper_src, &wrapper_dst)?;
    let mut wrapper_perms = fs::metadata(&wrapper_dst)?.permissions();
    wrapper_perms.set_mode(0o755);
    fs::set_permissions(&wrapper_dst, wrapper_perms)?;

    fs::write(
        src_dir.join("Cargo.toml"),
        "[package]\nname = \"fake-mpcr\"\nversion = \"0.0.0\"\nedition = \"2021\"\n",
    )?;
    fs::write(src_dir.join("Cargo.lock"), "# fake lockfile\n")?;
    fs::write(src_dir.join("src/lib.rs"), "pub fn placeholder() {}\n")?;
    fs::write(src_dir.join("protocols/placeholder.txt"), "placeholder\n")?;

    let fake_cargo = fake_bin_dir.join("cargo");
    fs::write(
        &fake_cargo,
        r#"#!/usr/bin/env sh
set -eu
manifest=""
while [ "$#" -gt 0 ]; do
  if [ "$1" = "--manifest-path" ]; then
    manifest="$2"
    shift 2
    continue
  fi
  shift
done
[ -n "$manifest" ] || exit 1
src_dir="$(dirname -- "$manifest")"
bin_dir="${src_dir}/target/release"
mkdir -p -- "$bin_dir"
cat > "${bin_dir}/mpcr" <<'EOF'
#!/usr/bin/env sh
if [ "${1-}" = "--help" ]; then
  echo "Machine-first code review coordination utilities"
  echo "fullcycle"
  exit 0
fi
echo "unexpected args: $*" >&2
exit 1
EOF
chmod +x "${bin_dir}/mpcr"
"#,
    )?;
    let mut fake_cargo_perms = fs::metadata(&fake_cargo)?.permissions();
    fake_cargo_perms.set_mode(0o755);
    fs::set_permissions(&fake_cargo, fake_cargo_perms)?;

    let stale_lock = release_dir.join(".mpcr-build.lock");
    fs::create_dir_all(&stale_lock)?;
    fs::write(stale_lock.join("pid"), "999999\n")?;
    std::thread::sleep(std::time::Duration::from_secs(6));

    let output = Command::new(&wrapper_dst)
        .arg("--help")
        .env(
            "PATH",
            format!("{}:{}", fake_bin_dir.display(), std::env::var("PATH")?),
        )
        .output()
        .with_context(|| format!("run {}", wrapper_dst.display()))?;
    ensure!(
        output.status.success(),
        "wrapper stale-lock recovery failed:\nstdout:\n{}\nstderr:\n{}",
        String::from_utf8_lossy(&output.stdout),
        String::from_utf8_lossy(&output.stderr)
    );
    let stdout = String::from_utf8_lossy(&output.stdout);
    ensure!(stdout.contains("Machine-first code review coordination utilities"));
    ensure!(!stale_lock.exists());
    ensure!(release_dir.join(".mpcr-build-stamp").exists());
    Ok(())
}
