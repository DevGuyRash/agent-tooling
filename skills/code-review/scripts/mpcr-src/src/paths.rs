//! Path helpers for the canonical session layout.

use crate::artifacts::ArtifactKind;
use anyhow::Context;
use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};
use time::Date;

const REPORTS_ROOT: &str = ".local/reports/code_reviews";
const SCRATCH_ROOT: &str = ".local/tmp/code-review";
const SESSION_JSON_FILE: &str = "_session.json";
const SESSION_TOML_FILE: &str = "_session.toml";
const SESSION_LOCK_FILE: &str = "_session.lock";
const LEGACY_SESSION_LOCK_FILES: &[&str] = &["_session.toml.lock", "_session.json.lock"];
const AGENT_JSON_FILE: &str = "_agent.json";
const AGENT_TOML_FILE: &str = "_agent.toml";
const AGENT_LOCK_FILE: &str = "_agent.lock";
const AGENT_CHILDREN_JSON_FILE: &str = "children.json";
const AGENT_CHILDREN_TOML_FILE: &str = "children.toml";
const AGENT_ARTIFACTS_JSON_FILE: &str = "_artifacts.json";
const AGENT_ARTIFACTS_TOML_FILE: &str = "_artifacts.toml";

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
/// Supported machine-readable storage formats.
pub enum StorageFormat {
    /// JSON primary storage.
    Json,
    /// TOML mirror or fallback storage.
    Toml,
}

impl StorageFormat {
    /// File extension for the format.
    #[must_use]
    pub const fn extension(self) -> &'static str {
        match self {
            Self::Json => "json",
            Self::Toml => "toml",
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
/// Resolved canonical paths for a single session day.
pub struct SessionPaths {
    /// Session day directory.
    pub session_dir: PathBuf,
    /// Primary JSON ledger file.
    pub session_json_file: PathBuf,
    /// Mirrored TOML ledger file.
    pub session_toml_file: PathBuf,
    /// Canonical lock file.
    pub lock_file: PathBuf,
    /// Compatibility lock files left behind by older versions.
    pub legacy_lock_files: Vec<PathBuf>,
    /// Canonical artifacts root.
    pub artifacts_dir: PathBuf,
    /// Rendered markdown root.
    pub rendered_dir: PathBuf,
    /// Root directory for recursive agent subdirectories.
    pub agents_dir: PathBuf,
    /// Recursive final report markdown.
    pub final_report_file: PathBuf,
    /// Machine-readable final summary in JSON.
    pub final_summary_json_file: PathBuf,
    /// Machine-readable final summary in TOML.
    pub final_summary_toml_file: PathBuf,
}

/// Resolve canonical session paths for `repo_root` and `session_date`.
#[must_use]
pub fn session_paths(repo_root: &Path, session_date: Date) -> SessionPaths {
    let session_dir = repo_root.join(REPORTS_ROOT).join(session_date.to_string());
    SessionPaths {
        session_json_file: session_dir.join(SESSION_JSON_FILE),
        session_toml_file: session_dir.join(SESSION_TOML_FILE),
        lock_file: session_dir.join(SESSION_LOCK_FILE),
        legacy_lock_files: legacy_lock_paths(&session_dir),
        artifacts_dir: session_dir.join("artifacts"),
        rendered_dir: session_dir.join("rendered"),
        agents_dir: session_dir.join("agents"),
        final_report_file: session_dir.join("final_report.md"),
        final_summary_json_file: session_dir.join("final_summary.json"),
        final_summary_toml_file: session_dir.join("final_summary.toml"),
        session_dir,
    }
}

/// Resolve the canonical scratch root for non-canonical intermediate files.
#[must_use]
pub fn scratch_dir(repo_root: &Path) -> PathBuf {
    repo_root.join(SCRATCH_ROOT)
}

/// Resolve the canonical session ledger path for `format`.
#[must_use]
pub fn session_file(session_dir: &Path, format: StorageFormat) -> PathBuf {
    match format {
        StorageFormat::Json => session_dir.join(SESSION_JSON_FILE),
        StorageFormat::Toml => session_dir.join(SESSION_TOML_FILE),
    }
}

/// Resolve compatibility lock paths for `session_dir`.
#[must_use]
pub fn legacy_lock_paths(session_dir: &Path) -> Vec<PathBuf> {
    LEGACY_SESSION_LOCK_FILES
        .iter()
        .map(|name| session_dir.join(name))
        .collect()
}

/// Resolve the canonical agents root for `session_dir`.
#[must_use]
pub fn agents_dir(session_dir: &Path) -> PathBuf {
    session_dir.join("agents")
}

/// Resolve a root agent directory.
#[must_use]
pub fn root_agent_dir(session_dir: &Path, agent_id: &str) -> PathBuf {
    agents_dir(session_dir).join(agent_id)
}

/// Resolve a nested child agent directory under `parent_agent_dir`.
#[must_use]
pub fn child_agent_dir(parent_agent_dir: &Path, child_id: &str) -> PathBuf {
    parent_agent_dir.join("children").join(child_id)
}

/// Resolve the agent ledger path for `format`.
#[must_use]
pub fn agent_ledger_path(agent_dir: &Path, format: StorageFormat) -> PathBuf {
    match format {
        StorageFormat::Json => agent_dir.join(AGENT_JSON_FILE),
        StorageFormat::Toml => agent_dir.join(AGENT_TOML_FILE),
    }
}

/// Resolve the agent children manifest path for `format`.
#[must_use]
pub fn agent_children_path(agent_dir: &Path, format: StorageFormat) -> PathBuf {
    match format {
        StorageFormat::Json => agent_dir.join(AGENT_CHILDREN_JSON_FILE),
        StorageFormat::Toml => agent_dir.join(AGENT_CHILDREN_TOML_FILE),
    }
}

/// Resolve the agent artifact manifest path for `format`.
#[must_use]
pub fn agent_artifacts_manifest_path(agent_dir: &Path, format: StorageFormat) -> PathBuf {
    match format {
        StorageFormat::Json => agent_dir.join(AGENT_ARTIFACTS_JSON_FILE),
        StorageFormat::Toml => agent_dir.join(AGENT_ARTIFACTS_TOML_FILE),
    }
}

/// Resolve the authored report path for an agent.
#[must_use]
pub fn agent_report_path(agent_dir: &Path) -> PathBuf {
    agent_dir.join("report.md")
}

/// Resolve the canonical per-agent lock path.
#[must_use]
pub fn agent_lock_path(agent_dir: &Path) -> PathBuf {
    agent_dir.join(AGENT_LOCK_FILE)
}

/// Resolve the canonical artifact directory for `kind`.
#[must_use]
pub fn artifact_dir(session_dir: &Path, kind: ArtifactKind) -> PathBuf {
    session_dir.join("artifacts").join(kind.dir_name())
}

/// Resolve the canonical rendered directory for `kind`.
#[must_use]
pub fn rendered_dir(session_dir: &Path, kind: ArtifactKind) -> PathBuf {
    session_dir.join("rendered").join(kind.dir_name())
}

/// Compute the canonical artifact path for `artifact_id` and `format`.
#[must_use]
pub fn artifact_path(
    session_dir: &Path,
    kind: ArtifactKind,
    artifact_id: &str,
    format: StorageFormat,
) -> PathBuf {
    artifact_dir(session_dir, kind).join(format!("{artifact_id}.{}", format.extension()))
}

/// Resolve the preferred existing artifact path, preferring JSON over TOML.
#[must_use]
pub fn existing_artifact_path(
    session_dir: &Path,
    kind: ArtifactKind,
    artifact_id: &str,
) -> Option<PathBuf> {
    let json = artifact_path(session_dir, kind, artifact_id, StorageFormat::Json);
    if json.exists() {
        return Some(json);
    }
    let toml = artifact_path(session_dir, kind, artifact_id, StorageFormat::Toml);
    if toml.exists() {
        return Some(toml);
    }
    None
}

/// Compute the canonical rendered markdown path for `artifact_id`.
#[must_use]
pub fn rendered_path(session_dir: &Path, kind: ArtifactKind, artifact_id: &str) -> PathBuf {
    rendered_dir(session_dir, kind).join(format!("{artifact_id}.md"))
}

/// Create the canonical session layout if it does not exist.
///
/// # Errors
/// Returns an error if any directory cannot be created.
pub fn ensure_session_layout(session_dir: &Path) -> anyhow::Result<()> {
    std::fs::create_dir_all(session_dir)
        .with_context(|| format!("create session dir {}", session_dir.display()))?;
    std::fs::create_dir_all(session_dir.join("artifacts"))
        .with_context(|| format!("create artifacts root {}", session_dir.display()))?;
    std::fs::create_dir_all(session_dir.join("rendered"))
        .with_context(|| format!("create rendered root {}", session_dir.display()))?;
    std::fs::create_dir_all(agents_dir(session_dir))
        .with_context(|| format!("create agents root {}", session_dir.display()))?;
    for kind in ArtifactKind::all() {
        std::fs::create_dir_all(artifact_dir(session_dir, kind))
            .with_context(|| format!("create artifact dir {}", kind.dir_name()))?;
        std::fs::create_dir_all(rendered_dir(session_dir, kind))
            .with_context(|| format!("create rendered dir {}", kind.dir_name()))?;
    }
    Ok(())
}

/// Create the canonical directory scaffold for an agent dir.
///
/// # Errors
/// Returns an error if the directories cannot be created.
pub fn ensure_agent_layout(agent_dir: &Path) -> anyhow::Result<()> {
    std::fs::create_dir_all(agent_dir)
        .with_context(|| format!("create agent dir {}", agent_dir.display()))?;
    std::fs::create_dir_all(agent_dir.join("children"))
        .with_context(|| format!("create agent children dir {}", agent_dir.display()))?;
    Ok(())
}

/// Convert `path` into a repo-relative string using `/` separators.
///
/// # Errors
/// Returns an error if `path` is not under `repo_root`.
pub fn repo_relative_path(repo_root: &Path, path: &Path) -> anyhow::Result<String> {
    let relative = path.strip_prefix(repo_root).with_context(|| {
        format!(
            "path {} is not under {}",
            path.display(),
            repo_root.display()
        )
    })?;
    Ok(normalize_repo_relative(relative))
}

/// Normalize a repo-relative path to `/` separators without a leading `./`.
#[must_use]
pub fn normalize_repo_relative(path: &Path) -> String {
    path.components()
        .map(|component| component.as_os_str().to_string_lossy().into_owned())
        .collect::<Vec<_>>()
        .join("/")
}

/// Resolve a repo-relative path against `repo_root`.
#[must_use]
pub fn resolve_repo_relative(repo_root: &Path, repo_relative: &str) -> PathBuf {
    repo_root.join(repo_relative.replace('\\', "/"))
}

#[cfg(test)]
mod tests {
    use super::*;
    use anyhow::ensure;
    use time::Month;

    #[test]
    fn session_layout_and_artifact_paths_match_contract() -> anyhow::Result<()> {
        let root = Path::new("/repo/root");
        let date = Date::from_calendar_date(2026, Month::March, 8)?;
        let paths = session_paths(root, date);

        ensure!(paths
            .session_dir
            .ends_with(Path::new(".local/reports/code_reviews/2026-03-08")));
        ensure!(paths.session_json_file == paths.session_dir.join("_session.json"));
        ensure!(paths.session_toml_file == paths.session_dir.join("_session.toml"));
        ensure!(paths.lock_file == paths.session_dir.join("_session.lock"));
        ensure!(
            paths.legacy_lock_files
                == vec![
                    paths.session_dir.join("_session.toml.lock"),
                    paths.session_dir.join("_session.json.lock"),
                ]
        );
        ensure!(
            artifact_path(
                &paths.session_dir,
                ArtifactKind::ParentReview,
                "abc123def456",
                StorageFormat::Json
            ) == paths
                .session_dir
                .join("artifacts/parent_review/abc123def456.json")
        );
        ensure!(
            artifact_path(
                &paths.session_dir,
                ArtifactKind::ParentReview,
                "abc123def456",
                StorageFormat::Toml
            ) == paths
                .session_dir
                .join("artifacts/parent_review/abc123def456.toml")
        );
        ensure!(
            rendered_path(
                &paths.session_dir,
                ArtifactKind::VerificationResult,
                "abc123def456"
            ) == paths
                .session_dir
                .join("rendered/verification_result/abc123def456.md")
        );
        ensure!(
            root_agent_dir(&paths.session_dir, "deadbeef")
                == paths.session_dir.join("agents/deadbeef")
        );
        ensure!(
            child_agent_dir(&root_agent_dir(&paths.session_dir, "deadbeef"), "cafebabe")
                == paths.session_dir.join("agents/deadbeef/children/cafebabe")
        );
        ensure!(scratch_dir(root) == root.join(".local/tmp/code-review"));
        ensure!(
            normalize_repo_relative(Path::new("./a/b/../c")) == "./a/b/../c".replace('\\', "/")
        );
        Ok(())
    }
}
