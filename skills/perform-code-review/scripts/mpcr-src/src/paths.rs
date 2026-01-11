//! Path helpers for `mpcr` sessions and report filenames.
//!
//! Session directories are stored under:
//! `{repo_root}/.local/reports/code_reviews/{YYYY-MM-DD}/`

use std::path::{Path, PathBuf};
use time::Date;

const MAX_REF_LEN: usize = 64;

#[derive(Debug, Clone)]
/// Resolved paths for a single session date under a given repo root.
pub struct SessionPaths {
    /// The session directory (contains `_session.json`, lock file, and report markdown).
    pub session_dir: PathBuf,
    /// The full path to `_session.json` within [`SessionPaths::session_dir`].
    pub session_file: PathBuf,
}

/// Compute the session directory and session file path for `repo_root` and `session_date`.
#[must_use]
pub fn session_paths(repo_root: &Path, session_date: Date) -> SessionPaths {
    let date = session_date.to_string();
    let session_dir = repo_root
        .join(".local")
        .join("reports")
        .join("code_reviews")
        .join(date);
    let session_file = session_dir.join("_session.json");
    SessionPaths {
        session_dir,
        session_file,
    }
}

/// Sanitize a target ref for use in filenames.
///
/// Keeps ASCII alphanumerics and `.` / `-` / `_`; everything else becomes `_`.
/// Leading/trailing underscores are trimmed and the final string is capped to 64 bytes.
#[must_use]
pub fn sanitize_ref(input: &str) -> String {
    let mut out = String::with_capacity(input.len());
    for ch in input.chars() {
        if ch.is_ascii_alphanumeric() || matches!(ch, '.' | '-' | '_') {
            out.push(ch);
        } else {
            out.push('_');
        }
    }
    let trimmed = out.trim_matches('_');
    let mut normalized = if trimmed.is_empty() {
        "ref".to_string()
    } else {
        trimmed.to_string()
    };
    if normalized.len() > MAX_REF_LEN {
        normalized.truncate(MAX_REF_LEN);
    }
    normalized
}

#[cfg(test)]
mod tests {
    use super::*;
    use time::Month;

    #[test]
    fn session_paths_and_sanitize_ref() -> anyhow::Result<()> {
        let root = Path::new("/repo/root");
        let date = Date::from_calendar_date(2026, Month::January, 11)?;
        let paths = session_paths(root, date);
        assert!(paths
            .session_dir
            .ends_with(Path::new(".local/reports/code_reviews/2026-01-11")));
        assert_eq!(
            paths.session_file,
            paths.session_dir.join("_session.json")
        );

        assert_eq!(sanitize_ref("refs/heads/main"), "refs_heads_main");
        assert_eq!(sanitize_ref("___"), "ref");
        assert_eq!(sanitize_ref("a.b-c_d"), "a.b-c_d");

        let long = "x".repeat(MAX_REF_LEN + 10);
        let sanitized = sanitize_ref(&long);
        assert_eq!(sanitized.len(), MAX_REF_LEN);

        Ok(())
    }
}
