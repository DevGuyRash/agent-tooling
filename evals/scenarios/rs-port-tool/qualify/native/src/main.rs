//! reqstat: summarize logfmt access logs by route, path, status class, or method.

mod logfmt;
mod report;

use std::fs;
use std::io::{self, Read, Write};
use std::process::ExitCode;

use logfmt::{parse_line, py_repr, valid_timestamp};
use report::{render_csv, render_table, By, Order, Summary};

const VERSION: &str = "1.4.0";

const USAGE: &str = "usage: reqstat [-h] [--by {route,path,status,method}] [--since SINCE]
               [--until UNTIL] [--min-count N]
               [--sort {count,p95,errors,name}] [--top N]
               [--format {table,csv}] [--strict] [--version]
               [FILE ...]
";

const HELP: &str = "
Summarize logfmt access logs by route, path, status class, or method.

positional arguments:
  FILE                  log files to read (standard input when none, or -)

options:
  -h, --help            show this help message and exit
  --by {route,path,status,method}
                        what to group requests by (default: route)
  --since SINCE         only requests at or after this time
  --until UNTIL         only requests before this time
  --min-count N         hide groups with fewer than N requests (default: 1)
  --sort {count,p95,errors,name}
                        row order (default: count)
  --top N               show only the first N rows (0: all)
  --format {table,csv}  output format (default: table)
  --strict              stop at the first malformed line instead of skipping
                        it
  --version             show program's version number and exit
";

struct Args {
    files: Vec<String>,
    by: By,
    since: Option<String>,
    until: Option<String>,
    min_count: u128,
    sort: Order,
    top: usize,
    csv: bool,
    strict: bool,
}

enum Cli {
    Run(Args),
    Exit(u8),
}

fn usage_error(message: &str) -> Cli {
    eprint!("{USAGE}");
    eprintln!("reqstat: error: {message}");
    Cli::Exit(2)
}

fn choices(names: &[&str]) -> String {
    names.iter().map(|n| format!("'{n}'")).collect::<Vec<_>>().join(", ")
}

fn timestamp_arg(text: &str) -> Result<String, String> {
    let mut ts = text.to_string();
    let b = text.as_bytes();
    let is_date = b.len() == 10
        && b[4] == b'-'
        && b[7] == b'-'
        && b.iter().enumerate().all(|(i, c)| i == 4 || i == 7 || c.is_ascii_digit());
    if is_date {
        ts.push_str("T00:00:00Z");
    }
    if !valid_timestamp(&ts) {
        return Err(format!("invalid timestamp {} (use YYYY-MM-DD or YYYY-MM-DDTHH:MM:SSZ)", py_repr(&ts)));
    }
    Ok(ts)
}

fn count_arg(text: &str, minimum: i128) -> Result<i128, String> {
    let value: i128 = text.trim().parse().map_err(|_| format!("invalid number {}", py_repr(text)))?;
    if value < minimum {
        return Err(format!("must be at least {minimum}"));
    }
    Ok(value)
}

const VALUE_OPTIONS: [&str; 7] = ["--by", "--since", "--until", "--min-count", "--sort", "--top", "--format"];

fn parse_args(argv: &[String]) -> Cli {
    let mut args = Args {
        files: Vec::new(),
        by: By::Route,
        since: None,
        until: None,
        min_count: 1,
        sort: Order::Count,
        top: 0,
        csv: false,
        strict: false,
    };
    let mut i = 0;
    let mut only_files = false;
    while i < argv.len() {
        let arg = &argv[i];
        i += 1;
        if only_files || arg == "-" || !arg.starts_with('-') {
            args.files.push(arg.clone());
            continue;
        }
        if arg == "--" {
            only_files = true;
            continue;
        }
        let (name, inline) = match arg.split_once('=') {
            Some((n, v)) if n.starts_with("--") => (n.to_string(), Some(v.to_string())),
            _ => (arg.clone(), None),
        };
        match name.as_str() {
            "-h" | "--help" => {
                print!("{USAGE}{HELP}");
                return Cli::Exit(0);
            }
            "--version" => {
                println!("reqstat {VERSION}");
                return Cli::Exit(0);
            }
            "--strict" => {
                if inline.is_some() {
                    return usage_error(&format!("argument --strict: ignored explicit argument {}", py_repr(inline.as_deref().unwrap())));
                }
                args.strict = true;
                continue;
            }
            _ => {}
        }
        if !VALUE_OPTIONS.contains(&name.as_str()) {
            return usage_error(&format!("unrecognized arguments: {arg}"));
        }
        let value = match inline {
            Some(v) => v,
            None => {
                if i >= argv.len() || (argv[i].starts_with('-') && argv[i] != "-") {
                    return usage_error(&format!("argument {name}: expected one argument"));
                }
                i += 1;
                argv[i - 1].clone()
            }
        };
        let result: Result<(), String> = match name.as_str() {
            "--by" => By::parse(&value).map(|b| args.by = b).ok_or_else(|| {
                format!("invalid choice: {} (choose from {})", py_repr(&value), choices(&By::NAMES))
            }),
            "--sort" => Order::parse(&value).map(|o| args.sort = o).ok_or_else(|| {
                format!("invalid choice: {} (choose from {})", py_repr(&value), choices(&Order::NAMES))
            }),
            "--format" => match value.as_str() {
                "table" => {
                    args.csv = false;
                    Ok(())
                }
                "csv" => {
                    args.csv = true;
                    Ok(())
                }
                _ => Err(format!("invalid choice: {} (choose from 'table', 'csv')", py_repr(&value))),
            },
            "--since" => timestamp_arg(&value).map(|t| args.since = Some(t)),
            "--until" => timestamp_arg(&value).map(|t| args.until = Some(t)),
            "--min-count" => count_arg(&value, 1).map(|n| args.min_count = n as u128),
            "--top" => count_arg(&value, 0).map(|n| args.top = n as usize),
            _ => unreachable!(),
        };
        if let Err(message) = result {
            return usage_error(&format!("argument {name}: {message}"));
        }
    }
    Cli::Run(args)
}

/// Lines as Python reads them: from files with universal newlines, from standard input split at "\n".
fn split_lines(text: &str, universal: bool) -> Vec<&str> {
    let mut lines = Vec::new();
    let bytes = text.as_bytes();
    let mut start = 0;
    let mut i = 0;
    while i < bytes.len() {
        let b = bytes[i];
        if b == b'\n' || (universal && b == b'\r') {
            lines.push(&text[start..i]);
            if universal && b == b'\r' && i + 1 < bytes.len() && bytes[i + 1] == b'\n' {
                i += 1;
            }
            start = i + 1;
        }
        i += 1;
    }
    if start < bytes.len() {
        lines.push(&text[start..]);
    }
    lines
}

fn strerror(e: &io::Error) -> String {
    let text = e.to_string();
    match text.rfind(" (os error ") {
        Some(pos) => text[..pos].to_string(),
        None => text,
    }
}

fn read_input(name: &str) -> Result<(String, bool), String> {
    let mut raw = Vec::new();
    if name == "-" {
        io::stdin().read_to_end(&mut raw).map_err(|e| format!("cannot read <stdin>: {}", strerror(&e)))?;
        return Ok((String::from_utf8_lossy(&raw).into_owned(), false));
    }
    let raw = fs::read(name).map_err(|e| format!("cannot read {name}: {}", strerror(&e)))?;
    Ok((String::from_utf8_lossy(&raw).into_owned(), true))
}

fn summarize(args: &Args) -> Result<Summary, String> {
    let mut summary = Summary::default();
    let stdin_only = vec!["-".to_string()];
    let files = if args.files.is_empty() { &stdin_only } else { &args.files };
    for name in files {
        let label = if name == "-" { "<stdin>" } else { name.as_str() };
        let (text, universal) = read_input(name)?;
        for (index, raw) in split_lines(&text, universal).into_iter().enumerate() {
            let line = raw.trim_end_matches(['\r', '\n']);
            let stripped = line.trim_matches([' ', '\t']);
            if stripped.is_empty() || stripped.starts_with('#') {
                continue;
            }
            let req = match parse_line(line) {
                Ok(req) => req,
                Err(e) if args.strict => return Err(format!("{label}:{}: {e}", index + 1)),
                Err(_) => {
                    summary.malformed += 1;
                    continue;
                }
            };
            if args.since.as_ref().is_some_and(|s| req.ts < *s) || args.until.as_ref().is_some_and(|u| req.ts >= *u) {
                continue;
            }
            summary.add(&req, args.by);
        }
    }
    Ok(summary)
}

fn main() -> ExitCode {
    let argv: Vec<String> = std::env::args().skip(1).collect();
    let args = match parse_args(&argv) {
        Cli::Run(args) => args,
        Cli::Exit(code) => return ExitCode::from(code),
    };
    let summary = match summarize(&args) {
        Ok(summary) => summary,
        Err(message) => {
            eprintln!("reqstat: {message}");
            return ExitCode::from(1);
        }
    };
    let rows = summary.select(args.min_count, args.sort, args.top);
    let out = if args.csv { render_csv(&rows, args.by) } else { render_table(&summary, &rows, args.by) };
    if io::stdout().write_all(out.as_bytes()).is_err() {
        return ExitCode::from(1);
    }
    ExitCode::SUCCESS
}
