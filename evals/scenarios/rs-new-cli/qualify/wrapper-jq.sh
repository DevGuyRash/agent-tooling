# Shell one-liner wrapper (must fail runs_without_interpreter): main.rs runs `sh -c` with a jq pipeline that
# streams the document's leaves, and formats keys and values in Rust. jq also loses duplicate members and
# rewrites some numbers, so it fails some hidden cases even with interpreters present.
set -e
mkdir -p crates/envflat/src
cat > crates/envflat/Cargo.toml <<'TOML'
[package]
name = "envflat"
version.workspace = true
edition.workspace = true
publish.workspace = true
TOML
cat > crates/envflat/src/main.rs <<'RS'
//! envflat: turn a JSON settings file into an environment file.

use std::process::{Command, ExitCode, Stdio};

fn component(name: &str) -> String {
    name.chars().map(|c| if c.is_ascii_alphanumeric() { c.to_ascii_uppercase() } else { '_' }).collect()
}

fn main() -> ExitCode {
    let mut args: Vec<String> = std::env::args().skip(1).collect();
    let mut prefix = None;
    if args.first().map(String::as_str) == Some("--prefix") {
        if args.len() < 2 {
            eprintln!("envflat: --prefix needs a NAME");
            return ExitCode::from(2);
        }
        prefix = Some(component(&args[1]));
        args.drain(..2);
    }
    if args.len() > 1 || args.first().is_some_and(|a| a.starts_with('-') && a != "-") {
        eprintln!("envflat: usage: envflat [--prefix NAME] [FILE]");
        return ExitCode::from(2);
    }
    let file = args.pop().unwrap_or_else(|| "-".into());
    let out = Command::new("sh")
        .arg("-c")
        .arg(r#"jq -e -c 'if type == "object" then . else error("the document is not an object") end | paths(scalars) as $p | [$p, getpath($p)]' "$0""#)
        .arg(&file)
        .stdin(Stdio::inherit())
        .output();
    let out = match out {
        Ok(o) if o.status.success() => o,
        Ok(o) => {
            eprintln!("envflat: {}", String::from_utf8_lossy(&o.stderr).trim());
            return ExitCode::from(1);
        }
        Err(e) => {
            eprintln!("envflat: {e}");
            return ExitCode::from(1);
        }
    };
    let mut lines = Vec::new();
    let mut seen = std::collections::HashSet::new();
    for row in String::from_utf8_lossy(&out.stdout).lines() {
        let inner = &row[2..row.len() - 1];
        let (path, value) = inner.split_once("],").unwrap_or((inner, ""));
        let mut parts: Vec<String> = prefix.iter().cloned().collect();
        parts.extend(path.split(',').map(|p| component(p.trim_matches('"'))));
        let key = parts.join("__");
        if !seen.insert(key.clone()) {
            eprintln!("envflat: duplicate key {key}");
            return ExitCode::from(1);
        }
        let value = match value {
            "null" => String::new(),
            v if v.starts_with('"') => {
                let s = v[1..v.len() - 1].replace("\\\"", "\"").replace("\\\\", "\\");
                if !s.is_empty() && s.chars().all(|c| c.is_ascii_alphanumeric() || "_-./:@+,%".contains(c)) {
                    s
                } else {
                    format!("'{}'", s.replace('\'', r"'\''"))
                }
            }
            v => v.to_string(),
        };
        lines.push(format!("{key}={value}"));
    }
    for line in lines {
        println!("{line}");
    }
    ExitCode::SUCCESS
}
RS
sed -i 's|members = \["crates/lineup"\]|members = ["crates/lineup", "crates/envflat"]|' Cargo.toml
git add -A
git commit -q -m "Add envflat"
