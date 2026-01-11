use std::path::{Path, PathBuf};
use time::Date;

#[derive(Debug, Clone)]
pub struct SessionPaths {
    pub session_dir: PathBuf,
    pub session_file: PathBuf,
}

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
    const MAX_LEN: usize = 64;
    if normalized.len() > MAX_LEN {
        normalized.truncate(MAX_LEN);
    }
    normalized
}
