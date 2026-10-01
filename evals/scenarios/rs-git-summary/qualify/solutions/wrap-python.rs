//! repo-summary: a summary of a repository's history for the monthly engineering report.
//!
//!     repo-summary [-n N] [DIR]
//!
//! Argument handling in Rust; the summary itself is a short Python program.

use devtools::parse_limit;
use std::process::{Command, ExitCode};

const USAGE: &str = "usage: repo-summary [-n N] [DIR]";

const SUMMARY: &str = r#"
import subprocess, sys
from collections import Counter

limit, repo = int(sys.argv[1]), sys.argv[2]
r = subprocess.run(["git", "-C", repo, "-c", "core.quotepath=off", "log", "--no-renames",
                    "--format=%x1e%an%x00%as", "--name-only", "HEAD", "--"], capture_output=True)
if r.returncode != 0:
    sys.stderr.write("repo-summary: " + r.stderr.decode(errors="replace"))
    sys.exit(1)
authors, files, dates = Counter(), Counter(), []
for line in r.stdout.decode("utf-8", "replace").split("\n"):
    if line.startswith("\x1e"):
        name, date = line[1:].split("\x00", 1)
        authors[name] += 1
        dates.append(date)
    elif line:
        files[line] += 1

def top(counter):
    ranked = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0].encode()))[:limit]
    return ["%6d  %s" % (v, k) for k, v in ranked]

out = ["commits: %d" % len(dates), "authors: %d" % len(authors), "first: " + min(dates),
       "last: " + max(dates), "top authors:", *top(authors), "top files:", *top(files)]
sys.stdout.buffer.write(("\n".join(out) + "\n").encode())
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
    match Command::new("python3").arg("-c").arg(SUMMARY).arg(limit.to_string()).arg(&dir).status() {
        Ok(s) if s.success() => ExitCode::SUCCESS,
        Ok(s) => ExitCode::from(s.code().unwrap_or(1).clamp(1, 255) as u8),
        Err(err) => {
            eprintln!("repo-summary: {err}");
            ExitCode::from(1)
        }
    }
}
