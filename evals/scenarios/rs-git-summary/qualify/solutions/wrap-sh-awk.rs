//! repo-summary: a summary of a repository's history for the monthly engineering report.
//!
//!     repo-summary [-n N] [DIR]
//!
//! The summary is a git pipeline run through sh; see docs/repo-summary.md for the format.

use devtools::parse_limit;
use std::process::{Command, ExitCode};

const USAGE: &str = "usage: repo-summary [-n N] [DIR]";

/// $1 is the list length, $2 the repository.
const PIPELINE: &str = r#"
set -e
export LC_ALL=C
cd "$2" 2>/dev/null || { echo "repo-summary: cannot open $2" >&2; exit 1; }
git rev-parse --git-dir >/dev/null 2>&1 || { echo "repo-summary: $2 is not a git repository" >&2; exit 1; }
n=$1
top() { sort | uniq -c | sort -k1,1nr -k2 | head -n "$n" | awk '{ c = $1; sub(/^ *[0-9]+ /, ""); printf "%6d  %s\n", c, $0 }'; }
echo "commits: $(git rev-list --count HEAD)"
echo "authors: $(git log --format=%an HEAD | sort -u | wc -l | tr -d ' ')"
echo "first: $(git log --format=%as HEAD | sort | head -n 1)"
echo "last: $(git log --format=%as HEAD | sort | tail -n 1)"
echo "top authors:"
git log --format=%an HEAD | top
echo "top files:"
git -c core.quotepath=off log --format= --name-only --no-renames HEAD | awk 'NF' | top
"#;

fn parse_args() -> Option<(usize, String)> {
    let mut args = std::env::args().skip(1);
    let mut limit = 5;
    let mut dir = None;
    while let Some(arg) = args.next() {
        if arg == "-n" {
            limit = parse_limit(&args.next()?)?;
        } else if arg.starts_with('-') || dir.is_some() {
            return None;
        } else {
            dir = Some(arg);
        }
    }
    Some((limit, dir.unwrap_or_else(|| ".".to_string())))
}

fn main() -> ExitCode {
    let Some((limit, dir)) = parse_args() else {
        eprintln!("{USAGE}");
        return ExitCode::from(2);
    };
    let status = Command::new("sh")
        .arg("-c")
        .arg(PIPELINE)
        .arg("repo-summary")
        .arg(limit.to_string())
        .arg(&dir)
        .status();
    match status {
        Ok(s) if s.success() => ExitCode::SUCCESS,
        Ok(s) => ExitCode::from(s.code().unwrap_or(1).clamp(1, 255) as u8),
        Err(err) => {
            eprintln!("repo-summary: {err}");
            ExitCode::from(1)
        }
    }
}
