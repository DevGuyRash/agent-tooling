//! Path helpers for the canonical v2 session layout.

use crate::artifacts::ArtifactKind;
use anyhow::Context;
use std::path::{Path, PathBuf};
use time::Date;

const REPORTS_ROOT: &str = ".local/reports/code_reviews";
const SCRATCH_ROOT: &str = ".local/tmp/code-review";

#[derive(Debug, Clone, PartialEq, Eq)]
/// Resolved canonical paths for a single session day.
pub struct SessionPaths {
    /// Session day directory.
    pub session_dir: PathBuf,
    /// Compact session ledger file.
    pub session_file: PathBuf,
    /// Session lock file.
    pub lock_file: PathBuf,
    /// Canonical artifacts root.
    pub artifacts_dir: PathBuf,
    /// Rendered markdown root.
    pub rendered_dir: PathBuf,
}

/// Resolve canonical session paths for `repo_root` and `session_date`.
#[must_use]
pub fn session_paths(repo_root: &Path, session_date: Date) -> SessionPaths {
    let session_dir = repo_root.join(REPORTS_ROOT).join(session_date.to_string());
    SessionPaths {
        session_file: session_dir.join("_session.toml"),
        lock_file: session_dir.join("_session.toml.lock"),
        artifacts_dir: session_dir.join("artifacts"),
        rendered_dir: session_dir.join("rendered"),
        session_dir,
    }
}

/// Resolve the canonical scratch root for non-canonical intermediate files.
#[must_use]
pub fn scratch_dir(repo_root: &Path) -> PathBuf {
    repo_root.join(SCRATCH_ROOT)
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

/// Compute the canonical artifact path for `artifact_id`.
#[must_use]
pub fn artifact_path(session_dir: &Path, kind: ArtifactKind, artifact_id: &str) -> PathBuf {
    artifact_dir(session_dir, kind).join(format!("{artifact_id}.toml"))
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
    for kind in ArtifactKind::all() {
        std::fs::create_dir_all(artifact_dir(session_dir, kind))
            .with_context(|| format!("create artifact dir {}", kind.dir_name()))?;
        std::fs::create_dir_all(rendered_dir(session_dir, kind))
            .with_context(|| format!("create rendered dir {}", kind.dir_name()))?;
    }
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
    fn session_layout_and_artifact_paths_match_prd() -> anyhow::Result<()> {
        let root = Path::new("/repo/root");
        let date = Date::from_calendar_date(2026, Month::March, 8)?;
        let paths = session_paths(root, date);

        ensure!(paths
            .session_dir
            .ends_with(Path::new(".local/reports/code_reviews/2026-03-08")));
        ensure!(paths.session_file == paths.session_dir.join("_session.toml"));
        ensure!(paths.lock_file == paths.session_dir.join("_session.toml.lock"));
        ensure!(
            artifact_path(
                &paths.session_dir,
                ArtifactKind::ParentReview,
                "abc123def456"
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
        ensure!(scratch_dir(root) == root.join(".local/tmp/code-review"));
        ensure!(
            normalize_repo_relative(Path::new("./a/b/../c")) == "./a/b/../c".replace('\\', "/")
        );
        Ok(())
    }
}
