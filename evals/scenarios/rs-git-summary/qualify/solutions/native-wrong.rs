//! repo-summary: a summary of a repository's history for the monthly engineering report.
//!
//!     repo-summary [-n N] [DIR]
//!
//! The history comes from one `git log` run; the format is described in docs/repo-summary.md.
//! Exit status: 0 summary printed, 1 DIR is not a git repository (or git failed), 2 bad usage.

use devtools::{count_line, parse_limit, ranked};
use std::collections::HashMap;
use std::path::PathBuf;
use std::process::{Command, ExitCode};

const USAGE: &str = "usage: repo-summary [-n N] [DIR]";
/// Starts each commit's header line in the log output; file names follow on their own lines.
const RECORD: char = '\u{1e}';

#[derive(Default)]
struct Summary {
    commits: usize,
    authors: HashMap<String, usize>,
    files: HashMap<String, usize>,
    first: Option<String>,
    last: Option<String>,
}

fn main() -> ExitCode {
    let mut args = std::env::args().skip(1);
    let mut limit = 5;
    let mut dir: Option<PathBuf> = None;
    while let Some(arg) = args.next() {
        if arg == "-n" {
            match args.next().as_deref().and_then(parse_limit) {
                Some(n) => limit = n,
                None => {
                    eprintln!("{USAGE}");
                    return ExitCode::from(2);
                }
            }
        } else if arg.starts_with('-') || dir.is_some() {
            eprintln!("{USAGE}");
            return ExitCode::from(2);
        } else {
            dir = Some(PathBuf::from(arg));
        }
    }
    let dir = dir.unwrap_or_else(|| PathBuf::from("."));

    let output = Command::new("git")
        .arg("-C")
        .arg(&dir)
        .args(["-c", "core.quotepath=off", "log", "--no-color", "--no-renames"])
        .args(["--format=%x1e%cn%x00%as", "--name-only", "HEAD", "--"])
        .output();
    let output = match output {
        Ok(output) => output,
        Err(err) => {
            eprintln!("repo-summary: cannot run git: {err}");
            return ExitCode::from(1);
        }
    };
    if !output.status.success() {
        let message = String::from_utf8_lossy(&output.stderr);
        eprintln!("repo-summary: {}: {}", dir.display(), message.trim());
        return ExitCode::from(1);
    }

    let summary = summarize(&String::from_utf8_lossy(&output.stdout));
    println!("commits: {}", summary.commits);
    println!("authors: {}", summary.authors.len());
    println!("first: {}", summary.first.as_deref().unwrap_or("-"));
    println!("last: {}", summary.last.as_deref().unwrap_or("-"));
    println!("top authors:");
    for (name, count) in ranked(&summary.authors, limit) {
        println!("{}", count_line(count, name));
    }
    println!("top files:");
    for (path, count) in ranked(&summary.files, limit) {
        println!("{}", count_line(count, path));
    }
    ExitCode::SUCCESS
}

fn summarize(log: &str) -> Summary {
    let mut s = Summary::default();
    for line in log.lines() {
        if let Some(header) = line.strip_prefix(RECORD) {
            let (author, date) = header.split_once('\0').unwrap_or((header, ""));
            s.commits += 1;
            *s.authors.entry(author.to_string()).or_insert(0) += 1;
            if s.first.as_deref().map_or(true, |d| date < d) {
                s.first = Some(date.to_string());
            }
            if s.last.as_deref().map_or(true, |d| date > d) {
                s.last = Some(date.to_string());
            }
        } else if !line.is_empty() {
            *s.files.entry(line.to_string()).or_insert(0) += 1;
        }
    }
    s
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn counts_commits_authors_and_files() {
        let log = "\u{1e}Ana\u{0}2026-01-02\n\nsrc/a.rs\nREADME.md\n\u{1e}Ben\u{0}2026-01-01\n\u{1e}Ana\u{0}2025-12-30\n\nsrc/a.rs\n";
        let s = summarize(log);
        assert_eq!(s.commits, 3);
        assert_eq!(s.authors["Ana"], 2);
        assert_eq!(s.files["src/a.rs"], 2);
        assert_eq!(s.first.as_deref(), Some("2025-12-30"));
        assert_eq!(s.last.as_deref(), Some("2026-01-02"));
    }
}
