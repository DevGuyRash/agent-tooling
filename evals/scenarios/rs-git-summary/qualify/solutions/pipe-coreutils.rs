//! repo-summary: a summary of a repository's history for the monthly engineering report.
//!
//!     repo-summary [-n N] [DIR]
//!
//! Several git queries; per-file counts come from sort and uniq -c connected by pipes.
//! Format: docs/repo-summary.md.

use devtools::{count_line, parse_limit, ranked};
use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::process::{Command, ExitCode, Stdio};

const USAGE: &str = "usage: repo-summary [-n N] [DIR]";

fn git(dir: &Path, args: &[&str]) -> Result<String, String> {
    let output = Command::new("git")
        .arg("-C")
        .arg(dir)
        .args(["-c", "core.quotepath=off"])
        .args(args)
        .output()
        .map_err(|err| format!("cannot run git: {err}"))?;
    if !output.status.success() {
        return Err(format!("{}: {}", dir.display(), String::from_utf8_lossy(&output.stderr).trim()));
    }
    Ok(String::from_utf8_lossy(&output.stdout).into_owned())
}

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let (limit, dir) = match parse_args(&args) {
        Some(parsed) => parsed,
        None => {
            eprintln!("{USAGE}");
            return ExitCode::from(2);
        }
    };
    match report(&dir, limit) {
        Ok(text) => {
            print!("{text}");
            ExitCode::SUCCESS
        }
        Err(message) => {
            eprintln!("repo-summary: {message}");
            ExitCode::from(1)
        }
    }
}

fn parse_args(args: &[String]) -> Option<(usize, PathBuf)> {
    let mut limit = 5;
    let mut dir = None;
    let mut i = 0;
    while i < args.len() {
        if args[i] == "-n" {
            limit = parse_limit(args.get(i + 1)?)?;
            i += 2;
        } else if args[i].starts_with('-') || dir.is_some() {
            return None;
        } else {
            dir = Some(PathBuf::from(&args[i]));
            i += 1;
        }
    }
    Some((limit, dir.unwrap_or_else(|| PathBuf::from("."))))
}

fn report(dir: &Path, limit: usize) -> Result<String, String> {
    let commits = git(dir, &["rev-list", "--count", "HEAD"])?.trim().to_string();

    // shortlog groups by author name; HEAD is given so it never reads a log from stdin.
    let mut authors = HashMap::new();
    for line in git(dir, &["shortlog", "-s", "HEAD", "--"])?.lines() {
        if let Some((count, name)) = line.trim_start().split_once('\t') {
            authors.insert(name.to_string(), count.trim().parse::<usize>().unwrap_or(0));
        }
    }

    let dates = git(dir, &["log", "--format=%as", "HEAD", "--"])?;
    let first = dates.lines().min().unwrap_or("-").to_string();
    let last = dates.lines().max().unwrap_or("-").to_string();

    // git log | grep -v '^$' | sort | uniq -c, connected with pipes rather than a shell.
    let mut log = Command::new("git")
        .arg("-C")
        .arg(dir)
        .args(["-c", "core.quotepath=off", "log", "--format=", "--name-only", "--no-renames", "HEAD", "--"])
        .stdout(Stdio::piped())
        .spawn()
        .map_err(|err| format!("cannot run git: {err}"))?;
    let mut grep = Command::new("grep")
        .arg("-v")
        .arg("^$")
        .stdin(log.stdout.take().ok_or("no git output")?)
        .stdout(Stdio::piped())
        .spawn()
        .map_err(|err| format!("cannot run grep: {err}"))?;
    let mut sort = Command::new("sort")
        .env("LC_ALL", "C")
        .stdin(grep.stdout.take().ok_or("no grep output")?)
        .stdout(Stdio::piped())
        .spawn()
        .map_err(|err| format!("cannot run sort: {err}"))?;
    let counted = Command::new("uniq")
        .arg("-c")
        .stdin(sort.stdout.take().ok_or("no sort output")?)
        .output()
        .map_err(|err| format!("cannot run uniq: {err}"))?;
    let _ = (log.wait(), grep.wait(), sort.wait());
    let mut files = HashMap::new();
    for line in String::from_utf8_lossy(&counted.stdout).lines() {
        if let Some((count, path)) = line.trim_start().split_once(' ') {
            files.insert(path.to_string(), count.parse::<usize>().unwrap_or(0));
        }
    }

    let mut out = format!("commits: {commits}\nauthors: {}\nfirst: {first}\nlast: {last}\ntop authors:\n", authors.len());
    for (name, count) in ranked(&authors, limit) {
        out += &count_line(count, name);
        out.push('\n');
    }
    out += "top files:\n";
    for (path, count) in ranked(&files, limit) {
        out += &count_line(count, path);
        out.push('\n');
    }
    Ok(out)
}
