//! todo-count: how many TODO and FIXME markers a source tree has, and where.
//!
//!     todo-count [-n N] [DIR]
//!
//! DIR defaults to the current directory; -n is how many files to list (default 5).
//! Hidden files and directories, and `target`, are skipped. Exit status: 0 report printed,
//! 1 DIR cannot be read, 2 bad usage.

use devtools::{count_line, parse_limit, ranked};
use std::collections::HashMap;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::ExitCode;

const USAGE: &str = "usage: todo-count [-n N] [DIR]";

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
    let root = dir.unwrap_or_else(|| PathBuf::from("."));

    let mut per_file = HashMap::new();
    if let Err(err) = walk(&root, &root, &mut per_file) {
        eprintln!("todo-count: cannot read {}: {err}", root.display());
        return ExitCode::from(1);
    }
    let total: usize = per_file.values().sum();
    println!("markers: {total}");
    println!("files: {}", per_file.len());
    println!("top files:");
    for (name, count) in ranked(&per_file, limit) {
        println!("{}", count_line(count, name));
    }
    ExitCode::SUCCESS
}

fn walk(root: &Path, dir: &Path, per_file: &mut HashMap<String, usize>) -> std::io::Result<()> {
    let mut entries: Vec<_> = fs::read_dir(dir)?.collect::<Result<_, _>>()?;
    entries.sort_by_key(|e| e.file_name());
    for entry in entries {
        let name = entry.file_name();
        let name = name.to_string_lossy();
        if name.starts_with('.') || name == "target" {
            continue;
        }
        let path = entry.path();
        if entry.file_type()?.is_dir() {
            walk(root, &path, per_file)?;
        } else if let Ok(text) = fs::read_to_string(&path) {
            let n = text.matches("TODO").count() + text.matches("FIXME").count();
            if n > 0 {
                let rel = path.strip_prefix(root).unwrap_or(&path);
                per_file.insert(rel.to_string_lossy().into_owned(), n);
            }
        }
    }
    Ok(())
}
